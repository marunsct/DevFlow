# How this harness is monitored, what that has found, and where to look next

**Written for:** whoever continues the harness-hardening loop from here, on a
different account and with none of this conversation's context.

**As of:** 2026-09-29, branch `harness-hardening-session`, pushed to the git
remote named `main` (`git push main harness-hardening-session`). Section 0 is
kept current by whoever runs the loop; sections 1-10 are the method and history
written on 2026-09-24 and still hold unless section 0 says otherwise.

**What this document is not.** It is not a list of what to change. That lives
in `docs/harness-hardening-plan.md` (the running findings log) and in the git
log of this branch, where every fix's commit message says what a run did and
why the change answers it.

---

## 0. Start here: the loop as it runs now

### 0.1 The standing instruction

Run a continuous audit / fix / deploy loop on this harness, and do not stop:

1. start a run of a brief;
2. audit its transcript, logs, database and tool calls closely - especially
   failed and unnecessary calls - every **15-20 minutes** (not more often; it
   costs tokens);
3. fix what the harness did wrong, **technology-agnostically**: the harness
   builds full-stack apps in any language or framework, so a fix must not
   assume JavaScript, npm or a browser. Language/framework guidance belongs in
   the `plugin_instructions` table and its seed, `src/app/plugins/seed.py`,
   never hard-coded in prompts;
4. add a test for every fix, **prove it fails on the unfixed code** (stash the
   fix or make it a no-op, run the test, restore), run the full suite;
5. commit, push, deploy, and start the next run.

**The gate.** A run is *clean* when it completes and the audit finds no bug
and no improvement worth making. Two consecutive clean runs of
`tests/brief_low.md` move the loop to `tests/brief_medium.md`; two clean runs
of that move it to `tests/brief_high.md`; then the same there. A run in which
anything was fixed resets the count to zero, including a fix deployed while it
ran.

**Keep, and fix only where wrong:** dynamic agent instruction injection (the
`plugin_instructions` table, the seed and its middleware), the parallel/linear
execution toggle in settings, and the sprint summary.

**Never:** hard-code run ids (`tests/test_no_run_ids_in_the_source.py`
enforces it), read or reset the `admin` password, use the admin account for
the loop, write the settings table directly (settings need admin; the owner
configured the model endpoint `:8888` and parallel mode), print values from
`.env`, kill the owner's GPU processes (llama-server and friends), or add
knowledge/doc credentials to `sandbox._ENV_PASSTHROUGH`.

### 0.2 Where it stands

| | |
|---|---|
| brief | `tests/brief_low.md` |
| clean runs toward the gate | **0 of 2** on brief_low (run-dc4043b3 was clean; run-21a2bf0c then exposed a spec that never described `edit`, fixed in the architecture review, so the count reset) |
| current run | `data/loop/current_run.txt` (git-ignored; `loop.sh status`) |
| database | Postgres data lives in the repo at `./data/postgres` (bind mount, git-ignored), database `langchain`, table `runs` keyed by `run_id` |
| transcripts | `/app/data/transcripts/<run-id>*.jsonl` inside the worker (`appdata` volume) |
| workspaces | `runs.repo_root`, e.g. `/app/data/workspaces/default/workspace-<run-id>` |

Healthy numbers on recent brief_low runs: 1.7-6% of tool calls failed (most of
those guards working), 0 duplicate executions, 8-19% redundant reads, three or
fewer architecture reviews.

### 0.3 The scripts

All in `scripts/loop/`, all documented in their own headers. The Python ones
run **inside the worker** and are piped in on stdin, so nothing is copied into
the container and a redeploy (which wipes the worker's `/tmp`) costs nothing.

| script | what it is for |
|---|---|
| `loop.sh` | the one entry point: `status`, `start [brief]`, `wait [minutes]`, `audit`, `stage <name> [HH:MM]`, `reads`, `deploy`, `suite`. Run with no argument for help. |
| `audit_live.py` | the 15-minute check: failure rate, duplicate executions (must be 0), redundant reads, stage order, failures per stage, failure signatures with an example each. Says *where* to look. |
| `stage_trace.py` | every model reply, tool call and result of one stage, in order. Says *why*: the model's words just before a failed call usually name the harness message it misread. `HH:MM` is UTC (JST - 9) and skips earlier sprints of the same stage name. |
| `redundant_reads.py` | re-reads by (stage, file) and which notice answered them. One pair with many re-reads has twice been a misleading harness message. |
| `scripts/audit_run.py` | the older whole-run audit (predates this loop): separates *refusals that prevented damage* from *failures that cost the run*, and runs the cross-file checks over the product. Use it on a finished run; see section 5. |

`loop.sh start` logs in with `LOOP_USER` / `LOOP_PASSWORD` from the
environment; no credential is stored in the repository. The loop's operator
account (currently `harness-test`) exists only in the local database and must
be deleted when the loop ends. On a fresh database, create one:

```sh
docker exec langchain-app-1 python -m app.server.manage create-user <name> \
  --password <password> --role operator
```

### 0.4 One iteration, step by step

```sh
export LOOP_USER=harness-test LOOP_PASSWORD=...        # the operator account
scripts/loop/loop.sh start                             # prints the run id and JST start time
scripts/loop/loop.sh wait 18                           # prints "next report by HH:MM JST", then the audit
```

Then, for every failure signature and every stage that looks wrong:

1. `loop.sh stage <stage>` and read the replies around the failure. Decide:
   guard working as designed (a refused repeat, a parse refusal that kept a
   broken file off disk) - or a harness message that is wrong, misleading or
   missing. Only the second is a finding.
2. Also read the product: `docker compose exec -T worker sh -c "cd <repo_root>/<project> && npm test"`
   (or the stack's equivalent) and the review documents in `<repo_root>/docs/`.
   A reviewer or checker that reports working code as broken is a finding
   (several of the fixes on this branch were false positives in
   `src/app/analysis/*`).
3. Fix in `src/`, add a test named for the behaviour, prove it fails on the
   old code, then `loop.sh suite` (do not edit `src/` while it runs).
4. Commit with a message that says what the run did and why the change
   answers it; `git push main harness-hardening-session`.
5. `loop.sh deploy`. A run that already has a finding may be resumed on the
   new code (orphan recovery does it); a run that could still be clean should
   be left to finish first.
6. When the run ends: if nothing was found, count it toward the gate;
   otherwise the count is 0. `loop.sh start` the next one.

Always say when the next check will report (JST). If shell commands stop
working (the tool-approval check can fail transiently), schedule a retry about
10 minutes later rather than waiting for a person.

### 0.5 Things that bite

- Deploy = `docker compose build app worker && docker compose up -d app worker`.
  There is no source mount; a restart deploys nothing. `loop.sh deploy`
  compares the image's files with the working tree.
- Orphan recovery resumes any `running` run after a deploy. A superseded run
  comes back and competes for the two worker slots and the single model
  server: cancel it with `POST /api/runs/{id}/cancel`.
- Auth is a form-encoded `POST /api/auth/token`; there is no JSON login.
- Containers log UTC; the host is JST (+9). Transcript times are UTC.
- The full suite takes about 2.5 minutes here: roughly 7,330 pass, 16 skip,
  and three `tests/test_codebase_seeding_api.py` tests fail for want of S3
  credentials. Any other failure is real - unless `src/` was edited while the
  suite ran (tests that read source with `inspect` then see shifted lines).
- A tool call id run twice, or a stage that restarts, is always worth a trace.

### 0.5.1 Parked: known, not fixed

- Tools are still offered when command execution is disabled; the duplicate
  `test/` and `tests/` suites seen in run 71d58b84 are not addressed.

### 0.6 Removed on 2026-09-29

`scratch/` (`check_run.py`, `get_run_logs.py`, `get_runs.py`,
`resume_run.py`, `run_monitor.py`, `start_run_api.py`, `run_logs.json`,
`worker.log`) and the root-level `audit_output.txt`. They logged in as
`admin`/`dev`, named fixed run ids and the old `langchain_auth` database, and
carried plain-text credentials; everything they did is covered by
`scripts/loop/`. **Those credentials remain in git history and should be
treated as exposed and rotated.**

---

## 1. The loop, in the order it must happen

```
start a run  ->  read its transcript and its product  ->  find what the
harness did wrong  ->  fix it with a test  ->  run the suite  ->  commit and
push  ->  rebuild and deploy  ->  start the next run
```

Four ordering rules, each of which has cost a stage or an hour when broken:

1. **Never rebuild the worker while a run is executing.** Replacing the
   container kills the in-flight Celery task. The run is not lost - the graph
   checkpoints at every node and the startup sweep recovers and resumes it -
   but it costs that stage's work and two minutes of orphan-recovery grace,
   and it muddies whatever the run was being observed for. Check first:

   ```sh
   docker exec langchain-db-1 psql -U postgres -d langchain -tAc \
     "select run_id, status, left(updated_at,16) from runs
      where status in ('running','waiting_for_approval','waiting_for_review');"
   ```

   Ten rows come back and none of them matter: nine attended runs parked at
   approval gates on 18 September and one waiting for review since the 14th.
   They have no live task. Look at `updated_at` - anything older than an hour
   is parked, not running.

2. **Never edit `src/` while the suite is running.** Several tests assert on
   `inspect.getsource(...)`, and a module imported before an edit keeps its
   old line numbers, so the assertion fails on code that is correct. This
   produced three phantom regressions on the other machine before it was
   understood.

3. **Never run two suites at once.** They share one testcontainers Postgres.
   Two concurrent sessions is what turned one stuck suite into two, and the
   instinct to "start another run to compare" is exactly what a silent hang
   produces.

4. **Deploy before starting the run you intend to observe**, or you are
   measuring the previous build. **Check first whether the source is actually
   mounted**, because it decides what "deploy" means:

   ```sh
   docker inspect langchain-worker-1 \
     --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
   ```

   - A `./src -> /app/src` line means the dev overlay is up and the source is
     live. A `docker compose restart worker app` is then enough, because the
     only stale thing is the modules the running process imported at start.
   - **No such line means the stack was started from the base file alone and
     `/app/src` is baked into the image.** A restart then deploys nothing at
     all: `docker compose build app worker` followed by `up -d app worker`.

   On 2026-09-26 the stack was up without the overlay, and only the base file
   had been used. A restart would have looked like a deploy and changed
   nothing - the worker would have kept running the previous commit while
   every later measurement was attributed to the new one.

5. **A setting that saves is not a setting that is read.** Deploying
   `execution_mode` exposed three independent breakages in one toggle: it was
   missing from `runtime_settings.SETTABLE_KEYS` so a write raised
   `ValueError`; the mode it selected crashed and then looped; and the
   dispatcher called bare `load_settings()`, which reads the container's own
   environment, so the stored value was never consulted. The store row said
   `parallel` while the worker said `linear`.

   After changing a setting, check the value where the code reads it, in the
   container that reads it:

   ```sh
   docker exec langchain-worker-1 python3 -c "
   import sys; sys.path.insert(0,'/app/src')
   from app.server.runtime_settings import effective_settings
   print(effective_settings().execution_mode)"
   ```

   `effective_settings()` is the store-aware one. `load_settings()` is
   deliberately a pure function of the environment handed to it, so a bare
   call anywhere in the product is this bug.

6. **A dashboard that is down looks exactly like a harness with nothing to
   report.** `/metrics` returned HTTP 500 for an unknown length of time, and
   every `STAGE_DURATION` recording in the worker failed with it - 17 per run,
   one per stage. The cause was a single file:

   ```
   RuntimeError: Read beyond file size detected, file is corrupted.
   ```

   `prometheus_client` names each process's mmap file after `os.getpid()`,
   `PROMETHEUS_MULTIPROC_DIR` is inside the persistent volume, and a
   container's PIDs start from 1 again on every restart - so a fresh process
   opened `histogram_9.db` written by a different PID 9 days earlier. One of
   49 files, and it took out every metric in both containers.

   The fix names files per process generation, and removes unreadable ones at
   startup. Nothing stops it happening again through some other route, so
   check the endpoint itself rather than trusting that a quiet dashboard is a
   quiet harness:

   ```sh
   curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/metrics
   curl -s http://localhost:8000/metrics | grep -c stage_duration_seconds
   ```

   A 500, or a zero count while a run is executing, means the multiprocess
   directory - not the harness. List it and read each file:

   ```sh
   docker exec langchain-worker-1 python3 -c "
   from pathlib import Path
   from prometheus_client.mmap_dict import MmapedDict
   for f in sorted(Path('/app/data/prometheus').glob('*.db')):
       try: list(MmapedDict.read_all_values_from_file(str(f)))
       except Exception as e: print('unreadable:', f.name, e)"
   ```

   `read_all_values_from_file` returns a generator, so it must be consumed.
   Calling it without `list(...)` reads nothing and every corrupt file looks
   fine - which is a mistake made once already, inside the fix for this.

---

## 2. Running the suite

```sh
cd /home/arun/Desktop/langchain
ENV=development TEST_TIMEOUT_SECONDS=240 timeout 1200 \
  python3 -m pytest -q --no-cov -p no:randomly -p no:cacheprovider \
  > /tmp/suite.txt 2>&1
tail -20 /tmp/suite.txt
```

Every part of that matters:

- **`> /tmp/suite.txt` rather than `| tail`.** Piping `pytest -q` to `tail`
  buffers everything until the end, so a running suite and a hung one look
  identical: no output, one process, no way to tell. Two runs were lost to
  this for 32 and 11 minutes. Redirect, then read the file - the `[ NN%]`
  markers tell you where it is.
- **`ENV=development`** or the suite refuses to start: `JWT_SECRET_KEY is not
  set`.
- **`--no-cov`** because `addopts` in `pyproject.toml` sets
  `--cov-fail-under=80`, and a partial run always fails that.
- **`TEST_TIMEOUT_SECONDS`** drives the hang guard added to
  `tests/conftest.py`: `faulthandler.dump_traceback_later(..., exit=True)`
  around every test. A hang becomes a stack trace naming the test instead of
  an unbounded wait. Set `0` to disable.

**Expected result on this machine: about 4,671 passing, 3 failing, 6 skipped,
in under three minutes.**

The three failures are environmental and must not be chased:
`tests/test_codebase_seeding_api.py` needs S3 credentials this host does not
provide (`botocore.exceptions.NoCredentialsError` against the
`langchain-artifacts` bucket). Verify that claim rather than trusting it -
`git stash`, run that file, `git stash pop`, and confirm the same three fail.
That is how they were cleared here.

**Stale baselines to ignore.** `/tmp/base2.txt` and `/tmp/base_fresh.txt`
were captured on the other machine with a partial mount and carry 78 failures
including 32 `test_graph_routing` errors, which are artefacts of the
invocation. Diffing against them invents regressions.

---

## 3. Starting a run

The cheapest way is to clone a finished run: it carries the same brief,
reviewer, review policy, model choices and unattended mode, so consecutive
runs are comparable.

```sh
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "username=$LOOP_USER" --data-urlencode "password=$LOOP_PASSWORD" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

NEW=$(curl -s -X POST http://localhost:8000/api/runs/<finished-run-id>/clone \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")

curl -s -X POST "http://localhost:8000/api/runs/$NEW/start" \
  -H "Authorization: Bearer $TOKEN"
```

`harness-test` is an operator account created for this loop. It exists only in
the local Postgres volume and is not a production credential. Delete it when
the loop ends.

The brief throughout has been `tests/brief_low.md`: a to-do list with add,
edit, delete, filtering, persistence and responsive design, capped at 500
lines of code. Keep using it. Every number in this document and in the
findings log is against that brief, and changing it invalidates the
comparison.

The model is whatever `runtime_settings` points at:

```sh
docker exec langchain-db-1 psql -U postgres -d langchain -tAc \
  "select key, value from runtime_settings;"
```

Currently `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` at
`http://host.docker.internal:8888/v1`. **Confirm the endpoint answers before
starting a run**, or the run stalls with nothing in the log:

```sh
docker exec langchain-worker-1 bash -lc \
  'curl -s -m 10 -o /dev/null -w "%{http_code}\n" \
   -H "Authorization: Bearer $OPENAI_API_KEY" \
   http://host.docker.internal:8888/v1/models'
```

Note that `.env` points `OPENAI_BASE_URL` at port **1234** (LM Studio), which
is usually not running, while the runtime settings point at **8888**. The
runtime settings win for runs. Do not "fix" the mismatch without checking
which server is actually up.

---

## 4. Watching a run while it runs

### 4.1 The three commands

**State:**

```sh
docker exec langchain-db-1 psql -U postgres -d langchain -tAc \
  "select status, current_stage, left(updated_at,19) from runs
   where run_id='<run-id>';"
```

**Progress, from the transcript, which is the authoritative record:**

```sh
docker exec langchain-worker-1 /opt/venv/bin/python - <<'PY'
import json, collections
p = '/app/data/transcripts/<run-id>.jsonl'
mc = 0; last = None; stages = []; tools = collections.Counter(); errs = collections.Counter()
for line in open(p, encoding='utf-8', errors='replace'):
    try: r = json.loads(line)
    except Exception: continue
    k = r.get('kind')
    if k == 'model_request':
        mc += 1
        if r.get('stage') != last: stages.append([r.get('stage'), 0]); last = r.get('stage')
        stages[-1][1] += 1
    elif k == 'tool_call': tools[r.get('tool')] += 1
    elif k == 'tool_result':
        c = str(r.get('content') or '')
        if c.lstrip().startswith('{"error"') or c.startswith('Error:'): errs[c[:70]] += 1
print('model calls:', mc, '| tool calls:', sum(tools.values()), '| failed:', sum(errs.values()))
print(' -> '.join(f'{s}({n})' for s, n in stages))
print(dict(tools.most_common(6)))
for e, n in errs.most_common(6): print(f'  {n} {e}')
PY
```

**Events worth being interrupted for**, as a filter on the worker log rather
than raw tailing:

```sh
docker compose logs worker --since 1m -f 2>&1 | grep -E --line-buffered \
  "Traceback|ERROR|CRITICAL|Task .* succeeded|Task .* failed|withholding its tools|\
restarted|Resumed run|escalat|MUST FIX|brief requirement|Committed sprint|paused"
```

That filter is deliberate. It covers the *failure* signatures as well as the
happy path, because a filter that greps only for success stays silent through
a crash and silence looks identical to "still running".

### 4.1.1 After a run dies, ask what the worker recorded

A task that fails permanently is written to a Redis dead-letter list, and for
most of this harness's life nothing read it. Nine entries had accumulated over
thirteen days before anything reported them, including two runs killed by a
`SyntaxError` in `sandbox.py` and two by SIGKILL:

```sh
docker exec langchain-worker-1 python3 -m app.server.manage failed-tasks
```

It reports and changes nothing. `--clear` forgets them, and is worth passing
once a batch has been dealt with, so the next report is only new failures.

This is the first place to look when a run's own `error` field says nothing
useful, because a task killed by the pool never got to write one.

### 4.2 Telling slow from stuck

This is the single most useful diagnostic skill here, because on a 35-billion
parameter model a legitimate model call can take three and a half minutes and
a stuck run looks the same.

```sh
docker exec langchain-worker-1 stat -c "%y" /app/data/transcripts/<run-id>.jsonl
docker exec langchain-worker-1 date -u "+%H:%M:%S"
```

If the transcript was written in the last couple of minutes, the run is
working. Note that the containers log UTC and the host is in JST (+0900);
comparing the two directly has caused a false alarm here (a run "stuck for 15
minutes" was 70 seconds old).

For a process rather than a run, **CPU time is the test**:

```sh
ps -eo pid,etime,time,pcpu,cmd | grep pytest
```

A process with 4 seconds of CPU after 32 minutes of wall clock is blocked,
not computing. That one line is what identified the deadlock in §6.1.

---

## 5. Auditing a finished run

```sh
docker cp langchain-worker-1:/app/data/transcripts/<run-id>.jsonl /tmp/run.jsonl
ENV=development python3 scripts/audit_run.py /tmp/run.jsonl \
  /app/data/workspaces/default/workspace-<run-id> tests/brief_low.md
```

**Pass the brief as the third argument.** Two of the cross-file checks compare
the product against the operator's brief rather than the run's restatement of
it, and without it they fall back to the run's own documents - which is
precisely what a run that redefined a requirement out of existence has already
edited. The script says so when the brief is missing, but it is easy to
ignore.

### 5.1 The numbers that matter, and what they have been

| number | meaning | history |
|---|---|---|
| failures that cost the run | the one to drive down | 11.8% corpus average -> 2.6% -> 1.5% -> 0.4% on the other machine -> 2.0% -> **1.0%** on `977eedf8` |
| refusals that prevented damage | the checks working; **not waste** | 8 on `977eedf8` |
| identical repeats in a stage | a stage re-asking an answered question | 5, or 1.6% of model calls |
| read repeat / read withheld notices | the read ladder doing its work | 44 / 18 |

Refusals and failures are counted separately on purpose. A refusal is the
harness stopping something bad; counting it as waste makes a working check
look like a defect, and that mistake has been made in this repo before.

### 5.2 The other half: the product itself

**Every run in this harness's history that shipped something broken shipped it
with a green suite.** A green suite is not evidence. Check the product
directly:

```sh
docker exec langchain-worker-1 /opt/venv/bin/python -c "
import sys; sys.path.insert(0,'/app/src')
from pathlib import Path
from app.analysis.integration_checks import summarise_integration
print(summarise_integration('<workspace>', None, Path('/tmp/brief.md').read_text()))
"
```

And read what the product actually exports, because that is the question the
documents can lie about:

```sh
docker exec langchain-worker-1 bash -lc \
  "grep -oE 'export (async )?function [a-zA-Z]+' <workspace>/<project>/app.js"
```

On `977eedf8` that listed `addTask, deleteTask, toggleTask, editTaskTitle,
filterTasks, loadTasks, saveTasks, init` - and the presence of
`editTaskTitle` is the whole story of that run (see §7.1).

---

## 6. What monitoring has actually found

Ordered by how much each cost to find, because that is the best guide to
where to look next.

### 6.1 A deadlock that only fires on a fresh database

**Found by:** noticing a pytest process with 4 seconds of CPU after 32
minutes, then querying `pg_stat_activity` in the testcontainers Postgres.

```
pid 77 | idle in transaction | SELECT pg_advisory_xact_lock($1)
pid 78 | active | Lock | virtualxid | CREATE INDEX CONCURRENTLY IF NOT EXISTS ...
```

The schema lock added to serialise `CREATE TABLE` is transaction-scoped.
LangGraph's `PostgresSaver.setup()` runs three `CREATE INDEX CONCURRENTLY`
statements, which cannot run inside a transaction block, so they run on
another connection and wait for every overlapping transaction to end -
including the one holding the lock, which is waiting for `setup()` to return.

**Why it hid:** the indexes use `IF NOT EXISTS`, so it fires on a fresh
database and never on an established one. In production that is a cold start,
which reads as "the service took two goes to start". In the suite it is every
session, because testcontainers gives each one a new database. And the test
file it stopped at **passes in six seconds on its own** - it needs an earlier
test to have left a connection holding the lock, so bisecting by file would
never have found it.

**The lesson to carry:** when something hangs, look at CPU time first and the
database's own lock views second. Do not bisect by test file; an interaction
bug is invisible to that.

### 6.2 The harness instructing and then punishing the same thing

This is the most common defect class in this codebase - **five instances
found so far** - and the one to suspect first when a run is blocked by
something that looks correct.

- `TESTABILITY_RULE` tells the model to declare a Playwright `webServer`; two
  checks then reported the resulting `server.mjs` as blocking.
- Four role prompts said "All documentation goes in the `docs/` directory"
  while the tool refused every write there.
- The environment description told the stack selector Playwright is required
  for UI and, separately, to prefer the runtime's built-in runner, without
  saying how they combine: 14 specifications named Playwright and only 2 of
  their stack documents agreed.
- A timed-out Playwright run was answered with "there is no browser to open a
  page with", seven minutes before 34 browser tests ran in the same sandbox.
- `_the_test_command_will_not_run_this` fired 215 times on files that are not
  tests, telling `app.js` 83 times that its assertions never execute.

**How to find them:** when a check blocks something, ask *"which of our own
instructions produces a file that trips this?"* and grep the prompts for the
thing being refused.

### 6.3 Checks that read the run's own account of itself

`56faee7` is the most important change in the branch and the shape is worth
internalising. The brief says "Users can add, edit, delete tasks". A run
recorded in its own specification that "'Edit' refers to toggling completion
status; inline text editing is deferred", and from that point every document
enumerated create, update, complete and delete. Every check read those
documents and agreed. `edit` is absent from four of the eight products stored
on the other machine.

A run may *defer* a requirement and say so - that path exists and reports it.
What it may not do is redefine one out of existence. **Any check that reads
`docs/` is reading something the run can edit.** When adding a check, ask
what it would say about a run that had quietly rewritten the requirement.

### 6.4 State that outlives the call that set it

Three instances, all subtle:

- `_LAST_FAILING_FIELDS` is module-level, so a stage that answered in prose
  was logged with some earlier stage's field names and "(unknown)".
- A test double defined `WorkflowRunner.shared()`, a method that existed
  nowhere else, so every test passed and the deploy raised `AttributeError`.
- The transcript's delta recording trimmed nothing, because the tests grew a
  conversation by appending to its end and the harness injects a message
  before the end.

**The rule:** where a test patches a boundary, one test somewhere must assert
that the boundary is spelled the way the code spells it, with nothing
patched.

### 6.5 Measurements that killed an obvious idea

Keep doing this. Each cost an hour and saved days.

- **Inlining small files into every request.** 46% of reads are redundant,
  five files are 78% of them, so inlining looks obvious. But only 13% of
  reads are whole files under 16 KB, and the one role already handed its
  source inline still made 13 `read_file` calls. Rejected.
- **Playwright correlating with failure.** Two failed runs blocked on a
  Playwright suite nothing ran, so the harness looked like the cause. Of the
  eight stored products, the only earlier one that installed Playwright is
  also the only earlier one that built and tested `edit`. Rejected.
- **The security reviewer rubber-stamping.** Three of 41 reviews returned
  `passed` with no tool call - but that role is handed its source inline, so a
  review with no reads has still read the code. Rejected.

---

## 7. What is working and must not be rebuilt

Each of these was verified against live output, not inferred.

### 7.1 The brief check, end to end on `977eedf8`

At the end of sprint one the product had `addTask, deleteTask, toggleTask,
filterTasks` and no way to edit - the same defect as the other machine's runs
7, 8, 11 and 14. The cross-file check fed the milestone reviewer a finding
quoting both the requirement and the architecture-review line that deferred
it. Two sprints later the product exports `editTaskTitle` and ships
`app.edit.spec.ts`. The last-sprint brief gate never fired, because the
reviewer caught it first, which is the cheaper path. **Both mechanisms are
needed; only one has now been exercised.**

### 7.2 Budget-edge tool withholding

`specialist_backend_1` reached 38 of its 40 model calls with no answer
written. Its tools were withheld, leaving it bound to the structured-output
tool only; it answered; the run continued with no stage restart. Fired 9
times across the other machine's runs 13 and 14, both of which had zero
restarts, against run 12's three restarts and death at 13.5 million tokens.

### 7.3 Orphan recovery, its grace, and auto-resume

A run touched in the last 120 seconds is logged as "too recent to call
abandoned" rather than judged - verified on this run's first seconds. A
genuinely abandoned run is marked failed and put back on the queue
automatically, with three safety properties: nothing resumes unless a worker
answered and did not claim the task, a run resumes at most once per worker
process, and an OOM-killed worker resumes nothing.

### 7.4 The read ladder

Note, then withhold the bytes with an anchor, then refuse the read entirely
past twice the exit threshold. Verified live in the deployed image. The read
refusals fired twice on `977eedf8` and 18 withholdings.

---

## 8. Where to look next, in priority order

1. **`replace_lines` is the least reliable tool** - 27 of 46 calls errored on
   the other machine, 58.7%. Its stale-line-number message has since been
   improved to name where the line moved to, but the rate has not been
   re-measured since. Measure it on the next two runs and decide whether the
   tool earns its place beside `edit_artifact`.
2. **Reads are still 70% of tool calls.** Every mechanism aimed at this has
   helped and none has changed the shape: 55% of all reads across 13 runs
   asked for a file nothing had touched since that stage last read it. The
   project memory (purpose and interface per file, carried between stages)
   deployed too late to be measured. **Measure it**: the §22.1 method in the
   hardening plan, on runs produced by the same brief.
3. **Nothing marks a failed run's workspace as not deliverable.** Run
   `6b511391`'s product fails 5 of its own 45 tests and sits in the
   workspaces directory looking like everything else.
4. **The repeat-timeout refusal never escalates.** It reached "already timed
   out 8 time(s)" on the same argv with identical wording each time.
5. **Test code is 2.4x the product** on `977eedf8`: 965 lines of tests
   against 402 of application code. Counted separately so no budget was
   breached, but worth a measurement of its own.
6. **The task list is built and switched off.** `HARNESS_TASK_LIST=true`
   enables `TodoListMiddleware`. No measurement supports it yet; §25 of the
   hardening plan records the experiment that would decide it.
7. **`mkdir` is the one doubled-path shape the guard cannot catch.**
   `strip_a_doubled_working_directory` rewrites an argument that repeats its
   own `working_directory`, but only when the path as given does not exist
   and the stripped one does - which is what makes it safe rather than
   clever. A command that *creates* a path defeats that test, because
   neither path exists yet. Measured across every stored transcript: 972
   commands ran with a `working_directory`, 60 repeated it, and the guard
   silently corrected 59 of them. The one it could not was
   `mkdir -p todo-app/e2e` with the working directory already `todo-app`, on
   run `07cd52ae`, which left an empty `todo-app/todo-app/e2e` in the
   delivered product. Cost is clutter, not breakage, and at one occurrence
   in 972 it is recorded rather than fixed. If it is fixed, the test to use
   is the *parent* directory's existence, not the target's.
8. **Part I items 3, 4, 5, 6, 10, 11, 13-16** of the hardening plan, and
   Part III item 5 - wiring the `deploy/` generators, whose security defects
   are fixed but which nothing calls.

---

## 9. Things that will waste your time if nobody tells you

- **`current_stage` is empty in the `runs` table** for much of a run's life.
  It is set at approval gates. Use the transcript, not that column.
- **The `runs` table has 150+ rows**, nearly all from before this loop. Sort
  by `updated_at` and ignore anything older than the current session.
- **`docker ps` filtered on names misses the testcontainers** - they get
  random names like `pedantic_perlman`. Filter on the image
  (`redis:7-alpine`, `postgres:15-alpine`) and exclude `langchain-`.
- **`pgrep -f pytest` matches your own shell command**, so it reports
  processes that do not exist. Use `ps -eo pid,cmd | awk '$2=="python3" &&
  /pytest/'`.
- **A `docker compose restart worker` does not pick up a Dockerfile change.**
  Rebuild, then `up -d`.
- **The dev overlay bounds uvicorn's graceful shutdown to 5 seconds.** Without
  that, a source edit triggers a reload that waits for the run event stream to
  close, which never happens, and the API hangs unhealthy while the worker
  carries on - so nothing tells you the API has gone.
- **Chromium is in the worker image now**, at
  `/home/appuser/.cache/ms-playwright`, shared by every run. If a run starts
  downloading its own copy, that cache has gone missing and every run will
  pay 650 MB again.

---

## 10. Disk, and the two commands that reclaim it

```sh
docker run --rm -v langchain_appdata:/v alpine du -sh /v/*
docker compose exec worker python -m app.server.manage workspaces
docker compose exec worker python -m app.server.manage checkpoints
```

`python -m app.server.manage` is the entry point - there is no top-level
`manage.py`. `--help` lists the rest: `recover-orphans`, `reconcile-runs`,
`list-users`, `clear-run-overrides` and the account commands.

The `workspaces` and `checkpoints` subcommands report size, age and run
status, and each takes a flag to delete. Neither has been run in anger.

History here: the volume reached 11.8 GB for about 90 runs, of which 8.5 GB
was per-run Chromium copies and 0.9 GB `node_modules`. Both were cleared and
the image-level browser cache means the Chromium half will not come back.
Transcripts are about 500 MB and are **the evidence base for every
measurement in the findings log** - do not delete those.
