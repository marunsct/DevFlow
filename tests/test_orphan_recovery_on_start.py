"""A run whose worker died must not stay `running` until someone notices.

A run is handed to one Celery task and the row says `running` for as long as
that task lives. `task_acks_late=False`, so a worker that dies mid-task never
has the task redelivered: nothing writes a terminal status and the row says
`running` for ever. `resume_run` compare-and-sets from `failed` and refuses,
and `reconcile-runs` deliberately leaves unattended runs alone, so nothing can
reach the work - which is all still on disk, because the graph checkpoints at
every node boundary.

`recover_orphaned_runs` already fixed that, as a command an operator has to
remember to type. Nothing called it. Measured on 2026-09-19 against the live
database: of the forty most recent failed runs, twenty carried "The worker
running this stage stopped without finishing", and one run had sat at
`running` for eight hours after its container was replaced, reporting healthy
to every caller that asked.

A worker restart is not exceptional here - it happens on every deploy, every
OOM and every configuration change, against runs that last hours.
"""

from __future__ import annotations

import pytest

from app.server import tasks


def test_a_worker_becoming_ready_recovers_abandoned_runs(monkeypatch):
    called: list[bool] = []

    class _Lock:
        def set(self, *_args, **_kwargs):
            return True

    monkeypatch.setattr("app.server.redis_client.get_redis_client", lambda: _Lock())
    monkeypatch.setattr(
        "app.server.manage.recover_orphaned_runs",
        lambda dry_run=False: called.append(dry_run) or 0,
    )

    tasks._recover_runs_their_worker_abandoned()

    assert called == [False], "recovery did not run, or ran as a dry run"


def test_only_one_worker_sweeps_per_restart(monkeypatch):
    """Several workers come up together on every deploy."""
    called: list[bool] = []

    class _TakenLock:
        def set(self, *_args, **_kwargs):
            return False

    monkeypatch.setattr("app.server.redis_client.get_redis_client", lambda: _TakenLock())
    monkeypatch.setattr(
        "app.server.manage.recover_orphaned_runs",
        lambda dry_run=False: called.append(dry_run) or 0,
    )

    tasks._recover_runs_their_worker_abandoned()

    assert called == [], "a second worker repeated the sweep"


def test_recovery_can_be_switched_off(monkeypatch):
    called: list[bool] = []
    monkeypatch.setenv("RECOVER_ORPHANS_ON_START", "false")
    monkeypatch.setattr(
        "app.server.manage.recover_orphaned_runs",
        lambda dry_run=False: called.append(dry_run) or 0,
    )

    tasks._recover_runs_their_worker_abandoned()

    assert called == []


@pytest.mark.parametrize("boom", [RuntimeError("redis down"), OSError("no socket")])
def test_a_worker_still_starts_when_recovery_fails(monkeypatch, boom):
    """A worker that cannot run this must still accept tasks."""
    def _raise():
        raise boom

    monkeypatch.setattr("app.server.redis_client.get_redis_client", _raise)

    tasks._recover_runs_their_worker_abandoned()  # must not raise


def test_a_failing_sweep_does_not_propagate(monkeypatch):
    class _Lock:
        def set(self, *_args, **_kwargs):
            return True

    def _explode(dry_run=False):
        raise RuntimeError("database unreachable")

    monkeypatch.setattr("app.server.redis_client.get_redis_client", lambda: _Lock())
    monkeypatch.setattr("app.server.manage.recover_orphaned_runs", _explode)

    tasks._recover_runs_their_worker_abandoned()  # must not raise


def test_the_handler_is_connected_to_worker_ready():
    """Wiring is the whole fix; the function already existed and was never called."""
    from celery.signals import worker_ready

    receivers = [r() for _, r in worker_ready.receivers]
    names = {getattr(r, "__name__", "") for r in receivers if r is not None}

    assert "_recover_runs_their_worker_abandoned" in names, (
        "the recovery function exists but nothing calls it - which was the bug"
    )


def test_late_acknowledgement_stays_off():
    """The premise: a dead worker's task is never redelivered.

    If `task_acks_late` were turned on, the broker would redeliver and this
    recovery would race with it, putting two writers on one thread.
    """
    assert tasks.celery_app.conf.task_acks_late is False
    assert tasks.celery_app.conf.task_reject_on_worker_lost is False
