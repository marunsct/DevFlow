"""A rewind waits until no worker task still drives the run (harness review R1, cause found 2026-11-07).

Measured: a paused run was rewound while its worker was inside a model call; the call returned nine seconds later,
the stage wrote its checkpoint over the rewind's, and the resumed run carried on from the abandoned branch.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.server import driving
from app.server.runner import RunConflict, WorkflowRunner


class FakeRedis:
    def __init__(self):
        self.keys = {}

    def set(self, key, value, ex=None):
        self.keys[key] = value

    def expire(self, key, seconds):
        return key in self.keys

    def delete(self, key):
        self.keys.pop(key, None)

    def exists(self, key):
        return int(key in self.keys)


def test_a_driven_run_is_held_and_released():
    redis = FakeRedis()
    with driving.driving("run-1", client=redis):
        assert driving.held("run-1", client=redis)
        assert driving.wait_until_free("run-1", seconds=0.05, client=redis, poll=0.01) is False
    assert not driving.held("run-1", client=redis)
    assert driving.wait_until_free("run-1", seconds=0.05, client=redis, poll=0.01) is True


def test_a_rewind_of_a_run_still_driven_is_refused(monkeypatch):
    monkeypatch.setattr(driving, "wait_until_free", lambda run_id, **_: False)
    runner = SimpleNamespace(run_store=SimpleNamespace(load=lambda run_id: SimpleNamespace(status="paused")))
    with pytest.raises(RunConflict, match="still finishing"):
        asyncio.run(WorkflowRunner.rewind_run(runner, "run-1", "checkpoint-1"))


def test_the_worker_task_holds_the_run_while_it_drives_it():
    import inspect

    from app.server import tasks

    source = inspect.getsource(tasks.execute_workflow_run)
    assert "driving(run_id)" in source and source.index("driving(run_id)") < source.index("runner._run_loop")
