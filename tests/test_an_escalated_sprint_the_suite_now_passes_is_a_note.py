"""A sprint an escalation accepted unfinished, whose tests the locked suite passes in full at release, is a note (LR.21).

Measured on one run: a sprint accepted after three re-plans, a later sprint made all 31 locked tests pass, 10 of 10
hidden and 7 of 7 quality tests passed - and the run was called not deliverable for the old sprint.
"""
from __future__ import annotations

import inspect

from app import completion_verdict as cv
from app.graph import delivery

SPRINT = "Sprint 'Sign-up and sign-in' was re-planned 3 times and still could not be accepted: AC-2 failed.\\n\\nreport"


def test_it_is_a_note_when_the_suite_passes_at_release_and_blocks_otherwise():
    green = f"An escalation left this open (DR-14): {delivery.PASSES_AT_RELEASE}: {SPRINT}"
    assert not cv.is_blocking(green)
    assert cv.is_blocking(f"An escalation left this open (DR-14): {SPRINT}")


def test_the_release_says_so_only_for_an_unfinished_sprint_and_a_green_suite():
    assert delivery._AN_UNFINISHED_SPRINT.search(SPRINT)
    assert not delivery._AN_UNFINISHED_SPRINT.search("Design review left open: [blocking] x")
    source = inspect.getsource(delivery.release)
    assert "green_at_release = suite.is_locked(root) and not failing" in source
