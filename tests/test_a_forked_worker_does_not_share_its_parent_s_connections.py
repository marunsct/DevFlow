"""A process forked after a pool was built must not use or close that pool.

The Celery parent built a runner (and its checkpointer pool) when the orphan
sweep resumed a run. A pool process forked later inherited the pool's sockets,
both processes spoke over them, and the server dropped a connection mid-run:
"consuming input failed: server closed the connection unexpectedly".
"""
from __future__ import annotations

import json
import os

import pytest

from app.server.process_local import PerProcess, owned_here

pytestmark = pytest.mark.skipif(not hasattr(os, "fork"), reason="needs fork()")


def _in_a_child(body) -> dict:
    """Run `body` in a forked child and return what it reported."""
    read, write = os.pipe()
    pid = os.fork()
    if pid == 0:  # pragma: no cover - the child reports through the pipe
        os.close(read)
        try:
            result = body()
        except BaseException as exc:  # noqa: BLE001
            result = {"error": repr(exc)}
        os.write(write, json.dumps(result).encode())
        os.close(write)
        os._exit(0)
    os.close(write)
    chunks = []
    while chunk := os.read(read, 65536):
        chunks.append(chunk)
    os.close(read)
    os.waitpid(pid, 0)
    return json.loads(b"".join(chunks))


def test_a_child_builds_its_own_value_instead_of_the_parent_s():
    holder: PerProcess[object] = PerProcess()
    parent_value = holder.get(object)

    def body():
        mine = holder.get(object)
        return {"same": mine is parent_value, "again": holder.get(object) is mine}

    report = _in_a_child(body)
    assert report == {"same": False, "again": True}
    assert holder.get(object) is parent_value


def test_a_child_is_never_handed_the_parent_s_value_to_close():
    holder: PerProcess[object] = PerProcess()
    holder.get(object)

    def body():
        return {"mine": holder.mine() is not None, "take": holder.take() is not None}

    assert _in_a_child(body) == {"mine": False, "take": False}
    assert holder.mine() is not None


def test_owned_here_names_only_this_process():
    assert owned_here(os.getpid())
    assert not owned_here(None)
    assert not owned_here(os.getpid() + 1)


def test_the_checkpointer_pool_is_rebuilt_in_a_forked_worker(monkeypatch):
    import app.graph.checkpointing as checkpointing

    built = []

    class _Pool:
        def __init__(self, **kwargs):
            built.append(os.getpid())

    monkeypatch.setattr(checkpointing, "ConnectionPool", _Pool)
    monkeypatch.setattr(checkpointing, "_pool", PerProcess())
    parent_pool = checkpointing.get_connection_pool()
    assert checkpointing.get_connection_pool() is parent_pool

    def body():
        return {"same": checkpointing.get_connection_pool() is parent_pool}

    assert _in_a_child(body) == {"same": False}


@pytest.mark.parametrize("module, name", [
    ("app.server.run_store", "RunStore"),
    ("app.server.plugin_store", "PluginStore"),
])
def test_a_shared_store_is_per_process(monkeypatch, module, name):
    import importlib

    cls = getattr(importlib.import_module(module), name)
    closed = []

    def _init(self, db_url=None):
        self.pid = os.getpid()

    monkeypatch.setattr(cls, "__init__", _init)
    monkeypatch.setattr(cls, "close", lambda self: closed.append(os.getpid()), raising=False)
    monkeypatch.setattr(cls, "_shared", None)
    monkeypatch.setattr(cls, "_shared_owner", None)
    parent_store = cls.shared()
    assert cls.shared() is parent_store

    def body():
        child_store = cls.shared()
        return {"same": child_store is parent_store, "built_here": child_store.pid == os.getpid()}

    assert _in_a_child(body) == {"same": False, "built_here": True}


def test_resetting_an_inherited_run_store_does_not_close_the_parent_s(monkeypatch):
    from app.server.run_store import RunStore

    def _init(self, db_url=None):
        self.pid = os.getpid()

    closes = []
    monkeypatch.setattr(RunStore, "__init__", _init)
    monkeypatch.setattr(RunStore, "close", lambda self: closes.append(os.getpid()))
    monkeypatch.setattr(RunStore, "_shared", None)
    monkeypatch.setattr(RunStore, "_shared_owner", None)
    RunStore.shared()

    def body():
        RunStore.reset_shared()
        return {"closed_in_child": bool(closes)}

    assert _in_a_child(body) == {"closed_in_child": False}
    RunStore.reset_shared()
    assert closes == [os.getpid()]


def test_the_worker_runner_is_rebuilt_in_a_forked_worker(monkeypatch):
    from app.server import tasks

    def _init(**_kwargs):
        tasks._runner = object()
        tasks._runner_owner = os.getpid()

    monkeypatch.setattr(tasks, "_init_worker_process", _init)
    monkeypatch.setattr(tasks, "_runner", None)
    monkeypatch.setattr(tasks, "_runner_owner", None)
    parent_runner = tasks._get_runner()
    assert tasks._get_runner() is parent_runner

    def body():
        return {"same": tasks._get_runner() is parent_runner}

    assert _in_a_child(body) == {"same": False}
