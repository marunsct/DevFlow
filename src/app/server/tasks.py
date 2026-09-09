"""Celery worker entry point for workflow execution.

Three things this module gets deliberately right, having previously got them
wrong:

- **Shared resources live for the worker process, not the task.** A store and an
  event bus are built once per process. Constructing them per task opened a new
  20-connection Postgres pool every time and never closed it, which exhausted the
  database after a few dozen tasks.
- **Time limits exist.** A hung provider call used to pin a worker slot forever.
- **Retries do not repeat side effects.** The workflow writes files and spends
  tokens, so a blanket retry of the whole segment was not safe. Only genuinely
  transient infrastructure failures are retried; anything else marks the run
  failed for a human to resume deliberately.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from celery import Celery
from celery.signals import task_failure, worker_process_init, worker_process_shutdown

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("langchain_tasks", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    # A workflow segment writes files and calls paid APIs, so it must not be
    # silently re-run when a worker dies mid-task. The run is left in a state a
    # human can inspect and resume instead.
    task_acks_late=False,
    task_reject_on_worker_lost=False,
    task_time_limit=int(os.environ.get("CELERY_TASK_TIME_LIMIT", "3600")),
    task_soft_time_limit=int(os.environ.get("CELERY_TASK_SOFT_TIME_LIMIT", "3300")),
    worker_max_tasks_per_child=int(os.environ.get("CELERY_MAX_TASKS_PER_CHILD", "50")),
    broker_connection_retry_on_startup=True,
)

# Failures that are worth retrying: the work never started, or the infrastructure
# blinked. Anything else is a logic or model failure that retrying will reproduce.
_RETRYABLE = (ConnectionError, TimeoutError, OSError)

_runner = None


@worker_process_init.connect
def _init_worker_process(**_kwargs) -> None:
    """Build the per-process runner once, after fork."""
    global _runner
    from app.server.events import EventBus
    from app.server.run_store import RunStore
    from app.server.runner import WorkflowRunner

    _runner = WorkflowRunner(event_bus=EventBus(), run_store=RunStore.shared())
    logger.info("Worker process initialised")


@worker_process_shutdown.connect
def _shutdown_worker_process(**_kwargs) -> None:
    from app.server.run_store import RunStore

    RunStore.reset_shared()


def _get_runner():
    """Return the process-wide runner, building it if a signal did not fire."""
    global _runner
    if _runner is None:
        _init_worker_process()
    return _runner


@task_failure.connect
def handle_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, **_other):
    """Record a permanently failed task on the dead-letter list."""
    from app.server.redis_client import get_redis_client

    try:
        client = get_redis_client()
        client.lpush(
            "celery_dlq",
            json.dumps(
                {
                    "task_id": task_id,
                    "task_name": getattr(sender, "name", "unknown"),
                    "exception": str(exception),
                    "kwargs": kwargs,
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
        )
        # Bounded, so a persistent failure cannot fill Redis.
        client.ltrim("celery_dlq", 0, 999)
    except Exception:  # noqa: BLE001
        logger.error("Failed to write to the dead-letter queue", exc_info=True)


def _mark_failed(run_id: str, message: str) -> None:
    from app.server.run_store import RunStore

    try:
        store = RunStore.shared()
        record = store.load(run_id)
        if record is None:
            return
        record.status = "failed"
        record.error = message[:500]
        record.updated_at = datetime.now(timezone.utc).isoformat()
        store.save(record)
    except Exception:  # noqa: BLE001
        logger.error("Could not mark run %s as failed", run_id, exc_info=True)


@celery_app.task(bind=True, name="execute_workflow_run", max_retries=2)
def execute_workflow_run(
    self,
    run_id: str,
    resume: bool = False,
    decision_payload: dict | None = None,
) -> None:
    """Run one segment of a workflow graph."""
    runner = _get_runner()
    record = runner.run_store.load(run_id)
    if record is None:
        logger.error("Run %s not found; nothing to execute", run_id)
        return

    if runner.run_store.is_cancel_requested(run_id):
        logger.info("Run %s was cancelled before execution started", run_id)
        return

    if decision_payload:
        record.pending_decision_payload = decision_payload

    document = None
    if record.document_paths and not resume:
        from app.documents import read_document

        try:
            document = read_document(record.document_paths)
        except Exception as exc:  # noqa: BLE001
            _mark_failed(run_id, f"Could not read the uploaded documents: {exc}")
            return

    repository = None
    if record.repo_root:
        from app.tools.repository import build_repository_context

        try:
            repository = build_repository_context(record.repo_root, allow_subdirectories=True)
        except Exception as exc:  # noqa: BLE001
            _mark_failed(run_id, f"Could not prepare the workspace: {exc}")
            return

    try:
        # asyncio.run gives each task its own loop and closes it afterwards.
        # get_event_loop() was deprecated in this position and raises outright
        # under the threads and gevent worker pools.
        asyncio.run(runner._run_loop(record, document, repository, resume=resume))
    except _RETRYABLE as exc:
        if self.request.retries < self.max_retries:
            countdown = 5 * (2**self.request.retries)
            logger.warning(
                "Transient failure on run %s (attempt %s); retrying in %ss",
                run_id, self.request.retries + 1, countdown,
            )
            raise self.retry(exc=exc, countdown=countdown)
        _mark_failed(run_id, f"Infrastructure failure after retries: {exc}")
        raise
    except Exception as exc:  # noqa: BLE001
        # _run_loop already records the failure; this catches anything raised
        # outside it. Not retried: re-running would duplicate file writes and
        # model spend.
        logger.exception("Run %s failed permanently", run_id)
        _mark_failed(run_id, f"{type(exc).__name__}: {exc}")
        raise


__all__ = ["celery_app", "execute_workflow_run"]
