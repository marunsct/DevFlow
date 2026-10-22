"""Each model call that missed the cached prefix is classified by the first part of its request that changed (plan PX.1).

Read from the transcript's existing records - the tools offered, each block's
size, how many earlier messages were resent - so it changes no request.
"""
from __future__ import annotations

from app.observability.prefix_breaks import breaks, reason
from app.observability.run_kpis import kpis

BLOCKS = {"tool_schemas": 100, "system": 50, "environment_contract": 5, "project_memory": 900, "specification": 300, "request": 40, "conversation": 10}


def _request(tools=("read_file", "edit_artifact"), carried=3, added=3, **blocks):
    return {"at": "2026-10-22T00:00:00+00:00", "kind": "model_request", "stage": "defect_fix_1_0", "tools": list(tools), "carried": carried,
            "messages": [{}] * added, "blocks": {**BLOCKS, **blocks}}


def test_the_first_differing_part_names_the_break():
    before = _request()
    assert reason(before, _request(tools=("edit_artifact",), carried=5, tool_schemas=60), 0) == "tools_changed"
    assert reason(before, _request(carried=5, system=80), 0) == "system_changed"
    assert reason(before, _request(carried=5, project_memory=950), 0) == "opening_changed"
    assert reason(before, _request(carried=3), 4000) == "history_rewritten"
    assert reason(before, _request(carried=5), 0) == "evicted"
    assert reason(before, _request(carried=5), 4000) == "stable"


def test_the_run_kpis_carry_the_counts_and_the_uncached_tokens():
    usage = lambda read: {"input_tokens": 10000, "input_token_details": {"cache_read": read}}  # noqa: E731
    records = [
        _request(carried=0), {"at": "2026-10-22T00:01:00+00:00", "kind": "model_response", "stage": "defect_fix_1_0", "usage": usage(0)},
        _request(tools=("edit_artifact",), carried=3, tool_schemas=60), {"at": "2026-10-22T00:02:00+00:00", "kind": "model_response", "stage": "defect_fix_1_0", "usage": usage(2000)},
    ]
    assert breaks(records)["calls_by_reason"] == {"first_of_the_stage": 1, "tools_changed": 1}
    found = kpis(records)
    assert found["prefix_break_tools_changed"] == 1 and found["uncached_tokens_tools_changed"] == 8000


def test_malformed_records_never_raise():
    records = [
        {"kind": "model_request", "stage": "s", "at": "t", "tools": "[", "blocks": "{[1]: 2}", "messages": 3},
        {"kind": "model_response", "stage": "s", "at": "t", "usage": {"input_tokens": "abc", "input_token_details": {"cache_read": [1]}}},
        {"kind": "model_request", "stage": "s", "at": "t", "tools": [], "blocks": {}, "messages": None},
        {"kind": "model_response", "stage": "s", "at": "t", "usage": {"input_tokens": {"a": 1}}},
    ]
    out = breaks(records)
    assert sum(out["calls_by_reason"].values()) == 2
