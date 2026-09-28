"""A finding about something nobody asked for cannot hold the sprint.

`SCOPE_DISCIPLINE` states this at every stage that can inflate scope:
"Something the intake does not ask for is not a requirement, however standard
the practice is... never as a blocking or major finding." It is stated, and
it is ignored.

Measured across all 50 stored transcripts, milestone review raised 174
findings of which 87 blocked:

    testing         59 blocking   24 advisory
    documentation    0 blocking   36 advisory
    accessibility   13 blocking   11 advisory
    security        11 blocking    8 advisory
    correctness      1 blocking    1 advisory

No brief in this repository contains "accessibility", "aria", "wcag",
"screen reader" or "contrast", and `accessibility` appears in zero of
one run's documents. Thirteen sprints were held up for a requirement
nobody stated, while only 2 of the 174 findings were about correctness at
all. Seven of the last sixty failures are runs that ended with "the milestone
review still required changes after N revisions".

So the rule becomes a check. The finding is still reported; it stops being a
reason for another round.
"""

from __future__ import annotations

import pathlib

import pytest

from app.analysis.scope_attestation import categories_in_scope, out_of_scope_reason


@pytest.fixture()
def workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "product_intake.md").write_text(
        "# To-Do List\nAdd, edit and delete tasks. Tasks persist between refreshes.\n"
        "## Acceptance Criteria\nFilter works correctly.\n",
        encoding="utf-8",
    )
    (docs / "technical_specification.md").write_text(
        "Testing framework: node --test. Secrets are never written to disk.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_a_category_the_documents_raise_can_block(workspace):
    in_scope = categories_in_scope(workspace)
    assert "testing" in in_scope
    assert out_of_scope_reason("testing", in_scope) == ""


def test_a_category_nobody_asked_for_cannot_block(workspace):
    in_scope = categories_in_scope(workspace)
    assert "accessibility" not in in_scope
    assert "cannot hold the sprint" in out_of_scope_reason("accessibility", in_scope)


def test_the_word_accessible_does_not_attest_accessibility(tmp_path):
    """The false positive this check was nearly shipped with.

    One run's tools-and-models document says "files are accessible via
    HTTPS" - a sentence about file access. A substring match on `accessib`
    took that as the brief asking for accessibility, which would have let the
    very findings this exists to cap go on blocking.
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "product_intake.md").write_text(
        "Public or private repos; files are accessible via HTTPS.\n", encoding="utf-8"
    )

    assert "accessibility" not in categories_in_scope(tmp_path)


def test_the_word_author_does_not_attest_security(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "product_intake.md").write_text("Author: a person.\n", encoding="utf-8")

    assert "security" not in categories_in_scope(tmp_path)


def test_a_brief_that_does_ask_for_accessibility_is_respected(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "product_intake.md").write_text(
        "The page must be usable with a screen reader.\n", encoding="utf-8"
    )

    in_scope = categories_in_scope(tmp_path)
    assert "accessibility" in in_scope
    assert out_of_scope_reason("accessibility", in_scope) == ""


def test_a_workspace_with_no_documents_caps_nothing(tmp_path):
    """Failing closed would cap legitimate findings before the docs exist."""
    in_scope = categories_in_scope(tmp_path)
    for category in ("accessibility", "testing", "security", "migrations"):
        assert out_of_scope_reason(category, in_scope) == ""


def test_the_review_documents_are_never_read(workspace):
    """A reviewer's own output would otherwise attest its own category."""
    (workspace / "docs" / "milestone_review.md").write_text(
        "Blocking: accessibility is missing aria labels.\n", encoding="utf-8"
    )

    assert "accessibility" not in categories_in_scope(workspace)


def test_an_unknown_category_is_left_alone(workspace):
    """Only categories this module knows about are judged."""
    assert out_of_scope_reason("something_new", categories_in_scope(workspace)) == ""


# --- the decision this feeds -------------------------------------------------


class _Finding:
    def __init__(self, category, severity):
        self.category = category
        self.severity = severity


class _Review:
    def __init__(self, findings):
        self.findings = findings


def test_an_out_of_scope_finding_stops_blocking(workspace):
    from app.graph.workflow import _findings_that_block

    review = _Review([
        _Finding("accessibility", "blocking"),
        _Finding("testing", "blocking"),
    ])

    kept = _findings_that_block(review, str(workspace))

    assert [f.category for f in kept] == ["testing"]


def test_without_a_workspace_the_decision_is_unchanged(workspace):
    """The gate is additive: no root, no capping."""
    from app.graph.workflow import _findings_that_block

    review = _Review([_Finding("accessibility", "blocking")])

    assert len(_findings_that_block(review)) == 1
