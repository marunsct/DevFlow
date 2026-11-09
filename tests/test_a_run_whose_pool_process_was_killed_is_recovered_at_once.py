"""A run whose pool process was killed is marked and resumed when Celery says so, not at the next sweep.

Found in review: a pool process lost to the kernel's OOM killer or a SIGKILL
makes Celery's parent send `task_failure` with `WorkerLostError`, and
`handle_task_failure` only wrote the dead-letter list. The run's row read
`running` until the recurring orphan sweep next looked and judged it - up to
its 90 s period plus the 60 s a recently touched run is spared - and the run's
page said it was running all that time, with nothing driving it.

It is marked the way orphan recovery marks a run a stopped worker left
(`STOPPED_WORKER_MARKER`), so the same resume carries it on, and if that
resume is lost, a starting worker's `runs_a_restart_left_failed` finds it.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from celery.exceptions import TimeLimitExceeded, WorkerLostError

from app.server import manage


class _Store:
    def __init__(self, status: str = "running", task_id: str = "task-7"):
        self.record = SimpleNamespace(
            run_id="run-x", status=status, task_id=task_id, current_stage="engineering",
            error=None, updated_at=datetime.now(timezone.utc).isoformat(), cancel_requested=False,
        )
        self.moves: list[tuple] = []

    def load(self, run_id):
        return self.record

    def compare_and_set_status(self, run_id, expected, new_status, *, updated_at, error=None, **_):
        if self.record.status != expected:
            return False
        self.moves.append((run_id, expected, new_status))
        self.record.status, self.record.error, self.record.updated_at = new_status, error, updated_at
        return True


@pytest.fixture
def recovery(monkeypatch):
    """The store and the resumes `recover_a_run_whose_worker_was_lost` reaches, without a database."""
    from app.server import run_store

    store = _Store()
    resumed: list[list[str]] = []
    monkeypatch.setattr(run_store.RunStore, "shared", classmethod(lambda cls: store))
    monkeypatch.setattr(manage, "resume_runs_a_restart_abandoned", lambda ids: resumed.append(list(ids)) or len(ids))
    monkeypatch.setattr(manage, "_worker_ran_out_of_memory", lambda: False)
    monkeypatch.delenv("RECOVER_ORPHANS_ON_START", raising=False)
    return SimpleNamespace(store=store, resumed=resumed)


def test_a_running_run_whose_task_was_lost_is_marked_as_recovery_marks_it_and_resumed(recovery):
    assert manage.recover_a_run_whose_worker_was_lost("run-x", "task-7") is True

    assert recovery.store.moves == [("run-x", "running", "failed")]
    assert recovery.store.record.error.startswith(manage.STOPPED_WORKER_MARKER)
    assert recovery.resumed == [["run-x"]]


def test_a_lost_resume_is_found_by_the_next_worker_to_start(recovery):
    manage.recover_a_run_whose_worker_was_lost("run-x", "task-7")

    assert manage.runs_a_restart_left_failed([recovery.store.record]) == ["run-x"]


def test_a_run_a_newer_task_drives_is_left_alone(recovery):
    recovery.store.record.task_id = "task-8"

    assert manage.recover_a_run_whose_worker_was_lost("run-x", "task-7") is False
    assert recovery.store.moves == [] and recovery.resumed == []


@pytest.mark.parametrize("status", ["completed", "failed", "paused", "cancelled"])
def test_a_run_that_has_ended_is_left_as_it_ended(recovery, status):
    recovery.store.record.status = status

    assert manage.recover_a_run_whose_worker_was_lost("run-x", "task-7") is False
    assert recovery.store.moves == [] and recovery.resumed == []


def test_an_out_of_memory_kill_is_named_on_the_run(recovery, monkeypatch):
    monkeypatch.setattr(manage, "_worker_ran_out_of_memory", lambda: True)

    manage.recover_a_run_whose_worker_was_lost("run-x", "task-7")

    assert "OOM-killed" in recovery.store.record.error


def _fail(exception, monkeypatch, task_name="execute_workflow_run", expected=False):
    """`handle_task_failure` as Celery's parent calls it, with the recovery it starts recorded."""
    from app.server import redis_client, tasks

    class _Redis:
        def lpush(self, *args):
            pass

        def ltrim(self, *args):
            pass

    monkeypatch.setattr(redis_client, "get_redis_client", lambda: _Redis())
    called = threading.Event()
    seen: list[tuple] = []

    def recover(run_id, task_id):
        seen.append((run_id, task_id))
        called.set()
        return True

    monkeypatch.setattr(manage, "recover_a_run_whose_worker_was_lost", recover)
    tasks.handle_task_failure(
        sender=SimpleNamespace(name=task_name), task_id="task-7", exception=exception,
        args=[], kwargs={"run_id": "run-x", "resume": True},
    )
    called.wait(timeout=5 if expected else 0.5)
    return seen


@pytest.mark.parametrize("lost", [WorkerLostError("Worker exited prematurely: signal 9 (SIGKILL)"), TimeLimitExceeded(43500)])
def test_celery_reporting_a_lost_pool_process_recovers_its_run(monkeypatch, lost):
    assert _fail(lost, monkeypatch, expected=True) == [("run-x", "task-7")]


def test_a_task_that_raised_is_not_taken_for_a_lost_process(monkeypatch):
    assert _fail(RuntimeError("boom"), monkeypatch) == []


def test_another_task_s_lost_process_is_not_a_run(monkeypatch):
    assert _fail(WorkerLostError("signal 9"), monkeypatch, task_name="diagnose_the_model") == []
