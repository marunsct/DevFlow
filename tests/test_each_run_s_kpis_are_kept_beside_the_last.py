"""Each run's KPIs are one JSON object, kept in a ledger beside the runs before it (Initiative W.4).

The audits printed text for a person; nothing kept the numbers, so "this cut
the waste" was a claim about two terminal screens. `kpi.py` computes one
object per run from its transcript, `kpi_ledger.py` keeps it in a CSV and
names every KPI past 1.5x its five-run mean.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "scripts" / "loop"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"loop_{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kpi = _load("kpi")
ledger = _load("kpi_ledger")


def _at(second: int) -> str:
    return f"2026-10-18T00:00:{second:02d}+00:00"


RECORDS = [
    {"at": _at(0), "stage": "test_round_0", "kind": "defect", "event": "raised"},
    {"at": _at(1), "stage": "defect_fix_0_0", "kind": "model_request"},
    {"at": _at(5), "stage": "defect_fix_0_0", "kind": "model_response",
     "usage": {"input_tokens": 900, "output_tokens": 100, "input_token_details": {"cache_read": 450}}},
    {"at": _at(6), "stage": "defect_fix_0_0", "kind": "tool_call", "call_id": "a", "tool": "read_file", "args": {"file_path": "x"}},
    {"at": _at(6), "stage": "defect_fix_0_0", "kind": "tool_result", "call_id": "a", "content": "one"},
    {"at": _at(7), "stage": "defect_fix_0_0", "kind": "tool_call", "call_id": "b", "tool": "read_file", "args": {"file_path": "x"}},
    {"at": _at(7), "stage": "defect_fix_0_0", "kind": "tool_result", "call_id": "b", "content": "one"},
    {"at": _at(8), "stage": "defect_fix_0_0", "kind": "tool_call", "call_id": "c", "tool": "read_file", "args": {"file_path": "x"}},
    {"at": _at(8), "stage": "defect_fix_0_0", "kind": "tool_result", "call_id": "c",
     "content": "Refusing to read 'x' again: this returns nothing you have not already been given"},
    {"at": _at(9), "stage": "defect_fix_0_0", "kind": "tool_call", "call_id": "d", "tool": "edit_file", "args": {}},
    {"at": _at(9), "stage": "defect_fix_0_0", "kind": "tool_result", "call_id": "d", "content": "Error: edit_file is not a valid tool"},
    {"at": _at(10), "stage": "defect_fix_0_0", "kind": "model_response", "finish_reason": "length", "tool_calls": []},
    {"at": _at(10), "stage": "defect_fix_0_0", "kind": "defect", "event": "left open"},
    {"at": _at(10), "stage": "defect_fix_0_0", "kind": "defect", "event": "reverted"},
]


def test_one_run_s_kpis_come_from_its_transcript() -> None:
    got = kpi.kpis(RECORDS)

    assert got["tool_calls"] == 4
    assert got["tool_failure_rate"] == 0.5          # the refusal and the unknown tool
    assert got["redundant_read_rate"] == round(1 / 3, 4)
    assert got["identical_call_rate"] == 0.25       # the second read answered the same; the refusal is a guard
    assert got["unknown_tool_name_rate"] == 0.25
    assert got["cached_token_share"] == 0.5
    assert got["prefill_decode_ratio"] == 4.5       # (900 input - 450 from cache) / 100 output
    assert got["replies_lost_to_length"] == 1
    assert (got["defects_raised"], got["defects_left_open"], got["fixes_reverted"]) == (1, 1, 1)
    assert got["defect_fix_stages"] == 1
    json.dumps(got)


def test_a_kpi_past_one_and_a_half_times_its_recent_mean_is_flagged(tmp_path) -> None:
    path = tmp_path / "ledger.csv"
    for number, rate in enumerate((0.05, 0.06, 0.04, 0.05, 0.05)):
        ledger.append(path, {"run": f"r{number}", "tool_failure_rate": rate, "cached_token_share": 0.7})

    worse = {"run": "now", "tool_failure_rate": 0.12, "cached_token_share": 0.1}
    earlier = ledger.append(path, worse)

    flagged = ledger.regressions(earlier, worse)
    assert len(flagged) == 1 and flagged[0].startswith("tool_failure_rate: 0.12")


def test_a_run_scored_again_replaces_its_row(tmp_path) -> None:
    path = tmp_path / "ledger.csv"
    ledger.append(path, {"run": "r", "tool_calls": 1})
    earlier = ledger.append(path, {"run": "r", "tool_calls": 2})

    assert earlier == []
    assert path.read_text().count("\nr,") == 1


def test_the_loop_keeps_every_scored_run_s_kpis() -> None:
    loop = (ROOT / "loop.sh").read_text()
    assert 'in_worker kpi.py "$run"' in loop
    assert '"$0" kpi "$run"' in loop


def test_a_read_the_memory_answers_with_a_pointer_is_redundant() -> None:
    """431 of one run's identical repeats were these pointers, and neither audit counted them."""
    records = [
        {"at": _at(0), "stage": "s", "kind": "tool_call", "call_id": "a", "tool": "read_file", "args": {"file_path": "m.py"}},
        {"at": _at(1), "stage": "s", "kind": "tool_result", "call_id": "a",
         "content": "`m.py` is in the project memory at the start of this conversation, whole and as it is now"},
    ]
    assert kpi.kpis(records)["redundant_read_rate"] == 1.0
    assert "is in the project memory at the start of this conversation" in (ROOT / "audit_live.py").read_text()


def test_each_guard_layer_s_interventions_are_counted() -> None:
    """Initiative V: how often each layer acted, kept per run."""
    got = kpi.kpis(RECORDS)
    assert got["layer_read_refused"] == 1
    assert all(key in got for key in kpi.LAYERS)


def test_two_runs_compare_side_by_side() -> None:
    lines = ledger.compare({"tool_calls": 100, "run": "a"}, {"tool_calls": 80, "run": "b"})
    assert lines == ["tool_calls                              100             80 (-20%)"]


def test_a_tool_withheld_is_counted_from_the_requests_tool_lists() -> None:
    """The withholding notice is a correction message, never a tool result."""
    records = [
        {"at": _at(0), "stage": "s", "kind": "model_request", "tools": "['ls', 'read_file', 'edit_artifact']"},
        {"at": _at(1), "stage": "s", "kind": "model_request", "tools": "['ls', 'edit_artifact']"},
        {"at": _at(2), "stage": "s", "kind": "model_request", "tools": "['ls', 'edit_artifact']"},
        {"at": _at(3), "stage": "t", "kind": "model_request", "tools": "['ls']"},
    ]
    assert kpi.kpis(records)["layer_tool_withheld"] == 1
