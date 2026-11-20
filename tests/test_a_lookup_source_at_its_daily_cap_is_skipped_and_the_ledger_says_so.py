"""Each lookup source has a daily request cap; one that reached it is skipped and the ledger says so (plan WL.6).

Stack Exchange allows 300 requests a day per address without a key, and a paid search spends money per request; a
run that met many errors could spend either before the day ends. The requests are counted per source per day.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.graph import stuck_lookup
from app.tools import lookups


@pytest.fixture(autouse=True)
def _here(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    monkeypatch.setenv("LOOKUP_DAILY_CAPS", "stack exchange=2")
    for variable in ("BRAVE_API_KEY", "TAVILY_API_KEY", "LOOKUP_ORDER", "STACKEXCHANGE_KEY"):
        monkeypatch.delenv(variable, raising=False)


def _fetch(sent):
    def fetch(url, headers, body=None):
        sent.append(url)
        if "search/advanced" in url:
            return 200, json.dumps({"items": [{"title": "q", "link": f"https://stackoverflow.com/q/{len(sent)}",
                                               "accepted_answer_id": 7, "last_activity_date": 1_700_000_000}]})
        if "/answers/" in url:
            return 200, json.dumps({"items": [{"answer_id": 7, "body": "<p>Rebuild the lock file.</p>"}]})
        return 200, json.dumps({"items": [], "results": []})
    return fetch


def test_a_source_at_its_cap_is_not_asked_again_that_day():
    first, second = [], []
    lookups.look_up("error: lock file version 4 requires a newer toolchain", "rust", fetch=_fetch(first))

    answer = lookups.look_up("error: failed to parse manifest at line 12", "rust", fetch=_fetch(second))

    assert [u for u in first if "stackexchange" in u] and not [u for u in second if "stackexchange" in u]
    assert answer["skipped"] == ["stack exchange: capped (daily cap of 2 requests reached)"]
    assert "stack exchange" not in answer["asked"]


def test_the_ledger_record_of_a_lookup_names_the_source_skipped(tmp_path, monkeypatch):
    recorded = []
    monkeypatch.setattr("app.observability.transcript.record", lambda *a, **k: recorded.append(k))
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "run-x")
    monkeypatch.setattr(lookups, "_get", _fetch([]))
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")
    stuck_lookup._DONE.clear()  # noqa: SLF001
    lookups.look_up("error: lock file version 4 requires a newer toolchain", "rust")
    stuck = SimpleNamespace(description="The product does not build.", attempts=[{"outcome": "left open"}] * 2,
                            actual_behavior="error: failed to parse manifest at line 12 column 3")

    stuck_lookup.section(tmp_path / "workspace", stuck, SimpleNamespace(language="Rust", framework=""))

    details = [k["detail"] for k in recorded if k.get("event") == stuck_lookup.LOOKUP_EVENT]
    assert details and "skipped stack exchange: capped (daily cap of 2 requests reached)" in details[0]
