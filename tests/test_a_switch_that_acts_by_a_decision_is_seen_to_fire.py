"""A switch whose act is a decision is seen to fire, and the switches with no signal at all are named (deep review of
silent mechanisms, 2026-11-25).

The switch-firing register read only the transcript, and a decision lived only in the workspace's decision log:
`ONE_DESIGN_REVIEW` acted in 33 of 40 decision logs and was counted as firing in none of 29 runs, so the gate that
decides whether a switch earned its place read it as dead. And 90 of the 125 switches recorded on had no signal at all,
which nothing said.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from app.observability import switch_firing

CAPTURED = Path(__file__).parent / "captured" / "decision-log-a-design-revised-once.md"


def test_a_decision_log_that_says_the_design_was_revised_once_fires_the_switch():
    assert "ONE_DESIGN_REVIEW" in switch_firing.fired([], CAPTURED.read_text(encoding="utf-8"))


def test_a_decision_taken_in_a_run_is_kept_in_its_transcript_and_read_as_firing(tmp_path, monkeypatch):
    from app.decisions import record_decision
    from app.observability.log_context import for_the_run
    from app.observability.transcript import read_transcript

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RUN_TRANSCRIPT", "true")
    why = [line for line in CAPTURED.read_text(encoding="utf-8").splitlines()
           if "revised once and not reviewed again" in line][0].removeprefix("- **Why:** ")
    with for_the_run("run-a"):
        record_decision({"repository": SimpleNamespace(root_path=str(tmp_path))}, {}, point="design",
                        question="The architecture review still asks for changes: how does the run go on?",
                        decision="build from the latest specification, recording the open points as known risks",
                        rationale=why)

    assert "ONE_DESIGN_REVIEW" in switch_firing.fired(read_transcript("run-a"))


def test_the_switches_on_with_no_signal_are_named():
    records = [{"kind": "provenance", "switches_on": ["ONE_DESIGN_REVIEW", "STABLE_MEMORY_ORDER", "FIX_CYCLE",
                                                       "SETTLE_SPEC_CONTRADICTIONS", "PRODUCT_PREVIEW"]}]

    assert switch_firing.without_a_signal(records) == ["FIX_CYCLE", "PRODUCT_PREVIEW"]


def _effects():
    spec = importlib.util.spec_from_file_location(
        "effects_script", Path(__file__).resolve().parents[1] / "scripts" / "loop" / "effects.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_effects_report_names_them():
    records = [{"kind": "provenance", "switches_on": ["ONE_DESIGN_REVIEW", "PRODUCT_PREVIEW"]}]

    text = "\n".join(_effects().effects(records, ""))

    assert "no firing signal" in text and "PRODUCT_PREVIEW" in text.split("no firing signal")[1]


def test_the_kpi_row_counts_a_decision_as_firing(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "kpi_script", Path(__file__).resolve().parents[1] / "scripts" / "loop" / "kpi.py")
    kpi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kpi)
    transcript = tmp_path / "run-b.jsonl"
    transcript.write_text(json.dumps({"at": "2026-11-25T00:00:00+00:00", "kind": "model_request", "stage": "s",
                                      "messages": []}) + "\n")
    monkeypatch.setattr(kpi.glob, "glob", lambda pattern: [str(transcript)] if "transcripts" in pattern else
                        [str(CAPTURED)] if "decision_log" in pattern else [])
    monkeypatch.setattr(kpi, "paused_seconds_of", lambda run: 0.0)
    monkeypatch.setattr(kpi, "accepted_criteria", lambda run: None)
    monkeypatch.setattr(kpi, "owner_rating", lambda run: {})
    printed: list[str] = []
    monkeypatch.setattr("builtins.print", printed.append)

    kpi.main("run-b")

    assert "ONE_DESIGN_REVIEW" in json.loads(printed[-1])["switches_fired"].split()
