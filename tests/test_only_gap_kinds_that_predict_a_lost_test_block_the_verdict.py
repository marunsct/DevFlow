"""Only the kinds of completion gap that predict a lost hidden or quality test make a product "not deliverable".

Deep review 2026-11-18, item B4: over 427 scored runs a "not deliverable" verdict lost a hidden or quality test no
more often than "delivered" (39 of 181 against 53 of 246). An escalation's open issue (106 runs, 17% lost), failing
unit tests of the product's own (94 runs, 23%), a static re-reading's finding (19 runs, 21%) and write lines left
unasked by the concurrent-write probe lost no more often than all runs (22%), so they are notes; a broken contract
line, an unproven setup and a milestone finding marked blocking still block.
"""
from __future__ import annotations

import pytest

from app import completion_verdict

NOTES = [
    "An escalation left this open: Sprint 'Users can add and remove notes' accepted with 2 locked test(s) failing.",
    "An escalation left this open (DR-14): The sprint's own test suite was still failing after 3 revisions.",
    "3 of the project's own unit tests still fail and ship failing (the locked acceptance suite passes; the fixes did "
    "not close them): tests/test_store.py::test_ids.",
    "At release, reading the files still finds: notes/package.json still has the placeholder test script.",
    "3 write line(s) of the interface contract were not sent 16 creates at once: AC-9 POST /signup -> 201.",
]

BLOCKING = [
    "At release the product does not keep its interface contract: [AC-3] contract 4: AC-3 GET /notes/:id -> 404",
    "The project setup was never proven: its smoke tests did not pass",
    "A milestone review's findings were recorded as risks, not fixed (DR-3): [blocking] correctness: ids repeat",
    "The product changed at release, after the suite last measured it, and the suite run again failed 2 test(s): x",
    "At release a harness probe still finds: Writes made at the same moment are not each kept: x",
    "No acceptance suite was locked; the milestone reviews were the only gate.",
]


@pytest.mark.parametrize("gap", NOTES)
def test_a_gap_kind_that_lost_no_more_often_than_any_run_is_a_note(gap) -> None:
    assert not completion_verdict.is_blocking(gap)
    assert completion_verdict.verdict([gap]) == completion_verdict.DELIVERED


@pytest.mark.parametrize("gap", BLOCKING)
def test_a_gap_kind_that_predicts_a_lost_test_still_blocks(gap) -> None:
    assert completion_verdict.verdict([*NOTES, gap]) == completion_verdict.NOT_DELIVERABLE


def test_a_demoted_gap_is_kept_as_a_note_not_dropped() -> None:
    blocking, notes = completion_verdict.split(NOTES)

    assert blocking == []
    assert notes == NOTES
