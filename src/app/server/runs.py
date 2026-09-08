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
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, Form
from fastapi.responses import FileResponse

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
) -> tuple[APIRouter, APIRouter]:
    """Build the API router for workflow control and observation."""
    runs = APIRouter(prefix="/api/runs", tags=["runs"])
    public_runs = APIRouter(prefix="/api/runs", tags=["runs"])

    # ------------------------------------------------------------------
    # Step 6.1: Create and start runs
    # ------------------------------------------------------------------

    @runs.post("", response_model=CreateRunResponse, status_code=201)
    async def create_run(files: list[UploadFile]) -> CreateRunResponse:
        """Upload product documents and create a new workflow run.

        The server validates file type and size. The documents are stored
        outside executable paths. Returns a run ID and thread ID for
        subsequent operations.
        """
        if not files:
            raise HTTPException(status_code=400, detail="No files provided.")

        stored_paths = []
        original_names = []

        for file in files:
            if file.filename is None:
                raise HTTPException(status_code=400, detail="No filename provided.")

            try:
                result = validate_and_store(
                    file.file,
                    file.filename,
                    upload_dir,
                )
                stored_paths.append(result.stored_path)
                original_names.append(result.original_name)
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
            document_names=original_names,
            document_paths=stored_paths,
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

        # Read the stored documents.
        try:
            document = read_document(record.document_paths)
        except (FileNotFoundError, DocumentReadError) as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Could not read the stored document: {exc}",
            )

        # Build repository context.
        try:
            # Override repo_root if artifact_directory is provided.
            target_repo_root = body.artifact_directory if body.artifact_directory else repo_root
            repository = build_repository_context(
                target_repo_root, 
                allow_subdirectories=body.allow_subdirectories
            )
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
            reviewer=body.reviewer or "unassigned",
            auto_approve=body.auto_approve,
            model_overrides={
                "llm_provider": body.llm_provider,
                "openai_base_url": body.openai_base_url,
                "openai_api_key": body.openai_api_key,
                "anthropic_api_key": body.anthropic_api_key,
                "google_api_key": body.google_api_key,
                "model_name": body.model_name,
            }
        )

        return {"message": f"Run {run_id} started."}

    @runs.post("/{run_id}/resume", status_code=202)
    async def resume_run(run_id: str) -> dict[str, str]:
        """Resume a failed run."""
        record = runner.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
        if record.status != "failed":
            raise HTTPException(
                status_code=409,
                detail=f"Run {run_id} is {record.status}; can only resume failed runs.",
            )

        await runner.resume_run(run_id)
        return {"message": f"Run {run_id} resumed."}

    @runs.post("/{run_id}/clone", status_code=201, response_model=CreateRunResponse)
    async def clone_run(run_id: str) -> CreateRunResponse:
        """Clone a run into a new one using the same documents."""
        record = runner.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

        new_run_id = f"run-{uuid.uuid4()}"
        new_thread_id = f"thread-{uuid.uuid4()}"

        # Register a new run with the same uploaded documents
        runner.register_run(
            run_id=new_run_id,
            thread_id=new_thread_id,
            document_names=record.document_names,
            document_paths=record.document_paths,
        )

        return CreateRunResponse(
            run_id=new_run_id,
            thread_id=new_thread_id,
            status="created",
            created_at=datetime.now(timezone.utc).isoformat(),
        )



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
                document_names=r.document_names,
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

        events = await event_bus.get_history(run_id)
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

    @public_runs.get("/{run_id}/artifacts/download")
    async def download_artifact(run_id: str, path: str) -> Any:
        """Download a generated artifact by path."""
        record = runner.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

        # Check if the requested path is a logical artifact ID in the state
        logical_mapping = {
            "product-intake": "product_intake",
            "tools-and-models": "tools_and_models",
            "technical-specification": "technical_specification",
            "architecture-review": "architecture_review",
            "sprint-milestone": "milestone_plan",
            "milestone-review": "milestone_review",
        }
        
        logical_key = logical_mapping.get(path) or path.replace("-", "_")
        if logical_key in record.state and record.state[logical_key] is not None:
            val = record.state[logical_key]
            if hasattr(val, "model_dump_json"):
                content = val.model_dump_json(indent=2)
            elif isinstance(val, dict):
                import json
                content = json.dumps(val, indent=2)
            else:
                import json
                content = json.dumps(str(val), indent=2)
            from fastapi.responses import Response
            return Response(content=content, media_type="application/json")
        elif logical_key in logical_mapping.values():
            # If the path explicitly matched a logical key but it's not in the state, return 404 cleanly.
            raise HTTPException(status_code=404, detail=f"Logical artifact {path} not generated yet.")

        # Ensure path is absolute or resolve it against repo_root
        import os
        
        # This is a bit tricky: the artifact_path in approval is usually absolute if we use temp dirs, 
        # but if we used repo_root, it might be relative or absolute.
        # It's safest to check if it exists directly first.
        full_path = path
        if not os.path.isabs(path):
            if record.repo_root and record.repo_root != "/app":
                full_path = os.path.join(record.repo_root, path)
            else:
                raise HTTPException(status_code=404, detail=f"Artifact {path} requested but repo_root is not set or invalid.")

        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail=f"Artifact not found at {full_path}")

        return FileResponse(
            full_path, 
            filename=os.path.basename(full_path),
            media_type="application/octet-stream"
        )

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

        all_events = await event_bus.get_history(run_id)
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
        if runner.run_store is not None:
            runner.run_store.delete(run_id)
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
            comments="\n".join(review.comments) if review and review.comments else None,
            available_actions=["approve", "changes", "skip"],
        )
        return {"pending": True, "run_id": run_id, "review": payload.model_dump()}

    @runs.post("/{run_id}/review")
    async def submit_review(
        run_id: str, 
        action: str = Form(...),
        comment: str = Form(None),
        file: UploadFile = None,
    ) -> dict[str, str]:
        """Submit a review decision."""
        record = runner.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
        if record.status != "waiting_for_review":
            raise HTTPException(
                status_code=409,
                detail=f"Run {run_id} is not waiting for review (status: {record.status}).",
            )

        edited_content = None
        if file:
            content = await file.read()
            edited_content = content.decode("utf-8")

        if action == "approve":
            decision = approve_decision(comment=comment, edited_content=edited_content)
        elif action == "skip":
            decision = skip_decision()
        elif action == "changes":
            if not comment and not edited_content:
                raise HTTPException(
                    status_code=400,
                    detail="A 'changes' decision requires a comment explaining what must change or an uploaded edited file.",
                )
            decision = request_changes_decision(comment or "Changes requested via file upload.", edited_content=edited_content)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

        await runner.submit_review(run_id, decision)
        return {"message": f"Review decision '{action}' submitted for run {run_id}."}

    return runs, public_runs


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
            "comments": "\n".join(getattr(review, "comments", [])) if getattr(review, "comments", None) else None,
            "updated_at": getattr(review, "updated_at", record.updated_at),
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

    artifacts = []
    if record.repo_root:
        repo_path = Path(record.repo_root)
        if repo_path.exists():
            # Scan for markdown files to treat as artifacts
            for md_file in repo_path.rglob("*.md"):
                # Skip any node_modules, .git, etc
                if ".git" in md_file.parts or "node_modules" in md_file.parts:
                    continue
                try:
                    rel_path = md_file.relative_to(repo_path)
                    artifacts.append({
                        "path": str(rel_path),
                        "kind": "document",
                        "revision": 1,
                        "created_by": "workflow",
                        "stage": record.run_id
                    })
                except ValueError:
                    pass

    return RunStatusResponse(
        run_id=record.run_id,
        thread_id=record.thread_id,
        status=record.status,
        current_stage=record.current_stage,
        stage_meaning=record.stage_meaning or _stage_meaning(record.current_stage),
        created_at=record.created_at,
        updated_at=record.updated_at,
        stages=record.state.get("stages", []),
        artifacts=artifacts,
        reviews=reviews,
        remediation=remediation,
        error=record.error,
    )


__all__ = ["create_runs_router"]
