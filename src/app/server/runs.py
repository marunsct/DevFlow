"""Run lifecycle and management API endpoints.

Steps 6.1, 6.2, and 6.4 of the workflow plan.  This router handles the
full lifecycle of a workflow run: create, start, observe, decide, cancel.

The browser is an observer and controlled input surface.  It never
directly mutates workflow state — every decision goes through the server,
which validates it and resumes the LangGraph thread.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile

from app.agents.approval import approve_write_decision, reject_write_decision
from app.documents import DocumentReadError, read_document
from app.graph.workflow import (
    APPROVAL_PAUSE_PREFIX,
    REVIEW_PAUSE_PREFIX,
    SPECIFICATION_REVIEW,
    SPRINT_REVIEW,
    approve_decision,
    request_changes_decision,
    skip_decision,
)
from app.server.events import EventBus
from app.server.models import (
    ApprovalDecisionRequest,
    ApprovalPayload,
    CreateRunResponse,
    ReviewDecisionRequest,
    ReviewPayload,
    RunListResponse,
    RunStatusResponse,
    RunSummary,
    SpinnerResponse,
    StartRunRequest,
)
from app.server.runner import RunRecord, WorkflowRunner, _api_status, _stage_meaning
from app.server.uploads import (
    FileTooLarge,
    UnsupportedFileType,
    UploadError,
    validate_and_store,
)
from app.tools.repository import RepositoryToolError, build_repository_context


def create_runs_router(
    runner: WorkflowRunner,
    event_bus: EventBus,
    upload_dir: str,
    repo_root: str,
) -> APIRouter:
    """Build the runs router with shared state.

    This is a factory because the router needs access to the runner,
    event bus, and configuration, which are created at app startup.
    """
    runs = APIRouter(prefix="/api/runs", tags=["runs"])

    # ------------------------------------------------------------------
    # Step 6.1: Create and start runs
    # ------------------------------------------------------------------

    @runs.post("", response_model=CreateRunResponse, status_code=201)
    async def create_run(file: UploadFile) -> CreateRunResponse:
        """Upload a product document and create a new workflow run.

        The server validates file type and size.  The document is stored
        outside executable paths.  Returns a run ID and thread ID for
        subsequent operations.
        """
        if file.filename is None:
            raise HTTPException(status_code=400, detail="No filename provided.")

        try:
            result = validate_and_store(
                file.file,
                file.filename,
                upload_dir,
            )
        except UnsupportedFileType as exc:
            raise HTTPException(status_code=415, detail=str(exc))
        except FileTooLarge as exc:
            raise HTTPException(status_code=413, detail=str(exc))
        except UploadError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        run_id = f"run-{uuid.uuid4()}"
        thread_id = f"thread-{uuid.uuid4()}"

        runner.register_run(
            run_id=run_id,
            thread_id=thread_id,
            document_name=result.original_name,
            document_path=result.stored_path,
        )

        return CreateRunResponse(
            run_id=run_id,
            thread_id=thread_id,
            status="created",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @runs.post("/{run_id}/start", status_code=202)
    async def start_run(run_id: str, body: StartRunRequest | None = None) -> dict[str, str]:
        """Start a created run.  Launches the workflow in a background task.

        Accepts optional settings: review policy, reviewer identity, and
        model override.  Returns 202 Accepted because the workflow runs
        asynchronously.
        """
        record = runner.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
        if record.status != "created":
            raise HTTPException(
                status_code=409,
                detail=f"Run {run_id} is already {record.status}; cannot start again.",
            )

        body = body or StartRunRequest()
        review_policy = body.review_policy or {}

        # Read the stored document.
        try:
            document = read_document(record.document_path)
        except (FileNotFoundError, DocumentReadError) as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Could not read the stored document: {exc}",
            )

        # Build repository context.
        try:
            repository = build_repository_context(repo_root)
        except RepositoryToolError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Could not inspect the repository: {exc}",
            )

        await runner.start_run(
            run_id,
            document,
            repository,
            review_policy=review_policy,
            reviewer=body.reviewer,
        )

        return {"message": f"Run {run_id} started.", "status": "running"}

    # ------------------------------------------------------------------
    # Step 6.2: Run status, logs, and artifacts
    # ------------------------------------------------------------------

    @runs.get("", response_model=RunListResponse)
    async def list_runs() -> RunListResponse:
        """List all runs with summary status."""
        summaries = [
            RunSummary(
                run_id=r.run_id,
                status=r.status,
                current_stage=r.current_stage,
                created_at=r.created_at,
                document_name=r.document_name,
            )
            for r in runner.runs.values()
        ]
        return RunListResponse(runs=summaries)

    @runs.get("/{run_id}", response_model=RunStatusResponse)
    async def get_run(run_id: str) -> RunStatusResponse:
        """Return the full status of a run."""
        record = runner.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

        return _build_status_response(record)

    @runs.get("/{run_id}/stages")
    async def get_stages(run_id: str) -> dict[str, Any]:
        """Return stage history with timing information."""
        record = runner.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

        events = await event_bus.history(run_id)
        stage_events = [e for e in events if e.event_type == "stage_change"]
        return {
            "run_id": run_id,
            "stages": [
                {
                    "stage": e.stage,
                    "meaning": e.message,
                    "timestamp": e.timestamp,
                    "sequence": e.sequence,
                }
                for e in stage_events
            ],
        }

    @runs.get("/{run_id}/artifacts")
    async def get_artifacts(run_id: str) -> dict[str, Any]:
        """List artifacts generated by this run."""
        record = runner.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

        state = record.state
        artifacts = []
        for key, label in [
            ("product_intake", "Product Intake"),
            ("tools_and_models", "Tools and Models"),
            ("technical_specification", "Technical Specification"),
            ("architecture_review", "Architecture Review"),
            ("sprint_plan", "Sprint Plan"),
            ("milestone_plan", "Milestone Plan"),
        ]:
            if state.get(key) is not None:
                artifacts.append({"key": key, "label": label, "present": True})

        specialist_outputs = state.get("specialist_outputs", {})
        for name in specialist_outputs:
            artifacts.append({"key": name, "label": f"Specialist: {name}", "present": True})

        return {"run_id": run_id, "artifacts": artifacts}

    @runs.get("/{run_id}/logs")
    async def get_logs(
        run_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Paginated log entries from the event history."""
        record = runner.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

        all_events = await event_bus.history(run_id)
        page = all_events[offset : offset + limit]
        return {
            "run_id": run_id,
            "total": len(all_events),
            "offset": offset,
            "limit": limit,
            "logs": [e.model_dump() for e in page],
        }

    # ------------------------------------------------------------------
    # Run lifecycle controls
    # ------------------------------------------------------------------

    @runs.post("/{run_id}/cancel", status_code=200)
    async def cancel_run(run_id: str) -> dict[str, str]:
        """Cancel a running or paused workflow."""
        record = runner.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
        if record.status in ("completed", "failed", "cancelled"):
            return {"message": f"Run {run_id} is already {record.status}."}

        await runner.cancel_run(run_id)
        return {"message": f"Run {run_id} cancelled.", "status": "cancelled"}

    @runs.delete("/{run_id}", status_code=200)
    async def delete_run(run_id: str) -> dict[str, str]:
        """Delete a completed, failed, or cancelled run."""
        record = runner.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
        if record.status not in ("completed", "failed", "cancelled"):
            raise HTTPException(
                status_code=409,
                detail=f"Run {run_id} is {record.status}; only terminal runs can be deleted.",
            )

        del runner.runs[run_id]
        return {"message": f"Run {run_id} deleted."}

    # ------------------------------------------------------------------
    # Step 6.4: Approval and review decisions
    # ------------------------------------------------------------------

    @runs.get("/{run_id}/approval")
    async def get_pending_approval(run_id: str) -> dict[str, Any]:
        """Return the pending approval request, if any."""
        record = runner.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
        if record.status != "waiting_for_approval":
            return {"pending": False, "run_id": run_id}

        approval = record.state.get("pending_approval")
        if approval is None:
            return {"pending": True, "run_id": run_id, "detail": "No approval payload available."}

        return {
            "pending": True,
            "run_id": run_id,
            "approval": ApprovalPayload(
                artifact_path=approval.artifact_path,
                content_summary=approval.notes or "",
                risk_level=approval.risk_level,
                requested_by=approval.requested_by,
                stage=approval.stage,
            ).model_dump(),
        }

    @runs.post("/{run_id}/approval")
    async def submit_approval(run_id: str, body: ApprovalDecisionRequest) -> dict[str, str]:
        """Submit an approval decision for a pending artifact write."""
        record = runner.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
        if record.status != "waiting_for_approval":
            raise HTTPException(
                status_code=409,
                detail=f"Run {run_id} is not waiting for approval (status: {record.status}).",
            )

        if body.action == "approve":
            decision = approve_write_decision()
        elif body.action == "reject":
            decision = reject_write_decision(body.reason or "Rejected via web UI.")
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")

        await runner.submit_approval(run_id, decision)
        return {"message": f"Approval decision '{body.action}' submitted for run {run_id}."}

    @runs.get("/{run_id}/review")
    async def get_pending_review(run_id: str) -> dict[str, Any]:
        """Return the pending review request, if any."""
        record = runner.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
        if record.status != "waiting_for_review":
            return {"pending": False, "run_id": run_id}

        review = record.state.get("pending_review")
        stage = record.state.get("stage", "")
        review_point = stage.removeprefix(REVIEW_PAUSE_PREFIX)

        payload = ReviewPayload(
            point=review_point,
            artifact_id=review.artifact_id if review else "",
            revision=review.revision if review else 0,
            comments=list(review.comments) if review and review.comments else [],
            available_actions=["approve", "changes", "skip"],
        )
        return {"pending": True, "run_id": run_id, "review": payload.model_dump()}

    @runs.post("/{run_id}/review")
    async def submit_review(run_id: str, body: ReviewDecisionRequest) -> dict[str, str]:
        """Submit a review decision."""
        record = runner.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
        if record.status != "waiting_for_review":
            raise HTTPException(
                status_code=409,
                detail=f"Run {run_id} is not waiting for review (status: {record.status}).",
            )

        if body.action == "approve":
            decision = approve_decision(comment=body.comment)
        elif body.action == "skip":
            decision = skip_decision()
        elif body.action == "changes":
            if not body.comment:
                raise HTTPException(
                    status_code=400,
                    detail="A 'changes' decision requires a comment explaining what must change.",
                )
            decision = request_changes_decision(body.comment)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")

        await runner.submit_review(run_id, decision)
        return {"message": f"Review decision '{body.action}' submitted for run {run_id}."}

    return runs


def _build_status_response(record: RunRecord) -> RunStatusResponse:
    """Build a RunStatusResponse from a RunRecord."""
    state = record.state
    reviews = []
    for point, review in (state.get("reviews") or {}).items():
        reviews.append({
            "point": point,
            "status": review.status.value if hasattr(review.status, "value") else str(review.status),
            "reviewer": getattr(review, "reviewer", "unassigned"),
            "revision": getattr(review, "revision", 1),
        })

    remediation = None
    cycle = state.get("remediation")
    if cycle is not None:
        remediation = {
            "attempt": cycle.attempt,
            "max_attempts": cycle.max_attempts,
            "escalated": cycle.escalated,
            "defect_count": len(cycle.defects),
            "test_runs": len(cycle.test_runs),
        }

    return RunStatusResponse(
        run_id=record.run_id,
        thread_id=record.thread_id,
        status=record.status,
        current_stage=record.current_stage,
        stage_meaning=record.stage_meaning or _stage_meaning(record.current_stage),
        created_at=record.created_at,
        updated_at=record.updated_at,
        reviews=reviews,
        remediation=remediation,
        error=record.error,
    )


__all__ = ["create_runs_router"]
