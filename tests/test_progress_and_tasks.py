"""Streaming tickets, progress endpoints, worker dispatch and tracing."""

import pytest
from fastapi.testclient import TestClient

from app.server.runner import RunRecord


@pytest.fixture(autouse=True)
def fresh_redis(redis_container):
    from app.server.redis_client import reset_clients

    reset_clients()
    yield


def _seed_run(run_store, run_id="run-stream", tenant="default", status="running") -> RunRecord:
    record = RunRecord(
        run_id=run_id,
        thread_id=f"thread-{run_id}",
        document_names=["brief.md"],
        document_paths=["/tmp/brief.md"],
        owner="testuser",
        tenant_id=tenant,
        status=status,
        current_stage="product_manager",
    )
    run_store.save(record)
    return record


# ---------------------------------------------------------------------------
# Streaming tickets
# ---------------------------------------------------------------------------


async def test_a_ticket_is_single_use():
    """A redeemed ticket is worthless, which is what makes it safe in a URL."""
    from app.server.progress import issue_stream_ticket, redeem_stream_ticket

    ticket = await issue_stream_ticket("run-1", "alice")

    assert await redeem_stream_ticket(ticket, "run-1") == "alice"
    assert await redeem_stream_ticket(ticket, "run-1") is None


async def test_a_ticket_is_bound_to_one_run():
    from app.server.progress import issue_stream_ticket, redeem_stream_ticket

    ticket = await issue_stream_ticket("run-1", "alice")
    assert await redeem_stream_ticket(ticket, "run-2") is None


async def test_an_unknown_ticket_is_refused():
    from app.server.progress import redeem_stream_ticket

    assert await redeem_stream_ticket("not-a-real-ticket", "run-1") is None


def test_a_ticket_can_be_requested_for_an_accessible_run(client, run_store):
    _seed_run(run_store)
    response = client.post("/api/runs/run-stream/events/ticket")
    assert response.status_code == 200
    assert response.json()["ticket"]


def test_no_ticket_is_issued_for_an_unknown_run(client):
    assert client.post("/api/runs/run-nope/events/ticket").status_code == 404


# ---------------------------------------------------------------------------
# Progress endpoints
# ---------------------------------------------------------------------------


def test_spinner_status_reports_the_current_stage(client, run_store):
    _seed_run(run_store)
    body = client.get("/api/runs/run-stream/status").json()
    assert body["stage"] == "product_manager"
    assert body["is_terminal"] is False
    assert body["status"] == "running"


def test_spinner_status_marks_terminal_runs(client, run_store):
    _seed_run(run_store, run_id="run-done", status="completed")
    assert client.get("/api/runs/run-done/status").json()["is_terminal"] is True


def test_polling_returns_events_after_a_cursor(client, run_store):
    _seed_run(run_store)

    first = client.get("/api/runs/run-stream/events", params={"since": 0})
    assert first.status_code == 200
    assert "cursor" in first.json()


def test_progress_endpoints_reject_an_unknown_run(client):
    assert client.get("/api/runs/run-missing/status").status_code == 404
    assert client.get("/api/runs/run-missing/events").status_code == 404


def test_logs_are_paginated(client, run_store):
    _seed_run(run_store)
    body = client.get("/api/runs/run-stream/logs", params={"limit": 10, "offset": 0}).json()
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert isinstance(body["logs"], list)


def test_an_oversized_log_page_is_refused(client, run_store):
    _seed_run(run_store)
    assert client.get("/api/runs/run-stream/logs", params={"limit": 10_000}).status_code == 422


# ---------------------------------------------------------------------------
# Worker dispatch
# ---------------------------------------------------------------------------


def test_a_missing_run_is_skipped_rather_than_crashing(run_store, monkeypatch):
    from app.server import tasks

    monkeypatch.setattr(tasks, "_runner", None)

    class _Runner:
        def __init__(self):
            self.run_store = run_store
            self.called = False

    monkeypatch.setattr(tasks, "_get_runner", lambda: _Runner())
    tasks.execute_workflow_run("run-does-not-exist", resume=False, decision_payload=None)


def test_a_cancelled_run_is_not_executed(run_store, monkeypatch):
    from datetime import datetime, timezone

    from app.server import tasks

    _seed_run(run_store, run_id="run-cancel-me")
    run_store.request_cancel("run-cancel-me", datetime.now(timezone.utc).isoformat())

    executed = []

    class _Runner:
        def __init__(self):
            self.run_store = run_store

        async def _run_loop(self, *a, **k):
            executed.append(True)

    monkeypatch.setattr(tasks, "_get_runner", lambda: _Runner())
    tasks.execute_workflow_run("run-cancel-me", resume=False, decision_payload=None)

    assert executed == []


def test_marking_a_run_failed_is_recorded(run_store, monkeypatch):
    from app.server import tasks
    from app.server.run_store import RunStore

    _seed_run(run_store, run_id="run-fail")
    monkeypatch.setattr(RunStore, "shared", classmethod(lambda cls: run_store))

    tasks._mark_failed("run-fail", "something went wrong")

    record = run_store.load("run-fail")
    assert record.status == "failed"
    assert "something went wrong" in record.error


def test_the_dead_letter_queue_is_bounded(monkeypatch):
    """An unbounded DLQ was itself a way to fill Redis."""
    from app.server import tasks
    from app.server.redis_client import get_redis_client

    client = get_redis_client()
    client.delete("celery_dlq")

    for i in range(5):
        tasks.handle_task_failure(
            sender=type("S", (), {"name": "execute_workflow_run"}),
            task_id=f"task-{i}",
            exception=RuntimeError("boom"),
            kwargs={"run_id": "run-x"},
        )

    assert client.llen("celery_dlq") == 5
    assert client.llen("celery_dlq") <= 1000
    client.delete("celery_dlq")


def test_celery_has_time_limits_configured():
    """A hung provider call used to pin a worker slot indefinitely."""
    from app.server.tasks import celery_app

    assert celery_app.conf.task_time_limit > 0
    assert celery_app.conf.task_soft_time_limit < celery_app.conf.task_time_limit


def test_workflow_tasks_are_not_silently_replayed():
    """The workflow writes files and spends tokens, so late-ack replay is off."""
    from app.server.tasks import celery_app

    assert celery_app.conf.task_acks_late is False
    assert celery_app.conf.task_reject_on_worker_lost is False


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------


def test_tracing_is_off_unless_enabled(monkeypatch):
    from app.tracing import is_tracing_enabled, trace_metadata

    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    assert is_tracing_enabled() is False
    assert trace_metadata("r", "s", "role", "t") == {}


def test_trace_metadata_carries_run_identity(monkeypatch):
    from app.tracing import APP_RUN_ID_KEY, trace_metadata

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    meta = trace_metadata("run-1", "intake", "product_manager", "thread-1", product_name="Widget")

    assert meta[APP_RUN_ID_KEY] == "run-1"
    assert meta["stage"] == "intake"
    assert meta["product_name"] == "Widget"
    # Never `run_id`: LangGraph reserves it and drops the input of any invoke
    # whose run_id matches the checkpoint's, which silently voids every resume.
    assert "run_id" not in meta


def test_tracing_requires_a_key_when_enabled(monkeypatch):
    from app.config import load_settings
    from app.tracing import configure_tracing

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

    settings = load_settings({"LANGSMITH_TRACING": "true", "OPENAI_MODEL": "m"})
    with pytest.raises(ValueError, match="LANGSMITH_API_KEY"):
        configure_tracing(settings)


def test_configure_tracing_accepts_a_settings_object(monkeypatch):
    """It was previously handed the settings *route handler's* coroutine."""
    from app.config import load_settings
    from app.tracing import configure_tracing

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    settings = load_settings(
        {
            "LANGSMITH_TRACING": "true",
            "LANGSMITH_API_KEY": "ls-key",
            "LANGSMITH_PROJECT": "proj",
            "OPENAI_MODEL": "m",
        }
    )
    configure_tracing(settings)
    import os

    assert os.environ["LANGCHAIN_PROJECT"] == "proj"


def test_a_run_name_is_readable():
    from app.tracing import make_run_name

    assert "Widget" in make_run_name("Widget", "thread-1")
    assert "Unknown Product" in make_run_name("", "thread-1")
