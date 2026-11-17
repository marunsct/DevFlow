"""A stage thread left running after its run was paused or cancelled makes no more model calls in that process.

Measured on one run: after a pause, the paused stage's agent loop - in an executor thread the stopped task did not end -
kept calling the model for five minutes, beside the same run rewound in the other worker process, and could have
written into the workspace the rewind had just restored.
"""
from __future__ import annotations

import pytest

from app.models import call_gate as models
from app.graph import workflow
from app.server import runner


def _in_run(monkeypatch, run_id):
    monkeypatch.setattr("langgraph.config.get_config", lambda: {"configurable": {"app_run_id": run_id}})


def test_a_call_for_a_run_this_process_stopped_raises_and_a_resume_lets_it_through(monkeypatch):
    _in_run(monkeypatch, "run-stopped-here")
    workflow.remember_the_stop("run-stopped-here")
    try:
        with pytest.raises(workflow.RunCancelled):
            models._stop_if_this_run_was_stopped()
        workflow.forget_the_stop("run-stopped-here")
        models._stop_if_this_run_was_stopped()
    finally:
        workflow.forget_the_stop("run-stopped-here")


def test_another_run_and_no_run_are_left(monkeypatch):
    workflow.remember_the_stop("run-a")
    try:
        _in_run(monkeypatch, "run-b")
        models._stop_if_this_run_was_stopped()
        _in_run(monkeypatch, None)
        models._stop_if_this_run_was_stopped()
    finally:
        workflow.forget_the_stop("run-a")


@pytest.fixture
def a_runner(run_store, redis_container, monkeypatch):
    from app.server.events import EventBus
    from app.server.redis_client import reset_clients

    reset_clients()
    monkeypatch.setenv("CHECKPOINTER_TYPE", "memory")
    monkeypatch.setattr("app.server.tasks.celery_app.control.revoke", lambda task_id, **kwargs: None)  # the broker
    return runner.WorkflowRunner(EventBus(), run_store=run_store)


@pytest.mark.parametrize("stop", ["pause_run", "cancel_run"])
async def test_a_paused_or_cancelled_run_s_next_model_call_is_refused(a_runner, monkeypatch, stop):
    from langchain_core.messages import HumanMessage

    from app.models import CompatibleChatOpenAI

    record = a_runner.register_run(run_id="run-stopped", thread_id="thread-stopped", document_names=["brief.md"],
                                   document_paths=["/tmp/brief.md"], owner="alice", tenant_id="acme")
    record.status, record.task_id = "running", "task-1"
    a_runner.run_store.save(record)
    await getattr(a_runner, stop)("run-stopped")
    await a_runner._finish_cancelled(record)  # the worker's end of the stopped task
    _in_run(monkeypatch, "run-stopped")
    model = CompatibleChatOpenAI(model="m", api_key="k", base_url="http://localhost:1/v1", max_retries=0)
    try:
        with pytest.raises(workflow.RunCancelled):
            model._generate([HumanMessage(content="go on")])
    finally:
        workflow.forget_the_stop("run-stopped")
