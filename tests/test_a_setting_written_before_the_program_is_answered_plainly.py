"""A command written `NAME=value program ...` is answered as what it is (LF.1314).

Measured on one medium run: thirteen calls set a browser folder before `npx playwright install`, and each was told
the setting's name "is not permitted for role", with the list of programs - so the next call tried another folder.
"""
from __future__ import annotations

import re

import pytest

from app.tools import sandbox

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _refusal(argv: list[str]) -> str:
    with pytest.raises(sandbox.CommandNotAllowed) as refused:
        sandbox.validate_command(argv, "testing_specialist")
    return str(refused.value)


def test_the_setting_is_named_and_the_program_is_given_without_it():
    said = _refusal(["PLAYWRIGHT_BROWSERS_PATH=/tmp/x", "npx", "playwright", "install", "chromium"])

    assert "there is no shell here" in said
    assert "['npx', 'playwright', 'install', 'chromium']" in said
    assert "is not permitted for role" not in said
    assert not BANNED.search(said)


def test_a_program_not_permitted_after_the_setting_is_still_refused_as_such():
    said = _refusal(["DEBUG=1", "curl", "http://x"])

    assert "'curl' is not permitted for role 'testing_specialist'" in said
