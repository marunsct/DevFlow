#!/usr/bin/env bash
# Print the operator login line of docs/HANDOVER.md (the line marked `# operator-login`), for `eval`.
# Found by its marker, not its line number, so a line added above it changes nothing. Never echo it elsewhere.
set -euo pipefail
file="${HANDOVER_FILE:-$(dirname "$0")/../../docs/HANDOVER.md}"
grep -m1 -E '# operator-login$' "$file"
