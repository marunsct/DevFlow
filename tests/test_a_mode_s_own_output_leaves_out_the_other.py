"""A mode whose output replaces another's is tested for the other output's absence, by the writer and its reviewer.

Measured on two runs, both false acceptances of one brief: a mode's output was given in place of another's, the
locked test checked only that the mode's own part was there, and a product that printed both passed it.
"""
from __future__ import annotations

import re

from app.acceptance import requests
from app.agents import acceptance_reviewer

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
RULE = "a test of that mode also checks the other output is absent"


def test_the_writer_and_the_reviewer_are_told():
    assert RULE in requests.TESTS_ASSUME_ONLY_WHAT_THEY_MADE
    assert RULE in acceptance_reviewer._SYSTEM_PROMPT or RULE in str(getattr(acceptance_reviewer, "SYSTEM_PROMPT", ""))


def test_it_reaches_the_writer_s_request(tmp_path):
    said = str(requests.build_author_request(tmp_path, []))
    assert RULE in said and "whole set of keys or lines" in said


def test_the_rule_names_no_product():
    assert not BANNED.search(requests.TESTS_ASSUME_ONLY_WHAT_THEY_MADE)
