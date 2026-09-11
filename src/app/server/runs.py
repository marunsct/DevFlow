"""Run lifecycle and management API endpoints.

Steps 6.1, 6.2, and 6.4 of the workflow plan.  This router handles the
full lifecycle of a workflow run: create, start, observe, decide, cancel.

The browser is an observer and controlled input surface.  It never
directly mutates workflow state — every decision goes through the server,
which validates it and resumes the LangGraph thread.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response

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
from pathlib import Path

from app.server.models import (
    ApprovalDecisionRequest,
    ArtifactInfo,
    RemediationInfo,
    ReviewInfo,
    ApprovalPayload,
    CodebaseUploadResponse,
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
from app.server.object_store import archive_directory, archive_file, ensure_local
from app.server.seeding import SeedError, seed_workspace
from app.server.uploads import (
    ARCHIVE_EXTENSIONS,
    DEFAULT_MAX_ARCHIVE_BYTES,
    FileTooLarge,
    UnsupportedFileType,
    UploadError,
    validate_and_store,
)
from app.server.auth import UserInDB, get_current_active_user, record_audit, require_operator
from app.server.runner import RunConflict
from app.server.workspaces import (
    WorkspaceError,
    allocate_workspace,
    delete_workspace,
    resolve_within_workspace,
)
from app.tools.repository import RepositoryToolError, build_repository_context

logger = logging.getLogger(__name__)

MAX_DOCUMENTS_PER_RUN = 10
"""Cap the file count as well as the per-file size: without it a caller could
send hundreds of at-limit uploads in one request."""


def _require_run(runner: WorkflowRunner, run_id: str, user: UserInDB) -> RunRecord:
    """Load a run the caller is allowed to see, or raise.

    Authorisation lives here rather than in each handler so no endpoint can
    forget it. A run in another tenant returns 404, not 403: telling an attacker
    that a run exists but belongs to someone else is itself a disclosure.
    """
    record = runner.run_store.load(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
    if user.role != "admin" and record.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
    return record


def create_runs_router(
    runner: WorkflowRunner,
    event_bus: EventBus,
    upload_dir: str,
    repo_root: str,
) -> APIRouter:
    """Build the API router for workflow control and observation."""
    runs = APIRouter(prefix="/api/runs", tags=["runs"])

    # ------------------------------------------------------------------
    # Step 6.1: Create and start runs
    # ------------------------------------------------------------------

    @runs.post("", response_model=CreateRunResponse, status_code=201)
    async def create_run(
        files: list[UploadFile] = File(...),
        user: UserInDB = Depends(require_operator),
    ) -> CreateRunResponse:
        """Upload product documents and register a new run."""
        if not files:
            raise HTTPException(status_code=400, detail="No files provided.")
        if len(files) > MAX_DOCUMENTS_PER_RUN:
            raise HTTPException(
                status_code=400,
                detail=f"At most {MAX_DOCUMENTS_PER_RUN} documents may be uploaded per run.",
            )

        stored_paths: list[str] = []
        original_names: list[str] = []
        for file in files:
            if not file.filename:
                raise HTTPException(status_code=400, detail="Every file must have a filename.")
            try:
                result = validate_and_store(file.file, file.filename, upload_dir)
            except UnsupportedFileType as exc:
                raise HTTPException(status_code=415, detail=str(exc))
            except FileTooLarge as exc:
                raise HTTPException(status_code=413, detail=str(exc))
            except UploadError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            stored_paths.append(result.stored_path)
            original_names.append(result.original_name)
            # A durable second copy, and the only way a worker on another node
            # can read a document this replica received.
            archive_file(f"uploads/{Path(result.stored_path).name}", result.stored_path)

        run_id = f"run-{uuid.uuid4()}"
        thread_id = f"thread-{uuid.uuid4()}"
        record = runner.register_run(
            run_id=run_id,
            thread_id=thread_id,
            document_names=original_names,
            document_paths=stored_paths,
            owner=user.username,
            tenant_id=user.tenant_id,
        )
        record_audit(
            actor=user.username, tenant_id=user.tenant_id, action="run.create",
            subject=run_id, detail={"documents": original_names},
        )
        return CreateRunResponse(
            run_id=record.run_id,
            thread_id=record.thread_id,
            status=record.status,
            created_at=record.created_at,
        )

    def _resolve_upload(upload_id: str) -> str | None:
        """Map an upload id back to a stored path, or None.

        The id is a filename this server generated, but it arrives from a
        request, so it is resolved under the upload directory with the same
        containment check used for artifact downloads: an id of
        ``../../etc/passwd`` must not name a file outside it.
        """
        if not upload_id:
            return None
        try:
            candidate = resolve_within_workspace(upload_dir, upload_id)
        except WorkspaceError:
            return None
        # Same reason as the document fetch: the archive may have been uploaded
        # to a different replica.
        ensure_local(f"uploads/{candidate.name}", candidate)
        return str(candidate) if candidate.is_file() else None

    @runs.post("/{run_id}/codebase", response_model=CodebaseUploadResponse, status_code=201)
    async def upload_codebase(
        run_id: str,
        file: UploadFile = File(...),
        user: UserInDB = Depends(require_operator),
    ) -> CodebaseUploadResponse:
        """Upload an existing codebase as an archive, for a brownfield run.

        Stored, not yet extracted: it is unpacked into the workspace when the
        run starts, so a run that is never started never expands an archive.
        """
        record = _require_run(runner, run_id, user)
        if record.status != "created":
            raise HTTPException(
                status_code=409,
                detail=f"Run {run_id} is already {record.status}; its workspace is fixed.",
            )
        if not file.filename:
            raise HTTPException(status_code=400, detail="The archive must have a filename.")

        try:
            result = validate_and_store(
                file.file, file.filename, upload_dir,
                max_size_bytes=DEFAULT_MAX_ARCHIVE_BYTES,
                allowed_extensions=ARCHIVE_EXTENSIONS,
            )
        except UnsupportedFileType as exc:
            raise HTTPException(status_code=415, detail=str(exc))
        except FileTooLarge as exc:
            raise HTTPException(status_code=413, detail=str(exc))
        except UploadError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        archive_file(f"uploads/{Path(result.stored_path).name}", result.stored_path)
        record_audit(
            actor=user.username, tenant_id=user.tenant_id, action="run.codebase_upload",
            subject=run_id, detail={"archive": result.original_name, "bytes": result.file_size_bytes},
        )
        return CodebaseUploadResponse(
            upload_id=Path(result.stored_path).name,
            original_name=result.original_name,
            file_size_bytes=result.file_size_bytes,
        )

    @runs.post("/{run_id}/start", status_code=202)
    async def start_run(
        run_id: str,
        body: StartRunRequest | None = None,
        user: UserInDB = Depends(require_operator),
    ) -> dict[str, str]:
        """Start a registered run in a worker."""
        record = _require_run(runner, run_id, user)
        if record.status != "created":
            raise HTTPException(
                status_code=409,
                detail=f"Run {run_id} is already {record.status}; it cannot be started again.",
            )

        body = body or StartRunRequest()

        # On a single node the files are already here and this is a no-op. On
        # more than one, the upload may have landed on a different replica's
        # disk, so pull it back from object storage before reading.
        for stored in record.document_paths:
            ensure_local(f"uploads/{Path(stored).name}", stored)

        try:
            document = read_document(record.document_paths)
        except (FileNotFoundError, DocumentReadError) as exc:
            raise HTTPException(status_code=422, detail=f"Could not read the uploaded document: {exc}")

        # The workspace is allocated server-side from the run id. It used to come
        # from the request body, which let a caller point every agent tool and
        # the sandbox bind-mount at any directory on the host, including "/".
        try:
            workspace = allocate_workspace(run_id, body.workspace_label)
        except WorkspaceError as exc:
            raise HTTPException(status_code=500, detail=f"Could not prepare the workspace: {exc}")

        # Seeding happens before the repository context is built, so a brownfield
        # run reports the real branch and commit it was based on rather than the
        # "unknown" a blank directory yields.
        try:
            seeded = await run_in_threadpool(
                seed_workspace, workspace, body.source, resolve_upload=_resolve_upload
            )
        except SeedError as exc:
            # The caller's own input was rejected, so this is a 400, and the
            # message is the operator-facing reason.
            raise HTTPException(status_code=400, detail=str(exc))

        try:
            repository = build_repository_context(
                str(workspace), allow_subdirectories=body.allow_subdirectories
            )
        except RepositoryToolError as exc:
            raise HTTPException(status_code=500, detail=f"Could not prepare the workspace: {exc}")

        try:
            await runner.start_run(
                run_id,
                document,
                repository,
                # Omitted means "keep what the run was registered with". A clone
                # carries the source run's settings, and a Start button that sent
                # an empty body used to overwrite every one of them with a
                # default - turning an unattended run attended on start.
                review_policy=body.review_policy if body.review_policy is not None else record.review_policy,
                reviewer=body.reviewer or record.reviewer or user.username,
                auto_approve=record.auto_approve if body.auto_approve is None else body.auto_approve,
                model_overrides={
                    "llm_provider": body.llm_provider,
                    "openai_base_url": body.openai_base_url,
                    "model_name": body.model_name,
                },
            )
        except RunConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        record_audit(
            actor=user.username, tenant_id=user.tenant_id, action="run.start", subject=run_id,
            # `seeded.provenance` is built by the seeding module and carries a
            # redacted URL. The access token from the request is deliberately
            # not in it, and must not be added: this row is long-lived.
            detail={
                "auto_approve": record.auto_approve if body.auto_approve is None else body.auto_approve,
                "reviewer": body.reviewer,
                "workspace_source": seeded.provenance,
            },
        )
        return {"message": f"Run {run_id} started."}

    @runs.post("/{run_id}/resume", status_code=202)
    async def resume_run(
        run_id: str, user: UserInDB = Depends(require_operator)
    ) -> dict[str, str]:
        """Resume a failed run."""
        record = _require_run(runner, run_id, user)
        if record.status != "failed":
            raise HTTPException(
                status_code=409,
                detail=f"Run {run_id} is {record.status}; only failed runs can be resumed.",
            )
        try:
            await runner.resume_run(run_id)
        except RunConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        record_audit(actor=user.username, tenant_id=user.tenant_id, action="run.resume", subject=run_id)
        return {"message": f"Run {run_id} resumed."}

    @runs.post("/{run_id}/clone", status_code=201, response_model=CreateRunResponse)
    async def clone_run(
        run_id: str, user: UserInDB = Depends(require_operator)
    ) -> CreateRunResponse:
        """Create a new run from an existing run's documents.

        The clone carries the source run's settings as well. Cloning exists so
        an operator can repeat an attempt - for example after a run that died
        in a way it cannot be resumed from - and it is only useful if the new
        run behaves the same way: the same reviewer, the same review policy,
        the same model choices, and the same attended/unattended mode.
        """
        record = _require_run(runner, run_id, user)
        clone = runner.register_run(
            run_id=f"run-{uuid.uuid4()}",
            thread_id=f"thread-{uuid.uuid4()}",
            document_names=record.document_names,
            document_paths=record.document_paths,
            owner=user.username,
            tenant_id=user.tenant_id,
            review_policy=record.review_policy,
            reviewer=record.reviewer,
            auto_approve=record.auto_approve,
            model_overrides=record.model_overrides,
        )
        record_audit(
            actor=user.username, tenant_id=user.tenant_id, action="run.clone",
            subject=clone.run_id,
            detail={
                "cloned_from": run_id,
                "auto_approve": bool(record.auto_approve),
                "review_policy": record.review_policy,
            },
        )
        return CreateRunResponse(
            run_id=clone.run_id,
            thread_id=clone.thread_id,
            status=clone.status,
            created_at=clone.created_at,
        )

    # ------------------------------------------------------------------
    # Status, logs, artifacts
    # ------------------------------------------------------------------

    @runs.get("", response_model=RunListResponse)
    async def list_runs(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        user: UserInDB = Depends(get_current_active_user),
    ) -> RunListResponse:
        """List runs in the caller's tenant, newest first."""
        tenant = None if user.role == "admin" else user.tenant_id
        records = runner.run_store.list_all(tenant_id=tenant, limit=limit, offset=offset)
        return RunListResponse(
            runs=[
                RunSummary(
                    run_id=r.run_id,
                    status=r.status,
                    current_stage=r.current_stage,
                    created_at=r.created_at,
                    document_names=r.document_names,
                )
                for r in records
            ],
            total=runner.run_store.count(tenant),
        )

    @runs.get("/{run_id}", response_model=RunStatusResponse)
    async def get_run(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> RunStatusResponse:
        record = _require_run(runner, run_id, user)
        return await _build_status_response(record, runner)

    @runs.get("/{run_id}/stages")
    async def get_stages(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> dict[str, Any]:
        _require_run(runner, run_id, user)
        events = await event_bus.get_history(run_id)
        return {
            "run_id": run_id,
            "stages": [
                {
                    "stage": e.stage,
                    "meaning": e.message,
                    "timestamp": e.timestamp,
                    "sequence": e.sequence,
                }
                for e in events
                if e.event_type == "stage_change"
            ],
        }

    @runs.get("/{run_id}/artifacts")
    async def get_artifacts(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> dict[str, Any]:
        """List this run's artifacts: structured outputs plus workspace files."""
        record = _require_run(runner, run_id, user)
        return {"run_id": run_id, "artifacts": _collect_artifacts(record, runner)}

    @runs.get("/{run_id}/artifacts/download")
    async def download_artifact(
        run_id: str,
        path: str,
        user: UserInDB = Depends(get_current_active_user),
    ) -> Any:
        """Download one artifact belonging to this run.

        Two things changed here. The route is authenticated and tenant-scoped -
        it previously sat on a router mounted with no auth dependency at all.
        And the caller-supplied path is resolved *inside* the run's workspace and
        rejected if it escapes; absolute paths used to be passed straight to
        FileResponse, which made this an unauthenticated arbitrary file read.
        """
        record = _require_run(runner, run_id, user)

        logical_mapping = {
            "product-intake": "product_intake",
            "tools-and-models": "tools_models",
            "technical-specification": "technical_specification",
            "architecture-review": "architecture_review",
            "sprint-milestone": "milestone_plan",
            "milestone-review": "milestone_review",
        }
        state = record.graph_state(runner.checkpointer)
        logical_key = logical_mapping.get(path) or path.replace("-", "_")
        if state.get(logical_key) is not None:
            value = state[logical_key]
            if hasattr(value, "model_dump_json"):
                content = value.model_dump_json(indent=2)
            else:
                content = json.dumps(value, indent=2, default=str)
            return Response(content=content, media_type="application/json")
        if logical_key in logical_mapping.values():
            raise HTTPException(status_code=404, detail=f"Artifact '{path}' has not been generated yet.")

        if not record.repo_root:
            raise HTTPException(status_code=404, detail="This run has no workspace.")

        try:
            full_path = resolve_within_workspace(record.repo_root, path)
        except WorkspaceError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if not full_path.is_file():
            raise HTTPException(status_code=404, detail=f"Artifact not found: {path}")

        record_audit(
            actor=user.username, tenant_id=user.tenant_id, action="run.artifact.download",
            subject=run_id, detail={"path": path},
        )
        return FileResponse(
            full_path,
            filename=full_path.name,
            media_type="application/octet-stream",
        )

    @runs.get("/{run_id}/logs")
    async def get_logs(
        run_id: str,
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        user: UserInDB = Depends(get_current_active_user),
    ) -> dict[str, Any]:
        """Paginated log entries, paged in Redis rather than in Python."""
        _require_run(runner, run_id, user)
        total = await event_bus.history_length(run_id)
        page = await event_bus.get_history(run_id, offset=offset, limit=limit)
        return {
            "run_id": run_id,
            "total": total,
            "offset": offset,
            "limit": limit,
            "logs": [e.model_dump() for e in page],
        }

    # ------------------------------------------------------------------
    # Lifecycle controls
    # ------------------------------------------------------------------

    @runs.post("/{run_id}/cancel", status_code=200)
    async def cancel_run(
        run_id: str, user: UserInDB = Depends(require_operator)
    ) -> dict[str, str]:
        """Cancel a run: flags it and revokes the worker task."""
        record = _require_run(runner, run_id, user)
        if record.status in ("completed", "failed", "cancelled"):
            return {"message": f"Run {run_id} is already {record.status}.", "status": record.status}
        await runner.cancel_run(run_id)
        record_audit(actor=user.username, tenant_id=user.tenant_id, action="run.cancel", subject=run_id)
        return {"message": f"Run {run_id} cancelled.", "status": "cancelled"}

    @runs.delete("/{run_id}", status_code=200)
    async def delete_run(
        run_id: str, user: UserInDB = Depends(require_operator)
    ) -> dict[str, str]:
        """Delete a terminal run and everything it owns.

        Deletion cascades: uploads, workspace, checkpoints and event history all
        go. Previously only the metadata row was removed, so documents and
        checkpoints accumulated forever - which is also a data-retention problem,
        not just a disk one.
        """
        record = _require_run(runner, run_id, user)
        if record.status not in ("completed", "failed", "cancelled"):
            raise HTTPException(
                status_code=409,
                detail=f"Run {run_id} is {record.status}; only terminal runs can be deleted.",
            )

        # Uploads may be shared with a clone, so only remove files no other run
        # still references.
        for path in record.document_paths:
            if not runner.run_store.document_in_use(path, exclude_run_id=run_id):
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove upload %s", path, exc_info=True)

        if record.repo_root:
            try:
                delete_workspace(record.repo_root)
            except WorkspaceError:
                logger.warning("Refusing to delete workspace outside the configured root")

        # Compaction context is deliberately NOT deleted here. The summariser's
        # scratch space lives in per-agent directories (DATA_DIR/context/<agent_name>/),
        # not per run: the worker runs with concurrency > 1, so at the moment one
        # run ends its agent directory may still hold scratch data for another
        # active run, and deleting it would clobber that run's in-flight
        # compaction state. The files inside are small markdown summaries keyed
        # by a per-invocation session id; their slow accumulation is a known,
        # accepted limitation (see docs/context-compaction-remediation-steps.md).

        runner.discard_run_threads(record)
        await event_bus.purge(run_id)
        runner.run_store.delete(run_id)
        record_audit(actor=user.username, tenant_id=user.tenant_id, action="run.delete", subject=run_id)
        return {"message": f"Run {run_id} deleted."}

    # ------------------------------------------------------------------
    # Approvals and reviews
    # ------------------------------------------------------------------

    @runs.get("/{run_id}/approval")
    async def get_pending_approval(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> dict[str, Any]:
        """Return the pending approval, read from the checkpointer."""
        record = _require_run(runner, run_id, user)
        if record.status != "waiting_for_approval":
            return {"pending": False, "run_id": run_id}

        approval = record.graph_state(runner.checkpointer).get("pending_approval")
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
    async def submit_approval(
        run_id: str,
        body: ApprovalDecisionRequest,
        user: UserInDB = Depends(require_operator),
    ) -> dict[str, str]:
        """Record an approval decision. Only one can win."""
        _require_run(runner, run_id, user)
        decision = (
            approve_write_decision()
            if body.action == "approve"
            else reject_write_decision(body.reason or "Rejected by reviewer.")
        )
        try:
            await runner.submit_approval(run_id, decision)
        except RunConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        record_audit(
            actor=user.username, tenant_id=user.tenant_id, action=f"run.approval.{body.action}",
            subject=run_id, detail={"reason": body.reason},
        )
        return {"message": f"Approval decision '{body.action}' recorded for run {run_id}."}

    @runs.get("/{run_id}/review")
    async def get_pending_review(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> dict[str, Any]:
        record = _require_run(runner, run_id, user)
        if record.status != "waiting_for_review":
            return {"pending": False, "run_id": run_id}

        state = record.graph_state(runner.checkpointer)
        review = state.get("pending_review")
        review_point = str(state.get("stage", "")).removeprefix(REVIEW_PAUSE_PREFIX)
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
        comment: str | None = Form(None),
        file: UploadFile | None = File(None),
        user: UserInDB = Depends(require_operator),
    ) -> dict[str, str]:
        """Record a review decision, optionally with an edited artifact."""
        _require_run(runner, run_id, user)

        edited_content: str | None = None
        if file is not None and file.filename:
            raw = await file.read()
            if len(raw) > MAX_REVIEW_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Edited artifact exceeds the {MAX_REVIEW_UPLOAD_BYTES:,}-byte limit.",
                )
            try:
                edited_content = raw.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=400, detail="The edited artifact must be UTF-8 text."
                )

        if action == "approve":
            decision = approve_decision(comment=comment, edited_content=edited_content)
        elif action == "skip":
            decision = skip_decision()
        elif action == "changes":
            if not comment and not edited_content:
                raise HTTPException(
                    status_code=400,
                    detail="Requesting changes needs a comment saying what must change, "
                           "or an edited file.",
                )
            decision = request_changes_decision(
                comment or "Changes requested via an edited file.", edited_content=edited_content
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown review action: {action}")

        try:
            await runner.submit_review(run_id, decision)
        except RunConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        record_audit(
            actor=user.username, tenant_id=user.tenant_id, action=f"run.review.{action}",
            subject=run_id, detail={"has_comment": bool(comment), "has_edit": bool(edited_content)},
        )
        return {"message": f"Review decision '{action}' recorded for run {run_id}."}

    return runs


MAX_REVIEW_UPLOAD_BYTES = 2 * 1024 * 1024


_LOGICAL_ARTIFACTS = (
    ("product_intake", "Product Intake"),
    ("tools_models", "Tools and Models"),
    ("stack_selection", "Stack Selection"),
    ("technical_specification", "Technical Specification"),
    ("architecture_review", "Architecture Review"),
    ("security_review", "Security Review"),
    ("sprint_plan", "Sprint Plan"),
    ("milestone_plan", "Milestone Plan"),
    ("milestone_review", "Milestone Review"),
)

MAX_WORKSPACE_ARTIFACTS = 500


def _collect_artifacts(record: RunRecord, runner: WorkflowRunner) -> list[dict[str, Any]]:
    """Structured outputs plus files in this run's own workspace.

    Scoped to the run's workspace and bounded. The previous implementation walked
    the entire repository root with `rglob("*.md")` on every status request,
    pruning only `.git` and `node_modules` - so it recursed through `.venv` and
    `site-packages`, synchronously, on the event loop.
    """
    state = record.graph_state(runner.checkpointer)
    artifacts: list[dict[str, Any]] = [
        {"key": key, "label": label, "kind": "structured", "present": True}
        for key, label in _LOGICAL_ARTIFACTS
        if state.get(key) is not None
    ]
    for name in state.get("specialist_outputs", {}):
        artifacts.append({"key": name, "label": f"Specialist: {name}", "kind": "structured", "present": True})

    if record.repo_root:
        workspace = Path(record.repo_root)
        if workspace.is_dir():
            from app.tools.repository import list_repository_files

            try:
                for relative in list_repository_files(workspace)[:MAX_WORKSPACE_ARTIFACTS]:
                    artifacts.append(
                        {"key": relative, "label": relative, "kind": "file", "present": True}
                    )
            except Exception:  # noqa: BLE001 - a listing failure must not break status
                logger.warning("Could not list workspace for run %s", record.run_id, exc_info=True)
    return artifacts


def _derive_stages(events: list[Any], current_stage: str | None) -> list[dict[str, Any]]:
    """Build the execution timeline from this run's `stage_change` history.

    `stages` was returned as a hardcoded empty list, so the dashboard's flow
    chart fell through to a fallback that fabricates a single node from
    `current_stage` - which is why a run that had finished three stages showed
    one.

    One entry per distinct stage, in the order first seen, carrying the duration
    to the next transition. A stage that repeats (the specialist loop, a review
    revision) increments `retry_count` rather than adding a second node, so the
    chart stays a readable spine instead of growing a row per iteration.
    """
    from datetime import datetime

    def _parsed(value: str):
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    ordered: list[dict[str, Any]] = []
    by_name: dict[str, dict[str, Any]] = {}

    for event in events:
        if event.event_type != "stage_change":
            continue
        name = event.stage or ""
        if not name:
            continue
        existing = by_name.get(name)
        if existing is not None:
            existing["retry_count"] += 1
            existing["meaning"] = event.message
            existing["ended_at"] = None
            continue
        entry = {
            "name": name,
            "meaning": event.message,
            "started_at": event.timestamp,
            "ended_at": None,
            "status": str(event.metadata.get("status") or "running"),
            "duration_seconds": None,
            "retry_count": 0,
        }
        by_name[name] = entry
        ordered.append(entry)

    # A stage ended when the next one began. The last stays open.
    for earlier, later in zip(ordered, ordered[1:]):
        earlier["ended_at"] = later["started_at"]
        start, end = _parsed(earlier["started_at"]), _parsed(later["started_at"])
        if start and end:
            earlier["duration_seconds"] = max((end - start).total_seconds(), 0.0)
        if earlier["status"] not in {"failed", "cancelled"}:
            earlier["status"] = "completed"

    return ordered


async def _build_status_response(record: RunRecord, runner: WorkflowRunner) -> RunStatusResponse:
    """Assemble the full status payload for one run."""
    # Derived from the event history rather than stored: the history is already
    # the authority on what ran, and a second source would drift from it.
    try:
        history = await runner.event_bus.get_history(record.run_id)
        stages = _derive_stages(history, record.current_stage)
    except Exception:  # noqa: BLE001 - a timeline is never worth failing a status call for
        stages = []

    state = record.graph_state(runner.checkpointer)

    reviews = []
    for point, review in (state.get("reviews") or {}).items():
        status_value = getattr(review, "status", None)
        reviews.append(
            ReviewInfo(
                point=point,
                status=status_value.value if hasattr(status_value, "value") else str(status_value),
                reviewer=getattr(review, "reviewer", "unassigned"),
                revision=getattr(review, "revision", 1),
                comments="\n".join(getattr(review, "comments", []) or []) or None,
                updated_at=getattr(review, "updated_at", record.updated_at),
            )
        )

    remediation = None
    cycle = state.get("remediation")
    if cycle is not None:
        remediation = RemediationInfo(
            attempt=cycle.attempt,
            max_attempts=cycle.max_attempts,
            escalated=cycle.escalated,
            defect_count=len(cycle.defects),
            test_runs=len(cycle.test_runs),
        )

    artifacts = [
        ArtifactInfo(
            path=item["key"],
            kind=item["kind"],
            revision=1,
            created_by="workflow",
            stage=record.current_stage or "",
        )
        for item in _collect_artifacts(record, runner)
    ]

    return RunStatusResponse(
        run_id=record.run_id,
        thread_id=record.thread_id,
        status=record.status,
        current_stage=record.current_stage,
        stage_meaning=record.stage_meaning or _stage_meaning(record.current_stage),
        created_at=record.created_at,
        updated_at=record.updated_at,
        stages=stages,
        artifacts=artifacts,
        reviews=reviews,
        remediation=remediation,
        error=record.error,
    )


__all__ = ["create_runs_router"]
