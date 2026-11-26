"""What a model did in runs overrules the research check (tool review 2026-11-26, TR.8, LF.1542).

The model diagnosis's check found the local model calls a lookup and uses its answer (3 of 3), so it was offered
`research` in place of the web pair; in runs it was offered `research` 2,343 times and called it 0 times (the web pair
before it: 1,883 offers, 0 calls). Each finished run's transcript is now counted per model that answered, kept with
the model, and with `WEB_TOOLS_BY_MEASURED_TIER` on, a model offered a lookup often enough with no call is offered no
web tool whatever the check said. The owner's value on the settings page still wins.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import switches

#: Requests and replies copied from a small run's transcript on the local model: two stages offered `research` and
#: did not call it, and a fixer's request offered none.
CAPTURED = Path(__file__).parent / "captured" / "transcript-lookups-offered-and-not-called-qwen3.6.jsonl"
MODEL = "qwen3.6-35b-a3b"


def _captured() -> list[dict]:
    return [json.loads(line) for line in CAPTURED.read_text(encoding="utf-8").splitlines() if line.strip()]


class _Runs:
    def __init__(self):
        self.overrides: dict[str, dict[str, bool]] = {}

    def switch_overrides(self, run_id):
        return dict(self.overrides.get(run_id, {}))


@pytest.fixture
def a_run(monkeypatch, tmp_path):
    """Inside a run whose Internet lookups choice is Always, on the local model, with nothing kept of it yet."""
    from app.internet_lookups import switches_for
    from app.models import model_guidance

    runs = _Runs()
    run = f"run-evidence-{tmp_path.name}"  # one per test: a choice is recorded once per run
    runs.overrides[run] = switches_for("always")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SWITCH_OVERRIDES_FROM_SETTINGS", "on")
    monkeypatch.setenv("SEARXNG_URL", "http://search.invalid")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("WEB_TOOLS_BY_MEASURED_TIER", "on")
    monkeypatch.setattr("app.server.run_store.RunStore.shared", classmethod(lambda cls: runs))
    monkeypatch.setattr(switches, "stored", lambda name: None)
    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: run)
    monkeypatch.setattr("app.models.model_pin.pinned_snapshot", lambda: None)
    monkeypatch.setattr(model_guidance, "served_now", lambda: MODEL)
    switches._RUN_OVERRIDES.clear()  # noqa: SLF001
    from app.models.registry import merge_into_fitness

    # The check passed it, as it passed the local model.
    merge_into_fitness(MODEL, {"capabilities_found": {"researches": {"value": True, "source": "measured"}}})
    yield SimpleNamespace(env=monkeypatch, run=run)
    switches._RUN_OVERRIDES.clear()  # noqa: SLF001


def _finished(run: str, entries: list[dict], times: int) -> None:
    """A finished run whose transcript holds `entries` `times` over, kept as a run's end keeps it."""
    from app.models.research_check import keep_the_run_s_use
    from app.observability.transcript import transcript_path

    path = transcript_path(run)
    path.write_text("".join(json.dumps(entry) + "\n" for _ in range(times) for entry in entries), encoding="utf-8")
    keep_the_run_s_use(run)


def _offered() -> set[str]:
    from app.tools import web_search

    return {tool.name for tool in web_search.web_tools()}


def test_a_run_s_lookups_are_counted_per_model_from_its_transcript():
    from app.models.research_check import lookup_use

    assert lookup_use(_captured()) == {MODEL: (2, 0)}


@pytest.mark.parametrize("switch, offered", [("on", set()), ("off", {"research"})])
def test_a_model_the_check_passed_but_that_never_called_a_lookup_in_its_runs_is_offered_no_web_tool(a_run, switch,
                                                                                                  offered):
    a_run.env.setenv("WEB_TOOLS_BY_MEASURED_TIER", switch)
    _finished("run-first", _captured(), 75)
    _finished("run-second", _captured(), 75)

    assert _offered() == offered


def test_one_call_in_its_runs_keeps_the_research_tool(a_run):
    called = [dict(entry) for entry in _captured()]
    reply = next(entry for entry in called if entry["kind"] == "model_response" and entry["stage"] == "acceptance_author_0")
    reply["tool_calls"] = [{"name": "research", "args": {"question": "vitest 3 what replaced vi.fn().mockReturnValue"}}]
    _finished("run-first", _captured(), 75)
    _finished("run-second", called, 75)

    assert _offered() == {"research"}


def test_a_run_finished_twice_is_counted_once(a_run):
    _finished("run-first", _captured(), 150)
    _finished("run-first", _captured(), 150)

    assert _offered() == {"research"}


def test_the_owner_s_value_on_the_settings_page_wins_over_the_runs(a_run):
    from app.models import capabilities

    _finished("run-first", _captured(), 75)
    _finished("run-second", _captured(), 75)
    capabilities.set_owner_values(MODEL, {"researches": True})

    assert _offered() == {"research"}


def test_the_run_records_that_no_web_tool_was_offered_and_why(a_run):
    from app.observability.switch_firing import fired
    from app.observability.transcript import read_transcript

    _finished("run-first", _captured(), 75)
    _finished("run-second", _captured(), 75)
    _offered()

    records = read_transcript(a_run.run)
    assert "WEB_TOOLS_BY_MEASURED_TIER" in fired(records)
    assert "called none" in next(r["message"] for r in records if r.get("kind") == "tool_list_chosen")


def test_the_effects_report_counts_writer_requests_and_lookups():
    from app.agents.role_tool_lists import effects_lines

    lines = effects_lines(_captured())

    assert "     2  TR.7 writer requests: tool schemas median 20,585 characters; 1 carried" in lines[0]
    assert lines[1] == f"     2  TR.8 replies to a request offering a lookup ({MODEL}); 0 lookup calls"
