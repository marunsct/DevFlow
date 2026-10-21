#!/usr/bin/env bash
# One entry point for the harness improvement loop. See docs/monitoring-handover.md
# section 0 for the loop itself; this script is only the mechanics.
#
#   scripts/loop/loop.sh status [run]        state of the run (default: current) + anything else running
#   scripts/loop/loop.sh start [brief]       create and start a run (default tests/brief_low.md)
#   scripts/loop/loop.sh cancel [run-id]     cancel a run (default: the current one); needs LOOP_USER/LOOP_PASSWORD
#   scripts/loop/loop.sh wait [minutes] [run] block until the run (default: current) ends or N minutes pass (default 18),
#                                            then print status, key log lines and the audit
#   scripts/loop/loop.sh audit [run-id]      failure / redundancy audit of a run (audit_live.py)
#   scripts/loop/loop.sh stage <stage> [HH:MM]  trace one stage (stage_trace.py; HH:MM is UTC)
#   scripts/loop/loop.sh reads [run-id]      redundant reads by stage and file (redundant_reads.py)
#   scripts/loop/loop.sh deploy-app          rebuild and restart the app container only (API, UI); the worker and live runs untouched
#   scripts/loop/loop.sh timing [run-id..]   where the wall-clock time went: model vs tools, phases, reasoning share (run_timing.py)
#   scripts/loop/loop.sh kpi [run-id]        the run's KPIs as JSON (data/kpi/<run>.json), a row of data/kpi/ledger.csv,
#                                            and any KPI past 1.5x its 5-run mean (kpi.py, kpi_ledger.py); score runs it too
#   scripts/loop/loop.sh product [run-id]    audit the generated product: files, code lines, the
#                                            harness's claims, and the product's own tests (product_audit.py)
#   scripts/loop/loop.sh deploy              rebuild + restart app and worker, verify the image
#                                            matches the working tree, list runs orphan recovery revived
#   scripts/loop/loop.sh suite               the full test suite, logged to data/loop/suite.log
#   scripts/loop/loop.sh fitness [--edits]   five scripted tool calls to the build model: FIT/USABLE/UNFIT;
#                                            --edits also measures well-formed whole-file writes vs edits (BH)
#                                            (model_fitness.py); before a run, never beside a live one
#   scripts/loop/loop.sh bench <name>        start a run from benchmarks/<name>/brief.md (needs LOOP_USER/LOOP_PASSWORD);
#                                            a brownfield bench's bench.json "base" seeds the workspace (SEED=<dir> for start)
#   scripts/loop/loop.sh score [run] [name]  score a run's product against the benchmark's hidden tests
#                                            (scripts/bench/score.py); the result lands in data/bench/<run>.json
#   scripts/loop/loop.sh checks [labels] [--write]  how often each cross-file check fires over the stored
#                                            workspaces, and its precision against labels (check_precision.py)
#   scripts/loop/loop.sh defects [run-id]    each round's defect queue: the check that raised each
#                                            defect and what became of it (defects.py)
#   scripts/loop/loop.sh asked [run-id] <stage> [visit] [--full] [--system]
#                                            what a stage was told, the calls it made, and its answer (asked.py)
#   scripts/loop/loop.sh failures [run-id] [--full]
#                                            each failing acceptance test: criterion, error, the page (failures.py)
#   scripts/loop/loop.sh ready               is the model the settings name served where they name it?
#                                            last line ALL READY, or start nothing (model_ready.py)
#   scripts/loop/loop.sh resumed             after a deploy while a run was live: wait up to 10 minutes
#                                            for orphan recovery to resume it (await_resume.sh)
#   scripts/loop/loop.sh freshness           pins in the stack packs a major version behind their registry
#                                            (pack_freshness.py, on the host)
#   scripts/loop/loop.sh reasoning-probe [run]  does the server shorten replies when asked to think less? prints a plan
#                                            unless given `run` (uses the model: only when no run waits)
#   scripts/loop/loop.sh lessons [min-runs]  failed-call shapes recurring across runs, by language: candidates
#                                            for guidance in src/app/plugins/seed.py (lessons.py, in the worker)
#   scripts/loop/loop.sh nightly             verify every pack in the worker, then the freshness report, into
#                                            data/loop/nightly-<date>.log - skipped while a run is live
#
# LOOP_SHADOW_SCORE=1 makes `wait` also score the product against the benchmark's
# hidden tests at every check - for the operator only, off by default: a score in
# view mid-run invites tuning the harness to the benchmark instead of fixing its
# faults in general. The hidden tests are deleted from the worker right after.
#
# Credentials: `bench`, `start` and `cancel` log in with LOOP_USER / LOOP_PASSWORD from the
# environment. The loop's operator account and its password are written in
# docs/monitoring-handover.md section 0.3.1 (at the owner's request; it exists only in the
# local database). A fresh database lacks it; create it with
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

# One group, parsed whole before it runs, that exits inside itself: bash reads a script as it
# goes, so an edit to this file while a long command runs - a deploy, the suite - would otherwise be
# read from the old byte offset when the command ends - a syntax error at a random line.
{
case "${1:-status}" in
status)
  run="${2:-$(current)}"
  echo "current run: $run"
  "${DB[@]}" "select status, left(coalesce(error,''),300), updated_at from runs where run_id='$run'"
  echo "live runs:"
  "${DB[@]}" "select run_id, status, updated_at from runs where status in ('running','queued','pending')"
  ;;

start)
  brief="${2:-tests/brief_low.md}"
  # Never a run on a model that does not answer: the readiness check is part
  # of starting, so a pipeline around `ready` cannot swallow its verdict.
  if ! in_worker model_ready.py | grep -q "ALL READY"; then
    in_worker model_ready.py | grep -v "^READY" >&2 || true
    echo "not starting: the models are not all ready" >&2
    exit 1
  fi
  : "${LOOP_USER:?set LOOP_USER to the loop operator account}"
  : "${LOOP_PASSWORD:?set LOOP_PASSWORD for that account}"
  token=$(curl -s -X POST "$API/api/auth/token" --data-urlencode "username=$LOOP_USER" \
            --data-urlencode "password=$LOOP_PASSWORD" |
          "$PY" -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
  run=$(curl -s -X POST "$API/api/runs" -H "Authorization: Bearer $token" -F "files=@$brief" |
        "$PY" -c "import sys,json; d=json.load(sys.stdin); print(d.get('run_id') or d.get('id'))")
  # A brownfield run (plan BW.3): SEED names a directory, the previous product,
  # uploaded as an archive and extracted into the workspace before the first agent reads it.
  source=""
  if [ -n "${SEED:-}" ]; then
    [ -d "$SEED" ] || { echo "SEED is not a directory: $SEED" >&2; exit 2; }
    archive="$STATE/seed-$run.tar.gz"
    tar -czf "$archive" -C "$SEED" .
    upload=$(curl -s -X POST "$API/api/runs/$run/codebase" -H "Authorization: Bearer $token" -F "file=@$archive" |
             "$PY" -c "import sys,json; print(json.load(sys.stdin).get('upload_id') or '')")
    rm -f "$archive"
    [ -n "$upload" ] || { echo "the base was not uploaded" >&2; curl -s -X DELETE "$API/api/runs/$run" -H "Authorization: Bearer $token" >/dev/null; exit 1; }
    source=", \"source\": {\"type\": \"archive\", \"upload_id\": \"$upload\"}"
  fi
  # A refused start (a frontier model asked for and not answering, a run
  # already started) said "started" before; it names the refusal now, and the
  # run it created is not left behind as the current one.
  answer=$(curl -s -w '\n%{http_code}' -X POST "$API/api/runs/$run/start" -H "Authorization: Bearer $token" \
       -H "Content-Type: application/json" -d "{\"auto_approve\": true${DELIVERY:+, \"delivery_mode\": \"$DELIVERY\"}${FRONTIER:+, \"use_frontier_model\": $FRONTIER}$source}")
  code=$(echo "$answer" | tail -n 1)
  echo "$answer" | sed '$d'
  if [ "$code" != "202" ]; then
    echo "not started: the server answered HTTP $code" >&2
    curl -s -X DELETE "$API/api/runs/$run" -H "Authorization: Bearer $token" >/dev/null
    exit 1
  fi
  echo "$run" > "$STATE/current_run.txt"
  echo "$brief" > "$STATE/current_brief.txt"
  echo "started $run from $brief at $(jst +%H:%M) JST"
  ;;

bench)
  name="${2:?name a benchmark under benchmarks/}"
  [ -f "benchmarks/$name/brief.md" ] || { echo "no benchmark named $name" >&2; exit 2; }
  # A brownfield bench names its previous product in bench.json's "base"; the run starts from it.
  base=$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1])).get('base') or '')" "benchmarks/$name/bench.json")
  if [ -n "$base" ]; then
    SEED="benchmarks/$name/$base" "$0" start "benchmarks/$name/brief.md"
  else
    "$0" start "benchmarks/$name/brief.md"
  fi
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
  # What the release knew it did not prove rides the export (Initiative J.4).
  # An old database without the column answers empty, which scores as no gaps.
  gaps=$("${DB[@]}" "select completion_gaps from runs where run_id='$run'" 2>/dev/null | head -1)
  # Whether the run was started from this benchmark's own brief, by content:
  # every benchmark's brief is named brief.md (Initiative W.1, score.py).
  own=""
  doc=$("${DB[@]}" "select document_paths from runs where run_id='$run'" 2>/dev/null \
    | "$PY" -c 'import json,sys;p=json.loads(sys.stdin.read() or "[]");print(p[0] if len(p)==1 else "")' 2>/dev/null)
  if [ -n "$doc" ] && docker compose exec -T worker test -f "$doc"; then
    # Normalised text and a similarity, not a byte comparison (Initiative AN).
    own=$(docker compose exec -T worker cat "$doc" | "$PY" "$ROOT/scripts/bench/brief_match.py" - "benchmarks/$name/brief.md" 2>/dev/null | tr ' ' ':')
  fi
  docker compose exec -T worker python /tmp/bench-src/score.py "$ws/$project" "/tmp/bench-src/$name" "/tmp/bench-$run.json" "$status" "$gaps" "$own"
  mkdir -p data/bench
  docker cp "langchain-worker-1:/tmp/bench-$run.json" "data/bench/$run.json" >/dev/null && echo "result: data/bench/$run.json"
  # The score alone - no test names - for the outcome dashboard (app.server.outcomes).
  "$PY" -c 'import json,sys;d=json.load(open(sys.argv[1]));print(json.dumps({k:d.get(k) for k in ("benchmark","passed","total","score","completion_gaps","brief_mismatch")}))' "data/bench/$run.json" \
    | docker compose exec -T worker sh -c "mkdir -p /app/data/outcomes && cat > /app/data/outcomes/$run.json" || true
  # The hidden tests and the copy they ran against leave the worker at once:
  # it is the container the harness's agents work in.
  docker compose exec -T -u root worker rm -rf /tmp/bench-src /tmp/bench-work "/tmp/bench-$run.json" || true
  # Every scored run's KPIs, beside the runs before it (Initiative W.4).
  "$0" kpi "$run" || true
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

rewind)
  # Rewind a run to the start of a stage, its files as they were then, and run
  # it on from there (owner, 2026-10-20): after a fix, instead of a new run that
  # redoes the work the fix did not touch. A live run is paused first; a paused,
  # failed or cancelled one is rewound as it is. Deploy between the pause and
  # the rewind, and the rewound stage runs on the new code:
  #   loop.sh rewind --pause-only; BOUNDARY_WAIT=0 loop.sh deploy; loop.sh rewind <stage>
  #   loop.sh rewind <graph stage> [run-id] [at or before, e.g. 2026-10-19T22:20]
  : "${LOOP_USER:?set LOOP_USER to the loop operator account}"
  : "${LOOP_PASSWORD:?set LOOP_PASSWORD for that account}"
  stage="${2:?usage: loop.sh rewind <graph stage>|--pause-only [run-id] [at-or-before]}"
  run="${3:-$(current)}"
  token=$(curl -s -X POST "$API/api/auth/token" --data-urlencode "username=$LOOP_USER" \
            --data-urlencode "password=$LOOP_PASSWORD" |
          "$PY" -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
  status() { "${DB[@]}" "select status from runs where run_id='$run'" | tr -d '[:space:]'; }
  if [ "$(status)" = "running" ] || [ "$(status)" = "queued" ]; then
    curl -s -X POST "$API/api/runs/$run/pause" -H "Authorization: Bearer $token" >/dev/null
    waited=0
    while [ "$(status)" != "paused" ] && [ "$waited" -lt 600 ]; do sleep 5; waited=$((waited + 5)); done
    echo "paused $run after ${waited}s ($(jst +%H:%M) JST): $(status)"
  fi
  [ "$stage" = "--pause-only" ] && exit 0
  # Timeouts on both calls (plan OP.4): listing the points of a long run took
  # minutes, and a call with none waited on a server that had stopped answering.
  checkpoint=$(curl -s -m "${REWIND_TIMEOUT:-600}" "$API/api/runs/$run/rewind-points" -H "Authorization: Bearer $token" |
               "$PY" "$HERE/rewind_point.py" "$stage" "${4:-}") || exit 1
  answer=$(curl -s -m "${REWIND_TIMEOUT:-600}" -w '\n%{http_code}' -X POST "$API/api/runs/$run/rewind" -H "Authorization: Bearer $token" \
       -H "Content-Type: application/json" -d "{\"checkpoint_id\": \"$checkpoint\"}")
  code=$(echo "$answer" | tail -n 1)
  echo "$answer" | sed '$d'; echo
  [ "$code" = "202" ] || { echo "not rewound: the server answered HTTP $code" >&2; exit 1; }
  echo "rewound $run to $stage at $(jst +%H:%M) JST: $(status)"
  ;;
wait)
  minutes="${2:-18}"
  run="${3:-$(current)}"
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
kpi)
  run="${2:-$(current)}"
  mkdir -p data/kpi
  # Written beside the file and moved over it only when the worker succeeded: a
  # failed run of the script used to leave an empty or half JSON in its place.
  if in_worker kpi.py "$run" > "data/kpi/$run.json.tmp"; then
    mv "data/kpi/$run.json.tmp" "data/kpi/$run.json"
    bench=$(echo "$(cat "$STATE/current_brief.txt" 2>/dev/null)" | sed -n 's#^benchmarks/\([^/]*\)/brief.md$#\1#p')
    "$PY" "$HERE/kpi_ledger.py" "data/kpi/$run.json" data/kpi/ledger.csv "$bench"
    # And the run's reader inputs into the corpus the suite replays (plan RC.1).
    "$0" corpus harvest "$run" >/dev/null 2>&1 || echo "kpi: the corpus harvest did not run" >&2
  else
    rm -f "data/kpi/$run.json.tmp"; echo "kpi: the worker could not read $run's transcript; nothing was changed" >&2; exit 1
  fi
  ;;
product) in_worker product_audit.py "${2:-$(current)}" ;;
corpus)
  # The reader corpus (plan RC): `corpus harvest [run]` keeps a run's reader inputs
  # with today's results and copies the corpus to the host's data/corpus, where the
  # suite replays it; `corpus` lists it; `corpus accept` keeps today's results after
  # a reader change made on purpose.
  case "${2:-list}" in
  harvest)
    in_worker corpus.py "${3:-$(current)}"
    mkdir -p data/corpus && docker cp langchain-worker-1:/app/data/corpus/. data/corpus/ >/dev/null 2>&1 || true
    ;;
  accept) DATA_DIR=data PYTHONPATH="$ROOT/src" "$PY" -c 'from app.observability.reader_corpus import replay; print(replay(accept=True))' ;;
  *) DATA_DIR=data PYTHONPATH="$ROOT/src" "$PY" -c 'from app.observability.reader_corpus import sizes, replay; print(sizes()); print("changed:", replay())' ;;
  esac
  ;;
checks)
  shift
  # The scored runs are the host's (data/bench); the measurement runs in the worker.
  case " $* " in *" --write "*) (cd "$ROOT" && docker compose cp data/bench worker:/app/data/ >/dev/null) ;; esac
  in_worker check_precision.py "$@"
  ;;
ready)  in_worker model_ready.py ;;
fitness) shift; in_worker model_fitness.py "$@" ;;
reasoning-probe) shift; in_worker reasoning_probe.py "${@:-plan}" ;;
resumed) sh "$HERE/await_resume.sh" ;;
stage)
  [ -n "${2:-}" ] || { echo "usage: loop.sh stage <stage> [HH:MM UTC]" >&2; exit 2; }
  in_worker stage_trace.py "$(current)" "$2" "${3:-}"
  ;;

deploy-app)
  # The app container alone - the API and the UI - for a change that touches
  # nothing the worker runs (a screen, a route). A full deploy restarts the
  # worker, and with it the live run's stage, for a change the run never sees.
  # Built from a clean checkout of HEAD, under the deploy lock, like `deploy`.
  exec 9>"$STATE/deploy.lock"
  flock -n 9 || { echo "another deploy is running (lock $STATE/deploy.lock); not starting a second" >&2; exit 1; }
  head_tree=$(mktemp -d)/head
  built=$(git -C "$ROOT" rev-parse HEAD)
  git -C "$ROOT" worktree add -q --detach "$head_tree" "$built"
  docker compose -p langchain --env-file "$ROOT/.env" -f "$head_tree/docker-compose.yml" \
    build --progress=plain --build-arg HARNESS_COMMIT="$built" app >/dev/null 2>&1
  git -C "$ROOT" worktree remove --force "$head_tree"
  docker compose up -d --no-deps app
  echo "app rebuilt from $(git -C "$ROOT" rev-parse --short "$built") at $(jst +%H:%M) JST; the worker and its runs were not touched"
  ;;
deploy)
  # One deploy at a time (plan OP.4): two sessions deploying at once left
  # containers stuck at `Created`.
  exec 9>"$STATE/deploy.lock"
  flock -n 9 || { echo "another deploy is running (lock $STATE/deploy.lock); not starting a second" >&2; exit 1; }
  echo "live runs before deploy (they will be resumed by orphan recovery):"
  "${DB[@]}" "select run_id, status from runs where status in ('running','queued','pending')"
  # Built from a clean checkout of HEAD, never the working tree: another
  # session's uncommitted, unverified edits sat in the same tree, and a build
  # of it shipped them into the live run.
  head_tree=$(mktemp -d)/head
  built=$(git -C "$ROOT" rev-parse HEAD)
  git -C "$ROOT" worktree add -q --detach "$head_tree" "$built"
  docker compose -p langchain --env-file "$ROOT/.env" -f "$head_tree/docker-compose.yml" \
    build --progress=plain --build-arg HARNESS_COMMIT="$built" app worker >/dev/null 2>&1
  git -C "$ROOT" worktree remove --force "$head_tree"
  # At a stage boundary: a resume restarts the running stage's conversation,
  # and one fix stage was restarted five times in an hour by deploys landing
  # mid-stage. Wait (up to BOUNDARY_WAIT seconds, default 1800; 0 skips) for
  # the live run's transcript to name a new stage.
  live=$("${DB[@]}" "select run_id from runs where status='running' limit 1" | tr -d '[:space:]')
  if [ -n "$live" ] && [ "${BOUNDARY_WAIT:-1800}" -gt 0 ]; then
    last_stage() { docker compose exec -T worker sh -c "tail -n 1 \$(ls /app/data/transcripts/$live*.jsonl | head -1)" \
      | python3 -c 'import sys,json; print(json.loads(sys.stdin.read() or "{}").get("stage",""))' 2>/dev/null; }
    was=$(last_stage); waited=0
    echo "waiting for $live to leave stage '$was' ($(jst '+%H:%M JST'))"
    while [ "$(last_stage)" = "$was" ] && [ "$waited" -lt "${BOUNDARY_WAIT:-1800}" ]; do sleep 20; waited=$((waited + 20)); done
    echo "stage now '$(last_stage)' after ${waited}s"
  fi
  # Between model calls (owner, 2026-10-15): hold new calls, wait for the ones
  # in flight to return, then restart (app.models.call_gate). GATE_WAIT caps the
  # wait in seconds; a call still running then is restarted with its stage.
  gate=/app/data/loop/gate
  docker compose exec -T worker sh -c "mkdir -p $gate/inflight && touch $gate/hold"
  waited=0
  while :; do
    # Only markers younger than the longest a model call may run: one left by a
    # process that died mid-call (a power loss, 2026-10-20) is never removed,
    # and the deploy waited its whole GATE_WAIT on it.
    # And only markers whose process still runs: a pause or cancel stops its
    # task with SIGTERM mid-call, the marker stays, and the worker that would
    # forget it at its start is not restarted (2026-10-20: 13 minutes held).
    n=$(docker compose exec -T worker sh -c "for f in \$(find $gate/inflight -type f -mmin -40 2>/dev/null); do p=\${f##*__}; p=\${p%%-*}; [ -d /proc/\$p ] && echo \$f; done | wc -l" | tr -d '[:space:]')
    [ "${n:-0}" = 0 ] && break
    [ "$waited" -ge "${GATE_WAIT:-1800}" ] && { echo "still $n model call(s) in flight after ${waited}s; deploying anyway"; break; }
    [ "$waited" = 0 ] && echo "waiting for $n model call(s) in flight to finish ($(jst '+%H:%M JST'))"
    sleep 5; waited=$((waited + 5))
  done
  [ "$waited" -gt 0 ] && echo "model calls finished after ${waited}s; deploying ($(jst '+%H:%M JST'))"
  docker compose up -d app worker
  # The old processes are gone: their markers mean nothing now. Lift the hold.
  docker compose exec -T worker sh -c "rm -f $gate/inflight/* $gate/hold"
  sleep 10
  # The image bakes src/ in; a restart without a build deploys nothing. Prove it.
  pkg=$(docker compose exec -T worker python -c "import app,os;print(os.path.dirname(app.__file__))")
  stale=0
  # Against the commit that was built: HEAD may have moved while the deploy
  # waited for a stage boundary.
  for f in $(git diff --name-only "$built~1" "$built" -- src/app | sed 's#^src/app/##'); do
    git -C "$ROOT" cat-file -e "$built:src/app/$f" 2>/dev/null || continue
    here=$(git -C "$ROOT" show "$built:src/app/$f" | sha1sum | cut -c1-12)
    there=$(docker compose exec -T worker sha1sum "$pkg/$f" | cut -c1-12)
    [ "$here" = "$there" ] || { echo "STALE in image: $f"; stale=1; }
  done
  [ "$stale" = 0 ] && echo "image matches ${built:0:7} (the commit built) for its files"
  echo "live runs after deploy:"
  "${DB[@]}" "select run_id, status from runs where status in ('running','queued','pending')"
  ;;

freshness) "$PY" "$HERE/pack_freshness.py" ;;
lessons) shift; in_worker lessons.py "${@:-3}" ;;
backup)
  # The run database and the lessons, kept under data/backups/<date> (plan OP.3).
  # `backup --check` restores the newest into a scratch database and counts its runs:
  # a backup nobody has restored is a hope, not a backup.
  if [ "${2:-}" = "--check" ]; then
    dump=$(ls -1d data/backups/*/ 2>/dev/null | sort | tail -1)
    [ -n "$dump" ] && [ -f "$dump/langchain.dump" ] || { echo "no backup to check" >&2; exit 1; }
    scratch="restore_check_$(date +%s)"
    docker exec langchain-db-1 psql -U postgres -qc "create database $scratch" >/dev/null
    docker exec -i langchain-db-1 pg_restore -U postgres --no-owner -d "$scratch" < "$dump/langchain.dump" >/dev/null 2>&1
    restored=$(docker exec langchain-db-1 psql -U postgres -d "$scratch" -tAc "select count(*) from runs" 2>/dev/null | tr -d '[:space:]')
    live=$("${DB[@]}" "select count(*) from runs" | tr -d '[:space:]')
    docker exec langchain-db-1 psql -U postgres -qc "drop database $scratch" >/dev/null
    echo "restore check of $dump: ${restored:-0} run(s) restored, ${live:-?} in the live database"
    [ "${restored:-0}" -gt 0 ] || exit 1
    exit 0
  fi
  dir="data/backups/$(date +%F)"
  mkdir -p "$dir"
  # Custom format, compressed: the checkpoint tables dumped as plain SQL came to 15 GB.
  docker exec langchain-db-1 pg_dump -U postgres -d langchain --no-owner -Fc > "$dir/langchain.dump.tmp" && mv "$dir/langchain.dump.tmp" "$dir/langchain.dump"
  docker cp langchain-worker-1:/app/data/lessons.json "$dir/lessons.json" >/dev/null 2>&1 || true
  # Three days kept.
  ls -1d data/backups/*/ 2>/dev/null | sort | head -n -3 | xargs -r rm -rf
  echo "backup -> $dir ($(du -sh "$dir" | cut -f1))"
  ;;
restore)
  # Into a database of its own, never over the live one (plan OP.3):
  #   loop.sh restore data/backups/<date> <new-database>
  # then point DATABASE_URL at it, or rename it over the live one by hand.
  src="${2:?usage: loop.sh restore <backup-dir> <new-database>}"; target="${3:?name a new database to restore into}"
  [ "$target" != "langchain" ] || { echo "not over the live database; name a new one" >&2; exit 1; }
  docker exec langchain-db-1 psql -U postgres -qc "create database $target" && \
    docker exec -i langchain-db-1 pg_restore -U postgres --no-owner -d "$target" < "$src/langchain.dump" >/dev/null && \
    echo "restored $src into database $target"
  ;;
nightly)
  # The backup first, live run or not: it reads the database and touches nothing else.
  "$0" backup | tee -a "$STATE/nightly.log"
  # Never beside a live run: scaffolding 27 packs competes for its memory and CPU.
  live=$("${DB[@]}" "select count(*) from runs where status in ('running','queued','pending')")
  if [ "${live:-1}" != "0" ]; then echo "$(jst '+%F %H:%M JST') nightly skipped: a run is live" | tee -a "$STATE/nightly.log"; exit 0; fi
  log="$STATE/nightly-$(date +%F).log"
  { echo "== $(jst)"; in_worker verify_packs.py; "$PY" "$HERE/pack_freshness.py"; } > "$log" 2>&1 || true
  echo "$(jst '+%F %H:%M JST') nightly: $(grep -E 'packs scaffolded' "$log" | tail -1); $(tail -1 "$log") -> $log" | tee -a "$STATE/nightly.log"
  ;;
suite)
  log="$STATE/suite.log"
  # Across workers when pytest-xdist is installed (owner, 2026-10-20: testing
  # efficient): measured, the whole suite in 64 s on 12 workers against 290 s
  # on one, with the same result - every fix waited on it before its deploy.
  workers=""
  "$PY" -c "import xdist" 2>/dev/null && workers="-n ${SUITE_WORKERS:-12}"
  echo "suite -> $log (${workers:+about 1 minute on ${SUITE_WORKERS:-12} workers}${workers:-about 5 minutes})"
  # The venv on PATH: tests marked for a bare `python` (the in-container
  # sandbox resolves it with shutil.which) were skipped without it, and one
  # went stale unseen.
  PATH="$ROOT/.venv/bin:$PATH" ENV=development timeout 900 "$PY" -m pytest tests/ -q --no-cov -p no:cacheprovider \
      $workers -o console_output_style=count > "$log" 2>&1 || true
  grep -E "^(FAILED|ERROR)" "$log" | head -20 || true
  tail -1 "$log"
  echo "(the three tests/test_codebase_seeding_api.py failures need S3 credentials this host lacks)"
  # Every other failure once more, alone and in order (plan CH.3): the known
  # flaky tests fail only beside others in the parallel run. Reported apart, so
  # a flaky test is never mistaken for a fix's breakage, nor the other way round.
  again=$(grep -E "^(FAILED|ERROR) " "$log" | grep -v "test_codebase_seeding_api.py" | sed -E 's/^(FAILED|ERROR) //; s/ - .*//' | sort -u)
  if [ -n "$again" ]; then
    PATH="$ROOT/.venv/bin:$PATH" ENV=development timeout 600 "$PY" -m pytest -q --no-cov -p no:cacheprovider $again > "$STATE/suite-again.log" 2>&1 || true
    still=$(grep -E "^(FAILED|ERROR) " "$STATE/suite-again.log" | sed -E 's/^(FAILED|ERROR) //; s/ - .*//' | sort -u)
    for t in $again; do
      if echo "$still" | grep -qxF "$t"; then echo "FAILED alone too: $t"; else echo "flaky (passed alone): $t"; fi
    done
  fi
  ;;

*) sed -n '2,/^set -euo/p' "$0" | sed '$d'; exit 2 ;;
esac
exit $?
}
