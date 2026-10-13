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
| deployed | `79089ea` is live (deployed 08:15 JST 2026-10-13): wave 2 and 3 packs, Node 24 in the image, Angular, and fix/work-order stages that fall back on exhausted retries. `verify_packs.py` in the live worker: 27 of 27. **Pushed, not deployed** (deploy when run-23896345 ends): `70c2e66`, an unready plan ranked by problems per work order; the next commit, parallel work orders wait only for a manifest still to be made and a file truly shared. Note: LM Studio served overlapping calls at 27 tok/s each against 86 alone, so parallel mode saves little wall time until the server batches requests. Also pushed, not deployed: a test acts on the page only when it takes the page fixture (a comment saying 'page' reopened a locked suite twice). |
| current run | `run-23896345` (brief_medium, parallel), started 09:07 JST 2026-10-13 on `e95d943`. |
| model | `qwen3.6-35b-a3b-mtp` on LM Studio, `http://host.docker.internal:1234/v1`, thinking effort medium, execution mode **parallel**. |
| Celery limits | soft 43,200 s (12 h), hard 43,500 s - in `tasks.py`, `docker-compose.yml` and `.env.example` (the handover had claimed this before it was done). |
| suite | 9,840+ pass, 29 skip, 3 expected S3 fails (`tests/test_codebase_seeding_api.py`). |

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
