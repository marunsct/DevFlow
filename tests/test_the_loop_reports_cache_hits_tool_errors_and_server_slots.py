"""The loop's reports carry the prompt-cache share, per-tool error rates and the server's slots (U.2, S).

Each was measured by hand in one review: cache hits 45-73% (no report read the
cached-token counts the transcripts carry), replace_lines failing 62%, and a
one-slot server that made two runs wait for each other.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "loop"


def _run_timing(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_timing.py"])
    spec = importlib.util.spec_from_file_location("run_timing_under_test", SCRIPTS / "run_timing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_timing_report_states_cache_share_and_tool_errors(monkeypatch, tmp_path):
    records = [
        {"at": "2026-10-18T00:00:00+00:00", "stage": "technical_lead", "kind": "model_request"},
        {"at": "2026-10-18T00:00:10+00:00", "stage": "technical_lead", "kind": "model_response",
         "usage": {"input_tokens": 1000, "output_tokens": 10, "input_token_details": {"cache_read": 600}}},
        {"at": "2026-10-18T00:00:11+00:00", "stage": "technical_lead", "kind": "tool_call", "call_id": "a", "tool": "replace_lines"},
        {"at": "2026-10-18T00:00:12+00:00", "stage": "technical_lead", "kind": "tool_result", "call_id": "a", "tool": "replace_lines", "content": "Error: stale range"},
        {"at": "2026-10-18T00:00:13+00:00", "stage": "technical_lead", "kind": "tool_call", "call_id": "b", "tool": "edit_artifact"},
        {"at": "2026-10-18T00:00:14+00:00", "stage": "technical_lead", "kind": "tool_result", "call_id": "b", "tool": "edit_artifact", "content": "{\"status\": \"edited\"}"},
    ]
    transcript = tmp_path / "run-x.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in records))
    module = _run_timing(monkeypatch)
    monkeypatch.setattr(module.glob, "glob", lambda pattern: [str(transcript)])

    out = io.StringIO()
    with redirect_stdout(out):
        module.analyse("run-x")

    assert "600 of 1,000 input tokens served from cache (60%)" in out.getvalue()
    assert "replace_lines 1/1 (100%)" in out.getvalue() and "edit_artifact 0/1 (0%)" in out.getvalue()


def test_readiness_reads_what_the_server_says_of_its_slots_and_context():
    source = (SCRIPTS / "model_ready.py").read_text()
    assert "from app.models.server_profile import read" in source
    from app.models import server_profile

    profile = (SCRIPTS.parents[1] / "src" / "app" / "models" / "server_profile.py").read_text()
    assert '"/props"' in profile and "total_slots" in profile and "n_ctx" in profile
    assert server_profile.from_props({"total_slots": 2, "default_generation_settings": {"n_ctx": 8192}}).slots == 2
