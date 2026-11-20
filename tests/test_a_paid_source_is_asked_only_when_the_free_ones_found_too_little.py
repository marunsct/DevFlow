"""A paid web search is asked only with its key and only when the free sources found fewer than two answers (WL.6).

Appendix 10's provider chain: Stack Exchange and GitHub's issue search first (free, official), then the private
search, and a paid search (Brave, then Tavily) only for the general web those leave unanswered - each costs money.
Context7's library documentation is asked on the same terms, with or without its key. The order can be changed.
"""
from __future__ import annotations

import json

import pytest

from app.tools import lookups, page_reader

ERROR = "ImportError: cannot import name 'soft_unicode' from 'markupsafe'"


@pytest.fixture(autouse=True)
def _here(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    for variable in ("BRAVE_API_KEY", "TAVILY_API_KEY", "CONTEXT7_API_KEY", "LOOKUP_ORDER", "LOOKUP_DAILY_CAPS"):
        monkeypatch.delenv(variable, raising=False)


def _question(n):
    return {"title": f"question {n}", "link": f"https://stackoverflow.com/q/{n}", "accepted_answer_id": 100 + n,
            "last_activity_date": 1_700_000_000}


def _web(free_answers, sent):
    """The outside world: Stack Exchange with `free_answers` answered questions, nothing on GitHub or Context7, and
    each paid search with one result of its own."""
    def fetch(url, headers, body=None):
        sent.append((url, headers, body))
        if "search/advanced" in url:
            return 200, json.dumps({"items": [_question(n) for n in range(free_answers)]})
        if "/answers/" in url:
            return 200, json.dumps({"items": [{"answer_id": 100 + n, "body": "<p>Pin markupsafe below 2.1 or upgrade "
                                               "the library that imports it.</p>" * 4} for n in range(free_answers)]})
        if "api.search.brave.com" in url:
            return 200, json.dumps({"web": {"results": [{"title": "<strong>soft_unicode</strong> removed",
                                                         "url": "https://blog.example.org/soft-unicode",
                                                         "description": "markupsafe 2.1 removed soft_unicode " * 10,
                                                         "page_age": "2025-03-01T00:00:00"}]}})
        if "api.tavily.com" in url:
            return 200, json.dumps({"results": [{"title": "Fixing soft_unicode", "url": "https://docs.example.net/fix",
                                                 "content": "Upgrade Jinja2 to 3.x, which no longer imports it. " * 6}]})
        return 200, json.dumps({"items": [], "results": []})
    return fetch


def _to(host, sent):
    return [entry for entry in sent if host in entry[0]]


@pytest.mark.parametrize("free_answers, paid_asked", [(1, True), (3, False)])
def test_brave_is_asked_with_its_key_only_when_the_free_sources_found_fewer_than_two(monkeypatch, free_answers,
                                                                                       paid_asked):
    monkeypatch.setenv("BRAVE_API_KEY", "brave-key-canary-0001")
    sent = []

    answer = lookups.look_up(ERROR, "python 3.12", fetch=_web(free_answers, sent))

    assert bool(_to("api.search.brave.com", sent)) is paid_asked
    assert ("brave" in answer["asked"]) is paid_asked


def test_brave_is_sent_its_key_and_its_answer_joins_the_free_ones(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "brave-key-canary-0001")
    sent = []

    answer = lookups.look_up(ERROR, "python 3.12", fetch=_web(1, sent))

    assert [headers["X-Subscription-Token"] for _, headers, _ in _to("api.search.brave.com", sent)] == [
        "brave-key-canary-0001"]
    assert [f["url"] for f in answer["found"]] == ["https://stackoverflow.com/q/0",
                                                   "https://blog.example.org/soft-unicode"]
    assert answer["found"][1]["title"] == "soft_unicode removed"


def test_without_a_key_no_paid_search_is_asked_even_when_nothing_was_found():
    sent = []

    answer = lookups.look_up(ERROR, "python 3.12", fetch=_web(0, sent))

    assert not _to("api.search.brave.com", sent) and not _to("api.tavily.com", sent)
    assert answer["found"] == []


def test_the_order_can_put_tavily_first_and_brave_is_then_not_needed(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "brave-key-canary-0002")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-key-canary-0002")
    monkeypatch.setenv("LOOKUP_ORDER", "stack exchange, github issues, tavily, brave")
    sent = []

    answer = lookups.look_up(ERROR, "python 3.12", fetch=_web(1, sent))

    tavily = _to("api.tavily.com", sent)
    assert len(tavily) == 1 and tavily[0][1]["Authorization"] == "Bearer tvly-key-canary-0002"
    assert json.loads(tavily[0][2])["query"] == answer["query"]
    assert not _to("api.search.brave.com", sent), "two answers were found before Brave's turn"
    assert [f["url"] for f in answer["found"]][-1] == "https://docs.example.net/fix"


def test_context7_is_asked_for_the_stack_s_library_without_a_key():
    sent = []

    def fetch(url, headers, body=None):
        sent.append((url, headers, body))
        if "context7.com/api/v2/libs/search" in url:
            return 200, json.dumps({"results": [{"id": "/pallets/jinja", "title": "Jinja"}]})
        if "context7.com/api/v2/context" in url:
            return 200, json.dumps({"infoSnippets": [{"content": "Jinja 3 no longer uses soft_unicode."}],
                                    "codeSnippets": []})
        return 200, json.dumps({"items": []})

    answer = lookups.look_up(ERROR, "python jinja2 3.1", fetch=fetch)

    search = _to("libs/search", sent)
    assert search and "libraryName=jinja2" in search[0][0] and "Authorization" not in search[0][1]
    assert answer["found"][0]["url"] == "https://context7.com/pallets/jinja"
    assert "no longer uses soft_unicode" in answer["found"][0]["excerpt"]


def test_a_thin_paid_snippet_is_filled_from_its_page(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "brave-key-canary-0003")
    page = ("<html><body><nav>Blog home</nav><article><h2>The cause</h2><p>markupsafe 2.1 removed soft_unicode; "
            "Jinja2 below 3.0 still imports it. Upgrade Jinja2 to 3.1.</p></article></body></html>")

    def site(url):
        if url.endswith("/robots.txt"):
            return 404, {}, b""
        return 200, {"content-type": "text/html"}, page.encode()

    monkeypatch.setattr(page_reader, "_fetch", site)
    monkeypatch.setattr(page_reader, "_resolve", lambda host: ["93.184.215.14"])

    def fetch(url, headers, body=None):
        if "api.search.brave.com" in url:
            return 200, json.dumps({"web": {"results": [{"title": "soft_unicode", "description": "markupsafe news",
                                                         "url": "https://blog.example.org/soft-unicode"}]}})
        return 200, json.dumps({"items": []})

    answer = lookups.look_up(ERROR, "python", fetch=fetch)

    assert "Jinja2 below 3.0 still imports it" in answer["found"][0]["excerpt"]
    assert "Blog home" not in answer["found"][0]["excerpt"]
