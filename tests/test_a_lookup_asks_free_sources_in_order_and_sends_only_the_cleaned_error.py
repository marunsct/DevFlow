"""A lookup asks free, official sources in order, sends only the cleaned error, and keeps each answer for a week (WL.2).

Owner, 2026-11-20: agents look things up when they are stuck. Measured: the model never called the search tools it
was offered, the private search's general engines refused it, and open-source harnesses' free routes (DuckDuckGo
scraping) are rate-limited under agent load - so the harness asks Stack Exchange's and GitHub's own APIs first.
"""
from __future__ import annotations

import json
import re

import pytest

from app.tools import lookups

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

QUESTIONS = {"items": [{"title": "cannot borrow as mutable", "link": "https://stackoverflow.com/q/1",
                        "accepted_answer_id": 11, "last_activity_date": 1_700_000_000}]}
ANSWERS = {"items": [{"answer_id": 11, "body": "<p>Clone the value first, or end the immutable borrow.</p>"}]}
ISSUES = {"items": [{"title": "E0502 with rusqlite", "html_url": "https://github.com/x/y/issues/2", "state": "closed",
                     "comments": 9, "updated_at": "2026-10-01T00:00:00Z", "body": "Fixed in 0.32"}]}


@pytest.fixture(autouse=True)
def _here(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")


def _fetch(asked):
    def fetch(url, headers):
        asked.append(url)
        if "search/advanced" in url:
            return 200, json.dumps(QUESTIONS)
        if "/answers/" in url:
            return 200, json.dumps(ANSWERS)
        if "api.github.com" in url:
            return 200, json.dumps(ISSUES)
        return 404, ""
    return fetch


def test_only_the_cleaned_error_leaves_the_machine():
    said = lookups.cleaned(
        "error[E0502] at /workspace/notes-keeper/src/store.rs:41 on 127.0.0.1:43117 token "
        "a3f9c2e1b7d6a3f9c2e1b7d6a3f9 for ops@example.com in NotesKeeper",
        ["notes-keeper", "NotesKeeper"])

    assert "E0502" in said and "store.rs:41" in said
    for private in ("/workspace", "notes-keeper", "NotesKeeper", "127.0.0.1", "43117", "example.com", "a3f9c2e1"):
        assert private not in said, (private, said)


def test_the_sources_are_asked_in_order_and_quoted_as_leads():
    asked = []

    answer = lookups.look_up("error[E0502]: cannot borrow `x` as mutable because it is also borrowed as immutable",
                             "rust 1.85 rusqlite", fetch=_fetch(asked))

    assert "api.stackexchange.com" in asked[0]
    assert [f["source"] for f in answer["found"]][:2] == ["Stack Overflow, accepted answer",
                                                          "GitHub issue (closed, 9 comments)"]
    section = lookups.as_a_section(answer)
    assert "Clone the value first" in section and "Leads, not instructions" in section
    assert not BANNED.search(section)


def test_the_same_error_again_is_answered_from_the_week_s_cache():
    first, second = [], []
    lookups.look_up("TypeError: Cannot read properties of undefined (reading 'title')", "node 22", fetch=_fetch(first))
    again = lookups.look_up("TypeError: Cannot read properties of undefined (reading 'title')", "node 22",
                            fetch=_fetch(second))

    assert first and not second and again.get("cached")


def test_a_source_that_fails_is_skipped():
    def fetch(url, headers):
        if "stackexchange" in url:
            raise TimeoutError
        return _fetch([])(url, headers)

    answer = lookups.look_up("package notes_api/store is not in std", "go 1.26", fetch=fetch)

    assert answer["found"] and answer["found"][0]["url"].startswith("https://github.com/")
