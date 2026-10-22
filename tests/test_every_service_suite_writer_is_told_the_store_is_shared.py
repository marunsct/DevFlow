"""Every writer of a suite run against one service is told its store is shared by every test.

Measured on a gate run: a test asserted a signed-in account's list was empty
after signing in to an account an earlier test had filled - it could pass for
no product, and the suite was reopened and reviewed twice. Only one service
pack said so.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.acceptance import requests
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _pack(kind, guide):
    return SimpleNamespace(kind=kind, acceptance_guide=guide, acceptance_test=("pytest", "acceptance"),
                           filled=lambda text, project, title, package: text)


def _guide(monkeypatch, kind, guide):
    monkeypatch.setattr(contract, "the_pack", lambda root: (_pack(kind, guide), {"project": "app"}))
    return requests._how_to_write_them("/w", "app", "acceptance", None)


def test_a_service_or_fullstack_suite_is_told_and_a_guide_that_says_it_is_not_repeated(monkeypatch):
    assert requests.SHARED_STORE in _guide(monkeypatch, "http_api", "Write tests with httpx.")
    assert requests.SHARED_STORE in _guide(monkeypatch, "fullstack", "Write tests in Playwright.")
    already = "The service keeps its data, so a test must not assume it starts empty."
    assert requests.SHARED_STORE not in _guide(monkeypatch, "http_api", already)
    assert not BANNED.search(requests.SHARED_STORE)


def test_a_library_or_a_command_line_suite_is_not(monkeypatch):
    assert requests.SHARED_STORE not in _guide(monkeypatch, "library", "Import the package.")
    assert requests.SHARED_STORE not in _guide(monkeypatch, "cli", "Run the program.")
