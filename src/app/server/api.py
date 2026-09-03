"""FastAPI application factory for the web control plane.

Step 6 of the workflow plan.  This is the entry point for the web server.
It mounts the upload, runs, progress, and review routers, and manages
the shared state (event bus, workflow runner, upload directory).

Usage:
    uvicorn app.server.api:app --reload

Or programmatically:
    from app.server.api import create_app
    app = create_app()
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.server.events import EventBus
from app.server.progress import create_progress_router
from app.server.runner import WorkflowRunner
from app.server.runs import create_runs_router
from app.server.uploads import ensure_upload_dir


def create_app(
    *,
    model: str | None = None,
    repo_root: str | None = None,
    upload_dir: str | None = None,
) -> FastAPI:
    """Build the FastAPI application with all routers mounted.

    Args:
        model: model name override; default comes from OPENAI_MODEL env var.
        repo_root: repository the agents may inspect; default is this repo.
        upload_dir: where uploaded documents are stored; default is
            ``./uploads`` relative to the repo root.

    Returns:
        A fully configured FastAPI application ready for ``uvicorn``.
    """
    effective_repo_root = repo_root or os.environ.get(
        "WORKFLOW_REPO_ROOT",
        str(Path(__file__).resolve().parents[3]),
    )
    effective_upload_dir = upload_dir or os.environ.get(
        "WORKFLOW_UPLOAD_DIR",
        str(Path(effective_repo_root) / "uploads"),
    )

    # Tracing
    from app.tracing import configure_tracing
    class DummySettings:
        pass
    configure_tracing(DummySettings())

    # Shared state.
    event_bus = EventBus()
    runner = WorkflowRunner(event_bus, model=model, repo_root=effective_repo_root)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Startup: ensure upload directory exists.  Shutdown: cancel running tasks."""
        ensure_upload_dir(effective_upload_dir)
        yield
        # Shutdown: cancel any running workflow tasks.
        for record in runner.runs.values():
            if record._task is not None and not record._task.done():
                record._task.cancel()

    application = FastAPI(
        title="Product Development Workflow",
        description=(
            "Web control plane for the agentic product-development workflow. "
            "Upload product documents, start runs, observe progress, and "
            "submit review and approval decisions."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS: allow all origins in development.  A production deployment
    # should restrict this to the actual frontend origin.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routers.
    runs_router = create_runs_router(runner, event_bus, effective_upload_dir, effective_repo_root)
    progress_router = create_progress_router(runner, event_bus)

    application.include_router(runs_router)
    application.include_router(progress_router, prefix="/api/runs", tags=["progress"])

    # Health check.
    @application.get("/api/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # Try to mount templates if jinja2 is available and the templates dir exists.
    templates_dir = Path(__file__).parent / "templates"
    if templates_dir.is_dir():
        try:
            from fastapi.templating import Jinja2Templates

            templates = Jinja2Templates(directory=str(templates_dir))

            @application.get("/", tags=["ui"])
            async def index(request: Request) -> Any:
                return templates.TemplateResponse(request, "index.html")

            @application.get("/runs/{run_id}", tags=["ui"])
            async def run_view(request: Request, run_id: str) -> Any:
                record = runner.runs.get(run_id)
                if record is None:
                    return templates.TemplateResponse(
                        request,
                        "index.html",
                        {"error": f"Run {run_id} not found."},
                    )
                return templates.TemplateResponse(
                    request,
                    "run.html",
                    {"run_id": run_id, "record": record},
                )
        except ImportError:
            pass  # Jinja2 not installed, skip template routes.

    return application


# Default app instance for ``uvicorn app.server.api:app``.
app = create_app()

__all__ = ["app", "create_app"]
