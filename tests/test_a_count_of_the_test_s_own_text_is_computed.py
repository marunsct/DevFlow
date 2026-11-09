"""The suite's writer and its reviewer are told a count of the test's own text is computed, never typed.

Measured on two runs in a row (both arms of a measurement): a locked test expected 24 characters for a string of 23
or 25, counted by hand; each cost two fix rounds on a product that counted right.
"""
from __future__ import annotations

import re

from app.acceptance.requests import TESTS_ASSUME_ONLY_WHAT_THEY_MADE
from app.agents import acceptance_reviewer

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _rule() -> str:
    return TESTS_ASSUME_ONLY_WHAT_THEY_MADE[TESTS_ASSUME_ONLY_WHAT_THEY_MADE.index("- A count or length"):]


def test_the_rule_says_compute_it_from_the_text():
    rule = " ".join(_rule().split())
    assert "is worked out in the test from that text" in rule and "never written as a number" in rule


def test_the_reviewer_is_shown_it_too():
    assert "never written as a number" in acceptance_reviewer._SYSTEM_PROMPT


def test_the_rule_bans_the_product_words():
    assert not BANNED.search(_rule())
