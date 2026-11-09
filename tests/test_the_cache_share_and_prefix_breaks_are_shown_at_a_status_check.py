"""The share of prompt tokens served from the server's cache, and where the prefix broke, are shown at a status check.

Measured on one model that reports cached tokens (`prompt_tokens_details.cached_tokens`): 71% of prompt tokens
came from the cache, and the share decides prefill time, a large part of wall-clock on the local model. Both numbers
were computed only after a run (`cached_token_share`, `prefix_break_<reason>` in the KPI row), so a stage that
re-prefilled its context could not be seen while the run was live. And one of the reasons was mismeasured: the note
at the end of a call naming what a write changed was counted into the project memory, so the opening looked changed
after every write and `opening_changed` named breaks the prefix never had.
"""
from __future__ import annotations

from pathlib import Path

from app.observability import cache_report
from app.observability.prefix_breaks import reason
from app.observability.transcript import MEMORY_CHARS, prompt_blocks

LOOP = Path(__file__).resolve().parent.parent / "scripts" / "loop"


def _call(stage, carried, blocks=None, read=0, taken=1000):
    request = {"kind": "model_request", "stage": stage, "at": "t", "carried": carried, "messages": [{}] * 2, "tools": [],
               "blocks": blocks or {"system": 50, "project_memory": 900, "request": 40}}
    usage = {"input_tokens": taken}
    if read is not None:
        usage["input_token_details"] = {"cache_read": read}
    return [request, {"kind": "model_response", "stage": stage, "at": "t", "usage": usage}]


def test_the_note_naming_what_a_write_changed_is_not_counted_as_the_memory():
    memory = "[Project memory: the project's files]\n" + "x" * 500
    opening = {"role": "human", "content": memory + "\n\nFix the failing test.", MEMORY_CHARS: len(memory) + 2}
    reply = {"role": "ai", "content": "", "tool_calls": [{"name": "edit_file", "args": {}, "id": "1"}]}
    result = {"role": "tool", "content": "ok", "tool_call_id": "1"}
    note = {"role": "user", "content": "[Project memory update]\nChanged since the project memory was taken: a.py (3 lines now)"}
    first = prompt_blocks([opening])
    second = prompt_blocks([opening, reply, result, note])

    assert first["project_memory"] == second["project_memory"]
    assert second["notes"] == len(note["content"])
    assert reason({"blocks": first, "carried": 1, "messages": [{}]}, {"blocks": second, "carried": 2, "messages": [{}] * 3}, 4000) == "stable"


def test_the_note_the_memory_writes_is_the_one_the_blocks_know():
    from app.agents.project_memory import changes_since

    assert changes_since({"a.py": "1\n"}, {"a.py": "1\n2\n"}).startswith("[Project memory update]")


def test_the_report_gives_the_share_the_breaks_and_the_stages_that_cost_most():
    records = [
        *_call("defect_fix_1_0", 0, read=0, taken=10000),
        *_call("defect_fix_1_0", 3, read=9000, taken=10500),
        *_call("defect_fix_1_0", 5, blocks={"system": 50, "project_memory": 950, "request": 40}, read=2000, taken=11000),
        *_call("specialist_testing_2", 0, read=0, taken=4000),
        *_call("specialist_testing_2", 3, read=3500, taken=4400),
    ]
    out = cache_report.lines(records)

    assert out[0] == "prompt cache: 36% of 40k input tokens served from cache"
    assert out[1] == "prefix breaks: opening_changed x1 (9k uncached)"
    assert out[2].split() == ["stage", "calls", "cached", "uncached", "first", "break"]
    assert out[3].split()[0] == "defect_fix_1_0" and out[3].split()[-2:] == ["opening_changed", "x1"]
    assert out[4].split()[:2] == ["specialist_testing_2", "2"]


def test_a_server_that_reports_no_cached_tokens_is_not_shown_as_a_cache_that_never_hits():
    out = cache_report.lines([*_call("s", 0, read=None), *_call("s", 3, read=None)])

    assert out[0] == "prompt cache: the server reported no cached tokens over 2 calls (share unknown)"
    assert out[1] == "prefix breaks: none"
    assert len(out) == 2


def test_a_run_with_no_answered_call_prints_nothing():
    assert cache_report.lines([]) == []
    assert cache_report.lines(_call("s", 0)[:1]) == []


def test_status_and_the_audit_print_the_report():
    assert 'in_worker cache_status.py "$run"' in (LOOP / "loop.sh").read_text()
    assert "cache_report.lines" in (LOOP / "audit_live.py").read_text()
    assert "cache_report.lines" in (LOOP / "cache_status.py").read_text()
