"""A sprint accepted at an escalation says so at release, and its known issues name the decision (harness review HR2.G.8).

8 of 40 runs closed their only sprint through the escalation decision and skipped every review; "No review read the
product's code" fired on 24% of runs and read as a review failing when it was a routing fact.
"""
from __future__ import annotations

from app import completion_verdict
from app.graph import delivery

ACCEPTED = {"decisions": [
    {"id": "DR-2", "point": "scaffold", "decision": "a proven setup"},
    {"id": "DR-5", "point": "escalation", "decision": "accept the sprint with its open problems recorded as known issues"},
]}


def test_the_note_names_the_escalation_that_accepted_the_sprint(monkeypatch) -> None:
    monkeypatch.setattr("app.observability.transcript.read_transcript",
                        lambda run_id, kinds=None: [{"stage": "technical_lead"}, {"stage": "defect_fix_1"}])
    note = delivery._code_no_review_read("run-x", ACCEPTED)
    assert note == ["No review read the product's code: the sprint was accepted at an escalation (DR-5), "
                    "so no code, milestone or security review ran."]
    assert not completion_verdict.is_blocking(note[0]), "still a note, not a reason it may not work"


def test_without_an_escalation_the_note_is_as_before(monkeypatch) -> None:
    monkeypatch.setattr("app.observability.transcript.read_transcript",
                        lambda run_id, kinds=None: [{"stage": "technical_lead"}])
    assert "accepted on its locked suite alone" in delivery._code_no_review_read("run-x", {"decisions": []})[0]


def test_a_stop_is_not_an_acceptance() -> None:
    assert delivery._accepted_at_an_escalation({"decisions": [
        {"id": "DR-3", "point": "escalation", "decision": "stop the run"}]}) == ""


def test_a_known_issue_with_its_decision_id_is_still_a_note() -> None:
    gap = "An escalation left this open (DR-5): Design review left open: the retry limit is stated twice"
    assert not completion_verdict.is_blocking(gap)
    assert not completion_verdict.is_blocking("An escalation left this open: Design review left open: x")
