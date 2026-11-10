"""What the brief states is never assumed, advised or restated otherwise before the specification.

Per-role audit over 30 runs: all four false acceptances came from the brief's wording overridden on the way to the
suite; two began as an intake assumption that output "preserves the original casing" where the brief said words are
compared in lower case - the advice repeated it and the specification adopted it.
"""
from __future__ import annotations

import re

from app.agents import assumptions, principal_architect, product_manager, specialist_advice
from app.agents.brief_over_spec import WHAT_THE_BRIEF_STATES

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_every_stage_that_fills_a_gap_before_the_specification_is_told():
    for prompt in (product_manager._SYSTEM_PROMPT, specialist_advice._SYSTEM_PROMPT, assumptions.RULE):
        assert WHAT_THE_BRIEF_STATES in prompt


def test_the_rule_names_what_the_brief_states_and_bans_the_product_words():
    for word in ("shown", "compared", "ordered", "formatted", "named", "open question"):
        assert word in WHAT_THE_BRIEF_STATES
    assert not BANNED.search(WHAT_THE_BRIEF_STATES)


# Measured on a Measure run (wordstats-cli, 6/8, a false acceptance): the brief said `--top N` prints the top words
# "instead"; the specification - written by the architect, who was not told this rule - added "followed by three-count
# summary lines", the suite followed the specification, and both hidden tests of the top words failed.
def test_the_architect_is_told_too_and_that_instead_means_nothing_else():
    prompt = principal_architect._SYSTEM_PROMPT
    assert WHAT_THE_BRIEF_STATES in prompt
    start = prompt.find("replaces another")
    rule = prompt[start - 80:start + 120]
    assert '"instead"' in rule and "prints\n  nothing else" in rule
    assert not BANNED.search(rule)
