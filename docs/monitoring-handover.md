# How this harness is monitored, what that has found, and where to look next

**Written for:** whoever continues the harness-hardening loop from here, on a
different account and with none of this conversation's context.

**As of:** 2026-10-04, branch `harness-hardening-session`, pushed to the git
remote named `main` (`git push main harness-hardening-session`). Section 0 is
kept current by whoever runs the loop - **in the same commit as any change to
how runs are tested** (the gate, the cadence, the scripts, how a product's
tests are set up and run, what the healthy numbers are; owner, 2026-10-04).
Sections 1-10 are the method and history written on 2026-09-24 and still hold
unless section 0 says otherwise.

**What this document is not.** It is not a list of what to change. That lives
in `docs/harness-improvement-plan.md` (the current plan) and in the git
log of this branch, where every fix's commit message says what a run did and
why the change answers it.

---

## 0. Start here: the loop as it runs now

### 0.1 The standing instruction

Run a continuous audit / fix / deploy loop on this harness, and do not stop:

1. start a run of a brief;
2. audit its transcript, logs, database and tool calls closely - especially
   failed and unnecessary calls - every **~10 minutes in a run's first 40
   minutes** (so the early stop below can bite), then every **~18 minutes**
   (not more often; it costs tokens);
3. fix what the harness did wrong, **technology-agnostically**: the harness
   builds full-stack apps in any language or framework, so a fix must not
   assume JavaScript, npm or a browser. Language/framework guidance belongs in
   the `plugin_instructions` table and its seed, `src/app/plugins/seed.py`,
   never hard-coded in prompts. Product-agnostic too: a rule written into an
   agent's instructions must fit an API, a CLI or a service as well as the
   to-do app the test briefs describe - no examples from the brief ("task",
   "the add form"), no UI-only words (button, click, focus, keyboard) in a
   rule meant for every product. Phrase it over capabilities, entry points and
   paths, and give it a test that bans those words (whole-word match; see
   `tests/test_a_criterion_is_checked_per_action.py`);
4. add a test for every fix, **prove it fails on the unfixed code** (stash the
   fix or make it a no-op, run the test, restore), run the full suite;
5. commit, push, deploy, and start the next run.

**Early stop (operator, 2026-09-30).** Any bug found in a run's first 40
minutes: cancel it (`loop.sh cancel`), fix, deploy, start a new run - do not
wait for it to finish. A major harness bug or gap found at any point: cancel
immediately, fix, restart. So during the first 40 minutes check every ~10
minutes (`loop.sh wait 10`), not every 18.

**The gate (since the 2026-10-03 redesign; `benchmarks/README.md`).** A run is
*clean* when its product scores 100% on the benchmark's hidden tests
(`loop.sh score`), the run needed no harness fix, and the product audit (0.4.1)
passes. Stage 1: `web-todo`, 2 consecutive clean runs. Stage 2: `notes-api`,
`wordstats-cli`, `textkit-lib`, 1 clean run each. Stage 3:
`fullstack-bookmarks`, 2 consecutive. Then `tests/brief_medium.md` and
`tests/brief_high.md`, audited by hand. A run in which anything was fixed
resets the count to zero, including a fix deployed while it ran. (Before the
redesign the gate was two clean hand-audited runs each of `tests/brief_low.md`,
`brief_medium.md` and `brief_high.md`.)

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

A new session or account starts at `docs/HANDOVER.md` (written 2026-10-01): the standing instruction, the current run, setting up on another desktop, and the security rules. Runs b69802cd, 391a8b68 and d9642862 (2026-10-01) ran on `qwen3.8-flash-next-coder-iq1_m` on port 9090; the owner switched back to `openai/gpt-oss-20b` on LM Studio at about 17:45 JST.

| | |
|---|---|
| brief | the benchmark in `benchmarks/` the gate is on (`benchmarks/README.md`); `data/loop/current_brief.txt` |
| clean runs toward the gate | **stage 1 (web-todo): 0 of 2.** Gate = benchmark scores since the 2026-10-03 redesign (`benchmarks/README.md`). Runs: fa27ea5b cancelled 22:05 (slow red suite; `40b48f3`); 58190cd3 cancelled 22:23 (code review scope, serving script; `e6eb039`); a4ea15b5 cancelled 00:48 at sprint 3/5, 7 of 9 criteria passing (due-only test rounds, server refusal advice, kept config; `57b1fc8`); run-56e37323 56e37323 cancelled 01:23 (ledger red-suite gate read the acceptance run; `a12fa5f`); run-1264ac2e started 01:29 JST. 1264ac2e cancelled 01:50 (locked tests broken by their own helper; `1aa4eee`); run-84832a29 started 01:55 JST, cancelled 02:52 at sprint 3 (work orders on kept files; loop paused for the plan review, R1-R6 `88356da`..`be0be78`); run-e6294473 started 03:17 JST, cancelled 03:28 (acceptance port picked per Playwright process, so every agent-run suite hit ERR_CONNECTION_REFUSED; `baba502`); run-a8a952c4 started 03:35 JST, cancelled 04:02 (page threw on load and agents saw only 'element not found'; page check `3e4909b`); run-36ad4578 started 04:04 JST, cancelled 05:52 at 7 of 8 tests (agents could not see what the page renders; `4216193`); run-85fcf530 started 05:54 JST, cancelled 06:30 after sprint 1 accepted (the harness's own suite run was withheld as an agent repeat; `27e0714`, with `aa8c02c`); run-d3827f72 started 06:37 JST, completed 07:10, score 7/10 (not clean: placeholder locator in QA's suite, `3c41ab2`; size count, `6534294`); run-34237d1b started 07:24 JST, scored 10/10 at 08:07 but not clean (sprints with nothing left invented work; `7389b23`), cancelled 08:08; run-97036e80 started 08:09 JST, cancelled 08:40 (milestone review blocked on later criteria written AC\u2011n; `e01059a`); run-2466fb53 started 08:47 JST, cancelled 09:22 (sprint 1 stuck; failing tests now carry the page they failed on, `2226632`); run-6f8bed24 started 09:24 JST, cancelled 09:45 (re-planned sprint closed without work; `61bac8a`); run-dded3a26 started 09:50 JST, cancelled 10:11 (locked tests called toBeUnchecked; `eede7fa`); run-e5048126 started 10:17 JST, cancelled 10:52 (CI blind to a re-plan's regressions before any accepted sprint; `1bb78d9`); run-4e3e12c2 started 10:58 JST, cancelled 11:26 to deploy R7 (`467872b`, IDE-grade checks); run-7106082c started 11:28 JST, cancelled 12:33 (9/9 criteria but sprint 1 looped on its own unit tests; `578d74f`); run-9676bcd5 started 12:35 JST, completed 13:09, 10/10 hidden tests, not clean (audit: Sprint Record counts, unrun probes shipped; `f895d4a`); run-b88ce47a started 13:18 JST, cancelled 14:05 in sprint 2 fix round 4 (unit tests of the page churned on hand-built DOMs; kept jsdom setup and agreeing notes, `80e97e7`); run-1cbcdad2 started 14:07 JST, cancelled 14:25 in sprint 1 with 9/9 criteria passing (briefs still asked one command to run both suites; kept-file label untrue; no one-file unit command; `dca01ed`); run-5cfba2c8 started 14:27 JST, cancelled 14:59 in sprint 1 at 2/9 (fix stages did not connect a locator with a label one colon off; refusal advice left a probe named like the product; `f8bc9eb`, `dc91cf5`); run-eb409cbe started 15:00 JST, completed 18:23, scored 2/10 (not clean: list items, fake controls for unpassable locked tests; `2944517`, `1e39bf2`); run-142bada9 started 10:19 JST on 2026-10-05, cancelled 10:42 (a wedged model call held for up to 1800 s; pace bound `1ea4567`); run-2edd7b8f started 10:49 JST, cancelled 11:32 (specification sent back twice for refusing manual checks; `31e5dd7`); run-2922a051 started 11:39 JST, cancelled 12:01 at the owner's request to change the model (no finding); loop paused until the new model is served; run-a5127a41 started 13:27 JST on `qwen3.8-flash-next-q2_0` (:9090). |
| current run | `data/loop/current_run.txt` (git-ignored; `loop.sh status`) |
| database | Postgres data lives in the repo at `./data/postgres` (bind mount, git-ignored), database `langchain`, table `runs` keyed by `run_id` |
| transcripts | `/app/data/transcripts/<run-id>*.jsonl` inside the worker (`appdata` volume) |
| workspaces | `runs.repo_root`, e.g. `/app/data/workspaces/default/workspace-<run-id>` |

Healthy numbers on recent `web-todo` runs (2026-10-04): 11-19% of tool calls
failed - most of them guards working as designed (work-order ownership, parse
refusals, `node -e` refused) - 0 duplicate executions, 0-15% redundant reads,
sprint 1 reaching 9/9 acceptance criteria within ~20 minutes. On brief_low
before the redesign: 1.7-6% failed, 8-19% redundant reads.

### 0.3 The scripts

All in `scripts/loop/`, all documented in their own headers. The Python ones
run **inside the worker** and are piped in on stdin, so nothing is copied into
the container and a redeploy (which wipes the worker's `/tmp`) costs nothing.

| script | what it is for |
|---|---|
| `loop.sh` | the one entry point: `status`, `bench <benchmark>` (a gate run, e.g. `bench web-todo`), `start [brief]` (a brief file; defaults to `tests/brief_low.md`), `wait [minutes]`, `cancel [run-id]`, `score [run] [benchmark]` (also records the harness's own verdict and flags a false acceptance), `mutate [run] [n]` (n small changes to the product; how many the run's locked suite catches), `bench-report` (false acceptances per benchmark across `data/bench/`), `audit`, `stage <name> [HH:MM]`, `reads`, `timing`, `product [run-id]`, `checks`, `deploy`, `suite`. Its header documents each. `bench`, `start` and `cancel` need `LOOP_USER`/`LOOP_PASSWORD` in the environment. |
| `audit_live.py` | the 15-minute check: failure rate, duplicate executions (must be 0), redundant reads, stage order, failures per stage, failure signatures with an example each. Says *where* to look. |
| `stage_trace.py` | every model reply, tool call and result of one stage, in order. Says *why*: the model's words just before a failed call usually name the harness message it misread. `HH:MM` is UTC (JST - 9) and skips earlier sprints of the same stage name. |
| `product_audit.py` | the product half of the audit (`loop.sh product [run-id]`): the product files, code lines per file (counted as the brief's line cap is), the intake's acceptance criteria, what the harness claimed (sprint summary counts, milestone acceptance evidence), and the product's own test command run once. Prints evidence; the reading is the checklist in 0.4.1. |
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
scripts/loop/loop.sh bench web-todo                    # the benchmark the gate is on; prints the run id and JST start
scripts/loop/loop.sh wait 10                           # first 40 minutes; then `wait 18`
scripts/loop/loop.sh score                             # when it ends: the hidden tests
scripts/loop/loop.sh product                           # then the product audit (0.4.1)
scripts/loop/loop.sh mutate                            # a finished run: how strong its locked suite is (~1 min a change)
scripts/loop/loop.sh bench-report                      # false acceptances across every scored run
```

`score` prints `FALSE ACCEPTANCE` when the harness finished a run whose product
fails hidden tests: that is a harness finding even when no transcript shows a
fault. `mutate` says how well the locked tests check what they check; it cannot
see a requirement no test checks (run-eb409cbe's suite caught 5 of 6 changes yet
the product scored 2/10). Do not edit `loop.sh` while a `wait` runs: bash reads
the script as it goes, and the wait dies with a syntax error.

Before `bench`, check the served model matches the settings (`docs/HANDOVER.md`
§5). After `deploy`, the worker's `/tmp` is empty: anything copied there for
auditing has to be copied again.

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
6. When the run ends, `loop.sh score`, then **audit the generated product
   before counting the run** (0.4.1). Then: if it scored 100% and nothing was
   found in the run or the product, count it toward the gate; otherwise the
   count is 0. `loop.sh bench` the next one.
7. Record the run in the gate row of 0.2 and the status table of
   `docs/HANDOVER.md`, and anything that changed how runs are tested in this
   section; commit and push.

### 0.4.1 Audit the generated product - every run, at the end (and mid-run when needed)

A run can look clean in its transcript and still ship a wrong product, or a
harness document that describes it wrongly. Standing instruction from the
owner (2026-09-30): audit the generated files at the end of every run, and
whenever a mid-run finding touches the product. A run is not clean until this
is done.

```sh
scripts/loop/loop.sh product [run-id]    # evidence: files, code lines, claims, real test result
```

Then read the product itself - every source file, not only the tests - against
the brief (`tests/brief_*.md`) and check:

1. **Every brief requirement is really built and reachable by a user.** A pure
   function with no UI wiring is not a feature. Try the obvious edge of each:
   empty input, whitespace, the value another path refuses (an add form that
   rejects an empty title while inline edit saves one was shipped past every
   review on run-fb102e16).
2. **The brief's constraints hold**: line caps (the script counts non-blank,
   non-comment lines as the harness check does), "no external dependencies"
   (a test runner in devDependencies is allowed), the stack it names.
3. **The tests exercise the real code**: they import the product module or load
   the real page; a suite that only asserts the repository's shape is not
   evidence.
4. **Hallucinations - every claim the harness or an agent made is true**:
   sprint summary counts against the real test result (run-fb102e16's
   summaries said 36 test cases for 36 unit + 10 browser tests - a harness
   counting bug), milestone-review acceptance evidence against the code it
   cites, README/docs against what exists, "tests added" against the files.
5. **Classify each finding.** A harness document or check that is wrong is a
   harness bug: fix it in `src/`. A product defect every stage missed is a
   finding about the pipeline: ask what instruction or check would have
   caught it in general (not for this product), and add that. Either way the
   run is not clean.

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
- The full suite (`loop.sh suite`) takes about 3.3 minutes here: roughly
  8,840 pass, 17 skip, and three `tests/test_codebase_seeding_api.py` tests
  fail for want of S3 credentials. Tests that need the TypeScript compiler or
  Pyright skip on the host; run those inside the worker after a deploy. Any other failure is real - unless `src/` was edited while the
  suite ran (tests that read source with `inspect` then see shifted lines).
- A tool call id run twice, or a stage that restarts, is always worth a trace.
- A run that fails on `psycopg.OperationalError: ... server closed the
  connection unexpectedly` while `db` logs nothing is two processes on one
  socket, not a database fault. Check with a socket-to-pid map inside
  `worker` (`/proc/net/tcp` port 5432 against `/proc/<pid>/fd`): a socket held
  by both pid 1 and a pool child is the defect. Every shared pool and the
  worker's runner are per process (`app.server.process_local`); a new one must
  be too.

### 0.5.1 Parked: known, not fixed

- Tools are still offered when command execution is disabled; the duplicate
  `test/` and `tests/` suites seen in run 71d58b84 are not addressed.
- Commands run without a shell, so a wildcard argument reaches the program
  as written: `node --test tests/unit/*.js` fails with "Could not find" on
  Node 20, which does not expand it itself. 4 calls in 25 runs (to
  run-ccc66650), each recovered on the next call by naming the files.
  Expanding wildcards in the harness would also rewrite arguments that are
  patterns on purpose (a `grep` regex), so it is left until it costs more.

### 0.6 Removed on 2026-09-29

`scratch/` (`check_run.py`, `get_run_logs.py`, `get_runs.py`,
`resume_run.py`, `run_monitor.py`, `start_run_api.py`, `run_logs.json`,
`worker.log`) and the root-level `audit_output.txt`. They logged in as
`admin`/`dev`, named fixed run ids and the old `langchain_auth` database, and
carried plain-text credentials; everything they did is covered by
`scripts/loop/`. **Those credentials remain in git history and should be
treated as exposed and rotated.**

### 0.7 How a sprint runs now (work orders, templates, the Sprint Record) - 2026-09-30

Built at the operator's request, modelled on how a software team hands work to a
developer who is new to the codebase. The loop was paused for it; audit the next
runs against this section.

**Every document comes from a template.** `src/app/doc_templates/templates/*.md.j2`
holds one Jinja template per workflow document (the nine in `docs/`, the sprint
summary, the stage summaries). A model supplies the content of each section; the
template fixes the headings, their order, the labels inside a record and what an
empty section says, so a different model produces the same document shape.
`tests/test_document_templates.py` fails if a schema field is not placed in its
template or if the heading skeleton varies with the content. The sprint panel in
the UI parses `sprint_N_summary.md`; its template's header comment says which
lines must not change.

**The technical lead writes work orders.** `SpecialistTask` now carries `title`,
`files`, `interfaces`, `steps`, `edge_cases`, `test_cases`, `verification` and
`out_of_scope`. The lead is given the specification's contract sections to copy
from. Each specialist's brief shows its own work order; the `testing` specialist
also gets every other work order's interfaces and test cases and writes the tests
against them while the code is written (contract first).

**Definition of ready** (`app.analysis.work_orders.readiness_problems`), checked
before dispatch: a code work order with no `files` or no `test_cases`, a file
outside the pinned project directory or in `docs/`, code with no `testing` work
order, a `verification` command the sandbox refuses, or carried-forward items with
no `carried_forward_decisions`. An unready plan goes back to the lead once with the
list and the plan it was (log line: "Milestone plan is not ready to hand out");
after the retry budget it is dispatched with the problems in `integration_notes`.
`WORKFLOW_WORK_ORDER_READINESS=off` disables it - only the test suite does that.
Commands a task names are also checked against the sandbox and a refusal is
written onto the task (`app.analysis.planned_commands`).

**Definition of done** (`app.sprint.record.definition_of_done_gaps`), checked when
the milestone review accepts: every work order returned a result and no tracked
defect is open. A gap sends the sprint back (bounded by `MAX_MILESTONE_REVISIONS`,
then escalates) - the next sprint never starts on an unfinished one.

**The Sprint Record** (`docs/sprint_N_summary.md`) keeps the old header, test
counts, "Planned", "Features Implemented" (task titles now) and "Defect Summary",
and adds: Work Orders (outcome, files planned vs changed, verification, blockers),
Defect Log (reproduction, expected/actual, how it was fixed, what verified it,
regression test), Review Findings (every round of the milestone and security
reviews, with a disposition), Carried Forward, and Lessons for the Next Sprint.
Everything in it comes from state, the execution ledger and the transcript, not
from an agent's account.

**Carry-forward and lessons.** Non-blocking findings from a sprint's last review
round are handed to the next sprint's lead, who must take or decline each in
`carried_forward_decisions`. Tool failures repeated in a sprint (from the
transcript) are handed on as lessons. Both reach the lead's request under
"Carried forward from earlier sprints" and "What went wrong earlier in this run".

**What to audit on the next runs:** does the lead fill the work-order fields (read
`docs/milestone_plan.md` - "not stated" everywhere means it did not); how often
the readiness check bounces a plan and whether the second plan fixes it; whether
specialists follow their work orders (fewer refused commands, fewer files outside
`files`); whether the Sprint Record's dispositions and carried items match what
the reviews said; and whether a carried item is actually taken in the next sprint.

**The intake keeps the brief's acceptance criteria** (19c5033). They join the
success measures verbatim, a comma list without "and" counts as a list, and a
deferred item naming (whole word) a capability the brief's own acceptance
criteria require is marked `(the brief requires X: "..." - only what goes
beyond that is deferred)`; nothing is removed. Audit `docs/product_intake.md`
first on every run: nothing the brief's acceptance criteria require may appear
unmarked under Deferred scope, nor as an exclusion in the specification's
Product Scope (run-557346a2 deferred "Task editing" for "Users can add, edit,
delete tasks"). Also check the marks are right: a mark on an unrelated item
means the matching is too loose again.

---

### 0.8 What the model is given (review of 2026-09-30, commits 6719aec..15a6241)

A review of 23 runs (2,604 tool calls) found most of the struggle was context,
not capability: 26% of calls repeated a read/list/search the stage had already
made, and failed calls were led by missing files, answers written to files and
line-number edits. What changed, and what to audit on the next runs:

- **Locked dependencies.** Both images install `uv.lock` exactly (`uv export
  --frozen`); production had been running 38 packages the suite never saw,
  including deepagents 0.7.20, whose `read_file` has no line numbers. Check
  after any deploy: `docker exec langchain-worker-1 python -c "import
  importlib.metadata as m; print(m.version('deepagents'))"` equals the lock.
- **Reasoning carried across tool calls** (`app.models.with_the_reasoning_carried`):
  the tail of each of the last four tool-calling replies' reasoning is sent back
  in that reply's `content` (LM Studio ignores every reasoning field). Audit:
  the repeated-identical-call share should fall well below 26%.
- **Tools**: `inspect_repository` and `read_repository_file` removed from role
  agents; the answer tool's description now says it is the only way to finish.
  Audit: "answer saved as a file" refusals.
- **Prompts**: writing rules ~9,100 -> ~5,000 chars, testing rules halved, a
  framework block shared by several seeded modules injected once; generated
  framework notes now describe the tool, not the product, and rows generated
  under the old prompt are regenerated. Specialist system prompt ~25,300 ->
  ~12,500 chars before framework notes.
- **Saved models** (settings page): every applied model configuration is kept
  and can be picked again; credentials are never stored with it.
- **Model settings are the operator's.** The review found gpt-oss-20b loaded
  with 10 experts per token (trained with 4). The loaded model and
  `runtime_settings.model_name` must agree before a run starts - check
  `/v1/models` on the model server; do not start a run while they differ, or
  LM Studio either refuses it or unloads the operator's model to serve it.

### 0.9 Why a run takes ~3 hours (review of 2026-10-01, run-482cd03b)

163 minutes for a 347-line app: 1,024 model calls, 950 tool calls. The model
is busy 98% of the wall clock; tools 2%, idle ~0%. Measure a run with
`loop.sh timing [run-id]` (per phase, per stage family, model vs tool time,
reasoning share, how far model calls overlapped) and LM
Studio's `print_timing` lines (`prompt eval time = ... / N tokens` is the
part of the prompt re-read; `f_keep` is the share of the cache kept).

- 91% of output tokens are reasoning (838k of 918k). gpt-oss at its default
  effort reasons ~1,000 tokens before each tool call; "low" measured 6-25x less
  on a probe. Effort is the operator's setting - propose an A/B, do not change it.
- The first reasoning carry-over (last 4 replies) re-wrote the prompt 4 replies
  back every call: median 6,390 prompt tokens re-read per request vs 1,068
  before, 44 min a run vs 6. Now append-only, per OpenAI's gpt-oss guidance
  (keep analysis since the last final message). Check `f_keep` stays ~0.9.
- 82% of tool calls look (read/ls/glob/grep), 8% write. `ui.js` was read 60
  times across 27 stages; every stage starts fresh on a ~10-file product.
- Parallel mode overlaps model calls only 1.0-1.3x (>1 in flight 13-28% of
  specialist time): every gated write/command pauses and pauses drain one per
  superstep. LM Studio's 8 slots go unused.
- The lead spends ~37 min a run: one huge structured plan, 94% reasoning, the
  25k ceiling hit almost every run.
- Verification is the biggest phase (62 min: 7 test rounds, 6 defect fixes).

Implemented after a self-review the owner asked for: the whole small product in
each stage's opening request (`app.agents.project_snapshot`), and, instead of
approving in-line, every queued parallel pause answered in one resume under
auto-approve (`queued_parallel_pauses`, `_GateCount`) - linear and attended runs
never have a queued pause and are unchanged. Not implemented: two-step lead
planning (measure first), per-role reasoning effort (the operator's setting -
an A/B with thinking mode on / effort low needs no code), one sprint for a
small brief (sprints and the Sprint Record are the product's design).

---

### 0.10 How a product is tested now (2026-10-04)

`docs/PRODUCT.md` describes the whole product; this is what a monitor needs to
know about its testing, and what changed most recently.

- **A stack pack scaffolds every project and keeps its test setup**
  (`src/app/stacks/packs/`). For `browser-javascript`: `playwright.config.js`,
  `playwright.setup.mjs` (the page check), `test-setup.mjs` (a jsdom page for
  unit tests), `scripts/serve.mjs`, and the manifest scripts `start`, `test`,
  `test:acceptance`. Agents are refused writes to them and the workspace digest
  labels them "the project's test commands run it". The scaffold proves itself
  with two smoke tests before any agent writes.
- **Acceptance suite.** Written by QA from the criteria, then locked
  (`acceptance/`); the harness runs it every round. A failing test carries what
  the page showed when it failed, and - when nothing on the page matches its
  locator but something differs only in case, punctuation or role - a
  "Nearly there" line naming it (`near_misses` in the JavaScript packs). The
  page check records uncaught errors, console errors, failed requests and HTTP
  errors on load (`test-results/page-load.json`).
- **One-off scripts.** Code on the command line (`node -e`, `python -c`) is
  refused; the refusal says to put it in a file named `tmp-<what it checks>`.
  Files named as throwaways (`file_kinds.is_scratch`) that a stage created and
  nothing references are swept before every test round and at release; any
  other name is taken for the product and ships.
- **Unit tests** use the pack's runner. In `browser-javascript`, `npm test` is
  `node --import ./test-setup.mjs --test ... tests/`, so every test file has
  `document`, `window`, `localStorage` and the page's own `Event`/`FormData`
  classes (jsdom 26.1.0 - the last release for the image's Node 20). One file:
  `node --import ./test-setup.mjs --test tests/<module>.test.js`; a bare
  `node --test` skips the page. A test that builds a page of its own is told to
  use the one it has, and refused on the third time in a stage. `browser-react`
  gets the same from Vitest's jsdom environment.
- **Instructions follow the pack.** Seed rows `<key>:setup` (how to install and
  configure runners) are left out where a pack set the project up, and so are
  the stack block's rules for projects that set themselves up (one command
  running both suites, the module-system choice).
- **IDE-grade checks.** The TypeScript language service (JavaScript/TypeScript)
  and Pyright (Python) report names nothing defines, missing exports and
  imports, and use before declaration: a note on every write, a defect at the
  CI gate once the batch is done.
- **CI gate.** Regressions are measured against both the last accepted state
  and the last measurement; a fix that breaks a passing test is reverted; code
  review runs on each batch.

**Watch on the next runs:** unit-test churn on page code (five web-todo runs in
a row before `80e97e7`; should now be gone); probes named like the product
(`src/import-ui.mjs` in run-5cfba2c8, beside twelve `tmp-*` ones the sweep
handles) - the refusal now names the throwaway form; fix rounds that circle a
locked test whose locator nearly matches the page (six stages in run-5cfba2c8;
the "Nearly there" line should end it); agents adding their own scripts to
the manifest; a fullstack run churning on unit tests of its page
code (`fullstack-node` has no unit DOM yet; see
`docs/harness-improvement-plan.md` §3).

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
