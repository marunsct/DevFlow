"""The architect adds no limit the brief does not state, and states a needed one once.

Measured over 14 runs' first architecture reviews: 19 of 31 blocking or major findings were the specification
contradicting itself - mostly limits the brief never set (a title's maximum length, a request's size) given one
value in one section and another elsewhere - and 21 of 23 runs needed a second design.
"""
import re

from app.agents import principal_architect


def test_the_architect_is_told():
    assert principal_architect.ONE_SOURCE_FOR_LIMITS in principal_architect._SYSTEM_PROMPT


def test_the_rule_uses_none_of_the_banned_words():
    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b",
                         principal_architect.ONE_SOURCE_FOR_LIMITS, re.I)
