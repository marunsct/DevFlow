"""A server that reports no cache reads has an unknown cache share, not a share of 0 (harness review C1).

Measured on 2026-11-07: 112 of 217 ledger rows held `cached_token_share = 0` - every run on the server that reports no
`input_token_details` - which pulled the ledger's median to 0 and let `impact.py` compare a known share against a
false 0. `prefix_breaks` already says a server that reports nothing "has no share, which is not a share of 0%".
"""
from __future__ import annotations

from app.observability.run_kpis import kpis


def _call(at, usage):
    return [
        {"at": at, "stage": "s", "kind": "model_request"},
        {"at": at, "stage": "s", "kind": "model_response", "usage": usage},
    ]


def test_no_reported_cache_reads_is_unknown():
    records = _call("2026-11-07T00:00:00+00:00", {"input_tokens": 1000, "output_tokens": 10}) + _call(
        "2026-11-07T00:00:05+00:00", {"input_tokens": 1200, "output_tokens": 10})
    assert kpis(records)["cached_token_share"] is None


def test_a_reported_zero_is_a_real_zero():
    usage = {"input_tokens": 1000, "output_tokens": 10, "input_token_details": {"cache_read": 0}}
    assert kpis(_call("2026-11-07T00:00:00+00:00", usage))["cached_token_share"] == 0.0


def test_a_reported_share_is_kept():
    usage = {"input_tokens": 1000, "output_tokens": 10, "input_token_details": {"cache_read": 750}}
    assert kpis(_call("2026-11-07T00:00:00+00:00", usage))["cached_token_share"] == 0.75
