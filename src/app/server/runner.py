"""Async bridge between the web control plane and the synchronous LangGraph workflow.

The workflow graph is invoked synchronously (``graph.invoke(...)``), but the
web server is async (FastAPI/Starlette).  This module runs each invoke in a
thread pool so the event loop stays responsive, publishes events to the
``EventBus`` on every state change, and uses ``asyncio.Event`` objects to
hand off human decisions (approval, review) without polling.

Design note: the graph itself is unchanged — it still returns state dicts and
pauses by setting a ``stage`` prefix.  The runner just wraps that same
invoke-loop pattern from ``main.py`` in an async harness that emits events
instead of printing to stdout.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.agents.approval import approve_write_decision, reject_write_decision
from app.documents import DocumentContent
from app.graph.workflow import (
    APPROVAL_PAUSE_PREFIX,
    REVIEW_PAUSE_PREFIX,
    approve_decision,
    build_workflow_graph,
    request_changes_decision,
    resume_pending_approval,
    resume_pending_review,
    skip_decision,
    start_workflow,
)
from app.server.events import EventBus, RunEvent, redact_metadata
from app.state import RepositoryContext

logger = logging.getLogger(__name__)

MAX_GATES = 200
"""Safety ceiling: stop after this many invoke rounds per run.

Higher than the CLI's 50 because the web runner handles gates automatically
when a decision is already queued (e.g. auto-approve), so it can hit more
gates per run without human interaction at each one.
"""

# Stage-meaning map, matching main.py's _STAGE_MEANINGS.
_STAGE_MEANINGS: dict[str, str] = {
    "product_manager": "Reading the product document and extracting product understanding.",
    "tools_models": "Comparing frameworks, model providers, and infrastructure options.",
    "principal_architect": "Writing the technical specification and architecture decisions.",
    "architecture_review": "The architecture reviewer is checking security and feasibility.",
    "user_review_specification": "Waiting for your review of the technical specification.",
    "scrum_master": "Breaking approved architecture into independent vertical sprints.",
    "technical_lead": "Selecting one sprint and planning a small milestone.",
    "specialist_dispatch": "Specialists are implementing and testing the milestone.",
    "test_and_triage": "Running tests and triaging any failures into tracked defects.",
    "defect_remediation": "Routing defects to their owners for fixing.",
    "milestone_review": "The milestone reviewer is checking the completed work.",
    "user_review_sprint": "Waiting for your review of the completed sprint.",
    "complete": "The run finished successfully.",
    "failed": "The run stopped and needs a human decision.",
}


def _stage_meaning(stage: str) -> str:
    """Human-readable meaning for a stage."""
    if stage.startswith(APPROVAL_PAUSE_PREFIX):
        return f"Waiting for approval: {stage.removeprefix(APPROVAL_PAUSE_PREFIX)}"
    if stage.startswith(REVIEW_PAUSE_PREFIX):
        return f"Waiting for review: {stage.removeprefix(REVIEW_PAUSE_PREFIX)}"
    return _STAGE_MEANINGS.get(stage, stage)


def _api_status(stage: str) -> str:
    """Map a raw stage string to one of the API's status enum values."""
    if stage == "complete":
        return "completed"
    if stage == "failed":
        return "failed"
    if stage.startswith(APPROVAL_PAUSE_PREFIX):
        return "waiting_for_approval"
    if stage.startswith(REVIEW_PAUSE_PREFIX):
        return "waiting_for_review"
    return "running"


@dataclass
class RunRecord:
    """In-memory record of a single workflow run.

    Tracks everything the API needs to answer status queries and route
    decisions back to the graph.  Lives only as long as this process.
    """

    run_id: str
    thread_id: str
    document_names: list[str]
    document_paths: list[str]
    status: str = "created"
    current_stage: str = ""
    stage_meaning: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    state: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    # Settings captured at start time.
    review_policy: dict[str, bool] = field(default_factory=dict)
    reviewer: str = "unassigned"
    auto_approve: bool = False

    # Decision handoff: the runner waits on this event, and the API sets it
    # after populating `pending_decision_payload`.
    _decision_ready: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    pending_decision_payload: dict[str, Any] | None = field(default=None, repr=False)

    # Background task handle.
    _task: asyncio.Task | None = field(default=None, repr=False)


class WorkflowRunner:
    """Manages workflow runs for the web server.

    Each run gets its own background task that drives the graph invoke-loop.
    The runner publishes events and pauses for human decisions without
    blocking the event loop.

    Thread safety: all state mutation happens inside asyncio tasks on the
    same event loop.  The ``asyncio.Event`` handoff ensures the runner and
    the API endpoint never race on the decision payload.
    """

    def __init__(
        self,
        event_bus: EventBus,
        *,
        model: str | None = None,
        repo_root: str | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.model = model
        self.repo_root = repo_root
        self.runs: dict[str, RunRecord] = {}



    def register_run(
        self,
        run_id: str,
        thread_id: str,
        document_names: list[str],
        document_paths: list[str],
    ) -> RunRecord:
        """Register a new run without starting it."""
        record = RunRecord(
            run_id=run_id,
            thread_id=thread_id,
            document_names=document_names,
            document_paths=document_paths,
        )
        self.runs[run_id] = record
        return record

    async def start_run(
        self,
        run_id: str,
        document: DocumentContent,
        repository: RepositoryContext,
        *,
        review_policy: dict[str, bool] | None = None,
        reviewer: str = "unassigned",
        auto_approve: bool = False,
    ) -> None:
        """Launch the workflow in a background task."""
        record = self.runs.get(run_id)
        if record is None:
            raise ValueError(f"Run {run_id} is not registered")
        if record.status != "created":
            raise ValueError(f"Run {run_id} is already {record.status}")

        record.review_policy = review_policy or {}
        record.reviewer = reviewer
        record.auto_approve = auto_approve
        record.status = "running"
        record.updated_at = datetime.now(timezone.utc).isoformat()

        record._task = asyncio.create_task(
            self._run_loop(record, document, repository),
            name=f"workflow-{run_id}",
        )

    async def submit_approval(self, run_id: str, decision: dict[str, Any]) -> None:
        """Submit an approval decision for a paused run."""
        record = self.runs.get(run_id)
        if record is None:
            raise ValueError(f"Run {run_id} not found")
        if record.status != "waiting_for_approval":
            raise ValueError(f"Run {run_id} is not waiting for approval (status: {record.status})")

        record.pending_decision_payload = {"type": "approval", "decision": decision}
        record._decision_ready.set()

    async def submit_review(self, run_id: str, decision: dict[str, Any]) -> None:
        """Submit a review decision for a paused run."""
        record = self.runs.get(run_id)
        if record is None:
            raise ValueError(f"Run {run_id} not found")
        if record.status != "waiting_for_review":
            raise ValueError(f"Run {run_id} is not waiting for review (status: {record.status})")

        record.pending_decision_payload = {"type": "review", "decision": decision}
        record._decision_ready.set()

    async def cancel_run(self, run_id: str) -> None:
        """Cancel a running or paused workflow."""
        record = self.runs.get(run_id)
        if record is None:
            raise ValueError(f"Run {run_id} not found")
        if record.status in ("completed", "failed", "cancelled"):
            return  # already terminal

        if record._task is not None and not record._task.done():
            record._task.cancel()

        record.status = "cancelled"
        record.updated_at = datetime.now(timezone.utc).isoformat()
        await self.event_bus.publish(
            run_id,
            RunEvent(
                run_id=run_id,
                sequence=self.event_bus.next_sequence(run_id),
                stage=record.current_stage,
                event_type="complete",
                message="Run was cancelled by user.",
            ),
        )
        await self.event_bus.close(run_id)

    async def _run_loop(
        self,
        record: RunRecord,
        document: DocumentContent,
        repository: RepositoryContext,
    ) -> None:
        """Drive the graph invoke-loop, publishing events at every step.

        This mirrors the loop in ``main.py`` but runs asynchronously and
        hands off decisions via ``asyncio.Event`` instead of stdin prompts.
        """
        graph = build_workflow_graph(
            model=self.model,
            repo_root=repository.root_path,
            allow_subdirectories=repository.allow_subdirectories
        )
        run_id = record.run_id

        try:
            # First invoke.
            state = await asyncio.to_thread(
                start_workflow,
                graph,
                document,
                repository,
                record.thread_id,
                review_policy=record.review_policy,
                reviewer=record.reviewer,
            )
            record.state = state
            self._update_record(record, state)

            for _ in range(MAX_GATES):
                stage = state.get("stage", "")

                # Publish a stage-change event.
                await self.event_bus.publish(
                    run_id,
                    RunEvent(
                        run_id=run_id,
                        sequence=self.event_bus.next_sequence(run_id),
                        stage=stage,
                        event_type="stage_change",
                        message=_stage_meaning(stage),
                        metadata=redact_metadata({"status": _api_status(stage)}),
                    ),
                )

                if stage in ("complete", "failed"):
                    record.status = "completed" if stage == "complete" else "failed"
                    record.error = state.get("error")
                    record.updated_at = datetime.now(timezone.utc).isoformat()
                    event_type = "complete" if stage == "complete" else "error"
                    await self.event_bus.publish(
                        run_id,
                        RunEvent(
                            run_id=run_id,
                            sequence=self.event_bus.next_sequence(run_id),
                            stage=stage,
                            event_type=event_type,
                            message=record.error or "Run completed successfully.",
                        ),
                    )
                    await self.event_bus.close(run_id)
                    return

                if stage.startswith(APPROVAL_PAUSE_PREFIX):
                    approval = state.get("pending_approval")

                    if record.auto_approve:
                        # Auto-approve: skip human interaction, approve immediately.
                        await self.event_bus.publish(
                            run_id,
                            RunEvent(
                                run_id=run_id,
                                sequence=self.event_bus.next_sequence(run_id),
                                stage=stage,
                                event_type="approval_auto",
                                message=f"Auto-approved: {approval.notes if approval else 'artifact write'}",
                                metadata=redact_metadata({
                                    "artifact_path": approval.artifact_path if approval else "",
                                    "risk_level": approval.risk_level if approval else "unknown",
                                    "requested_by": approval.requested_by if approval else "",
                                }),
                            ),
                        )
                        record.status = "running"
                        record.updated_at = datetime.now(timezone.utc).isoformat()
                        decision_payload = {"type": "approval", "decision": approve_write_decision()}
                    else:
                        record.status = "waiting_for_approval"
                        record.updated_at = datetime.now(timezone.utc).isoformat()

                        # Publish approval request event.
                        await self.event_bus.publish(
                            run_id,
                            RunEvent(
                                run_id=run_id,
                                sequence=self.event_bus.next_sequence(run_id),
                                stage=stage,
                                event_type="approval_request",
                                message=f"Approval required: {approval.notes if approval else 'artifact write'}",
                                metadata=redact_metadata({
                                    "artifact_path": approval.artifact_path if approval else "",
                                    "risk_level": approval.risk_level if approval else "unknown",
                                    "requested_by": approval.requested_by if approval else "",
                                }),
                            ),
                        )

                        # Wait for the decision.
                        decision_payload = await self._wait_for_decision(record)
                        if decision_payload is None:
                            return  # cancelled

                    state = await asyncio.to_thread(
                        resume_pending_approval,
                        graph,
                        record.thread_id,
                        decision_payload["decision"],
                    )
                    record.state = state
                    self._update_record(record, state)
                    continue

                if stage.startswith(REVIEW_PAUSE_PREFIX):
                    record.status = "waiting_for_review"
                    record.updated_at = datetime.now(timezone.utc).isoformat()

                    review_point = stage.removeprefix(REVIEW_PAUSE_PREFIX)
                    review = state.get("pending_review")
                    await self.event_bus.publish(
                        run_id,
                        RunEvent(
                            run_id=run_id,
                            sequence=self.event_bus.next_sequence(run_id),
                            stage=stage,
                            event_type="review_request",
                            message=f"Optional review open: {review_point}",
                            metadata=redact_metadata({
                                "review_point": review_point,
                                "artifact_id": review.artifact_id if review else "",
                                "revision": review.revision if review else 0,
                            }),
                        ),
                    )

                    decision = await self._wait_for_decision(record)
                    if decision is None:
                        return  # cancelled

                    state = await asyncio.to_thread(
                        resume_pending_review,
                        graph,
                        record.thread_id,
                        decision["decision"],
                    )
                    record.state = state
                    self._update_record(record, state)
                    continue

                # Stage is running (not paused, not terminal).  This should
                # only happen on the initial invoke or when a resume pushes
                # through multiple stages at once.  We loop back and the next
                # invoke is implicit (the graph ran to its next pause/terminal).
                break

            else:
                record.status = "failed"
                record.error = f"Stopped after {MAX_GATES} gates without reaching a terminal stage."
                record.updated_at = datetime.now(timezone.utc).isoformat()

        except asyncio.CancelledError:
            record.status = "cancelled"
            record.updated_at = datetime.now(timezone.utc).isoformat()
            logger.info("Run %s was cancelled", run_id)
        except Exception:
            record.status = "failed"
            record.error = traceback.format_exc()
            record.updated_at = datetime.now(timezone.utc).isoformat()
            logger.exception("Run %s failed with an unhandled exception", run_id)
            await self.event_bus.publish(
                run_id,
                RunEvent(
                    run_id=run_id,
                    sequence=self.event_bus.next_sequence(run_id),
                    stage=record.current_stage,
                    event_type="error",
                    message=f"Run failed: {record.error}",
                ),
            )
            await self.event_bus.close(run_id)

    async def _wait_for_decision(self, record: RunRecord) -> dict[str, Any] | None:
        """Block until the API submits a decision or the run is cancelled.

        Returns None if the run was cancelled while waiting.
        """
        record._decision_ready.clear()
        try:
            await record._decision_ready.wait()
        except asyncio.CancelledError:
            return None

        payload = record.pending_decision_payload
        record.pending_decision_payload = None
        record._decision_ready.clear()
        record.status = "running"
        record.updated_at = datetime.now(timezone.utc).isoformat()
        return payload

    def _update_record(self, record: RunRecord, state: dict[str, Any]) -> None:
        """Sync the run record with the latest graph state."""
        stage = state.get("stage", "")
        record.current_stage = stage
        record.stage_meaning = _stage_meaning(stage)
        record.status = _api_status(stage)
        record.error = state.get("error")
        record.updated_at = datetime.now(timezone.utc).isoformat()


__all__ = [
    "RunRecord",
    "WorkflowRunner",
]
