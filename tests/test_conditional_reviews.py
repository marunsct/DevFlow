"""Tests for conditional security and advice reviews.

Milestones that only touched stylesheets or non-code files do not require
spinning up full security and database review agents when no relevant files changed.
"""

from __future__ import annotations

from app.agents.security_reviewer import SecurityReviewOutput
from app.agents.advice_review import AdviceReview


def test_clean_security_review_output() -> None:
    review = SecurityReviewOutput(status="passed", findings=[])
    assert review.status == "passed"
    assert len(review.findings) == 0


def test_clean_advice_review_output() -> None:
    review = AdviceReview(not_built=[], design_problems=[])
    assert len(review.not_built) == 0
    assert len(review.design_problems) == 0

