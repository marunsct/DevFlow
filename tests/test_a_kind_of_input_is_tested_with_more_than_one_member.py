"""A criterion about a kind of input is tested with more than one member of it, by the writer and as the reviewer judges.

Measured on one run, a false acceptance: the brief said `title_case` leaves "the whitespace exactly as it was"; every
locked test used spaces alone, the product split words on spaces only, and a hidden test with a tab failed.
"""
from __future__ import annotations

import re

from app.acceptance import requests
from app.agents import acceptance_reviewer

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_writer_and_the_reviewer_are_told():
    rule = "its tests use more than one member of that kind (a space and a tab"
    assert rule in requests.TESTS_ASSUME_ONLY_WHAT_THEY_MADE
    assert rule in acceptance_reviewer._SYSTEM_PROMPT or rule in str(getattr(acceptance_reviewer, "SYSTEM_PROMPT", ""))


def test_the_rule_names_no_product():
    assert not BANNED.search(requests.TESTS_ASSUME_ONLY_WHAT_THEY_MADE)
