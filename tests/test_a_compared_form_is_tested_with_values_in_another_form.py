"""A criterion comparing values in a normal form is tested with values in another form (found on three runs).

Measured on three runs of one brief: it said words are "compared in lower case", the locked tests used lower-case words
only, the product printed "The 3", and the hidden tests expecting "the 3" failed.
"""
from __future__ import annotations

import re

from app.acceptance.requests import TESTS_ASSUME_ONLY_WHAT_THEY_MADE
from app.agents import acceptance_reviewer

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _rule() -> str:
    start = TESTS_ASSUME_ONLY_WHAT_THEY_MADE.index("- Where a criterion compares values in a normal form")
    return TESTS_ASSUME_ONLY_WHAT_THEY_MADE[start:TESTS_ASSUME_ONLY_WHAT_THEY_MADE.index("\n", start)]


def test_the_writer_is_told_to_test_another_form_and_expect_the_normal_one():
    rule = " ".join(_rule().split())
    assert "give values in another form" in rule and "expect the normal form in what the product shows" in rule


def test_the_reviewer_is_shown_it_too():
    assert "expect the normal form in what the product shows" in " ".join(acceptance_reviewer._SYSTEM_PROMPT.split())


def test_the_rule_bans_the_product_words():
    assert not BANNED.search(_rule())
