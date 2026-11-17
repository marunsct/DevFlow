# The sandbox image of the Go packs (LR.30, `app.stacks.packs._sandbox`): Go and gotestsum beside Node and the
# browsers, for container mode, where every agent command runs in a container of its own - the service's suite
# runs under Playwright and starts the Go service from inside the same container.
# Built by `scripts/loop/build_sandbox_images.sh`. Go matches the packs' `GO_VERSION` (1.26) and the worker image's
# release; gotestsum is the worker image's pin.
ARG PLAYWRIGHT_VERSION=1.64.0
FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-noble

ARG GO_VERSION=1.26.9
ARG GOTESTSUM_VERSION=1.12.3

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-$(dpkg --print-architecture).tar.gz" | tar -xz -C /usr/local \
    && ln -sf /usr/local/go/bin/go /usr/local/bin/go && ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt \
    && GOBIN=/usr/local/bin GOPATH=/tmp/gopath GOCACHE=/tmp/gocache GOTOOLCHAIN=local \
        go install "gotest.tools/gotestsum@v${GOTESTSUM_VERSION}" \
    && rm -rf /tmp/gopath /tmp/gocache \
    && go version && gotestsum --version && node --version

# A module asking for a newer Go fails plainly instead of downloading a toolchain into the workspace.
ENV GOTOOLCHAIN=local
