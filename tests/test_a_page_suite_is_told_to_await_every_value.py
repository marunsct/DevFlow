"""Every page pack's suite guidance says to await each Playwright call that gives back a value.

Measured over three runs: unawaited page assertions and an unawaited `headerValue()` (read as "[object Promise]")
each went to a fixer as a product fault; the guidance named none of them.
"""
from __future__ import annotations

import re

from app.stacks.packs import _javascript as js

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


def test_the_shared_control_guidance_carries_the_rule():
    assert js.AWAIT_EVERY_VALUE in js.FIND_CONTROLS
    for call in ("headerValue", "response.json()", "await expect(locator)"):
        assert call in js.AWAIT_EVERY_VALUE


def test_the_rule_names_what_takes_no_await():
    assert "response.status()" in js.AWAIT_EVERY_VALUE


def test_the_rule_uses_no_banned_word():
    for word in BANNED:
        assert not re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", js.AWAIT_EVERY_VALUE, re.I), word
