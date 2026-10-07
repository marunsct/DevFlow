#!/usr/bin/env bash
# One entry point for the harness improvement loop. See docs/monitoring-handover.md
# section 0 for the loop itself; this script is only the mechanics.
#
#   scripts/loop/loop.sh status              state of the current run + anything else running
#   scripts/loop/loop.sh start [brief]       create and start a run (default tests/brief_low.md)
#   scripts/loop/loop.sh cancel [run-id]     cancel a run (default: the current one); needs LOOP_USER/LOOP_PASSWORD
#   scripts/loop/loop.sh wait [minutes]      block until the run ends or N minutes pass (default 18),
#                                            then print status, key log lines and the audit
#   scripts/loop/loop.sh audit [run-id]      failure / redundancy audit of a run (audit_live.py)
#   scripts/loop/loop.sh stage <stage> [HH:MM]  trace one stage (stage_trace.py; HH:MM is UTC)
#   scripts/loop/loop.sh reads [run-id]      redundant reads by stage and file (redundant_reads.py)
#   scripts/loop/loop.sh timing [run-id..]   where the wall-clock time went: model vs tools, phases, reasoning share (run_timing.py)
#   scripts/loop/loop.sh product [run-id]    audit the generated product: files, code lines, the
#                                            harness's claims, and the product's own tests (product_audit.py)
#   scripts/loop/loop.sh deploy              rebuild + restart app and worker, verify the image
#                                            matches the working tree, list runs orphan recovery revived
#   scripts/loop/loop.sh suite               the full test suite, logged to data/loop/suite.log
#   scripts/loop/loop.sh bench <name>        start a run from benchmarks/<name>/brief.md (needs LOOP_USER/LOOP_PASSWORD)
#   scripts/loop/loop.sh score [run] [name]  score a run's product against the benchmark's hidden tests
#                                            (scripts/bench/score.py); the result lands in data/bench/<run>.json
#   scripts/loop/loop.sh checks [labels]     how often each cross-file check fires over the stored
#                                            workspaces, and its precision against labels (check_precision.py)
#   scripts/loop/loop.sh defects [run-id]    each round's defect queue: the check that raised each
#                                            defect and what became of it (defects.py)
#   scripts/loop/loop.sh asked [run-id] <stage> [visit] [--full] [--system]
#                                            what a stage was told, the calls it made, and its answer (asked.py)
#   scripts/loop/loop.sh failures [run-id] [--full]
#                                            each failing acceptance test: criterion, error, the page (failures.py)
#
# LOOP_SHADOW_SCORE=1 makes `wait` also score the product against the benchmark's
# hidden tests at every check - for the operator only, off by default: a score in
# view mid-run invites tuning the harness to the benchmark instead of fixing its
# faults in general. The hidden tests are deleted from the worker right after.
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

bench)
  name="${2:?name a benchmark under benchmarks/}"
  [ -f "benchmarks/$name/brief.md" ] || { echo "no benchmark named $name" >&2; exit 2; }
  "$0" start "benchmarks/$name/brief.md"
  ;;

score)
  run="${2:-$(current)}"
  brief=$(cat "$STATE/current_brief.txt" 2>/dev/null || true)
  name="${3:-$(echo "$brief" | sed -n 's#^benchmarks/\([^/]*\)/brief.md$#\1#p')}"
  [ -n "$name" ] && [ -d "benchmarks/$name/hidden" ] || { echo "say which benchmark: score <run> <name>" >&2; exit 2; }
  ws="/app/data/workspaces/default/workspace-$run"
  project=$(docker compose exec -T worker cat "$ws/.project-directory" 2>/dev/null | tr -d '\r\n')
  [ -n "$project" ] || { echo "$run has no project directory yet" >&2; exit 1; }
  docker compose exec -T -u root worker sh -c "rm -rf /tmp/bench-src/$name && mkdir -p /tmp/bench-src"
  docker cp "benchmarks/$name" "langchain-worker-1:/tmp/bench-src/$name" >/dev/null
  docker cp scripts/bench/score.py langchain-worker-1:/tmp/bench-src/score.py >/dev/null
  docker compose exec -T -u root worker chown -R appuser:appuser /tmp/bench-src
  status=$("${DB[@]}" "select status from runs where run_id='$run'" | tr -d '[:space:]')
  docker compose exec -T worker python /tmp/bench-src/score.py "$ws/$project" "/tmp/bench-src/$name" "/tmp/bench-$run.json" "$status"
  mkdir -p data/bench
  docker cp "langchain-worker-1:/tmp/bench-$run.json" "data/bench/$run.json" >/dev/null && echo "result: data/bench/$run.json"
  # The hidden tests and the copy they ran against leave the worker at once:
  # it is the container the harness's agents work in.
  docker compose exec -T -u root worker rm -rf /tmp/bench-src /tmp/bench-work "/tmp/bench-$run.json" || true
  ;;

mutate)
  # How strong is the run's own locked suite? See scripts/bench/mutate.py.
  run="${2:-$(current)}"; count="${3:-12}"
  docker cp scripts/bench/mutate.py langchain-worker-1:/tmp/mutate.py >/dev/null
  docker compose exec -T worker python /tmp/mutate.py "/app/data/workspaces/default/workspace-$run" "/tmp/mutate-$run.json" "$count"
  mkdir -p data/bench/mutation
  docker cp "langchain-worker-1:/tmp/mutate-$run.json" "data/bench/mutation/$run.json" >/dev/null && echo "result: data/bench/mutation/$run.json"
  ;;

bench-report)
  "$PY" scripts/bench/report.py data/bench
  ;;

cancel)
  run="${2:-$(current)}"
  : "${LOOP_USER:?set LOOP_USER to the loop operator account}"
  : "${LOOP_PASSWORD:?set LOOP_PASSWORD for that account}"
  token=$(curl -s -X POST "$API/api/auth/token" --data-urlencode "username=$LOOP_USER" \
            --data-urlencode "password=$LOOP_PASSWORD" |
          "$PY" -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
  curl -s -X POST "$API/api/runs/$run/cancel" -H "Authorization: Bearer $token"
  echo
  echo "cancel requested for $run at $(jst +%H:%M) JST: $("${DB[@]}" "select status from runs where run_id='$run'")"
  ;;
wait)
  minutes="${2:-18}"
  run=$(current)
  echo "waiting on $run; next report by $(jst -d "+$minutes minutes" +%H:%M) JST"
  end=$(( $(date +%s) + minutes * 60 ))
  status=""
  while [ "$(date +%s)" -lt "$end" ]; do
    status=$("${DB[@]}" "select status from runs where run_id='$run'" 2>/dev/null || true)
    if [ "$status" = failed ]; then
      # A deploy mid-run marks it failed ("the worker ... stopped without
      # finishing") and orphan recovery resumes it within about two minutes.
      sleep 150
      status=$("${DB[@]}" "select status from runs where run_id='$run'" 2>/dev/null || true)
    fi
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
  if [ "${LOOP_SHADOW_SCORE:-0}" = 1 ]; then
    echo "--- shadow score (operator only; never shown to the harness) ---"
    "$0" score "$run" 2>&1 | grep -E "hidden tests pass|FALSE ACCEPTANCE|^  FAIL" | head -6 || true
  fi
  ;;

audit)  in_worker audit_live.py "${2:-$(current)}" ;;
defects) in_worker defects.py "${2:-$(current)}" ;;
asked)
  shift
  case "${1:-}" in run-*) ;; *) set -- "$(current)" "$@" ;; esac
  in_worker asked.py "$@"
  ;;
failures)
  shift
  case "${1:-}" in run-*) ;; *) set -- "$(current)" "$@" ;; esac
  in_worker failures.py "$@"
  ;;
reads)  in_worker redundant_reads.py "${2:-$(current)}" ;;
timing) shift; in_worker run_timing.py "${@:-$(current)}" ;;
product) in_worker product_audit.py "${2:-$(current)}" ;;
checks) in_worker check_precision.py "${2:-}" ;;
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
