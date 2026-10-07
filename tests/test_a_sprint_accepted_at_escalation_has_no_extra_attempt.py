"""A failed attempt an escalation accepts is closed in the Sprint Record, not followed by one more.

Measured on one run: an escalation accepted a sprint's fifth attempt "with its
open problems recorded as known issues", and the sprint's record read
"Attempts: 6 (re-run after 5 failed attempts)", the sixth "Completed" with the
fifth's rounds and defects - an attempt that never ran.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.sprint_summary import render_sprint_summary
from app.graph.escalation import _the_failed_attempt_accepted
from app.graph.workflow import _record_sprint_summary

DECISION = "accept the sprint with its open problems recorded as known issues"


def _attempt(number: int, status: str, **more) -> dict:
    return {"sprint_index": 0, "number": number, "status": status, "reason": "exhausted remediation attempts"
            if status == "Failed" else "", "rounds": 3, "defects": [], "cases": None, **more}


def test_the_escalation_marks_the_failed_attempt_it_accepts() -> None:
    state = {"current_sprint_index": 0, "sprint_attempts": [_attempt(1, "Failed"), _attempt(2, "Failed")]}

    marked = _the_failed_attempt_accepted(state, {"decisions": [{"id": "DR-4", "decision": DECISION}]})

    assert [entry.get("accepted_at_escalation") for entry in marked["sprint_attempts"]] == [None, DECISION]
    assert "accepted_at_escalation" not in state["sprint_attempts"][1], "the state itself is not changed"


def test_nothing_is_marked_when_the_last_attempt_passed_or_there_is_none() -> None:
    assert _the_failed_attempt_accepted({"current_sprint_index": 0, "sprint_attempts": []}, {}) == {}
    assert _the_failed_attempt_accepted(
        {"current_sprint_index": 0, "sprint_attempts": [_attempt(1, "Completed")]}, {}
    ) == {}


def _recorded(tmp_path, attempts: list[dict]) -> list[dict]:
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "current_sprint_index": 0,
        "sprint_attempts": attempts,
        "test_round": 3,
    }
    return _record_sprint_summary(state, "Completed")["sprint_attempts"]


def test_the_record_closes_that_attempt_rather_than_adding_one(tmp_path) -> None:
    attempts = _recorded(tmp_path, [_attempt(1, "Failed"), _attempt(2, "Failed", accepted_at_escalation=DECISION)])

    assert [(entry["number"], entry["status"]) for entry in attempts] == [(1, "Failed"), (2, "Completed")]
    assert attempts[-1]["accepted_at_escalation"] == DECISION


def test_a_sprint_completed_after_a_failed_attempt_still_adds_its_own(tmp_path) -> None:
    attempts = _recorded(tmp_path, [_attempt(1, "Failed")])

    assert [(entry["number"], entry["status"]) for entry in attempts] == [(1, "Failed"), (2, "Completed")]
    assert "accepted_at_escalation" not in attempts[-1]


def test_the_document_says_it_was_accepted_at_escalation() -> None:
    document = render_sprint_summary(
        sprint_number=3, total_sprints=3, goal="Fit a phone and a desktop.", planned=["Lay it out for both"],
        attempts=[_attempt(1, "Failed"), _attempt(2, "Completed", accepted_at_escalation=DECISION)],
    )

    assert "**Attempts:** 2 (re-run after 1 failed" in document
    assert f"**Accepted at escalation:** {DECISION}" in document
    assert f"- **Attempt 2** (re-run) - Completed at escalation ({DECISION})." in document
    assert "**Status:** Completed\n" in document, "the panel reads the status as it always has"
