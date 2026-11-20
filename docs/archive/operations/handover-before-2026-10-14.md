# Handover - sections before 2026-10-14

Moved from `docs/HANDOVER.md` on 2026-10-21 (plan MF.6): run narratives older than a week.
Nothing here is current; `docs/STATE.md` is.

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
  is live; in cron since 2026-10-20 (owner): daily 03:00, `crontab -l`, log `data/loop/nightly-cron.log`).
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

