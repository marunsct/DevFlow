"""A custom setup is asked to write its declaration first (measured live, three runs of three).

The setup request listed the declaration as its last step. On each of three
baselines the first setup attempt spent its call budget on the project - and on
product code - and ended without `stack-setup.json`, the one file the harness
proves a setup from; each was started again from nothing, about ten minutes lost.
"""
from __future__ import annotations

import re

from app.stacks import custom_setup

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _text() -> str:
    return custom_setup.build_setup_request("notes-api", {"language": "TypeScript"}, "http_api")["messages"][-1]["content"]


def test_the_declaration_is_asked_for_before_any_step():
    text = _text()
    first = text.index("First, before anything else, write `notes-api/stack-setup.json`")

    assert first < text.index("1. Create the project")
    assert "started again from nothing" in text


def test_the_last_step_brings_it_up_to_date():
    assert "4. Bring `notes-api/stack-setup.json` up to date" in _text()


def test_the_new_lines_use_none_of_the_banned_words():
    text = _text()
    start = text.index("First, before anything else")
    assert not BANNED.search(text[start:text.index("1. Create the project")])
