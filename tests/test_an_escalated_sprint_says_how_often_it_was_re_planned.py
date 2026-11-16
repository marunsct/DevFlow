"""An escalated sprint says how many times it was really re-planned (LR.53).

Measured over the scored runs: the escalation always said "was re-planned 3 times" - the limit, not the count - so
105 results carried it, many after no re-plan at all (a sprint settled or stopped on its first attempt), and the
release's gap read as three failed attempts that never happened.
"""
from __future__ import annotations

from app.graph import delivery, workflow


def test_the_words_carry_the_count_not_the_limit():
    assert workflow.an_unfinished_sprint("Sign-up", 0, "AC-2 failed", "report").startswith(
        "Sprint 'Sign-up' was planned once and still could not be accepted: AC-2 failed.")
    assert "was re-planned 1 time and still" in workflow.an_unfinished_sprint("Sign-up", 1, "x", "r")
    assert "was re-planned 3 times and still" in workflow.an_unfinished_sprint("Sign-up", 3, "x", "r")


def test_the_release_still_recognises_each_wording():
    for replans in (0, 1, 3):
        text = workflow.an_unfinished_sprint("Sign-up", replans, "AC-2 failed", "report")
        assert delivery._AN_UNFINISHED_SPRINT.match(text), text
    assert delivery._AN_UNFINISHED_SPRINT.match("Sprint 'S' was re-planned 3 times and still could not be accepted: x")
