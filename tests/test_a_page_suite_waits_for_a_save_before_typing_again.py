"""A writer of a suite that drives a page is told to wait for a save before typing into the form again.

Measured on runs: a test saved an entry and typed the next one at once; the page emptied its form when the save
finished and erased what the test had typed, and the test failed a product that was right.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.acceptance import requests
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _guide(monkeypatch, kind):
    pack = SimpleNamespace(kind=kind, acceptance_guide="Write the tests.", acceptance_test=("npx", "playwright", "test"),
                           filled=lambda text, project, title, package: text)
    monkeypatch.setattr(contract, "the_pack", lambda root: (pack, {"project": "app"}))
    return requests._how_to_write_them("/w", "app", "acceptance", None)


def test_a_suite_that_drives_a_page_is_told(monkeypatch):
    for kind in ("browser_app", "fullstack"):
        assert requests.WAIT_FOR_THE_SAVE in _guide(monkeypatch, kind), kind


def test_a_suite_that_drives_no_page_is_not(monkeypatch):
    for kind in ("http_api", "cli", "library"):
        assert requests.WAIT_FOR_THE_SAVE not in _guide(monkeypatch, kind), kind


def test_the_rule_names_no_product():
    assert not BANNED.search(requests.WAIT_FOR_THE_SAVE)
