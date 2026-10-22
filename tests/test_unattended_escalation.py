"""A run with no human reviewer must never be parked waiting for one.

`_run_review_gate` opens a review session and pauses unconditionally - it never
asks whether that review is switched on. Two escalations routed straight to it:
a milestone review that exhausted its revisions, and a sprint that exhausted its
remediation attempts. Both are the right place to want a person; neither checked
whether there is one.

Reviews are opt-in, and the default `review_policy` is `{}`. Measured on
one run: it sat in `awaiting_user_review:sprint` with an empty policy -
not failed, not progressing, and holding a worker.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.graph import escalation
from app.graph.workflow import SPRINT_REVIEW, _escalate_to_a_human

# Since the escalation ladder (`app.graph.escalation`), the helper no longer
# decides: it hands the reason to the escalation stage, which decides - and
# which asks a person only when the run asked for one at that point.


def test_every_escalation_carries_its_reason_to_the_escalation_stage() -> None:
    update = _escalate_to_a_human(
        {"review_policy": {}},
        error="Sprint exhausted its 3 remediation attempts with defects still open.",
        test_round=4,
    )
    assert update["stage"] == "escalation"
    assert "remediation attempts" in update["escalation"]["error"]
    # The context still travels, so a resume has what it needs.
    assert update["test_round"] == 4


def _stuck(tmp_path, policy):
    return {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "review_policy": policy,
        "escalation": {"error": "Sprint exhausted its 3 remediation attempts with defects still open."},
    }


def test_a_run_with_no_reviewer_is_never_parked(tmp_path) -> None:
    for policy in ({}, {SPRINT_REVIEW: True}):
        update = escalation.escalation(_stuck(tmp_path, policy), {"configurable": {}}, None)
        assert update["stage"] == "failed"
        assert "remediation attempts" in update["error"]


def test_a_missing_policy_is_read_as_no_reviewer(tmp_path) -> None:
    state = _stuck(tmp_path, {})
    state.pop("review_policy")
    assert escalation.escalation(state, {"configurable": {}}, None)["stage"] == "failed"


def test_a_run_that_asked_for_a_reviewer_waits_for_one(tmp_path) -> None:
    update = escalation.escalation(
        _stuck(tmp_path, {escalation.ESCALATION_REVIEW: True}), {"configurable": {}}, None
    )
    assert update["stage"] == "user_review_escalation"
    assert "error" not in update


def test_no_escalation_routes_to_a_review_unconditionally() -> None:
    """Every call site goes through the helper, and the helper names no review."""
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    assert source.count('stage="user_review_sprint"') == 0
    definition = source.count("def _escalate_to_a_human(")
    calls = source.count("_escalate_to_a_human(") - definition
    assert definition == 1
    assert calls >= 3, f"expected every escalation to go through the helper, found {calls}"
