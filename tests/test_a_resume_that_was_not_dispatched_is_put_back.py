"""A resume whose dispatch failed puts the run back as it was, rather than leaving it `running` with no task.

Found in review: `resume_run` compare-and-sets the row from its resumable
status to `running` and only then hands it to Celery. When the hand-off
raised - the broker did not answer, or every run slot was taken - the row read
`running` under the previous, finished task's id. Nothing drove it, a second
resume was refused ("not in one of the states a run resumes from"), and only
the orphan sweep, a minute and more later, moved it again. A run recovery had
marked also lost the words a starting worker looks for to resume it.
"""

from __future__ import annotations

import pytest

from app.server.events import EventBus
from app.server.manage import STOPPED_WORKER_MARKER
from app.server.runner import RunQueueFull, WorkflowRunner


@pytest.fixture
def runner(run_store, redis_container, monkeypatch):
    from app.server.redis_client import reset_clients

    reset_clients()
    monkeypatch.setenv("CHECKPOINTER_TYPE", "memory")
    return WorkflowRunner(EventBus(), run_store=run_store)


def _register(runner, **overrides):
    record = runner.register_run(
        run_id="run-one", thread_id="thread-run-one", document_names=["brief.md"],
        document_paths=["/tmp/brief.md"], owner="alice", tenant_id="acme",
    )
    for key, value in overrides.items():
        setattr(record, key, value)
    runner.run_store.save(record)
    return record


def _a_broker_that_does_not_answer(monkeypatch, error: Exception) -> None:
    import app.server.tasks as tasks_module

    def delay(**_kwargs):
        raise error

    monkeypatch.setattr(tasks_module.execute_workflow_run, "delay", delay)


@pytest.mark.parametrize("error", [ConnectionError("Error 111 connecting to redis:6379"), RunQueueFull("1 of 1 run slots are in use")])
async def test_a_failed_run_whose_resume_was_not_dispatched_is_failed_again_with_its_words(runner, monkeypatch, error):
    stopped = f"{STOPPED_WORKER_MARKER} - the host or the container went away mid-task."
    _register(runner, status="failed", task_id="task-old", error=stopped)
    _a_broker_that_does_not_answer(monkeypatch, error)

    with pytest.raises(type(error)):
        await runner.resume_run("run-one")

    record = runner.run_store.load("run-one")
    assert record.status == "failed"
    assert record.error == stopped


async def test_a_paused_run_goes_back_to_paused(runner, monkeypatch):
    _register(runner, status="paused", task_id="task-old")
    _a_broker_that_does_not_answer(monkeypatch, ConnectionError("broker gone"))

    with pytest.raises(ConnectionError):
        await runner.resume_run("run-one")

    assert runner.run_store.load("run-one").status == "paused"
