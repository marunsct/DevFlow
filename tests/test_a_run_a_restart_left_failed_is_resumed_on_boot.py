"""A run an earlier recovery left failed, its resume lost, is resumed when a worker starts (plan OP.1).

After every host restart the operator resumed such runs by hand: recovery marks
an abandoned run failed and resumes it, and when that resume was lost no sweep
looked at a failed row again. A paused run is someone's decision and is never touched.
"""

from __future__ import annotations

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


def test_the_words_recovery_writes_are_the_words_the_boot_sweep_reads():
    from app.server import manage

    for oom_killed in (False, True):
        written = manage._the_words_recovery_writes(oom_killed)
        assert runs_a_restart_left_failed([_run("run-a", "failed", written)]) == ["run-a"]


def test_the_startup_sweep_resumes_them(monkeypatch):
    """The run store (no database here) and the queue are stood in for; the sweep itself runs."""
    from app.server import manage, tasks

    stopped = manage._the_words_recovery_writes(False)
    rows = [_run("run-a", "failed", stopped), _run("run-c", "failed", "The acceptance suite cannot run")]
    queued = []
    monkeypatch.setattr(tasks, "_SWEEP_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(tasks, "_SECOND_SWEEP_DELAY_SECONDS", 0)
    monkeypatch.setattr(manage, "_live_task_ids", lambda: set())
    monkeypatch.setattr(manage, "recover_orphaned_runs", lambda **kwargs: 0)
    monkeypatch.setattr("app.server.run_store.RunStore.shared",
                        classmethod(lambda cls: SimpleNamespace(list_all=lambda limit=500: rows)))
    monkeypatch.setattr(manage, "_worker_ran_out_of_memory", lambda: False)
    monkeypatch.setattr(manage, "_resume_one", queued.append)
    monkeypatch.setattr(manage, "_RESUMED_ON_START", {})

    tasks._sweep_for_abandoned_runs()

    assert queued == ["run-a"]
