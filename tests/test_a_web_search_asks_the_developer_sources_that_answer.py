"""A web search asks the developer sources first and puts the pages that answer an error first.

Measured 2026-11-20: the general engines behind the private search all refused it (access denied, timeouts, rate
limits, CAPTCHAs), so three error lines from the day's runs - a borrow error, a framework 404, a package-version
error - each came back "Nothing was found", while the developer category gave 40-110 results; there, an image
listing and a glossary page came above the Q&A answer.
"""
from __future__ import annotations

import json

import pytest

from app.tools import web_search


@pytest.fixture(autouse=True)
def _searx(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")


def _answer(*urls):
    return 200, json.dumps({"results": [{"title": u, "url": u, "content": "x"} for u in urls]}), "application/json"


def test_the_developer_category_is_asked_and_the_answer_comes_first():
    asked = []

    def fetch(url, params):
        asked.append(params.get("categories"))
        return _answer("https://hub.docker.com/r/someone/error-pages", "https://example.org/glossary/mutable",
                       "https://stackoverflow.com/q/38023871", "https://github.com/rust-lang/rust/issues/1")

    answer = web_search.search("cannot borrow as mutable because it is also borrowed as immutable", fetch=fetch)

    assert asked == ["it"]
    urls = [r["url"] for r in answer["results"]]
    assert urls[0].startswith("https://stackoverflow.com/") and urls[1].startswith("https://github.com/")
    assert urls[-1].startswith("https://hub.docker.com/")


def test_the_general_web_is_asked_when_the_developer_sources_find_too_little():
    asked = []

    def fetch(url, params):
        asked.append(params.get("categories"))
        return _answer() if params.get("categories") == "it" else _answer("https://docs.example.com/guide")

    answer = web_search.search("an error nobody asked a question about", fetch=fetch)

    assert asked == ["it", "general"]
    assert answer["results"][0]["url"] == "https://docs.example.com/guide"
