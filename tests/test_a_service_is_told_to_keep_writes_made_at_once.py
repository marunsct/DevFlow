"""A product that answers requests is told to keep each write when two arrive at the same moment (LR.25 follow-up).

Measured: the quality sets found products that lost or merged records written at once - 20 of 67 runs of one family
and the first scored run of another - while every hidden test passed; three of four benchmark references did the same.
"""
from __future__ import annotations

import re

from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_rule_reaches_serving_kinds_only():
    assert {"http_api", "fullstack"} == set(contract.KINDS_THAT_SERVE)
    source = open(contract.__file__, encoding="utf-8").read()
    assert "(f\"{WRITES_AT_ONCE}\\n\" if pack.kind in KINDS_THAT_SERVE else \"\")" in source


def test_its_words_are_general_and_ban_the_product_s_nouns():
    assert not BANNED.search(contract.WRITES_AT_ONCE)
    assert "one request at a time" in contract.WRITES_AT_ONCE
