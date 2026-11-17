# The sandbox image of the Java packs (LR.30, `app.stacks.packs._sandbox`): a JDK and Maven beside Node and the
# browsers, for container mode, where every agent command runs in a container of its own - the service's suite runs
# under Playwright and starts the Java service from inside the same container.
# Built by `scripts/loop/build_sandbox_images.sh`. The JDK matches the packs' `JAVA_VERSION` (21).
ARG PLAYWRIGHT_VERSION=1.64.0
FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-noble

ARG JAVA_VERSION=21

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git "openjdk-${JAVA_VERSION}-jdk-headless" maven \
    && rm -rf /var/lib/apt/lists/* \
    && java -version && mvn -v && node --version
