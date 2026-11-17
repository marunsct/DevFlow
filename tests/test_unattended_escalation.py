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


def test_no_escalation_routes_to_a_review_unconditionally(tmp_path) -> None:
    """An exhausted sprint on a run with no reviewer goes to the escalation stage, which decides; never
    straight to a review. And no node of the graph names the sprint review as where it goes next."""
    from pathlib import Path

    from app.graph.workflow import MAX_MILESTONE_REVISIONS
    from app.sprint import Defect, RemediationCycle
    from workflow_nodes import a_test_round, reported

    still_open = Defect(description="Saving a note returns 500", severity="major", reproduction_steps="r",
                        expected_behavior="e", actual_behavior="a", owner="backend", affected_files=["app/server.js"])
    spent = RemediationCycle(sprint_goal="Sprint 1", defects=[still_open], attempt=3, max_attempts=3)

    update, _ = a_test_round(
        tmp_path, [reported("Deleting a note returns 500", affected_files=["app/server.js"])],
        state={"remediation": spent, "sprint_replan_count": MAX_MILESTONE_REVISIONS, "review_policy": {}},
    )

    assert update["stage"] == "escalation"
    assert "Sprint 1" in update["escalation"]["error"]

    graph = Path(escalation.__file__).parent
    routed = [path.name for path in graph.glob("*.py")
              if 'stage="user_review_sprint"' in path.read_text(encoding="utf-8")
              or '"stage": "user_review_sprint"' in path.read_text(encoding="utf-8")]
    assert routed == []
