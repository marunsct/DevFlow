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


# ---------------------------------------------------------------------------
# The rerun limit, and what it says when it fires
#
# The budget counts *rejections*, which are not the same as failures to
# improve. On one run all three were spent on defects in the workflow
# itself - a sandbox limit that broke every test, a prompt example that built
# the project in the wrong directory, two competing npm projects - each fixed
# between rejections. The budget was exhausted before the agent had been given
# one actionable instruction.
# ---------------------------------------------------------------------------


def test_the_limit_message_names_the_stage_not_its_enum():
    """`WorkflowStage.IMPLEMENTATION` is a Python repr, not a stage a reader knows."""
    import app.review as review_module
    from app.state import WorkflowStage

    review = review_module.start_review(
        run_id="r", thread_id="t", stage=WorkflowStage.IMPLEMENTATION,
        artifact_id="sprint-milestone", reviewer="arun",
    )
    for index in range(review_module.DEFAULT_MAX_REVIEW_RERUNS):
        try:
            review = review_module.request_changes(review, comment=f"round {index}")
        except review_module.ReviewRerunLimitExceeded as exceeded:
            message = str(exceeded)
            assert "implementation" in message
            assert "WorkflowStage" not in message, "the enum repr leaked into the message"
            return
    pytest.fail("the limit never fired")


def test_the_limit_message_says_what_to_do_about_it():
    import app.review as review_module
    from app.state import WorkflowStage

    review = review_module.start_review(
        run_id="r", thread_id="t", stage=WorkflowStage.IMPLEMENTATION,
        artifact_id="a", reviewer="arun",
    )
    with pytest.raises(review_module.ReviewRerunLimitExceeded) as excinfo:
        for index in range(review_module.DEFAULT_MAX_REVIEW_RERUNS + 1):
            review = review_module.request_changes(review, comment=f"round {index}")

    message = str(excinfo.value)
    assert "WORKFLOW_MAX_REVIEW_RERUNS" in message, "no way out is offered"
    assert "counts rejections" in message


def test_the_rerun_budget_is_configurable(monkeypatch):
    from app.review import _max_review_reruns

    monkeypatch.setenv("WORKFLOW_MAX_REVIEW_RERUNS", "6")
    assert _max_review_reruns() == 6
    monkeypatch.setenv("WORKFLOW_MAX_REVIEW_RERUNS", "nonsense")
    assert _max_review_reruns() == 3
    monkeypatch.setenv("WORKFLOW_MAX_REVIEW_RERUNS", "0")
    assert _max_review_reruns() >= 1, "a limit of zero would reject the first change request"
