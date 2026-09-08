from __future__ import annotations

import os
from celery import Celery
import asyncio
import logging

from app.server.runner import WorkflowRunner, RunRecord
from app.server.run_store import RunStore
from app.state import RepositoryContext
from app.documents import DocumentContent

# Configure Celery
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery("langchain_tasks", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

logger = logging.getLogger(__name__)

def _get_runner() -> WorkflowRunner:
    # Factory to get a runner instance in the worker process.
    store = RunStore()
    return WorkflowRunner(run_store=store)

@celery_app.task(name="execute_workflow_run")
def execute_workflow_run(
    run_id: str,
    resume: bool = False,
    decision_payload: dict | None = None
) -> None:
    """Execute a workflow graph run in the background."""
    runner = _get_runner()
    
    # We must run the async _run_loop within a synchronous Celery task.
    loop = asyncio.get_event_loop()
    
    record = runner.runs.get(run_id)
    if not record:
        logger.error(f"Run {run_id} not found in store for execution.")
        return

    # If this is a resume with a decision, inject the decision
    if decision_payload:
        record.pending_decision_payload = decision_payload

    # Run the loop synchronously via asyncio
    loop.run_until_complete(
        runner._run_loop(record, None, None, resume=resume)
    )
