# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: build the frontend
# ---------------------------------------------------------------------------
FROM node:24-slim AS frontend-builder
WORKDIR /app/langchain-ui

COPY langchain-ui/package*.json ./
RUN npm ci

COPY langchain-ui/ ./
# `npm run build` runs `tsc -b` first, so a type error fails the image build
# rather than shipping a frontend that cannot compile.
RUN npm run build

# The TypeScript compiler, for the runtime image and not for this build: the
# write tools parse every `.ts`, `.tsx` and `.jsx` an agent writes with it
# (`app.analysis.typescript_parse`), and Node cannot. Installed globally so it
# travels with `/usr/local/lib/node_modules` below. Pinned to the last release
# that ships the JavaScript API the check calls - 7.x is a native binary
# without it - and a project that installs its own TypeScript is parsed with
# that one instead.
RUN npm install -g typescript@6.0.3

# Pyright - the engine of VS Code's Python language support - for the same
# reason on the Python side: what an IDE would underline in a Python file (a
# name nothing defines, an import of something its module does not have), at
# the moment it is written (`app.analysis.language_service`). It runs on the
# Node already here.
RUN npm install -g pyright@1.1.414

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

COPY pyproject.toml uv.lock ./
COPY src/ ./src/
# Runtime dependencies only: the previous image also installed pytest into the
# production layer.
#
# Exactly the versions `uv.lock` pins - the ones the test suite runs against.
# `uv pip install .` resolved the newest release each range in pyproject.toml
# allows and ignored the lock, so on 2026-09-30 production was running 38
# packages at versions no test had seen: deepagents 0.7.20 against 0.7.13 in
# the suite, among them. 0.7.20 dropped the line-number gutter from
# `read_file`, and every line-addressed edit a model made from then on was
# counted by hand from unnumbered text - the largest class of failed edits
# that day, invisible to a suite running the older release. `--frozen` fails
# the build if the lock is out of date rather than resolving around it.
RUN uv export --frozen --no-dev --no-emit-project --format requirements-txt > /tmp/requirements.txt \
    && uv pip install --no-cache -r /tmp/requirements.txt \
    && uv pip install --no-cache --no-deps .

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

# Node for the agents, not for this image's own build - the UI specialist is
# expected to run `npm install` and compile what it writes, and cannot install a
# runtime for itself. Copied from the frontend builder rather than downloaded
# again, so both stages are pinned to exactly one Node version.
COPY --from=frontend-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend-builder /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && node --version && npm --version

# Chromium in the image, downloaded once and shared by every run.
#
# `sandbox._base_environment` already prefers `~/.cache/ms-playwright` over
# the per-run one and falls back only when it is absent - it just was
# absent, so every run downloaded its own copy into its own workspace.
# Measured on 2026-09-19: 22 stored workspaces holding 8.5 GB of Chromium
# between them, 0.6 to 1.2 GB each, none of it ever reused by another run,
# and each run paying the download before it could test a page.
#
# Run as `appuser` so it lands in that user's home, which is also what makes
# the failure mode graceful: when a run installs a Playwright whose browser
# revision is not in here, it downloads the missing one INTO this shared
# cache, and every later run gets it. The first run after a Playwright
# release pays once for all of them.
#
# The system libraries Chromium needs are installed further up, as root,
# with a note explaining why `--with-deps` is not used here.
#
# Pinned to the Playwright release every JavaScript pack pins
# (`app.stacks.packs._javascript.PLAYWRIGHT`, and the benchmark scorer's), and
# installed before anything that changes with the source. Unpinned, `npx --yes`
# fetched whatever release was newest on the day of the build, and because it ran
# after `COPY src/`, every deploy did it again: from one deploy on the image held
# only Chromium 1248 (Playwright 1.64) while the packs pinned 1.63, whose browser
# is 1243, and three of four runs had their scaffold "left to the agents" over an
# acceptance smoke test that could not start a browser.
# The toolchains the stack packs build with, beyond Node and Python: Go, Java
# with Maven, Rust, Ruby with Bundler, PHP with Composer, and .NET. A product in
# any of these languages starts from a pack whose own tests already run
# (`app.stacks.packs`), and a stage asked to build it can run what it writes.
# System-wide - from Debian's packages where Debian's are current, Go from its
# own release (Debian's 1.24 is older than modules like Gin now require, and Go
# fetched a newer toolchain into every run's workspace) - since the sandbox gives
# every command a home inside its run's workspace, so a toolchain installed
# under a user's home (rustup, sdkman) would not be found. Before anything a
# deploy changes, so a deploy keeps them. The test reporters each language
# lacks - gotestsum for Go, cargo-nextest for Rust - are pinned.
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
        openjdk-21-jdk-headless maven \
        rustc cargo \
        ruby ruby-dev ruby-bundler build-essential \
        php-cli php-xml php-mbstring php-curl php-sqlite3 composer unzip \
        libicu76 \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://go.dev/dl/go1.26.9.linux-amd64.tar.gz | tar -xz -C /usr/local \
    && ln -sf /usr/local/go/bin/go /usr/local/bin/go && ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt \
    && GOBIN=/usr/local/bin GOPATH=/tmp/gopath GOCACHE=/tmp/gocache GOTOOLCHAIN=local go install gotest.tools/gotestsum@v1.12.3 \
    && rm -rf /tmp/gopath /tmp/gocache \
    && curl -fsSL https://get.nexte.st/0.9.104/linux | tar -xz -C /usr/local/bin \
    && curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh \
    && bash /tmp/dotnet-install.sh --channel 8.0 --install-dir /usr/share/dotnet \
    && ln -sf /usr/share/dotnet/dotnet /usr/local/bin/dotnet \
    && rm /tmp/dotnet-install.sh \
    && go version && java -version && mvn -v && cargo --version && cargo nextest --version \
    && ruby --version && bundle --version && php --version && composer --version && dotnet --version
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 DOTNET_ROOT=/usr/share/dotnet

ARG PLAYWRIGHT_VERSION=1.64.0
USER appuser
RUN npx --yes playwright@${PLAYWRIGHT_VERSION} install chromium \
    && test -d "$HOME/.cache/ms-playwright" \
    && du -sh "$HOME/.cache/ms-playwright"
USER root

COPY --from=python-builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser pyproject.toml ./
COPY --from=frontend-builder --chown=appuser:appuser /app/langchain-ui/dist /app/langchain-ui/dist


RUN mkdir -p /app/data/uploads /app/data/workspaces && chown -R appuser:appuser /app/data

# Runs unprivileged. The image previously ran as root.
USER appuser


EXPOSE 8000

# The commit the image was built from, for every run's provenance (plan MF.1).
ARG HARNESS_COMMIT=unknown
ENV HARNESS_COMMIT=${HARNESS_COMMIT}

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
