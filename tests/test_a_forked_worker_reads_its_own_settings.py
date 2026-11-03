"""A worker process forked from another makes its own database connections and reads settings afresh.

Measured on one run: a new worker process inherited its parent's connection pool and settings caches. Its first read
failed on the parent's connection, it fell back to the inherited cache, which named a hosted model the settings had
long since left, and the run's first stage called that hosted API.
"""
from __future__ import annotations

import os

from app.server import auth, runtime_settings


def test_a_forked_process_does_not_use_its_parent_s_pool_and_leaves_it_open(monkeypatch):
    closed = []
    parent = type("Pool", (), {"closeall": lambda self: closed.append(True)})()
    made = []
    monkeypatch.setattr(auth, "_db_pool", parent)
    monkeypatch.setattr(auth, "_db_pool_owner", os.getpid() + 1)
    monkeypatch.setattr(auth.pool, "ThreadedConnectionPool", lambda *a, **k: made.append(a) or object())

    auth.init_db_pool()

    assert made and auth._db_pool is not parent and auth._db_pool_owner == os.getpid()
    assert not closed, "the parent's sessions are left to the parent"


def test_a_forked_process_does_not_answer_from_its_parent_s_settings(monkeypatch):
    monkeypatch.setattr(runtime_settings, "_cache", {"llm_provider": "anthropic"})
    monkeypatch.setattr(runtime_settings, "_cache_expires_at", float("inf"))
    monkeypatch.setattr(runtime_settings, "_cache_owner", os.getpid() + 1)
    monkeypatch.setattr(runtime_settings, "_read_overrides_from_db", lambda: {"llm_provider": "local"})

    assert runtime_settings.overrides()["llm_provider"] == "local"


def test_a_failed_first_read_in_a_forked_process_is_not_the_parent_s_settings(monkeypatch):
    monkeypatch.setattr(runtime_settings, "_cache", {"llm_provider": "anthropic"})
    monkeypatch.setattr(runtime_settings, "_cache_expires_at", 0.0)
    monkeypatch.setattr(runtime_settings, "_cache_owner", os.getpid() + 1)

    def unreachable():
        raise ConnectionError("server closed the connection unexpectedly")

    monkeypatch.setattr(runtime_settings, "_read_overrides_from_db", unreachable)

    assert "llm_provider" not in runtime_settings.overrides()
