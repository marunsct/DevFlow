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


def test_the_specification_s_parts_are_recorded_as_the_run_s(monkeypatch):
    # Measured on one gate run: the parts were written for six minutes with
    # nothing in the transcript, and the run read "neither model nor tool busy".
    import json as _json

    from pydantic import BaseModel

    from app.graph import specification_parts

    class Spec(BaseModel):
        overview: str = "x"
        file_plan: list[str] = []

    class _Writer(_Model):
        def invoke(self, messages, config=None):
            self.configs.append(config)
            return SimpleNamespace(content=_json.dumps({"file_plan": ["app/main.py"]}))

    monkeypatch.setattr("app.server.agent_stream.build_activity_callbacks", lambda run, stage: [f"{run}:{stage}"])
    monkeypatch.setattr(specification_parts, "PARTS", (("file_plan",),))
    monkeypatch.setattr("app.agents.thinking.without_reasoning", lambda model: model)
    model = _Writer()
    token = _TASK_RUN.set("run-abc")
    try:
        written = specification_parts.with_the_parts_written(Spec(), model, "")
    finally:
        _TASK_RUN.reset(token)

    assert written.file_plan == ["app/main.py"]
    assert model.configs == [{"callbacks": ["run-abc:principal_architect"]}]


def test_every_direct_model_call_in_the_source_is_recorded():
    import re

    root = Path(__file__).resolve().parent.parent / "src" / "app"
    # Probes and a health check run outside any run, where nothing is recorded.
    outside_a_run = {"models/fitness.py", "models/router.py", "agents/thinking.py"}
    unrecorded = []
    for path in root.rglob("*.py"):
        relative = path.relative_to(root).as_posix()
        if relative in outside_a_run:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for at, line in enumerate(lines):
            if line.lstrip().startswith("#") or not re.search(r"\.invoke\(", line):
                continue
            if re.search(r"\b(?:agent|graph)\.invoke\(|`[^`]*\.invoke\(", line):
                continue
            statement = "\n".join(lines[at:at + 8])
            if "config_for_this_run" not in statement and "**recorded" not in statement:
                unrecorded.append(f"{relative}:{at + 1}")
    assert not unrecorded, unrecorded
