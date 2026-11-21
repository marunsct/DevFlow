#!/usr/bin/env bash
# Resume one run, trying again while the API is not answering: resume_with_retry.sh <run-id>
#
# Measured on 2026-11-21: `ship-live` replaced the containers and then asked the app to resume the paused runs while
# it was still starting; the login answered nothing, `set -e` ended the script, and both runs sat paused with nothing
# left to resume them (found at the next audit, minutes later). Tries RESUME_TRIES times, RESUME_WAIT seconds apart,
# and says loudly, with the command to run, when the run was not resumed. Exit 0 only when it was.
LOOP_SH=${RESUME_LOOP_SH:-scripts/loop/loop.sh}
run=${1:?usage: resume_with_retry.sh <run-id>}
for attempt in $(seq 1 "${RESUME_TRIES:-12}"); do
  out=$(timeout 120 "$LOOP_SH" resume "$run" 2>/dev/null | tail -1 || true)
  if echo "$out" | grep -q "resumed"; then echo "$out" | cut -c1-120; exit 0; fi
  sleep "${RESUME_WAIT:-10}"
done
echo "ship-live: $run WAS NOT RESUMED - the API did not answer; resume it now: scripts/loop/loop.sh resume $run" >&2
exit 1
