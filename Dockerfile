# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: build the frontend
# ---------------------------------------------------------------------------
FROM node:20-slim AS frontend-builder
WORKDIR /app/langchain-ui

COPY langchain-ui/package*.json ./
RUN npm ci

COPY langchain-ui/ ./
# `npm run build` runs `tsc -b` first, so a type error fails the image build
# rather than shipping a frontend that cannot compile.
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: install Python dependencies into a virtualenv
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS python-builder
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

ENV VIRTUAL_ENV=/opt/venv
RUN uv venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY pyproject.toml ./
COPY src/ ./src/
# Runtime dependencies only: the previous image also installed pytest into the
# production layer.
RUN uv pip install --no-cache .

# ---------------------------------------------------------------------------
# Stage 3: runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# curl for the healthcheck; git because the repository tools shell out to it.
# No build toolchain in the final image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        git \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WORKFLOW_UPLOAD_DIR=/app/data/uploads \
    WORKFLOW_WORKSPACE_ROOT=/app/data/workspaces \
    DATA_DIR=/app/data

COPY --from=python-builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser pyproject.toml ./
COPY --from=frontend-builder --chown=appuser:appuser /app/langchain-ui/dist /app/langchain-ui/dist

RUN mkdir -p /app/data/uploads /app/data/workspaces && chown -R appuser:appuser /app/data

# Runs unprivileged. The image previously ran as root.
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# Gunicorn with uvicorn workers, not a single reloading dev server. Worker count
# is configurable because the right value depends on the deployment.
# `create_app()` with parentheses is gunicorn's factory syntax. (`--factory` is
# a uvicorn flag; gunicorn does not accept it.)
CMD ["sh", "-c", "exec gunicorn 'app.server.api:create_app()' \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers ${WEB_CONCURRENCY:-4} \
    --bind 0.0.0.0:8000 \
    --timeout ${WEB_TIMEOUT:-120} \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile -"]
