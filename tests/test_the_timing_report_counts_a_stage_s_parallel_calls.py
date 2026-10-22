"""The timing report counts every reply of a stage that asks several things at once.

A specification is written in parts, asked at once. The report kept one open
request per stage, so each request overwrote the last: only one reply was
paired, the others were dropped from its calls, tokens and model time, and a
gate run read 20% of its wall as "neither" when the model was answering.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "loop"


def _usage(out):
    return {"input_tokens": 100, "output_tokens": out, "output_token_details": {"reasoning": 0}}


def test_three_parallel_replies_are_three_calls_and_their_time(monkeypatch, tmp_path):
    records = [
        {"at": "2026-10-22T00:00:00+00:00", "stage": "principal_architect", "kind": "model_request"},
        {"at": "2026-10-22T00:00:01+00:00", "stage": "principal_architect", "kind": "model_request"},
        {"at": "2026-10-22T00:00:02+00:00", "stage": "principal_architect", "kind": "model_request"},
        {"at": "2026-10-22T00:01:00+00:00", "stage": "principal_architect", "kind": "model_response", "usage": _usage(1000)},
        {"at": "2026-10-22T00:02:00+00:00", "stage": "principal_architect", "kind": "model_response", "usage": _usage(1000)},
        {"at": "2026-10-22T00:03:00+00:00", "stage": "principal_architect", "kind": "model_response", "usage": _usage(1000)},
    ]
    transcript = tmp_path / "run-p.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in records))
    monkeypatch.setattr(sys, "argv", ["run_timing.py"])
    spec = importlib.util.spec_from_file_location("run_timing_parallel", SCRIPTS / "run_timing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.glob, "glob", lambda pattern: [str(transcript)])

    out = io.StringIO()
    with redirect_stdout(out):
        module.analyse("run-p")
    text = out.getvalue()

    assert "model calls 3 | output tokens 3,000" in text
    assert "neither 0 min (0%)" in text


def test_the_kpis_and_the_stage_usage_count_the_time_of_each_parallel_call():
    from app.observability.run_kpis import kpis
    from app.observability.stage_usage import recent_calls, stage_usage

    records = [
        {"at": "2026-10-22T00:00:00+00:00", "stage": "principal_architect", "kind": "model_request"},
        {"at": "2026-10-22T00:00:00+00:00", "stage": "principal_architect", "kind": "model_request"},
        {"at": "2026-10-22T00:01:00+00:00", "stage": "principal_architect", "kind": "model_response", "usage": _usage(10)},
        {"at": "2026-10-22T00:02:00+00:00", "stage": "principal_architect", "kind": "model_response", "usage": _usage(10)},
    ]
    row = next(r for r in stage_usage(records) if r["stage"] == "principal_architect")
    assert row["model_seconds"] == 180.0
    from datetime import datetime, timezone

    now = datetime(2026, 10, 22, 0, 3, tzinfo=timezone.utc)
    assert [c["seconds"] for c in recent_calls(records, now=now)] == [60.0, 120.0]
    assert kpis(records)["model_calls"] == 2
