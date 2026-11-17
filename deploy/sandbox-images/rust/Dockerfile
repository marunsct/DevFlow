# The sandbox image of the Rust packs (LR.30, `app.stacks.packs._sandbox`): Rust and cargo-nextest beside Node and
# the browsers, for container mode, where every agent command runs in a container of its own - the packs' unit and
# acceptance runner is `cargo nextest`, which no plain Rust image has, and the service's suite runs under Playwright
# and starts the Rust service from inside the same container.
# Built by `scripts/loop/build_sandbox_images.sh`. Rust matches the worker image's (Debian's 1.85); nextest is the
# worker image's pin.
ARG PLAYWRIGHT_VERSION=1.64.0
FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-noble

ARG RUST_VERSION=1.85.0
ARG NEXTEST_VERSION=0.9.104

# The toolchain is system-wide and read-only; CARGO_HOME is left unset at run time, so the registry a build
# downloads lands under the command's own HOME rather than in the image.
ENV RUSTUP_HOME=/usr/local/rustup \
    PATH=/usr/local/cargo/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/* \
    && curl --proto '=https' --tlsv1.2 -fsSL https://sh.rustup.rs \
        | CARGO_HOME=/usr/local/cargo sh -s -- -y --no-modify-path --profile minimal --default-toolchain "${RUST_VERSION}" \
    && curl -fsSL "https://get.nexte.st/${NEXTEST_VERSION}/linux" | tar -xz -C /usr/local/bin \
    && chmod -R a+rX /usr/local/rustup /usr/local/cargo \
    && rustc --version && cargo --version && cargo nextest --version && node --version
