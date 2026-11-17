# The sandbox image of the Python packs (LR.30, `app.stacks.packs._sandbox`): Python with venv and pip beside
# Node and the browsers, for container mode, where every agent command runs in a container of its own.
# Built by `scripts/loop/build_sandbox_images.sh`; Ubuntu 24.04's Python is 3.12, the packs' `PYTHON_VERSION`.
ARG PLAYWRIGHT_VERSION=1.64.0
FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-noble

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git \
        python3 python3-venv python3-pip python3-dev build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && python3 --version && python3 -m venv --help >/dev/null && node --version
