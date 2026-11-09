"""A test the dispute calls wrong past the reclassification cap has its criterion deferred, not re-planned against.

Measured on one run: two tests the dispute rightly called wrong (a character count off by one) were past the cap, so
they stayed locked - as the cap means - and the sprint was planned again for hours against a product that counted
right. The cap's own words say such a test is carried to the release; deferring its criterion with why does that.
"""
from __future__ import annotations

import inspect

from app.graph import workflow


def test_the_criteria_of_the_tests_past_the_cap_are_named():
    failing = [
        ("test_ac6_no_trailing_newline", "AC-6: Run as python -m wordstats <file>", "assert 'characters: 18' in ..."),
        ("test_ac1_ac3_json_output", "AC-1: Count the words; AC-3: --json prints ...", "lines == 2"),
        ("test_ac9_top", "AC-9: --top N", "a real failure"),
    ]
    assert workflow.criteria_past_the_cap(failing, ["test_ac6_no_trailing_newline", "test_ac1_ac3_json_output"]) == [
        "AC-1", "AC-3", "AC-6"]
    assert workflow.criteria_past_the_cap(failing, []) == []


def test_the_dispute_defers_them_as_beyond_repair():
    source = inspect.getsource(workflow)
    at = source.index("reclassification cap; they stay as they are")
    after = source[at:at + 1600]
    assert "criteria_past_the_cap(failing, past_the_cap)" in after
    assert "acceptance_nodes.defer_what_is_beyond_repair(state, beyond," in after
