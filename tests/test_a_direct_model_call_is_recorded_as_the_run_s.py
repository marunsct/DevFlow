"""A model call made outside an agent loop - a drafted file, a rewritten fix - is recorded as the run's.

Measured on one gate run: 61 drafted files and every rewrite were missing from
the transcript, the cost and the activity stream, so the run's KPIs counted 16
build calls and "neither model nor tool busy" 40% of the time; and the pool
threads that made them named their run "none" at the call gate.
"""
from __future__ import annotations

import contextvars
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from app.observability import direct_calls
from app.observability.log_context import _TASK_RUN


class _Model:
    def __init__(self):
        self.configs = []

    def invoke(self, messages, config=None):
        self.configs.append(config)
        return SimpleNamespace(content="```\nx = 1\n```")


def test_a_drafted_file_s_call_carries_the_run_s_callbacks(tmp_path, monkeypatch):
    from app.graph import drafting

    monkeypatch.setattr("app.server.agent_stream.build_activity_callbacks", lambda run, stage: [f"{run}:{stage}"])
    monkeypatch.setattr(drafting, "draft_request", lambda *a, **k: "write it")
    model = _Model()
    token = _TASK_RUN.set("run-abc")
    try:
        drafting._draft_one(model, Path(tmp_path), "app.py", SimpleNamespace(), None, None)
    finally:
        _TASK_RUN.reset(token)

    assert model.configs == [{"callbacks": ["run-abc:drafting"]}]


def test_outside_a_run_a_call_carries_nothing():
    assert direct_calls.config_for_this_run("drafting") == {}


def test_a_pool_thread_sees_the_caller_s_run():
    seen = contextvars.ContextVar("seen", default="none")
    token = seen.set("run-abc")
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            got = direct_calls.mapped_in_this_context(pool, lambda n: (n, seen.get()), [1, 2, 3])
    finally:
        seen.reset(token)

    assert got == [(1, "run-abc"), (2, "run-abc"), (3, "run-abc")]
