#!/bin/sh
# The reference installs its two dependencies on first start; a product's run installs them itself.
[ -d node_modules ] || npm install --no-audit --no-fund --silent >&2
exec node src/server.ts
