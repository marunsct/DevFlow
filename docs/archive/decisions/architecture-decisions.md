# Architecture Decision Records

> The architecture of DevFlow and the reason behind each decision. ADR-0005 (the company-shaped pipeline) is the one to read first; `docs/PRODUCT.md` §2–§3 describe the result. Consolidated 2026-10-19.

Record one decision per section. Do not silently replace a decision; supersede it with a new entry.

## ADR-0001: Initial Product Architecture

- **Status:** Superseded by ADR-0002
- **Date:** 2026-09-03
- **Context:** The Hub needs durable, multi-tenant Decision Threads combining video, AI processing, approvals, and ADR-style knowledge capture.
- **Options considered:** A monolith with in-process media/AI work; a client-only application; a modular API with asynchronous workers.
- **Decision:** Consolidate on a Python backend (FastAPI + Celery) and a lightweight React SPA frontend. Use PostgreSQL for relational data, S3-compatible object storage for artifacts, and Redis for Celery task queues and rate limiting. Keep model providers replaceable so LM Studio/local inference can be used in development.
- **Rationale:** The split keeps uploads and user requests responsive, isolates long-running media and AI workloads, preserves relational integrity for approvals, and supports local or hosted model backends without changing product contracts.
- **Consequences:** More deployment and observability work; explicit job idempotency, retry, status, and data-retention behavior are required.
- **Validation evidence:** Principal Architect specification and Senior Architect Reviewer approval are required before implementation.

## ADR-0002: Pivot to React+Vite, FastAPI, and Celery

- **Status:** Accepted
- **Date:** 2026-09-09
- **Context:** Initial prototypes required rapid iteration in Python due to heavy reliance on LangChain and LangGraph for AI orchestration. The NestJS middle-tier added unnecessary overhead when Python could serve both the API and worker tiers effectively.
- **Options considered:** Continuing with Next.js/NestJS vs consolidating on a Python backend (FastAPI + Celery) and a lightweight React SPA.
- **Decision:** Consolidate the backend to Python using FastAPI for the API layer and Celery for asynchronous workers. Replace Next.js with a React+Vite Single Page Application (SPA) to simplify frontend deployment and tooling. Use PostgreSQL via psycopg2 (and psycopg2.pool) for persistence and SQLite/Postgres for LangGraph checkpointers.
- **Rationale:** This architecture drastically reduces context switching by keeping all backend logic (API and AI) in Python. Celery natively integrates with FastAPI and Python ecosystems. React+Vite provides a fast, lightweight frontend experience without the complexity of SSR unless needed.
- **Security and privacy impact:** Requires standard FastAPI security practices (CORS, dependency injection for auth). DB credentials and JWT secrets must be carefully managed in the environment.
- **Operational impact:** Simplifies the container topology (fewer language runtimes). 
- **Consequences and trade-offs:** We lose some Next.js built-in optimizations (like SSR) but gain significant velocity in AI feature development.
- **Supersedes:** ADR-0001

## ADR-0003: The harness ships deployment artifacts for the products it builds

- **Status:** Superseded by ADR-0004
- **Date:** 2026-09-21
- **Context:** `src/app/deploy/` contains `DockerGenerator`, `ComposeGenerator` and `CIGenerator`, and `src/app/build/verifier.py` contains `BuildVerifier`. None of the four has a caller anywhere in `src/` - a grep for the class names returns only their own definitions - and all four sat inside a coverage `omit` glob, so nothing measured that they were never called. Part III §4 of the hardening plan (now `docs/improvement-plan.md`) raised this as a question that had to be answered before any code was written, because the two answers lead to opposite work: delete 340 lines, or fix and extend them.
- **Constraints:** What the generators emit today is insecure by default and would ship the moment they were connected: `POSTGRES_PASSWORD: password` and `MYSQL_ROOT_PASSWORD: password` in generated compose files; no `USER` directive in any of the five language branches, so every generated image runs as root; `COPY . .` placed after dependency installation, defeating layer caching; and `curl -LsSf https://astral.sh/uv/install.sh | sh` in generated CI, which pipes a script from the internet into a runner. That last one is the pattern `seeding.py` refuses `ext::` transports to prevent and `sandbox.py` refuses `python -c` to prevent, written into a file that runs on every push of the product the harness builds. Their language coverage is also narrower than the rest of the system's: four languages against the eleven the stack selector can choose.
- **Options considered:** (a) Retire them - delete the four modules and stop at a tested working tree. (b) Wire and fix them - repair the four defects, extend to every language the stack selector can choose, and connect them to the workflow. (c) Defer - leave them unwired and omitted from coverage.
- **Decision:** (b). The harness ships deployment artifacts for the products it builds. The three generators and `BuildVerifier` are to be repaired, extended and wired into the workflow.
- **Rationale:** A harness that builds a product and stops at a working tree leaves the last mile to a human, and the deployment artifacts are the part most likely to be got wrong by someone who did not write the code. The modules are individually well-made - `docker_generator.py` already produces correct multi-stage builds for five languages - so the work is repair and extension rather than design.
- **Security and privacy impact:** Net positive, but only once the work is done. Until the four defects in plan-part3 §4.1 are fixed, wiring these generators would actively ship plaintext default credentials, root containers and a `curl | sh` CI step. The defects must be fixed **before** the modules are connected to the workflow, not after; connecting first would be a regression.
- **Operational impact:** Generated products gain a Dockerfile, a compose file and a CI pipeline. The generator set becomes something that has to stay in step with the stack selector's language set, which is a standing maintenance obligation - hence the test below.
- **Consequences and trade-offs:** The plan sizes this at S-M effort, which was the estimate for *deciding*; the extension to eleven languages is days rather than hours. Option (a) was cheaper and remains the fallback if the extension proves not to be worth it. Taking (b) means the coverage `omit` entries for `deploy/*` and `build/verifier.py` in `pyproject.toml` are temporary and must be removed as each module gains a caller and a test.
- **Validation evidence:** Required before this ADR can be marked complete - a generated Dockerfile contains a non-root `USER` directive and no default password; a generated CI file contains no `curl | sh`; and one test asserts the generator language set equals the sandbox toolchain set, which is the §1-B rule (a rule defined over part of the set it governs) applied to this package so the sets cannot drift apart again.
- **Supersedes or related decisions:** None. Answers Part III item 5 of the hardening plan (now `docs/improvement-plan.md`).

## ADR-0004: Release files come from the stack pack, not from generic generators

- **Status:** Accepted
- **Date:** 2026-10-04
- **Context:** ADR-0003 chose to ship deployment artifacts through `DockerGenerator`, `ComposeGenerator` and `CIGenerator` in `src/app/deploy/`. Their security defects were fixed; the wiring never happened. Since then the stack packs (`src/app/stacks/`) became the one place that knows how a product installs, starts and is tested - the harness scaffolds every project from one and runs its exact commands for every CI gate and acceptance run.
- **Constraints:** A file the harness ships must not describe a build nobody has seen pass. The sandbox has no container runtime, so a container definition cannot be built here.
- **Options considered:** (a) Wire the generators as ADR-0003 decided. (b) Have each pack declare its release files, rendered from its own commands. (c) Ship nothing and stop at a tested working tree.
- **Decision:** (b). At release, once the suite passes, the harness adds a CI workflow that runs the pack's own install, unit and acceptance commands, and for a service a container definition and ignore file; it never writes over a file the product already has, commits what it added, and names it in the release decision. `src/app/deploy/` is deleted.
- **Rationale:** The generators held a second model of every stack - base images, entry points, test commands - that could disagree with the pack and had never been run. A CI file generated from `StackPack.commands` runs exactly what the harness ran, so it is correct by construction for every stack a pack covers, and a new pack gets it with no further work.
- **Security and privacy impact:** Containers run as an unprivileged user, take configuration from the environment the service already reads, and carry no credential; the CI file pipes nothing from the internet into a shell. Pinned by `tests/test_a_release_carries_what_ships_it.py`.
- **Operational impact:** Service packs read `HOST` (default `127.0.0.1`, `0.0.0.0` in the container). The release record states that the container definition was written, not built.
- **Consequences and trade-offs:** A product built without a pack gets no release files. CI targets GitHub Actions; another provider is a second renderer of the same commands.
- **Validation evidence:** every pack's CI runs its own commands; every service container is non-root with dependencies installed before the source; an existing product file is kept.
- **Supersedes or related decisions:** Supersedes ADR-0003. See `docs/improvement-plan.md`, R4.

## ADR-0005: Build products the way a software company does

- **Status:** Accepted (all phases done 2026-10-03/04)
- **Date:** 2026-10-03
- **Context:** About 70 runs on the simplest brief on 2026-10-03 produced no
  clean product. Two causes sat under almost every finding:
  1. **"Done" meant "the model's own tests pass".** The same stages wrote and
     rewrote the code and the tests. Products were accepted where nothing
     redrew after a delete, or whose page no test ever opened.
  2. **Quality was enforced by hand-written pattern checks.** There were over
     6,700 lines of them, mostly about JavaScript and HTML. Each new one
     brought false positives, and none carried over to another kind of
     product.
- **Options considered:** (a) keep adding pattern checks per failure; (b) one
  agent loop with self-tests; (c) a company-shaped pipeline whose definition
  of done is a locked acceptance suite written by QA before the build, run by
  the harness, with technology knowledge only in stack packs.
- **Decision:** (c). The target flow:

  ```
  intake -> [review] -> stack -> architecture -> architecture review -> [review]
       (a review that never converges -> escalation: build from the latest design, risks recorded)
    -> scaffold (stack pack, smoke-tested)
    -> acceptance author (QA writes one test or more per criterion)
    -> acceptance review (coverage check + reviewer) -> [review] -> LOCK
    -> sprint plan (vertical slices, each sprint names the criteria it makes pass)
    -> per sprint:
         work orders -> CI per batch (revert on regression) -> code review
         -> test round + harness-run acceptance suite -> fixes (escalation ladder)
         -> security review -> milestone review (cannot accept a red acceptance gate)
         -> [review with evidence] -> commit
    -> release gate (every criterion not deliberately deferred passes; CI and container files
       added from the pack) -> [review] -> complete
  ```

  `[review]` is a decision point. In **auto** mode the harness decides and
  writes a decision record. In **approval** mode the same record is shown to
  the user, who approves, requests changes or, where offered, picks an
  option. A requested change becomes a tracked change request with its own
  acceptance test.
- **Rationale:** a test suite the builders cannot edit is the only "done"
  that a weaker model cannot argue its way past. Packs keep the core
  language-agnostic, so the check that a product works is the pack's own
  test command and never a pattern written for one language.
- **Components:**

  | Component | Module | What it does |
  |---|---|---|
  | Stack packs | `app/stacks/` | One per kind of product and language: scaffold files, install/unit/acceptance commands, JUnit report paths, the acceptance-test guide, the files the harness keeps as set up, which cross-file check families apply. The core knows no language. |
  | Scaffold | `app/stacks/scaffold.py`, node `scaffold` | Writes the pack into the project directory, installs, and runs the pack's own unit and acceptance smoke tests before any agent writes code. |
  | Project contract | `app/stacks/contract.py` | Repairs the pack's commands and runner configuration after every stage, and describes them in every specialist request. `owned_by_the_harness` is the one answer to who owns a path. |
  | Release files | `app/stacks/release.py` | At release, a CI workflow that runs the pack's own commands and, for a service, a container definition; never over the product's own files (ADR-0004). |
  | Acceptance criteria | `app/acceptance/criteria.py` | Numbers the intake's acceptance criteria and success measures as AC-1..n. |
  | Acceptance suite | `app/acceptance/` | Author request, coverage check, lock (checksums plus a snapshot), harness-run suite with JUnit parsing, per-criterion results. |
  | Gates | `graph/workflow.py` | Test rounds add the harness-run acceptance failures as defects; the milestone review cannot accept a sprint whose criteria are red; the release gate needs every criterion not deliberately deferred. |
  | Per-role models | `models/roles.py`, `models/endpoints.py` | A judgement model for architect, QA, reviewers and fixes; the default model for everything else (see ADR-0008). |
  | Decision records | `app/decisions.py` | One record per decision point, in state, in `docs/decision_log.md`, and over the API and UI. |
  | Change requests | `app/decisions.py` | A user's requested change becomes CR-n with its own acceptance test and is followed to closure. |
  | CI and code review | `app/ci.py`, nodes `ci_gate`, `code_review` | Per batch: build, unit and acceptance runs against the baseline; a batch that breaks what passed is reverted; a reviewer reads the diff. |
  | Escalation ladder | `graph/escalation.py` | fix -> re-plan -> judgement model -> decision (auto: defer the criterion with a reason; approval: ask). |
  | Check scoping | `analysis/integration_checks.py` | Each check has a family; only core checks and the pack's families run; only near-certain checks can block. |
  | Benchmark | `benchmarks/`, `scripts/bench/` | Briefs across product kinds, hidden acceptance tests the harness never sees, and a scorer. |

- **Consequences and trade-offs:** many more model calls per run than a
  single agent loop (ceremony cost later answered by ADR-0007), in exchange
  for a verdict the builders cannot fake. Every stack the harness promises
  needs a pack (support tiers, `app.stacks.support_tier`).
- **Validation evidence:** phases 1–11 done (stack packs, acceptance suite
  and lock, gates, per-role models, decision records and change requests,
  CI per batch with revert, vertical-slice planning and the escalation
  ladder, check scoping, benchmarks with hidden tests). The loop restarted
  2026-10-03 21:53 JST. Stage 1 benchmark gate passed 2026-10-17 (2 of 2
  clean runs; `docs/monitoring-handover.md` §0.2).
- **Supersedes or related decisions:** formerly
  `docs/redesign-software-company.md`, merged here on 2026-10-19.

## ADR-0006: Refuse at the point of failure; never lock what cannot load (high-steering principles)

- **Status:** Accepted; implemented in substance (see the improvement plan,
  section E2, for each pillar's status)
- **Date:** 2026-10-09
- **Context:** On 2026-10-09 one web-todo run was fully built in 8 minutes
  and then spent 114 minutes failing. Its acceptance suite used a module
  syntax the project did not load, and it was locked before anything checked
  that it could run. Once the suite was locked, the write guard reverted
  every attempt to fix it. Advisory notes appended to successful tool output
  were ignored by local models.
- **Decision:** five standing principles:
  1. A broken file is **refused at the write** by the language's own parser,
     not noted.
  2. A suite is **proven to load and run** before it is locked.
  3. Remediation is grouped so one root cause is fixed once.
  4. Steering intensity follows a **measured** signal (repeated calls, parse
     failures, the `fitness` probe), never a model name.
  5. Steering **never** changes the owner's model or settings.
- **Rationale:** a tool result that says "success, but…" is read as success
  by weaker models; a refusal is not. A locked suite that cannot load turns
  the definition of done into a trap.
- **Consequences:** more refusals early in a stage (counted per run by V,
  layer economics); the tier logic needs measurement before it can act
  (BH).
- **Validation evidence:** the parser refusal and the integrity checks before
  lock are in the code (`docs/PRODUCT.md` §8). Each pillar's status is in
  the improvement plan, section E2.
- **Supersedes or related decisions:** formerly
  `docs/high-steering-software-company-implementation.md`, merged
  2026-10-19. That document's implementation pillars are in the improvement
  plan (section E2) and its research comparison is in the research findings
  (Part R6).

## ADR-0007: Two delivery modes — fast and thorough

- **Status:** Accepted
- **Date:** 2026-10-14 (`e55dd6f`)
- **Context:** One run of a five-route notes service took 13 hours: 1,081
  model calls one after another and 2.8 million output tokens (half of them
  reasoning) for 549 lines of product and 5,058 lines of tests. Most of the
  time went to ceremony (four sprints, each re-planned, reviewed and
  test-rounded) and to an agent loop of about forty tool calls per work
  order.
- **Decision:** `DELIVERY_MODE` = `fast` or `thorough`, chosen per run
  (`app/delivery.py`, `for_the_run`) and kept on the run's record.
  - **Fast** keeps every stage and record but changes how much each does:
    - a product with few criteria is one sprint;
    - each work order's files are drafted straight from the specification,
      one call per file, several at once (`graph/drafting.py`), with the
      agent loop as the fallback;
    - a test round is the harness's own (suite plus unit tests, failures
      become defects without a model reading them);
    - build stages run with reasoning off.
  - **Thorough** is the full pipeline.
  - What makes a run faster without removing anything is on in both:
    project memory, errors refused at the write, a silent suite run file by
    file, gathering on the build model, and candidate fixes.
- **Consequences:** fast mode is the deployment default
  (`docker-compose.yml`). The code's own default is thorough. Fast mode is
  what made the 82-minute web-todo run possible; complex briefs still
  struggle (review findings I2 and I5, plan AY and AZ).

## ADR-0008: Two model tiers; the model and its settings are the owner's

- **Status:** Accepted
- **Date:** 2026-10-03 (tiers), standing owner rule
- **Decision:**
  - A **build** (default) model and an optional **judgement** model
    (`models/roles.py`): judging stages and escalated retries use the
    judgement model, and `escalate_after()` moves a defect's fix there after
    repeated failures.
  - The harness **never** loads a model or changes the owner's model, server
    flags or sampling. Per-request sampling presets were dropped for this
    reason (plan M.3, owner decision 12).
  - The only per-request fields the harness may send are:
    - `max_tokens`;
    - the thinking switch and effort (already sent);
    - a reasoning budget (plan AX), like `max_tokens` a limit on this reply;
    - `seed` (plan AY candidates).

    Temperature, top-p, top-k, min-p and repetition penalties are never
    sent (plan Part 22.1 #1).
  - The harness reads what the server reports (`/props`: slots, per-slot
    context) and adapts to it (M.1, O.2, AB).
  - `loop.sh ready` must print `ALL READY` before any run.
- **Consequences:** an all-local deployment has one tier unless the owner
  serves two. Plan BD turns the same weights into a second tier through a
  per-request reasoning budget (AX) instead.

## ADR-0009: A product that stores data starts on an embedded database

- **Status:** Accepted (owner decision 3, 2026-10-18; plan K.2 option A)
- **Decision:**
  - The environment contract every stage receives says a product that
    stores data runs on an embedded database by default, in a file under
    `DATA_DIR`.
  - The acceptance server gets a fresh `DATA_DIR`.
  - A Postgres service is added to the compose file only when a brief
    demands it, and only with the owner's yes.
- **Rationale:** the sandbox cannot provision services per run. A
  specification free to require a server database produced products that
  could never start in the sandbox (review finding F2).

## ADR-0010: Measurement first — every claimed improvement is falsifiable

- **Status:** Accepted (plan Initiative W, 2026-10-18)
- **Decision:**
  - Every scored run writes a KPI JSON (`data/kpi/<run>.json`) and a row in
    `data/kpi/ledger.csv` (`loop.sh kpi`, run by every `loop.sh score`).
  - A KPI more than 1.5× its five-run mean is flagged.
  - A score against another brief's hidden tests is marked
    `brief_mismatch`.
  - Each change states the KPI it moves, and the W.2 baseline runs come
    before further harness changes are judged.
  - Wave gates need at least two runs (plan Part 20).
- **Rationale:** several plausible fixes were measured and dropped (L.2, M.2,
  AC.3, Z), and a single run's numbers swing widely.

## ADR-0011: Prompt layout follows the server's prefix cache

- **Status:** Accepted (plan O.3/AA, 2026-10-18); extended by BA and BJ
- **Decision:**
  - Byte-stable content comes first: system prompt, tool list and the
    environment contract.
  - Project memory is taken once per stage visit and stays byte-stable.
  - Changes are named in a note at the end of the request.
  - The conversation is append-only.
- **Rationale:** on a one-slot local server, any change near the start of a
  request re-reads the whole history. The cached share measured 0.73 on the
  medium run. Frontier guidance (Anthropic prompt caching, Claude Code's
  static/dynamic split, llama.cpp `--cache-reuse`) all use this layout.

## ADR-0012: S3-compatible object storage is SeaweedFS; MinIO is dropped

- **Status:** Proposed (2026-10-20; plan [OS](improvement-plan.md#plan-os))
- **Context:**
  - MinIO's community edition is archived and source-only, and its free tier is not open source.
  - The compose `minio` service was already commented out, so the Local backend keeps the "durable copy" on the same volume as the workspaces.
- **Options considered:**
  - SeaweedFS (Apache-2.0)
  - RustFS (Apache-2.0, GA 2026-09)
  - Garage (AGPL-3.0)
  - Ceph RGW
  - MinIO AIStor Free
- **Decision:**
  - SeaweedFS in single-process `weed mini` mode, as an opt-in compose profile on a bind mount.
  - The code keeps speaking plain S3 through boto3, so the backend stays replaceable by configuration.
- **Rationale:**
  - It is permissively licensed, mature and actively released, a one-command single-node deployment, and strong with many small objects (archived workspaces).
  - RustFS is too new and had critical CVEs in Dec 2025 and Jul 2026.
  - Garage lacks versioning and object lock and needs a CLI bootstrap.
  - Ceph is too heavy for one host.
- **Security impact:** an empty secret puts SeaweedFS in allow-all mode, so the app must refuse an S3 endpoint with empty credentials, and the admin UI is bound to loopback.
- **Consequences:**
  - One more container and roughly double the disk for archived output.
  - Rollback is unsetting `OBJECT_STORE_BUCKET`.
  - RustFS is to be re-evaluated around Q2 2027.
- **Validation evidence:** research [R8](research-findings.md#r8); the OS.0 spike result goes here when Accepted.

## ADR-0013: Agents communicate through harness-owned records, not peer messages

- **Status:** Proposed (2026-10-20; plan [CM](improvement-plan.md#plan-cm))
- **Context:**
  - About 11 of 15 traced failures were one agent missing a fact another agent or the harness already had.
  - Builders' `decisions` and `blockers` reach only the milestone reviewer.
  - The local server has one or two slots, and per-request budgets are already saturated.
- **Options considered:**
  - a peer mailbox or chat between agents;
  - debate or negotiation rounds;
  - broadcasting reasoning;
  - harness-written typed records routed by role, plus a bounded question tool.
- **Decision:**
  - Information moves between agents only as harness-written, typed, role-sliced and budgeted records (ADR-0010 measurement applies).
  - Agents may ask the specification a bounded number of questions, answered by retrieval first.
  - Reviewers keep a clean context.
  - No peer messaging between agents.
- **Rationale:**
  - CooperBench measured no gain from real-time messaging between coding agents.
  - MAST found protocol fixes insufficient on their own.
  - Sequential, tool-heavy work degrades under multi-agent coordination.
  - Debate's gains are mostly voting.
  - Structured hand-off (MetaGPT) and controller-mediated blackboards hold up.
- **Consequences:** Pillar 9 is built as CM.2. Prompt growth is capped under BJ, and any item that raises tokens per accepted criterion by more than 5% without lowering a defect metric is switched off.
- **Validation evidence:** research [R7](research-findings.md#r7); A/B results go here when Accepted.

## Decision Log Template

### ADR-XXXX: <Decision Title>

- **Status:** Proposed | Accepted | Superseded | Rejected
- **Date:** YYYY-MM-DD
- **Context:**
- **Constraints:**
- **Options considered:**
- **Decision:**
- **Rationale:**
- **Security and privacy impact:**
- **Operational impact:**
- **Consequences and trade-offs:**
- **Validation evidence:**
- **Supersedes or related decisions:**
