"""A run is refused before its first model call when the workers cannot run commands.

Execution is opt-in and Compose leaves it off, so a deployment could accept a
run that can write a product but never install, build or test it - and only
the start checked that a model answered.
"""

from __future__ import annotations

import asyncio
import subprocess

import pytest

from app.server.execution_readiness import (
    READINESS_KEY,
    readiness_record,
    record_this_workers_readiness,
    why_commands_cannot_run,
)
from app.server.runner import RunConflict, WorkflowRunner
from app.tools import sandbox
from app.tools.sandbox import execution_readiness


def test_execution_turned_off_is_not_ready_and_names_the_setting(monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "false")
    ready, detail = execution_readiness()
    assert not ready and "ALLOW_COMMAND_EXECUTION" in detail


def test_running_in_the_workers_own_container_is_ready(monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "in-container")
    assert execution_readiness()[0]


def test_container_mode_without_a_runtime_is_not_ready(monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "container")
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: None)
    ready, detail = execution_readiness()
    assert not ready and "SANDBOX_EXECUTION_MODE=in-container" in detail


def test_container_mode_whose_daemon_does_not_answer_is_not_ready(monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "container")
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        sandbox.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "Cannot connect to the Docker daemon\nmore"),
    )
    ready, detail = execution_readiness()
    assert not ready and "Cannot connect to the Docker daemon" in detail and "more" not in detail


def test_container_mode_whose_daemon_answers_is_ready(monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "container")
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(sandbox.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "27.0", ""))
    assert execution_readiness()[0]


def test_only_a_record_that_says_not_ready_refuses() -> None:
    assert why_commands_cannot_run(None) is None
    assert why_commands_cannot_run("not json") is None
    assert why_commands_cannot_run('["a list"]') is None
    assert why_commands_cannot_run(readiness_record(True, "fine")) is None
    assert why_commands_cannot_run(readiness_record(False, "turned off")) == "turned off"


class _Store:
    def __init__(self, value=None, fail=False) -> None:
        self.value, self.fail, self.written = value, fail, {}

    def set(self, key, value):
        if self.fail:
            raise ConnectionError("down")
        self.written[key] = value

    async def get(self, key):
        if self.fail:
            raise ConnectionError("down")
        return self.value


def test_a_worker_records_what_it_found(monkeypatch) -> None:
    monkeypatch.setattr(sandbox, "execution_readiness", lambda: (False, "turned off"))
    store = _Store()
    record_this_workers_readiness(store)
    assert why_commands_cannot_run(store.written[READINESS_KEY]) == "turned off"


def test_a_worker_that_cannot_record_still_starts() -> None:
    record_this_workers_readiness(_Store(fail=True))


def test_the_worker_records_it_when_it_comes_up(monkeypatch) -> None:
    from app.server import redis_client, tasks

    store = _Store()
    monkeypatch.setattr(redis_client, "get_redis_client", lambda: store)
    monkeypatch.setattr(sandbox, "execution_readiness", lambda: (True, "fine"))
    tasks._record_whether_commands_can_run()
    assert READINESS_KEY in store.written


@pytest.mark.real_execution_readiness
@pytest.mark.parametrize(
    ("store", "refused"),
    [
        (_Store(readiness_record(False, "Command execution is turned off")), True),
        (_Store(readiness_record(True, "fine")), False),
        (_Store(None), False),
        (_Store(fail=True), False),
    ],
)
def test_the_runner_refuses_only_on_a_record_of_not_ready(monkeypatch, store, refused) -> None:
    from app.server import redis_client

    monkeypatch.setattr(redis_client, "get_async_redis_client", lambda: store)
    check = WorkflowRunner._require_command_execution(object())
    if refused:
        with pytest.raises(RunConflict, match="turned off"):
            asyncio.run(check)
    else:
        asyncio.run(check)


def test_start_and_resume_both_check_before_dispatching() -> None:
    import inspect

    for method in (WorkflowRunner.start_run, WorkflowRunner.resume_run):
        source = inspect.getsource(method)
        assert source.index("_require_command_execution") < source.index("_dispatch(")
