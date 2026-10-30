#!/usr/bin/env bash
# Commit and push a change only when the full suite is clean: `loop.sh ship "<commit message>"`.
# Clean means only the three S3 tests in tests/test_codebase_seeding_api.py fail (they need credentials this host lacks).
# Why: twice in one day a change was committed with another test failing, because the commit ran after the suite
# without reading its result. The suite runs here, the failures are read here, and nothing is committed otherwise.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
message="${1:?usage: loop.sh ship \"<commit message>\"}"
cd "$ROOT" || exit 2
"$HERE/loop.sh" suite >/dev/null 2>&1
log="$ROOT/data/loop/suite.log"
other=$(grep -E "^(FAILED|ERROR) " "$log" | grep -v "tests/test_codebase_seeding_api.py" || true)
summary=$(grep -E "passed|failed" "$log" | tail -1)
if [ -n "$other" ] || ! grep -qE "passed" "$log"; then
  echo "NOT SHIPPED - the suite is not clean: $summary"
  [ -n "$other" ] && echo "$other"
  exit 1
fi
git add -A src tests docs scripts docker-compose.yml 2>/dev/null
if git diff --cached --quiet; then echo "nothing to commit ($summary)"; exit 0; fi
# The message carries its own attribution line when the caller wrote one; this one is for a message that has none.
case "$message" in
  *"Co-Authored-By:"*) git commit -q -m "$message" || exit 1 ;;
  *) git commit -q -m "$message

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" || exit 1 ;;
esac
git push -q main harness-hardening-session 2>&1 | grep -v credential
echo "SHIPPED $(git log --oneline -1) - $summary"
