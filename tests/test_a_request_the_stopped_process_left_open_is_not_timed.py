"""A model request left open by a stopped process is not timed against the next segment's first reply (owner, 2026-11-08).

A request open when a host fault stopped the run was paired with the first reply after the resume 19 hours later:
the stage counted 69,590 seconds of model time, and the run's overall tokens a second read 3.3 instead of about 90.
"""
from __future__ import annotations

from app.observability.stage_usage import stage_usage


def test_a_new_segment_drops_the_requests_the_old_one_left_open() -> None:
    entries = [
        {"at": "2026-11-07T16:45:00+00:00", "stage": "technical_lead", "kind": "model_request"},
        {"at": "2026-11-07T16:45:20+00:00", "stage": "technical_lead", "kind": "model_response",
         "usage": {"output_tokens": 2000}},
        {"at": "2026-11-07T16:45:23+00:00", "stage": "technical_lead", "kind": "model_request"},  # never answered
        {"at": "2026-11-08T12:05:12+00:00", "stage": "", "kind": "provenance"},
        {"at": "2026-11-08T12:05:12+00:00", "stage": "technical_lead", "kind": "model_request"},
        {"at": "2026-11-08T12:05:32+00:00", "stage": "technical_lead", "kind": "model_response",
         "usage": {"output_tokens": 2000}},
    ]
    row = stage_usage(entries)[0]
    assert row["model_seconds"] == 40.0
    assert row["output_tokens"] / row["model_seconds"] == 100.0
