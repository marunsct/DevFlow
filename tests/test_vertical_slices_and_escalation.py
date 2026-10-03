"""Sprints planned as vertical slices against the criteria, and the escalation ladder's last rung."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.acceptance import junit, suite
from app.acceptance.criteria import number
from app.agents.scrum_master import SprintDefinition, SprintPlanOutput, build_sprint_planning_request, with_every_criterion_assigned
from app.graph import escalation

BRIEF = "# Brief\n## Features\n- Add a note\n- Delete a note\n- Edit a note\n- Search notes\n"
CONFIG = {"configurable": {"thread_id": "t"}}


def _plan(*criteria: list[str]) -> SprintPlanOutput:
    return SprintPlanOutput(sprints=[
        SprintDefinition(goal=f"Sprint {n}", user_value="v", criteria=list(c)) for n, c in enumerate(criteria, 1)
    ])


def test_every_criterion_ends_up_in_exactly_one_sprint() -> None:
    plan, notes = with_every_criterion_assigned(
        _plan(["AC-1", "ac_2"], ["AC-2", "AC-9"], []), ["AC-1", "AC-2", "AC-3", "AC-4"]
    )
    assert [s.criteria for s in plan.sprints] == [["AC-1", "AC-2"], [], ["AC-3", "AC-4"]]
    assert any("AC-9" in n for n in notes) and any("claimed by an earlier sprint" in n for n in notes)
    assert any("AC-3, AC-4" in n for n in notes)


def test_a_walking_skeleton_always_has_something_to_show() -> None:
    plan, notes = with_every_criterion_assigned(_plan([], ["AC-1", "AC-2"]), ["AC-1", "AC-2"])
    assert [s.criteria for s in plan.sprints] == [["AC-1"], ["AC-2"]]
    assert any("sprint 1" in n for n in notes)


def test_a_plan_without_criteria_is_left_alone() -> None:
    plan = _plan(["AC-1"])
    assert with_every_criterion_assigned(plan, []) == (plan, [])


def test_the_planner_is_asked_for_vertical_slices() -> None:
    text = build_sprint_planning_request("spec", "/w", acceptance_criteria="- AC-1: Add a note")["messages"][0]["content"]
    assert "AC-1: Add a note" in text and "walking skeleton" in text
    assert "walking skeleton" not in build_sprint_planning_request("spec", "/w")["messages"][0]["content"]


# --- escalation -------------------------------------------------------------------


def _state(root: Path, **extra: Any) -> dict[str, Any]:
    (root / ".project-directory").write_text("notes\n")
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "sprint_plan": _plan(["AC-1", "AC-2"], ["AC-3", "AC-4"]),
        "current_sprint_index": 0,
        "escalation": {"error": "Sprint 'Sprint 1' was re-planned 3 times and still could not be accepted"},
        **extra,
    }


def _suite_with(root: Path, failing: tuple[str, ...]) -> None:
    suite.save_criteria(root, number(BRIEF))
    spec = root / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("".join(f"test('[AC-{n}] t', ()=>{{}});\n" for n in range(1, 5)))
    suite.lock(root)
    report = junit.Report(found=True, tests=[
        junit.TestResult(name=f"[AC-{n}] t", outcome="failed" if f"AC-{n}" in failing else "passed")
        for n in range(1, 5)
    ])
    suite._judged(root, suite.AcceptanceResult(ran=True, command="npm run test:acceptance", report=report), True)


def test_auto_mode_defers_what_fails_and_goes_on(tmp_path) -> None:
    _suite_with(tmp_path, failing=("AC-2",))

    update = escalation.escalation(_state(tmp_path), CONFIG, None)

    assert update["stage"] == "sprint_advance"
    assert "AC-2" in suite.deferred(tmp_path)
    decision = update["decisions"][-1]
    assert decision["decided_by"] == "auto" and decision["affects"] == ["AC-2"]
    assert "deferred" in (tmp_path / "docs" / "acceptance_criteria.md").read_text()


def test_the_last_sprint_goes_on_to_the_release(tmp_path) -> None:
    _suite_with(tmp_path, failing=("AC-4",))
    update = escalation.escalation(_state(tmp_path, current_sprint_index=1), CONFIG, None)
    assert update["stage"] == "release"


def test_auto_mode_stops_a_run_that_would_ship_less_than_half(tmp_path) -> None:
    _suite_with(tmp_path, failing=("AC-1", "AC-2", "AC-3"))
    state = _state(tmp_path, sprint_plan=_plan(["AC-1", "AC-2", "AC-3"], ["AC-4"]))
    update = escalation.escalation(state, CONFIG, None)
    assert update["stage"] == "failed" and "re-planned" in update["error"]
    assert update["decisions"][-1]["decision"] == "stop the run"


def test_with_nothing_to_measure_the_run_stops_as_before(tmp_path) -> None:
    update = escalation.escalation(_state(tmp_path), CONFIG, None)
    assert update["stage"] == "failed"


def test_approval_mode_asks_with_the_problem_in_front_of_the_person(tmp_path) -> None:
    _suite_with(tmp_path, failing=("AC-2",))
    state = _state(tmp_path, review_policy={escalation.ESCALATION_REVIEW: True})

    update = escalation.escalation(state, CONFIG, None)

    assert update["stage"] == "user_review_escalation"
    page = (tmp_path / "docs" / "reviews" / "escalation.md").read_text()
    assert "AC-2" in page and "re-planned 3 times" in page and "Request changes" in page
    assert suite.deferred(tmp_path) == {}


def test_a_sprint_review_alone_does_not_put_a_stuck_sprint_to_a_person(tmp_path) -> None:
    _suite_with(tmp_path, failing=("AC-2",))
    update = escalation.escalation(_state(tmp_path, review_policy={"sprint": True}), CONFIG, None)
    assert update["stage"] == "sprint_advance"


def test_the_person_s_answers(tmp_path) -> None:
    _suite_with(tmp_path, failing=("AC-2",))
    accepted = escalation.accept(_state(tmp_path), CONFIG, None)
    assert accepted["stage"] == "sprint_advance" and "AC-2" in suite.deferred(tmp_path)
    assert accepted["decisions"][-1]["decided_by"] == "user"

    retried = escalation.retry(
        _state(tmp_path, revision_comments=["store notes in a file, not memory"], sprint_replan_count=3),
        CONFIG, None,
    )
    assert retried["stage"] == "technical_lead" and retried["sprint_replan_count"] == 0
    assert retried["revision_comments"] == ["store notes in a file, not memory"]


def test_a_run_that_keeps_getting_stuck_stops(tmp_path) -> None:
    _suite_with(tmp_path, failing=("AC-2",))
    update = escalation.escalation(_state(tmp_path, escalation_count=escalation.MAX_ESCALATIONS), CONFIG, None)
    assert update["stage"] == "failed"


def test_a_retried_sprint_is_built_on_the_judgement_model() -> None:
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow.build_workflow_graph)
    assert source.count("model=_the_model_for_this_attempt(state)") == 2
    helper = source[source.index("def _the_model_for_this_attempt"):]
    for counter in ("sprint_replan_count", "milestone_revision_count", "release_attempts", "escalation_count"):
        assert counter in helper[:900]
