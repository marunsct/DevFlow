"""Every run records the harness commit, the served model and the switches on, per segment (plan MF.1).

No run recorded the harness commit or the model the server served, and no run
ever ran on one harness version: every deploy restarts the worker. The KPIs
say which commits a run ran on and mark one that ran on more than one.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

from app.observability import provenance
from app.observability.run_kpis import kpis

ROOT = Path(__file__).resolve().parent.parent


def test_a_segment_names_the_commit_the_model_and_the_switches(monkeypatch):
    monkeypatch.setenv("HARNESS_COMMIT", "abc12345")
    monkeypatch.setenv("DECISION_LEDGER", "on")
    profile = SimpleNamespace(model="Qwen3.6-35B-A3B-Q8_0.gguf", quantisation="Q8_0", slots=2, slot_context=190976)
    record = SimpleNamespace(delivery_mode="fast", local_only=True)

    segment = provenance.the_segment(record, profile)

    assert segment["harness_commit"] == "abc12345" and "DECISION_LEDGER" in segment["switches_on"]
    assert (segment["served_model"], segment["quantisation"], segment["slots"]) == ("Qwen3.6-35B-A3B-Q8_0.gguf", "Q8_0", 2)
    assert segment["delivery_mode"] == "fast" and segment["local_only"] is True


def test_a_build_without_the_commit_says_unknown(monkeypatch):
    monkeypatch.delenv("HARNESS_COMMIT", raising=False)
    assert provenance.harness_commit() == "unknown"


def test_the_kpis_name_the_commits_and_mark_a_mixed_run():
    records = [
        {"at": "2026-10-21T00:00:00+00:00", "kind": "provenance", "harness_commit": "abc12345",
         "served_model": "m.gguf", "quantisation": "Q8_0", "switches_on": []},
        {"at": "2026-10-21T01:00:00+00:00", "kind": "provenance", "harness_commit": "deadbeef",
         "served_model": "m.gguf", "quantisation": "Q8_0", "switches_on": ["FIX_CYCLE"]},
    ]

    row = kpis(records)

    assert row["harness_commits"] == "abc12345 deadbeef" and row["mixed_versions"] is True
    assert row["served_model"] == "m.gguf" and row["switches_on"] == "FIX_CYCLE" and row["segments"] == 2
    assert kpis(records[:1])["mixed_versions"] is False


def test_the_worker_records_each_segment_and_the_build_names_its_commit():
    from app.server import tasks

    assert "record_the_segment(run_id, record, profile)" in inspect.getsource(tasks)
    assert "ARG HARNESS_COMMIT" in (ROOT / "Dockerfile").read_text()
    assert '--build-arg HARNESS_COMMIT="$built"' in (ROOT / "scripts" / "loop" / "loop.sh").read_text()


def test_a_gate_s_wait_and_each_accepted_criterion_s_cost_are_kpis():
    # Plan MF.3: neither existed; human-gate waiting was noted by hand.
    from app.observability.run_kpis import per_accepted_criterion

    records = [
        {"at": "2026-10-21T00:00:00+00:00", "kind": "model_response", "stage": "s", "usage": {"output_tokens": 600}},
        {"at": "2026-10-21T00:10:00+00:00", "kind": "gate", "event": "opened", "gate": "review"},
        {"at": "2026-10-21T00:40:00+00:00", "kind": "gate", "event": "answered", "gate": "review"},
        {"at": "2026-10-21T01:00:00+00:00", "kind": "model_response", "stage": "s", "usage": {"output_tokens": 600}},
    ]
    row = kpis(records)
    assert row["gate_wait_minutes"] == 30.0

    costed = per_accepted_criterion({"wall_minutes": 60.0, "output_tokens": 1200}, 4)
    assert (costed["wall_clock_per_accepted_criterion"], costed["tokens_per_accepted_criterion"]) == (15.0, 300)
    assert per_accepted_criterion({"wall_minutes": 60.0}, 0)["wall_clock_per_accepted_criterion"] is None


def test_the_runner_records_each_gate():
    from app.server import runner

    source = inspect.getsource(runner)
    assert source.count('_record_a_gate(run_id, stage, "opened",') == 2
    assert source.count('_record_a_gate(run_id, "", "answered",') == 2


def test_two_versions_are_compared_on_two_runs_each_with_their_spread_and_no_mixed_run():
    import importlib.util

    spec = importlib.util.spec_from_file_location("kpi_ledger", ROOT / "scripts" / "loop" / "kpi_ledger.py")
    ledger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ledger)
    rows = [
        {"run": "1", "harness_commits": "abc12345", "mixed_versions": "False", "wall_minutes": "100"},
        {"run": "2", "harness_commits": "abc12345", "mixed_versions": "False", "wall_minutes": "120"},
        {"run": "3", "harness_commits": "abc12345 deadbeef", "mixed_versions": "True", "wall_minutes": "999"},
        {"run": "4", "harness_commits": "deadbeef", "mixed_versions": "False", "wall_minutes": "80"},
    ]
    a, b = ledger.the_arm(rows, "abc12345"), ledger.the_arm(rows, "deadbeef")

    assert [r["run"] for r in a] == ["1", "2"] and [r["run"] for r in b] == ["4"]
    assert ledger.compare_arms(a, b) == ["not compared: 2 and 1 run(s); each arm needs at least 2"]
    lines = ledger.compare_arms(a, [*b, {**b[0], "run": "5", "wall_minutes": "90"}])
    assert any(line.startswith("wall_minutes") and "[100-120]" in line and "[80-90]" in line for line in lines)


def test_a_run_whose_first_calls_predate_its_first_segment_is_mixed():
    """A run begun before provenance existed was read as one version: its earlier hours ran on others."""
    segment = {"at": "2026-10-21T06:00:00+00:00", "kind": "provenance", "harness_commit": "abc12345",
               "served_model": "m.gguf", "quantisation": "Q8_0", "switches_on": []}
    earlier = [
        {"at": "2026-10-20T22:25:00+00:00", "stage": "intake", "kind": "model_request"},
        {"at": "2026-10-20T22:26:00+00:00", "stage": "intake", "kind": "model_response"},
    ]

    row = kpis([*earlier, segment])

    assert row["harness_commits"] == "unknown abc12345" and row["mixed_versions"] is True
    assert kpis([segment, *earlier])["mixed_versions"] is False
