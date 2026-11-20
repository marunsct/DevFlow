"""A lookup source's key reaches its own source and is never logged or printed, even in a failure's message (WL.6).

A paid search's key is money: a key in a log line or in the readiness output before a run is a key in every
transcript and audit that copies them. A client library's error can quote the request it failed on, headers included.
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import pytest

from app.tools import lookups, package_registry, page_reader

ROOT = Path(__file__).resolve().parents[1]
CANARIES = {"BRAVE_API_KEY": "brave-canary-key-5150", "TAVILY_API_KEY": "tvly-canary-key-6160",
            "CONTEXT7_API_KEY": "ctx7-canary-key-7170"}


@pytest.fixture(autouse=True)
def _keys(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    monkeypatch.delenv("LOOKUP_DAILY_CAPS", raising=False)
    for variable, value in CANARIES.items():
        monkeypatch.setenv(variable, value)


def _failing(sent):
    """Every source fails with an error that quotes the request's headers, as an HTTP client's can."""
    def fetch(url, headers, body=None):
        sent.append(headers)
        raise ConnectionError(f"{sorted(headers.values(), reverse=True)} refused for {url}")
    return fetch


def test_a_failing_paid_source_s_log_line_carries_no_key(caplog):
    sent = []
    caplog.set_level(logging.INFO, logger="app.tools.lookups")

    lookups.look_up("panic: runtime error: index out of range [3] with length 3", "go 1.26", fetch=_failing(sent))

    assert {"X-Subscription-Token": "brave-canary-key-5150", "Accept": "application/json"} in sent
    assert "brave" in caplog.text
    assert not any(value in caplog.text for value in CANARIES.values())


def test_the_readiness_lines_carry_no_key(monkeypatch, capsys):
    monkeypatch.setattr(lookups, "_get", _failing([]))
    monkeypatch.setattr(package_registry, "look_up", lambda ecosystem, name: {"version": "5.0.0"})
    monkeypatch.setattr(page_reader, "_fetch", lambda url, address: (404, {}, b"") if url.endswith("robots.txt") else (
        200, {"content-type": "text/plain"}, b"Example Domain"))
    monkeypatch.setattr(page_reader, "_resolve", lambda host: ["93.184.215.14"])
    spec = importlib.util.spec_from_file_location("lookup_ready", ROOT / "scripts" / "loop" / "lookup_ready.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    probe.main()

    printed = capsys.readouterr().out
    assert "LOOKUPS brave: NO ANSWER (ConnectionError" in printed and "LOOKUPS tavily: NO ANSWER" in printed
    assert not any(value in printed for value in CANARIES.values())
