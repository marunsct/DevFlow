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


def test_each_review_stage_s_summaries_and_reads_a_file_are_counted():
    """LF.1284: measured on one medium run, a security review made 155 reads of 21 files and was summarised 11 times;
    the next medium run is read for at most 1.2 reads a file and no summary in a review."""
    effects = runpy.run_path(str(SCRIPT))["effects"]

    def read(stage: str, path: str) -> dict:
        return {"kind": "tool_call", "stage": stage, "tool": "read_file", "args": {"file_path": path}}

    records = [
        read("security_review", "app/a.py"), read("security_review", "app/a.py"), read("security_review", "/app/b.py"),
        {"kind": "model_request", "stage": "security_review",
         "messages": [{"content": "You are a Context Extraction Assistant ..."}]},
        read("code_review_0_1", "app/a.py"),
        read("technical_lead", "app/a.py"), read("technical_lead", "app/a.py"),
        read("acceptance_review_3", "acceptance/a.spec.js"), read("test_round_2", "app/a.py"),
        read("specialist_backend_0", "app/a.py"),
    ]
    lines = "\n".join(effects(records, ""))

    assert "   1  security_review: summaries; 3 reads of 2 files, 1.5 a file" in lines
    assert "   0  code_review: summaries; 1 reads of 1 files, 1.0 a file" in lines
    assert "   0  technical_lead: summaries; 2 reads of 1 files, 2.0 a file" in lines, "LF.1286: the lead too"
    assert "   0  acceptance_review: summaries; 1 reads of 1 files" in lines
    assert "   0  test_round: summaries; 1 reads of 1 files" in lines
    assert "   0  specialist_backend: summaries; 1 reads of 1 files" in lines, "LF.1288: the builders too"


def test_a_summary_made_as_the_stage_s_work_note_is_counted():
    """PA.2: the summariser's request opens with the work note's words, not langchain's; a summary is still one."""
    effects = runpy.run_path(str(SCRIPT))["effects"]
    records = [
        {"kind": "tool_call", "stage": "acceptance_author_2", "tool": "read_file", "args": {"file_path": "app/a.py"}},
        {"kind": "model_request", "stage": "acceptance_author_2",
         "messages": [{"content": "You keep the work note of one stage of a software build. ..."}]},
    ]

    assert "   1  acceptance_author: summaries; 1 reads of 1 files" in "\n".join(effects(records, ""))


def test_whole_reads_are_counted_against_reads_by_range_and_the_suite_s_author_is_read_too():
    """LF.1287/LF.1288: the memory outlines what it does not hold so a stage reads by range, and the suite's author
    holds its own files after a summary; measured on one medium run, the author read its own file 3-8 times a visit."""
    effects = runpy.run_path(str(SCRIPT))["effects"]

    def read(stage: str, path: str, **window) -> dict:
        return {"kind": "tool_call", "stage": stage, "tool": "read_file", "args": {"file_path": path, **window}}

    records = [
        read("technical_lead", "app/a.py"), read("technical_lead", "app/a.py", offset=40, limit=30),
        {"kind": "tool_call", "stage": "technical_lead", "tool": "read_file",
         "args": "{'file_path': 'app/b.py', 'offset': 1, 'limit': 20}"},
        read("acceptance_author_0_accounts", "acceptance/a.spec.js"),
        read("acceptance_author_1", "acceptance/a.spec.js"),
    ]
    lines = "\n".join(effects(records, ""))

    assert "technical_lead: summaries; 3 reads of 2 files, 1.5 a file; 1 whole, 2 by range" in lines
    assert "acceptance_author: summaries; 2 reads of 1 files, 2.0 a file; 2 whole, 0 by range" in lines


def test_a_run_with_no_review_yet_says_so():
    effects = runpy.run_path(str(SCRIPT))["effects"]

    assert "LF.1284/LF.1286 reading stages: summaries, and reads per distinct file (target <= 1.2, no summary): not reached" \
        in "\n".join(effects([], ""))
