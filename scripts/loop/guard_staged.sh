#!/usr/bin/env bash
# Refuse a commit whose staged docker-compose.yml adds the owner's local database port (127.0.0.1:5433:5432).
# That hunk is the owner's uncommitted edit and must never be committed with the harness's own changes
# (AGENTS.md). Stage compose changes line by line (`git add -p`, or `git hash-object -w` + `update-index`).
set -euo pipefail
added=$(git diff --cached -U0 -- docker-compose.yml | grep -E '^\+[^+]' || true)
if printf '%s\n' "$added" | grep -q '5433'; then
  echo "guard: the staged docker-compose.yml adds the owner's 5433 database port - unstage that hunk (git restore --staged -p docker-compose.yml)" >&2
  exit 1
fi
exit 0
