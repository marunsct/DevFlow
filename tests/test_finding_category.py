"""A finding's category, read in the vocabulary the schema asks for.

The exact shape `app.agents.severity` was written for, one field along.
`severity` is forgiven when a model writes a word from a neighbouring
vocabulary; `category` was a bare `Literal` and was not, so one unrecognised
word threw away a whole review.

Measured live on one run at 05:36, on a model swapped in mid-run:

    Stage milestone_reviewer sent an answer that does not satisfy its
    schema (findings.4.category); returning the validation errors

It cost that review three and a half minutes and a full re-generation. Across
the same run the model wrote `code_quality` 24 times and `test` for `testing`
four times - both perfectly clear, neither in the list.
"""

from __future__ import annotations

import pytest

from app.agents.finding_category import normalise
from app.agents.milestone_reviewer import MilestoneReviewFinding

ALLOWED = (
    "correctness", "contracts", "migrations", "authorization", "accessibility",
    "testing", "documentation", "security", "regression", "code_quality", "other",
)


@pytest.mark.parametrize(
    "written,expected",
    [
        ("testing", "testing"),
        ("test", "testing"),
        ("Tests", "testing"),
        ("QA", "testing"),
        ("code_quality", "code_quality"),
        ("Code Quality", "code_quality"),
        ("maintainability", "code_quality"),
        ("performance", "code_quality"),
        ("lint", "code_quality"),
        ("data_leakage", "security"),
        ("isolation", "security"),
        ("vulnerability", "security"),
        ("a11y", "accessibility"),
        ("docs", "documentation"),
        ("bug", "correctness"),
    ],
)
def test_a_word_a_model_actually_writes_is_understood(written, expected):
    assert normalise(written, ALLOWED) == expected


@pytest.mark.parametrize("written", ["Static Hosting", "LocalStorage", "", "???"])
def test_something_unrecognised_is_kept_as_other(written):
    """Preserved rather than guessed at, and `other` can never block."""
    assert normalise(written, ALLOWED) == "other"


def test_a_schema_without_other_is_never_handed_one():
    narrow = ("testing", "security")
    assert normalise("Static Hosting", narrow) == "Static Hosting"


@pytest.mark.parametrize(
    "written", ["code_quality", "test", "maintainability", "Static Hosting", "a11y"]
)
def test_the_reviewer_no_longer_throws_the_review_away(written):
    finding = MilestoneReviewFinding(
        severity="major", category=written, description="d", required_remediation="r"
    )
    assert finding.category in ALLOWED


def test_other_can_never_hold_a_sprint(tmp_path):
    """The composition that makes `other` safe."""
    from app.analysis.scope_attestation import categories_in_scope, out_of_scope_reason

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text(
        "Build a to-do list with tests.\n", encoding="utf-8"
    )

    in_scope = categories_in_scope(tmp_path)
    assert out_of_scope_reason("other", in_scope)


def test_a_category_with_an_underscore_is_matched_against_the_table(tmp_path):
    """Both sides normalised, or neither.

    Stripping only the incoming value left `code_quality` as `codequality`,
    which matches no key, so every such finding was treated as a category the
    module does not know and allowed to block - silently, in exactly the
    category this model reaches for most after testing and security.
    """
    from app.analysis.scope_attestation import categories_in_scope, out_of_scope_reason

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text(
        "Build a to-do list with tests.\n", encoding="utf-8"
    )

    in_scope = categories_in_scope(tmp_path)
    assert out_of_scope_reason("code_quality", in_scope)
    assert out_of_scope_reason("Code Quality", in_scope)
