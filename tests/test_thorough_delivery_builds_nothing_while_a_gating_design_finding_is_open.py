"""Thorough delivery starts no development while a design finding of a gating severity is open (owner, 2026-11-25).

Measured on one medium run before it: the architecture review raised five blocking findings and one major, one
revision answered them, `ONE_DESIGN_REVIEW` asked nobody again, and the design escalation built from the latest
specification with nine points recorded as known risks. The product shipped with no interface, which two of the open
findings were about. See `app.graph.design_gate`.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.agents.architecture_reviewer import ArchitectureReviewOutput
from app.graph import workflow
from workflow_nodes import a_design_finding, a_specification, an_architecture_review, run_node

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.IGNORECASE)

SERVING = "The specification never says how the interface is served beside the service."


@pytest.fixture(autouse=True)
def _delivered_thoroughly(monkeypatch):
    monkeypatch.setattr(workflow, "_fast_delivery", lambda: False)
    monkeypatch.setenv("ONE_DESIGN_REVIEW", "on")
    monkeypatch.setenv("HARNESS_FINDINGS_RECHECKED", "on")


QUIET = {"app.graph.workflow._record_document": lambda *args, **kwargs: None,
         "app.graph.workflow._review_enabled": lambda state, point: False}


def _reviewed(tmp_path, answer, state=None, patches=None):
    return an_architecture_review(tmp_path, answer, state={"decisions": [], **(state or {})},
                                  patches={**QUIET, **(patches or {})})


def _then(state, update):
    """The state the next stage reads: this one's with the update applied."""
    return {**state, **{key: value for key, value in update.items() if key != "stage"}}


def _a_review_that_raises_serving(tmp_path):
    first = ArchitectureReviewOutput(status="changes_required",
                                     findings=[a_design_finding("blocking", description=SERVING)])
    update, _ = _reviewed(tmp_path, first)
    return _then({"decisions": []}, update), update


def test_a_revised_specification_is_reviewed_again_whatever_one_design_review_says(tmp_path):
    state, _ = _a_review_that_raises_serving(tmp_path)

    _, asked = _reviewed(tmp_path, ArchitectureReviewOutput(status="approved", findings=[]), state=state, patches={
        "app.graph.workflow._decided_after_one_revision": workflow._decided_after_one_revision,
        "app.graph.workflow._approved_once_the_harness_s_findings_are_settled":
            workflow._approved_once_the_harness_s_findings_are_settled})

    assert len(asked) == 1
    # The re-review is given the finding, numbered, and asked to answer it.
    assert f"1. [blocking] {SERVING}" in asked[0]
    assert "earlier_findings" in asked[0]


def test_a_gating_finding_the_re_review_says_is_still_open_goes_back_to_the_architect(tmp_path):
    state, _ = _a_review_that_raises_serving(tmp_path)
    silent_but_open = ArchitectureReviewOutput.model_validate(
        {"status": "approved", "findings": [],
         "earlier_findings": [{"number": 1, "resolved": False, "where": "No serving section yet."}]})

    update, _ = _reviewed(tmp_path, silent_but_open, state=state)

    assert update["stage"] == "principal_architect"
    assert [f.description for f in update["architecture_review"].findings] == [SERVING]


def test_a_gating_finding_the_re_review_no_longer_finds_is_resolved_in_its_round_and_recorded(tmp_path):
    state, _ = _a_review_that_raises_serving(tmp_path)

    update, _ = _reviewed(tmp_path, ArchitectureReviewOutput(status="approved", findings=[]), state=state)

    assert update["stage"] == "scaffold"
    [resolved] = [d for d in update["decisions"] if d["decision"].startswith("resolved in review round")]
    assert resolved["decision"] == "resolved in review round 2"
    assert SERVING in resolved["rationale"]


BRIEF = "# Planner\n\n## Requirements\n- Due dates and reminders\n"
DEFERRING = a_specification(product_scope="A planner.\n## What this release explicitly defers\n- Reminders.")
SPECIFYING = a_specification(product_scope="A planner with reminders: each item has a reminder date.")


def test_a_finding_of_the_workflow_s_own_check_is_open_until_the_check_no_longer_finds_it(tmp_path):
    check = {"app.graph.workflow._a_brief_feature_the_specification_defers":
             workflow._a_brief_feature_the_specification_defers}
    approved = ArchitectureReviewOutput(status="approved", findings=[])
    given = {"document": SimpleNamespace(text=BRIEF), "technical_specification": DEFERRING}
    first, _ = _reviewed(tmp_path, approved, state=given, patches=check)
    state = _then({"decisions": [], **given}, first)

    unchanged, _ = _reviewed(tmp_path, approved, state=state, patches=check)
    revised, _ = _reviewed(tmp_path, approved, state={**state, "technical_specification": SPECIFYING}, patches=check)

    assert first["stage"] == unchanged["stage"] == "principal_architect"
    assert "reminders" in unchanged["architecture_review"].findings[0].description
    assert revised["stage"] == "scaffold"
    assert any("no longer finds it" in d["rationale"] for d in revised["decisions"])


def _at_the_revision_limit(tmp_path):
    """The state the escalation reads after the last revision left the serving finding open."""
    state, _ = _a_review_that_raises_serving(tmp_path)
    still = ArchitectureReviewOutput(status="changes_required",
                                     findings=[a_design_finding("blocking", description=SERVING)])
    update, _ = _reviewed(tmp_path, still,
                          state={**state, "architecture_revision_count": workflow.MAX_ARCHITECTURE_REVISIONS - 1})
    assert update["stage"] == "escalation"
    return {**_then(state, update), "repository": SimpleNamespace(root_path=str(tmp_path))}


NOBODY_ASKED = {"app.graph.workflow._review_enabled": lambda state, point: False,
                "app.agents.specification_rulings.settle": lambda *args, **kwargs: [],
                "app.graph.workflow._a_model_to_revise_with": lambda model: None}


def test_past_the_revision_limit_a_run_nobody_reviews_waits_for_a_person(tmp_path):
    state = _at_the_revision_limit(tmp_path)

    update = run_node("escalation", state, str(tmp_path), NOBODY_ASKED)

    assert update["stage"] == "user_review_escalation"
    assert update["decisions"][-1]["decision"].startswith("wait for a person")
    assert SERVING in update["decisions"][-1]["rationale"]
    assert SERVING in (tmp_path / "docs/reviews/escalation.md").read_text()


def test_in_fast_delivery_the_escalation_still_builds_with_its_open_points_as_risks(tmp_path, monkeypatch):
    state = _at_the_revision_limit(tmp_path)
    monkeypatch.setattr(workflow, "_fast_delivery", lambda: True)

    update = run_node("escalation", state, str(tmp_path), NOBODY_ASKED)

    assert update["stage"] == "scaffold"


def _answered_at_the_gate(state, by):
    gate = {"id": "DR-99", "point": "escalation", "decision": "approve", "decided_by": by}
    return {**state, "decisions": [*state["decisions"], gate]}


def test_the_gate_s_timeout_does_not_approve_a_gating_design_finding(tmp_path):
    state = _answered_at_the_gate(_at_the_revision_limit(tmp_path), "timeout")

    update = run_node("escalation_accept", state, str(tmp_path), NOBODY_ASKED)

    assert update["stage"] == "user_review_escalation"
    assert update["decisions"][-1]["decision"].startswith("wait for a person")


def test_a_person_s_approval_at_the_gate_builds_and_records_each_finding_as_theirs(tmp_path):
    state = _answered_at_the_gate(_at_the_revision_limit(tmp_path), "user")

    update = run_node("escalation_accept", state, str(tmp_path), NOBODY_ASKED)

    assert update["stage"] == "scaffold"
    [approved] = [d for d in update["decisions"] if d["decision"] == "approved by the person at the escalation gate"]
    assert approved["decided_by"] == "user" and SERVING in approved["rationale"]


def test_the_timeout_sweep_leaves_a_gate_holding_gating_design_findings_for_a_person(tmp_path):
    from app.server import approval_timeouts

    held = _at_the_revision_limit(tmp_path)
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


def test_what_the_gate_tells_the_reviewer_and_the_person_names_no_product_word(tmp_path):
    from app.agents.architecture_reviewer import EARLIER_FINDINGS_RULE

    state = _at_the_revision_limit(tmp_path)
    update = run_node("escalation", state, str(tmp_path), NOBODY_ASKED)
    page = (tmp_path / "docs/reviews/escalation.md").read_text().replace(SERVING, "")
    written = [EARLIER_FINDINGS_RULE, page, *(d["question"] + d["decision"] + d["rationale"].replace(SERVING, "")
                                              for d in update["decisions"])]

    for text in written:
        assert not BANNED.search(text), text


def test_a_value_the_specification_lists_is_not_read_as_deferred_by_a_deferral_heading_of_another_field():
    from app.analysis.integration_checks import brief_features_the_text_defers

    brief = "# Board\n\n## Requirements\n- Set priorities (low, medium, high, urgent)\n- Due dates and reminders\n"
    specification = json.dumps({
        "product_scope": "A team board.\n## What this release explicitly defers\n- Reminder delivery mechanism "
                         "(the brief states \"reminders\" but does not specify a channel; deferred).",
        "domain_model": ["Item: id (UUID), title (str), priority (ItemPriority enum: 'low', 'medium', 'high', "
                         "'urgent'), due_date (date, nullable)."],
    }, indent=2)

    assert [feature for feature, _, _ in brief_features_the_text_defers(brief, specification)] == ["reminders"]


def test_an_answer_on_an_earlier_finding_written_in_words_is_read_and_one_that_cannot_be_read_fails_nothing():
    review = ArchitectureReviewOutput.model_validate({"status": "changes_required", "findings": [], "earlier_findings": [
        {"number": "1", "resolved": "still open", "where": "No serving section."},
        {"number": "two", "resolved": True},
        {"number": 3, "resolved": "perhaps"},
    ]})

    assert [(answer.number, answer.resolved) for answer in review.earlier_findings] == [(1, False)]
