"""An accessibility finding says the change that settles each rule it names, without moving what the tests read.

Measured on three runs: the message shown when a list was empty sat inside the list as a plain element (the `list` rule
broken), and a fix that changed it was reverted for breaking the tests counting the list's items.
"""
import inspect
import re

from app.graph import acceptance_nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_each_measured_rule_has_a_remedy_in_plain_words():
    remedies = acceptance_nodes.ACCESSIBILITY_REMEDIES
    assert {"list", "color-contrast"} <= set(remedies)
    assert "beside" in remedies["list"] and "never inside it" in remedies["list"]
    for text in remedies.values():
        assert not BANNED.search(text), text


def test_the_finding_carries_the_remedies_of_the_rules_it_names():
    source = inspect.getsource(acceptance_nodes)
    assert "ACCESSIBILITY_REMEDIES[rule.get('id')]" in source and 'if rule.get("id") in ACCESSIBILITY_REMEDIES' in source
