"""The KPIs the loop depends on count what they claim (plan item AN).

Found by reading the code against the plan's own account: guard notes are
appended after a tool result's content, and the KPI searched only the first
600 characters for them; the prefill-to-decode ratio counted cached input as
work the server did; the ledger could not flag a count going from 0 to 3; a
bench and a real brief shared one five-run window; a ledger write that died
half-way left half a file.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "scripts" / "loop"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"loop_{name}_an", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kpi = _load("kpi")
ledger = _load("kpi_ledger")


def _at(second: int) -> str:
    return f"2026-10-18T{second // 3600:02d}:{second % 3600 // 60:02d}:{second % 60:02d}+00:00"


def test_a_guard_note_after_a_long_result_is_counted():
    body = "x" * 5000
    records = [
        {"at": _at(0), "stage": "s", "kind": "tool_call", "call_id": "a", "tool": "read_file", "args": {"file_path": "m.py"}},
        {"at": _at(1), "stage": "s", "kind": "tool_result", "call_id": "a",
         "content": body + "\n[These are the same bytes this file gave you 2 previous times in this stage]"},
    ]
    got = kpi.kpis(records)

    assert got["redundant_read_rate"] == 1.0
    assert got["layer_read_held_back"] == 1


def test_cached_input_is_not_prefill_work():
    records = [
        {"at": _at(0), "stage": "s", "kind": "model_request"},
        {"at": _at(2), "stage": "s", "kind": "model_response",
         "usage": {"input_tokens": 1000, "output_tokens": 100, "input_token_details": {"cache_read": 900}}},
    ]
    got = kpi.kpis(records)

    assert got["effective_input_tokens"] == 100
    assert got["prefill_decode_ratio"] == 1.0


def test_reasoning_and_lost_replies_are_estimated_from_the_transcript():
    records = [
        {"at": _at(0), "stage": "s", "kind": "model_request"},
        {"at": _at(2), "stage": "s", "kind": "model_response", "tool_calls": [{"name": "ls"}],
         "usage": {"input_tokens": 10, "output_tokens": 400}, "reasoning_chars": 1200},
        {"at": _at(3), "stage": "s", "kind": "model_request"},
        {"at": _at(5), "stage": "s", "kind": "model_response", "finish_reason": "length", "tool_calls": [],
         "usage": {"input_tokens": 10, "output_tokens": 600}, "reasoning_chars": 2400,
         "invalid_tool_calls": [{"name": "x"}]},
    ]
    got = kpi.kpis(records)

    assert got["reasoning_tokens_estimated"] == 300 + 600
    assert got["reasoning_share_estimated"] == 0.9
    assert got["lost_reply_output_share"] == 0.6
    assert got["invalid_tool_call_rate"] == 0.5


def test_each_stage_has_its_own_block_and_a_gap_between_workers_is_not_work():
    records = [
        {"at": _at(0), "stage": "a", "kind": "model_request"},
        {"at": _at(1), "stage": "a", "kind": "model_response", "usage": {"input_tokens": 5, "output_tokens": 1}},
        {"at": _at(3601), "stage": "b", "kind": "model_request"},
        {"at": _at(3602), "stage": "b", "kind": "model_response", "usage": {"input_tokens": 7, "output_tokens": 1}},
        {"at": _at(3603), "stage": "b", "kind": "model_request"},
        {"at": _at(3604), "stage": "b", "kind": "model_response", "usage": {"input_tokens": 7, "output_tokens": 1}},
    ]
    got = kpi.kpis(records)

    assert [(s["name"], s["calls"], s["input"]) for s in got["stages"]] == [("b", 2, 14), ("a", 1, 5)]
    assert abs(got["orphan_gap_minutes"] - 60.0) < 0.1
    assert got["active_minutes"] < 1


def test_a_count_going_from_zero_to_three_is_flagged_and_a_trivial_rise_is_not(tmp_path):
    path = tmp_path / "ledger.csv"
    for n in range(5):
        ledger.append(path, {"run": f"r{n}", "fixes_reverted": 0, "tool_failure_rate": 0.001})
    row = {"run": "now", "fixes_reverted": 3, "tool_failure_rate": 0.003}

    earlier = ledger.append(path, row)
    flagged = ledger.regressions(earlier, row)

    assert any(f.startswith("fixes_reverted: 3") for f in flagged)
    assert not any(f.startswith("tool_failure_rate") for f in flagged)


def test_a_run_is_compared_with_runs_of_its_own_benchmark(tmp_path):
    path = tmp_path / "ledger.csv"
    for n in range(5):
        ledger.append(path, {"run": f"b{n}", "benchmark": "bench", "identical_call_rate": 0.01})
    ledger.append(path, {"run": "real", "benchmark": "brief", "identical_call_rate": 0.30})
    row = {"run": "next", "benchmark": "brief", "identical_call_rate": 0.32}

    earlier = ledger.append(path, row)

    assert [r["run"] for r in earlier] == ["real"]
    assert ledger.regressions(earlier, row) == []


def test_the_ledger_is_written_beside_itself_and_moved_into_place(tmp_path):
    import inspect

    source = inspect.getsource(ledger.append)
    path = tmp_path / "ledger.csv"
    ledger.append(path, {"run": "r", "tool_calls": 1, "stages": [{"name": "a"}]})

    assert "temporary.replace(ledger)" in source
    assert not (tmp_path / "ledger.csv.tmp").exists()
    assert "stages" not in path.read_text().splitlines()[0]
