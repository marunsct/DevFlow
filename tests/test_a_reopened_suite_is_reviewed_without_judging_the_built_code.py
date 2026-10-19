"""A suite reopened part-way through a build is reviewed against its criteria alone (measured live).

The reviewer's prompt said the product "has not been built yet". A suite reopened
after a dispute meets a product that is half built, and the reviewer opened its
files and sent tests back for what that code did not register or render - things
a later sprint builds. The prompt now says the built code is not the standard.
"""
from __future__ import annotations

import re

from app.agents import acceptance_reviewer

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
PROMPT = acceptance_reviewer._SYSTEM_PROMPT


def test_the_prompt_no_longer_claims_nothing_is_built():
    assert "has not been built yet" not in PROMPT


def test_the_built_code_is_not_the_standard_for_a_test():
    assert "whatever part of it is built" in PROMPT
    assert "Never open its\nfiles" in PROMPT


def test_the_new_rule_uses_none_of_the_banned_words():
    start = PROMPT.index("whatever part of it is built")
    assert not BANNED.search(PROMPT[start:start + 600])
