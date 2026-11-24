"""Before a run, the lookup probe names each search engine that did not answer, the Stack Exchange and GitHub
allowances left, and whether the page reader reads the kinds of page answers live on (plan KS.6, LF.1297).

Measured 2026-11-24: the probe read example.com, which never fails the way an answer page does (Stack Overflow answers
the reader 403 and its robots.txt refuses everything); nothing read the private search's `unresponsive_engines`, and
no allowance was ever printed. Each line stays a warning, never a block.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from app.tools import page_reader, source_health

ROOT = Path(__file__).resolve().parents[1]

ENGINES = {"results": [{"url": "https://example.org/a"}],
           "unresponsive_engines": [["google", "Suspended: access denied"], ["brave", "timeout"]]}
STACK_EXCHANGE = {"items": [{"site": {}}], "quota_max": 300, "quota_remaining": 12, "backoff": 10}
GITHUB = {"resources": {"core": {"limit": 60, "remaining": 58, "reset": 1_700_003_600},
                        "search": {"limit": 10, "remaining": 0, "reset": 1_700_000_045}}}


def _recorded(sent: list[str]):
    def get(url, headers):  # the sources' recorded answers
        sent.append(url)
        if url.startswith("http://search.internal:8080/search?"):
            return 200, {}, json.dumps(ENGINES)
        if url.startswith("https://api.stackexchange.com/2.3/info?"):
            return 200, {}, json.dumps(STACK_EXCHANGE)
        if url == "https://api.github.com/rate_limit":
            return 200, {}, json.dumps(GITHUB)
        return 404, {}, ""
    return get


@pytest.fixture
def sources(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://search.internal:8080")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    for variable in ("STACKEXCHANGE_KEY", "GITHUB_TOKEN"):
        monkeypatch.delenv(variable, raising=False)
    sent: list[str] = []
    return _recorded(sent), sent


def test_each_engine_the_private_search_names_as_silent_gets_its_own_line(sources):
    get, sent = sources

    lines = source_health.search_engine_lines(get)

    assert lines == [
        "LOOKUPS private search engine google: NO ANSWER (Suspended: access denied) - lookups find less; not a block",
        "LOOKUPS private search engine brave: NO ANSWER (timeout) - lookups find less; not a block",
    ]
    assert len(sent) == 1


def test_every_engine_answering_is_said_once(sources, monkeypatch):
    monkeypatch.setitem(ENGINES, "unresponsive_engines", [])

    assert source_health.search_engine_lines(sources[0]) == [
        "LOOKUPS private search engines: every engine asked answered"]


def test_the_stack_exchange_and_github_allowances_left_are_printed_and_a_low_one_says_so(sources):
    get, _ = sources

    stack_exchange = source_health.stack_exchange_line(get)
    github = source_health.github_line(get, now=lambda: 1_700_000_000)

    assert stack_exchange.startswith("LOOKUPS stack exchange allowance: 12 of 300 requests left today")
    assert "wait 10s" in stack_exchange and "low" in stack_exchange and "not a block" in stack_exchange
    assert github.startswith("LOOKUPS github allowance: search 0 of 10 a minute, core 58 of 60 an hour left")
    assert "search again in 45s" in github and "not a block" in github


def test_a_refused_allowance_question_is_no_answer_not_a_number(monkeypatch):
    refused = lambda url, headers: (429, {}, '{"error_message": "too many requests from this IP"}')  # noqa: E731

    said = source_health.stack_exchange_line(refused)

    assert said.startswith("LOOKUPS stack exchange allowance: NO ANSWER (it answered 429")
    assert "too many requests" in said


def test_the_page_reader_is_probed_on_each_kind_of_page_a_lookup_reads_and_says_which_it_cannot_read(monkeypatch):
    def fetch(url, address):  # the sites' recorded answers
        if url == "https://stackoverflow.com/robots.txt":
            return 200, {"content-type": "text/plain"}, b"User-agent: *\nDisallow: /\n"
        if url.endswith("/robots.txt"):
            return 404, {}, b""
        return 200, {"content-type": "text/html"}, b"<html><main><p>" + b"The page's own words. " * 20 + b"</p></main>"

    monkeypatch.setattr(page_reader, "_fetch", fetch)
    monkeypatch.setattr(page_reader, "_resolve", lambda host: ["140.82.112.3"])

    lines = source_health.reader_lines()

    assert [line.split(":")[0] for line in lines] == [
        "LOOKUPS page reader, a file on a code host", "LOOKUPS page reader, a documentation page",
        "LOOKUPS page reader, a question and its answers"]
    assert "answers (1 page(s)" in lines[0] and "answers (1 page(s)" in lines[1]
    assert "NO ANSWER" in lines[2] and "robots.txt" in lines[2] and "not a block" in lines[2]


def test_the_ready_probe_prints_the_new_lines_and_example_com_is_no_longer_its_page(monkeypatch, capsys, tmp_path):
    from app.tools import lookups, package_registry

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    monkeypatch.setattr(lookups, "_get", lambda url, headers, body=None: (200, '{"items": []}'))
    monkeypatch.setattr(package_registry, "look_up", lambda ecosystem, name: {"version": "5.0.0"})
    monkeypatch.setattr(source_health, "_get", _recorded([]))
    read: list[str] = []
    monkeypatch.setattr(page_reader, "read", lambda url, *a, **k: read.append(url) or {"text": "words", "pages": 1})
    spec = importlib.util.spec_from_file_location("lookup_ready", ROOT / "scripts" / "loop" / "lookup_ready.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    assert probe.main() == 0

    printed = capsys.readouterr().out
    assert "LOOKUPS stack exchange allowance: 12 of 300" in printed and "LOOKUPS github allowance:" in printed
    assert len(read) == 3 and not [url for url in read if "example.com" in url]
