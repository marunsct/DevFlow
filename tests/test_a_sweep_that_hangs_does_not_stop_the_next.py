"""A sweep pass that never returns does not stop the passes after it, nor the recurring sweep after the start-time one.

Measured: after a worker restart the orphan-sweep thread sat in a socket read from the moment the worker started, so
neither the start-time sweep nor the 90-second one ever ran, and two runs whose tasks the restart had ended read
`running` with nothing executing until they were recovered by hand, about 18 minutes later.
"""
from __future__ import annotations

import threading

import pytest


@pytest.fixture(autouse=True)
def _leave_no_redis_client_behind():
    from app.server import redis_client
    yield
    try:
        redis_client.reset_clients()
    except Exception:  # noqa: BLE001
        pass


class _Client:
    def set(self, *args, **kwargs):
        return True


def test_a_pass_that_hangs_is_left_and_the_next_one_runs(monkeypatch):
    from app.server import manage, tasks

    release = threading.Event()
    calls: list[int] = []

    def recover(**kwargs):
        calls.append(1)
        if len(calls) == 1:
            release.wait(30)  # the first pass never answers

    monkeypatch.setattr(manage, "recover_orphaned_runs", recover)
    monkeypatch.setattr("app.server.redis_client.get_redis_client", lambda: _Client())
    monkeypatch.setattr(tasks, "_SWEEP_PASS_DEADLINE_SECONDS", 0.2)
    rounds = iter([False, False, False, True])
    worker = threading.Thread(target=lambda: tasks._keep_sweeping(sleep=lambda s: None, stop=lambda: next(rounds)),
                              daemon=True)
    worker.start()
    worker.join(5)
    release.set()

    assert not worker.is_alive()
    assert len(calls) == 3


def test_a_start_time_sweep_that_hangs_still_lets_the_recurring_one_start(monkeypatch):
    from app.server import tasks

    release = threading.Event()
    started: list[int] = []
    monkeypatch.setattr(tasks, "_sweep_for_abandoned_runs", lambda: release.wait(30))
    monkeypatch.setattr(tasks, "_keep_sweeping", lambda: started.append(1))
    monkeypatch.setattr(tasks, "_START_SWEEP_DEADLINE_SECONDS", 0.2)
    worker = threading.Thread(target=tasks._sweep_and_keep_sweeping, daemon=True)
    worker.start()
    worker.join(5)
    release.set()

    assert started == [1]


def test_the_worker_s_redis_client_never_waits_forever():
    from app.server import redis_client

    client = redis_client.get_redis_client()
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs.get("socket_timeout") and kwargs.get("socket_connect_timeout")
