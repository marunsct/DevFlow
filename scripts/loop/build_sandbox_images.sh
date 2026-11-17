#!/bin/sh
# Builds and tags the sandbox images the stack packs name for container mode (LR.30, `app.stacks.packs._sandbox`):
# one per toolchain, each FROM the Playwright image every pack pins, adding the toolchain and its test runners.
#
#     scripts/loop/build_sandbox_images.sh              every image
#     scripts/loop/build_sandbox_images.sh rust go      only these
#
# Each `deploy/sandbox-images/<toolchain>/Dockerfile` is tagged `harness-sandbox-<toolchain>:pw<playwright>`, the
# name `_sandbox.built_image` gives the packs. Run it on the host whose Docker the sandbox's proxy reaches: the proxy
# refuses builds, so `SANDBOX_EXECUTION_MODE=container` finds an image only if it was built here first. A pack that
# needs only Node runs in the Playwright image itself, which Docker pulls on first use.
cd "$(dirname "$0")/../.." || exit 1

playwright=$(sed -n 's/^PLAYWRIGHT = "\([0-9.]*\)"$/\1/p' src/app/stacks/packs/_javascript.py)
if [ -z "$playwright" ]; then
  echo "could not read the Playwright release from src/app/stacks/packs/_javascript.py" >&2
  exit 1
fi

if [ "$#" -gt 0 ]; then
  toolchains="$*"
else
  toolchains=$(for dockerfile in deploy/sandbox-images/*/Dockerfile; do basename "$(dirname "$dockerfile")"; done)
fi

failed=""
for toolchain in $toolchains; do
  dockerfile="deploy/sandbox-images/$toolchain/Dockerfile"
  if [ ! -f "$dockerfile" ]; then
    echo "no $dockerfile" >&2
    failed="$failed $toolchain"
    continue
  fi
  tag="harness-sandbox-$toolchain:pw$playwright"
  echo "== $tag"
  if docker build --pull --build-arg "PLAYWRIGHT_VERSION=$playwright" -t "$tag" -f "$dockerfile" "deploy/sandbox-images/$toolchain"; then
    echo "built $tag"
  else
    failed="$failed $toolchain"
  fi
done

if [ -n "$failed" ]; then
  echo "failed:$failed" >&2
  exit 1
fi
echo "all built"
