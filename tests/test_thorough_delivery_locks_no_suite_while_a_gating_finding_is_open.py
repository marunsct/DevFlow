"""Thorough delivery locks no acceptance suite while a finding about it of a gating severity is open (TG.2).

The owner's rule: in thorough delivery every review finding of severity blocking, major, critical or high is resolved
before development starts. Before it, the QA lead's findings and the harness's problems with the suite had no
severity, and past `MAX_ACCEPTANCE_ROUNDS` the suite was locked "with these still open" whatever they were - a test
no product can pass among them. See `app.graph.suite_gate`.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import delivery
from app.acceptance import suite
from the_acceptance_review import (
    A_FAIR_TEST, FAILED, NO_PRODUCT_CAN_PASS, a_service_suite, measured, qa_lead, reviewed,
)
from workflow_nodes import run_node

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.IGNORECASE)

CONTRADICTION = "AC-1: one test expects the newest note first and another the oldest first; both cannot pass."
LOOSE = "AC-1: the test could name the field the way the brief does."


@pytest.fixture(autouse=True)
def _thorough():
    with delivery.for_the_run("thorough"):
        yield


def _at_the_limit(tmp_path: Path, *findings, state=None):
    """The acceptance review at the round limit, the QA lead answering with `findings` (description, severity), after
    the one repair a test failing on a correct product gets before the lock (LF.1442) was made."""
    from app.graph import suite_gate

    root = a_service_suite(tmp_path, A_FAIR_TEST)
    suite._save_state(root, {**suite._state(root), suite_gate.REPAIRED_BEFORE_THE_LOCK: True})
    review = qa_lead(False, *({"description": text, "severity": severity} for text, severity in findings))
    return reviewed(root, measured(FAILED), rounds=3, review=review, state=state)


def _then(state, update):
    return {**state, **{key: value for key, value in update.items() if key != "stage"}}


def test_the_qa_lead_s_severity_is_read_in_any_vocabulary_and_a_bare_line_keeps_today_s_lock():
    from app.agents.acceptance_reviewer import AcceptanceReviewOutput

    review = AcceptanceReviewOutput.model_validate({"approved": False, "findings": [
        {"description": CONTRADICTION, "severity": "High"}, LOOSE]})

    assert [(str(f), f.severity) for f in review.findings] == [(CONTRADICTION, "major"), (LOOSE, "minor")]


def test_a_gating_finding_of_the_qa_lead_keeps_the_suite_from_locking_past_the_round_limit(tmp_path):
    update, _ = _at_the_limit(tmp_path, (CONTRADICTION, "blocking"))

    assert update["stage"] == "escalation"
    assert update["escalation"]["kind"] == "suite"
    assert CONTRADICTION in " ".join(update["escalation"]["findings"])
    assert not suite.is_locked(tmp_path)


def test_a_finding_below_the_gating_severities_locks_as_before(tmp_path):
    update, _ = _at_the_limit(tmp_path, (LOOSE, "minor"))

    assert update["stage"] != "escalation"
    assert suite.is_locked(tmp_path)


def test_in_fast_delivery_a_gating_finding_locks_as_before(tmp_path):
    with delivery.for_the_run("fast"):
        update, _ = _at_the_limit(tmp_path, (CONTRADICTION, "blocking"))

    assert update["stage"] != "escalation"
    assert suite.is_locked(tmp_path)


def test_a_test_no_product_can_pass_keeps_the_suite_from_locking_once_its_repair_is_spent(tmp_path):
    root = a_service_suite(tmp_path, NO_PRODUCT_CAN_PASS)
    spent = {"cannot_pass_repaired_once": True, "cannot_pass_sent": 1, "partial_strengthened_once": True}

    update, _ = reviewed(root, measured(FAILED), rounds=3, saved=spent)

    assert update["stage"] == "escalation"
    assert not suite.is_locked(tmp_path)


@pytest.mark.parametrize(("check", "severity"), [
    ("tests_that_want_json_from_a_204", "blocking"),
    ("tests_whose_success_status_the_contract_does_not_give", "blocking"),
    ("tests_guarded_by_the_answer", "major"),
    ("locators_nobody_sees", "minor"),
    ("tests_that_pass_before_the_product", "minor"),
    ("contract_lines_with_no_test", "minor"),
])
def test_a_harness_finding_is_as_severe_as_what_it_breaks(check, severity):
    from app.graph.suite_gate import severity_of_a_check

    assert severity_of_a_check(check) == severity


NOBODY_ASKED = {"app.graph.workflow._review_enabled": lambda state, point: False}


def _held(tmp_path):
    """The state the escalation reads after the review held the suite for a person."""
    state = {"acceptance_round": 3, "decisions": [], "repository": SimpleNamespace(root_path=str(tmp_path))}
    update, _ = _at_the_limit(tmp_path, (CONTRADICTION, "blocking"), state=state)
    return _then(state, update)


def test_a_held_suite_waits_for_a_person_whoever_the_run_asked_and_is_not_counted_as_an_escalation(tmp_path):
    state = _held(tmp_path)

    update = run_node("escalation", state, str(tmp_path), NOBODY_ASKED)

    assert update["stage"] == "user_review_escalation"
    assert update["decisions"][-1]["decision"].startswith("wait for a person")
    assert CONTRADICTION in (tmp_path / "docs/reviews/escalation.md").read_text()
    assert "escalation_count" not in update


def _answered_at_the_gate(state, by):
    gate = {"id": "DR-99", "point": "escalation", "decision": "approve", "decided_by": by}
    return {**state, "decisions": [*state["decisions"], gate]}


def test_the_gate_s_timeout_does_not_approve_a_gating_suite_finding(tmp_path):
    state = _answered_at_the_gate(_held(tmp_path), "timeout")

    update = run_node("escalation_accept", state, str(tmp_path), NOBODY_ASKED)

    assert update["stage"] == "user_review_escalation"
    assert update["decisions"][-1]["decision"].startswith("wait for a person")


def test_a_person_s_approval_locks_the_suite_as_it_stands_without_reading_it_again(tmp_path):
    state = _answered_at_the_gate(_held(tmp_path), "user")
    approved = run_node("escalation_accept", state, str(tmp_path), NOBODY_ASKED)
    assert approved["stage"] == "acceptance_review"

    update, asked = reviewed(tmp_path, measured(FAILED), rounds=3, review=qa_lead(False, {
        "description": "AC-1: a different wording of a new blocking point.", "severity": "blocking"}),
        state=_then(state, approved))

    assert suite.is_locked(tmp_path)
    assert asked == []
    [mine] = [d for d in approved["decisions"] if d["decision"] == "approved by the person at the escalation gate"]
    assert mine["decided_by"] == "user" and CONTRADICTION in mine["rationale"]
    assert CONTRADICTION in update["decisions"][-1]["rationale"]


def test_a_person_s_request_for_changes_sends_the_suite_back_with_the_open_findings(tmp_path):
    state = {**_held(tmp_path), "revision_comments": ["Keep one order, newest first."]}

    update = run_node("escalation_retry", state, str(tmp_path), NOBODY_ASKED)

    assert update["stage"] == "acceptance_author"
    assert any(CONTRADICTION in item for item in update["acceptance_feedback"])
    assert update["revision_comments"] == ["Keep one order, newest first."]


def test_a_gating_finding_the_next_review_no_longer_raises_is_resolved_in_its_round_and_recorded(tmp_path):
    state = {**_held(tmp_path), "acceptance_round": 4}

    update, _ = reviewed(tmp_path, measured(FAILED), rounds=4, review=qa_lead(True), state=state)

    assert suite.is_locked(tmp_path)
    [resolved] = [d for d in update["decisions"] if d["decision"].startswith("resolved in acceptance round")]
    assert resolved["decision"] == "resolved in acceptance round 4"
    assert CONTRADICTION in resolved["rationale"]


def test_the_timeout_sweep_leaves_a_suite_held_for_a_person(tmp_path):
    from app.server import approval_timeouts

    held = {**_held(tmp_path), "escalation": {"kind": "suite"}}
    now = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    record = SimpleNamespace(run_id="held", status="waiting_for_review", approval_timeout_minutes=30,
                             updated_at=(now - timedelta(minutes=45)).isoformat(), delivery_mode="thorough",
                             current_stage="awaiting_user_review:escalation", graph_state=lambda: held)
    answered = []

    class _Runner:
        run_store = SimpleNamespace(list_all=lambda limit, offset: [record])

        async def submit_review(self, run_id, decision):
            answered.append(run_id)

    assert asyncio.run(approval_timeouts.approve_what_is_due(_Runner(), now)) == []
    assert answered == []


def test_what_the_suite_gate_tells_the_qa_lead_and_the_person_names_no_product_word(tmp_path):
    from app.agents.acceptance_reviewer import SEVERITY_RULE, _SYSTEM_PROMPT

    state = _held(tmp_path)
    update = run_node("escalation", state, str(tmp_path), NOBODY_ASKED)
    page = (tmp_path / "docs/reviews/escalation.md").read_text().replace(CONTRADICTION, "")
    written = [SEVERITY_RULE, page, *(d["question"] + d["decision"] + d["rationale"].replace(CONTRADICTION, "")
                                     for d in [*state["decisions"], *update["decisions"]])]

    assert SEVERITY_RULE in _SYSTEM_PROMPT
    for text in written:
        assert not BANNED.search(text), text
