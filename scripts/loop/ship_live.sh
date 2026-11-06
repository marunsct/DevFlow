#!/usr/bin/env bash
# Deploy the pushed commit into the live runs in one checked step: loop.sh ship-live
#
# Measured on 2026-11-05/06: three operator slips in one night - a deploy sent with the pause skipped (the login was
# not loaded, so both runs sat orphaned ~18 min), a doubled `pool_grow`, and a routine `pool_grow` that made Celery
# fork and kill a pool process every 4 s. This does the steps in order and checks each:
#   1. the operator login is loaded, or nothing is touched;
#   2. every running run is paused (and the deploy refused if one did not pause);
#   3. `loop.sh deploy` with BOUNDARY_WAIT=0;
#   4. each run paused here is resumed;
#   5. no pool churn (a SIGKILLed pool process is shrunk away), and each resumed run is running a task.
# It never grows the pool: two slots serve one run per port.
set -euo pipefail
cd "$(dirname "$0")/../.."
L=scripts/loop/loop.sh
WORKER_C=$(docker compose ps -q worker 2>/dev/null | head -1 || true); WORKER_C=${WORKER_C:-langchain-worker-1}

eval "$(sed -n 65p docs/HANDOVER.md)"
export LOOP_USER LOOP_PASSWORD
if [ -z "${LOOP_USER:-}" ] || [ -z "${LOOP_PASSWORD:-}" ]; then
  echo "ship-live: the operator login is not loaded; nothing was touched" >&2; exit 1
fi

runs=$("$L" status 2>/dev/null | sed -n 's/^\(run-[0-9a-f-]\{36\}\)|running.*/\1/p' | sort -u)
paused=()
for run in $runs; do
  if timeout 900 "$L" rewind --pause-only "$run" | tail -1 | grep -q "paused"; then
    paused+=("$run")
  else
    echo "ship-live: $run did not pause; deploy refused (resume what was paused: loop.sh resume <run>)" >&2
    for done_run in "${paused[@]}"; do "$L" resume "$done_run" >/dev/null 2>&1 || true; done
    exit 1
  fi
done
echo "ship-live: paused ${#paused[@]} run(s): ${paused[*]:-none}"

BOUNDARY_WAIT=0 timeout 1500 "$L" deploy | grep -E "image matches|error|ERROR" || true

for run in "${paused[@]}"; do
  timeout 120 "$L" resume "$run" | tail -1 | cut -c1-120
done

sleep 45
for attempt in 1 2 3; do
  kills=$(docker logs --since 20s "$WORKER_C" 2>&1 | grep -c SIGKILL || true)
  [ "$kills" = 0 ] && break
  echo "ship-live: pool churn ($kills SIGKILL in 20 s); shrinking by one"
  docker exec "$WORKER_C" sh -c 'timeout 30 celery -A app.server.tasks control pool_shrink 1 -d celery@$HOSTNAME' >/dev/null 2>&1 || true
  sleep 20
done
active=$(docker exec "$WORKER_C" sh -c 'timeout 20 celery -A app.server.tasks inspect active -d celery@$HOSTNAME 2>&1' || true)
missing=0
for run in "${paused[@]}"; do
  if echo "$active" | grep -q "$run"; then echo "ship-live: $run running"; else echo "ship-live: $run NOT running a task" >&2; missing=1; fi
done
exit $missing
