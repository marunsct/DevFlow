"""A run that failed, or that sits started with no record at all, is told beyond the browser too (LR.62).

Found in the launch review: the notices covered only a running run gone quiet and a gate waiting; a run that failed
overnight, and one that sat nine hours "running" behind two long runs with no transcript, were told to nobody.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.server import stall_notices

NOW = datetime(2026, 11, 16, 4, 0, tzinfo=timezone.utc)


def _run(run_id, status, minutes_ago):
    return SimpleNamespace(run_id=run_id, status=status, current_stage="x",
                           updated_at=(NOW - timedelta(minutes=minutes_ago)).isoformat())


def test_a_recent_failure_and_a_run_never_picked_up_are_found():
    found = stall_notices.findings([_run("a", "failed", 5), _run("b", "failed", 600), _run("c", "running", 90)], NOW,
                                   activity=lambda run_id: None)
    assert [(f["run_id"], f["kind"]) for f in found] == [("a", "failed"), ("c", "queued")]


def test_a_running_run_with_recent_activity_is_not():
    found = stall_notices.findings([_run("c", "running", 90)], NOW, activity=lambda run_id: NOW - timedelta(minutes=2))
    assert found == []
