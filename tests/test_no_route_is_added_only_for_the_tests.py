"""Builders and fixers are told the product ships every route it has, so none is added only for the tests.

Measured on one run: acceptance tests collided on shared data, a work order made a root `conftest.py` that cleans
up between tests by calling the product, and a fixer added an unauthenticated route deleting every record and token.
"""
from __future__ import annotations

import re

from app.agents.specialists import _system_prompt
from app.agents.testability import TESTABILITY_RULE

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _rule() -> str:
    return TESTABILITY_RULE[TESTABILITY_RULE.index("- THE PRODUCT SHIPS EVERY ROUTE"):]


def test_the_rule_names_the_hook_and_what_to_do_instead():
    rule = " ".join(_rule().split())
    assert "only so tests can reset, seed or inspect its data" in rule
    assert "a unique name or account for each test" in rule


def test_the_rule_bans_the_product_words():
    assert not BANNED.search(_rule())


def test_a_builder_is_shown_it():
    assert "THE PRODUCT SHIPS EVERY ROUTE AND COMMAND IT HAS" in _system_prompt("backend")
