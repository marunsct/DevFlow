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
# ripgrep because the agents' file-search tool falls back to a slow Python grep
# without it - every search in every run logs the fallback and pays for it.
# The browser libraries are here because `TESTABILITY_RULE` makes Playwright
# mandatory for UI code, and Chromium cannot run without them: the run's own
# verdict on run-2d9066e2 was "Playwright regression tests fail due to missing
# system library libglib-2.0.so.0", and it spent all three remediation attempts
# on a defect no amount of code could fix. The rule tells the model to "fix the
# test environment" rather than delete the code under test; this is that fix.
# `playwright install --with-deps` is not used because it needs root and a
# package manager at install time; the names below are the same set it would
# pull, pinned to the image instead.
#
# The six marked `[host validation]` are the ones Playwright's own host check
# still reported missing on run-519a9d8a after the set above was installed:
# `npx playwright install` printed "Host system is missing dependencies to run
# browsers" and named exactly these, so Chromium downloaded and never ran. The
# model cannot fix this from inside a run - there is no tool that installs an
# OS package, and `TESTABILITY_RULE` tells it to "fix the test environment"
# rather than delete the code under test, which is an instruction the
# environment has to be able to satisfy.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        git \
        ca-certificates \
        ripgrep \
        libasound2t64 \
        libatk-bridge2.0-0t64 \
        libatk1.0-0t64 \
        libatspi2.0-0t64 \
        libcairo2 \
        libcups2t64 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libglib2.0-0t64 \
        libnss3 \
        libnspr4 \
        libpango-1.0-0 \
        libx11-6 \
        libxcomposite1 \
        libxcb1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
        libxshmfence1 \
        libxcursor1 \
        libgtk-3-0t64 \
        libgdk-pixbuf-2.0-0 \
        libpangocairo-1.0-0 \
        libcairo-gobject2 \
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

# Node for the agents, not for this image's own build - the UI specialist is
# expected to run `npm install` and compile what it writes, and cannot install a
# runtime for itself. Copied from the frontend builder rather than downloaded
# again, so both stages are pinned to exactly one Node version.
COPY --from=frontend-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend-builder /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && node --version && npm --version

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
