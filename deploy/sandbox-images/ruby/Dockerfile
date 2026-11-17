# The sandbox image of the Ruby packs (LR.30, `app.stacks.packs._sandbox`): Ruby with Bundler beside Node and the
# browsers, for container mode, where every agent command runs in a container of its own - the service's suite runs
# under Playwright and starts the Ruby service from inside the same container.
# Built by `scripts/loop/build_sandbox_images.sh`. Ruby matches the packs' `RUBY_VERSION` (3.3), which Ubuntu 24.04
# does not ship, so it is built from Ruby's own release; the build tools stay for gems with native extensions.
ARG PLAYWRIGHT_VERSION=1.64.0
FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-noble

ARG RUBY_VERSION=3.3.8

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git build-essential pkg-config \
        libssl-dev libyaml-dev zlib1g-dev libffi-dev libgmp-dev libreadline-dev libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /tmp/ruby-build \
    && curl -fsSL "https://cache.ruby-lang.org/pub/ruby/${RUBY_VERSION%.*}/ruby-${RUBY_VERSION}.tar.gz" \
        | tar -xz -C /tmp/ruby-build --strip-components=1 \
    && cd /tmp/ruby-build \
    && ./configure --prefix=/usr/local --disable-install-doc --enable-shared \
    && make -j"$(nproc)" && make install \
    && cd / && rm -rf /tmp/ruby-build \
    && ruby --version && gem --version && bundle --version && node --version

# Gems install under the project (`bundle config set --local path vendor/bundle`), never into the image.
ENV BUNDLE_SILENCE_ROOT_WARNING=1
