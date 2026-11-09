"""The improvement scan shows replies cut off at the output cap, with their minutes, and pointer-answered reads (HR2.P.8).

`effects` counted only replies lost to the cap: one run's 5 capped-and-salvaged planning replies, 14 minutes, read
as 0, and no audit line showed how often a read was answered from the project memory.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _scan():
    path = Path(__file__).resolve().parents[1] / "scripts" / "loop" / "scan.py"
    spec = importlib.util.spec_from_file_location("loop_scan_caps", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_salvaged_planning_reply_prints_its_minutes(tmp_path) -> None:
    transcript = tmp_path / "run-x.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in [
        {"at": "2026-01-01T00:00:00+00:00", "stage": "technical_lead", "kind": "model_request"},
        {"at": "2026-01-01T00:06:00+00:00", "stage": "technical_lead", "kind": "model_response",
         "finish_reason": "length", "salvaged": "reasoning"},
        {"at": "2026-01-01T00:07:00+00:00", "stage": "technical_lead", "kind": "tool_result",
         "content": "`docs/spec.md` is in the project memory at the start of this conversation, whole."},
        {"at": "2026-01-01T00:08:00+00:00", "stage": "technical_lead", "kind": "model_response", "finish_reason": "stop"},
    ]))
    assert _scan().cap_and_pointer_lines(str(transcript)) == [
        "capped replies: 1 (6 min): technical_lead 1 (6 min, 1 salvaged)",
        "reads answered with a pointer: 1: technical_lead 1",
    ]


def test_a_run_with_neither_prints_nothing(tmp_path) -> None:
    transcript = tmp_path / "run-y.jsonl"
    transcript.write_text(json.dumps({"at": "2026-01-01T00:00:00+00:00", "stage": "a", "kind": "model_response",
                                      "finish_reason": "stop"}))
    assert _scan().cap_and_pointer_lines(str(transcript)) == []
