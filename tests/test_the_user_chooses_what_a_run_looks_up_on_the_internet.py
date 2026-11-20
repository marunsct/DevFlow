"""The user chooses, per run, whether the agents may look things up on the internet (plan WL.3).

Owner, 2026-11-20: agents look things up when they are stuck, the user deciding whether they may. Three values - off,
when stuck (the form's default), always - kept as the run's own switch settings, so the run keeps the value it
started with; the run's page shows it. "Off" must reach nothing outside: no stuck-error lookup asks any source.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app import switches
from app.graph import stuck_lookup
from app.tools import lookups


class _Runs:
    """The run store's record of each run's own switch settings."""

    def __init__(self):
        self.overrides: dict[str, dict[str, bool]] = {}

    def switch_overrides(self, run_id):
        return dict(self.overrides.get(run_id, {}))


@pytest.fixture
def a_run(monkeypatch, tmp_path):
    """Inside a run whose record holds its own switches; the deployment has the stuck lookup on."""
    runs = _Runs()
    monkeypatch.setenv("SWITCH_OVERRIDES_FROM_SETTINGS", "on")
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("STACKEXCHANGE_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("app.server.run_store.RunStore.shared", classmethod(lambda cls: runs))
    monkeypatch.setattr(switches, "stored", lambda name: None)
    monkeypatch.setattr("app.server.runtime_settings.secrets", lambda **_: {})
    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-chosen")
    switches._RUN_OVERRIDES.clear()  # noqa: SLF001
    stuck_lookup._DONE.clear()  # noqa: SLF001
    yield runs
    switches._RUN_OVERRIDES.clear()  # noqa: SLF001
    stuck_lookup._DONE.clear()  # noqa: SLF001


@pytest.fixture
def outside(monkeypatch):
    """Every request a lookup sends out, answered with nothing found."""
    sent: list[str] = []

    def fetch(url, headers):
        sent.append(url)
        return 200, '{"items": []}'

    monkeypatch.setattr(lookups, "_get", fetch)
    return sent


def _a_stuck_defect():
    return SimpleNamespace(description="The product does not start.", attempts=[{"outcome": "left open"}],
                           actual_behavior="TypeError: Argument #2 ($handler) must be of type callable, "
                                           "RequestHandlerInterface given")


STACK = SimpleNamespace(language="PHP", framework="Slim 4")


def _started_with(runs: _Runs, choice: str) -> None:
    from app.internet_lookups import switches_for

    runs.overrides["run-chosen"] = switches_for(choice)


def test_a_run_started_with_lookups_off_sends_no_request_for_a_stuck_error(a_run, outside, tmp_path):
    _started_with(a_run, "off")

    shown = stuck_lookup.section(tmp_path / "workspace", _a_stuck_defect(), STACK)

    assert shown == "" and outside == []


@pytest.mark.parametrize("choice", ["when_stuck", "always"])
def test_a_run_started_with_lookups_on_asks_the_sources_for_a_stuck_error(a_run, outside, tmp_path, monkeypatch,
                                                                         choice):
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "off")
    _started_with(a_run, choice)

    stuck_lookup.section(tmp_path / "workspace", _a_stuck_defect(), STACK)

    assert any(url.startswith("https://api.stackexchange.com/") for url in outside)


@pytest.mark.parametrize("choice, offered", [("off", False), ("when_stuck", False), ("always", True)])
def test_the_web_tools_are_offered_only_to_a_run_that_chose_always(a_run, monkeypatch, choice, offered):
    from app.tools import web_search

    monkeypatch.setenv("SEARXNG_URL", "http://search.invalid")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    _started_with(a_run, choice)

    assert {tool.name for tool in web_search.web_tools()} == ({"search_the_web", "read_web_page"} if offered else set())


@pytest.mark.parametrize("overrides, choice", [
    ({"WEB_LOOKUP_WHEN_STUCK": False, "WEB_TOOLS_OFFERED": False}, "off"),
    ({"WEB_LOOKUP_WHEN_STUCK": True, "WEB_TOOLS_OFFERED": False}, "when_stuck"),
    ({"WEB_LOOKUP_WHEN_STUCK": True, "WEB_TOOLS_OFFERED": True, "LEAN_TOOL_LISTS": False}, "always"),
    ({"WEB_LOOKUP_WHEN_STUCK": False}, None),
    ({}, None),
])
def test_the_run_s_record_says_which_choice_it_was_started_with(overrides, choice):
    from app.internet_lookups import choice_of

    assert choice_of(overrides) == choice


def _new_run(client, tmp_path: Path) -> str:
    brief = tmp_path / "brief.md"
    brief.write_text("A product")
    with open(brief, "rb") as handle:
        return client.post("/api/runs", files=[("files", ("brief.md", handle, "text/plain"))]).json()["run_id"]


def test_a_run_started_with_a_choice_keeps_it_as_its_own_switches_and_shows_it(client, tmp_path):
    from app.server.run_store import RunStore

    run_id = _new_run(client, tmp_path)

    started = client.post(f"/api/runs/{run_id}/start", json={"internet_lookups": "off", "workspace_label": "lookups"})

    assert started.status_code == 202
    assert RunStore.shared().switch_overrides(run_id) == {"WEB_LOOKUP_WHEN_STUCK": False, "WEB_TOOLS_OFFERED": False}
    assert client.get(f"/api/runs/{run_id}").json()["internet_lookups"] == "off"


def test_a_switch_the_start_names_beats_the_choice_and_a_run_without_one_shows_none(client, tmp_path):
    from app.server.run_store import RunStore

    chosen, plain = _new_run(client, tmp_path), _new_run(client, tmp_path)

    client.post(f"/api/runs/{chosen}/start", json={"internet_lookups": "always", "workspace_label": "lookups-a",
                                                   "switches": {"WEB_TOOLS_OFFERED": False}})
    client.post(f"/api/runs/{plain}/start", json={"workspace_label": "lookups-b"})

    assert RunStore.shared().switch_overrides(chosen) == {"WEB_LOOKUP_WHEN_STUCK": True, "WEB_TOOLS_OFFERED": False}
    assert client.get(f"/api/runs/{plain}").json()["internet_lookups"] is None


def test_an_unknown_choice_is_refused_before_the_run_starts(client, tmp_path):
    run_id = _new_run(client, tmp_path)

    refused = client.post(f"/api/runs/{run_id}/start", json={"internet_lookups": "sometimes"})

    assert refused.status_code == 422
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "created"
