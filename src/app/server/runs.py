"""Run lifecycle and management API endpoints.

Steps 6.1, 6.2, and 6.4 of the workflow plan.  This router handles the
full lifecycle of a workflow run: create, start, observe, decide, cancel.

The browser is an observer and controlled input surface.  It never
directly mutates workflow state — every decision goes through the server,
which validates it and resumes the LangGraph thread.
"""

from __future__ import annotations

import asyncio
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
from app.server.events import EventBus, RunEvent
from pathlib import Path

from app.server.models import (
    RunCostSummary,
    ApprovalDecisionRequest,
    ArtifactInfo,
    RemediationInfo,
    ReviewInfo,
    ApprovalPayload,
    CodebaseUploadResponse,
    CreateRunResponse,
    ReviewDecisionRequest,
    ReviewPayload,
    ModelPinRequest,
    ModelSummary,
    RunNameRequest,
    RewindRequest,
    RunListResponse,
    RunStatusResponse,
    RunSummary,
    RunUsage,
    EventPage,
    BriefPreview,
    BriefPreviewRequest,
    OwnerRating,
    OwnerRatingRequest,
    PreviewCriterion,
    SprintsResponse,
    SpinnerResponse,
    StartRunRequest,
    SprintRevision,
    SteeringNote,
    WizardModel,
    WizardNote,
    WizardReview,
    WizardSection,
    WizardStep,
    WizardSummary,
)
from app.server.runner import (
    RESUMABLE_STATUSES,
    RunRecord,
    WorkflowRunner,
    _api_status,
    _max_run_cost_usd,
    _max_run_tokens,
    _stage_meaning,
)
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


def _the_pin_target(pinned: bool, base_url: str | None, model: str | None) -> tuple[str | None, str | None]:
    """(address, model name) to pin a run to, validated; (None, None) for the model it is on. HTTP 422 when refused.

    An address must be http or https with no credentials in it, and a model name must not be empty: nothing
    secret is accepted here, the endpoint's key is resolved server-side.
    """
    from app.models import model_pin

    if (base_url is not None or model is not None) and not pinned:
        raise HTTPException(status_code=422, detail="An address or a model name can only be given when pinning.")
    try:
        return (
            model_pin.clean_base_url(base_url) if base_url is not None else None,
            model_pin.clean_model_name(model) if model is not None else None,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


def _a_completed_run_s_workspace(runner: WorkflowRunner, run_id: str, user: UserInDB) -> Path | None:
    """The workspace of a completed run the caller may see, or None (plan BW.2)."""
    record = runner.run_store.load(run_id)
    if record is None or record.status != "completed" or not record.repo_root:
        return None
    if user.role != "admin" and record.tenant_id != user.tenant_id:
        return None
    return Path(record.repo_root)


def _support_tier_of(root: Any) -> str:
    """How well this run's stack is covered by the harness's own checks (pack-supported, custom, unverified); "" if unknown."""
    try:
        from app.stacks import contract, pack_named, support_tier

        record = contract.read(root) or {}
        return support_tier(pack_named(str(record.get("pack") or ""))) if record.get("pack") else ""
    except Exception:  # noqa: BLE001 - the evidence page works without it
        return ""


def _how_many_criteria_hold(record: Any) -> dict[str, int | None]:
    """The criteria passing and the criteria there are, from the last measured suite; None for each before there is one."""
    none: dict[str, int | None] = {"criteria_proven": None, "criteria_total": None}
    root = getattr(record, "repo_root", None)
    if not root:
        return none
    try:
        from app.acceptance import suite

        criteria = (suite.last_result(root) or {}).get("criteria") or {}
    except Exception:  # noqa: BLE001 - a list must not fail over one run's measurement
        return none
    if not criteria:
        return none
    return {
        "criteria_proven": sum(1 for c in criteria.values() if c.get("status") == "passed"),
        "criteria_total": len(criteria),
    }


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

    @runs.get("/{run_id}/rating", response_model=OwnerRating | None)
    async def get_rating(run_id: str, user: UserInDB = Depends(get_current_active_user)) -> dict | None:
        """The owner's rating of the delivered run, or null (plan EV.1)."""
        from app.server import ratings

        _require_run(runner, run_id, user)
        return ratings.read(run_id)

    @runs.put("/{run_id}/rating", response_model=OwnerRating)
    async def rate_run(
        run_id: str, body: OwnerRatingRequest, user: UserInDB = Depends(require_operator)
    ) -> dict:
        """Rate a delivered run 1-5 with a line; rating again replaces it (plan EV.1)."""
        from app.server import ratings

        record = _require_run(runner, run_id, user)
        if record.status != "completed":
            raise HTTPException(status_code=409, detail=f"Run {run_id} is {record.status}; only a delivered run is rated.")
        rating = ratings.save(run_id, body.score, body.note, user.username)
        record_audit(actor=user.username, tenant_id=user.tenant_id, action="run.rated",
                     subject=run_id, detail={"score": body.score})
        return rating

    @runs.post("/preview", response_model=BriefPreview)
    async def preview_brief(
        body: BriefPreviewRequest, user: UserInDB = Depends(get_current_active_user)
    ) -> BriefPreview:
        """The acceptance criteria a brief gives a run, before it starts: the same numbering, no model call (plan BG.10)."""
        from app.acceptance.criteria import from_brief, number

        from app.acceptance.ambiguity import criteria_without_an_interface_line, vague_phrases

        listed = len(from_brief(body.brief)) >= 2
        found = number(body.brief) if listed else []
        return BriefPreview(
            criteria=[PreviewCriterion(id=c.id, text=c.text) for c in found], from_brief=listed,
            # How much the run would guess, seen before it starts (plan IN.2).
            without_an_interface_line=criteria_without_an_interface_line(body.brief, found),
            vague_phrases=vague_phrases(body.brief),
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

        # A run pinned to an endpoint of its own is refused before anything is prepared if that is not an address
        # or a model name worth pinning to.
        pin_base_url, pin_model_name = _the_pin_target(body.pin_model, body.pin_base_url, body.pin_model_name)

        # Asked for the frontier model, it must be there and answering before
        # anything is prepared (owner, 2026-10-19): otherwise the run's
        # specification and reviews would quietly run on the local model, or it
        # would fail at its first judgement stage. Omitted keeps the run on
        # whatever is configured, as before.
        if body.use_frontier_model is True:
            from app.models.frontier_check import check_frontier

            frontier = await asyncio.to_thread(check_frontier)
            if frontier["problem"]:
                raise HTTPException(status_code=409, detail=frontier["problem"])

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
            workspace = allocate_workspace(run_id, body.workspace_label, user.tenant_id)
        except WorkspaceError as exc:
            raise HTTPException(status_code=500, detail=f"Could not prepare the workspace: {exc}")

        # Seeding happens before the repository context is built, so a brownfield
        # run reports the real branch and commit it was based on rather than the
        # "unknown" a blank directory yields.
        try:
            seeded = await run_in_threadpool(
                seed_workspace, workspace, body.source, resolve_upload=_resolve_upload,
                resolve_run=lambda finished_id: _a_completed_run_s_workspace(runner, finished_id, user),
            )
        except SeedError as exc:
            # The caller's own input was rejected, so this is a 400, and the
            # message is the operator-facing reason.
            raise HTTPException(status_code=400, detail=str(exc))

        # After seeding, never before it: a `git clone` needs to own an empty
        # directory, and initialising at allocation broke every brownfield run.
        # A seeded codebase that is already a repository keeps its own history;
        # this only adds one where there is none, so that each accepted
        # milestone has somewhere to be recorded.
        from app.tools.version_control import initialise_repository

        await run_in_threadpool(initialise_repository, workspace)

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
                delivery_mode=body.delivery_mode,
                use_frontier_model=body.use_frontier_model,
                approval_timeout_minutes=body.approval_timeout_minutes,
                pin_model=body.pin_model,
                pin_base_url=pin_base_url,
                pin_model_name=pin_model_name,
            )
        except RunConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        if body.name and " ".join(body.name.split()):
            await asyncio.to_thread(lambda: runner.run_store.set_run_name(run_id, " ".join(body.name.split())[:80]))

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
        """Resume a failed, paused, budget-paused or cancelled run from its last checkpoint."""
        record = _require_run(runner, run_id, user)
        # A run parked at its spending ceiling is not failed - it is waiting for
        # someone to decide whether to keep paying. Refusing to resume it here
        # would leave the only pause in the system with no way out but cancel.
        # A run its owner paused, or cancelled, keeps its checkpoints too.
        resumable = RESUMABLE_STATUSES
        if record.status not in resumable:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Run {run_id} is {record.status}; only {' or '.join(resumable)} "
                    "runs can be resumed."
                ),
            )
        try:
            await runner.resume_run(run_id)
        except RunConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        record_audit(actor=user.username, tenant_id=user.tenant_id, action="run.resume", subject=run_id)
        return {"message": f"Run {run_id} resumed."}

    @runs.get("/{run_id}/rewind-points")
    async def rewind_points(
        run_id: str, user: UserInDB = Depends(require_operator)
    ) -> dict[str, Any]:
        """Each stage the run started, oldest first, as a point to rewind it to."""
        _require_run(runner, run_id, user)
        return {"points": await runner.rewind_points(run_id)}

    @runs.post("/{run_id}/rewind", status_code=202)
    async def rewind_run(
        run_id: str, payload: RewindRequest, user: UserInDB = Depends(require_operator)
    ) -> dict[str, Any]:
        """Rewind a stopped run to the start of a stage, with its files as they were, and run it from there."""
        from app.graph.workflow import RewindError

        _require_run(runner, run_id, user)
        try:
            done = await runner.rewind_run(run_id, payload.checkpoint_id)
        except RunConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except RewindError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        record_audit(
            actor=user.username, tenant_id=user.tenant_id, action="run.rewind", subject=run_id,
        )
        return {"message": f"Run {run_id} rewound to {done['stage']} and resumed.", **done}

    @runs.post("/{run_id}/pause", status_code=202)
    async def pause_run(
        run_id: str, user: UserInDB = Depends(require_operator)
    ) -> dict[str, str]:
        """Pause a running run at its next stage boundary; resume continues it."""
        _require_run(runner, run_id, user)
        try:
            await runner.pause_run(run_id)
        except RunConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        record_audit(actor=user.username, tenant_id=user.tenant_id, action="run.pause", subject=run_id)
        return {"message": f"Run {run_id} is pausing."}

    @runs.post("/{run_id}/name")
    async def name_run(
        run_id: str, payload: RunNameRequest, user: UserInDB = Depends(require_operator)
    ) -> dict[str, Any]:
        """Give the run a name to tell it from the others in the list, or clear it with an empty name."""
        _require_run(runner, run_id, user)
        name = " ".join(payload.name.split())[:80]
        changed = await asyncio.to_thread(lambda: runner.run_store.set_run_name(run_id, name or None))
        if not changed:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
        record_audit(
            actor=user.username, tenant_id=user.tenant_id, action="run.name", subject=run_id, detail={"name": name},
        )
        return {"run_id": run_id, "run_name": name or None}

    @runs.post("/{run_id}/model-pin")
    async def pin_run_model(
        run_id: str, payload: ModelPinRequest, user: UserInDB = Depends(require_operator)
    ) -> dict[str, Any]:
        """Keep the run on the model it last ran on, or let it follow the current model settings again.

        Works at any time, mid-run included: a request already sent finishes where it was sent, and every new
        one asks which model the run is on. With `base_url` and/or `model` the run is pinned to that endpoint
        instead (the global settings are not touched); no credential is accepted or stored.
        """
        from app.models import model_pin
        from app.server.runtime_settings import global_model_snapshot

        _require_run(runner, run_id, user)
        base_url, model_name = _the_pin_target(payload.pinned, payload.base_url, payload.model)
        store = runner.run_store
        explicit = None
        if base_url or model_name:
            # The settings as they are now, with just these two replaced: the provider stays, no key is stored.
            explicit = model_pin.snapshot_for(global_model_snapshot(), base_url, model_name)
        # A run with no recorded model (it began before the pin existed) is pinned to what the settings name now.
        changed = await asyncio.to_thread(
            lambda: store.set_model_pin(
                run_id, payload.pinned, last=explicit, if_unknown=global_model_snapshot() if payload.pinned else None
            )
        )
        if not changed:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
        model_pin.forget(run_id)
        record_audit(
            actor=user.username, tenant_id=user.tenant_id, action="run.model_pin", subject=run_id,
            detail={"pinned": payload.pinned, "base_url": base_url, "model": model_name},
        )
        state = await asyncio.to_thread(store.model_state, run_id)
        return {
            "model_pinned": bool(state and state[0]),
            "model_last": model_pin.summary_of(state[1] if state else None),
        }

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
        pins = _the_model_pins([r.run_id for r in records], runner)
        names = runner.run_store.run_names([r.run_id for r in records])
        return RunListResponse(
            runs=[
                RunSummary(
                    run_id=r.run_id,
                    status=r.status,
                    current_stage=r.current_stage,
                    created_at=r.created_at,
                    document_names=r.document_names,
                    updated_at=getattr(r, "updated_at", None),
                    delivery_mode=getattr(r, "delivery_mode", None),
                    local_only=getattr(r, "local_only", None),
                    completion_gaps=len(getattr(r, "completion_gaps", None) or []),
                    gate_deadline=_when_the_gate_approves_itself(r),
                    **pins.get(r.run_id, {}),
                    run_name=names.get(r.run_id),
                    **_how_many_criteria_hold(r),
                )
                for r in records
            ],
            total=runner.run_store.count(tenant),
        )

    @runs.get("/compare")
    async def compare_runs(
        a: str, b: str, user: UserInDB = Depends(get_current_active_user)
    ) -> dict[str, Any]:
        """Two runs' KPIs side by side, each change marked worse by the ledger's rule (plan UI-S6).

        Declared before `/{run_id}`, which would otherwise take "compare" for a run.
        """
        from app.observability.run_kpis import kpis, worse
        from app.observability.transcript import read_transcript

        _require_run(runner, a, user)
        _require_run(runner, b, user)
        first, second = await asyncio.gather(
            asyncio.to_thread(read_transcript, a), asyncio.to_thread(read_transcript, b)
        )
        left, right = kpis(first), kpis(second)
        rows = []
        for key in sorted(set(left) & set(right)):
            x, y = left[key], right[key]
            if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                continue
            rows.append({
                "key": key, "a": x, "b": y,
                "change": None if x == 0 else round((y - x) / abs(x), 4),
                "worse": worse(key, float(x), float(y)),
            })
        return {"a": a, "b": b, "rows": rows}

    @runs.get("/outcomes")
    async def run_outcomes(user: UserInDB = Depends(get_current_active_user)) -> dict[str, Any]:
        """Finished runs with their time and score, and the typical time per delivery mode."""
        from app.server.outcomes import forecast, outcomes

        records = runner.run_store.list_all(
            tenant_id=None if user.role == "admin" else user.tenant_id, limit=500,
        )
        rows = outcomes(records)
        return {
            "runs": rows,
            "forecast": {mode: forecast(rows, mode) for mode in ("fast", "thorough")},
        }

    @runs.get("/{run_id}", response_model=RunStatusResponse)
    async def get_run(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> RunStatusResponse:
        record = _require_run(runner, run_id, user)
        return await _build_status_response(record, runner)

    @runs.get("/{run_id}/sprints", response_model=SprintsResponse)
    async def get_sprints(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> SprintsResponse:
        """The run's sprints as figures, from the attempts each sprint summary is rendered from (plan BG.6)."""
        from app.agents.sprint_summary import sprint_views
        from app.graph.workflow import the_attempt_in_progress

        record = _require_run(runner, run_id, user)
        state = record.graph_state(runner.checkpointer)
        # A live run's current sprint is the attempt under way, not the one it
        # last recorded; a finished run has none under way.
        live = record.status not in ("completed", "failed", "cancelled") and state.get("sprint_plan")
        return SprintsResponse(
            sprints=sprint_views(
                state.get("sprint_plan"),
                state.get("sprint_attempts") or [],
                the_attempt_in_progress(state) if live else None,
            )
        )

    @runs.get("/{run_id}/usage", response_model=RunUsage)
    async def get_usage(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> RunUsage:
        """Time, tokens and failures per stage, from the run's transcript (plan BG.7)."""
        from app.observability.stage_usage import recent_calls, stage_usage
        from app.observability.transcript import read_transcript

        _require_run(runner, run_id, user)
        entries = await asyncio.to_thread(read_transcript, run_id)
        return RunUsage(stages=stage_usage(entries), recent_calls=recent_calls(entries))

    @runs.get("/{run_id}/kpis")
    async def get_kpis(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> dict[str, Any]:
        """The run's KPIs from its transcript, as the loop's ledger keeps them (plan UI-S6)."""
        from app.observability.run_kpis import kpis
        from app.observability.transcript import read_transcript

        _require_run(runner, run_id, user)
        entries = await asyncio.to_thread(read_transcript, run_id)
        return {"run": run_id, **kpis(entries)}

    @runs.get("/{run_id}/transcript")
    async def download_transcript(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> Response:
        """The run's whole transcript as text: every model call, reply, tool call and result."""
        from app.observability.transcript import render_transcript

        _require_run(runner, run_id, user)
        text = await asyncio.to_thread(render_transcript, run_id)
        record_audit(
            actor=user.username, tenant_id=user.tenant_id, action="run.transcript.download",
            subject=run_id, detail={},
        )
        return Response(
            content=text,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{run_id}-transcript.txt"'},
        )

    @runs.get("/{run_id}/wizard", response_model=WizardModel)
    async def get_wizard(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> WizardModel:
        """The guided-wizard view of a run: phases, steps, revisions and the
        review outcomes that closed them.

        Built server-side from the event history (see `build_wizard_model`),
        so every client renders the same structure instead of each deriving it
        on its own."""
        record = _require_run(runner, run_id, user)
        return await build_wizard_model(record, runner)

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

        logical_mapping = _REVIEW_OUTPUTS
        path = _REVIEW_DOCUMENTS.get(path, path)
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

    @runs.get("/{run_id}/artifacts/diff")
    async def get_document_diff(
        run_id: str, path: str, user: UserInDB = Depends(get_current_active_user)
    ) -> dict[str, Any]:
        """What changed in one workspace document since its version before (plan BG.3)."""
        from app.server.changes import ChangesUnavailable, document_diff

        record = _require_run(runner, run_id, user)
        if not record.repo_root:
            raise HTTPException(status_code=404, detail="This run has no workspace.")
        try:
            full_path = resolve_within_workspace(record.repo_root, path)
        except WorkspaceError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        relative = full_path.relative_to(Path(record.repo_root).resolve()).as_posix()
        try:
            return await asyncio.to_thread(document_diff, record.repo_root, relative)
        except ChangesUnavailable as error:
            return {"path": relative, "since": None, "since_at": None, "diff": "", "truncated": False, "problem": str(error)}

    @runs.get("/{run_id}/handover")
    async def download_handover(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> Any:
        """The run's handover pack: its documents, decisions and acceptance suite, as one zip."""
        from app.sprint.handover import build

        record = _require_run(runner, run_id, user)
        if not record.repo_root or not Path(record.repo_root).is_dir():
            raise HTTPException(status_code=404, detail="This run has no workspace.")
        record_audit(
            actor=user.username, tenant_id=user.tenant_id, action="run.handover.download",
            subject=run_id, detail={},
        )
        return Response(
            content=build(record.repo_root, run_id),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{run_id}-handover.zip"'},
        )

    @runs.get("/{run_id}/logs", response_model=EventPage)
    async def get_logs(
        run_id: str,
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        user: UserInDB = Depends(get_current_active_user),
    ) -> EventPage:
        """Paginated log entries, paged in Redis rather than in Python.

        Typed (plan UI-S4): the event's schema is published with the API, so the
        page's type of it is generated and a new event type reaches the page's
        build, not a blank row.
        """
        _require_run(runner, run_id, user)
        total = await event_bus.history_length(run_id)
        page = await event_bus.get_history(run_id, offset=offset, limit=limit)
        return EventPage(run_id=run_id, total=total, offset=offset, limit=limit, logs=list(page))

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
        go, and so do the transcript, ledger, journal and stored copies - see
        `app.server.run_retention` for the full contract. Previously only the
        metadata row was removed, so documents and checkpoints accumulated
        forever - which is also a data-retention problem, not just a disk one.
        """
        record = _require_run(runner, run_id, user)
        if record.status not in ("completed", "failed", "cancelled"):
            raise HTTPException(
                status_code=409,
                detail=f"Run {run_id} is {record.status}; only terminal runs can be deleted.",
            )

        # Uploads may be shared with a clone, so only remove files no other run
        # still references.
        unshared = []
        for path in record.document_paths:
            if not runner.run_store.document_in_use(path, exclude_run_id=run_id):
                unshared.append(path)
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove upload %s", path, exc_info=True)

        from app.server.run_retention import purge_run_records

        purge_run_records(run_id, record.repo_root, unshared)

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
        # accepted limitation, recorded when context compaction was remediated.

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
        record = _require_run(runner, run_id, user)
        decision = (
            approve_write_decision()
            if body.action == "approve"
            else reject_write_decision(body.reason or "Rejected by reviewer.")
        )
        try:
            await runner.submit_approval(run_id, decision)
        except RunConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        # Same rationale as the review event above: a manual approval is a
        # fact about the run and belongs in its history. Auto-approvals are
        # already recorded (approval_auto); these were the missing half.
        stage = str(record.current_stage or "").removeprefix(APPROVAL_PAUSE_PREFIX)
        await event_bus.publish(
            run_id,
            RunEvent(
                run_id=run_id,
                sequence=await event_bus.next_sequence(run_id),
                stage=stage or record.current_stage or "",
                event_type="approval_decision",
                message=f"Approval decision: {body.action}"
                + (f" — {body.reason}" if body.reason else ""),
                metadata={"action": body.action},
            ),
        )

        record_audit(
            actor=user.username, tenant_id=user.tenant_id, action=f"run.approval.{body.action}",
            subject=run_id, detail={"reason": body.reason},
        )
        return {"message": f"Approval decision '{body.action}' recorded for run {run_id}."}

    @runs.get("/{run_id}/decisions")
    async def get_decisions(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> dict[str, Any]:
        """Every decision the run has taken, who took it and why (`app.decisions`)."""
        record = _require_run(runner, run_id, user)
        state = record.graph_state(runner.checkpointer)
        decisions = [d for d in (state.get("decisions") or []) if isinstance(d, dict)]
        return {"run_id": run_id, "decisions": decisions}

    @runs.get("/{run_id}/evidence")
    async def get_evidence(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> dict[str, Any]:
        """What a reviewer is shown: the acceptance suite's last measured result,
        the screenshots it kept, and the review pages written so far."""
        record = _require_run(runner, run_id, user)
        if not record.repo_root:
            return {"run_id": run_id, "acceptance": {}, "screenshots": [], "pages": []}
        from app.acceptance import suite
        from app.ci import first_passes
        from app.graph.delivery import screenshots

        root = Path(record.repo_root)
        pages = sorted(
            path.relative_to(root).as_posix()
            for path in (root / "docs" / "reviews").glob("*.md")
        ) if (root / "docs" / "reviews").is_dir() else []
        return {
            "run_id": run_id,
            "acceptance": suite.last_result(root),
            "deferred": suite.deferred(root),
            "change_requests": suite.change_requests(root),
            "screenshots": screenshots(root),
            "pages": pages,
            # What the release knew it did not prove, and how well the stack's own checks cover it.
            "completion_gaps": [str(gap) for gap in (getattr(record, "completion_gaps", None) or [])],
            "support_tier": _support_tier_of(root),
            # Each criterion's first passing test, after which step and when (plan BG.9).
            "first_passed": first_passes(root),
        }

    @runs.get("/{run_id}/changes")
    async def get_changes(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> dict[str, Any]:
        """The run's workspace history, newest first, with the files each commit touched."""
        from app.server.changes import ChangesTookTooLong, ChangesUnavailable, commits

        record = _require_run(runner, run_id, user)
        if not record.repo_root:
            return {"run_id": run_id, "commits": []}
        try:
            # Off the event loop: git can take seconds on a large history.
            return {"run_id": run_id, "commits": await asyncio.to_thread(commits, record.repo_root)}
        except ChangesTookTooLong as error:
            raise HTTPException(status_code=504, detail=str(error)) from error
        except ChangesUnavailable as error:
            return {"run_id": run_id, "commits": [], "problem": str(error)}

    @runs.get("/{run_id}/changes/{sha}")
    async def get_change(
        run_id: str, sha: str, user: UserInDB = Depends(get_current_active_user)
    ) -> dict[str, Any]:
        """One commit's diff in the run's workspace."""
        from app.server.changes import ChangesTookTooLong, ChangesUnavailable, diff

        record = _require_run(runner, run_id, user)
        if not record.repo_root:
            raise HTTPException(status_code=404, detail="This run has no workspace yet.")
        try:
            return {"run_id": run_id, **await asyncio.to_thread(diff, record.repo_root, sha)}
        except ChangesTookTooLong as error:
            raise HTTPException(status_code=504, detail=str(error)) from error
        except ChangesUnavailable as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @runs.get("/{run_id}/steering")
    async def get_steering(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> dict[str, Any]:
        """The notes the owner sent this run while it ran."""
        from app.server.steering import notes

        record = _require_run(runner, run_id, user)
        return {"run_id": run_id, "notes": notes(record.repo_root) if record.repo_root else []}

    @runs.post("/{run_id}/steering", status_code=201)
    async def post_steering(
        run_id: str, body: SteeringNote, user: UserInDB = Depends(get_current_active_user)
    ) -> dict[str, Any]:
        """Give a running run a direction its next model calls carry."""
        from app.server.steering import add

        record = _require_run(runner, run_id, user)
        if not record.repo_root or record.status in ("completed", "failed", "cancelled"):
            raise HTTPException(status_code=409, detail="Only a run that is still going can be steered.")
        if record.status in ("paused", "waiting_for_budget"):
            # A note on a run that is not running reaches nothing until it is
            # resumed, and the owner reads "sent" as "followed" (Initiative AS).
            raise HTTPException(status_code=409, detail="This run is paused. Resume it first, then send the direction.")
        try:
            return {"run_id": run_id, "note": add(record.repo_root, body.text, user.username, body.scope)}
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

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
            document=_the_review_document(record.repo_root, review.artifact_id if review else ""),
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
        record = _require_run(runner, run_id, user)

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

        # The decision is now a fact in the event history. Before this event
        # existed, "was the review approved or sent back" was only implied by
        # whichever stage ran next, and every timeline re-derived it separately.
        state = record.graph_state(runner.checkpointer)
        review_point = str(state.get("stage", "")).removeprefix(REVIEW_PAUSE_PREFIX)
        await event_bus.publish(
            run_id,
            RunEvent(
                run_id=run_id,
                sequence=await event_bus.next_sequence(run_id),
                stage=review_point or record.current_stage or "",
                event_type="review_decision",
                message=f"Review decision: {action}" + (f" — {comment}" if comment else ""),
                metadata={
                    "action": action,
                    "review_point": review_point,
                    "has_comment": bool(comment),
                    "has_edit": bool(edited_content),
                },
            ),
        )

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


#: Events that mean "this stage was allowed to act", as opposed to any other
#: event it happened to emit. Counting the latter reported 203 approvals for a
#: stage that passed 35 gates.
_APPROVAL_EVENTS = frozenset({"approval_auto", "approval_request", "approval_decision"})


def _derive_stages(events: list[Any], current_stage: str | None) -> list[dict[str, Any]]:
    """Build the execution timeline from this run's `stage_change` history.

    Three things this has to get right, each of which it previously got wrong.

    **A pause is not a stage.** `stage_change` events carry the
    `awaiting_approval:` prefix, and the UI strips it for display - so every
    gated stage rendered twice under the same title, once as itself and once as
    its own pause. The pause row is folded into its parent here.

    **An approval is not a retry.** A gated stage bounces
    `X -> awaiting_approval:X -> X` on every single approval, and each bounce
    incremented `retry_count`. A run whose authoritative retry count was 2 was
    telling the operator "retried 66 times" - it was counting gates. They are
    now separate numbers, because they mean opposite things: approvals are the
    stage working, retries are the stage starting over.

    **A stage name is not unique.** `technical_lead`, `test_round_0` and every
    specialist recur once per sprint. Keyed by name alone they collapsed into
    one row whose duration and counts summed across sprints. Entries are keyed
    by `(sprint, name)` and carry the sprint, so the timeline can group.
    """
    from datetime import datetime

    def _parsed(value: str):
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    ordered: list[dict[str, Any]] = []
    by_key: dict[tuple[int, str], dict[str, Any]] = {}
    sprint = 0
    previous: str | None = None

    for event in events:
        # Every event carries the stage that produced it, and only pauses emit
        # `stage_change` - the runner publishes one per gate, so a timeline
        # built from those alone showed 8 of one run's 17 stages and none
        # of the planning or review. Reading the stage off all events costs
        # nothing and shows the run that actually happened.
        raw = event.stage or ""
        if not raw:
            continue

        paused = raw.startswith(APPROVAL_PAUSE_PREFIX)
        name = raw[len(APPROVAL_PAUSE_PREFIX):] if paused else raw
        if not name:
            continue

        # Each planning stage opens a sprint. The stages before the first one
        # are the run's preamble, which the UI shows as sprint 0.
        if name == "technical_lead" and previous != "technical_lead":
            sprint += 1
        key = (sprint, name)
        existing = by_key.get(key)

        approved = event.event_type in _APPROVAL_EVENTS

        if existing is not None:
            if approved:
                # The stage asked to do something and was allowed to. Progress,
                # not repetition - and the number the old code reported as
                # "retries".
                existing["approval_count"] += 1
            elif previous != name:
                # Re-entered after another stage ran: this one is starting over.
                # A structured-response retry does not appear here, because it
                # re-enters the same stage on a fresh conversation and the stage
                # name never changes; the runner's log is authoritative for those.
                existing["retry_count"] += 1
            if event.event_type == "stage_change" and event.message:
                existing["meaning"] = event.message
            existing["ended_at"] = None
            previous = name
            continue

        entry = {
            "name": name,
            "sprint": sprint,
            # Empty, not None: `RunStage.meaning` is a string, and a stage
            # whose first event is a tool call rather than a `stage_change` has
            # no narration yet. Returning None here failed validation for every
            # such stage and took the whole run-detail endpoint down with a 500.
            "meaning": event.message if event.event_type == "stage_change" else "",
            "started_at": event.timestamp,
            "ended_at": None,
            "status": str((event.metadata or {}).get("status") or "running"),
            "duration_seconds": None,
            "retry_count": 0,
            "approval_count": 1 if approved else 0,
        }
        by_key[key] = entry
        ordered.append(entry)
        previous = name

    # A stage ended when the next one began. The last stays open.
    for earlier, later in zip(ordered, ordered[1:]):
        earlier["ended_at"] = later["started_at"]
        start, end = _parsed(earlier["started_at"]), _parsed(later["started_at"])
        if start and end:
            earlier["duration_seconds"] = max((end - start).total_seconds(), 0.0)
        if earlier["status"] not in {"failed", "cancelled"}:
            earlier["status"] = "completed"

    return ordered


def _stage_in_flight(record: RunRecord, stages: list[dict[str, Any]]) -> str:
    """What this run is actually doing, not what it last paused on.

    `current_stage` is written by the runner's gate loop, and that loop only
    turns when the graph pauses for an approval. A run between gates - which is
    most of a run - carries whatever it last paused on, or, for one that has
    not reached its first gate, nothing at all. Measured on one run: ten
    minutes of steady work, a model call every thirty seconds, and a blank
    stage on the screen the whole time.

    The event history knows: the last event carries the stage that produced it.
    The record still wins for a terminal run, whose last event is the ending.
    """
    if record.status in ("completed", "failed", "cancelled"):
        return record.current_stage or ""
    if stages:
        return stages[-1]["name"]
    return record.current_stage or ""


# ----------------------------------------------------------------------
# The wizard model
#
# The guided-wizard view of a run shows the build the way a person follows it:
# intake, design, sprint one, sprint two, done. That phase structure - which
# stage belongs to which sprint, which pass of a sprint was rejected and why,
# how each review ended up - has to be derived from the raw event stream.
#
# This derivation used to live in the browser (a 700-line TypeScript module)
# and separately in `_derive_stages` for the classic timeline: two readers of
# one truth, free to drift apart, with review outcomes *guessed* on the client
# because no event ever recorded them. The server now owns the derivation and
# hands the browser a finished `WizardModel`; the browser only renders it.
#
# Review decisions are facts since `review_decision` events exist (Step 1 of
# this change): when one follows a review pause, the outcome is read from the
# event. Old runs predate the event and their history cannot be rewritten, so
# those reviews fall back to inference from the stages that followed - the same
# rule the browser used, kept here for backward compatibility only.
# ----------------------------------------------------------------------

#: Plain-English copy for stage names, mirroring the frontend's `describeStage`
#: (langchain-ui/src/lib/activity.ts). The wizard must not show a raw
#: identifier, and this map is the one place those become sentences. Kept in
#: sync by hand: it is display text, not behaviour.
_WIZARD_STAGE_COPY: dict[str, tuple[str, str]] = {
    "product_manager": ("Understanding your product", "Reading your document to work out what you want built and who it is for."),
    "tools_models": ("Comparing the options", "Weighing up the technologies and AI models that would suit this product."),
    "stack_selector": ("Choosing the technology", "Settling on the languages, frameworks and services the build will use."),
    "specialist_consultation": ("Asking the specialists", "Getting the interface, data and service specialists' advice before the technical plan is written."),
    "principal_architect": ("Designing how it works", "Writing the technical plan: the pieces, the data, and how they fit together."),
    "architecture_review": ("Checking the design", "A second opinion on the plan, looking for security holes and things that will not work."),
    "user_review_specification": ("Your review", "Paused for you to read the technical plan and say whether to continue."),
    "scrum_master": ("Planning the work", "Splitting the design into sprints small enough to build one at a time."),
    "technical_lead": ("Setting up the next chunk", "Picking what to build first and breaking it into individual tasks."),
    "specialist_dispatch": ("Building it", "Writing the actual code and tests for this piece of the product."),
    "test_and_triage": ("Testing", "Running the tests and writing down anything that failed."),
    "defect_remediation": ("Fixing what broke", "Sending each problem back to be fixed, then testing again."),
    "security_review": ("Security check", "Looking over the finished code for anything unsafe."),
    "advice_review": ("Checking the specialists' advice", "Each specialist asked before the design checks its advice was built this sprint."),
    "acceptance_dispute": ("Judging the failing tests", "Before a failed sprint is planned again, the QA lead says which locked tests no right product could pass."),
    "milestone_review": ("Reviewing the work", "Checking the finished piece against what was planned."),
    "user_review_sprint": ("Your review", "Paused for you to look at the completed sprint and say whether to continue."),
    "sprint_advance": ("Starting the next sprint", "This chunk is done. Moving on to the next one."),
    "complete": ("Finished", "Everything ran through to the end. The results are ready below."),
    "failed": ("Stopped", "Something went wrong and the run needs a person to look at it."),
}

#: Numbered specialist stages (`specialist_backend_0`) resolve to their role.
_WIZARD_SPECIALIST_COPY: dict[str, tuple[str, str]] = {
    "backend": ("Building the backend", "Writing the server code, data models and APIs."),
    "frontend": ("Building the interface", "Writing the screens people will actually click on."),
    "ui_ux": ("Designing the interface", "Laying out the screens and how someone moves between them."),
    "testing": ("Writing tests", "Writing checks that prove the code does what it should, and running them."),
    "devops": ("Setting up deployment", "Making the project buildable and runnable outside a laptop."),
    "security": ("Hardening security", "Closing gaps that would let the wrong person in."),
    "data": ("Working on the data layer", "Shaping how information is stored and retrieved."),
}

#: The review *points* a run pauses on, mirroring the workflow's constants
#: (`SPRINT_REVIEW`, `SPECIFICATION_REVIEW`, `PRODUCT_INTAKE_REVIEW`). A pause
#: stage is `awaiting_user_review:<point>`, and the runner's `review_request`
#: event carries the same point in its metadata - so a review is recognised by
#: its point, not by the node name. An approval pause is not a review - it is
#: the stage working - so it does not count.
_REVIEW_POINTS = frozenset({"sprint", "technical_specification", "product_intake"})


def _wizard_base_stage(raw: str) -> str:
    """Strip the pause prefix from a stage name.

    While a run waits on a person, `stage` is `awaiting_user_review:sprint` or
    `awaiting_approval:principal_architect`; the part after the colon is the
    stage that is actually paused, and that is the name every other event uses.
    """
    for prefix in (APPROVAL_PAUSE_PREFIX, REVIEW_PAUSE_PREFIX):
        if raw.startswith(prefix):
            return raw[len(prefix):]
    return raw


def _wizard_stage_copy(name: str) -> tuple[str, str]:
    """Title and blurb for a stage name, never the raw identifier."""
    base = _wizard_base_stage(name)
    if copy := _WIZARD_STAGE_COPY.get(base):
        return copy
    # specialist_<role>[_<n>] -> role copy.
    if base.startswith("specialist_"):
        rest = base[len("specialist_"):]
        role, _, num = rest.rpartition("_")
        if not num.isdigit():
            role, num = rest, ""
        if role in _WIZARD_SPECIALIST_COPY:
            return _WIZARD_SPECIALIST_COPY[role]
        words = " ".join(w for w in role.split("_") if w)
        return (f"Building the {words} part", "Writing code and tests for this piece of the product.")
    title = " ".join(word.capitalize() for word in base.replace("-", "_").split("_") if word)
    return (title or "Getting started", "Working through this step.")


def _wizard_status(is_last: bool, run_status: str, current_stage: str | None) -> tuple[str, str]:
    """The status a step gets, in the words the UI badges use.

    Mirrors the frontend `stepStatus`: a step is done once a later step started;
    the last step of a live run is the one in flight (or waiting); a stopped
    run leaves its passed steps as 'Stopped' rather than pretending they
    finished cleanly.
    """
    if not is_last:
        if run_status in ("failed", "cancelled"):
            return ("error", "Stopped")
        return ("done", "Done")

    if run_status == "completed":
        return ("done", "Done")
    if run_status == "failed":
        return ("error", "Stopped")
    if run_status == "cancelled":
        return ("idle", "Cancelled")
    if run_status in ("waiting_for_review", "waiting_for_approval"):
        return ("waiting", "Waiting for you")
    if run_status == "paused":
        return ("waiting", "Paused")
    if run_status in ("running", "created"):
        if run_status == "created" or not current_stage:
            return ("idle", "Up next")
        return ("active", "Working on it")
    return ("idle", "Up next")


def _wizard_note(event: RunEvent) -> WizardNote:
    """A log line the wizard can render. The UI only needs its id, type and text."""
    return WizardNote(id=event.event_id, kind=event.event_type, message=event.message)


async def build_wizard_model(record: RunRecord, runner: WorkflowRunner) -> WizardModel:
    """Build the guided-wizard view of one run from its event history.

    A single pass over the events in sequence order, folding them into phases
    (intake, design, sprints 1..n, summary). The fold's only hard question is
    every `technical_lead` re-entry: new sprint or revision of the current one?
    `sprint_advance` ran in between -> genuinely new sprint; a review ran in
    between without an advance -> the sprint was sent back, so a new *revision*
    under the same sprint (the behaviour the wizard exists to show); neither
    (e.g. re-entry from defect remediation) -> the same revision continues.

    Review outcomes are read from `review_decision` events when present - the
    decision is recorded where it was made, not inferred from what ran next.
    Runs that predate those events fall back to stage inference; see
    `_wizard_review_outcome`.
    """
    history = await runner.event_bus.get_history(record.run_id)
    events = sorted(history, key=lambda e: e.sequence)

    run_status = record.status
    is_terminal = run_status in ("completed", "failed", "cancelled")
    current_stage = record.current_stage or None

    state = record.graph_state(runner.checkpointer)
    # The pending review's comment - the only place a still-open review's
    # text survives in the API.
    pending_comment: str | None = None
    for point, review in (state.get("reviews") or {}).items():
        status_value = getattr(review, "status", None)
        if status_value == "pending" or (hasattr(status_value, "value") and status_value.value == "pending"):
            comments = "\n".join(getattr(review, "comments", []) or []) or None
            if comments:
                pending_comment = comments

    intake = WizardSection(
        id="intake", kind="intake", title="Product intake",
        blurb="Reading your document to work out what you want built and who it is for.",
    )
    design = WizardSection(
        id="design", kind="design", title="Design",
        blurb="Comparing options, choosing the technology, and writing the technical plan.",
    )
    summary_section = WizardSection(
        id="summary", kind="summary", title="Final summary",
        blurb="How the run went: sprints planned vs. built, revisions, tests and reviews.",
    )

    sprint_sections: list[WizardSection] = []
    active_section = intake
    active_revision: SprintRevision | None = None
    sprint_number = 0
    current_steps: list[WizardStep] = []
    pending_review: WizardReview | None = None
    revision_comment: str | None = None
    saw_advance = False
    saw_review = False
    # Every review pause in order, with the sequence of the event that opened
    # it. A decision belongs to the review whose window contains it (after this
    # pause, before the next review anywhere), so each keeps its opening
    # sequence for the resolution pass at the end.
    review_seqs: list[tuple[WizardReview, int]] = []

    def step_container() -> list[WizardStep]:
        # Inside a sprint a step belongs to the revision being built; before
        # the first sprint, steps belong to their phase section directly.
        return current_steps if sprint_number > 0 else active_section.steps

    def close_current_step(at: str | None) -> None:
        container = step_container()
        if not container:
            return
        last = container[-1]
        if last.ended_at is None and at:
            try:
                start = datetime.fromisoformat(last.started_at.isoformat()) if last.started_at else None
                end = datetime.fromisoformat(at)
            except (TypeError, ValueError):
                start, end = None, None
            if start and end and end >= start:
                last.ended_at = end
                last.duration_seconds = max((end - start).total_seconds(), 0.0)

    def commit_revision() -> None:
        nonlocal active_revision, current_steps, pending_review, revision_comment, active_section
        if not active_revision:
            return
        # The review's rejection comment is the text that started the *next*
        # pass - it belongs to this revision only once a later one exists.
        active_revision.steps = list(current_steps)
        active_revision.review = pending_review
        active_revision.rejection_comment = revision_comment
        # Whether an approved review ran sprint_advance after this pass: the
        # fact the outcome fallback for old runs needs (see section 3).
        active_revision.saw_advance = saw_advance
        # A revision only exists once it is attached to its sprint - a sprint
        # with no committed revisions would render as an empty card.
        if isinstance(active_section, WizardSection) and active_section.kind == "sprint":
            active_section.revisions.append(active_revision)
        active_revision = None
        current_steps = []
        pending_review = None
        revision_comment = None

    def start_revision(comment: str | None) -> None:
        nonlocal active_revision, current_steps, pending_review, revision_comment
        number = (active_revision.number if active_revision else 0) + 1
        active_revision = SprintRevision(number=number, steps=[], review=None, rejection_comment=comment)
        current_steps = []
        pending_review = None
        revision_comment = comment

    def open_sprint_section() -> WizardSection:
        nonlocal sprint_number, active_section
        sprint_number += 1
        section = WizardSection(
            id=f"sprint-{sprint_number}", kind="sprint", title=f"Sprint {sprint_number}",
            blurb="Building, testing and reviewing this chunk of the product.",
            sprint_number=sprint_number,
        )
        sprint_sections.append(section)
        active_section = section
        return section

    # Transition detection compares *base* stages, not raw ones. A pause is a
    # state of the step that is running, not a new step: while a node works it
    # writes artifacts through the approval gate, so its events flap between
    # `specialist_backend_1` and `awaiting_approval:specialist_backend_1`.
    # Comparing raw stages would read every flap as two transitions and open a
    # duplicate step per gate (the classic timeline collapses these into one
    # stage with an approval count for exactly this reason). A genuine change
    # of base is always a transition, even if it arrives while paused.
    prev_base: str | None = None
    for event in events:
        # Decision events are recorded *after* the run has already moved on, so
        # their `stage` field carries a bare review point (e.g. `sprint`) that
        # matches no running stage - if they were walked like anything else they
        # would read as a transition and open a phantom step named after the
        # point. They carry no step information; the resolution pass below pairs
        # them with the reviews they answer.
        if event.event_type in ("review_decision", "approval_decision"):
            continue

        stage = event.stage
        base = _wizard_base_stage(stage)
        is_transition = base != prev_base
        prev_base = base

        if is_transition:
            # A pause is not a step - it is the current step waiting on a person.
            if stage.startswith(APPROVAL_PAUSE_PREFIX) or stage.startswith(REVIEW_PAUSE_PREFIX):
                meta = event.metadata or {}
                point = str(meta.get("review_point") or base)
                if point in _REVIEW_POINTS:
                    pending_review = WizardReview(
                        point=point,
                        revision=int(meta.get("revision") or 0),
                        requested_at=datetime.fromisoformat(event.timestamp) if event.timestamp else None,
                        outcome="pending",
                        comment=None,
                    )
                    saw_review = True
                    review_seqs.append((pending_review, event.sequence))
                # An approval pause is the step working, not a new step or a
                # review. `prev_base` is deliberately left untouched: if this
                # were the first word about its stage, the bare event that
                # follows must still read as a transition and open the step.
                continue

            if base in ("complete", "failed"):
                close_current_step(event.timestamp)
                commit_revision()
                continue

            if base == "technical_lead":
                close_current_step(event.timestamp)
                if sprint_number == 0:
                    open_sprint_section()
                    start_revision(None)
                elif saw_advance:
                    # An approved review ran sprint_advance in between: genuinely new sprint.
                    commit_revision()
                    open_sprint_section()
                    start_revision(None)
                elif saw_review:
                    # A review ran in between but no advance: sent back - a new
                    # revision under the *same* sprint, not a new sprint.
                    comment = pending_review.comment if pending_review else None
                    commit_revision()
                    start_revision(comment)
                # else: re-entry without review or advance (defect remediation);
                # the same revision continues.

                saw_advance = False
                saw_review = False
                title, blurb = _wizard_stage_copy(base)
                step = WizardStep(
                    name=base, title=title, blurb=blurb,
                    started_at=datetime.fromisoformat(event.timestamp) if event.timestamp else None,
                    status="active", status_label="Working on it",
                )
                step.events.append(_wizard_note(event))
                step_container().append(step)
                continue

            close_current_step(event.timestamp)
            if base == "sprint_advance":
                # The bridge between sprints: not a step of either, just the mark
                # that the current one is done.
                saw_advance = True
                continue

            if sprint_number == 0:
                active_section = intake if base == "product_manager" else design

            title, blurb = _wizard_stage_copy(base)
            step = WizardStep(
                name=base, title=title, blurb=blurb,
                started_at=datetime.fromisoformat(event.timestamp) if event.timestamp else None,
                status="active", status_label="Working on it",
            )
            step.events.append(_wizard_note(event))
            step_container().append(step)
            continue

        # Not a stage transition: a note about the stage already running.
        container = step_container()
        last_step = container[-1] if container else None
        if last_step is not None and _wizard_base_stage(last_step.name) == base:
            last_step.events.append(_wizard_note(event))

    # End of the walk: close whatever is still open.
    close_current_step(events[-1].timestamp if events else None)
    commit_revision()

    sections = [intake, design, *sprint_sections, summary_section]

    # ---- 2. Fill in section and step statuses ------------------------

    first_sprint_opened = bool(sprint_sections)
    if first_sprint_opened or is_terminal:
        for section in (intake, design):
            section.status, section.status_label = "done", "Done"
    elif run_status != "created":
        # In the design phase: whichever of intake/design is current.
        in_intake = bool(current_stage) and _wizard_base_stage(current_stage) == "product_manager"
        intake.status, intake.status_label = ("active", "Working on it") if in_intake else ("done", "Done")
        design.status, design.status_label = ("upcoming", "Up next") if in_intake else ("active", "Working on it")

    for section in (intake, design):
        steps = section.steps
        if section.status == "done":
            for step in steps:
                step.status, step.status_label = "done", "Done"
        elif section.status in ("active", "waiting"):
            for i, step in enumerate(steps):
                step.status, step.status_label = _wizard_status(
                    i < len(steps) - 1, run_status, current_stage
                )

    last_sprint_index = len(sprint_sections) - 1
    for idx, section in enumerate(sprint_sections):
        is_last_sprint = idx == last_sprint_index
        if is_last_sprint and not is_terminal:
            status, label = _wizard_status(True, run_status, current_stage)
            section.status, section.status_label = status, label
        else:
            section.status, section.status_label = "done", "Done"
        revisions = section.revisions
        last_revision_index = len(revisions) - 1
        for ridx, revision in enumerate(revisions):
            is_last_step_of_run = ridx == last_revision_index and is_last_sprint and not is_terminal
            for i, step in enumerate(revision.steps):
                step.status, step.status_label = _wizard_status(
                    is_last_step_of_run and i == len(revision.steps) - 1, run_status, current_stage
                )

    if is_terminal:
        summary_section.status, summary_section.status_label = "done", "Done"
    else:
        summary_section.status, summary_section.status_label = "upcoming", "Up next"

    current_section_id: str | None = None
    if not is_terminal:
        for section in sections:
            if section.status in ("active", "waiting"):
                current_section_id = section.id
                break

    # ---- 3. Resolve review outcomes -----------------------------------

    # Explicit decision events win: they record the answer where it was made,
    # so no inference is needed at all for runs that have them. Runs that
    # predate those events fall back to what ran next - the rule the browser
    # used before this endpoint existed, kept here so old history still reads
    # correctly rather than as a blank.
    decision_events = [e for e in events if e.event_type == "review_decision"]
    # Each review's opening sequence, plus the one that follows it (its upper
    # bound). A decision belongs to the window between this review opening and
    # the next one opening - so a later sprint's answer cannot leak backwards
    # onto an earlier review, even though both carry the same point name.
    opened_seqs = [seq for _, seq in review_seqs]
    upper_bound_for: dict[int, int | None] = {
        opened_seqs[i]: (opened_seqs[i + 1] if i + 1 < len(opened_seqs) else None)
        for i in range(len(opened_seqs))
    }
    seq_by_review = {id(review): seq for review, seq in review_seqs}

    def _decision_for(opened_seq: int) -> RunEvent | None:
        upper = upper_bound_for.get(opened_seq)
        window = [
            e for e in decision_events
            if e.sequence > opened_seq and (upper is None or e.sequence < upper)
        ]
        # There should be exactly one; the last is safe against out-of-order.
        return window[-1] if window else None

    for section in sprint_sections:
        revisions = section.revisions
        for i, revision in enumerate(revisions):
            review = revision.review
            if review is None or review.outcome != "pending":
                continue

            decision = _decision_for(seq_by_review.get(id(review), 0))

            if decision is not None:
                action = str((decision.metadata or {}).get("action") or "")
                message = decision.message or ""
                if action == "changes":
                    review.outcome = "changes"
                    # The event's message is `Review decision: changes — <comment>`.
                    tail = message.removeprefix("Review decision: changes")
                    review.comment = tail.strip().lstrip("—- ").strip() or None
                elif action == "skip":
                    review.outcome = "skipped"
                else:
                    # `approve` (the only other action the API accepts): approved.
                    review.outcome = "approved"
                    if action == "approve" and " — " in message:
                        review.comment = message.rsplit(" — ", 1)[1].strip() or None
                continue

            # Fallback for runs whose history predates decision events,
            # mirroring the browser's inference exactly: a later revision that
            # started with a rejection comment means this one was sent back;
            # moving on to the next sprint (or finishing) means approved or
            # skipped; still waiting means pending; anything else is not
            # "sent back".
            nxt = revisions[i + 1] if i + 1 < len(revisions) else None
            if nxt is not None and nxt.rejection_comment:
                review.outcome = "changes"
                review.comment = nxt.rejection_comment
            elif revision.saw_advance or is_terminal:
                review.outcome = "approved"
            elif run_status == "waiting_for_review":
                review.outcome = "pending"
            else:
                review.outcome = "approved"

    # A still-open review carries its comment from the graph state.
    if pending_comment is not None:
        for section in sprint_sections:
            for revision in section.revisions:
                if revision.review is not None and revision.review.outcome == "pending":
                    revision.review.comment = pending_comment

    # ---- 4. The summary -------------------------------------------------

    all_revisions = [rev for section in sprint_sections for rev in section.revisions]
    all_reviews = [rev.review for rev in all_revisions if rev.review is not None]

    def _count(outcome: str) -> int:
        return sum(1 for review in all_reviews if review.outcome == outcome)

    # The planned count is content, not structure: it comes from the sprint
    # plan artifact when it exists. A parse failure means "not known yet", not
    # "zero sprints".
    sprints_planned: int | None = None
    plan = state.get("sprint_plan")
    if plan is not None:
        sprints = getattr(plan, "sprints", None) or (plan.get("sprints") if isinstance(plan, dict) else None)
        if isinstance(sprints, list):
            sprints_planned = len(sprints)

    cycle = state.get("remediation")
    test_runs = len(getattr(cycle, "test_runs", []) or []) if cycle is not None else 0
    defects_found = len(getattr(cycle, "defects", []) or []) if cycle is not None else 0

    # Approvals: count the same way the classic timeline does - one per
    # approval event in this run's history.
    approvals_passed = sum(1 for e in events if e.event_type in _APPROVAL_EVENTS)

    started_at = datetime.fromisoformat(record.created_at) if record.created_at else None
    ended_at = (
        datetime.fromisoformat(record.updated_at) if is_terminal and record.updated_at else None
    )

    summary_model = WizardSummary(
        sprints_planned=sprints_planned,
        sprints_executed=len(sprint_sections),
        revisions_total=len(all_revisions),
        test_runs=test_runs,
        defects_found=defects_found,
        documents_produced=len(_collect_artifacts(record, runner)),
        approvals_passed=approvals_passed,
        reviews_approved=_count("approved") + _count("skipped"),
        reviews_changes=_count("changes"),
        reviews_skipped=_count("skipped"),
        reviews_pending=_count("pending"),
        started_at=started_at,
        ended_at=ended_at,
        status=run_status,
        status_label={
            "created": "Not started yet",
            "running": "Working on it",
            "waiting_for_approval": "Waiting for you",
            "waiting_for_review": "Needs your review",
            "paused": "Paused",
            "failed": "Stopped",
            "cancelled": "Cancelled",
            "completed": "Done",
        }.get(run_status, run_status),
        error=record.error,
    )

    return WizardModel(sections=sections, summary=summary_model, current_section_id=current_section_id)


#: Review points whose artifact is a structured output in the graph state, by its key.
_REVIEW_OUTPUTS = {
    "product-intake": "product_intake",
    "tools-and-models": "tools_models",
    "technical-specification": "technical_specification",
    "architecture-review": "architecture_review",
    "sprint-milestone": "milestone_plan",
    "milestone-review": "milestone_review",
}
#: Review points whose artifact is a document the workflow writes rather than a
#: structured output: the acceptance suite in plain language, and the release
#: evidence. See `app.graph.acceptance_nodes` and `delivery`.
_REVIEW_DOCUMENTS = {
    "acceptance-tests": "docs/acceptance_tests.md",
    "release": "docs/reviews/release-evidence.md",
    "escalation": "docs/reviews/escalation.md",
}


def _the_review_document(repo_root: str | None, artifact_id: str) -> str | None:
    """The workspace document a review is about, when the workflow wrote one (plan BG.3).

    A structured output is also rendered as `docs/<name>.md`; the page shows
    that in place of asking the owner to download, edit and upload it.
    """
    if not repo_root or not artifact_id:
        return None
    logical = _REVIEW_OUTPUTS.get(artifact_id) or artifact_id.replace("-", "_")
    for candidate in (_REVIEW_DOCUMENTS.get(artifact_id), f"docs/{logical}.md", f"docs/{artifact_id.replace('-', '_')}.md"):
        if candidate and (Path(repo_root) / candidate).is_file():
            return candidate
    return None


def _remediation_info(cycle: Any) -> RemediationInfo | None:
    """Where the fix loop stands, with the defects still open; None outside one."""
    if cycle is None:
        return None
    return RemediationInfo(
        attempt=cycle.attempt,
        max_attempts=cycle.max_attempts,
        escalated=cycle.escalated,
        defect_count=len(cycle.defects),
        test_runs=len(cycle.test_runs),
        open_defects=sum(1 for defect in cycle.defects if getattr(defect, "status", "open") == "open"),
    )


async def _build_status_response(record: RunRecord, runner: WorkflowRunner) -> RunStatusResponse:
    """Assemble the full status payload for one run."""
    # Derived from the event history rather than stored: the history is already
    # the authority on what ran, and a second source would drift from it.
    try:
        history = await runner.event_bus.get_history(record.run_id)
        stages = _derive_stages(history, record.current_stage)
    except Exception:  # noqa: BLE001 - a timeline is never worth failing a status call for
        stages = []

    in_flight = _stage_in_flight(record, stages)

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

    remediation = _remediation_info(state.get("remediation"))

    artifacts = [
        ArtifactInfo(
            path=item["key"],
            kind=item["kind"],
            revision=1,
            created_by="workflow",
            stage=in_flight,
        )
        for item in _collect_artifacts(record, runner)
    ]

    return RunStatusResponse(
        run_id=record.run_id,
        thread_id=record.thread_id,
        status=record.status,
        current_stage=in_flight,
        stage_meaning=record.stage_meaning or _stage_meaning(in_flight),
        created_at=record.created_at,
        updated_at=record.updated_at,
        stages=stages,
        artifacts=artifacts,
        reviews=reviews,
        remediation=remediation,
        error=record.error,
        auto_approve=bool(record.auto_approve),
        completion_gaps=[str(gap) for gap in (getattr(record, "completion_gaps", None) or [])],
        gate_deadline=_when_the_gate_approves_itself(record),
        approval_timeout_minutes=getattr(record, "approval_timeout_minutes", None),
        non_deliverable=_what_the_marker_says(record),
        delivery_mode=str(getattr(record, "delivery_mode", "") or ""),
        use_frontier_model=not bool(getattr(record, "local_only", False)),
        **_the_model_pin(record.run_id, runner),
        **_the_run_name(record.run_id, runner),
        cost=_cost_summary(record.run_id),
        # The ceilings the worker holds the run to: the API reads the same environment.
        max_run_tokens=_max_run_tokens() or None,
        max_run_cost_usd=_max_run_cost_usd() or None,
        # Its size, so the page can say what a run of this size takes here.
        **_how_many_criteria_hold(record),
    )


def _the_run_name(run_id: str, runner: Any) -> dict[str, Any]:
    """`run_name` for a status response, or nothing: a status is never failed by the name."""
    try:
        name = runner.run_store.run_names([run_id]).get(run_id)
        return {"run_name": name} if name else {}
    except Exception:  # noqa: BLE001
        return {}


def _the_model_pins(run_ids: list[str], runner: Any) -> dict[str, dict[str, Any]]:
    """`_the_model_pin` for a page of runs, from one statement: {run_id: the fields a summary carries}."""
    try:
        from app.models.model_pin import summary_of

        out: dict[str, dict[str, Any]] = {}
        for run_id, (pinned, last) in runner.run_store.model_states(run_ids).items():
            summary = summary_of(last)
            out[run_id] = {"model_pinned": bool(pinned), "model_last": ModelSummary(**summary) if summary else None}
        return out
    except Exception:  # noqa: BLE001 - a list is never failed by the pin
        return {}


def _the_model_pin(run_id: str, runner: Any) -> dict[str, Any]:
    """`model_pinned` and `model_last` for a status response: whether the run is kept on its model, and which."""
    try:
        from app.models.model_pin import summary_of

        state = runner.run_store.model_state(run_id)
        if not state:
            return {}
        summary = summary_of(state[1])
        return {"model_pinned": bool(state[0]), "model_last": ModelSummary(**summary) if summary else None}
    except Exception:  # noqa: BLE001 - a status response is never failed by the pin
        return {}


def _when_the_gate_approves_itself(record: Any) -> Any:
    """When a waiting gate approves itself, or None: nothing waits, or it waits for the person.

    The sweep approves a gate `approval_timeout_minutes` after the run started
    waiting (`app.server.approval_timeouts`), and the page never said so: a
    gate approved itself with nobody told, and gates with no timeout were
    measured parked for 12-13 h with nothing to say they would wait for ever.
    """
    from datetime import datetime, timedelta, timezone

    minutes = getattr(record, "approval_timeout_minutes", None)
    if record.status not in ("waiting_for_approval", "waiting_for_review") or not minutes:
        return None
    try:
        since = datetime.fromisoformat(str(record.updated_at))
    except (TypeError, ValueError):
        return None
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    return since + timedelta(minutes=int(minutes))


def _what_the_marker_says(record: Any) -> str:
    """The workspace's non-deliverable marker in one sentence, or "" (Initiative J.6)."""
    try:
        from app.graph import terminal_state

        found = terminal_state.read(getattr(record, "repo_root", "") or "")
    except Exception:  # noqa: BLE001 - a status response is never failed by the marker
        return ""
    if not found:
        return ""
    reason = str(found.get("reason") or "")
    status = str(found.get("status") or "")
    return f"{status}: {reason}" if reason else status


def _cost_summary(run_id: str) -> RunCostSummary | None:
    """This run's spend, or `None` when this process is not the one tracking it.

    Two sources, in order of precision. The live registry is authoritative but
    per-process, so it answers only in the worker that made the calls; the API
    is a different container and would otherwise report nothing for every run.
    The transcript is the shared fallback - both containers mount
    `DATA_DIR/transcripts/` and every `model_response` line carries its usage.

    `None` when neither has anything, and not a zeroed summary: absent means
    "not known here", and a `$0.00` on a run that has made a hundred paid calls
    is exactly the fabricated measurement plan-part3 §3.2 set out to remove.

    A run genuinely on a local model reports a summary with `0.0` and
    `fully_priced` true, which is a different statement and reads as one.
    """
    from app.observability.cost_tracker import cost_from_transcript, run_cost

    total = run_cost(run_id)
    if total.successful_requests == 0:
        # Not this process's run. Fall back to the transcript, which both
        # containers can read - otherwise the API reports no cost for every run,
        # because the worker is where the calls were made.
        provider = model = ""
        try:
            from app.models import _runtime_settings

            resolved = _runtime_settings()
            provider = getattr(resolved, "llm_provider", "") or ""
            model = getattr(resolved, "model_name", "") or ""
        except Exception:  # noqa: BLE001 - an unpriced total beats no total
            logger.debug("Could not resolve settings for the cost summary", exc_info=True)
        total = cost_from_transcript(run_id, provider, model)
        if total is None:
            return None
    return RunCostSummary(**total.summary())


__all__ = ["create_runs_router"]
