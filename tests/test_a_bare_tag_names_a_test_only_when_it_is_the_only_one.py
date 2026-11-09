"""A dispute line naming a bare criterion tag reopens a test only when one failing test carries that tag.

Deep review, acceptance A3: "[AC-4]: cannot pass, it asserts a title its steps never sent" named two failing tests of
AC-4; both were reopened, both counted against the cap, and QA was told to change the right one.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.agents import suite_dispute

WHY = "cannot pass for any product: it asserts a title its own steps never sent"


def test_a_tag_two_failing_tests_share_names_neither():
    answer = SimpleNamespace(cannot_pass=[f"[AC-4]: {WHY}"])
    named = suite_dispute.tests_it_names(answer, ["[AC-4] updates a note", "[AC-4] refuses an empty title"])
    assert named == []


def test_a_tag_one_failing_test_carries_names_it_and_a_full_name_always_does():
    answer = SimpleNamespace(cannot_pass=[f"[AC-4]: {WHY}"])
    assert len(suite_dispute.tests_it_names(answer, ["[AC-4] updates a note", "[AC-9] lists"])) == 1
    answer = SimpleNamespace(cannot_pass=[f"[AC-4] updates a note: {WHY}"])
    assert len(suite_dispute.tests_it_names(answer, ["[AC-4] updates a note", "[AC-4] refuses an empty title"])) == 1
