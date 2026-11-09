"""A run an earlier recovery left failed, its resume lost, is resumed when a worker starts (plan OP.1).

After every host restart the operator resumed such runs by hand: recovery marks
an abandoned run failed and resumes it, and when that resume was lost no sweep
looked at a failed row again. A paused run is someone's decision and is never touched.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.server.manage import STOPPED_WORKER_MARKER, runs_a_restart_left_failed


def _run(run_id: str, status: str, error: str = "", hours_ago: float = 1, cancel: bool = False):
    when = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    return SimpleNamespace(run_id=run_id, status=status, error=error, updated_at=when, cancel_requested=cancel)


def test_only_a_recent_run_recovery_failed_for_a_stopped_worker_is_picked():
    stopped = f"{STOPPED_WORKER_MARKER} - the host or the container went away mid-task."
    records = [
        _run("run-a", "failed", stopped),
        _run("run-b", "failed", stopped, hours_ago=30),
        _run("run-c", "failed", "The acceptance suite cannot run"),
        _run("run-d", "paused"),
        _run("run-e", "failed", stopped, cancel=True),
    ]

    assert runs_a_restart_left_failed(records) == ["run-a"]


def test_the_marker_is_the_one_recovery_writes():
    from app.server import manage

    assert f'"{STOPPED_WORKER_MARKER} - the host or "' in inspect.getsource(manage._the_words_recovery_writes)
    assert "_the_words_recovery_writes(oom_killed)" in inspect.getsource(manage.recover_orphaned_runs)


def test_the_startup_sweep_resumes_them():
    from app.server import tasks

    source = inspect.getsource(tasks._sweep_for_abandoned_runs)
    assert "resume_runs_a_restart_abandoned(left)" in source and "runs_a_restart_left_failed(" in source
