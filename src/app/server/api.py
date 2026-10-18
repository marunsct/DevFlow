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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.server.events import EventBus
from app.server.progress import create_progress_router
from app.server.runner import WorkflowRunner
from app.server.runs import create_runs_router
from app.server.context import set_correlation_id
from app.server.uploads import ensure_upload_dir


def create_app(
    *,
    model: str | None = None,
    repo_root: str | None = None,
    upload_dir: str | None = None,
) -> FastAPI:
    """Build the FastAPI application with every router mounted."""
    effective_repo_root = repo_root or os.environ.get(
        "WORKFLOW_REPO_ROOT", str(Path(__file__).resolve().parents[3])
    )
    effective_upload_dir = upload_dir or os.environ.get(
        "WORKFLOW_UPLOAD_DIR", str(Path(effective_repo_root) / "uploads")
    )

    from app.server.logging_config import configure_logging

    configure_logging()

    # app.config.load_settings, not the settings *route handler* of the same
    # name: importing the handler here passed an un-awaited coroutine into
    # configure_tracing, which then silently fell back to environment variables.
    from app.config import load_settings
    from app.tracing import configure_tracing

    configure_tracing(load_settings())

    from app.server.events import EventBus
    from app.server.run_store import RunStore
    from app.server.runner import WorkflowRunner

    run_store = RunStore.shared()
    event_bus = EventBus()
    runner = WorkflowRunner(
        event_bus, model=model, repo_root=effective_repo_root, run_store=run_store
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Open shared resources on startup and close them on shutdown."""
        from app.server.auth import close_db_pool, init_db, init_db_pool

        # Names a proxy origin timeout in the log rather than leaving a bare
        # status code. See `app.observability.proxy_timeouts`.
        from app.observability.proxy_timeouts import install as _install_proxy_diagnostics

        _install_proxy_diagnostics()

        ensure_upload_dir(effective_upload_dir)
        # Built here rather than at import so the URL is read after the
        # environment is fully assembled, and so a failure stops startup.
        init_db_pool()
        init_db()
        # Gates that approve themselves after the run's timeout
        # (`app.server.approval_timeouts`).
        import asyncio

        from app.server.approval_timeouts import sweep_for_ever

        sweeper = asyncio.create_task(sweep_for_ever(runner))
        try:
            yield
        finally:
            sweeper.cancel()
            close_db_pool()
            RunStore.reset_shared()
            from app.server.redis_client import close_async_redis, close_redis_pool

            close_redis_pool()
            await close_async_redis()

    application = FastAPI(
        title="Product Development Workflow",
        description=(
            "Control plane for the agentic product-development workflow: upload product "
            "documents, start runs, observe progress, and record review and approval decisions."
        ),
        version="0.2.0",
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        """Attach a correlation id to every request and its log lines."""
        import re
        import uuid

        incoming = request.headers.get("X-Correlation-ID", "")
        # Only accept a well-formed id: an arbitrary client string ends up in
        # structured logs and in the response header.
        correlation_id = incoming if re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", incoming or "") else str(uuid.uuid4())
        set_correlation_id(correlation_id)
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    @application.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        """Per-caller request budget, evaluated without blocking the loop."""
        from app.server.rate_limit import enforce_request_budget

        if not await enforce_request_budget(request):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Slow down and try again shortly."},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)

    # CORS: same-origin by default. Credentials are only enabled alongside an
    # explicit origin list, never with a wildcard.
    allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "").strip()
    allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=bool(allowed_origins),
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
    )

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return response

    from fastapi import Depends

    from app.server.auth import auth_router, get_current_active_user, require_admin
    from app.server.settings import settings_router
    from app.server.lessons_api import lessons_router

    runs_router = create_runs_router(runner, event_bus, effective_upload_dir, effective_repo_root)
    progress_router = create_progress_router(runner, event_bus)

    application.include_router(auth_router)
    application.include_router(runs_router)
    application.include_router(progress_router, prefix="/api/runs", tags=["progress"])
    application.include_router(settings_router)
    application.include_router(lessons_router)

    _mount_metrics(application)

    @application.get("/api/health", tags=["health"])
    async def health() -> dict[str, str]:
        """Liveness: the process is up. Cheap enough for a frequent probe."""
        return {"status": "ok"}

    @application.get("/api/health/ready", tags=["health"])
    async def readiness() -> dict[str, Any]:
        """Readiness: every dependency this app needs is reachable.

        Split from liveness so a transient database blip restarts nothing; each
        check runs off the event loop, because psycopg2 and Celery control calls
        are both blocking.
        """
        from starlette.concurrency import run_in_threadpool

        status: dict[str, Any] = {"status": "ok", "db": "ok", "redis": "ok", "celery": "ok"}

        def _check_db() -> None:
            from app.server.auth import get_db_connection

            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")

        try:
            await run_in_threadpool(_check_db)
        except Exception:  # noqa: BLE001
            status["db"] = "error"

        try:
            from app.server.redis_client import get_async_redis_client

            await get_async_redis_client().ping()
        except Exception:  # noqa: BLE001
            status["redis"] = "error"

        def _check_celery() -> bool:
            from app.server.tasks import celery_app

            # ping() returns [] when no worker replies and does not raise, so the
            # previous `try/except` could never report Celery as down.
            return bool(celery_app.control.ping(timeout=1.0))

        try:
            if not await run_in_threadpool(_check_celery):
                status["celery"] = "error"
        except Exception:  # noqa: BLE001
            status["celery"] = "error"

        # How many slots are taken, and how many there are. A full worker is
        # the difference between "queued" and "broken" and nothing here
        # distinguished them: an operator watching a run that had not started
        # could not tell whether it was waiting or wedged. Reported rather
        # than judged - a full pool is a healthy pool doing its job, so this
        # never makes readiness fail.
        def _slots() -> dict[str, Any]:
            from app.server.run_store import RunStore
            from app.server.runner import _max_concurrent_runs

            return {
                "in_flight": RunStore.shared().count_in_flight(),
                "limit": _max_concurrent_runs() or None,
            }

        try:
            status["runs"] = await run_in_threadpool(_slots)
        except Exception:  # noqa: BLE001 - never fail readiness over a count
            pass

        if any(
            v == "error" for k, v in status.items() if k not in ("status", "runs")
        ):
            status["status"] = "error"
            raise HTTPException(status_code=503, detail=status)
        return status

    @application.get("/api/health/models", tags=["health"])
    async def health_models(_: Any = Depends(require_admin)) -> dict[str, Any]:
        """Provider health. Admin-only: it triggers billable model calls."""
        from starlette.concurrency import run_in_threadpool

        from app.models.router import get_router_status

        return await run_in_threadpool(get_router_status)

    _mount_frontend(application)
    return application


def _mount_metrics(application: FastAPI) -> None:
    """Expose Prometheus metrics.

    Guarded by a scrape token rather than a user JWT: a Prometheus server cannot
    complete an interactive login, so the previous configuration made the
    endpoint unscrapeable. With no token configured the endpoint binds
    unauthenticated, which is the normal posture for a metrics port that is not
    routed publicly.
    """
    # Before the instrumentator, which creates its own metrics: importing this
    # is what names this process's mmap files uniquely, and a metric created
    # ahead of it keeps the `os.getpid()` name that collides across container
    # restarts. See `app.observability.metrics`.
    import app.observability.metrics  # noqa: F401 - imported for its side effect
    from prometheus_fastapi_instrumentator import Instrumentator

    scrape_token = os.environ.get("METRICS_SCRAPE_TOKEN", "").strip()
    dependencies = []
    if scrape_token:
        from fastapi import Depends, Header

        async def _verify(authorization: str = Header("")) -> None:
            import secrets as _secrets

            expected = f"Bearer {scrape_token}"
            if not _secrets.compare_digest(authorization, expected):
                raise HTTPException(status_code=401, detail="Invalid metrics credentials")

        dependencies = [Depends(_verify)]

    Instrumentator().instrument(application).expose(application, dependencies=dependencies)


def _mount_frontend(application: FastAPI) -> None:
    """Serve the built SPA, if present.

    A catch-all is used rather than an enumerated route list so that any
    client-side route resolves; the previous version listed five paths by hand
    and 404'd on anything else.
    """
    frontend_dist = Path(__file__).resolve().parents[3] / "langchain-ui" / "dist"
    if not frontend_dist.is_dir():
        return

    from fastapi.responses import FileResponse

    assets = frontend_dist / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    index = frontend_dist / "index.html"

    @application.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith(("api/", "metrics")):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = frontend_dist / full_path
        if full_path and candidate.is_file() and frontend_dist in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(index)


__all__ = ["create_app"]
