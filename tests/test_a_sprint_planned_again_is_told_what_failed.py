"""A sprint sent back to be planned again says why, and what is still open.

Measured on one run: sprint 1 failed its tests on one defect - an edit that
never reached the browser's storage. Each of its three re-plans was "run the
existing test suite", from a lead whose request was the one it got the first
time: nothing said the sprint had been tried, or what stopped it. The same
defect closed the run.
"""

from __future__ import annotations

from app.agents.technical_lead import build_milestone_planning_request
from app.graph.workflow import _the_last_failed_attempt_at_this_sprint

FAILED = {
    "sprint_index": 0, "number": 2, "status": "Failed",
    "reason": "exhausted remediation attempts",
    "defects": [
        {"status": "fixed", "description": "The add form does not submit.", "owner": "ui_ux"},
        {"status": "open", "description": "Editing a task does not persist after a reload.", "owner": "backend"},
    ],
}


def _request(last_attempt) -> str:
    return build_milestone_planning_request(
        "the sprint plan", "Create and persist tasks", "/workspace", last_attempt=last_attempt
    )["messages"][0]["content"]


def test_the_lead_is_told_the_sprint_was_tried_and_why_it_ended() -> None:
    body = _request(FAILED)

    assert "already been attempted and was not accepted" in body
    assert "Attempt 2 ended: exhausted remediation attempts." in body


def test_the_open_defects_are_named_with_their_owners() -> None:
    body = _request(FAILED)

    assert "- [owner: backend] Editing a task does not persist after a reload." in body
    assert "The add form does not submit." not in body, "a fixed defect is not left to plan for"


def test_it_comes_before_the_instruction_to_plan() -> None:
    body = _request(FAILED)

    assert body.index("was not accepted") < body.index("You are now planning the milestone")


def test_a_first_attempt_says_nothing() -> None:
    assert "already been attempted" not in _request(None)


def test_the_attempt_is_the_current_sprint_s_last_and_only_if_it_failed() -> None:
    other = {**FAILED, "sprint_index": 1}
    accepted = {**FAILED, "number": 3, "status": "Completed"}

    assert _the_last_failed_attempt_at_this_sprint(
        {"current_sprint_index": 0, "sprint_attempts": [FAILED]}
    ) == FAILED
    assert _the_last_failed_attempt_at_this_sprint(
        {"current_sprint_index": 0, "sprint_attempts": [other]}
    ) is None
    assert _the_last_failed_attempt_at_this_sprint(
        {"current_sprint_index": 0, "sprint_attempts": [FAILED, accepted]}
    ) is None
    assert _the_last_failed_attempt_at_this_sprint({"current_sprint_index": 0}) is None
