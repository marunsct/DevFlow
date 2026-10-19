"""A run's time, tokens and failures, stage by stage, from its transcript (plan BG.7).

The loop's audit scripts read the transcript inside the worker; the run page
could not, so where a run spent its hours was answered only by an operator
with a shell.
"""

from __future__ import annotations

from pathlib import Path

from app.observability import transcript
from app.observability.stage_usage import stage_usage


def _at(seconds: int) -> str:
    return f"2026-10-19T10:00:{seconds:02d}+00:00"


ENTRIES = [
    {"kind": "model_request", "stage": "architect", "at": _at(0)},
    {"kind": "model_response", "stage": "architect", "at": _at(10), "text": "", "tool_calls": [{"name": "read_file"}],
     "usage": {"input_tokens": 1000, "output_tokens": 50, "input_token_details": {"cache_read": 800}}, "finish_reason": "tool_calls"},
    {"kind": "tool_call", "stage": "architect", "at": _at(11), "tool": "read_file", "call_id": "c1"},
    {"kind": "tool_result", "stage": "architect", "at": _at(11), "tool": "read_file", "call_id": "c1",
     "content": "`docs/spec.md` is in the project memory at the start of this conversation, whole and as it is now"},
    {"kind": "model_request", "stage": "architect", "at": _at(12)},
    {"kind": "model_response", "stage": "architect", "at": _at(40), "text": "", "tool_calls": [],
     "usage": {"input_tokens": 1100, "output_tokens": 20000}, "finish_reason": "length"},
    {"kind": "tool_call", "stage": "defect_fix_1_0", "at": _at(45), "tool": "run_terminal_command", "call_id": "c2"},
    {"kind": "tool_result", "stage": "defect_fix_1_0", "at": _at(46), "tool": "run_terminal_command", "call_id": "c2",
     "content": {"error": "Not running `ls`: reading is done for this stage"}},
    {"kind": "tool_call", "stage": "defect_fix_1_0", "at": _at(50), "tool": "write_artifact", "call_id": "c3"},
    {"kind": "tool_result", "stage": "defect_fix_1_0", "at": _at(51), "tool": "write_artifact", "call_id": "c3", "content": {"path": "a.py"}},
]


def test_each_stage_with_its_time_tokens_and_failures():
    architect, fix = stage_usage(ENTRIES)

    assert architect["stage"] == "architect"
    assert (architect["wall_seconds"], architect["model_seconds"], architect["model_calls"]) == (40.0, 38.0, 2)
    assert (architect["input_tokens"], architect["cached_tokens"], architect["output_tokens"]) == (2100, 800, 20050)
    assert (architect["lost_replies"], architect["redundant_reads"], architect["tool_failures"]) == (1, 1, 0)
    assert (fix["stage"], fix["tool_calls"], fix["tool_failures"], fix["wall_seconds"]) == ("defect_fix_1_0", 2, 1, 6.0)


def test_the_routes_answer_from_the_transcript(client, tmp_path: Path, monkeypatch):
    brief = tmp_path / "brief.md"
    brief.write_text("A product")
    with open(brief, "rb") as handle:
        run_id = client.post("/api/runs", files=[("files", ("brief.md", handle, "text/plain"))]).json()["run_id"]
    monkeypatch.setattr(transcript, "read_transcript", lambda run, kinds=None: ENTRIES)
    monkeypatch.setattr(transcript, "render_transcript", lambda run, kinds=None: "[10:00:00] --> model\n")

    usage = client.get(f"/api/runs/{run_id}/usage").json()
    assert [row["stage"] for row in usage["stages"]] == ["architect", "defect_fix_1_0"]

    download = client.get(f"/api/runs/{run_id}/transcript")
    assert download.status_code == 200 and download.text.startswith("[10:00:00]")
    assert "attachment" in download.headers["content-disposition"]
