# Handover: running, testing, auditing and building on the harness

The handbook for agents that test, run, audit and build on DevFlow. Rules, mechanics and facts true now; no
history. What is live and the next action: `docs/STATE.md`. How the product works: `docs/PRODUCT.md`. The plan:
`docs/improvement-plan.md`. Decisions of the owner still in force: `docs/owner-decisions.md` (read it before acting
on any subject it lists). Everything below was checked against `scripts/loop/loop.sh` and the scripts it calls.

## 0. The rules that are never optional

- **The model is the owner's.** `scripts/loop/loop.sh ready` must print `ALL READY` (exit 0) before any run; if not,
  start nothing. Never load, unload or change the owner's model or its settings; never kill the owner's GPU or model
  processes (llama-server, LM Studio, unsloth, the :9090 server). Check passively; `lms ps` can wake LM Studio.
  Changing the harness's own default model setting to keep testing is allowed (owner 2026-11-09); loading a model is not.
- **The owner's runs are left alone.** A run started by the owner or the admin account (a UI run, a hosted-model
  test, a paused run) is never cancelled, resumed, rewound or deployed around by you.
- **Fixes are technology-, framework- and product-agnostic.** Stack-specific guidance goes only in
  `src/app/plugins/seed.py`, a stack pack, or a per-language table. A fix must not hinder other stacks.
- **No run ids** in code, comments, prompts or tests.
- **Each new prompt rule gets a test banning the whole words** task, tasks, to-do, todo, button, click, checkbox
  (the rule text must not use them). A plain wording or UI-label change needs no test.
- **Every fix gets a test proven to fail on the old code** (section 4). Load the `unit-testing` skill before writing one.
- **Both suites green** before a push: `loop.sh suite` and `loop.sh suite-production`.
- **Commit and push after every change:** `git push main harness-hardening-session` (the remote is named `main`).
  Update `docs/STATE.md` (what is live, the last runs, the next action) and `docs/PRODUCT.md` (how the product works)
  in the same commit as any change to what is live or how the product behaves.
- **Switch policy (owner):** bug fixes and quality changes are always on, no switch. Only optional non-quality
  improvements go behind a switch, and each is listed and measured in `docs/measuring.md` (`loop.sh measuring`).
- **Secrets:** never print, copy or commit values from `.env` or settings. Use the operator account only (section 2);
  never the admin account, never read or reset its password, never write the settings table directly.
  Never put knowledge or documentation credentials into `sandbox._ENV_PASSTHROUGH`.
- **Times to the owner in JST** (UTC+9). Containers, `docker logs` and transcripts are UTC.
- **Hosted (paid) model tests only when the owner starts or instructs them**; otherwise stubs and local models.
- **Frozen-version measuring (owner 2026-11-18):** a Measure run is one frozen harness SHA, scored by hidden tests
  only; a bug found is filed for the next bundle, not deployed. Fixes ship in bundles at run boundaries. A deploy
  into a live run only for a bug that changes its outcome (the run is then marked `mixed_versions`). In a run's
  first 40 minutes such a bug means cancel, fix, deploy, restart; later, fix, test, push, `ship-live`, and orphan
  recovery resumes the same run; only a major bug cancels a run after its first 40 minutes. UI-only changes
  (`deploy-app`) do not mark runs mixed. The language sweep and the release-candidate count are paused until
  review items 1.7 and 1.8 are built.
- **Keep the owner's features:** dynamic agent-instruction injection, the parallel/linear toggle, the sprint
  summary, work orders, templates, the Sprint Record.
- **Never commit the owner's uncommitted `docker-compose.yml` edit** (the `127.0.0.1:5433:5432` db port). Run
  `scripts/loop/install_hooks.sh` once per clone; the hook (`guard_staged.sh`) refuses such a commit.
- **Do not edit `src/`** while `suite`, `suite-production` or a `ship-live`/`build` is running, and do not edit
  `loop.sh` while a `wait` runs (bash reads the script as it goes).
- `docs/logs.md` was removed by the owner; do not recreate it.

## 1. The standing loop, in order

1. **Run** a benchmark (`loop.sh ready`, then the gated start, section 3). One run per port; both ports take runs.
2. **Audit** every ~10 minutes while a run is live (section 5): `wait`/`audit`, `defects`, `effects`, the stage
   order, the suite's latest pass/fail against the previous check (a fall without a code change is investigated at
   once), and which arm of `docs/measuring.md` the run is in. Efficiency and waste are reported unasked.
3. **Fix in general**, in the harness, not in the product the run built. A clear improvement found in a check is
   built in the same cycle. After three point fixes in one subsystem, review its design.
4. **Test** that fails on the old code (section 4).
5. **Both suites** green: `loop.sh suite`, `loop.sh suite-production`.
6. **Commit and push**, with STATE.md and PRODUCT.md current in the same commit.
7. **Deploy:** at a run boundary with nothing live, `loop.sh deploy`; into live runs, `loop.sh ship-live`
   (checked: build first, pause every running run at its stage boundary, `BOUNDARY_WAIT=0 loop.sh deploy`, resume,
   churn check; exit 2 = the deploy did not land). `SHIP_NOW=1` stops stages at once; `PAUSE_CEILING` (default 600 s)
   bounds the boundary wait; `SHIP_COMMIT=<sha>` ships an already built commit. App-only change: `loop.sh deploy-app`.
   Container mode: export `COMPOSE_FILE=docker-compose.yml:docker-compose.override.yml:docker-compose.sandbox.yml`
   (the override keeps the owner's Postgres port) before any `docker compose` command, and note `deploy` does not read
   the overlay: after a deploy re-run `docker compose up -d worker docker-proxy` with that variable set.
   Rewind instead of restarting when a fix does not reach intake or the stack choice (section 5).
8. **Next run.** Report to the owner in JST.

**Scoring a finished run:** `scripts/loop/loop.sh score <full run id>` (give the benchmark name as a second argument
when the run did not start from one). Run it in the background and read its log; never wrap it in `timeout` (it
copies the workspace, starts the product, runs the hidden tests and the mutation probe; `MUTATE=0` skips mutation).
Results: `data/bench/<run>.json`, `data/bench/mutation/<run>.json`, the product quality score
`data/quality/<run>.json`, KPIs `data/kpi/<run>.json`, one row in
`data/kpi/ledger.csv` (score runs `kpi`, which also harvests the reader corpus and proposes lessons).
**Product quality score (PQ.10):** `scripts/loop/loop.sh quality [run] [--json]` scores the stored product - interface,
data, service, each 0-100 with the file:line evidence behind every check - in the worker, in seconds, with no model
call (`app.analysis.product_quality`). `score` records it; run it by hand on a live or older run. Locally on a copy:
`PYTHONPATH=src .venv/bin/python -m app.analysis.product_quality <workspace dir>`. Measurement only: it changes no run.
Hidden tests are deleted from the worker right after; never show them to the harness.
After the score, an end-of-run product review goes to `reports/product-reviews/` (section 8).

**Start a run in a call of its own**, never chained after `score` or `kpi`: a chained call that outran the tool
timeout started a second run later. Hold `data/loop/current_run.txt` (the current run id; a UI run is not written
there, put its id in by hand).

**Recording a fix.** The commit that makes a fix also appends one row to `docs/archive/plans/fix-log.md` (what was
measured, what changed, the test proven to fail on the old code; the format is in that file). The plan
(`docs/improvement-plan.md`) holds only open work: when an item is built, delete it from the plan and say so in `STATE.md`.

## 2. Accounts, access and the operator login

The loop uses one account, role `operator`, in the local Postgres only. Load it into the shell with
`eval "$(scripts/loop/operator_login.sh)"` (it reads the marked line below; `ship-live` and the tests read it too).
The line, which must stay on one line ending with the marker:

export LOOP_USER=harness-test LOOP_PASSWORD=loop-test-only-pw-2026   # operator-login

- If a fresh database lacks the account: `docker exec langchain-app-1 python -m app.server.manage create-user <name>
  --password <pw> --role operator` (name and password as on the line above).
- Auth is a form-encoded `POST /api/auth/token`; there is no JSON login. Do not use the admin account. A run started by
  the admin may refuse a cancel from the operator: ask the owner.
- API: `http://localhost:8000` (`LOOP_API` overrides). Containers `langchain-app-1`, `-worker-1`, `-db-1`, `-redis-1`
  (found by compose service; a restart cut off mid-recreate can leave `<id>_langchain-worker-1` behind).
- The owner moves the operator login out of tracked docs and rotates it before any outside user (owner action). The
  marker and `operator_login.sh` stay as they are until then.
- Host needs `.venv` (`uv sync --extra test --inexact`; plain `uv add/remove` drops pytest) and Node (some tests run
  `node --check`). Host Pyright is pinned to the Dockerfile's version (`npm install -g pyright@1.1.414`; change both
  together) so the language-service tests run instead of skipping.
- Machine settings not in git: `data/loop/ops.env` (`BACKUP_DIR`, `RETENTION_DAYS`), read by `loop.sh`.
- Git remote is `main`; branch `harness-hardening-session`.

## 3. Commands

All are `scripts/loop/loop.sh <subcommand>`. Those marked L need `LOOP_USER`/`LOOP_PASSWORD` (section 2).
`[run]` defaults to `data/loop/current_run.txt`. Run with no or an unknown subcommand to print the header.

| Subcommand | What it does |
|---|---|
| `ready [url pin_model=<m>] [deep]` | Disk check, then is the model the settings name served where they name it. Last line `ALL READY` or start nothing. Allow up to 240 s. `deep` sends a ~13k-token request. |
| `status [run]` | State of the run, live runs, prompt-cache share. |
| `start [brief]` L | Create and start a run (default `tests/brief_low.md`). Runs the disk and readiness gates itself. Env: below. |
| `bench <name>` L | `start` from `benchmarks/<name>/brief.md`; a brownfield bench seeds from its `base`. A held-out family needs `MEASURE=1`. |
| `wait [min] [run]` | Block until the run ends or N min (default 18), then status, key log lines, audit. Do not pipe it. |
| `audit [run]` | Failures, duplicate executions, redundant reads, stage order, per-stage failure rate, signatures; disk line first. |
| `deep-audit [run...]` | Every invariant a run must hold, worst first; no ids = last day. |
| `defects [run]` | Each round's defect queue: the check that raised each and what became of it. |
| `effects [run]` / `effects gate [N]` | What each fix and switch did (fired, saved, cost) / per-switch KPI movement against its off arm, candidates to park. Report only. |
| `reads [run]` | Redundant reads by stage and file. |
| `stage <stage> [HH:MM]` | Trace one stage of the current run (time is UTC). |
| `asked [run] <stage> [visit] [--full] [--system]` | What a stage was told, its calls and answer. |
| `failures [run] [--full]` | Each failing acceptance test: criterion, error, page. |
| `timing [run..]` | Wall-clock: model vs tools, phases, reasoning share. |
| `scan [run]` | Where the run spends far more than recent runs. |
| `product [run]` | Audit the generated product: files, claims, its own tests. |
| `documents <run>` | Write the run's unit/acceptance test documents to `data/documents/<run>/`. |
| `score [run] [name]` | Hidden-test score; see section 1. |
| `mutate [run] [n]` | How many small product changes the locked suite catches. |
| `kpi [run]` | KPI JSON plus ledger row; flags a KPI past 1.5x its 5-run mean. |
| `bench-report` | False acceptances across scored runs. |
| `measuring` | One row per switch in `docs/measuring.md` from ledger and scores. |
| `patterns [since]`, `impact [N]`, `lessons [distil <run>\|N]`, `blind-spots`, `gap-precision`, `disputes`, `stack-misses`, `suite-checks`, `checks [labels] [--write]` | Cross-run analyses: recurring failures, did the last N changes worsen their families, lesson candidates, etc. Read-only. |
| `state` | Regenerate STATE.md's generated block (score also does). |
| `cancel [run]` L | Cancel a run. |
| `pin on\|off [run]` L | Keep a run on its model or let it follow settings; `PIN_URL`/`PIN_MODEL_NAME` re-pin to an endpoint. |
| `rewind <stage>\|--pause-only\|--list [run] [at-or-before]` L | Section 5. |
| `resume [run]` L | Resume a failed/paused/cancelled run from its last checkpoint (refused while the model is unreachable). |
| `resumed` | After a deploy: wait up to 10 min for orphan recovery to resume the live run. |
| `resume-when-ready [run]` | Poll `ready`, resume on first `ALL READY`; run it in the background after a model-server outage. |
| `ceiling ...` | Set a run's reply ceiling (`set_ceiling.py`). |
| `build [sha]` | Build app+worker images from a clean checkout; touches no run. `REBUILD=1` forces. Newest `KEEP_IMAGES` (5) kept per tag. |
| `deploy [sha]` | Rebuild/retag, restart app+worker, prove the image matches the commit, list revived runs. One at a time (lock). `BOUNDARY_WAIT=0` when nothing is live or runs are already paused. |
| `rollback <sha>` | `deploy` of an earlier kept build (a retag). |
| `deploy-app` | App container only (API, UI); worker and live runs untouched. |
| `ship-live` | Checked deploy into live runs; section 1. |
| `ship "<msg>"` | Runs `suite`, then commits and pushes only if no test fails; still run `suite-production` too before a deploy. |
| `suite` / `suite-production` | Section 4. |
| `fitness [--edits]`, `diagnose [--again] [--deep]`, `reasoning-probe [run]` | Model checks; use the model, so never beside a live run. |
| `corpus [harvest [run]\|accept]` | Reader corpus; section 6 for `accept`. |
| `freshness`, `nightly` | Pack pins a major version behind; nightly (log clean, disk, backup + restore check, retention report, pack verification, skipped beside 2 live runs). |
| `backup [--check]` / `restore <dir> <new-db>` | Dump the run database to `data/backups/<date>` (3 kept, plus `BACKUP_DIR` copies); `--check` restores into a scratch db; restore never overwrites `langchain`. |

Also: `scripts/loop/verify_packs.py` (every stack pack scaffolds; run after any pack template change, via
`nightly` or in the worker), `scripts/loop/build_sandbox_images.sh`, `scripts/loop/compose_up.sh app worker`
(compose up that unsticks containers left at `Created`), `scripts/loop/restart_watch.sh [report]` (machine
state sampler for host crashes), `python -m app.server.manage` in the worker (`failed-tasks`, `recover-orphans`,
`workspaces`, `checkpoints`, `list-users`, `create-user`, `--help`).

**Gated start.** `start` and `bench` refuse unless disk and model are ready (they run the `ready` gate against the
pinned target). Every Measure run is pinned to its port. Ready check for a port, then the start in a call of its own:

```sh
eval "$(scripts/loop/operator_login.sh)"; export LOOP_USER LOOP_PASSWORD
# one endpoint (owner 2026-11-25): olla on :4001 over two llama.cpp instances, 4 requests at once; at most 2 runs,
# each in parallel execution mode (.env MAX_CONCURRENT_RUNS=2; owner: test parallel mode). :8888 and :1234 are gone.
P=http://host.docker.internal:4001/olla/openai/v1; M=qwen3.6-35b-a3b
scripts/loop/loop.sh ready $P pin_model=$M
FRONTIER=false PIN_MODEL=1 PIN_URL=$P PIN_MODEL_NAME=$M RUN_NAME="<family> <n>" scripts/loop/loop.sh bench <name>
# move a paused run to it: PIN_URL=$P PIN_MODEL_NAME=$M scripts/loop/loop.sh pin on <run>
```

Env on `start`/`bench`: `FRONTIER=false` (all local, no paid model; always for local tests), `PIN_MODEL=1` (pin at
start; implied by `PIN_URL`/`PIN_MODEL_NAME`), `RUN_NAME`, `DELIVERY=fast|...`, `SWITCHES_OFF="A B"` /
`SWITCHES_ON="C"` (this run's own arm on one SHA), `SEED=<dir>` (brownfield), `MEASURE=1` (held-out family).
Benchmarks: `ls benchmarks/` (e.g. web-todo, tasks-api, notes-api-<lang>, fullstack-bookmarks-py, textkit-lib).
The gate can take ~50 s per server; do not use short timeouts. A model server that was just reloaded: `ready deep`.

## 4. Running the tests

- `loop.sh suite` runs `pytest tests/` (`ENV=development`, `--no-cov`, venv on `PATH`, 900 s cap) across
  `SUITE_WORKERS` xdist workers (default 12; about one minute, five on one worker) to `data/loop/suite.log`; then the
  UI type check (`npx tsc -b`, log `data/loop/ui-types.log`); then reruns every failure alone, in order, and labels it
  `FAILED alone too` (real) or `flaky (passed alone)` (parallel-order flake; never mistaken for a regression).
  Its last lines are the verdict; `grep -E "^(FAILED|ERROR)" data/loop/suite.log` lists failures. It must be fully
  green; the old "three S3 failures" were a test bug and are fixed.
- `loop.sh suite-production` runs the same tests with every built-in fix on together
  (`HARNESS_TEST_PRODUCTION_DEFAULTS=1`), which `suite` never does. It fails only on a failure not in
  `tests/production_defaults_expected.txt` (the triage baseline) and prints `NEW with production defaults: ...`.
- Do not edit `src/` while either runs (tests that read source with `inspect` see shifted lines). Tests needing the
  TypeScript compiler skip on the host if absent; verify inside the worker after a deploy.
- **Prove a test fails on the old code:** write the test, `git stash push -- <the fixed src file(s)>`, run only that
  test (`.venv/bin/python -m pytest <test> -q --no-cov -p no:cacheprovider` with `ENV=development`), confirm it fails
  for the right reason, `git stash pop`, confirm it passes. A test must reproduce the state production really produces.
- Run a single file while iterating, never `| tail` on a long run (a hung and a running suite look the same):
  redirect to a file and read it. `TEST_TIMEOUT_SECONDS` drives the per-test hang guard in `tests/conftest.py`.
- If **only the suite script exits 1** (every test line green): it is the `suite-again`/UI-type step or a shell
  pipeline edge, not a test. Read `data/loop/suite.log`, `suite-again.log` and `ui-types.log`; a `FAILED UI types`
  line is a real `tsc` error a fixture left behind (the image build fails on it). Do not edit `src/` while rereading.
- Flaky tests: a failure that passes alone is flaky; note it, rerun the suite once, do not ship over a failure that
  fails alone. A suite that fell without a code change (host load, a stale compile cache, a changed port) is
  investigated at once.
- Tests do not read the developer's model server (`tests/conftest.py` stubs `server_profile.read`).

## 5. Watching and auditing a run

**Stage order** (graph stages, roughly): intake (`product_manager`, `user_review_*`), `stack_selector`,
`principal_architect`, `architecture_review`, scaffold/setup, `acceptance_author` + `acceptance_review`,
`scrum_master` (sprint plan), `technical_lead`, specialists (parallel mode interleaves them, so repeated names are
normal), `test_and_triage`, `defect_remediation`/fix workers, reviews (`code_review`, `security_review`,
`milestone_review`), `sprint_advance`, `release`. A stage restarting, a tool call id run twice, or a stage entered
again without a reason deserves `loop.sh stage <name>`. `loop.sh rewind --list` names the run's real points.

**Cadence:** `loop.sh wait 10` every ~10 minutes for the first 40 minutes, then `wait 18`. The audit cron is the
routine (3,13,23,... minutes). Crons fire only when the session is idle: end turns about every 10 minutes while a
run is live. Session crons expire after 7 days: recreate the audit job when starting a session and when it lapses.

**Reading the output:**
- `audit`: `now in` (stage and tool-failure share); `duplicate executions` must be 0 (one counted apart as
  re-run after a restart is expected; anything else means a resume replayed a call, a harness bug); `redundant
  reads` 8-19% is healthy, above 40% is waste; `per stage` a stage above ~15% failures gets a trace;
  `failure signatures` group failures by tool and message shape.
- `defects`: each round's blocking/non-blocking defects, the check that raised them and what happened. About 63% of
  reported defects have been about tests and their set-up, not the product: read the failing test command's raw
  output (`failures`, `asked`) before believing a defect description.
- `effects`: for each fix and switch, whether it fired and whether it helped; a built-but-silent mechanism is a finding.
  `effects gate` lists switches to park. `measuring` and `docs/measuring.md` say which arm a run is in.
- A run `failed` with a Python exception is a harness bug, not a model fault: read the traceback in
  `docker compose logs worker`, fix, test, `deploy` (nothing live, `BOUNDARY_WAIT=0`), then `loop.sh resume <run>`.
- After a run dies with no useful `error`: `docker compose exec worker python -m app.server.manage failed-tasks`.

**Stuck or wasteful, signs:** the transcript (`/app/data/transcripts/<run>*.jsonl` in the worker) not written for
several minutes while the worker holds a task (compare in UTC: a "15 min stuck" once was 70 s); a process with
little CPU time after long wall clock is blocked (`ps -eo pid,etime,time,pcpu,cmd`); `current_stage` in the `runs`
table is unreliable (use the transcript); the same fix attempted over and over; one failing test chased for an hour;
a suite round that gets worse (1 to 3 problems); a read ratio far above the family's; replies lost to the length cap;
a stage re-prefilling its context (low cache share in `status`); a run `running` with no stage and no transcript, or
`celery inspect active` listing one run twice (two tasks on one run: pause, deploy, rewind to the point before the
second task). Healthy local model calls can take minutes; slow is not stuck.

**Rewind** (after a fix, instead of a new run): `loop.sh rewind --list [run]`, then `loop.sh rewind <stage> [run]
[at-or-before]`. Rewind to the earliest stage the fix affects; a new run only if the fix reaches intake or stack
choice. The optional bound is compared as a string prefix of each point's timestamp (`2026-11-20T09:5` matches
every point from 09:50 to 09:59; the last point of that stage at or before it is used), so give a full enough
timestamp. Rewind to a stage's **original** entry, never to a point an earlier rewind created (a second rewind to
that point resumed past the stage without its model call). A live run is paused first; an unknown stage touches
nothing. To deploy into the rewound stage: `rewind --pause-only`, `BOUNDARY_WAIT=0 loop.sh deploy`, `rewind <stage>`.

**Orphan recovery and resuming:** after a deploy, orphan recovery resumes `running` runs within about two minutes;
`loop.sh resumed` waits for it. Cancel a superseded run or it competes for the two worker slots. Never restart the
worker within two minutes of another restart (a 120 s lock; the second worker skips the sweep and the run sits
`running` with no worker). Recover by hand: `docker compose exec -T worker python -c "from app.server.manage import
recover_orphaned_runs; recover_orphaned_runs()"` (try `dry_run=True`), then `loop.sh resumed`. A partial
`celery inspect` answer judges nothing. After the **model server restarts or stops** (`ready` says NOTREADY,
"Network is unreachable", the run fails with a connection error and keeps its checkpoints): start nothing, do not
load the model; run `loop.sh resume-when-ready <run>` in the background, or `ready` then `resume <run>` yourself.
Pause time is not run time (a database trigger keeps `paused_seconds`).

**Evidence locations (worker):** transcripts `/app/data/transcripts/<run>*.jsonl` (kinds `model_request`,
`model_response`, `tool_call`, `tool_result`, `defect`; requests are windowed, use `carried`); workspace
`/app/data/workspaces/default/workspace-<run>/` with `.harness/` (`stack-pack.json`, `acceptance.json`,
`acceptance-result.json`, `acceptance-locks/vN/`, `ci.json`, `decisions.json`, `sprint-scope.json`); truncated tool
output `/app/data/journal/<ref>`. One-off analysis: pipe a script into the worker
(`docker compose exec -T worker python - <args> < script.py`) and keep reusable ones in `scripts/loop/`, because a
deploy wipes the worker's `/tmp` and `docker logs`.

## 6. Things that bite

- **There is no source mount.** A restart deploys nothing; only `build`/`deploy` do, and `deploy` verifies the image.
  A deploy wipes `docker logs` and the worker `/tmp`. `docker compose restart worker` does not pick up a Dockerfile change.
- **Database lock queue during backup:** `backup`/`nightly` run `pg_dump` beside live runs; a deploy, pause or rewind
  issued while it runs can queue behind the lock. Do not start a deploy or rewind during the nightly backup window.
- **`corpus accept` must go through `loop.sh corpus accept`**, not the host function alone: it also copies the
  accepted results into the worker, and the next `harvest` (after every score) otherwise undoes them and the suite fails
  again; it also fixes ownership (a root-owned copy makes the next harvest fail with Permission denied).
- **Do not edit `src/` while a suite or a `ship-live`/`build` runs.** `build` uses a clean checkout of the commit, never
  the working tree, so uncommitted edits (yours or another session's) are never shipped; commit first.
- **One driver per tree.** Before any commit, deploy, start or cancel, check `git status` for edits that are not yours
  and `pgrep -af loop.sh` for other waits. One agent drives; others audit read-only.
- **Two deploys at once** leave containers at `Created` (name already in use): `deploy` is lock-guarded, `compose_up.sh`
  unsticks one; otherwise `docker rm` the `Created` ones, `docker compose up -d app worker`, `loop.sh resumed`.
- **Docker hangs / 502 on a container create:** pause runs (`rewind --pause-only`) first; `build` refuses if
  `docker info` takes over 20 s. Restarting Docker Desktop is permitted (owner 2026-11-09) after pausing every run:
  `systemctl --user restart docker-desktop`, then check the owner's other containers returned, `deploy`, resume.
  `ship-live` exit 2 (THE DEPLOY DID NOT LAND) means the old containers still run the old code.
- **Never grow the Celery pool** (`pool_grow`): two slots serve one run per port; growing it made workers fork and be
  killed every few seconds.
- **Disk full:** `loop.sh ready`/`audit` print the disk line; `ready` fails under 50 GB / 5% free (`DISK_MIN_FREE_GB`,
  `DISK_MIN_FREE_PERCENT`). A full `/home` crashes Postgres. `nightly` clears LM Studio server logs (older than
  `LMSTUDIO_LOG_DAYS`=2 days, or over 2 GB; logs only, never models or settings); do the same by hand, restart
  app and worker, resume the runs. Reclaim also with `python -m app.server.manage workspaces|checkpoints`
  (report; `--delete` only with the owner's retention say-so; transcripts are the evidence base, keep them).
- **Host GPU fault** (`journalctl -k | grep amdgpu`) kills the model servers and may end the desktop session and Docker;
  nothing returns until the owner logs in. Then `ready` per port, `resume <run>`, re-run `nightly` by hand.
- **No sleep chaining.** Foreground `sleep` is blocked; use `loop.sh wait`, a watcher in the background, or a
  scheduled retry. If Bash stops working, schedule a ~10 min retry yourself and print the next check time in JST.
- **Start a run in a call of its own** and never cap `score` with `timeout` (section 1).
- **A pack template change:** after deploy run `verify_packs` on the changed packs before reporting done; unit tests
  have missed a broken JS config.
- **Model port keys:** :8888 answers 401 to a bare `curl`; ask through the harness's own settings in the worker and
  print names only. `.env`'s `OPENAI_BASE_URL` may name a port that is down while runtime settings name another; the
  settings win for runs: do not "fix" the mismatch without checking which server is up.
- **A run pinned to :1234 or :8888** keeps its pin through resume; a pin to an Anthropic provider is a hosted run.
- `uv add`/`uv remove` drops the test extra: restore with `uv sync --extra test --inexact`.
- Ordinals in guard messages count the whole run, not the stage. Two shell tools: `pgrep -f pytest` matches itself.
- A session's waits, watchers and crons die with the session; start them again after a restart.

### Security notes carried from the old handover
- Credentials in files removed long ago (`scratch/`) are still in git history: never repeat them, and recommend rotation to the owner.
- GitHub tokens are the owner's: never create, store or use one; the owner pushes from their own terminal when asked.
- Never route shell work through another command-running tool to get around an approval check.
- Docker socket access is root-level: the harness services that hold it are trusted code only.

## 7. Where things live

- Repo root `/home/arun/Desktop/langchain`. `src/app/` harness; `src/app/plugins/seed.py` stack-specific guidance;
  `src/app/stacks/` packs; `tests/`; `benchmarks/<name>/{brief.md,bench.json,hidden/}`; `langchain-ui/`.
- `scripts/loop/` operator scripts (this handbook); `scripts/bench/` scoring (`score.py`, `mutate.py`, `brief_match.py`).
- Data (git-ignored): `data/loop/` (`current_run.txt`, `current_brief.txt`, `suite.log`, `suite-production.log`,
  `suite-again.log`, `ui-types.log`, `build.log`, `nightly.log`, `nightly-<date>.log`, `ops.env`, locks);
  `data/bench/` scores (+ `mutation/`); `data/kpi/` KPI json and `ledger.csv`; `data/corpus/` reader corpus;
  `data/documents/<run>/`; `data/backups/<date>/`; `data/postgres/`. Worker volume `appdata`: transcripts,
  workspaces, journal, lessons.
- Docs: `docs/PRODUCT.md` (how the product works), `docs/STATE.md` (live now, last runs, next action; at most 150
  lines), `docs/improvement-plan.md` (the plan), `docs/ARCHIVE.md` (history), `docs/measuring.md` (every change
  under measurement: switch, arm, runs, verdict; the one register), `docs/owner-decisions.md` (decisions in force),
  this file `docs/HANDOVER.md`, `reports/` (all reports).

## 8. Reports

Every report (audits, per-role audits, end-of-run product reviews, research) is a Markdown file in the repo
folder `reports/`, never a cloud document, named `reports/<kind>/<YYYY-MM-DD>-<slug>.md`, and committed with
`git push main harness-hardening-session`. Kinds in use: `audits`, `product-reviews`, `research`, `status-board`.
An end-of-run product review states what to improve, how other harnesses do it, and the value added, one file per
run. Reports contain no secrets.
