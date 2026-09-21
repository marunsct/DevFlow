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


@pytest.fixture(autouse=True)
def _leave_no_redis_client_behind():
    """Reset the cached Redis pool this module's patches can leave pointing home.

    `app.server.redis_client` caches a client per process. Touching it here -
    even through a monkeypatch that is later undone - can leave a pool aimed
    at `localhost:6379`, which is not where Redis is under the test
    containers. Every later test that needs Redis then fails with
    `Connection refused`, and the failure looks like it belongs to that test.

    Measured on 2026-09-19: adding this module took the suite from 4 failures
    to 19, all of them in files that run after it and none of them broken.
    """
    from app.server import redis_client

    yield
    try:
        redis_client.reset_clients()
    except Exception:  # noqa: BLE001 - cleanup must not fail a passing test
        pass


@pytest.fixture()
def tasks():
    """Imported per test, never at module scope, for the same reason."""
    from app.server import tasks as module

    return module


def test_a_worker_becoming_ready_starts_the_sweep(monkeypatch, tasks):
    started: list[str] = []

    class _Lock:
        def set(self, *_args, **_kwargs):
            return True

    monkeypatch.setattr("app.server.redis_client.get_redis_client", lambda: _Lock())
    monkeypatch.setattr(
        tasks.threading if hasattr(tasks, "threading") else __import__("threading"),
        "Thread",
        lambda **kw: type("T", (), {"start": lambda self: started.append(kw.get("name", ""))})(),
    )

    tasks._recover_runs_their_worker_abandoned()

    assert started == ["orphan-sweep"]


def test_the_sweep_waits_until_the_broker_can_answer(monkeypatch, tasks):
    """`worker_ready` fires before this worker can answer about itself.

    Measured on the deploy at 04:36: the first version ran the sweep inline
    and was told "No worker answered, so nothing can be judged orphaned.
    Nothing changed." The safety property held and the feature did not exist.
    """
    answers = [None, None, {"abc"}]
    called: list[bool] = []

    monkeypatch.setattr(tasks, "_SWEEP_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(tasks, "_SECOND_SWEEP_DELAY_SECONDS", 0)
    monkeypatch.setattr("app.server.manage._live_task_ids", lambda: answers.pop(0))
    monkeypatch.setattr(
        "app.server.manage.recover_orphaned_runs",
        lambda dry_run=False, emit=print, grace_seconds=0: called.append(dry_run) or 0,
    )

    tasks._sweep_for_abandoned_runs()

    # Two passes, not one. A run inside the recency grace on the first pass has
    # to be judged once it leaves the window, or it stays `running` for ever -
    # see `RECENTLY_TOUCHED_SECONDS`.
    assert called == [False, False], "the sweep gave up before the broker answered"


def test_the_sweep_gives_up_rather_than_guessing(monkeypatch, tasks):
    """"Cannot tell" must never become "nothing is running"."""
    called: list[bool] = []

    monkeypatch.setattr(tasks, "_SWEEP_INTERVAL_SECONDS", 0)
    monkeypatch.setattr("app.server.manage._live_task_ids", lambda: None)
    monkeypatch.setattr(
        "app.server.manage.recover_orphaned_runs",
        lambda dry_run=False, emit=print: called.append(dry_run) or 0,
    )

    tasks._sweep_for_abandoned_runs()

    assert called == [], "a silent broker must repair nothing"


def test_a_failing_sweep_never_takes_the_worker_down(monkeypatch, tasks):
    monkeypatch.setattr(tasks, "_SWEEP_INTERVAL_SECONDS", 0)
    monkeypatch.setattr("app.server.manage._live_task_ids", lambda: {"x"})

    def _explode(dry_run=False, emit=print):
        raise RuntimeError("database unreachable")

    monkeypatch.setattr("app.server.manage.recover_orphaned_runs", _explode)

    tasks._sweep_for_abandoned_runs()  # must not raise


def test_only_one_worker_sweeps_per_restart(monkeypatch, tasks):
    """Several workers come up together on every deploy."""
    called: list[bool] = []

    class _TakenLock:
        def set(self, *_args, **_kwargs):
            return False

    monkeypatch.setattr("app.server.redis_client.get_redis_client", lambda: _TakenLock())
    monkeypatch.setattr(
        "app.server.manage.recover_orphaned_runs",
        lambda dry_run=False, emit=print: called.append(dry_run) or 0,
    )

    tasks._recover_runs_their_worker_abandoned()

    assert called == [], "a second worker repeated the sweep"


def test_recovery_can_be_switched_off(monkeypatch, tasks):
    called: list[bool] = []
    monkeypatch.setenv("RECOVER_ORPHANS_ON_START", "false")
    monkeypatch.setattr(
        "app.server.manage.recover_orphaned_runs",
        lambda dry_run=False, emit=print: called.append(dry_run) or 0,
    )

    tasks._recover_runs_their_worker_abandoned()

    assert called == []


@pytest.mark.parametrize("boom", [RuntimeError("redis down"), OSError("no socket")])
def test_a_worker_still_starts_when_recovery_fails(monkeypatch, boom, tasks):
    """A worker that cannot run this must still accept tasks."""
    def _raise():
        raise boom

    monkeypatch.setattr("app.server.redis_client.get_redis_client", _raise)

    tasks._recover_runs_their_worker_abandoned()  # must not raise




def test_the_handler_is_connected_to_worker_ready(tasks):
    """Wiring is the whole fix; the function already existed and was never called."""
    from celery.signals import worker_ready

    receivers = [r() for _, r in worker_ready.receivers]
    names = {getattr(r, "__name__", "") for r in receivers if r is not None}

    assert "_recover_runs_their_worker_abandoned" in names, (
        "the recovery function exists but nothing calls it - which was the bug"
    )


def test_late_acknowledgement_stays_off(tasks):
    """The premise: a dead worker's task is never redelivered.

    If `task_acks_late` were turned on, the broker would redeliver and this
    recovery would race with it, putting two writers on one thread.
    """
    assert tasks.celery_app.conf.task_acks_late is False
    assert tasks.celery_app.conf.task_reject_on_worker_lost is False
