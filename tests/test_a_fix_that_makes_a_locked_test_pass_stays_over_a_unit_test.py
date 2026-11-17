"""A fix that makes a locked test pass and breaks only unit tests stays, and each unit test is raised naming the locked one.

Measured on one run: a locked test asked for a JSON content type on a route, a unit test written earlier asserted the
route's body was empty, and three fixes in a row were reverted for that unit test, so the criterion was never reached.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app import ci
from app.graph import engineering

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
LOCKED = "[AC-3] GET /health answers JSON"
UNIT = "health route has an empty body"


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("UNIT_TESTS_YIELD_TO_THE_LOCKED_SUITE", "on")


def _snapshot(unit, acceptance, **more):
    return ci.Snapshot(label="s", unit=unit, unit_ran=True, acceptance=acceptance, acceptance_ran=True, **more)


BEFORE = _snapshot({UNIT: "passed"}, {LOCKED: "failed", "[AC-1] other": "passed"})
GAINED = _snapshot({UNIT: "failed"}, {LOCKED: "passed", "[AC-1] other": "passed"})


def _after_the_fix(monkeypatch, root, before, after):
    monkeypatch.setattr(engineering, "ci_applies", lambda _: True)
    monkeypatch.setattr(ci, "load", lambda _root, _which: before)
    monkeypatch.setattr(ci, "take", lambda _root, _label: after)
    monkeypatch.setattr(ci, "save", lambda _root, _snap, **_kw: None)
    monkeypatch.setattr(ci, "commit", lambda _root, _message: "c0ffee")
    reverted = []
    monkeypatch.setattr(ci, "revert_to", lambda _root, base: reverted.append(base) or True)
    broke = engineering.after_a_fix(str(root), "abc", "defect_fix_1_0", "[AC-3] health")
    return broke, reverted


def _state(root):
    return {"repository": SimpleNamespace(root_path=str(root))}


def test_the_fix_stays_when_a_locked_test_passes_and_only_a_unit_test_broke(monkeypatch, tmp_path):
    assert _after_the_fix(monkeypatch, tmp_path, BEFORE, GAINED) == ([], [])


def test_the_unit_test_is_raised_naming_the_locked_test(monkeypatch, tmp_path):
    from app.graph import workflow

    _after_the_fix(monkeypatch, tmp_path, BEFORE, GAINED)
    [defect] = workflow._the_unit_tests_a_kept_fix_broke(_state(tmp_path))["review_defects"]

    assert defect.description.startswith(f"Regression: `unit: {UNIT}` passed before")
    assert workflow._A_REGRESSED_TEST.match(defect.description), "closed when that unit test passes again"
    assert "disagrees with the locked test" in defect.actual_behavior and LOCKED in defect.actual_behavior
    assert "AC-3" not in defect.description, "a criterion's id here would judge it by that criterion's tests"
    text = " ".join([defect.description, defect.actual_behavior, defect.expected_behavior, defect.reproduction_steps])
    assert not BANNED.search(text)
    assert workflow._the_unit_tests_a_kept_fix_broke(_state(tmp_path)) == {}, "raised once"


def test_each_broken_unit_test_is_raised_and_what_the_round_holds_stays(monkeypatch, tmp_path):
    from app.graph import workflow

    before = _snapshot({"u1": "passed", "u2": "passed"}, {LOCKED: "failed"})
    after = _snapshot({"u1": "failed", "u2": "failed"}, {LOCKED: "passed"})
    _after_the_fix(monkeypatch, tmp_path, before, after)
    state = {**_state(tmp_path), "review_defects": ["held"]}

    raised = workflow._the_unit_tests_a_kept_fix_broke(state)["review_defects"]

    assert raised[0] == "held" and len(raised) == 3


def test_a_fix_that_also_broke_a_locked_test_is_reverted(monkeypatch, tmp_path):
    after = _snapshot({UNIT: "failed"}, {LOCKED: "passed", "[AC-1] other": "failed"})
    broke, reverted = _after_the_fix(monkeypatch, tmp_path, BEFORE, after)
    assert set(broke) == {f"unit: {UNIT}", "acceptance: [AC-1] other"} and reverted == ["abc"]


def test_a_fix_that_made_no_locked_test_pass_is_reverted(monkeypatch, tmp_path):
    after = _snapshot({UNIT: "failed", "new unit test": "passed"}, {LOCKED: "failed", "[AC-1] other": "passed"})
    broke, reverted = _after_the_fix(monkeypatch, tmp_path, BEFORE, after)
    assert broke == [f"unit: {UNIT}"] and reverted == ["abc"]


def test_a_locked_test_the_last_measurement_did_not_show_failing_is_no_gain(monkeypatch, tmp_path):
    after = _snapshot({UNIT: "failed"}, {"[AC-1] other": "passed", "[AC-8] never measured": "passed"})
    before = _snapshot({UNIT: "passed"}, {"[AC-1] other": "passed"})
    broke, reverted = _after_the_fix(monkeypatch, tmp_path, before, after)
    assert broke == [f"unit: {UNIT}"] and reverted == ["abc"]


def test_a_fix_after_which_the_product_does_not_start_is_reverted(monkeypatch, tmp_path):
    after = _snapshot({UNIT: "failed"}, {LOCKED: "passed", "[AC-1] other": "passed"}, problem="no server")
    _, reverted = _after_the_fix(monkeypatch, tmp_path, BEFORE, after)
    assert reverted == ["abc"]


def test_a_fix_that_stopped_the_unit_runner_is_reverted(monkeypatch, tmp_path):
    after = ci.Snapshot(label="s", unit={}, unit_ran=False, acceptance={LOCKED: "passed", "[AC-1] other": "passed"},
                        acceptance_ran=True)
    _, reverted = _after_the_fix(monkeypatch, tmp_path, BEFORE, after)
    assert reverted == ["abc"]


def test_off_the_fix_is_reverted_as_before_and_nothing_is_raised(monkeypatch, tmp_path):
    from app.graph import workflow

    monkeypatch.setenv("UNIT_TESTS_YIELD_TO_THE_LOCKED_SUITE", "off")
    broke, reverted = _after_the_fix(monkeypatch, tmp_path, BEFORE, GAINED)
    assert broke == [f"unit: {UNIT}"] and reverted == ["abc"]
    assert workflow._the_unit_tests_a_kept_fix_broke(_state(tmp_path)) == {}


def test_a_kept_fix_is_not_also_kept_as_a_candidate_for_a_replay(monkeypatch, tmp_path):
    """`KEPT_FIX_CANDIDATES` looks only at what is reverted."""
    monkeypatch.setattr(engineering, "ci_applies", lambda _: True)
    monkeypatch.setattr(ci, "load", lambda _root, _which: BEFORE)
    monkeypatch.setattr(ci, "take", lambda _root, _label: GAINED)
    monkeypatch.setattr(ci, "save", lambda _root, _snap, **_kw: None)
    monkeypatch.setattr(ci, "commit", lambda _root, _message: "c0ffee")
    seen = []
    assert engineering.after_a_fix(str(tmp_path), "abc", "s", "d", on_revert=seen.append) == [] and seen == []


# --- where the graph carries it: from a kept fix, alone or in a batch, to the next round ------------------------


def _kept_over_a_unit_test(monkeypatch, root):
    """`engineering.after_a_fix` measures BEFORE then GAINED: the fix stays and the unit test is recorded."""
    monkeypatch.setattr(engineering, "ci_applies", lambda _: True)
    monkeypatch.setattr(engineering, "before_a_fix", lambda *_a, **_k: "abc")
    monkeypatch.setattr(ci, "load", lambda _root, _which: BEFORE)
    monkeypatch.setattr(ci, "take", lambda _root, _label: GAINED)
    monkeypatch.setattr(ci, "save", lambda _root, _snap, **_kw: None)
    monkeypatch.setattr(ci, "commit", lambda _root, _message: "c0ffee")
    monkeypatch.setattr(ci, "revert_to", lambda _root, base: pytest.fail("the fix was reverted"))


def _a_fix_state(root, **more):
    from app.sprint import Defect, RemediationCycle

    defect = Defect(description=f"{LOCKED} fails", severity="major", reproduction_steps="r", expected_behavior="e",
                    actual_behavior="a", owner="backend", failing_criteria=["AC-3"], affected_files=["app/health.js"])
    return {
        "repository": SimpleNamespace(root_path=str(root)), "remediation": RemediationCycle(sprint_goal="g", defects=[defect]),
        "defect_cursor": 0, "test_round": 1, "current_sprint_index": 0, "specialist_outputs": {}, "review_defects": [],
        **more,
    }


def _graph(root):
    from langgraph.checkpoint.memory import MemorySaver

    from app.graph.workflow import build_workflow_graph

    return build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(root))


def _raised(update):
    return [d.description for d in update.get("review_defects") or []]


def test_a_fix_alone_hands_the_unit_test_to_the_next_round(monkeypatch, tmp_path):
    """The node's update goes where the regressions of a batch go: read by the round, cleared by it."""
    from unittest.mock import MagicMock, patch

    from app.agents.specialists import SpecialistOutput

    _kept_over_a_unit_test(monkeypatch, tmp_path)
    answer = SpecialistOutput(changed_files=["app/health.js"], tests=["tests/health.test.js"], decisions=["JSON"])
    with patch("app.graph.workflow._fixes_run_side_by_side", return_value=False), \
         patch("app.graph.workflow.create_specialist_agent", return_value=MagicMock()), \
         patch("app.graph.workflow.build_defect_fix_request", return_value={"messages": [{"role": "user", "content": ""}]}), \
         patch("app.graph.workflow._what_the_last_failure_printed", return_value=""), \
         patch("app.graph.workflow._closed_if_an_earlier_fix_resolved_it", return_value=None), \
         patch("app.graph.workflow._what_the_ledger_confirms", return_value="npm test"), \
         patch("app.graph.acceptance_nodes.done_by_the_definition", return_value=[]), \
         patch("app.graph.workflow._run_gated_agent", return_value={"__fix_result__": answer}):
        update = _graph(tmp_path).nodes["defect_remediation"].bound.invoke(
            _a_fix_state(tmp_path), {"configurable": {"thread_id": "t", "run_id": "r"}})

    assert _raised(update) == [f"Regression: `unit: {UNIT}` passed before a fix was kept, and fails now."]


def test_a_batch_hands_the_unit_test_to_the_next_round(monkeypatch, tmp_path):
    from app.agents.specialists import SpecialistOutput

    _kept_over_a_unit_test(monkeypatch, tmp_path)
    answer = SpecialistOutput(changed_files=["app/health.js"], tests=["tests/health.test.js"], decisions=["JSON"])
    state = _a_fix_state(tmp_path, fix_batch=[0], fix_base_commit="abc",
                         specialist_outputs={"defect_fix_1_0": answer})
    from unittest.mock import patch

    with patch("app.graph.workflow._what_the_ledger_confirms", return_value="npm test"), \
         patch("app.graph.acceptance_nodes.done_by_the_definition", return_value=[]):
        update = _graph(tmp_path).nodes["defect_fix_gather"].bound.invoke(
            state, {"configurable": {"thread_id": "t", "run_id": "r"}})

    assert _raised(update) == [f"Regression: `unit: {UNIT}` passed before a fix was kept, and fails now."]


def test_the_next_round_takes_what_was_raised_as_a_review_defect(monkeypatch, tmp_path):
    """The next test round reads what was raised among its defects, and clears it."""
    from unittest.mock import patch

    from app.agents.specialists import SpecialistOutput
    from app.graph import workflow

    _after_the_fix(monkeypatch, tmp_path, BEFORE, GAINED)
    raised = workflow._the_unit_tests_a_kept_fix_broke(_state(tmp_path))["review_defects"]
    milestone = SimpleNamespace(selected_sprint_goal="Build features", milestone_scope=[], delegated_tasks=[])
    state = {
        **_state(tmp_path), "milestone_plan": milestone, "test_round": 2, "specialist_outputs": {},
        "review_defects": raised, "current_sprint_index": 0,
    }
    with patch("app.graph.acceptance_nodes.acceptance_for_round", return_value=("", [])), \
         patch("app.graph.acceptance_nodes.reopen_the_suite_for", return_value=None), \
         patch("app.graph.acceptance_nodes.beyond_repair", return_value=[]), \
         patch("app.graph.acceptance_nodes._failing_due", return_value=([], "npx playwright test")), \
         patch("app.graph.workflow._run_unit_tests_procedurally", return_value=(False, "AssertionError")), \
         patch("app.graph.acceptance_nodes.suite.is_locked", return_value=True), \
         patch("app.graph.acceptance_nodes.suite.last_result", return_value={"ran": True, "passed": 2, "failed": 0}), \
         patch("app.agents.specialists.what_the_files_already_prove", return_value=[]), \
         patch("app.graph.acceptance_nodes.interface_defects", return_value=[]), \
         patch("app.graph.acceptance_nodes.failing_due_defects", return_value=[]), \
         patch("app.graph.workflow._with_the_contract_s_server_errors", side_effect=lambda s, result, m: result), \
         patch("app.acceptance.order_probe.at_a_green_round"), \
         patch("app.graph.workflow._run_gated_agent", return_value={"__test_result__": SpecialistOutput()}):
        result = _graph(tmp_path).nodes["test_and_triage"].bound.invoke(
            state, {"configurable": {"thread_id": "t", "run_id": "r"}})

    assert [d.description for d in result["remediation"].defects if d.status == "open"] == [raised[0].description]
    assert result["review_defects"] == []
