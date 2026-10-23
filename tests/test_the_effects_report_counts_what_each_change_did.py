"""`loop.sh effects` counts, from a run's own records, what each fix and switch did (owner, 2026-10-22)."""
from __future__ import annotations

import runpy
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "effects.py"


def test_each_signal_is_counted_and_one_not_reached_says_so():
    effects = runpy.run_path(str(SCRIPT))["effects"]
    records = [
        {"kind": "model_request", "messages": [{"content": "=== LESSONS FROM EARLIER RUNS ===\nx"}]},
        {"kind": "model_request", "messages": [{"content": "You find where in a codebase a failure is caused. You answer"}]},
        {"kind": "tool_result", "content": "... The harness ran this defect's own tests after the write: they pass now. Your defect is fixed"},
        {"kind": "model_response", "usage": {"output_tokens": 32768}},
        {"kind": "defect", "event": "left open", "detail": "left open after 61 model calls across its attempts"},
        "not a record",
    ]
    lines = "\n".join(effects(records, "AC-7 to sprint 2, where a test of it can first pass"))
    assert "   1  LF.191 approved lessons shown" in lines and "   1  AY.1 a defect localised" in lines
    assert "   1  AY.3 a write followed by the defect's tests - passing" in lines
    assert "   1  LF.202 a criterion moved" in lines and "   1  AY.4 a defect left open at its call cap" in lines
    assert "   1  replies lost to the output cap" in lines and "defects: left open 1" in lines
    assert "LF.203 the lead told why a release was held: not reached" in lines


def test_a_salvaged_reply_is_counted_as_salvaged_not_lost():
    """RS.1: a salvaged reply's usage counts the cut-off attempt too, so it is past the cap but was answered."""
    effects = runpy.run_path(str(SCRIPT))["effects"]
    records = [
        {"kind": "model_response", "usage": {"output_tokens": 33_100}, "salvaged": "reasoning"},
        {"kind": "model_response", "usage": {"output_tokens": 9_000}, "salvaged": "continuation"},
        {"kind": "model_response", "usage": {"output_tokens": 32_768}},
    ]
    lines = "\n".join(effects(records, ""))
    assert "   1  replies lost to the output cap" in lines
    assert "   1  RS.1 replies cut off while reasoning" in lines and "   1  RS.1 replies cut off part way" in lines


def test_a_long_reply_that_answered_is_not_lost():
    """An architect's specification came back whole, as its tool call, at 33,613 tokens, and was counted as lost."""
    effects = runpy.run_path(str(SCRIPT))["effects"]
    records = [
        {"kind": "model_response", "usage": {"output_tokens": 33_613}, "finish_reason": "tool_calls",
         "tool_calls": "[{'name': 'TechnicalSpecificationOutput'}]"},
        {"kind": "model_response", "usage": {"output_tokens": 32_768}, "finish_reason": "length", "text": "",
         "tool_calls": "[]"},
    ]
    assert "   1  replies lost to the output cap" in "\n".join(effects(records, ""))
