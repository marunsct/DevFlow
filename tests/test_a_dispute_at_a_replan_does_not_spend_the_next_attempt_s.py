"""A dispute held at a re-plan judges the attempt that failed; the next attempt may still hold its own.

Measured on one run: the re-plan dispute after attempt N and a dispute held during attempt N+1 shared one key, so every
fixer that blamed a locked test during the next two attempts found its attempt "already disputed" - fixers worked a
right product for 283 more model calls until the run escalated.
"""
from __future__ import annotations

from app.graph import acceptance_nodes, workflow


def _state(attempts: int, disputed: list[str]) -> dict:
    return {"current_sprint_index": 0, "sprint_attempts": [{"sprint_index": 0}] * attempts,
            "disputed_sprints": disputed}


def test_the_replan_key_names_the_attempt_that_failed_and_the_running_key_the_next():
    after_one_failure = _state(1, [])
    assert workflow._this_attempt(after_one_failure, judging_the_last=True) == "0:0"
    assert workflow._this_attempt(after_one_failure) == "0:1"
    assert workflow._this_attempt(_state(0, []), judging_the_last=True) == "0:0"


def test_a_fixer_s_blame_during_the_next_attempt_may_still_be_judged(monkeypatch):
    monkeypatch.setattr(workflow, "_the_locked_tests_still_failing", lambda state: [("test_ac3_json", "f", "x")])
    monkeypatch.setattr(acceptance_nodes, "may_repair", lambda state, broken: True)
    replan_key = workflow._this_attempt(_state(1, []), judging_the_last=True)
    assert workflow._a_dispute_may_be_held_now(_state(1, [replan_key])) is True
    # Its own dispute held, the attempt holds no second one.
    assert workflow._a_dispute_may_be_held_now(_state(1, [replan_key, workflow._this_attempt(_state(1, []))])) is False
