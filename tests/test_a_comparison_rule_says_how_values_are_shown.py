"""The architect is told that a rule for comparing values must also say how those values are shown.

Measured on two runs (one review with reasoning, one without): the brief said "Words are compared in lower case";
the products counted case-insensitively and printed each word as first read ("The 3"), and two hidden tests expected
"the 3". The specification never said, and the suite never checked.
"""
from __future__ import annotations

import re

from app.agents import principal_architect

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _rule() -> str:
    prompt = principal_architect._SYSTEM_PROMPT
    start = prompt.index("- Where the brief says how values are compared")
    return prompt[start:prompt.index("\n- ", start + 3)]


def test_the_rule_asks_for_the_shown_form():
    rule = " ".join(_rule().split())
    assert "also say in what form those values are shown" in rule


def test_the_rule_bans_the_product_words():
    assert not BANNED.search(_rule())


def test_a_named_compared_form_is_the_shown_form():
    """Measured on a third run: "compared in lower case"; the architect chose "the casing of the first occurrence",
    the suite followed it, and the two hidden tests expecting the lower-case form failed (a false acceptance)."""
    rule = " ".join(_rule().split())
    assert "Where the brief names the form they are compared in" in rule
    assert "they are shown in that form unless the brief shows otherwise" in rule
