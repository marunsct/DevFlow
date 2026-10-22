"""A review the workflow accepts is filed as accepted.

A `changes_required` review whose findings are all below the gating severities
is routed down the accepted path. The record did not follow: one run's sprint
was accepted while its review document read "Status: changes_required", after
the one gating finding was contradicted by the command record and made minor.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.graph.workflow import _accepted_when_nothing_in_it_gates


class _Review(SimpleNamespace):
    def model_copy(self, update):
        return _Review(**{**self.__dict__, **update})


def _finding(severity: str) -> SimpleNamespace:
    return SimpleNamespace(severity=severity, description="x", category="testing")


def test_changes_required_over_minor_findings_alone_is_accepted() -> None:
    review = _Review(status="changes_required", findings=[_finding("minor"), _finding("suggestion")])

    assert _accepted_when_nothing_in_it_gates(review, "/nowhere").status == "accepted"


def test_a_gating_finding_keeps_it_as_written() -> None:
    review = _Review(status="changes_required", findings=[_finding("minor"), _finding("major")])

    assert _accepted_when_nothing_in_it_gates(review, "/nowhere") is review


def test_a_review_with_no_findings_is_left_to_its_own_handling() -> None:
    review = _Review(status="changes_required", findings=[])

    assert _accepted_when_nothing_in_it_gates(review, "/nowhere") is review


def test_other_statuses_are_untouched() -> None:
    for status in ("accepted", "blocked"):
        review = _Review(status=status, findings=[_finding("minor")])
        assert _accepted_when_nothing_in_it_gates(review, "/nowhere") is review
