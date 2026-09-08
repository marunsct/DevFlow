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
from app.tracing import is_tracing_enabled, trace_metadata

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
    repo_root: str | None = None
    review_policy: dict[str, bool] = field(default_factory=dict)
    reviewer: str = "unassigned"
    auto_approve: bool = False

    # Decision handoff: the API sets this when enqueuing a resume task
    pending_decision_payload: dict[str, Any] | None = field(default=None, repr=False)


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
        run_store: Any | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.model = model
        self.repo_root = repo_root
        self.run_store = run_store
        self.runs: dict[str, RunRecord] = {}

        # Restore persisted run records on startup.
        if self.run_store is not None:
            for record in self.run_store.list_all():
                self.runs[record.run_id] = record



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
        self._persist(record)
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
        model_overrides: dict[str, str | None] | None = None,
    ) -> None:
        """Launch the workflow in a background task."""
        record = self.runs.get(run_id)
        if record is None:
            raise ValueError(f"Run {run_id} is not registered")
        if record.status != "created":
            raise ValueError(f"Run {run_id} is already {record.status}")

        record.repo_root = str(repository.root_path)
        record.review_policy = review_policy or {}
        record.reviewer = reviewer
        record.auto_approve = auto_approve
        record.status = "running"
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(record)

        from app.server.tasks import execute_workflow_run
        execute_workflow_run.delay(run_id=run_id, resume=False, decision_payload=None)

    async def resume_run(self, run_id: str) -> None:
        """Resume a failed workflow in a background task."""
        record = self.runs.get(run_id)
        if record is None:
            raise ValueError(f"Run {run_id} is not registered")
        if record.status != "failed":
            raise ValueError(f"Run {run_id} is {record.status}, cannot resume")

        record.status = "running"
        record.error = None
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(record)

        from app.server.tasks import execute_workflow_run
        execute_workflow_run.delay(run_id=run_id, resume=True, decision_payload=None)


    async def submit_approval(self, run_id: str, decision: dict[str, Any]) -> None:
        """Submit an approval decision for a paused run."""
        record = self.runs.get(run_id)
        if record is None:
            raise ValueError(f"Run {run_id} not found")
        if record.status != "waiting_for_approval":
            raise ValueError(f"Run {run_id} is not waiting for approval (status: {record.status})")

        payload = {"type": "approval", "decision": decision}
        record.status = "running"
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(record)
        
        from app.server.tasks import execute_workflow_run
        execute_workflow_run.delay(run_id=run_id, resume=True, decision_payload=payload)

    async def submit_review(self, run_id: str, decision: dict[str, Any]) -> None:
        """Submit a review decision for a paused run."""
        record = self.runs.get(run_id)
        if record is None:
            raise ValueError(f"Run {run_id} not found")
        if record.status != "waiting_for_review":
            raise ValueError(f"Run {run_id} is not waiting for review (status: {record.status})")

        payload = {"type": "review", "decision": decision}
        record.status = "running"
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(record)
        
        from app.server.tasks import execute_workflow_run
        execute_workflow_run.delay(run_id=run_id, resume=True, decision_payload=payload)

    async def cancel_run(self, run_id: str) -> None:
        """Cancel a running or paused workflow."""
        record = self.runs.get(run_id)
        if record is None:
            raise ValueError(f"Run {run_id} not found")
        if record.status in ("completed", "failed", "cancelled"):
            return  # already terminal

        record.status = "cancelled"
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(record)
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
        document: DocumentContent | None,
        repository: RepositoryContext | None,
        resume: bool = False,
        model_overrides: dict[str, str | None] | None = None,
    ) -> None:
        """Drive the graph invoke-loop, publishing events at every step.

        This mirrors the loop in ``main.py`` but runs asynchronously and
        hands off decisions via ``asyncio.Event`` instead of stdin prompts.
        """
        # We might not have a full repository context when resuming.
        # But we still need repo_root and allow_subdirectories for build_workflow_graph.
        # We can extract it from record.repo_root if repository is None.
        repo_root = repository.root_path if repository else record.repo_root
        allow_subs = repository.allow_subdirectories if repository else True
        
        graph = build_workflow_graph(
            model=self.model,
            repo_root=repo_root,
            allow_subdirectories=allow_subs,
            model_overrides=model_overrides
        )
        run_id = record.run_id

        # Build tracing metadata if LangSmith is enabled.
        trace_meta = trace_metadata(
            run_id=run_id,
            stage="start",
            role="controller",
            thread_id=record.thread_id,
        ) if is_tracing_enabled() else {}

        try:
            if resume:
                from app.graph.workflow import resume_failed_run
                state = await asyncio.to_thread(
                    resume_failed_run,
                    graph,
                    record.thread_id,
                )
            else:
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
                    self._persist(record)
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
                        self._persist(record)

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
                        return # Exit the celery task; will be resumed via submit_approval

                elif stage.startswith(REVIEW_PAUSE_PREFIX):
                    record.status = "waiting_for_review"
                    record.updated_at = datetime.now(timezone.utc).isoformat()
                    self._persist(record)

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
                    return # Exit the celery task; will be resumed via submit_review

                # Stage is running (not paused, not terminal).  This should
                # only happen on the initial invoke or when a resume pushes
                # through multiple stages at once.  We loop back and the next
                # invoke is implicit (the graph ran to its next pause/terminal).
                continue

            else:
                record.status = "failed"
                record.error = f"Stopped after {MAX_GATES} gates without reaching a terminal stage."
                record.updated_at = datetime.now(timezone.utc).isoformat()
                self._persist(record)

        except asyncio.CancelledError:
            record.status = "cancelled"
            record.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist(record)
            logger.info("Run %s was cancelled", run_id)
        except Exception:
            record.status = "failed"
            record.error = traceback.format_exc()
            record.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist(record)
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



    def _update_record(self, record: RunRecord, state: dict[str, Any]) -> None:
        """Sync the run record with the latest graph state."""
        stage = state.get("stage", "")
        record.current_stage = stage
        record.stage_meaning = _stage_meaning(stage)
        record.status = _api_status(stage)
        record.error = state.get("error")
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(record)

    def _persist(self, record: RunRecord) -> None:
        """Persist a run record to the store, if one is configured."""
        if self.run_store is not None:
            self.run_store.save(record)


__all__ = [
    "RunRecord",
    "WorkflowRunner",
]
