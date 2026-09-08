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
    from app.server.run_store import RunStore
    run_store = RunStore()
    event_bus = EventBus()
    runner = WorkflowRunner(event_bus, model=model, repo_root=effective_repo_root, run_store=run_store)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Startup: ensure upload directory exists."""
        ensure_upload_dir(effective_upload_dir)
        yield

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

    # Rate Limiting Middleware
    from fastapi.responses import JSONResponse
    import time
    
    # In-memory rate limiting dictionary: {ip: [timestamps]}
    rate_limit_records = {}
    RATE_LIMIT_MAX_REQUESTS = 100
    RATE_LIMIT_WINDOW_SECONDS = 60
    
    @application.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        
        # Clean up old records for this IP
        if client_ip in rate_limit_records:
            rate_limit_records[client_ip] = [
                ts for ts in rate_limit_records[client_ip] 
                if now - ts < RATE_LIMIT_WINDOW_SECONDS
            ]
        else:
            rate_limit_records[client_ip] = []
            
        if len(rate_limit_records[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
            return JSONResponse(
                status_code=429, 
                content={"detail": "Too Many Requests"}
            )
            
        rate_limit_records[client_ip].append(now)
        response = await call_next(request)
        return response

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
    runs_router, public_runs_router = create_runs_router(runner, event_bus, effective_upload_dir, effective_repo_root)
    progress_router = create_progress_router(runner, event_bus)
    
    from app.server.settings import settings_router

    from fastapi import Depends
    from app.server.auth import auth_router, get_current_active_user
    from prometheus_fastapi_instrumentator import Instrumentator

    application.include_router(auth_router)
    application.include_router(public_runs_router)
    application.include_router(runs_router, dependencies=[Depends(get_current_active_user)])
    application.include_router(progress_router, prefix="/api/runs", tags=["progress"], dependencies=[Depends(get_current_active_user)])
    application.include_router(settings_router, dependencies=[Depends(get_current_active_user)])

    Instrumentator().instrument(application).expose(application)

    # Health check.
    @application.get("/api/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # Serve React Frontend if it exists
    frontend_dist = Path(__file__).resolve().parents[3] / "langchain-ui" / "dist"
    if frontend_dist.is_dir():
        from fastapi.responses import FileResponse
        
        @application.get("/", tags=["ui"])
        async def serve_index():
            return FileResponse(frontend_dist / "index.html")
            
        @application.get("/runs/{run_id}", tags=["ui"])
        async def serve_run():
            return FileResponse(frontend_dist / "index.html")
            
        @application.get("/runs", tags=["ui"])
        async def serve_runs():
            return FileResponse(frontend_dist / "index.html")
            
        @application.get("/login", tags=["ui"])
        async def serve_login():
            return FileResponse(frontend_dist / "index.html")

        @application.get("/settings", tags=["ui"])
        async def serve_settings():
            return FileResponse(frontend_dist / "index.html")

        # Mount static assets
        application.mount("/", StaticFiles(directory=str(frontend_dist)), name="static")

    return application


# Default app instance for ``uvicorn app.server.api:app``.
app = create_app()

__all__ = ["app", "create_app"]
