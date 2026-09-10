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
import os
import traceback
from dataclasses import dataclass, field
from pathlib import Path
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

MAX_GATES = int(os.environ.get("WORKFLOW_MAX_GATES", "1000"))
"""Safety ceiling: stop after this many invoke rounds in one run segment.

Only auto-approved runs get anywhere near this - a supervised run returns to the
human at each gate, ending the segment. An unattended run does the opposite: it
answers every gate itself and does the whole build in one segment, and every
artifact write by every specialist across every sprint is one round. The old
ceiling of 200 was sized for a mostly-supervised run and would stop a real
unattended build part-way through.

It exists to catch a stage that is genuinely looping, not to bound normal work,
so it is set high and made configurable rather than tuned.
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


def _stage_narration(stage: str, *, auto_approve: bool) -> tuple[str, str]:
    """The message and API status to report for a stage.

    Returns `(message, status)`.

    An unattended run is not waiting for anyone. Reporting
    `waiting_for_approval` for a gate the run is about to clear itself is wrong
    three times over: the dashboard renders an approval modal nobody needs to
    answer, the log narrates a pause that is not happening, and - the reason
    this is not merely cosmetic - `submit_approval`'s
    compare-and-set guard accepts the transition, dispatching a second Celery
    task onto a graph thread the first task is still driving.
    """
    status = _api_status(stage)
    if auto_approve and status == "waiting_for_approval":
        return (f"Auto-approving: {stage.removeprefix(APPROVAL_PAUSE_PREFIX)}", "running")
    return (_stage_meaning(stage), status)


class RunConflict(RuntimeError):
    """A lifecycle transition was attempted from the wrong status."""


_SECRET_OVERRIDE_KEYS = frozenset({"openai_api_key", "anthropic_api_key", "google_api_key"})

_DEPLOYMENT_OVERRIDE_KEYS = frozenset({"openai_base_url"})
"""Overrides that describe *where the model is hosted*, not what the run chose.

`llm_provider` and `model_name` are experiment choices worth pinning to a run:
re-running it later should use the same model. A base URL is not - it is
deployment configuration, and the host moves.

Pinning it meant that moving the model server broke every run that already
existed, permanently: the stored URL won over the corrected setting on every
resume, so there was no way to point an existing run at the new address.
"""

_UNPINNED_OVERRIDE_KEYS = _SECRET_OVERRIDE_KEYS | _DEPLOYMENT_OVERRIDE_KEYS


def _public_model_overrides(overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only the parts of a model override worth persisting on the run.

    API keys must not be persisted in the metadata table or shipped through the
    Celery broker; the worker resolves credentials from its own environment or
    the secret store. The base URL is dropped for a different reason - see
    `_DEPLOYMENT_OVERRIDE_KEYS`.
    """
    if not overrides:
        return {}
    return {k: v for k, v in overrides.items() if v and k not in _UNPINNED_OVERRIDE_KEYS}


def _applicable_overrides(overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Filter overrides at the point of use, so rows written earlier self-heal.

    Runs created before the base URL stopped being pinned still carry one in
    their stored overrides. Dropping it here means those runs pick up the
    current setting on their next attempt instead of staying pointed at a host
    that may no longer exist.
    """
    return _public_model_overrides(overrides)


def _approval_metadata(approval: Any) -> dict[str, Any]:
    return {
        "artifact_path": getattr(approval, "artifact_path", "") if approval else "",
        "risk_level": getattr(approval, "risk_level", "unknown") if approval else "unknown",
        "requested_by": getattr(approval, "requested_by", "") if approval else "",
    }


def _resume_config(thread_id: str, metadata: dict[str, Any] | None) -> dict[str, Any]:
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    if metadata:
        config["metadata"] = metadata
    return config


@dataclass
class RunRecord:
    """Metadata envelope for one workflow run.

    Graph state is deliberately *not* stored here. It lives in the checkpointer
    keyed by ``thread_id`` and is read from there on demand - keeping a second
    copy meant the two drifted, and in practice the copy was never written, so
    every API read saw an empty dict.
    """

    run_id: str
    thread_id: str
    document_names: list[str]
    document_paths: list[str]
    owner: str = "unknown"
    tenant_id: str = "default"
    status: str = "created"
    current_stage: str = ""
    stage_meaning: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: str | None = None

    # Settings captured at start time.
    repo_root: str | None = None
    review_policy: dict[str, bool] = field(default_factory=dict)
    reviewer: str = "unassigned"
    auto_approve: bool = False
    model_overrides: dict[str, Any] = field(default_factory=dict)

    # Execution bookkeeping.
    task_id: str | None = None
    cancel_requested: bool = False

    # Decision handoff: set by the API when enqueuing a resume task.
    pending_decision_payload: dict[str, Any] | None = field(default=None, repr=False)

    def graph_state(self, checkpointer: Any = None) -> dict[str, Any]:
        """Read this run's live graph state from the checkpointer.

        Returns an empty dict when the run has not started or the checkpoint is
        unavailable, so callers can treat "no state yet" and "cannot reach the
        store" the same way: nothing to show.
        """
        from app.graph.workflow import load_thread_state

        try:
            return load_thread_state(self.thread_id, checkpointer=checkpointer)
        except Exception:  # noqa: BLE001
            logger.warning("Could not load graph state for run %s", self.run_id, exc_info=True)
            return {}


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

        # Built through app.graph.checkpointing so the deserialization allowlist
        # and the configured backend actually apply. The previous hardcoded
        # `sqlite3.connect("workflow_state.db")` bypassed both: it ignored
        # DATA_DIR, put the database in each container's ephemeral layer, and
        # meant the API and the worker held separate invisible checkpoint stores.
        from app.graph.checkpointing import build_checkpointer

        self.checkpointer = build_checkpointer()





    def register_run(
        self,
        run_id: str,
        thread_id: str,
        document_names: list[str],
        document_paths: list[str],
        *,
        owner: str = "unknown",
        tenant_id: str = "default",
    ) -> RunRecord:
        """Register a new run without starting it."""
        record = RunRecord(
            run_id=run_id,
            thread_id=thread_id,
            document_names=document_names,
            document_paths=document_paths,
            owner=owner,
            tenant_id=tenant_id,
        )
        self._persist(record)
        return record

    def discard_run_threads(self, record: RunRecord) -> None:
        """Delete the checkpoints this run created, outer and inner.

        Each agent attempt mints a fresh inner thread id to get a clean context
        window, so without this they accumulate unreachable forever.
        """
        from app.graph.workflow import discard_thread

        state = record.graph_state(self.checkpointer)
        for thread_id in [*state.get("inner_thread_ids", []), record.thread_id]:
            discard_thread(thread_id, checkpointer=self.checkpointer)

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
        """Persist start settings and dispatch the run to a worker.

        The status transition is atomic: two concurrent starts cannot both win,
        because only one UPDATE can match ``status = 'created'``.
        """
        record = self.run_store.load(run_id)
        if record is None:
            raise ValueError(f"Run {run_id} is not registered")

        record.repo_root = str(repository.root_path)
        record.review_policy = review_policy or {}
        record.reviewer = reviewer
        record.auto_approve = auto_approve
        # Overrides are persisted so the worker can apply them. They were
        # previously built here and then dropped, so choosing a model in the UI
        # had no effect at all. Secrets are filtered out: they must not travel
        # through the broker or sit in the metadata table.
        record.model_overrides = _public_model_overrides(model_overrides)
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(record)

        if not self.run_store.compare_and_set_status(
            run_id, "created", "running", updated_at=record.updated_at
        ):
            raise RunConflict(f"Run {run_id} is not in the 'created' state.")

        self._dispatch(run_id, resume=False, decision_payload=None)

    async def resume_run(self, run_id: str) -> None:
        """Resume a failed run from its last checkpoint."""
        now = datetime.now(timezone.utc).isoformat()
        if not self.run_store.compare_and_set_status(
            run_id, "failed", "running", updated_at=now, clear_error=True
        ):
            raise RunConflict(f"Run {run_id} is not in the 'failed' state.")
        self._dispatch(run_id, resume=True, decision_payload=None)

    async def submit_approval(self, run_id: str, decision: dict[str, Any]) -> None:
        # Defence in depth against a stale status row. An unattended run answers
        # its own gates inside the worker; accepting a decision here would
        # dispatch a second task onto a thread that one is still driving, and
        # both would write checkpoints to it.
        record = self.run_store.load(run_id)
        if record is not None and record.auto_approve:
            raise RunConflict(
                f"Run {run_id} is unattended and approves its own gates. "
                "There is nothing to decide; cancel it if you want it to stop."
            )

        now = datetime.now(timezone.utc).isoformat()
        if not self.run_store.compare_and_set_status(
            run_id, "waiting_for_approval", "running", updated_at=now
        ):
            raise RunConflict(f"Run {run_id} is not waiting for approval.")
        self._dispatch(run_id, resume=True, decision_payload={"type": "approval", "decision": decision})

    async def submit_review(self, run_id: str, decision: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.run_store.compare_and_set_status(
            run_id, "waiting_for_review", "running", updated_at=now
        ):
            raise RunConflict(f"Run {run_id} is not waiting for review.")
        self._dispatch(run_id, resume=True, decision_payload={"type": "review", "decision": decision})

    async def cancel_run(self, run_id: str) -> None:
        """Request cancellation and revoke the worker task.

        Two mechanisms, because neither alone is sufficient: revoke stops a task
        that has not started or kills one that has, while the cancel flag lets a
        task that is mid-superstep stop cleanly at the next checkpoint rather
        than being killed halfway through a graph write.
        """
        record = self.run_store.load(run_id)
        if record is None:
            raise ValueError(f"Run {run_id} not found")
        if record.status in ("completed", "failed", "cancelled"):
            return

        now = datetime.now(timezone.utc).isoformat()
        self.run_store.request_cancel(run_id, now)

        if record.task_id:
            try:
                from app.server.tasks import celery_app

                celery_app.control.revoke(record.task_id, terminate=True, signal="SIGTERM")
            except Exception:  # noqa: BLE001 - the flag still stops it at the next check
                logger.warning("Could not revoke task %s for run %s", record.task_id, run_id, exc_info=True)

        # A run that is paused has no worker to notice the flag, so mark it
        # terminal here. A running one is left to the worker, which will see the
        # flag and record the cancellation itself.
        if record.status in ("created", "waiting_for_approval", "waiting_for_review", "paused"):
            self.run_store.compare_and_set_status(
                run_id,
                ("created", "waiting_for_approval", "waiting_for_review", "paused"),
                "cancelled",
                updated_at=now,
            )

        await self.event_bus.publish(
            run_id,
            RunEvent(
                run_id=run_id,
                sequence=await self.event_bus.next_sequence(run_id),
                stage=record.current_stage,
                event_type="complete",
                message="Run was cancelled by user.",
            ),
        )
        await self.event_bus.close(run_id)

    def _dispatch(self, run_id: str, *, resume: bool, decision_payload: dict[str, Any] | None) -> None:
        """Hand the run to a Celery worker and remember the task id."""
        from app.server.tasks import execute_workflow_run

        async_result = execute_workflow_run.delay(
            run_id=run_id, resume=resume, decision_payload=decision_payload
        )
        try:
            self.run_store.set_task_id(run_id, async_result.id)
        except Exception:  # noqa: BLE001 - dispatch succeeded; cancel is just less precise
            logger.warning("Could not record task id for run %s", run_id, exc_info=True)

    async def _run_loop(
        self,
        record: RunRecord,
        document: DocumentContent | None,
        repository: RepositoryContext | None,
        resume: bool = False,
        model_overrides: dict[str, str | None] | None = None,
    ) -> None:
        """Drive one segment of the graph, publishing events as it goes.

        One invoke per call. The graph runs until it pauses for a human or
        reaches a terminal stage, and this method then returns so the Celery task
        finishes; a later decision dispatches a fresh task. The previous version
        wrapped this in a 200-iteration loop whose non-terminal branch fell
        through to `continue` without re-invoking anything, so it republished the
        same event 200 times and then reported a gate-limit failure that had not
        happened.
        """
        run_id = record.run_id
        repo_root = repository.root_path if repository else record.repo_root
        allow_subs = repository.allow_subdirectories if repository else True
        overrides = _applicable_overrides(
            model_overrides if model_overrides is not None else record.model_overrides
        )

        try:
            if self.run_store.is_cancel_requested(run_id):
                await self._finish_cancelled(record)
                return

            graph = build_workflow_graph(
                model=self.model,
                repo_root=repo_root,
                allow_subdirectories=allow_subs,
                model_overrides=overrides or None,
                checkpointer=self.checkpointer,
            )

            trace_meta = (
                trace_metadata(
                    run_id=run_id, stage="start", role="controller", thread_id=record.thread_id
                )
                if is_tracing_enabled()
                else {}
            )

            if resume:
                decision = getattr(record, "pending_decision_payload", None)
                if decision and decision.get("type") == "approval":
                    state = await asyncio.to_thread(
                        resume_pending_approval, graph, record.thread_id, decision["decision"],
                        metadata=trace_meta,
                    )
                elif decision and decision.get("type") == "review":
                    state = await asyncio.to_thread(
                        resume_pending_review, graph, record.thread_id, decision["decision"],
                        metadata=trace_meta,
                    )
                else:
                    from app.graph.workflow import resume_failed_run

                    state = await asyncio.to_thread(
                        resume_failed_run, graph, record.thread_id, metadata=trace_meta
                    )
            else:
                state = await asyncio.to_thread(
                    start_workflow, graph, document, repository, record.thread_id,
                    review_policy=record.review_policy, reviewer=record.reviewer,
                    metadata=trace_meta,
                )

            await self._handle_state(record, graph, state, trace_meta)

        except asyncio.CancelledError:
            await self._finish_cancelled(record)
            raise
        except Exception as exc:
            # The full traceback goes to the log, keyed by correlation id. Only a
            # short message reaches the API, because run.error is rendered in the
            # browser and a traceback leaks paths, versions and module layout.
            logger.exception("Run %s failed", run_id)
            record.status = self._status_after_failure(record)
            record.error = f"{type(exc).__name__}: {exc}"[:500]
            record.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist(record)
            await self.event_bus.publish(
                run_id,
                RunEvent(
                    run_id=run_id,
                    sequence=await self.event_bus.next_sequence(run_id),
                    stage=record.current_stage,
                    event_type="error",
                    message=f"Run failed: {record.error}",
                ),
            )
            await self.event_bus.close(run_id)

    async def _handle_state(
        self,
        record: RunRecord,
        graph: Any,
        state: dict[str, Any],
        trace_meta: dict[str, Any],
    ) -> None:
        """Interpret the state the graph returned and settle the run's status.

        Auto-approval is the one case that legitimately loops, and it is bounded
        by MAX_GATES with a real re-invoke on each pass.
        """
        run_id = record.run_id

        for _ in range(MAX_GATES):
            stage = state.get("stage", "")
            self._update_record(record, state)
            narration, narrated_status = _stage_narration(
                stage, auto_approve=bool(record.auto_approve)
            )

            await self.event_bus.publish(
                run_id,
                RunEvent(
                    run_id=run_id,
                    sequence=await self.event_bus.next_sequence(run_id),
                    stage=stage,
                    event_type="stage_change",
                    message=narration,
                    metadata=redact_metadata({"status": narrated_status}),
                ),
            )

            if self.run_store.is_cancel_requested(run_id):
                await self._finish_cancelled(record)
                return

            if stage in ("complete", "failed"):
                record.status = "completed" if stage == "complete" else "failed"
                record.error = state.get("error")
                record.updated_at = datetime.now(timezone.utc).isoformat()
                self._persist(record)
                await asyncio.to_thread(self._archive_artifacts, record)
                await asyncio.to_thread(self._prune_scratch)
                await self.event_bus.publish(
                    run_id,
                    RunEvent(
                        run_id=run_id,
                        sequence=await self.event_bus.next_sequence(run_id),
                        stage=stage,
                        event_type="complete" if stage == "complete" else "error",
                        message=record.error or "Run completed successfully.",
                    ),
                )
                await self.event_bus.close(run_id)
                return

            if stage.startswith(APPROVAL_PAUSE_PREFIX):
                approval = state.get("pending_approval")
                if record.auto_approve:
                    await self.event_bus.publish(
                        run_id,
                        RunEvent(
                            run_id=run_id,
                            sequence=await self.event_bus.next_sequence(run_id),
                            stage=stage,
                            event_type="approval_auto",
                            message=f"Auto-approved: {approval.notes if approval else 'artifact write'}",
                            metadata=redact_metadata(_approval_metadata(approval)),
                        ),
                    )
                    state = await asyncio.to_thread(
                        resume_pending_approval, graph, record.thread_id,
                        approve_write_decision(), metadata=trace_meta,
                    )
                    continue

                record.status = "waiting_for_approval"
                record.updated_at = datetime.now(timezone.utc).isoformat()
                self._persist(record)
                await self.event_bus.publish(
                    run_id,
                    RunEvent(
                        run_id=run_id,
                        sequence=await self.event_bus.next_sequence(run_id),
                        stage=stage,
                        event_type="approval_request",
                        message=f"Approval required: {approval.notes if approval else 'artifact write'}",
                        metadata=redact_metadata(_approval_metadata(approval)),
                    ),
                )
                return

            if stage.startswith(REVIEW_PAUSE_PREFIX):
                record.status = "waiting_for_review"
                record.updated_at = datetime.now(timezone.utc).isoformat()
                self._persist(record)
                review_point = stage.removeprefix(REVIEW_PAUSE_PREFIX)
                review = state.get("pending_review")
                await self.event_bus.publish(
                    run_id,
                    RunEvent(
                        run_id=run_id,
                        sequence=await self.event_bus.next_sequence(run_id),
                        stage=stage,
                        event_type="review_request",
                        message=f"Review open: {review_point}",
                        metadata=redact_metadata({
                            "review_point": review_point,
                            "artifact_id": review.artifact_id if review else "",
                            "revision": review.revision if review else 0,
                        }),
                    ),
                )
                return

            # A stage that is neither terminal nor a pause means the graph
            # returned mid-flight. Re-invoke to make progress; without this the
            # loop would spin on unchanged state.
            state = await asyncio.to_thread(graph.invoke, None, _resume_config(record.thread_id, trace_meta))

        # Reaching here means the auto-approval loop ran out of rounds. This is
        # the one failure an unattended run is most likely to hit, and it used
        # to be recorded silently: the row said "failed" while no event was
        # published and the stream was never closed, so a UI watching the run
        # simply waited forever. Report it like any other terminal state.
        record.status = "failed"
        record.error = (
            f"Stopped after {MAX_GATES} automatic approvals without finishing. "
            "Raise WORKFLOW_MAX_GATES if this run legitimately needs more, or "
            "inspect the log for a stage that is repeating."
        )
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(record)
        await self.event_bus.publish(
            run_id,
            RunEvent(
                run_id=run_id,
                sequence=await self.event_bus.next_sequence(run_id),
                stage=record.current_stage,
                event_type="error",
                message=record.error,
            ),
        )
        await self.event_bus.close(run_id)

    def _archive_artifacts(self, record: RunRecord) -> None:
        """Push this run's produced files to object storage, if configured.

        Runs once, when the run reaches a terminal stage. Two reasons this is
        worth doing at all: the workspace volume is the only copy that exists,
        and the API serves downloads by reading the workspace - which is a
        different disk from this worker's as soon as there is more than one
        node. Failures are logged, never raised: the run is finished and its
        files are on disk, so a storage outage must not turn a completed run
        into a failed one.
        """
        if not record.repo_root:
            return
        try:
            from app.server.object_store import archive_directory
            from app.tools.repository import list_repository_files

            workspace = Path(record.repo_root)
            if not workspace.is_dir():
                return
            # The same pruned listing the status page shows, so what is archived
            # is exactly what the run reports as its artifacts.
            relative = list_repository_files(workspace)
            stored = archive_directory(
                f"runs/{record.run_id}", workspace, relative_paths=relative
            )
            logger.info("Archived %d artifact(s) for run %s", stored, record.run_id)
        except Exception:  # noqa: BLE001 - archiving is never load-bearing
            logger.warning("Could not archive artifacts for run %s", record.run_id, exc_info=True)

    def _prune_scratch(self) -> None:
        """Age out the journal and the compaction context store.

        Run at a terminal stage because that is a moment this worker is already
        doing filesystem work and nothing is waiting on it. Both trees live
        under `DATA_DIR`, which is one shared volume across the API and every
        worker, and neither had any retention: the journal grows by one >50 KB
        file per truncated stream, the context store by one evicted-history file
        per inner-thread attempt.

        Deliberately age-based rather than run-scoped - two runs share the
        per-agent context directories under worker concurrency, so nothing here
        may key off the run that happens to have just finished. Failures are
        logged, never raised: the run is over and its artifacts are safe.
        """
        try:
            from app.agents.context_store import prune as prune_context
            from app.tools.journal import prune as prune_journal

            removed = prune_journal() + prune_context()
            if removed:
                logger.info("Pruned %d expired scratch file(s)", removed)
        except Exception:  # noqa: BLE001 - cleanup is never load-bearing
            logger.warning("Could not prune scratch storage", exc_info=True)

    def _status_after_failure(self, record: RunRecord) -> str:
        """The status to record when an invoke raised.

        A raising node is not checkpointed, so the graph is still parked exactly
        where it was before the attempt - and if that was a human gate, the gate
        is still the only thing that can move the run forward.

        Recording a flat "failed" in that case desynchronised the row from the
        graph: `status` said failed while `current_stage` still said
        `awaiting_approval:...`. The API gates each lifecycle route on `status`
        and the UI picks its controls from it, so the run became unreachable -
        /resume was offered but could not clear an approval gate, and /approve
        was rejected because the status was not `waiting_for_approval`. Keeping
        the status derived from the stage keeps exactly one route open, and it is
        the route that actually works. The error is still surfaced in `error`.
        """
        stage = record.current_stage or ""
        if stage.startswith((APPROVAL_PAUSE_PREFIX, REVIEW_PAUSE_PREFIX)):
            return _api_status(stage)
        return "failed"

    async def _finish_cancelled(self, record: RunRecord) -> None:
        record.status = "cancelled"
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(record)
        logger.info("Run %s cancelled", record.run_id)
        await self.event_bus.close(record.run_id)

    def _update_record(self, record: RunRecord, state: dict[str, Any]) -> None:
        """Sync the run record with the latest graph state."""
        stage = state.get("stage", "")
        meaning, status = _stage_narration(stage, auto_approve=bool(record.auto_approve))
        record.current_stage = stage
        record.stage_meaning = meaning
        record.status = status
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
