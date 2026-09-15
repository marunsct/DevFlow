"""Optional user review sessions for generated artifacts (Step 3.3).

This module is deliberately separate from `app.agents.approval`. That module
implements a *mandatory* safety gate: every artifact write pauses so a human
can approve, edit, or reject it before anything is saved (Step 3.2). This
module implements an *optional*, collaborative review that can happen after an
artifact already exists: a user may inspect it, comment, request changes, or
explicitly skip the review. Skipping must never look like approval, so
`ReviewRequestStatus.SKIPPED` is a distinct value a workflow or auditor can
tell apart from `ReviewRequestStatus.APPROVED`.

The functions here are pure and synchronous: they take a `ReviewStatus` (see
`app.state`) and return a new one, so callers (future graph nodes, tests, or a
web API handler) can compose them without hidden side effects.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.state import ReviewRequestStatus, ReviewStatus, WorkflowStage

def _max_review_reruns() -> int:
    """Bound the automatic reruns triggered by 'changes requested'.

    Without a limit, a review that never converges loops the same role agent
    forever. Once reached, `request_changes` raises instead of producing another
    revision, so the workflow pauses for a human.

    Configurable because the limit counts *rejections*, not failures to improve,
    and those are not always the same thing. On run-0b55ad49 all three were
    spent on defects in the workflow itself - a sandbox limit that broke every
    test, a prompt example that built the project in the wrong directory, two
    competing npm projects - each fixed between rejections. The budget was
    exhausted before the agent was given a single actionable instruction.
    """
    import logging
    import os

    raw = os.environ.get("WORKFLOW_MAX_REVIEW_RERUNS", "").strip()
    if not raw:
        return 3
    try:
        return max(1, int(raw))
    except ValueError:
        logging.getLogger(__name__).warning(
            "Malformed WORKFLOW_MAX_REVIEW_RERUNS=%r; using 3", raw
        )
        return 3


DEFAULT_MAX_REVIEW_RERUNS = _max_review_reruns()


class ReviewRerunLimitExceeded(RuntimeError):
    """Raised when 'changes requested' would exceed the configured rerun limit."""


def _now() -> str:
    """Return the current UTC time as an ISO-8601 string for review timestamps."""
    return datetime.now(timezone.utc).isoformat()


def start_review(
    *,
    run_id: str,
    thread_id: str,
    stage: WorkflowStage,
    artifact_id: str,
    reviewer: str,
) -> ReviewStatus:
    """Create a new pending review request for one stage's artifact.

    Revision starts at 1 because the artifact being reviewed is itself the
    first revision; `request_changes` increments this each time a new
    revision is requested.
    """
    timestamp = _now()
    return ReviewStatus(
        stage=stage,
        status=ReviewRequestStatus.PENDING,
        reviewer=reviewer,
        revision=1,
        run_id=run_id,
        thread_id=thread_id,
        artifact_id=artifact_id,
        created_at=timestamp,
        updated_at=timestamp,
    )


def skip_review(review: ReviewStatus) -> ReviewStatus:
    """Explicitly record that the user skipped this optional review.

    Skipping must be visible as its own status rather than silently treated as
    approval, so later stages and auditors can tell the difference between
    "a human looked at this and approved it" and "no one reviewed this."
    """
    return review.model_copy(update={"status": ReviewRequestStatus.SKIPPED, "updated_at": _now()})


def approve_review(review: ReviewStatus, *, comment: str | None = None) -> ReviewStatus:
    """Record that the user approved the current artifact revision as-is."""
    updates: dict[str, object] = {"status": ReviewRequestStatus.APPROVED, "updated_at": _now()}
    if comment:
        updates["comments"] = [*review.comments, comment]
    return review.model_copy(update=updates)


def request_changes(review: ReviewStatus, *, comment: str) -> ReviewStatus:
    """Record requested changes and advance the revision counter.

    Raises:
        ReviewRerunLimitExceeded: if accepting this request would exceed
            `DEFAULT_MAX_REVIEW_RERUNS`, so the caller can pause the workflow
            with a clear error instead of rerunning the same role agent
            indefinitely on a review that never converges.
    """
    next_revision = review.revision + 1
    if next_revision > DEFAULT_MAX_REVIEW_RERUNS:
        # `review.stage` is a `WorkflowStage`, and an f-string renders that as
        # `WorkflowStage.IMPLEMENTATION` on Python 3.11+. The value is what a
        # reader recognises.
        stage_name = getattr(review.stage, "value", review.stage)
        raise ReviewRerunLimitExceeded(
            f"The '{stage_name}' stage has been sent back for changes "
            f"{review.revision - 1} time(s), which is the configured limit of "
            f"{DEFAULT_MAX_REVIEW_RERUNS}. It will not rerun again on its own.\n\n"
            "If the earlier rejections were about problems that have since been "
            "fixed elsewhere, raise WORKFLOW_MAX_REVIEW_RERUNS and resume - the "
            "budget counts rejections, not failures to improve. Otherwise this "
            "stage is not converging and needs a person to look at the work."
        )
    return review.model_copy(
        update={
            "status": ReviewRequestStatus.CHANGES_REQUESTED,
            "revision": next_revision,
            "comments": [*review.comments, comment],
            "updated_at": _now(),
        }
    )


def build_revision_prompt(previous_artifact_text: str, comments: list[str]) -> str:
    """Build the message sent back to a role agent to produce a new revision.

    Including the previous artifact and the specific requested changes lets
    the agent make a targeted revision instead of guessing what to fix or
    silently discarding earlier content that was never flagged.
    """
    joined_comments = "\n".join(f"- {comment}" for comment in comments)
    return (
        "A human reviewer requested changes to your previous artifact.\n\n"
        f"--- Previous artifact ---\n{previous_artifact_text}\n\n"
        f"--- Requested changes ---\n{joined_comments}\n\n"
        "Create a new revision that addresses every requested change. Do not "
        "silently drop earlier content that reviewers did not flag."
    )


__all__ = [
    "DEFAULT_MAX_REVIEW_RERUNS",
    "ReviewRerunLimitExceeded",
    "approve_review",
    "build_revision_prompt",
    "request_changes",
    "skip_review",
    "start_review",
]
