"""A suite's writer and reviewer are told a test picks out its own records by a marker each one carries (found on a run).

Measured on one run: a locked test made "Work <id>" and "Work Two <id>", kept those whose title held "Work <id>" and
expected two; the second title never held it, the test failed a right product through every round of fixes, and the
dispute, not told to look at how a test picks out its records, ruled it right.
"""
from __future__ import annotations

import re

from app.acceptance.requests import TESTS_ASSUME_ONLY_WHAT_THEY_MADE
from app.agents import acceptance_reviewer, suite_dispute

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _rule() -> str:
    start = TESTS_ASSUME_ONLY_WHAT_THEY_MADE.index("- A test picks out its own records")
    return TESTS_ASSUME_ONLY_WHAT_THEY_MADE[start:TESTS_ASSUME_ONLY_WHAT_THEY_MADE.index("\n", start)]


def test_the_writer_is_told_to_pick_its_records_by_a_marker_each_carries_whole():
    rule = " ".join(_rule().split())
    assert "one marker every one of them carries whole" in rule
    assert "never by a piece of one record's name" in rule


def test_the_reviewer_is_shown_it_too():
    assert "one marker every one of them carries whole" in " ".join(acceptance_reviewer._SYSTEM_PROMPT.split())


def test_the_dispute_names_a_test_whose_way_of_picking_its_records_misses_one():
    prompt = " ".join(suite_dispute._SYSTEM_PROMPT.split())
    assert "a way of picking out its own records that does not match every record it made" in prompt


def test_the_new_rules_ban_the_product_words():
    assert not BANNED.search(_rule())
    assert not BANNED.search("a way of picking out its own records that does not match every record it made")
