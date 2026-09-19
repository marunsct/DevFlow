"""A run a restart abandoned is recovered, and then nothing reaches it.

`recover_orphaned_runs` marks such a run `failed`, which is exactly what
makes it reachable again - `resume_run` compare-and-sets from `failed`. But
nothing called resume, so every worker restart left a correctly-diagnosed run
sitting still until an operator typed something.

Measured over one session's own work on 2026-09-19: four worker restarts,
four runs correctly recovered, four manual resume calls to carry each one
forward. A deploy is not an exceptional event here - it happens on every
configuration change and every code change - and a run lasts hours.

The three safety properties, each tested below:

* nothing is resumed unless `recover_orphaned_runs` first established that no
  worker claims the task;
* a run is resumed at most once per worker process, so a run that kills its
  worker every time costs one repeat rather than an unbounded number;
* an OOM-killed worker resumes nothing, because the cause is the run's own
  memory use and restarting repeats the kill.
"""

from __future__ import annotations

import pytest

from app.server import manage


@pytest.fixture(autouse=True)
def _forget_what_was_resumed():
    manage._RESUMED_ON_START.clear()
    yield
    manage._RESUMED_ON_START.clear()


def test_the_runner_this_calls_is_the_one_that_exists():
    """The regression that reached the worker log and not the suite.

    The first version called `WorkflowRunner.shared()`. There is no such
    method: the runner is built per worker process by
    `tasks._init_worker_process` and handed out by `tasks._get_runner`. The
    unit test supplied a double that had `shared`, so the double was the only
    place the method existed, and every test passed while the deploy logged
    `AttributeError: type object 'WorkflowRunner' has no attribute 'shared'`.

    So this asserts against the real modules, with nothing patched: the name
    this code reaches for has to be there, and it has to be callable with no
    arguments and return something that can resume a run.
    """
    from app.server.runner import WorkflowRunner
    from app.server.tasks import _get_runner

    assert callable(_get_runner)
    assert hasattr(WorkflowRunner, "resume_run")
    assert not hasattr(WorkflowRunner, "shared"), (
        "if this is ever added, prefer it - but the code must match the code"
    )


@pytest.fixture
def resumed(monkeypatch):
    """Record which runs were handed to the runner, without a runner."""
    seen: list[str] = []

    def _resume_one(run_id: str) -> None:
        seen.append(run_id)

    monkeypatch.setattr(manage, "_resume_one", _resume_one)
    monkeypatch.setattr(manage, "_worker_ran_out_of_memory", lambda: False)
    monkeypatch.delenv("RESUME_ORPHANS_ON_START", raising=False)
    return seen


def test_a_recovered_run_is_put_back_on_the_queue(resumed):
    assert manage.resume_runs_a_restart_abandoned(["run-a", "run-b"]) == 2
    assert resumed == ["run-a", "run-b"]


def test_a_run_is_resumed_once_however_often_its_worker_dies(resumed):
    """A crash loop costs one repeat, not an unbounded number."""
    manage.resume_runs_a_restart_abandoned(["run-a"])

    assert manage.resume_runs_a_restart_abandoned(["run-a"]) == 0
    assert resumed == ["run-a"]


def test_an_out_of_memory_worker_resumes_nothing(resumed, monkeypatch):
    """Restarting repeats the kill, and the operator needs to see the message."""
    monkeypatch.setattr(manage, "_worker_ran_out_of_memory", lambda: True)

    assert manage.resume_runs_a_restart_abandoned(["run-a"]) == 0
    assert resumed == []


@pytest.mark.parametrize("setting", ["0", "false", "no", "off", "FALSE", " Off "])
def test_an_operator_can_turn_it_off(resumed, monkeypatch, setting: str):
    monkeypatch.setenv("RESUME_ORPHANS_ON_START", setting)

    assert manage.resume_runs_a_restart_abandoned(["run-a"]) == 0
    assert resumed == []


def test_one_run_that_cannot_resume_does_not_block_the_rest(resumed, monkeypatch):
    def _resume_one(run_id: str) -> None:
        if run_id == "run-a":
            raise RuntimeError("the model server is down")
        resumed.append(run_id)

    monkeypatch.setattr(manage, "_resume_one", _resume_one)

    assert manage.resume_runs_a_restart_abandoned(["run-a", "run-b"]) == 1
    assert resumed == ["run-b"]


def test_nothing_is_resumed_when_no_worker_answered(monkeypatch):
    """The safety property the whole sweep rests on, end to end.

    `_live_task_ids` returning None means "cannot tell", not "nothing is
    running". `recover_orphaned_runs` stops there, so nothing is recovered and
    therefore nothing is resumed.
    """
    called: list[str] = []
    monkeypatch.setattr(manage, "_live_task_ids", lambda: None)
    monkeypatch.setattr(
        manage, "resume_runs_a_restart_abandoned", lambda ids: called.extend(ids)
    )

    assert manage.recover_orphaned_runs(dry_run=False) == 1
    assert called == []


def test_a_dry_run_resumes_nothing(monkeypatch):
    called: list[str] = []
    monkeypatch.setattr(manage, "_live_task_ids", lambda: set())
    monkeypatch.setattr(manage, "_worker_ran_out_of_memory", lambda: False)
    monkeypatch.setattr(
        manage, "resume_runs_a_restart_abandoned", lambda ids: called.extend(ids)
    )

    class _Record:
        run_id = "run-a"
        status = "running"
        task_id = "gone"
        current_stage = "test_round_0"
        error = None
        updated_at = ""

    class _Store:
        @staticmethod
        def shared():
            return _Store()

        @staticmethod
        def list_all(limit: int = 500, offset: int = 0):
            return [_Record()] if offset == 0 else []

    import app.server.run_store as run_store

    monkeypatch.setattr(run_store, "RunStore", _Store)

    manage.recover_orphaned_runs(dry_run=True)

    assert called == []
