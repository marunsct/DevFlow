"""Every stage that writes is told to write in its calls, not in its reasoning.

Measured on two runs of one model: 75% of all output tokens were reasoning,
23 replies ran out of room while still reasoning, and one stage reasoned for
20,821 tokens and then reported edits it never made - it had made them in its
reasoning, and its answer said the file was cut when it was unchanged.
"""

from __future__ import annotations

import re

from app.agents.role_agent import _READ_ONLY_RULES, _WRITING_RULES

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


def _rule() -> str:
    return _WRITING_RULES[_WRITING_RULES.index("REASONING IS NOT WORK:"):_WRITING_RULES.index("ARTIFACTS ARE NOT YOUR STRUCTURED RESPONSE:")]


def test_every_writing_stage_is_told() -> None:
    rule = " ".join(_rule().split())
    assert "Write code, tests and file contents in the write and edit calls themselves" in rule
    assert "A change exists only when the call that made it succeeded" in rule


def test_a_stage_that_cannot_write_is_not() -> None:
    assert "REASONING IS NOT WORK" not in _READ_ONLY_RULES


def test_it_fits_any_product() -> None:
    text = _rule().lower()
    for word in BANNED:
        assert not re.search(rf"\b{word}\b", text), word
