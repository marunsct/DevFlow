#!/usr/bin/env bash
# One entry point for the harness improvement loop. See docs/monitoring-handover.md
# section 0 for the loop itself; this script is only the mechanics.
#
#   scripts/loop/loop.sh status              state of the current run + anything else running
#   scripts/loop/loop.sh start [brief]       create and start a run (default tests/brief_low.md)
#   scripts/loop/loop.sh wait [minutes]      block until the run ends or N minutes pass (default 18),
#                                            then print status, key log lines and the audit
#   scripts/loop/loop.sh audit [run-id]      failure / redundancy audit of a run (audit_live.py)
#   scripts/loop/loop.sh stage <stage> [HH:MM]  trace one stage (stage_trace.py; HH:MM is UTC)
#   scripts/loop/loop.sh reads [run-id]      redundant reads by stage and file (redundant_reads.py)
#   scripts/loop/loop.sh deploy              rebuild + restart app and worker, verify the image
#                                            matches the working tree, list runs orphan recovery revived
#   scripts/loop/loop.sh suite               the full test suite, logged to data/loop/suite.log
#
# Credentials: `start` logs in with LOOP_USER / LOOP_PASSWORD from the environment.
# They are never stored in this repository. The loop's operator account is created with
#   docker exec langchain-app-1 python -m app.server.manage create-user <name> --password <pw> --role operator
# Do not use the admin account for the loop.
#
# The current run id is kept in data/loop/current_run.txt (data/ is git-ignored), so a
# new session, or a different account, picks up where the last one stopped.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HERE="$ROOT/scripts/loop"
STATE="$ROOT/data/loop"
API="${LOOP_API:-http://localhost:8000}"
DB=(docker exec langchain-db-1 psql -U postgres -d langchain -tAc)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3
mkdir -p "$STATE"
cd "$ROOT"

current() { cat "$STATE/current_run.txt" 2>/dev/null || { echo "no current run: use 'start'" >&2; exit 1; }; }
in_worker() { local script=$1; shift; docker compose exec -T worker python - "$@" < "$HERE/$script"; }
jst() { TZ=Asia/Tokyo date "$@"; }

case "${1:-status}" in
status)
  run=$(current)
  echo "current run: $run"
  "${DB[@]}" "select status, left(coalesce(error,''),300), updated_at from runs where run_id='$run'"
  echo "live runs:"
  "${DB[@]}" "select run_id, status, updated_at from runs where status in ('running','queued','pending')"
  ;;

start)
  brief="${2:-tests/brief_low.md}"
  : "${LOOP_USER:?set LOOP_USER to the loop operator account}"
  : "${LOOP_PASSWORD:?set LOOP_PASSWORD for that account}"
  token=$(curl -s -X POST "$API/api/auth/token" --data-urlencode "username=$LOOP_USER" \
            --data-urlencode "password=$LOOP_PASSWORD" |
          "$PY" -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
  run=$(curl -s -X POST "$API/api/runs" -H "Authorization: Bearer $token" -F "files=@$brief" |
        "$PY" -c "import sys,json; d=json.load(sys.stdin); print(d.get('run_id') or d.get('id'))")
  curl -s -X POST "$API/api/runs/$run/start" -H "Authorization: Bearer $token" \
       -H "Content-Type: application/json" -d '{"auto_approve": true}'
  echo
  echo "$run" > "$STATE/current_run.txt"
  echo "$brief" > "$STATE/current_brief.txt"
  echo "started $run from $brief at $(jst +%H:%M) JST"
  ;;

wait)
  minutes="${2:-18}"
  run=$(current)
  echo "waiting on $run; next report by $(jst -d "+$minutes minutes" +%H:%M) JST"
  end=$(( $(date +%s) + minutes * 60 ))
  status=""
  while [ "$(date +%s)" -lt "$end" ]; do
    status=$("${DB[@]}" "select status from runs where run_id='$run'" 2>/dev/null || true)
    case "$status" in completed|failed|cancelled) break ;; esac
    sleep 30
  done
  status=$("${DB[@]}" "select status from runs where run_id='$run'" 2>/dev/null || true)
  echo "=== $(jst +%H:%M) JST  $run: $status ==="
  "${DB[@]}" "select left(coalesce(error,''),600) from runs where run_id='$run'"
  docker compose logs worker --since "${minutes}m" 2>&1 |
    grep -iE "Traceback|thinking switched off|output budget|after this reply's earlier edits|Framework instructions" |
    tail -8 || true
  in_worker audit_live.py "$run"
  ;;

audit)  in_worker audit_live.py "${2:-$(current)}" ;;
reads)  in_worker redundant_reads.py "${2:-$(current)}" ;;
stage)
  [ -n "${2:-}" ] || { echo "usage: loop.sh stage <stage> [HH:MM UTC]" >&2; exit 2; }
  in_worker stage_trace.py "$(current)" "$2" "${3:-}"
  ;;

deploy)
  echo "live runs before deploy (they will be resumed by orphan recovery):"
  "${DB[@]}" "select run_id, status from runs where status in ('running','queued','pending')"
  docker compose build app worker >/dev/null
  docker compose up -d app worker
  sleep 10
  # The image bakes src/ in; a restart without a build deploys nothing. Prove it.
  pkg=$(docker compose exec -T worker python -c "import app,os;print(os.path.dirname(app.__file__))")
  stale=0
  for f in $(git diff --name-only HEAD~1 -- src/app | sed 's#^src/app/##'); do
    [ -f "src/app/$f" ] || continue
    here=$(sha1sum "src/app/$f" | cut -c1-12)
    there=$(docker compose exec -T worker sha1sum "$pkg/$f" | cut -c1-12)
    [ "$here" = "$there" ] || { echo "STALE in image: $f"; stale=1; }
  done
  [ "$stale" = 0 ] && echo "image matches the working tree for the last commit's files"
  echo "live runs after deploy:"
  "${DB[@]}" "select run_id, status from runs where status in ('running','queued','pending')"
  ;;

suite)
  log="$STATE/suite.log"
  echo "suite -> $log (about 2.5 minutes)"
  ENV=development timeout 900 "$PY" -m pytest tests/ -q --no-cov -p no:cacheprovider \
      -o console_output_style=count > "$log" 2>&1 || true
  grep -E "^(FAILED|ERROR)" "$log" | head -20 || true
  tail -1 "$log"
  echo "(the three tests/test_codebase_seeding_api.py failures need S3 credentials this host lacks)"
  ;;

*) sed -n '2,20p' "$0"; exit 2 ;;
esac
