"""The stages between an approved architecture and the sprint plan.

scaffold -> acceptance_author -> acceptance_review -> [user review] -> scrum_master,
and the acceptance gate the test rounds and the milestone review read.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.acceptance import junit, suite
from app.acceptance.criteria import number
from app.graph import acceptance_nodes as nodes

BRIEF = """# Brief
## Features
- Add a note
- Delete a note
## Acceptance Criteria
- Notes persist between page refreshes
"""


def _state(root: Path, **extra: Any) -> dict[str, Any]:
    (root / ".project-directory").write_text("notes\n")
    (root / "notes").mkdir(exist_ok=True)
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "document": SimpleNamespace(text=BRIEF),
        "product_intake": SimpleNamespace(product_name="Notes", success_measures=[]),
        "stack_selection": SimpleNamespace(technology_stack=SimpleNamespace(product_kind="browser_app")),
        **extra,
    }


CONFIG = {"configurable": {"thread_id": "t"}}
CTX = nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=None)


@pytest.fixture
def gated(monkeypatch):
    """`_run_gated_agent` answering with whatever the test queues, per stage prefix."""
    answers: dict[str, list[Any]] = {}
    asked: list[str] = []

    def run(state, config, *, stage_name, agent, initial_request, output_key, next_stage):
        asked.append(stage_name)
        prefix = stage_name.rsplit("_", 1)[0]
        return {output_key: answers[prefix].pop(0), "stage": next_stage}

    monkeypatch.setattr("app.graph.workflow._run_gated_agent", run)
    monkeypatch.setattr("app.agents.specialists.create_specialist_agent", lambda *a, **k: object())
    monkeypatch.setattr(
        "app.agents.acceptance_reviewer.create_acceptance_reviewer_agent", lambda *a, **k: object()
    )
    return SimpleNamespace(answers=answers, asked=asked)


def _ran(passed_names=(), failed_names=()) -> suite.AcceptanceResult:
    report = junit.Report(found=True, tests=[
        *(junit.TestResult(name=n) for n in passed_names),
        *(junit.TestResult(name=n, outcome="failed", message="nope") for n in failed_names),
    ])
    return suite.AcceptanceResult(ran=True, exit_code=1, command="npm run test:acceptance", report=report)


def test_scaffold_proves_the_pack_and_records_the_decision(tmp_path, monkeypatch) -> None:
    calls = []

    def fake(root, pack, project, title, package=None):
        calls.append((pack.name, project, title))
        return SimpleNamespace(ok=True, problem="")

    monkeypatch.setattr("app.stacks.scaffold.scaffold", fake)
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)

    update = nodes.scaffold(_state(tmp_path, stack_pack="browser-javascript"), CONFIG, CTX)

    assert calls == [("browser-javascript", "notes", "Notes")]
    assert update["stage"] == "acceptance_author"
    assert update["scaffold_result"]["ok"]
    assert update["decisions"][0]["point"] == "scaffold"
    assert (tmp_path / "docs" / "decision_log.md").is_file()


def test_a_scaffold_that_cannot_be_proven_drops_the_pack(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.stacks.scaffold.scaffold", lambda *a, **k: SimpleNamespace(ok=False, problem="no network")
    )
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)

    update = nodes.scaffold(_state(tmp_path, stack_pack="browser-javascript"), CONFIG, CTX)

    assert update["stage"] == "acceptance_author"
    assert update["stack_pack"] is None
    assert "no network" in update["decisions"][0]["rationale"]


def test_no_pack_means_no_scaffold(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)
    update = nodes.scaffold(_state(tmp_path), CONFIG, CTX)
    assert update["stage"] == "acceptance_author" and "scaffold_result" not in update


def test_the_author_numbers_the_criteria_and_records_what_it_cannot_test(tmp_path, gated) -> None:
    gated.answers["acceptance_author"] = [SimpleNamespace(blockers=["AC-3: needs a person to judge it"])]

    update = nodes.acceptance_author(_state(tmp_path), CONFIG, CTX)

    assert gated.asked == ["acceptance_author_0"]
    assert update["stage"] == "acceptance_review" and update["acceptance_round"] == 1
    assert [c.id for c in suite.criteria(tmp_path)] == ["AC-1", "AC-2", "AC-3"]
    assert suite.deferred(tmp_path) == {"AC-3": "needs a person to judge it"}
    assert "AC-1" in (tmp_path / "docs" / "acceptance_criteria.md").read_text()


def test_no_criteria_means_no_suite(tmp_path, gated) -> None:
    state = _state(tmp_path)
    state["document"] = SimpleNamespace(text="Make something nice.")
    update = nodes.acceptance_author(state, CONFIG, CTX)
    assert update["stage"] == "scrum_master" and gated.asked == []


def _authored(root: Path, spec: str) -> None:
    suite.save_criteria(root, number(BRIEF))
    target = root / "notes" / "acceptance" / "notes.spec.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(spec)


ALL_THREE = (
    "test('[AC-1] adds', async () => {});\n"
    "test('[AC-2] deletes', async () => {});\n"
    "test('[AC-3] persists', async () => {});\n"
)


def test_a_suite_with_gaps_goes_back_to_qa(tmp_path, gated, monkeypatch) -> None:
    state = _state(tmp_path, acceptance_round=1)
    _authored(tmp_path, ALL_THREE.replace("[AC-3]", ""))
    monkeypatch.setattr(suite, "run", lambda root: _ran(failed_names=["[AC-1] adds", "[AC-2] deletes"]))

    update = nodes.acceptance_review(state, CONFIG, CTX)

    assert update["stage"] == "acceptance_author"
    assert any(item.startswith("AC-3") for item in update["acceptance_feedback"])
    assert not suite.is_locked(tmp_path) and gated.asked == []


def test_an_approved_suite_is_locked_and_described(tmp_path, gated, monkeypatch) -> None:
    state = _state(tmp_path, acceptance_round=1, review_policy={nodes.ACCEPTANCE_REVIEW: True})
    _authored(tmp_path, ALL_THREE)
    monkeypatch.setattr(suite, "run", lambda root: _ran(failed_names=["[AC-1] adds", "[AC-2] deletes", "[AC-3] persists"]))
    gated.answers["acceptance_review"] = [SimpleNamespace(approved=True, findings=[])]

    update = nodes.acceptance_review(state, CONFIG, CTX)

    assert suite.is_locked(tmp_path)
    assert update["stage"] == "user_review_acceptance"
    assert update["acceptance_open_problems"] == []
    assert "[AC-2] deletes" in (tmp_path / "docs" / "acceptance_tests.md").read_text()
    assert update["decisions"][-1]["point"] == "acceptance_tests"


def test_the_qa_lead_s_findings_go_back_until_the_last_round(tmp_path, gated, monkeypatch) -> None:
    _authored(tmp_path, ALL_THREE)
    monkeypatch.setattr(suite, "run", lambda root: _ran(passed_names=["[AC-1] adds"]))
    finding = "AC-1: passes before anything is built; it only checks the heading"
    gated.answers["acceptance_review"] = [SimpleNamespace(approved=False, findings=[finding])] * 2

    first = nodes.acceptance_review(_state(tmp_path, acceptance_round=1), CONFIG, CTX)
    assert first["stage"] == "acceptance_author" and first["acceptance_feedback"] == [finding]

    last = nodes.acceptance_review(
        _state(tmp_path, acceptance_round=nodes.MAX_ACCEPTANCE_ROUNDS), CONFIG, CTX
    )
    assert last["stage"] == "scrum_master" and suite.is_locked(tmp_path)
    assert last["acceptance_open_problems"] == [finding]


def _plan(*criteria_per_sprint):
    return SimpleNamespace(sprints=[SimpleNamespace(criteria=list(c)) for c in criteria_per_sprint])


def test_criteria_fall_due_sprint_by_sprint(tmp_path) -> None:
    suite.save_criteria(tmp_path, number(BRIEF))
    state = _state(tmp_path, sprint_plan=_plan(["AC-1"], ["AC-2"], []), current_sprint_index=0)
    assert nodes.criteria_due(state) == ["AC-1"]
    state["current_sprint_index"] = 1
    assert nodes.criteria_due(state) == ["AC-1", "AC-2"]
    state["current_sprint_index"] = 2
    # The last sprint answers for every criterion, assigned or not.
    assert nodes.criteria_due(state) == ["AC-1", "AC-2", "AC-3"]


def test_a_plan_that_assigns_nothing_makes_only_the_last_sprint_answer(tmp_path) -> None:
    suite.save_criteria(tmp_path, number(BRIEF))
    state = _state(tmp_path, sprint_plan=_plan([], []), current_sprint_index=0)
    assert nodes.criteria_due(state) == []
    state["current_sprint_index"] = 1
    assert nodes.criteria_due(state) == ["AC-1", "AC-2", "AC-3"]


def test_a_failing_due_criterion_the_round_left_out_becomes_a_defect(tmp_path) -> None:
    _authored(tmp_path, ALL_THREE)
    suite.lock(tmp_path)
    suite._judged(tmp_path, _ran(passed_names=["[AC-1] adds"], failed_names=["[AC-2] deletes"]), True)
    state = _state(tmp_path, sprint_plan=_plan(["AC-1", "AC-2"], ["AC-3"]), current_sprint_index=0)
    reported_by_the_round = [SimpleNamespace(description="Delete leaves the item [AC-2]")]

    assert nodes.failing_due_defects(state, reported_by_the_round) == []
    defects = nodes.failing_due_defects(state, [])
    assert [d.description.split("]")[0] for d in defects] == ["[AC-2"]
    assert defects[0].owner == "ui_ux" and "nope" in defects[0].actual_behavior
    assert "AC-2" in nodes.due_criteria_failing(state)
    # AC-3 is not due yet, so its absence from the report is no defect.
    assert "AC-3" not in nodes.due_criteria_failing(state)


def test_nothing_is_gated_without_a_locked_suite(tmp_path) -> None:
    state = _state(tmp_path)
    assert nodes.due_criteria_failing(state) == ""
    assert nodes.failing_due_defects(state, []) == []
    assert nodes.acceptance_text_for(state) == ""


def _all_passing(tmp_path, monkeypatch, failing=()):
    _authored(tmp_path, ALL_THREE)
    suite.lock(tmp_path)
    names = {"AC-1": "[AC-1] adds", "AC-2": "[AC-2] deletes", "AC-3": "[AC-3] persists"}
    monkeypatch.setattr(suite, "run", lambda root, **k: suite._judged(root, _ran(
        passed_names=[n for c, n in names.items() if c not in failing],
        failed_names=[n for c, n in names.items() if c in failing],
    ), True))


def test_a_sprint_whose_criteria_already_pass_has_nothing_left_to_build(tmp_path, monkeypatch) -> None:
    """One run's last four of seven sprints invented a "noop" work order each,
    because every criterion had passed since the third."""
    _all_passing(tmp_path, monkeypatch)
    state = _state(tmp_path, sprint_plan=_plan(["AC-1"], ["AC-2"], ["AC-3"]), current_sprint_index=1)

    why = nodes.sprint_already_done(state)

    assert "AC-1, AC-2" in why and "nothing left to build" in why


def test_it_is_built_when_a_due_criterion_fails_or_a_change_was_asked(tmp_path, monkeypatch) -> None:
    _all_passing(tmp_path, monkeypatch, failing=("AC-2",))
    state = _state(tmp_path, sprint_plan=_plan(["AC-1"], ["AC-2"], ["AC-3"]), current_sprint_index=1)
    assert nodes.sprint_already_done(state) == ""

    _all_passing(tmp_path, monkeypatch)
    asked = _state(tmp_path, sprint_plan=_plan(["AC-1"], ["AC-2"], ["AC-3"]), current_sprint_index=1,
                   revision_comments=["Make the delete button red"])
    assert nodes.sprint_already_done(asked) == ""
    # A sprint given no criteria of its own builds its goal, unless it is the last.
    no_own = _state(tmp_path, sprint_plan=_plan(["AC-1", "AC-2", "AC-3"], [], []), current_sprint_index=1)
    assert nodes.sprint_already_done(no_own) == ""
    no_own["current_sprint_index"] = 2
    assert nodes.sprint_already_done(no_own) != ""


def test_such_a_sprint_is_closed_like_an_accepted_one(tmp_path, monkeypatch) -> None:
    from app.graph import delivery, engineering
    from app.graph.workflow import _close_a_sprint_with_nothing_to_build

    monkeypatch.setattr(delivery, "write_evidence", lambda *a, **k: None)
    measured = []
    monkeypatch.setattr(engineering, "accepted_state", lambda root: measured.append(root))
    plan = SimpleNamespace(sprints=[SimpleNamespace(goal="One", criteria=["AC-1"]), SimpleNamespace(goal="Two", criteria=["AC-2"])])
    state = _state(tmp_path, sprint_plan=plan, current_sprint_index=0, decisions=[])

    update = _close_a_sprint_with_nothing_to_build(state, "Every criterion due by sprint 1 already passes")

    assert update["stage"] == "sprint_advance" and measured == [str(tmp_path)]
    (decision,) = update["decisions"]
    assert decision["point"] == "sprint" and decision["decision"] == "accept without new work"
    state["current_sprint_index"] = 1
    assert _close_a_sprint_with_nothing_to_build(state, "x")["stage"] == "release"


def test_a_re_planned_or_revised_sprint_is_never_closed_without_work(tmp_path, monkeypatch) -> None:
    """One run's sprint 1 was re-planned because its unit tests failed; it came
    back with no requested changes and, its one criterion passing, was accepted
    without its security and milestone reviews."""
    _all_passing(tmp_path, monkeypatch)
    plan = _plan(["AC-1"], ["AC-2"], ["AC-3"])
    for marker in ({"sprint_replan_count": 1}, {"milestone_revision_count": 1}, {"release_attempts": 1},
                   {"sprint_attempts": [{"sprint_index": 0, "status": "Failed"}]}):
        state = _state(tmp_path, sprint_plan=plan, current_sprint_index=0, **marker)
        assert nodes.sprint_already_done(state) == "", marker
    # An earlier sprint's record does not count against this one.
    fresh = _state(tmp_path, sprint_plan=plan, current_sprint_index=1,
                   sprint_attempts=[{"sprint_index": 0, "status": "Completed"}])
    assert nodes.sprint_already_done(fresh) != ""


def test_a_locked_test_that_cannot_pass_sends_the_suite_back_to_qa_once_built(tmp_path, monkeypatch) -> None:
    """One run's locked tests called a matcher that does not exist; before the
    product existed they failed earlier, and once it did they could never pass."""
    _authored(tmp_path, ALL_THREE)
    suite.lock(tmp_path)
    broken = ["`[AC-2] deletes` fails because of an error in the test's own code"]
    monkeypatch.setattr(nodes, "run_for_sprint", lambda state: (_ran(failed_names=["[AC-2] deletes"]), ["AC-2"]))
    monkeypatch.setattr(suite, "tests_that_broke_themselves", lambda root, result: list(broken))
    monkeypatch.setattr(suite, "assertions_that_do_not_exist", lambda root: [])
    state = _state(tmp_path, sprint_plan=_plan(["AC-1", "AC-2"]), current_sprint_index=0, decisions=[])

    text, cannot_pass = nodes.acceptance_for_round(state)
    update = nodes.reopen_the_suite_for(state, cannot_pass)

    assert cannot_pass == broken and "AC-2" in text
    assert update["stage"] == "acceptance_author" and update["acceptance_return_to"] == "test_and_triage"
    assert update["acceptance_feedback"][-1] == nodes.REPAIR_RULE and update["suite_repairs"] == 1
    assert update["decisions"][0]["affects"] == ["AC-2"]
    spent = _state(tmp_path, suite_repairs=nodes.MAX_SUITE_REPAIRS)
    assert nodes.reopen_the_suite_for(spent, cannot_pass) is None
    assert nodes.reopen_the_suite_for(state, []) is None


def test_a_plan_s_criteria_written_as_bare_numbers_are_read_as_ids() -> None:
    """One run's plan named its criteria 1 to 8; all were dropped as unknown."""
    from app.agents.scrum_master import SprintDefinition, SprintPlanOutput, with_every_criterion_assigned

    plan = SprintPlanOutput.model_construct(sprints=[
        SprintDefinition.model_construct(goal="Add", criteria=["1", "#2"]),
        SprintDefinition.model_construct(goal="Keep", criteria=["ac_3", "AC‑4", "9"]),
    ])
    cleaned, notes = with_every_criterion_assigned(plan, ["AC-1", "AC-2", "AC-3", "AC-4"])
    assert [list(s.criteria) for s in cleaned.sprints] == [["AC-1", "AC-2"], ["AC-3", "AC-4"]]
    assert notes == ["sprint 2 named 9, which is not a criterion"]


def test_a_fixer_is_told_when_the_definition_of_done_already_holds(tmp_path, monkeypatch) -> None:
    """Three runs' first sprints went round their fix loops for an hour on the
    team's own unit tests while every criterion passed; each fix bent the
    product towards a test about an internal detail."""
    from app.agents.specialists import build_defect_fix_request

    _all_passing(tmp_path, monkeypatch)
    suite.run(tmp_path)
    state = _state(tmp_path, sprint_plan=_plan(["AC-1"], ["AC-2"], ["AC-3"]), current_sprint_index=0)
    assert nodes.done_by_the_definition(state) == ["AC-1"]

    text = build_defect_fix_request(
        "Unit test expects a <p> for the description", "npm test", "passes", "fails", ["tests/ui.test.js"],
        False, str(tmp_path), done_already=["AC-1"],
    )["messages"][0]["content"]
    assert "Where the product stands" in text and "AC-1" in text and "unchanged" in text
    plain = build_defect_fix_request("x", "y", "z", "w", [], False, str(tmp_path))["messages"][0]["content"]
    assert "Where the product stands" not in plain

    _all_passing(tmp_path, monkeypatch, failing=("AC-1",))
    suite.run(tmp_path)
    assert nodes.done_by_the_definition(state) == []


def test_a_criterion_the_suite_tests_is_not_deferred_as_not_automatable(tmp_path, gated) -> None:
    """One run's QA, repairing a reopened suite, listed the product's bugs as
    blockers - "AC-5: product bug, the filter buttons never fire" - and four
    criteria with failing tests in the suite left the release gate."""
    state = _state(tmp_path)
    _authored(tmp_path, (
        "import { test } from '@playwright/test';\n"
        "test('[AC-1] adds a note', async ({ page }) => {});\n"
        "test('[AC-2] deletes a note', async ({ page }) => {});\n"
    ))
    assert suite.coverage(tmp_path).get("AC-2")
    gated.answers["acceptance_author"] = [SimpleNamespace(blockers=[
        "AC-2: product bug - the delete control never fires",
        "AC-3: needs a person to judge it",
    ])]

    nodes.acceptance_author(state, CONFIG, CTX)

    assert suite.deferred(tmp_path) == {"AC-3": "needs a person to judge it"}
