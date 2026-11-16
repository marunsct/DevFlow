"""A finished run says one of three things about its product: delivered, delivered with cuts, or not deliverable.

Measured over the last 150 scored runs (LR.21, LR.22): every gap but a list of notes made a run "non-deliverable",
so 66 of them were marked, 57 of those passed every hidden test, and the marker missed 4 of the 13 that lost one.
29 runs shipped a criterion deferred, unproven by the suite, and none of them lost a hidden test: a stated scope cut,
told to the reader, not a sign the product fails.
"""
from __future__ import annotations

from types import SimpleNamespace

from app import completion_verdict as cv
from app.server import runs

CUT = "AC-4 ships deferred, unproven by the suite: the export view"
FAILS = "3 of the project's own unit tests still fail and ship failing: test_a, test_b, test_c"
NOTE = "2 line(s) of the interface contract were not checked at release: GET /x"


def test_the_three_verdicts():
    assert cv.verdict([]) == cv.DELIVERED
    assert cv.verdict([NOTE]) == cv.DELIVERED
    assert cv.verdict([NOTE, CUT]) == cv.DELIVERED_WITH_CUTS
    assert cv.verdict([CUT, FAILS]) == cv.NOT_DELIVERABLE
    assert cv.verdict(["A gap of a kind never seen before"]) == cv.NOT_DELIVERABLE


def test_a_cut_does_not_block_and_is_listed_apart():
    assert cv.is_blocking(CUT) is False and cv.is_a_cut(CUT)
    assert cv.split([CUT, FAILS]) == ([FAILS], [CUT])


def test_the_run_s_record_carries_its_verdict_only_when_it_completed():
    done = SimpleNamespace(status="completed", completion_gaps=[NOTE, CUT])
    assert runs._the_verdict(done) == {"verdict": cv.DELIVERED_WITH_CUTS, "scope_cuts": [CUT]}
    assert runs._the_verdict(SimpleNamespace(status="failed", completion_gaps=[CUT])) == {"verdict": "", "scope_cuts": []}
