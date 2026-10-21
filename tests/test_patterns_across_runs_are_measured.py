"""`loop.sh patterns` measures across every run what one run's audit cannot see.

A fixer handed four or more defects fixed 26% of them against 64% for one
handed one - visible only across all runs, and missed while each audit read
only the live one.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("patterns", ROOT / "scripts" / "loop" / "patterns.py")
patterns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patterns)

AT = "2026-10-21T00:00:00+00:00"


def _run(path: Path, records: list[dict]) -> str:
    path.write_text("\n".join(json.dumps({"at": AT, **r}) for r in records) + "\n")
    return str(path)


def test_reply_health_bundle_outcomes_and_recurring_failures(tmp_path):
    lone = _run(tmp_path / "run-aaaaaaaa.jsonl", [
        {"kind": "model_response", "stage": "defect_fix_1_0", "usage": {"output_tokens": 900}, "finish_reason": "stop", "text": ""},
        {"kind": "defect", "stage": "defect_fix_1_0", "event": "fixed", "index": 0},
        {"kind": "model_response", "stage": "scrum_master", "usage": {"output_tokens": 33000}, "finish_reason": "length",
         "text": "{\"sprints\": [" + "\" - " * 3000},
        {"kind": "tool_call", "stage": "defect_fix_1_0", "tool": "edit_artifact", "call_id": "c1"},
        {"kind": "tool_result", "stage": "defect_fix_1_0", "call_id": "c1", "content": "{\"error\": \"Could not find that text in 'a.py'.\"}"},
    ])
    bundle = _run(tmp_path / "run-bbbbbbbb.jsonl", [
        {"kind": "model_response", "stage": "defect_fix_1_0", "usage": {"output_tokens": 33000}, "finish_reason": "length", "text": ""},
        *[{"kind": "defect", "stage": "defect_fix_1_0", "event": "bundled", "index": i} for i in (1, 2, 3)],
        {"kind": "defect", "stage": "defect_fix_1_0", "event": "left open", "index": 0},
        {"kind": "tool_call", "stage": "specialist_backend_0", "tool": "edit_artifact", "call_id": "c2"},
        {"kind": "tool_result", "stage": "specialist_backend_0", "call_id": "c2", "content": "{\"error\": \"Could not find that text in 'b.py'.\"}"},
    ])

    report = patterns.analyse([lone, bundle], "2026-10-20")

    planner = next(r for r in report["families"] if r["family"] == "scrum_master")
    assert planner["cut"] == 1 and planner["looping"] == 1
    fixer = next(r for r in report["families"] if r["family"] == "defect_fix")
    assert fixer["all_reasoning"] == 1 and fixer["replies"] == 2
    assert [(b["bundle"], b["stages"], b["fixed_share"], b["cut_share"]) for b in report["bundles"]] == [
        ("1", 1, 1.0, 0.0), ("4+", 1, 0.0, 1.0)]
    top = report["failures"][0]
    assert top["tool"] == "edit_artifact" and top["runs"] == 2 and "Could not find that text" in top["signature"]


def test_the_loop_offers_it():
    assert "patterns) shift; in_worker patterns.py" in (ROOT / "scripts" / "loop" / "loop.sh").read_text()
