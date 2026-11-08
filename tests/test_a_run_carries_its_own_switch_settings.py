"""A run carries its own switch settings, so two runs on one harness version are a measurement's two arms (HR2.E.1).

Since 11-05 no family had two clean runs on one harness version: each off arm needed a deploy, which itself marked
the live run mixed, so no switch could be judged.
"""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import pytest

from app import switches


class _Store:
    def __init__(self, overrides):
        self.overrides, self.reads = overrides, 0

    def switch_overrides(self, run_id):
        self.reads += 1
        return dict(self.overrides.get(run_id, {}))


@pytest.fixture
def runs(monkeypatch):
    store = _Store({"run-off": {"MILESTONE_EVIDENCE_GATE": False}})
    monkeypatch.setenv("SWITCH_OVERRIDES_FROM_SETTINGS", "on")
    monkeypatch.setenv("MILESTONE_EVIDENCE_GATE", "on")
    monkeypatch.setattr("app.server.run_store.RunStore.shared", classmethod(lambda cls: store))
    monkeypatch.setattr(switches, "stored", lambda name: None)
    switches._RUN_OVERRIDES.clear()
    current = {"run": ""}
    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: current["run"])
    yield current, store
    switches._RUN_OVERRIDES.clear()


def test_the_run_s_own_setting_beats_the_environment(runs) -> None:
    current, _ = runs
    current["run"] = "run-off"
    assert switches.is_on("MILESTONE_EVIDENCE_GATE", False) is False
    current["run"] = "run-on"
    assert switches.is_on("MILESTONE_EVIDENCE_GATE", False) is True, "another run follows the environment"
    current["run"] = ""
    assert switches.is_on("MILESTONE_EVIDENCE_GATE", False) is True, "outside a run nothing changes"


def test_the_run_s_settings_are_read_once_a_while_not_on_every_check(runs) -> None:
    current, store = runs
    current["run"] = "run-off"
    for _ in range(20):
        switches.is_on("MILESTONE_EVIDENCE_GATE", False)
    assert store.reads == 1


def test_without_stored_settings_the_run_s_record_is_not_read(runs, monkeypatch) -> None:
    current, store = runs
    monkeypatch.delenv("SWITCH_OVERRIDES_FROM_SETTINGS")
    current["run"] = "run-off"
    assert switches.is_on("MILESTONE_EVIDENCE_GATE", False) is True
    assert store.reads == 0


def test_two_runs_on_one_commit_one_with_the_switch_off_fall_into_different_arms() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts" / "loop" / "kpi_ledger.py"
    spec = importlib.util.spec_from_file_location("loop_kpi_ledger_arms", path)
    ledger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ledger)
    rows = [
        {"run": "a", "harness_commits": "abc123", "switches_on": "MILESTONE_EVIDENCE_GATE OTHER", "benchmark": "web-todo"},
        {"run": "b", "harness_commits": "abc123", "switches_on": "OTHER", "benchmark": "web-todo"},
    ]
    assert [r["run"] for r in ledger.the_arm(rows, "abc", "web-todo", "MILESTONE_EVIDENCE_GATE", True)] == ["a"]
    assert [r["run"] for r in ledger.the_arm(rows, "abc", "web-todo", "MILESTONE_EVIDENCE_GATE", False)] == ["b"]
    assert len(ledger.the_arm(rows, "abc", "web-todo")) == 2


def test_a_run_is_started_with_its_switches_and_an_unknown_name_is_refused_first() -> None:
    from app.server import models, runs as run_api

    assert "switches" in models.StartRunRequest.model_fields
    source = inspect.getsource(run_api)
    refused = source.index("Unknown switch(es)")
    stored = source.index("set_switch_overrides(run_id, dict(body.switches))")
    started = source.index("pin_model=body.pin_model,")
    assert refused < started < stored


def test_the_provenance_reads_the_switches_as_the_run_sees_them() -> None:
    from app.observability import provenance

    source = inspect.getsource(provenance.record_the_segment)
    assert "with as_the_run(run_id):" in source and "switch_overrides" in source
