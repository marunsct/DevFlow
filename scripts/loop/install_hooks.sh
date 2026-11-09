#!/usr/bin/env bash
# Point this clone's git hooks at .githooks (repo-local; changes no global setting).
set -euo pipefail
cd "$(dirname "$0")/../.."
git config core.hooksPath .githooks
echo "hooks: core.hooksPath = .githooks"
