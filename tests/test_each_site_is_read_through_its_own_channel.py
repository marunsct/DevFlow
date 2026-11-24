"""Each site is read through its official channel, code keeps its shape, a refusal is told from "nothing found", and
one counted search path spends the Stack Exchange and GitHub quotas (plans KS.1-KS.4, LF.1294).

Measured on this machine (2026-11-24): the page reader got HTTP 403 for every Stack Overflow question, which search
results rank first; a GitHub issue read as HTML began with the page's controls and never reached the closing comment;
a multi-line code answer reached the fixer as one line; any status but 200 read as "0 found", so a source that refused
was asked again inside the window it had named; and one query to the private search fired three Stack Exchange
engines and a GitHub engine on the same per-address quota, uncounted.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.tools import lookups, page_reader, web_search

ROOT = Path(__file__).resolve().parents[1]

QUESTION = {"items": [{"question_id": 61, "title": "Depends with a yield", "link": "https://stackoverflow.com/q/61",
                       "creation_date": 1_700_000_000, "score": 4, "owner": {"display_name": "asker"},
                       "body": "<p>My dependency never closes.</p>"}]}
ANSWERS = {"items": [
    {"answer_id": 2, "is_accepted": False, "score": 40, "creation_date": 1_710_000_000,
     "owner": {"display_name": "voter"}, "body": "<p>Upgrade first.</p>"},
    {"answer_id": 1, "is_accepted": True, "score": 12, "creation_date": 1_705_000_000,
     "owner": {"display_name": "answerer"},
     "body": "<p>Yield inside a try:</p><pre><code class=\"language-python\">def get_db():\n    db = Session()\n"
             "    try:\n        yield db\n    finally:\n        db.close()\n</code></pre>"},
]}
ISSUE = {"title": "E0599 on fetch_optional", "state": "closed", "state_reason": "completed",
         "closed_at": "2026-03-02T10:00:00Z", "created_at": "2026-03-01T09:00:00Z",
         "html_url": "https://github.com/launchbadge/sqlx/issues/3", "user": {"login": "reporter"},
         "body": "I get E0599 when I call fetch_optional on QueryAs."}
COMMENTS = [
    {"body": "Same here, +1", "author_association": "NONE", "created_at": "2026-03-01T12:00:00Z",
     "user": {"login": "bystander"}, "reactions": {"total_count": 9}},
    {"body": "Import the `Executor` trait; fixed in 0.8.3 by #3790.", "author_association": "MEMBER",
     "created_at": "2026-03-02T09:59:00Z", "user": {"login": "maintainer"}},
]


@pytest.fixture(autouse=True)
def _here(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for variable in ("STACKEXCHANGE_KEY", "GITHUB_TOKEN", "LOOKUP_ORDER", "LOOKUP_DAILY_CAPS", "BRAVE_API_KEY",
                     "TAVILY_API_KEY"):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture
def apis(monkeypatch):
    """The sites' APIs, answering as recorded; every request kept."""
    sent: list[str] = []

    def fetch(url, headers, body=None):
        sent.append(url)
        path = urlsplit(url).path
        if path == "/2.3/questions/61":
            return 200, json.dumps(QUESTION), {}
        if path == "/2.3/questions/61/answers":
            return 200, json.dumps(ANSWERS), {}
        if path == "/repos/launchbadge/sqlx/issues/3":
            return 200, json.dumps(ISSUE), {}
        if path == "/repos/launchbadge/sqlx/issues/3/comments":
            return 200, json.dumps(COMMENTS), {}
        if urlsplit(url).hostname == "raw.githubusercontent.com":
            return 200, "## 0.8.3\n- `fetch_optional` works on `QueryAs` again\n", {}
        return 404, "", {}

    monkeypatch.setattr(lookups, "_get", fetch)
    return sent


@pytest.fixture
def pages(monkeypatch):
    """The sites' HTML pages, as they answer this harness: Stack Overflow refuses, GitHub serves its page chrome."""
    fetched: list[str] = []

    def fetch(url, address):
        fetched.append(url)
        if "stackoverflow.com" in url:
            return 403, {}, b""
        return 200, {"content-type": "text/html"}, b"<html><body><p>New issue Copy link Files Blame</p></body></html>"

    monkeypatch.setattr(page_reader, "_fetch", fetch)
    monkeypatch.setattr(page_reader, "_resolve", lambda host: ["140.82.112.3"])
    return fetched


# --- KS.1: the official channel ---------------------------------------------------------------------------------------

def test_a_stack_overflow_question_is_read_through_the_api_with_its_accepted_answer_first(apis, pages):
    shown = page_reader.read("https://stackoverflow.com/questions/61/depends-with-a-yield")

    text = shown.get("text", "")
    assert "error" not in shown and not pages, shown
    assert text.index("Accepted answer") < text.index("score 40"), "the accepted answer comes before the top-voted"
    assert "by answerer" in text and "https://stackoverflow.com/q/61" in text, "the author and the link are kept"


def test_a_github_issue_is_read_with_the_maintainer_s_closing_reply_as_its_resolution(apis, pages):
    shown = page_reader.read("https://github.com/launchbadge/sqlx/issues/3")

    text = shown.get("text", "")
    assert "Import the `Executor` trait; fixed in 0.8.3" in text and not pages, shown
    assert text.index("The resolution: maintainer") < text.index("Same here, +1")
    assert "fixed in 0.8.3" in text.split("Linked changes:")[-1]


def test_a_github_file_is_fetched_from_the_raw_host_not_its_page(apis, pages):
    shown = page_reader.read("https://github.com/launchbadge/sqlx/blob/main/CHANGELOG.md")

    assert [urlsplit(u).hostname for u in apis] == ["raw.githubusercontent.com"] and not pages
    assert apis[0].endswith("/launchbadge/sqlx/main/CHANGELOG.md")
    assert "works on `QueryAs` again" in shown["text"] and "Blame" not in shown["text"]


def test_an_address_with_no_channel_is_read_as_a_page(apis, pages):
    shown = page_reader.read("https://docs.example.org/guide")

    assert not apis and pages and "New issue" in shown["text"]


# --- KS.2: code keeps its shape -------------------------------------------------------------------------------------

def test_a_code_block_in_an_answer_keeps_its_lines_and_a_fence(apis, pages):
    text = page_reader.read("https://stackoverflow.com/q/61")["text"]

    assert "```python\ndef get_db():\n    db = Session()\n    try:\n        yield db\n" in text, text


def test_a_lookup_s_excerpt_keeps_the_answer_s_code_and_is_never_cut_inside_it():
    long_code = "\n".join(f"    step_{n} = run({n})" for n in range(60))

    def fetch(url, headers, body=None):
        if "search/advanced" in url:
            return 200, json.dumps({"items": [{"title": "q", "link": "https://stackoverflow.com/q/1",
                                               "accepted_answer_id": 7, "last_activity_date": 1_700_000_000}]})
        if "/answers/" in url:
            return 200, json.dumps({"items": [{"answer_id": 7, "body": (
                "<p>Close it:</p><pre><code>with open(p) as f:\n    data = f.read()\nreturn data\n</code></pre>"
                f"<p>Or the long way:</p><pre><code>{long_code}</code></pre>")}]})
        return 200, json.dumps({"items": []})

    excerpt = lookups.look_up("ResourceWarning: unclosed file", "python", fetch=fetch)["found"][0]["excerpt"]

    assert "```\nwith open(p) as f:\n    data = f.read()\nreturn data\n```" in excerpt, excerpt
    assert len(re.findall(r"(?m)^```", excerpt)) % 2 == 0, "a fence is never left open"


# --- KS.3: refused is not "nothing found" ----------------------------------------------------------------------------

def _refusing(sent, status=429, headers=None, body=""):
    def fetch(url, headers_sent, body_sent=None):
        sent.append(url)
        if "api.stackexchange.com" in url:
            return status, body, headers or {}
        return 200, json.dumps({"items": []}), {}
    return fetch


def test_a_429_with_retry_after_holds_the_source_and_is_not_remembered_as_nothing_found(tmp_path):
    first, second = [], []

    refused = lookups.look_up("TypeError: x is not a function", "node",
                              fetch=_refusing(first, 429, {"Retry-After": "120"}))
    again = lookups.look_up("TypeError: x is not a function", "node", fetch=_refusing(second))

    assert refused["refused"] == ["stack exchange"] and not refused.get("nothing_found")
    assert any(s.startswith("stack exchange: refused until") for s in refused["skipped"])
    assert [u for u in first if "stackexchange" in u] and not [u for u in second if "stackexchange" in u]
    assert not again.get("cached"), "a refusal is never kept as an answer"


def test_github_s_spent_rate_limit_holds_issue_search_until_its_reset(tmp_path):
    import time

    sent = []

    def fetch(url, headers, body=None):
        sent.append(url)
        if "api.github.com" in url:
            return 403, '{"message": "API rate limit exceeded"}', {
                "x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(time.time()) + 600)}
        return 200, json.dumps({"items": []}), {}

    answer = lookups.look_up("panic: runtime error: index out of range", "go", fetch=fetch)
    later = lookups.state(next(s for s in lookups.SOURCES if s.name == "github issues"))

    assert answer["refused"] == ["github issues"] and later.startswith("held until")


def test_stack_exchange_s_backoff_holds_it_even_after_an_answer(tmp_path):
    first, second = [], []
    body = json.dumps({"items": [], "backoff": 30})

    lookups.look_up("KeyError: 'id'", "python", fetch=_refusing(first, 200, {}, body))
    lookups.look_up("ValueError: bad value", "python", fetch=_refusing(second))

    assert [u for u in first if "stackexchange" in u] and not [u for u in second if "stackexchange" in u]


def test_a_true_nothing_found_is_remembered_for_a_day():
    first, second = [], []

    lookups.look_up("WeirdError: nobody wrote about this", "zig", fetch=_refusing(first, 200, {}, '{"items": []}'))
    again = lookups.look_up("WeirdError: nobody wrote about this", "zig", fetch=_refusing(second))

    assert first and not second and again.get("cached") and again.get("nothing_found")


# --- KS.4: one counted search path ----------------------------------------------------------------------------------

#: Engines that refuse a self-hosted instance, and engines that duplicate the APIs the harness asks itself.
BLOCKED = {"google", "bing", "brave", "startpage", "mojeek"}
DUPLICATES = {"stackoverflow", "askubuntu", "superuser", "github"}


def test_the_private_search_keeps_no_blocked_or_duplicate_engine_and_states_its_suspensions():
    settings = (ROOT / "docker" / "searxng" / "settings.yml").read_text()
    kept = re.findall(r"^\s+-\s+(?:name:\s+)?([\w. ]+?)\s*$", settings, re.M)

    assert kept and not (BLOCKED | DUPLICATES) & {k.strip() for k in kept}, kept
    assert re.search(r"^  suspended_times:\n(    \w+: \d+\n)+", settings, re.M)


def test_one_model_search_spends_stack_exchange_requests_on_the_counter_and_the_private_search_the_rest(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    asked = []

    def apis(url, headers, body=None):
        if "search/advanced" in url:
            return 200, json.dumps({"items": [{"title": "q", "link": "https://stackoverflow.com/q/5",
                                               "accepted_answer_id": 9, "last_activity_date": 1_700_000_000}]}), {}
        if "/answers/" in url:
            return 200, json.dumps({"items": [{"answer_id": 9, "body": "<p>Pin the toolchain.</p>"}]}), {}
        return 200, json.dumps({"items": []}), {}

    def searx(url, params=None):
        asked.append(params)
        return 200, json.dumps({"results": [{"title": "mdn", "url": "https://developer.mozilla.org/x",
                                             "content": "c"}]}), "application/json"

    monkeypatch.setattr(lookups, "_get", apis)
    answer = web_search.search("error: package requires rustc 1.88", fetch=searx)

    assert lookups.requests_today()["stack exchange"] == 2
    assert asked and [r["url"] for r in answer["results"]][0] == "https://stackoverflow.com/q/5"


def test_engines_that_did_not_answer_are_said_so_not_nothing_found(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")

    def searx(url, params=None):
        return 200, json.dumps({"results": [], "unresponsive_engines": [["duckduckgo", "CAPTCHA"]]}), "application/json"

    answer = web_search.search("an error", fetch=searx, with_the_apis=False)

    assert answer["unresponsive"] == ["duckduckgo"] and "did not answer" in answer["error"]
    assert "Nothing was found" not in answer["error"]
