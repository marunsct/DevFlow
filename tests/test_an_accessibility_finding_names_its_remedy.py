"""An accessibility finding says the change that settles each rule it names, without moving what the tests read.

Measured on three runs: the message shown when a list was empty sat inside the list as a plain element (the `list` rule
broken), and a fix that changed it was reverted for breaking the tests counting the list's items.
"""
import json
import re
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.graph import acceptance_nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_no_remedy_uses_a_banned_word():
    for text in acceptance_nodes.ACCESSIBILITY_REMEDIES.values():
        assert not BANNED.search(text), text


def _the_finding(tmp_path, rule: str) -> str:
    """What the UI/UX owner is told to expect when the page check finds `rule` broken."""
    saved = tmp_path / suite.RESULT_FILE
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_text(json.dumps({"ran": True, "shows": "list 'Notes'", "accessibility": [
        {"id": rule, "impact": "serious", "help": "h", "count": 1, "where": ["ul"]}]}))
    found = acceptance_nodes.interface_defects({"repository": SimpleNamespace(root_path=str(tmp_path))})
    return next(d.expected_behavior for d in found if "accessibility check" in d.description)


@pytest.mark.parametrize("rule", [
    "list",
    # Measured on one run: an empty-list message inside `<ul role="list">` was reported as `aria-required-children`,
    # got no remedy, and stayed open through three fix rounds.
    "aria-required-children",
])
def test_an_element_inside_a_list_is_told_to_go_beside_it(tmp_path, rule):
    expected = _the_finding(tmp_path, rule)

    assert "beside" in expected and "never inside it" in expected


def test_low_contrast_is_told_to_take_the_page_s_own_colours(tmp_path):
    assert "design tokens" in _the_finding(tmp_path, "color-contrast")
