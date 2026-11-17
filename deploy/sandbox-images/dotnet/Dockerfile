# The sandbox image of the C# packs (LR.30, `app.stacks.packs._sandbox`): the .NET SDK beside Node and the
# browsers, for container mode, where every agent command runs in a container of its own - the service's suite runs
# under Playwright and starts the .NET service from inside the same container.
# Built by `scripts/loop/build_sandbox_images.sh`. The SDK channel matches the packs' `DOTNET` (8.0), installed the
# way the worker image installs it.
ARG PLAYWRIGHT_VERSION=1.64.0
FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-noble

ARG DOTNET_CHANNEL=8.0

ENV DOTNET_ROOT=/usr/share/dotnet \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    DOTNET_NOLOGO=1 \
    DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git libicu74 \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh \
    && bash /tmp/dotnet-install.sh --channel "${DOTNET_CHANNEL}" --install-dir /usr/share/dotnet \
    && rm /tmp/dotnet-install.sh \
    && ln -sf /usr/share/dotnet/dotnet /usr/local/bin/dotnet \
    && chmod -R a+rX /usr/share/dotnet \
    && dotnet --version && node --version
