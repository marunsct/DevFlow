"""The QA lead's dispute judges a locked test against its criterion, not against the code (measured live).

A dispute's reasons all compared tests with the implementation - "the schema only
has username", "the modal has no Tags field" - while the specification said
otherwise, and the suite was rewritten to match a product that departed from it.
"""
from __future__ import annotations

import re

from app.agents import suite_dispute

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_code_is_not_the_standard():
    prompt = suite_dispute._SYSTEM_PROMPT
    assert "The product's code is not the standard" in prompt
    assert "never open the product's files" in prompt
    start = prompt.index("The product's code is not the standard")
    assert not BANNED.search(prompt[start:start + 400])
