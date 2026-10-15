# Handover - the harness improvement loop

**Written for:** any coding agent (or person) taking over the loop, with none
of the previous sessions' context. Last updated **2026-10-12 13:40 JST**.

Read this file first, then `docs/monitoring-handover.md` §0 (the mechanics and
the full gate history), §0.4.1 (the product audit checklist), §0.7 (how a
sprint runs) and §0.9 (where a run's time goes). `AGENTS.md` at the repo root
points here.

The previous agent's private notes (Claude Code's memory) do not travel.
Everything they held that is not a secret is in this file.

## 0. Your first ten minutes

The owner's direction (2026-10-12): test on **`tests/brief_medium.md`**, in
**parallel** execution mode first and linear mode after; a run taking unusually
long is cancelled, improved, deployed and started again. Check what is live
before anything else:

```sh
cd /home/arun/Desktop/langchain
git status --short                      # only " M docs/logs.md" - the owner's file; never commit or touch it
export LOOP_USER=harness-test LOOP_PASSWORD=loop-test-only-pw-2026
scripts/loop/loop.sh status             # the current run, and whether anything is live
scripts/loop/loop.sh ready              # last line ALL READY, exit 0 - otherwise start nothing (§5)
scripts/loop/loop.sh start tests/brief_medium.md   # only when nothing is live
scripts/loop/loop.sh wait 10            # every ~10 min for 40 min, then `wait 18`
```

Execution mode is a global setting read at every dispatch (`runtime_settings`
`execution_mode`); there is no per-run override. Switching to linear is the
owner's setting change - ask them, never write the settings table.

`loop.sh wait N` blocks for up to N minutes and then prints the status, key
log lines and the audit. Run it so that its output reaches you when it ends:
as a background task your agent is notified about, or in the foreground with
a timeout longer than N minutes. Never detach it with a bare `&` and forget
it. Each time you start a wait, tell the owner the clock time of the next
check **in JST**. Containers and transcripts log UTC; JST = UTC+9.

Then work through §2.2 ("Verify on the next run") as the run goes.

## 1. The standing instruction

The owner wants a loop that **never stops on its own**:

1. Start a run (`loop.sh bench <name>` from `benchmarks/`, or
   `loop.sh start <brief>` for a brief with no hidden tests).
2. Audit it: transcripts, worker logs, the database, tool calls - especially
   failed and unnecessary ones.
3. Fix what you find **technology-agnostically**: the harness must build any
   product in any language or framework. Never fix for one stack, one product
   or one run.
4. Add tests (each proven to fail on the old code) and run the full suite
   (`loop.sh suite`).
5. Commit and push (`git push main harness-hardening-session` - the remote is
   named `main`), deploy (`loop.sh deploy`), and start the next run.

**Gate** (since the 2026-10-03 redesign, `docs/redesign-software-company.md`,
`benchmarks/README.md`). A run is clean when its product scores 100% on its
benchmark's hidden tests (`loop.sh score`), the run needed no harness fix, and
the product audit (monitoring §0.4.1) passes. Any fix resets the current
stage's count. Stages, in order:

1. `web-todo`: two consecutive clean runs.
2. `notes-api`, `wordstats-cli`, `textkit-lib`: one clean run each.
3. `fullstack-bookmarks`: two consecutive clean runs.
4. `tests/brief_medium.md`, then `tests/brief_high.md`, audited by hand.

**Gate:** stage 1 (`web-todo`) passed - run-49dec2db and run-5aadbddd scored
10/10 with no harness fix during them (49dec2db's scaffold was "left to the
agents" over the browser-version mismatch below, and it still scored 10/10).
By the owner's direction the loop now tests `tests/brief_medium.md`, which has no
hidden tests: audit it by hand (§0.4.1 of the monitoring handover).

**Unusually long (owner, 2026-10-12):** a run that stalls - one stage visit over
~30 minutes, a fix loop that keeps reopening the same failure, no sprint
accepted after ~2.5 hours on brief_medium - is cancelled (`loop.sh cancel`),
the cause fixed in general, deployed, and the run started again.

**Early stop.** If you find a bug in a run's first 40 minutes, cancel the run
(`loop.sh cancel`), fix, deploy and start again. If you find a major harness
bug or gap at any time, cancel immediately.

**Mid-run deploys when defect fixed (owner instruction 2026-10-10 18:45 JST):**

- When a harness defect or bottleneck is caught during a run, implement the fix and test immediately.
- Deploy mid-run (`loop.sh deploy`) and wait for orphan recovery to resume it (`loop.sh resumed`) once the fix is verified (not at an exact scheduled time).
- This ensures the run is not held on the same defect and can be observed through its remaining stages for further defects and improvements.

**Design each batch fully before deploying it.** For each fix:

- trace every other path it touches;
- replay it on the real evidence (the transcript, the workspace's `.harness/`
  files) rather than a made-up fixture;
- fix the cause once, not one symptom per run.

Two lessons behind this rule:

- `38ef971` introduced a regression.
- The sprint-scope fixes (`3b01d8a` → `6ff499e` → `c3a5fca` → `d833edb` →
  `351d1ec`) arrived one run at a time when one design would have done.

**Product audit, every run, at the end.** Run `loop.sh product <run-id>`, then
read every product source file against the brief (monitoring §0.4.1). Check:

- every brief feature is built *and reachable by a user*;
- edge inputs and the brief's constraints;
- that the tests exercise the real code;
- that every claim in the sprint summaries and the milestone review is true.

**After each run:**

1. `loop.sh score <run> web-todo` and `loop.sh product <run>`.
2. Record the run in §2 of this file and in the gate row of monitoring §0.2.
3. Commit and push.
4. Deploy the batch, if there is one.
5. Start the next run.

**Code rules:**

- **No run ids** in code, comments, prompts or tests
  (`tests/test_no_run_ids_in_the_source.py`). The placeholders `deadbeef` and
  `abc12345` are fine. Evidence goes in commit messages, and in docstrings as
  "one run".
- **No language- or framework-specific instructions in code.** They belong in
  `src/app/plugins/seed.py` (the `plugin_instructions` table, injected
  dynamically) or in a stack pack (`src/app/stacks/packs/`).
- **Rules for agents are product-agnostic.** No examples from the test brief,
  and no UI-only words in rules meant for every product. Every new prompt rule
  gets a test that bans the whole words task, tasks, to-do, todo, button,
  click and checkbox (e.g. `tests/test_a_suite_that_asserts_an_unstated_order.py`).
- **Preserve the owner's features:**
  - dynamic agent-instruction injection;
  - the parallel/linear execution toggle;
  - the sprint summary;
  - work orders, document templates and the Sprint Record (monitoring §0.7).

  Fix them where wrong; never remove them.
- **Do not force the model to pick only from pre-existing scaffolds:**
  If the best open-source option for a product's requirements is not in the
  existing scaffolding (`app.stacks.packs`), do not force the model to select a
  non-ideal technological stack. The stack selector chooses the optimal stack
  for the product, and the harness supports and scaffolds open-source stacks
  cleanly. Extend scaffolding to cover known open-source frameworks.
- **Implement only what adds value** (owner, 2026-10-04). That holds for the
  owner's own plans too. Where an existing implementation does not fit the
  product vision (a software-company harness: auto mode decides, approval mode
  asks), replace it rather than patch it. Say which items you drop and why.
- **Use the LangChain docs MCP server** (or the docs site) when changing
  LangChain/LangGraph behaviour.

**Standing permissions and habits:**

- **You may edit any file in the repo, `.env` and `docker-compose.yml`
  included** (owner, 2026-09-28). Back `.env` up first and never print its
  values. Don't wait for the owner's input: make the best decision and keep
  the loop going. The exceptions are the owner's decisions in §7 and the
  model (§5).
- **Commit and push after every change**, handover updates included. Never
  leave the tree dirty between steps, apart from `docs/logs.md`.
- **Keep monitoring §0 current in the same commit** as any change to how runs
  are tested: the gate, the cadence, the scripts, the healthy numbers or the
  suite size.
- **When idle and waiting on the owner** (for example a model mismatch), use
  one long passive watcher, not periodic wake-ups. Credits are limited.
- **When the shell fails** for an infrastructure reason (a tool-approval check
  that gives no verdict), stop retrying. Schedule a check about 10 minutes
  later, or tell the owner when you will retry, and resume. Testing comes
  first when it returns: deploy the pending fix and start the next run, then
  commit and push. A failing git step must never stop the testing.

## 2. Where it stands (2026-10-12 13:40 JST)

| | |
|---|---|
| branch | `harness-hardening-session`, pushed to `https://github.com/marunsct/DevFlow.git` (remote named `main`). `docs/PRODUCT.md` describes the whole product. |
| deployed | `d5e6465` deployed 23:24 JST 2026-10-13 into run-c2e62179 (resumed); the rewind-points grouping fix after it is pushed, deploy with the next fix. `verify_packs.py` for the 35 packs has NOT been run in the worker yet - run it when no run is live (`loop.sh nightly` does). |
| current run | `run-c2e62179` (`notes-api-hono`, parallel), started 21:21 JST 2026-10-13: no pack fits (TypeScript/Hono), so the setup stage path is live. `run-23896345` (brief_medium) is PAUSED since 21:07 JST at the owner's request (one run at a time; resumable). `loop.sh status|wait` take a run id. |
| model | Two tiers set by the owner: build model `qwen3.8-flash-next-coder-iq1_m` (Strata on the owner's `localhost:9090`; reached as `host.docker.internal` with `Host: localhost:9090` - every client must go through `app.models.endpoints.reached_from_here`), frontier (judgement) `qwen3.8-flash` on `https://token-plan.maas.qwencloudapi.com/compatible-mode/v1` (it refuses a forced tool call while thinking - handled). Qwen cloud's free quota ran out on qwen3.8-max(-0902) on 2026-10-13; a quota refusal now parks a run as `waiting_for_budget`. Execution mode **parallel**, `HARNESS_MAX_PARALLEL=6`. |
| Celery limits | soft 43,200 s (12 h), hard 43,500 s - in `tasks.py`, `docker-compose.yml` and `.env.example` (the handover had claimed this before it was done). |
| suite | 9,840+ pass, 29 skip, 3 expected S3 fails (`tests/test_codebase_seeding_api.py`). |

### 2.000 Fast delivery (2026-10-14, `e55dd6f`)

The owner judged the harness too slow to be worth using: run-c2e62179
(notes-api-hono, thorough) took 13.3 h for 1.5 of 4 sprints - 1,081 model
calls one after another (only one in flight 91% of the time even in
parallel mode, the local server serves one at a time), 2.84 M output tokens
of which 48% reasoning, 54 M input tokens, 549 lines of product and 5,058
lines of tests. `DELIVERY_MODE` (`app.delivery`; settings page "Delivery
Mode"; compose default `fast`, code default `thorough`) adds a fast path:
one sprint for <=20 criteria; work-order files drafted from the
specification one call per file (`app.graph.drafting`, unattended runs
only, agent loop as fallback); harness-run test rounds once the locked suite
has run (unit failures -> a product-owner defect); tests limited to the
specification's file plan; building/fixing with reasoning off
(`thinking.without_reasoning`). Benchmark: notes-api-hono on fast vs the
13.3 h thorough baseline. Owner 2026-10-14 (frontier only where its reasoning is
needed): in fast delivery the intake, comparison, stack choice,
consultations, sprint plan, work orders and acceptance-test authoring run
on the build model; the specification and every review stay on the
judgement model, and a judgement stage gathers (reads, docs, lookups) on
the build model with reasoning off and writes on the judgement model
(`app.agents.gathering`, registered by `gather_with`). Owner 2026-10-15: the
architect's reading is done before it starts - the harness looks up every
library of the stack in its registry, the build model names the documentation
topics once, the harness reads them, and the notes go into the architect's
request (`app.agents.research_brief`, kept in `architect_research`); the
architect is then offered no documentation or registry lookups
(`research.researched`). Only read-only calls
(`GATHERING_TOOLS`) are gathering - a write or a command, as in a building
stage escalated to the judgement model, is the judgement model's. One architecture
revision and one acceptance send-back, then open findings are decided
risks. Owner 2026-10-15: each run chooses whether to use the frontier model ('Use the
frontier model' on the start form; `use_frontier_model` in the start request,
`runs.local_only`, `app.models.roles.on_the_build_model_only`); unchecked, every
stage runs on the build model. `loop.sh start` takes `FRONTIER=false`. Owner
2026-10-15: a milestone review still asking for changes after
`MAX_MILESTONE_REVISIONS` records its findings as risks (a decision, carried to
the next sprint) and goes on to the checks - a red suite, a criterion due that
fails or a sprint not done still stop it; thorough still escalates. Research has a share per stage visit (8 docs, 12 packages;
`app.tools.research`), carries to a fresh attempt, and package lookups
batch. A cut-off answer keeps its whole fields and asks for the rest
(`app.models.tool_arguments`); a specification revision sends only what
it changes. 2026-10-15: the harness does what needs no model in fast delivery -
fixes by rewriting (`app.graph.rewritten_fixes`), compile-and-repair after
drafting, a silent suite run file by file (`app.acceptance.per_file`), work
orders from the specification (`app.graph.planned_work`; only to build the
product - once half its planned files exist the lead plans the change, and
files the harness keeps are never listed), no model code
review. Analysis and next steps (project source in memory, parallel
candidate fixes, type errors refused at the write, specification in parallel
parts): https://claude.ai/artifact/SBZagb9VAP9P5Q4bHMsVgJ. Built the same night: the project memory
(`app.agents.project_memory`, `PROJECT_MEMORY` on/off, default on in fast),
candidate fixes, errors refused at the write, the specification in parts.
Owner 2026-10-15: the delivery mode is each run's own - chosen on the start
form (`StartRunRequest.delivery_mode`), kept in `runs.delivery_mode`, applied by
the worker with `delivery.for_the_run`; a run started without one takes
`DELIVERY_MODE` (`loop.sh start` passes `DELIVERY=fast|thorough` if set). The
settings page no longer has it. On in BOTH modes: project memory, errors
refused at the write, a silent suite run file by file, gathering on the build
model, candidate fixes. Fast only: one sprint, drafting, harness work orders
and test rounds, rewrite fixes, no code review, one revision/send-back,
planning on the build model, the specification in parts. The harness-run test
round stays fast-only: it measures existing tests, while the model round also
writes tests for what the sprint built.
A read of a file the project memory holds, unchanged, is answered with a
pointer to it - a window (`offset`/`limit`) too: a third of all reads were
windows. Files over `LARGEST_FILE_CHARACTERS` (60k; the specification is often
~200k) are not held and are still read from disk.
A withheld tool that a model keeps calling (a 1-bit model did, 23 times)
takes every looking tool away (`settled_answer._a_withheld_tool_still_called`);
the stall rule counts distinct calls, so one tool asked about one thing after
another with nothing new is a stall too.
A call to a tool name not offered that plainly means one offered tool
(`Read` for `read_file`) is taken as that tool (`tool_arguments`).
Fast delivery's milestone review sends a sprint back once
(`FAST_MILESTONE_REVISIONS`), then records the findings as risks.

### 2.00 Rewind, a specification a local model builds from, two tiers that hold (2026-10-13 night)

- **Rewind** (`d5e6465`): every stage snapshots the workspace as it starts
  (`version_control.snapshot_workspace`, refs `refs/harness/stages/<ms>-<node>`,
  about 10 ms; `node_modules`/caches/test output left out, `.harness/` and
  `.project-*` kept). `GET /api/runs/{id}/rewind-points` lists each stage
  entered (approval round-trips are one entry); `POST /api/runs/{id}/rewind
  {"checkpoint_id"}` branches the run from the checkpoint before that stage
  (`workflow.rewind_to`: `update_state` on the old checkpoint), restores the
  files (a `before-rewind` snapshot first; branch and `sprint-N` tags moved
  back) and resumes. Only a stopped run (pause first). UI: **Rewind** beside
  Resume on the run page. Runs from before `d5e6465` have no snapshots: their
  state rewinds, their files stay.
- **Specification for the build model** (`f008ec4`): new `library_usage`
  section (exact import + call per library, from `read_docs`), handed to every
  work order; the architect must make the configuration allow what the files
  do (import extensions, module system, runner config names); the custom-stack
  setup stage is shown the specification's files/testing/configuration and
  uses its names.
- **Fixes the same night**: quota refusal parks the run (`526b5b4`); Express
  pack no longer fits a Hono stack (`12fef11`); npm READMEs via jsDelivr
  (`1e0bf09`); the judgement model's reply ceiling is its own
  (`JUDGEMENT_MAX_OUTPUT_TOKENS`, "Longest reply" in settings, `357131c`);
  forced tool refused in thinking mode -> offered instead (commit after
  `b1ed794`); a setup stage resumed after its own approval pause is finished
  and proven, not skipped (`2915a36`).
- **Context budgets** follow the settings page (not the process environment,
  which said 100k while settings said 130k), and a judgement stage compacts at
  its own model's window (`models.environment_of`). Note: a 1M-token frontier
  window means long conversations are resent whole on each call - more quota
  per call on a metered provider.
- **Gate**: `loop.sh suite` now puts the venv on PATH; ten sandbox tests marked
  for a bare `python` had been skipped (one had gone stale).
- **Temporary directory**: each workspace's commands get a short `/tmp/run-<hash>`
  TMPDIR (a socket under the workspace path exceeded the 107-char limit).

### 2.0 Reach beyond the packs (2026-10-13, `58600ee` and `d9fd387`, pushed; deploy after run-23896345 ends)

Three features (on the owner's request, after comparing how cloud coding
agents handle any language): they change what stages are given, so they go
live between runs, not into one.

- **`look_up_package`** (`app/tools/package_registry.py`): a stage asks the
  registry an ecosystem installs from (npm, PyPI, crates.io, Go proxy, Maven
  Central, RubyGems, Packagist, NuGet) for the latest stable version, the
  runtime it needs, peer dependencies, and the runtime this environment has.
  Fixed hosts, checked names. Given to the stack selector, the architect and
  specialists. Off with `PACKAGE_LOOKUP_ENABLED=false`.
- **A proven setup for a stack no pack covers** (`app/stacks/custom_setup.py`):
  the scaffold node runs `stack_setup_<n>` (the testing specialist), which
  creates the project with the framework's own generator and declares its
  runners in `<project>/stack-setup.json`. The harness runs the install and
  both smoke tests through those commands; only a passing setup is recorded,
  as a contract with `"pack": "proven-setup"` whose runner files and manifest
  scripts are kept as proven. Unproven: sent back once with what failed, then
  left to the agents as before. Seeded codebases are skipped. Off with
  `CUSTOM_STACK_SETUP=false`.
- **`use_runtime`** (`app/tools/runtimes.py`): Node, Go, Java (Temurin) or
  Python (through `uv`) at the version a project needs, downloaded from the
  official distribution, checksum-verified, cached in `/app/data/toolchains`
  (beside the workspaces, so it survives deploys) and first on that project's
  PATH only; container mode picks the image of that version. Verified for
  real on the host: Node 22.23.3, Go 1.26.9, JDK 25, Python 3.13 in 1-5 s each.
  Off with `SANDBOX_RUNTIMES_ENABLED=false`.

Then (`d9fd387`, same branch, also to deploy between runs):

- **Compiler checks for compiled languages** (`app/analysis/compiler_check.py`).
  JS/TS (TypeScript language service) and Python (Pyright) already had an IDE's
  view on every write; Go, Rust, Java/Kotlin, C#, Swift and PHP had only a parse.
  Now the project's own build is asked for errors only - `go test -run '^$'`,
  `cargo check --all-targets`, `mvn test-compile` / `gradle testClasses`,
  `dotnet build`, `swift build`, PHPStan level 0 when installed - at a stage's
  exit (not while another work order's files are unwritten) and as defects at
  the sprint gate. Ruby has no checker that finds an undefined name; its tests
  are the check. The image has no Gradle, so Kotlin/Gradle projects get none.
- **`look_at_page`** (`app/tools/page_view.py`): specialists on a product with a
  page start it through the project's own Playwright configuration and get its
  accessibility tree, page errors and failed requests (desktop or phone). Fix
  stages are told to look before changing the page. Verified in the worker
  image on a scaffolded React page.
- **`read_docs`** (`app/tools/docs.py`): a framework's own `llms.txt` docs
  (Svelte, Angular, Vue, Nuxt, React, Next, Vite, Vitest, Solid, Nest, Express,
  Hono, Prisma, Drizzle, Bun, Deno, Pydantic, Quarkus) or a package's README
  from npm/PyPI/crates.io/GitHub, cut to the topic.
- **MCP servers** (`app/tools/mcp_tools.py`, adds `langchain-mcp-adapters`):
  off until the owner sets `HARNESS_MCP_SERVERS` (example in `.env.example`:
  Context7). Only listed tools, only the listed roles, answers capped and
  labelled as data. Verified with Context7 (no key) and a local stdio server.
- **Eight packs** (35 in all): `node-cli`, `node-library`, `typescript-cli`,
  `typescript-library`, `go-cli`, `go-library`, `rust-cli`, `rust-library`,
  each scaffolded and smoke-tested through the sandbox in the worker image.
- **A framework no pack knows gets no pack** (`e92c5b5`): Hono had been read as
  "no framework" and given the Nest pack.
- **`loop.sh freshness`** (pins a major behind: 78 of 194 on first run - e.g.
  Vitest 3 vs 5, Vite 7 vs 8, TypeScript 5 vs 7, Next 15 vs 16, Spring Boot 3
  vs 4; update a pack only with `verify_packs.py`), **`loop.sh lessons`**
  (failure shapes recurring across runs, per language: candidates for
  `seed.py`), **`loop.sh nightly`** (all packs + freshness, skipped while a run
  is live; not scheduled - the owner decides whether to add it to cron).
- **`benchmarks/notes-api-hono`**: notes-api's hidden tests on TypeScript/Hono,
  which no pack covers; reference 9/9. The first run of the proven setup stage.

Not yet seen on a real run: a custom stack under the served model. Run
`loop.sh bench notes-api-hono` after the parallel/linear medium runs, and check
§2.2 item 5.

**Suite repairs budgeted by test (`e985111`, deployed mid-run 13:57 JST).** run-23896345 spent
both of its suite repairs on tests the old "acts on the page" check wrongly named; then two
login tests called `.json()` on the plain object their helper returned (`TypeError: res.json
is not a function`), and with the budget spent two fix stages could only answer "a bug in the
locked test". `acceptance_nodes.may_repair` now lets a test never sent for repair earn one past
`MAX_SUITE_REPAIRS` (2), up to `MAX_SUITE_REPAIRS_IN_ALL` (4); the state records the tests each
repair was for (`suite_repaired_tests`). Verify: the run's next test round reopens the suite for
the two auth tests (decision "QA repairs those tests ...").

**Undefined names in tests (`4774f20`, deployed mid-run 16:16 JST).** QA's repair of the suite
called `getTask`, which nothing defined, and the suite was locked with it (DR-11) and reopened
at once (DR-12, the fourth and last repair). Names were checked only in product code. A test
importing `@playwright/test` or `node:test` now has its names checked too (browser and Node
globals; functions handed to the page left to the page). Swept over 1,038 stored test files:
5 flagged, all real faults, no false alarm.

**Pause and resume from the screen (`2ea697d`, deployed 16:41 JST, on the owner's request).**
`POST /api/runs/{id}/pause` (operator; a Pause button on the run page and in the run list)
raises the cancel flag with `stop_reason='pause'` and revokes the task; the worker records
`paused` and keeps everything. Resume takes `failed`, `waiting_for_budget`, `paused` and
`cancelled` (`RESUMABLE_STATUSES`) and lowers the flag. **Use Pause, not `docker compose stop
worker`, to stop a run for a model change** - and a cancelled run can now be resumed too.

**A save never writes back a stale task id (`ff9faab`).** The first Pause revoked a task that no
longer existed: the worker's record, loaded before the API recorded the new task, wrote the old
task id back on every persist (`COALESCE(EXCLUDED.task_id, runs.task_id)`). `set_task_id` now
owns the column. The run was stopped by revoking its real task by hand.

**Parallel fixes and reviews, two model tiers, a detailed specification, per-endpoint keys
(`cdb57b3`..`c7dada5`, deployed 19:27 JST).**
- Parallel mode fixes file-disjoint defects side by side (`_the_next_fix_batch`,
  `defect_fix_worker`/`defect_fix_gather`; a batch that broke what passed is reverted whole
  and its defects fixed alone) and runs the security and advice reviews side by side
  (`review_worker`/`review_gather`). Every fan-out is capped at `HARNESS_MAX_PARALLEL` (6).
- Two tiers (`app/models/roles.py`): the judgement model ("Planning & judgement model
  (frontier)" on the settings page) plans - intake, tools, stack, sprint plan, work orders
  (`PLAN_ON_JUDGEMENT_MODEL`, on) - and judges; the default ("build") model builds work
  orders and fixes, and a stage that restarted, or a defect whose fixes failed
  (`Defect.fix_attempts`), `ESCALATE_AFTER_ATTEMPTS` (2) times goes to the judgement model.
  With one model configured nothing changes. The owner's plan: build = gpt-oss-20b
  (local), frontier = qwen3.8-max (Qwen cloud).
- The specification gains `file_plan`, `function_contracts`, `data_contracts`,
  `error_catalogue`, `implementation_order`, `test_cases`, `configuration`; each work order
  is handed the entries for its files (`specification_for_the_work_order`).
- Each endpoint (provider + address) keeps its own encrypted API key
  (`runtime_settings.save_endpoint_key`); one provider serving both models shares one.

### 2.1 What changed on 2026-10-12

A review of the 35 commits since `9c41cba` (`6314d91`, each fix with a test
proven to fail on the code before it):

- **No contract is guessed.** `contract.the_pack()` used to read pack names out
  of the stack decision and the stack document, write its guess to
  `.harness/stack-pack.json`, and `enforce()` then wrote that pack's runner
  configuration into the project. Two of three brief_medium runs got a wrong
  pack that way. The lookup only reads now. A scaffold that cannot be proven
  records its pack with `scaffolded: false`: its test checks and commands
  apply, nothing of it is kept or put back (`contract.scaffolded`).
- **Batched defects stay open.** A fixer is shown every open defect of its role
  that a measurement can close. Only the measurement taken after the fix closes
  them; one still failing goes to its own fixer. The batch no longer marks them
  fixed on the first defect's answer, and no longer writes "verified by
  <command>" in place of a regression test.
- **Unknown is not passed.** The procedural test round skips the testing
  specialist only when the locked suite ran and passes everything due, and the
  unit tests ran and passed.
- **The "missing from locked suite" dispute needs a suite that ran.** A test
  carrying two criteria is now one failure naming both.
- **Suite checks are the pack's and refuse no correct test.** They accept
  `addInitScript` seeding storage, comments, `await Promise.all([helper()])` and
  `createRequire`. The generic QA prompt carries no Playwright rule.
- **Reviews run on code in any language.** They skip only a sprint that changed
  nothing but prose, styles and images.
- **Builders are not told to fix another work order's file.** This holds in
  both execution modes: the in-write note and the exit gate both treat an
  import of a file another work order is writing as expected.
- **One sprint-sizing rule.** It is computed from
  `max_sprints_for_criteria_count`.

Stack packs and the image:

- **Five new packs**, each scaffolded for real in the worker with its smoke
  tests passing:
  - `browser-vue`;
  - `fullstack-react-express` and `fullstack-vue-express`;
  - `fullstack-react-fastapi` and `fullstack-vue-fastapi`.

  The page is built with Vite and served by the service beside `/api/`, so the
  product is one process on one port. Unit tests are Vitest for the page, and
  Vitest or pytest for the service, merged into one report.
- **Matching reads both languages of a full-stack stack.** It also requires
  the component framework a stack names: "Vue on Vite" had matched the React
  pack. The medium brief's stack (Python/FastAPI + React on Vite) now gets
  `fullstack-react-fastapi`; before, no pack fit it.
- **One Playwright release everywhere: 1.64.0.** This covers the packs
  (`_javascript.PLAYWRIGHT`), the image (`ARG PLAYWRIGHT_VERSION`) and the
  scorer, and `tests/test_one_playwright_everywhere.py` keeps them equal.
  - The image used to install the newest release on every deploy, after
    `COPY src/`.
  - From one deploy on, it held Chromium 1248 while the packs looked for 1243.
  - Three of four web-todo runs had their scaffold "left to the agents" over a
    browser that could not start.
  - The browser is now installed in a layer before anything a deploy changes.

**Waves 2 and 3 (`d1b664b`, `79089ea`, deployed).** Packs now cover every major language:

| kind | packs |
|---|---|
| browser app | `browser-javascript`, `browser-react`, `browser-vue`, `browser-svelte`, `browser-angular` |
| full-stack | `fullstack-node`, `fullstack-{react,vue}-{express,fastapi}`, `fullstack-next`, `fullstack-django` |
| HTTP service | `node-http-api`, `python-http-api` (FastAPI), `python-flask-api`, `node-nest-api`, `go-http-api`, `go-gin-api`, `java-spring-api`, `csharp-aspnet-api`, `rust-axum-api`, `ruby-sinatra-api`, `ruby-rails-api`, `php-slim-api`, `php-laravel-api` |
| CLI / library | `python-cli`, `python-library` |

- **Services in any language** are accepted through Playwright's `request`
  fixture against the running service (`packs/_service.py`).
- **`scripts/loop/verify_packs.py`** scaffolds packs for real. All 27 passed in
  the live worker on `79089ea`.
- **Node 24** (Node 20 is end-of-life; Angular 22 refuses it). Node 24 loads a
  directory given to `node --test` as a module and runs nothing, so pack unit
  scripts name a quoted pattern, the sandbox refuses `node --test <dir>` with
  the pattern form, and the stranded-tests check reads arguments as Node 24
  does (files, patterns, TypeScript it collects).
- **`StackPack.process_memory`**: the per-process data limit counts what V8
  reserves, not uses. Angular needs 4g (real use 0.4-1.6 GB); the tree
  watcher still bounds real use. The scaffold writes its contract (unproven)
  before the first install so its smoke tests get the same limit.
- **Not yet covered** (a stack naming one gets no pack, by design rather than
  the wrong one): Nuxt, SvelteKit, Remix, Ktor, Quarkus, Solid, plus CLI and
  library packs outside Python - the next scaffolding wave (design notes:
  CLI acceptance through `node:test` running the built program, as services
  use Playwright's `request`; libraries in each language's own runner).

### 2.2 Verify on the next run

1. **The scaffold.** The decision record says the pack's title. On brief_medium
   that is `fullstack-react-fastapi` or a sibling, not "left to the agents".
   `.harness/stack-pack.json` has `"scaffolded": true`.
2. **Batching.** In `loop.sh defects`, a bundled defect's story reads "bundled",
   then either "closed without a fixer" (by measurement) or a fixer of its own -
   never "fixed in batch".
3. **The procedural test round.** "skipping specialist LLM invocation" appears
   only when the locked suite ran green.
4. **Builders in parallel.** No `belongs to another work order` refusal follows
   an IDE note about an import.
5. **A custom stack (after `58600ee` is deployed).** The decision record says
   "a proven setup" or "left to the agents" with the failing smoke test; with a
   proven one, `.harness/stack-pack.json` has `"pack": "proven-setup"` and QA
   writes into the declared acceptance directory. `look_up_package` and
   `use_runtime` calls appear in transcripts without failing.

### 2.3 Recent runs (newest first; full history in monitoring §0.2)

- **run-d1899b44** (brief_medium, 08:19-09:02 JST 2026-10-13, on `79089ea`):
  CANCELLED at 44 min. The selector chose "Browser app in React with its own
  HTTP service in FastAPI" in its rationale but left the frontend field "not
  stated", so no pack fitted (custom stack). Fixed in `e95d943`: a pack the
  rationale names alone is chosen when the fields fit none.
- **run-c7a1f6cf** (brief_medium, 21:19 JST 2026-10-12 - 07:11 JST 2026-10-13,
  parallel, on `b0c092c`): FAILED in sprint 1's defect fixing at 9 h 52 min.
  - First medium run on a proven pack (`fullstack-react-fastapi`, scaffolded).
  - `defect_fix_1_3` spent its 40 calls three times over on one defect (login
    422: email validation); the third attempt found the cause on its last call.
  - Fixed in `2e4e2ef`: fix and work-order stages out of retries leave their
    work open (the defect stays open; the blocker carries where the attempt
    ended) instead of failing the run.
  - 80% of output tokens were reasoning; verification took 197 min. Lost
    replies were all recovered by `b0c092c`.
  - The operator session was paused overnight, so the run was not cancelled
    for its length; it should have been, around hour 6.
- **run-c83ee867** (brief_medium, 13:40-14:34 JST 2026-10-12, on `b2f837b`):
  FAILED at sprint planning.
  - The scrum master reasoned through its whole 25,000-token reply twice.
  - The first loss was carried by the graph's one nudge, with thinking off;
    the second ended the stage with thinking never switched off for the rest
    of the visit.
  - Fixed in `b0c092c`: a lost reply jumps straight back to the model.
  - The architecture, consultation and acceptance-authoring stages before it
    had 0 failed tool calls.
  - The loop then sat idle about seven hours: the operator session had hit its
    usage limit.

- **run-fe7854b9** (brief_medium, 23:50 JST 2026-10-11 - 02:29 JST
  2026-10-12): cancelled in a defect fix.
  - Its stack decision said no pack fits (Python/FastAPI + React), yet the
    contract lookup wrote a `node-http-api` contract two minutes in.
  - It inferred that from a stack-document sentence explaining why a
    JavaScript option was rejected.
  - Fixed in `6314d91`.
- **run-fd3a244d** (brief_medium, 17:16-23:17 JST 2026-10-11): FAILED at the
  6-hour Celery limit.
  - It was given a guessed `python-http-api` contract; that pack's
    `pytest.ini` and `acceptance/conftest.py` were written into a project with
    a browser page.
  - The pack's acceptance command never produced a report (13/13 criteria
    "untested").
- **run-fdc1385c** (brief_medium, 12:59-16:45 JST 2026-10-11): FAILED. Its
  test round could not answer, which `f9987af` now records as blocked.
- **run-5aadbddd / run-49dec2db** (web-todo, 2026-10-10/11): the stage 1 gate
  runs, 10/10 each.
  - 49dec2db took 327 min (4 defect-fix stages over one ambiguous locked
    locator); 5aadbddd took 80 min with no defects - same code.
  - 49dec2db's scaffold was "left to the agents" over the browser-version
    mismatch.

- **run-d96ae4c7** (12:15-17:32 JST, 2026-10-10): COMPLETED, score 10/10 (1.0).
  Product audit clean: 323 LOC, 47 unit tests pass (exit 0), working tree clean.
  Not clean: locked acceptance suite had `locator('button', { name: 'Edit' })`
  and `locator('button', { name: 'Delete' })` asserting `toHaveCount(1)`. In
  Playwright, `locator()` does not accept `name` options (only `hasText`, `has`,
  `hasNot`), so Playwright ignored `name` and matched all buttons (2 buttons in
  sprint 2), trapping specialists in 102 minutes of defect remediation until
  auto-escalation deferred criteria. Fixed before next run with
  `suite.locators_with_invalid_name_option` and `PLAYWRIGHT_LOCATORS_RULE`.
- **run-d211dc86** (14:10 JST, 2026-10-08): cancelled within seconds.
  `loop.sh ready` printed NOT READY but exited 0, so the run started while
  LM Studio served gpt-oss and the settings named qwen. Fixed in `344b4a9`,
  so `ready` exits 1.
- **run-7b219f82** (07:47-13:57, on `97d9dd1`): cancelled by the owner in
  sprint 2's second revision. Not clean. Findings, each fixed in the commit
  named:
  - A fix stage built later sprints' features (`d833edb`).
  - `style.css` against `styles.css` in the plan check (`8da1e0d`).
  - Two locked tests contradicted each other on order (`60971c5`; the
    mid-attempt dispute then worked).
  - `npm test` failed only on sprint 3's tests and was recorded as a defect
    (`351d1ec`).
  - The scaffold smoke test failed once, so no contract kept the pack's files.
    A tester then switched sprint 3's tests off in the runner configuration
    (`1dde0ed`).
- **run-0e484d19** (00:17-07:44): COMPLETED. Hidden tests 10/10, locked suite
  25/0, product audit clean. Not clean: seven fixes were deployed during it
  (`c3a5fca`, `f3d2409`, `9cc524a`, `fa8da1a`, `4bdf05c`, `cc875e7`, and
  `548a63d`/`97d9dd1` after it).
- **run-379e32c0** (23:24-00:06): cancelled. The sprint plan put sprint 2's
  work in sprint 1 (`6ff499e`).
- **run-d43cb02c** (21:00-23:14, 2026-10-07): cancelled. Sprint 1 built every
  sprint's features (`3b01d8a`), and the rewrite guard refused a stage its own
  code (`46be22f`).
- **run-f7f82c39** (12:15-14:15, 2026-10-07): COMPLETED 10/10 with no harness
  fix during the run. It was not clean only because the release record was left
  uncommitted (`6ff9456`). It is the closest any run has come.

### 2.4 Why runs got long, and what to expect now

Runs went from 1-3 hours to 5-8 hours on 2026-10-07. Three causes:

- **The owner's model switch.** `qwen3.6-35b-a3b-mtp` writes 2,100-3,700
  output tokens and takes 19-32 s per call, against gpt-oss-20b's 400-840
  tokens and 5-8 s.
- **Thinking left on.**
- **Sprints that now really are sprints** (the scope fixes above).

Back on gpt-oss-20b, expect calls about 4× faster. The thinking budget is the
biggest remaining lever, and it is the owner's decision (§7).

## 3. Setting up on a new desktop

Skip this section on the same machine (`/home/arun/Desktop/langchain`):
everything is already set up there.

1. `git clone https://github.com/marunsct/DevFlow.git` and
   `git checkout harness-hardening-session`. Name the remote `main`
   (`git remote rename origin main`) so the push command above works.
2. **`.env`**: copy it from the old machine yourself, by a private route. It
   holds secrets: never commit it, print it or paste it into a chat. The old
   machine's `/home/arun/harness-handover-2026-09-19.zip` contains a `.env`
   too; treat it the same way.
3. **Database**: Postgres data lives in `./data/postgres` (git-ignored). Copy
   that directory across to keep runs, settings and users, or start fresh. A
   fresh database's admin password comes from `ADMIN_PASSWORD` in `.env`, or is
   printed once in the app log. Transcripts and workspaces live in the Docker
   volume `appdata` and do not travel; they are only needed for history.
4. `docker compose build app worker && docker compose up -d`. The containers
   are `langchain-app-1`, `langchain-worker-1`, `langchain-db-1` and
   `langchain-redis-1`; the API is on `http://localhost:8000`.
5. **Model server**: the owner sets `model_name`, the base URL and the
   reasoning settings in the admin UI's settings. A model on the host is
   reached from the containers as `host.docker.internal`.
6. **Loop operator account.** Do not use the admin account for the loop. Use
   user `harness-test`, password `loop-test-only-pw-2026`, role `operator`.
   - It is written here at the owner's request (2026-10-07) so any agent can
     run the scripts.
   - It exists only in the local Postgres, and the owner deletes it when
     development completes.
   - Run `export LOOP_USER=harness-test LOOP_PASSWORD=loop-test-only-pw-2026`
     in your shell.
   - If a fresh database lacks it:
     `docker exec langchain-app-1 python -m app.server.manage create-user harness-test --password loop-test-only-pw-2026 --role operator`.
7. **Tests** need a Python venv at `.venv` with the project and its test extra
   (`uv sync --extra test --inexact`), and Node on the host (some tests run
   `node --check`). Then run `loop.sh suite`.

## 4. Commands

```sh
scripts/loop/loop.sh status              # current run + anything live
scripts/loop/loop.sh ready               # served model matches the settings? last line ALL READY, exit 0
scripts/loop/loop.sh bench web-todo      # a gate run; needs LOOP_USER / LOOP_PASSWORD (§3 step 6)
scripts/loop/loop.sh start [brief]       # a brief with no hidden tests; same credentials
scripts/loop/loop.sh cancel [run-id]
scripts/loop/loop.sh wait [minutes]      # blocks until the run ends or N minutes, then audits
scripts/loop/loop.sh audit [run-id]      # failures, redundant reads, stage order
scripts/loop/loop.sh stage <stage> [HH:MM]  # trace one stage (HH:MM is UTC)
scripts/loop/loop.sh timing [run-id]     # model vs tool time, reasoning share
scripts/loop/loop.sh product [run-id]    # the generated product, the harness's claims, its own tests
scripts/loop/loop.sh score [run] [name]  # the hidden tests of a finished run
scripts/loop/loop.sh failures [run-id]   # each failing acceptance test, its error and the page
scripts/loop/loop.sh defects [run-id]    # each round's defects: what raised each, how it ended
scripts/loop/loop.sh asked [run-id] <stage> [visit] [--full] [--system]  # what a stage was told, and its answer
scripts/loop/loop.sh mutate [run] [n]    # how many small product changes the locked suite catches
scripts/loop/loop.sh bench-report        # false acceptances across every scored run
scripts/loop/loop.sh resumed             # after a deploy into a live run: waits for it to resume
scripts/loop/loop.sh deploy              # rebuild, restart, verify the image matches the tree
scripts/loop/loop.sh suite               # full suite -> data/loop/suite.log (~3 min)

docker exec langchain-db-1 psql -U postgres -d langchain -tAc "<sql>"   # read-only; tables: runs, runtime_settings, ...
docker compose logs --since 20m worker   # model calls, stage failures
```

**State files:**

- The current run id is in `data/loop/current_run.txt`, and the current brief
  in `data/loop/current_brief.txt` (both git-ignored).
- A run the owner starts from the UI is not written there; put its id in by
  hand.
- A run started by the admin account may refuse a cancel from the operator
  account. If so, ask the owner to cancel it from the UI.

**Where a run's evidence lives:**

- **Transcripts:** `/app/data/transcripts/<run-id>*.jsonl` inside the worker.
  - Record kinds: `model_request`, `model_response` (text, usage,
    finish_reason, tool_calls), `tool_call` (`tool`, `call_id`, `args`),
    `tool_result` and `defect`.
  - `model_request` records are windowed: use the `carried` offset for
    absolute message positions.
- **Workspace:** `runs.repo_root`, e.g.
  `/app/data/workspaces/default/workspace-<run-id>/`.
  - The harness's own state is in its `.harness/` folder (git-ignored):
    - `stack-pack.json` (the scaffold contract);
    - `acceptance.json` and `acceptance-result.json`;
    - `acceptance-locks/vN/` (every locked suite version, each with its diff);
    - `ci.json`, `decisions.json` and `sprint-scope.json` (this sprint, the
      total and the criteria not yet due).
- **Truncated tool output:** the full text is under
  `/app/data/journal/<reference>` in the worker.

**For one-off analysis:** pipe a Python script into the worker
(`docker compose exec -T worker python - <args> < script.py`), as
`scripts/loop/*.py` do. Put a helper you will reuse in `scripts/loop/`, never
only in a scratch directory: a deploy wipes the worker's `/tmp`, and
scratchpads don't travel between agents.

## 5. Things that bite

**Deploys and the worker:**

- There is no source mount, so a restart deploys nothing. A deploy wipes
  `docker logs` and the worker's `/tmp`.
- Orphan recovery resumes any `running` run after a deploy. Cancel a
  superseded run, or it competes for the worker and the model server.

**Editing while something runs:**

- Do not edit `src/` while the suite runs. Tests that read source with
  `inspect` see shifted lines and fail.
- Do not edit `loop.sh` while a `wait` is running: bash reads the script as it
  goes. Check with `pgrep -f "loop.sh wait"` first.

**Tests:**

- The suite baseline is in §2. Apart from the three expected S3 failures, any
  failure is real. Tests that need the TypeScript compiler or Pyright skip on
  the host; verify those inside the worker after a deploy.
- A test must reproduce the state production really produces. Prove that a new
  test fails on the old code (stash the fix, run the test, restore) before
  trusting it.

**The environment:**

- `uv add` / `uv remove` re-sync `.venv` without the test extra and drop
  pytest. Restore it with `uv sync --extra test --inexact`, then
  `uv pip install uvloop watchfiles` if they went too.
- Auth is a form-encoded `POST /api/auth/token`; there is no JSON login.

**Before starting a run, check the model:**

- Never start a run while the model server's loaded model differs from
  `runtime_settings.model_name`. The owner changes both without saying so.
  Run `loop.sh ready` before every `bench`/`start`; it exits 1 when they
  differ.
- With no model loaded, do not load one. Leave one long background watcher on
  the endpoint, the settings and live runs, and start when they agree.
- Check passively with `curl <base url>/v1/models`. `lms ps` wakes LM Studio's
  background service when the app is closed.
- A model server that needs a key answers 401 to a bare `curl`. Ask through
  the harness's own settings instead, inside the worker, and print names only:

  ```sh
  docker compose exec -T worker python - <<'PY'
  import json, urllib.request
  from app.models import _runtime_settings
  s = _runtime_settings()
  r = urllib.request.Request(s.openai_base_url.rstrip("/") + "/models",
      headers={"Authorization": f"Bearer {s.openai_api_key}"} if s.openai_api_key else {})
  served = [m.get("id") for m in json.load(urllib.request.urlopen(r, timeout=10)).get("data", [])]
  print(s.model_name, "at", s.openai_base_url, "served:", s.model_name in served)
  PY
  ```

**Your own session:**

- Waits, watchers and scheduled retries belong to the session that started
  them. After a restart there are none, so start them again.
- **Two agents in one tree:** before any commit, deploy, start or cancel, look
  for edits that are not yours (`git status`) and for another agent's waits
  (`pgrep -af "loop.sh"`). One agent drives (commits, deploys, starts and
  cancels); any other audits read-only and passes its findings on. If the
  driver has gone, take the role so the loop does not stall.

**Reading the evidence:**

- About 63% of reported defects in a 46-run study were about tests and their
  set-up, not the product. When a run stalls, read the failing test command's
  raw output before believing any defect description.
- Ordinals in guard messages count the whole run, not the stage.

## 6. Security rules

- Never print or copy secret values from `.env`. Change only the keys that
  need changing, and back the file up first.
- Do not kill the owner's GPU or model processes (llama-server, Bonsai,
  unsloth, the server on port 9090, LM Studio), and do not take over the
  port-8888 server.
- Do not change the owner's model-server settings, and never load a model
  yourself.
- Never add knowledge or documentation credentials to
  `sandbox._ENV_PASSTHROUGH`.
- Do not read or reset the admin password, use the admin account, escalate
  the loop account, or write the settings table directly.
- Credentials once committed in removed `scratch/` files are still in git
  history. Never repeat them; recommend rotation; rewrite history only if the
  owner asks.
- API keys that appear in `ps` output or logs are never repeated.
- For GitHub tokens, the owner uses their own terminal.
- Docker socket access is root-level; don't enable it more widely.
- The loop account's password is in this file by the owner's decision
  (2026-10-07). It is the only credential that may be written down.
- Never commit or alter `docs/logs.md`, the owner's own file.
- Never route shell work through another command-running tool to get around
  the tool-approval check.

## 7. Open, parked, and awaiting the owner

**The owner's decisions - do not change these on your own:**

- **The thinking budget** (thinking effort / thinking mode per role). This is
  the biggest time lever (§2.4).
- **Whether every fix must add a regression test.** A run-7b219f82 attempt
  failed over a code-review defect two fixers left without one.
- **The CRITERION severity policy** (minor vs blocking grading).
- **The `node -e` policy.** One-off command-line code is refused.
- **Whether a browser test must cover every action the brief names.**
- **Whether CLI products get the UI/UX consultation.**
- **Deleting the `harness-test` account** when the loop ends.

**Parked** (details in monitoring §0.5.1):

- A milestone review may ask for later sprints' work to be removed.
- The plan check's action table has no persistence: sprint 1 may build storage
  early, which is minor.
- A scaffold whose smoke test fails twice leaves its files unkept, though
  their comments say the harness keeps them.
- A stage's own notes (`blocker.txt`, `verification.log`) may ship in the
  product.
- Wildcard arguments are not expanded, because commands run without a shell.
- Tools are offered when command execution is disabled.
- `test/` and `tests/` suites are duplicated.

**Throughput** (monitoring §0.9). Proposals measured but not built:

- two-step lead planning;
- per-role reasoning effort (the owner's setting);
- one sprint for a small brief (conflicts with the product design).

In parallel mode with auto-approve, gated calls pause and drain one per
superstep. Fixing that would be a redesign of the runner's auto-approve loop,
not a fix.
