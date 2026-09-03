"""Tests for optional user review sessions (Step 3.3).

These are pure, fast unit tests: no agent, model, or LangGraph invocation is
needed because `app.review` only transforms `ReviewStatus` values.
"""

from __future__ import annotations

import pytest

from app.review import (
    DEFAULT_MAX_REVIEW_RERUNS,
    ReviewRerunLimitExceeded,
    approve_review,
    build_revision_prompt,
    request_changes,
    skip_review,
    start_review,
)
from app.state import ReviewRequestStatus, WorkflowStage


def _new_review():
    return start_review(
        run_id="run-1",
        thread_id="thread-1",
        stage=WorkflowStage.ARCHITECTURE,
        artifact_id="technical-specification.md",
        reviewer="user-1",
    )


def test_start_review_is_pending_at_revision_one() -> None:
    review = _new_review()

    assert review.status == ReviewRequestStatus.PENDING
    assert review.revision == 1
    assert review.run_id == "run-1"
    assert review.thread_id == "thread-1"
    assert review.artifact_id == "technical-specification.md"
    assert review.created_at == review.updated_at


def test_skip_review_is_distinct_from_approval() -> None:
    review = skip_review(_new_review())

    assert review.status == ReviewRequestStatus.SKIPPED
    assert review.status != ReviewRequestStatus.APPROVED


def test_approve_review_records_optional_comment() -> None:
    review = approve_review(_new_review(), comment="Looks good.")

    assert review.status == ReviewRequestStatus.APPROVED
    assert review.comments == ["Looks good."]


def test_request_changes_advances_revision_and_records_comment() -> None:
    review = request_changes(_new_review(), comment="Please add a rollback plan.")

    assert review.status == ReviewRequestStatus.CHANGES_REQUESTED
    assert review.revision == 2
    assert review.comments == ["Please add a rollback plan."]


def test_request_changes_raises_after_rerun_limit() -> None:
    review = _new_review()
    for _ in range(DEFAULT_MAX_REVIEW_RERUNS - 1):
        review = request_changes(review, comment="one more pass")

    with pytest.raises(ReviewRerunLimitExceeded):
        request_changes(review, comment="past the limit")


def test_build_revision_prompt_includes_artifact_and_comments() -> None:
    prompt = build_revision_prompt("old text", ["fix typo", "add section"])

    assert "old text" in prompt
    assert "fix typo" in prompt
    assert "add section" in prompt
