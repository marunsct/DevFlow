"""A test's criterion ids come from its own name; the spec file's name (its JUnit classname) only when it has none.

Deep review, acceptance A1: a file named for one criterion tagged every test in it, so a failing test of another
criterion charged it; the round raised it, dispatch found it passing and closed it, and the next round raised it again.
"""
from __future__ import annotations

from app.acceptance.junit import TestResult


def test_the_name_s_tags_win_over_the_file_s():
    test = TestResult(name="[AC-5] deletes a note", suite="ac-3.spec.js")
    assert test.tags == ("AC-5",)


def test_a_name_with_no_tag_takes_its_describe_or_file_s():
    assert TestResult(name="deletes a note", suite="ac-3.spec.js").tags == ("AC-3",)
    assert TestResult(name="deletes a note", suite="test", within="AC-7 notes").tags == ("AC-7",)
