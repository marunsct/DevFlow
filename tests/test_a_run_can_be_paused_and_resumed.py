"""A run can be paused from the screen and resumed where it stopped, and so can a cancelled one.

The owner wanted to stop a run to change the model and go on with it. There
was no pause: cancelling ended the run for good (resume took only `failed` and
`waiting_for_budget`), and the only way back was to rewrite its database row.
A pause raises the same stop flag a cancel does, so the worker stops the same
way at a stage boundary, but the run is recorded `paused` and nothing is
cleaned up; resume takes `paused` and `cancelled` too and lowers the flag.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.server.events import EventBus
from app.server.runner import RESUMABLE_STATUSES, RunConflict, WorkflowRunner


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def runner(run_store, redis_container, monkeypatch):
    from app.server.redis_client import reset_clients

    reset_clients()
    monkeypatch.setenv("CHECKPOINTER_TYPE", "memory")
    return WorkflowRunner(EventBus(), run_store=run_store)


@pytest.fixture
def dispatched(monkeypatch):
    calls = []

    class _AsyncResult:
        id = "task-2"

    import app.server.tasks as tasks_module

    monkeypatch.setattr(tasks_module.execute_workflow_run, "delay", lambda **kw: calls.append(kw) or _AsyncResult())
    return calls


@pytest.fixture
def revoked(monkeypatch):
    calls = []
    import app.server.tasks as tasks_module

    monkeypatch.setattr(tasks_module.celery_app.control, "revoke", lambda task_id, **kw: calls.append(task_id))
    return calls


def _register(runner, run_id="run-1", **overrides):
    record = runner.register_run(
        run_id=run_id, thread_id=f"thread-{run_id}", document_names=["brief.md"],
        document_paths=["/tmp/brief.md"], owner="alice", tenant_id="acme",
    )
    for key, value in overrides.items():
        setattr(record, key, value)
    runner.run_store.save(record)
    return record


async def test_pausing_a_running_run_stops_its_task_and_flags_a_pause(runner, revoked):
    _register(runner, status="running", task_id="task-7")

    await runner.pause_run("run-1")

    assert runner.run_store.is_cancel_requested("run-1")
    assert runner.run_store.stop_reason("run-1") == "pause"
    assert revoked == ["task-7"]


@pytest.mark.parametrize("status", ["waiting_for_approval", "completed", "paused", "failed"])
async def test_only_a_running_run_can_be_paused(runner, revoked, status):
    _register(runner, status=status)

    with pytest.raises(RunConflict):
        await runner.pause_run("run-1")
    assert revoked == []


async def test_a_paused_run_is_recorded_paused_and_a_cancelled_one_cancelled(runner, revoked):
    paused = _register(runner, status="running", task_id="t")
    await runner.pause_run("run-1")
    await runner._finish_cancelled(paused)
    assert runner.run_store.load("run-1").status == "paused"

    cancelled = _register(runner, run_id="run-2", status="running", task_id="t")
    await runner.cancel_run("run-2")
    await runner._finish_cancelled(cancelled)
    assert runner.run_store.load("run-2").status == "cancelled"


async def test_a_cancel_after_a_pause_is_a_cancel(runner, revoked):
    _register(runner, status="running", task_id="t")
    await runner.pause_run("run-1")

    await runner.cancel_run("run-1")

    assert runner.run_store.stop_reason("run-1") == "cancel"


@pytest.mark.parametrize("status", ["paused", "cancelled"])
async def test_a_paused_or_cancelled_run_resumes_with_its_stop_flag_lowered(runner, dispatched, status):
    _register(runner, status=status, cancel_requested=True)

    await runner.resume_run("run-1")

    record = runner.run_store.load("run-1")
    assert record.status == "running"
    assert not runner.run_store.is_cancel_requested("run-1")
    assert dispatched and dispatched[0]["resume"] is True


async def test_a_running_run_is_still_not_resumed(runner, dispatched):
    _register(runner, status="running")

    with pytest.raises(RunConflict):
        await runner.resume_run("run-1")


def test_a_stop_remembered_in_a_worker_process_is_forgotten_on_resume():
    from app.graph import workflow

    workflow._CANCELLED_RUNS.add("run-9")
    workflow.forget_the_stop("run-9")

    assert "run-9" not in workflow._CANCELLED_RUNS


def test_the_screen_and_the_server_agree_on_what_resumes():
    from pathlib import Path

    activity = (Path(__file__).resolve().parents[1] / "langchain-ui/src/lib/activity.ts").read_text()
    for status in RESUMABLE_STATUSES:
        assert f"'{status}'" in activity.split("export const RESUMABLE")[1]


def test_the_api_offers_pause_and_refuses_a_run_that_is_not_running(client, tmp_path):
    brief = tmp_path / "brief.txt"
    brief.write_text("A notes page")
    with open(brief, "rb") as handle:
        run_id = client.post("/api/runs", files=[("files", ("brief.txt", handle, "text/plain"))]).json()["run_id"]

    response = client.post(f"/api/runs/{run_id}/pause")

    assert response.status_code == 409
    assert "only a running run can be paused" in response.json()["detail"]
