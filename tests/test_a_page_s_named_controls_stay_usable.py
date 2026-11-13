"""Every stage planning, building or judging a page is told a named control stays usable and refuses when tried.

Measured on two runs: the drafted page disabled the control adding a record while its required field was empty, its
unit tests asserted that, fixes keeping it usable were reverted for those tests, and a hidden test of the refusal timed
out on the disabled control - a false acceptance each time.
"""
import re

from app.agents import shared_facts
from app.stacks import pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_page_packs_carry_the_rule_and_others_do_not():
    for name in ("browser-react", "browser-javascript", "fullstack-page-fastapi"):
        assert shared_facts.CONTROLS_STAY_USABLE in shared_facts.layout_facts(pack_named(name), "app", None), name
    assert shared_facts.CONTROLS_STAY_USABLE not in shared_facts.layout_facts(pack_named("python-library"), "lib", "lib")


def test_it_says_refuse_when_tried_never_disable_and_uses_no_banned_word():
    rule = shared_facts.CONTROLS_STAY_USABLE
    assert "refused when it is tried" in rule and "never by disabling the control" in rule
    assert not BANNED.search(rule)
