"""A running row whose task is gone is found between worker restarts, not only at the next one.

Measured on one run: Celery's pool process was OOM-killed mid-stage; the row sat `running` for 14 minutes, until a
deploy's restart ran the start-time sweep. Nothing had looked at running rows in between.
"""
from __future__ import annotations

import inspect

import pytest


@pytest.fixture(autouse=True)
def _leave_no_redis_client_behind():
    from app.server import redis_client
    yield
    try:
        redis_client.reset_clients()
    except Exception:  # noqa: BLE001
        pass


def test_the_recurring_sweep_calls_the_guarded_recovery_under_a_lock(monkeypatch):
    from app.server import manage, tasks

    calls: list[float] = []
    monkeypatch.setattr(manage, "recover_orphaned_runs", lambda **kw: calls.append(kw["grace_seconds"]))
    answers = iter([True, False, True])

    class Client:
        def set(self, key, value, nx=False, ex=None):
            assert key == tasks._RECURRING_LOCK_KEY and nx and ex
            return next(answers)

    monkeypatch.setattr("app.server.redis_client.get_redis_client", lambda: Client())
    slept: list[float] = []
    rounds = iter([False, False, False, True])
    tasks._keep_sweeping(sleep=slept.append, stop=lambda: next(rounds))

    assert slept == [tasks._RECURRING_SWEEP_SECONDS] * 3
    assert calls == [manage.RECENTLY_TOUCHED_SECONDS] * 2, "swept when the lock was taken, skipped when it was not"


def test_a_failing_sweep_keeps_going(monkeypatch):
    from app.server import manage, tasks

    monkeypatch.setattr("app.server.redis_client.get_redis_client", lambda: (_ for _ in ()).throw(RuntimeError("down")))
    rounds = iter([False, False, True])
    tasks._keep_sweeping(sleep=lambda s: None, stop=lambda: next(rounds))  # must not raise


def test_the_start_time_sweep_thread_keeps_sweeping():
    from app.server import tasks

    source = inspect.getsource(tasks)
    assert 'target=_sweep_and_keep_sweeping, name="orphan-sweep"' in source
    assert "_sweep_for_abandoned_runs()\n    _keep_sweeping()" in inspect.getsource(tasks._sweep_and_keep_sweeping)
