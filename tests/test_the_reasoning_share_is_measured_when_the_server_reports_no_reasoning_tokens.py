"""The reasoning share is measured on a server that reports no reasoning tokens.

Measured live: a run's timing report said 0% of its 2.7M output tokens were
reasoning, on a model that lost replies to reasoning. The local server sends
no reasoning token count, and the transcript kept no trace of the reasoning,
so the figure measured nothing.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

from app.models import REASONING_CHARS, REASONING_FIELD, CompatibleChatOpenAI

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "loop"


def _response(reasoning):
    message = {"role": "assistant", "content": "done", "reasoning_content": reasoning}
    return {"id": "r", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}]}


def test_a_reply_keeps_its_whole_reasoning_length_out_of_what_is_sent_back():
    model = CompatibleChatOpenAI(base_url="http://local:1234/v1", api_key="k", model="m")
    message = model._create_chat_result(_response("x" * 5000)).generations[0].message

    assert message.response_metadata[REASONING_CHARS] == 5000
    assert REASONING_CHARS not in message.additional_kwargs
    assert len(message.additional_kwargs[REASONING_FIELD]) < 5000


def test_the_transcript_records_the_reasoning_length():
    source = (SCRIPTS.parents[1] / "src" / "app" / "observability" / "transcript.py").read_text()
    assert 'reasoning_chars=(getattr(message, "response_metadata", None) or {}).get("reasoning_chars")' in source


def test_the_timing_report_estimates_the_share_from_the_length(monkeypatch, tmp_path):
    records = [
        {"at": "2026-10-18T00:00:00+00:00", "stage": "defect_fix_1_0", "kind": "model_request"},
        {"at": "2026-10-18T00:00:10+00:00", "stage": "defect_fix_1_0", "kind": "model_response",
         "usage": {"input_tokens": 1000, "output_tokens": 1000, "output_token_details": {}},
         "reasoning_chars": 2000},
    ]
    transcript = tmp_path / "run-r.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in records))
    monkeypatch.setattr(sys, "argv", ["run_timing.py"])
    spec = importlib.util.spec_from_file_location("run_timing_reasoning", SCRIPTS / "run_timing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.glob, "glob", lambda pattern: [str(transcript)])

    out = io.StringIO()
    with redirect_stdout(out):
        module.analyse("run-r")

    assert "of which reasoning 500 (50%)" in out.getvalue()
