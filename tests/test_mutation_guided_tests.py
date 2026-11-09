"""A deliberate change no test notices is a finding for the testing role, settled by the harness (plan QM.2).

Behind `MUTATION_GUIDED_TESTS`, off. The release probe reported such changes
as a completion gap nobody acted on: measured on one finished run, the locked
suite noticed 6 of 10 and the product shipped with no test holding it to the
other four. With the switch on, a sprint whose due criteria pass is probed on
the sources it changed, each survivor is one finding for the testing role, and
the finding is settled only when the unit tests fail with the change and pass
without it - measured, never taken from a named test. Off, nothing changes.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.acceptance import mutation, mutation_guided
from app.agents.specialists import SpecialistOutput
from app.sprint import RemediationCycle, recurrence_of

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

SOURCE = "def over(a, b):\n    return a > b\n"


@pytest.fixture
def product(tmp_path, monkeypatch):
    """A workspace with one source file and a pack whose suite drives no browser."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calc.py").write_text(SOURCE, encoding="utf-8")
    monkeypatch.setattr(
        "app.stacks.contract.the_pack",
        lambda root: (SimpleNamespace(kind="python_service", kept_files=[]), {"project": ""}),
    )
    return tmp_path


def _a_site(product: Path) -> dict:
    return {"file": "src/calc.py", "line": 2, "column": 13, "original": ">", "replacement": "<=",
            "text": "    return a > b"}


def _unit_tests_that_notice(product: Path):
    """Unit tests that fail while the comparison is turned round, pass otherwise."""
    return lambda: "a <= b" not in (product / "src" / "calc.py").read_text(encoding="utf-8")


# --- the probe -------------------------------------------------------------


def test_a_change_no_test_notices_becomes_one_finding_for_the_testing_role(product):
    survivors = mutation_guided.probe(product, ["src/calc.py"], count=1, run_unit=lambda: True)

    assert [(s["file"], s["line"], s["original"], s["replacement"]) for s in survivors] == [
        ("src/calc.py", 2, ">", "<=")]
    assert (product / "src" / "calc.py").read_text(encoding="utf-8") == SOURCE
    found = mutation_guided.defect(survivors[0])
    assert found.owner == "testing" and found.source == "mutation" and found.status == "open"
    assert "`src/calc.py` line 2" in found.description and "`>` made `<=`" in found.description
    assert "no test holds the product to that behaviour" in found.description
    assert "fails with that change and passes without it" in found.expected_behavior
    assert found.affected_files == [] and not found.regression_test_required
    for text in (found.description, found.reproduction_steps, found.expected_behavior, found.actual_behavior,
                 mutation_guided.what_settles_it(found)):
        assert not BANNED.search(text), text


def test_a_change_the_unit_tests_notice_is_no_finding(product):
    assert mutation_guided.probe(product, ["src/calc.py"], count=1, run_unit=_unit_tests_that_notice(product)) == []


def test_only_the_sources_the_sprint_changed_are_probed(product):
    assert mutation_guided.probe(product, ["src/other.py"], run_unit=lambda: True) == []


def test_a_suite_that_drives_a_browser_is_not_probed(product, monkeypatch):
    monkeypatch.setattr(
        "app.stacks.contract.the_pack",
        lambda root: (SimpleNamespace(kind="browser_app", kept_files=[]), {"project": ""}),
    )
    assert mutation_guided.probe(product, ["src/calc.py"], run_unit=lambda: True) == []


def test_unit_tests_failing_already_probe_nothing(product):
    assert mutation_guided.probe(product, ["src/calc.py"], run_unit=lambda: False) == []


def test_a_change_the_locked_suite_notices_is_no_finding(product):
    held = {"keeps the comparison"}
    suite = lambda: set() if "a <= b" in (product / "src" / "calc.py").read_text() else held  # noqa: E731
    assert mutation_guided.probe(product, ["src/calc.py"], count=1, run_unit=lambda: True, run_suite=suite) == []


def test_at_most_a_few_findings_a_sprint(product):
    (product / "src" / "calc.py").write_text(
        "".join(f"def f{i}(a, b):\n    return a > b and True\n" for i in range(6)), encoding="utf-8")
    survivors = mutation_guided.probe(product, ["src/calc.py"], count=12, run_unit=lambda: True)
    assert len(survivors) == mutation_guided.MOST_FINDINGS


# --- files are always put back ---------------------------------------------


def test_the_file_is_put_back_when_the_test_command_raises(product):
    calls = []

    def run_unit():
        calls.append(1)
        if len(calls) == 1:
            return True  # the product as it is
        raise RuntimeError("the runner died")

    assert mutation_guided.probe(product, ["src/calc.py"], count=1, run_unit=run_unit) == []
    assert (product / "src" / "calc.py").read_text(encoding="utf-8") == SOURCE
    assert not (product / mutation.JOURNAL).exists()


def test_the_settle_check_puts_the_file_back_when_the_test_command_raises(product):
    finding = mutation_guided.defect(_a_site(product))

    def run_unit():
        raise RuntimeError("the runner died")

    assert mutation_guided.settled(product, finding, run_unit=run_unit) is None
    assert (product / "src" / "calc.py").read_text(encoding="utf-8") == SOURCE
    assert not (product / mutation.JOURNAL).exists()


def test_a_change_a_dead_worker_left_is_put_back_before_the_check(product):
    finding = mutation_guided.defect(_a_site(product))
    mutation._journal_before_changing(product, product, _a_site(product))
    assert "a <= b" in (product / "src" / "calc.py").read_text()

    mutation_guided.settled(product, finding, run_unit=lambda: True)

    assert (product / "src" / "calc.py").read_text(encoding="utf-8") == SOURCE


# --- settling a finding ------------------------------------------------------


def test_settled_only_when_the_unit_tests_fail_with_the_change_and_pass_without_it(product):
    finding = mutation_guided.defect(_a_site(product))

    assert mutation_guided.settled(product, finding, run_unit=_unit_tests_that_notice(product)) is True
    assert mutation_guided.settled(product, finding, run_unit=lambda: True) is False
    assert mutation_guided.settled(product, finding, run_unit=lambda: False) is False
    assert (product / "src" / "calc.py").read_text(encoding="utf-8") == SOURCE


def test_a_line_moved_by_the_fix_is_still_found(product):
    finding = mutation_guided.defect(_a_site(product))
    (product / "src" / "calc.py").write_text("import math\n\n" + SOURCE, encoding="utf-8")

    assert mutation_guided.settled(product, finding, run_unit=_unit_tests_that_notice(product)) is True
    assert (product / "src" / "calc.py").read_text(encoding="utf-8") == "import math\n\n" + SOURCE


def test_a_line_the_fix_rewrote_cannot_settle_it(product):
    finding = mutation_guided.defect(_a_site(product))
    (product / "src" / "calc.py").write_text("def over(a, b):\n    return b < a\n", encoding="utf-8")

    assert mutation_guided.settled(product, finding, run_unit=lambda: False) is None


def _settle(product: Path, result: SpecialistOutput, *, tries: int = 0):
    from app.graph.workflow import _settle_the_fix

    finding = mutation_guided.defect(_a_site(product)).model_copy(update={"fix_attempts": tries})
    cycle = RemediationCycle(sprint_goal="g", defects=[finding])
    state = {"repository": SimpleNamespace(root_path=str(product)), "specialist_outputs": {}, "test_round": 2}
    update, blames = _settle_the_fix(state, cycle, 0, "defect_fix_2_0", result, measured="after defect_fix_2_0")
    return update["remediation"].defects[0], blames


def test_a_fix_is_recorded_fixed_on_the_harness_s_check_not_on_a_named_test(product):
    with patch.object(mutation_guided, "settled", return_value=True):
        fixed, blames = _settle(product, SpecialistOutput(changed_files=["tests/test_calc.py"]))
    assert fixed.status == "fixed" and fixed.verified_by == "the harness's mutation check" and not blames

    with patch.object(mutation_guided, "settled", return_value=False):
        left, _ = _settle(product, SpecialistOutput(changed_files=["tests/test_calc.py"], tests=["test_over"]))
    assert left.status == "open" and left.fix_attempts == 1


def test_a_finding_its_tries_could_not_settle_is_a_gap_not_an_escalation(product):
    with patch.object(mutation_guided, "settled", return_value=False):
        closed, _ = _settle(product, SpecialistOutput(changed_files=["tests/test_calc.py"]),
                            tries=mutation_guided.MOST_TRIES - 1)
    assert closed.status == "accepted_risk" and closed.accepted_risk_reason.startswith(mutation_guided.A_GAP)
    assert "`src/calc.py` line 2" in mutation_guided.the_gap(closed)


def test_a_change_the_fixer_shows_behaves_the_same_is_closed_as_equivalent(product):
    said = SpecialistOutput(decisions=["Equivalent: both comparisons agree for every input the function can be given"])
    with patch.object(mutation_guided, "settled", return_value=False):
        closed, _ = _settle(product, said)
    assert closed.status == "accepted_risk" and closed.accepted_risk_reason.startswith(mutation_guided.EQUIVALENT)
    assert mutation_guided.the_gap(closed) == ""

    with patch.object(mutation_guided, "settled", return_value=False):
        bare, _ = _settle(product, SpecialistOutput(decisions=["Equivalent: yes"]))
    assert bare.status == "open"


def test_a_round_with_no_room_closes_the_open_findings_as_gaps(product):
    from app.graph.workflow import _mutation_findings_set_aside

    finding = mutation_guided.defect(_a_site(product))
    cycle = RemediationCycle(sprint_goal="g", defects=[finding], attempt=2, max_attempts=3)
    after, gaps = _mutation_findings_set_aside({"mutation_gaps": ["an earlier sprint's"]}, cycle, 4)

    assert after.defects[0].status == "accepted_risk"
    assert gaps[0] == "an earlier sprint's" and "`src/calc.py` line 2" in gaps[1]


def test_two_findings_in_one_file_are_two_problems_not_one_restated(product):
    first = mutation_guided.defect(_a_site(product)).model_copy(update={"status": "fixed", "regression_test": "x"})
    second = mutation_guided.defect({**_a_site(product), "line": 7, "column": 4, "text": "    x = a > b"})
    assert recurrence_of(second, [first]) is None


def test_the_fixer_is_told_what_settles_it_instead_of_the_regression_clause(product):
    from app.agents.specialists import build_defect_fix_request

    finding = mutation_guided.defect(_a_site(product))
    request = build_defect_fix_request(
        finding.description, finding.reproduction_steps, finding.expected_behavior, finding.actual_behavior,
        finding.affected_files, finding.regression_test_required, str(product),
        what_settles_it=mutation_guided.what_settles_it(finding),
    )
    text = request["messages"][-1]["content"]
    assert "--- What settles this finding ---" in text and "A regression test is not required" not in text
    assert mutation_guided.what_settles_it(SimpleNamespace(source="test round")) == ""


# --- where it runs in the graph, and that off changes nothing ----------------


def _a_clean_round(tmp_path, state_extra=None):
    from langgraph.checkpoint.memory import MemorySaver

    from app.graph.workflow import build_workflow_graph

    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "milestone_plan": SimpleNamespace(selected_sprint_goal="Build features", milestone_scope=[], delegated_tasks=[]),
        "test_round": 1,
        "specialist_outputs": {},
        "review_defects": [],
        "current_sprint_index": 0,
        **(state_extra or {}),
    }
    with patch("app.graph.acceptance_nodes.acceptance_for_round", return_value=("All passed", [])), \
         patch("app.graph.acceptance_nodes.reopen_the_suite_for", return_value=None), \
         patch("app.graph.acceptance_nodes.beyond_repair", return_value=[]), \
         patch("app.graph.acceptance_nodes._failing_due", return_value=([], "npm test")), \
         patch("app.graph.workflow._run_unit_tests_procedurally", return_value=(True, "")), \
         patch("app.graph.acceptance_nodes.suite.is_locked", return_value=True), \
         patch("app.graph.acceptance_nodes.suite.last_result", return_value={"ran": True}), \
         patch("app.agents.specialists.what_the_files_already_prove", return_value=[]), \
         patch("app.graph.acceptance_nodes.interface_defects", return_value=[]), \
         patch("app.graph.acceptance_nodes.failing_due_defects", return_value=[]), \
         patch("app.graph.workflow._the_files_this_milestone_changed", return_value=["src/calc.py"]), \
         patch.object(mutation_guided, "probe", return_value=[_a_site(tmp_path)]) as probe:
        graph = build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))
        result = graph.nodes["test_and_triage"].bound.invoke(state, {"configurable": {"thread_id": "t", "run_id": "r"}})
    return result, probe


def test_off_a_clean_round_routes_to_the_reviews_as_before_and_probes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("MUTATION_GUIDED_TESTS", raising=False)
    assert not mutation_guided.enabled()

    result, probe = _a_clean_round(tmp_path)

    assert not probe.called
    assert result["stage"] == "security_review"
    assert "mutation_probed" not in result and "mutation_gaps" not in result
    assert not any(mutation_guided.is_a_finding(d) for d in result["remediation"].defects)


def test_on_a_clean_round_hands_the_findings_to_the_testing_role_once_per_sprint_attempt(tmp_path, monkeypatch):
    monkeypatch.setenv("MUTATION_GUIDED_TESTS", "on")

    result, probe = _a_clean_round(tmp_path)

    assert probe.called and result["stage"] == "defect_remediation" and result["defect_cursor"] == 0
    assert result["mutation_probed"] == ["0:0"]
    [finding] = [d for d in result["remediation"].defects if d.status == "open"]
    assert finding.source == "mutation" and finding.owner == "testing"

    again, probe = _a_clean_round(tmp_path, {"mutation_probed": ["0:0"]})
    assert not probe.called and again["stage"] == "security_review"

    released, probe = _a_clean_round(tmp_path, {"mutation_probed": ["0:0"], "sprint_replan_count": 1,
                                                "release_attempts": 1})
    assert not probe.called and released["stage"] == "security_review"


def test_the_release_lists_the_findings_left_as_gaps():
    import inspect

    from app.graph import delivery

    assert 'gaps.extend(state.get("mutation_gaps") or [])' in inspect.getsource(delivery.release)


# --- beside unit tests that already fail -------------------------------------
# Measured on every run of one day: the switch was on and never probed, because some unit test the model wrote
# always failed and the probe asked that all of them pass first. The unit tests are measured as the set that passes.

def _passing_unless_turned_round(product: Path, notices: bool):
    """`kept` passes always, `broken` never; `compares` passes unless the comparison is turned round (when it notices)."""
    def run():
        turned = "a <= b" in (product / "src" / "calc.py").read_text(encoding="utf-8")
        return {"kept"} | ({"compares"} if not (notices and turned) else set())
    return run


def test_a_change_no_test_notices_is_found_beside_a_unit_test_that_already_fails(product):
    survivors = mutation_guided.probe(product, ["src/calc.py"], count=1,
                                      run_unit=_passing_unless_turned_round(product, notices=False))

    assert [(s["line"], s["original"], s["replacement"]) for s in survivors] == [(2, ">", "<=")]


def test_a_change_that_makes_a_passing_unit_test_fail_is_noticed_beside_a_failing_one(product):
    assert mutation_guided.probe(product, ["src/calc.py"], count=1,
                                 run_unit=_passing_unless_turned_round(product, notices=True)) == []


def test_settled_beside_a_unit_test_that_already_fails(product):
    finding = mutation_guided.defect(_a_site(product))

    assert mutation_guided.settled(product, finding, run_unit=_passing_unless_turned_round(product, notices=True)) is True
    assert mutation_guided.settled(product, finding, run_unit=_passing_unless_turned_round(product, notices=False)) is False


def test_only_unit_test_failures_open_beside_a_green_suite_is_where_the_probe_also_runs(tmp_path, monkeypatch):
    """Measured on every run of one day: the probe ran only with nothing open, and a failing unit test the model
    wrote was nearly always open, so a sprint whose criteria all passed was never probed."""
    from app.graph import acceptance_nodes, workflow

    unit = SimpleNamespace(status="open", description="The unit tests fail. It says: x", caught_by="", failing_criteria=[])
    criterion = SimpleNamespace(status="open", description="[AC-5] Delete a note - the acceptance suite says ...",
                                caught_by="npx playwright test", failing_criteria=["AC-5"])
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}
    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda state: ([], "npx playwright test"))
    monkeypatch.setattr("app.acceptance.suite.last_result", lambda root: {"ran": True, "passed": 9, "failed": 0})

    assert workflow._only_unit_tests_open_beside_a_green_suite(state, SimpleNamespace(defects=[unit])) is True
    assert workflow._only_unit_tests_open_beside_a_green_suite(state, SimpleNamespace(defects=[unit, criterion])) is False
    assert workflow._only_unit_tests_open_beside_a_green_suite(state, SimpleNamespace(defects=[])) is False


def test_the_round_asks_for_the_probe_before_it_sends_unit_test_failures_to_a_fixer():
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    at = source.index("_only_unit_tests_open_beside_a_green_suite(state, cycle)")
    assert at < source.index('return _handing_on(**base_update, stage="defect_remediation", defect_cursor=0)', at - 2000)
