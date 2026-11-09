"""A prefix break of the opening names which block moved (HR2.C.3); what followed a salvaged reply is counted
(HR2.C.4a); a model's pre-flight diagnosis is said in the transcript (HR2.OB.1)."""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

from app.observability import prefix_breaks


def _request(stage, memory, carried=1):
    return {"kind": "model_request", "stage": stage, "carried": carried, "tools": ["a"],
            "blocks": {"system": 10, "environment_contract": 5, "project_memory": memory, "specification": 20, "request": 7}}


def _reply(stage, cached=50):
    return {"kind": "model_response", "stage": stage, "usage": {"input_tokens": 100, "input_token_details": {"cache_read": cached}}}


def test_the_block_that_moved_is_named_and_its_tokens_summed():
    records = [_request("s", 30), _reply("s"), _request("s", 31), _reply("s"), _request("s", 31, carried=2), _reply("s")]
    calls = list(prefix_breaks.classified(records))
    assert calls[1]["why"] == "opening_changed" and calls[1]["block"] == "project_memory"
    assert prefix_breaks.breaks(records)["uncached_tokens_opening_by_block"] == {"project_memory": 50}


def test_what_followed_each_salvaged_reply_is_counted():
    SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "kpi.py"
    spec = importlib.util.spec_from_file_location("kpi_script2", SCRIPT)
    kpi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kpi)
    records = [
        {"kind": "model_response", "stage": "a", "salvaged": "reasoning"},
        {"kind": "model_request", "stage": "a"}, {"kind": "model_response", "stage": "a", "salvaged": "reasoning"},
        {"kind": "model_request", "stage": "a"}, {"kind": "model_response", "stage": "a"},
        {"kind": "model_response", "stage": "b", "salvaged": "continuation"},
    ]
    out = kpi.with_salvage_outcomes({}, records)
    assert (out["salvaged_replies"], out["salvaged_then_cut_again"], out["salvaged_then_another_call"],
            out["salvaged_at_stage_end"]) == (3, 1, 1, 1)


def test_the_diagnosis_is_said_in_the_transcript():
    from app.server import tasks

    source = inspect.getsource(tasks.execute_workflow_run)
    assert source.count('"model_diagnostic"') >= 3


def test_a_resume_writes_its_record_again():
    from app.server import runner

    source = inspect.getsource(runner.WorkflowRunner.resume_run)
    assert '"resumed"' in source and "note_in_transcript(run_id" in source
