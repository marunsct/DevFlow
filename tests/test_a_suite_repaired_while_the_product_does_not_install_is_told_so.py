"""QA repairing a suite while the product's dependencies do not install is told that, and that the manifest is not its.

Measured on one Ruby run: the product's Gemfile asked a sqlite3 version RubyGems never had, every install failed, and QA,
repairing one test of a reopened suite, spent a 22-minute round re-running its validation against a product that could
not install and tried six times to edit the Gemfile - refused each time, as QA writes only the suite.
"""
from __future__ import annotations

import re

from app.acceptance import requests, suite
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _a_measurement(monkeypatch, repairs):
    monkeypatch.setattr(suite, "last_result", lambda root: {"passed": 2, "failed": 10, "repairs": repairs})
    monkeypatch.setattr(suite, "location", lambda root: ("notes-api", "acceptance"))


def _content(tmp_path) -> str:
    return requests.build_author_request(tmp_path, [])["messages"][-1]["content"]


def test_a_failed_install_is_named_and_left_to_the_product(tmp_path, monkeypatch):
    _a_measurement(monkeypatch, [f"`bundle install` {contract.INSTALL_FAILED}; it said:\n"
                                 "Could not find gem 'sqlite3 (~> 1.0.2)' in rubygems repository\n; it ended: ..."])

    content = _content(tmp_path)

    assert "Could not find gem 'sqlite3 (~> 1.0.2)'" in content
    assert "do not install" in content and "not part of the suite" in content
    assert not BANNED.search(content.split("--- Acceptance criteria ---")[0])


def test_an_install_that_worked_says_nothing_of_it(tmp_path, monkeypatch):
    _a_measurement(monkeypatch, ["The project's dependencies were installed again: a manifest changed since the last install."])

    assert "do not install" not in _content(tmp_path)
