# DevFlow — the Product Development Workflow harness

> **Read this first.** One document that explains the whole product: what it is, how
> it is built, how it works end to end, what is done, what is next and what is
> deliberately not done. Facts here were taken from the code on 2026-10-04
> (branch `harness-hardening-session`, around commit `467872b`). Where a detail
> matters, the module that owns it is named so you can verify it.

---

## 1. What it is, in one paragraph

DevFlow is a **multi-agent software-development harness**. A person gives it a
**product brief** (a Markdown document describing a product). The harness runs a
simulated software company of LLM agents - product manager, architect, reviewers,
QA, scrum master, technical lead, specialist developers, security reviewer - that
turns the brief into a **working, tested product** in its own git workspace,
sprint by sprint, and hands it over with CI and deployment files. It runs in two
modes: **auto mode**, where the harness makes and records every decision and
review itself and finishes development and testing unattended; and **approval
mode**, where a person is asked at the review points they chose and the run
continues from their decision. It is technology-agnostic by design: what is
specific to a language or framework lives only in **stack packs** and **plugin
instructions**, never in the core.

| | |
|---|---|
| Input | a product brief (Markdown, optionally with an uploaded codebase or git repository to build on) |
| Output | a git repository: the product, its unit tests, a locked acceptance suite, generated documents (`docs/`), decision log, sprint records, evidence pages, CI workflow, container files for services |
| Users | an operator/reviewer through a web UI (React) and an HTTP API |
| Models | any OpenAI-compatible server (self-hosted e.g. LM Studio, vLLM, llama.cpp, or hosted), Anthropic, Gemini; a second **judgement model** optional for the judging stages |
| Runs on | Docker Compose: FastAPI app, Celery worker, Postgres, Redis |
| Judged by | benchmark briefs with **hidden tests** the harness never sees (`benchmarks/`) |
| Repository | `https://github.com/marunsct/DevFlow` (package `product-development-workflow`) |

---

## 2. System architecture

```
                         ┌──────────────────────────────────────────────┐
  Browser (React UI) ───▶│  app  (FastAPI, uvicorn)                     │
  langchain-ui/          │  /api/auth  /api/runs  /api/settings         │
                         │  /api/health  /metrics  + serves the UI      │
                         └───────┬───────────────────────┬──────────────┘
                                 │ enqueue run           │ read state, events
                                 ▼                       ▼
                         ┌──────────────┐        ┌──────────────────────┐
                         │ Redis        │        │ Postgres             │
                         │ Celery broker│        │ runs, users, audit,  │
                         │ + event bus  │        │ runtime settings,    │
                         └──────┬───────┘        │ plugin instructions, │
                                │                │ model profiles,      │
                                ▼                │ LangGraph checkpoints│
                         ┌───────────────────────┴──────────────────────┐
                         │ worker (Celery task execute_workflow_run)    │
                         │  LangGraph StateGraph  ──▶ agents (deepagents│
                         │  (app.graph.workflow)      create_deep_agent)│
                         │        │                       │ tools        │
                         │        ▼                       ▼              │
                         │  harness checks          SandboxExecutor      │
                         │  (acceptance, CI,        (argv only, no shell,│
                         │   language services)      allowlists, rlimits)│
                         │        │                       │              │
                         │        └──────▶ workspace (git repo per run) ◀┘
                         │                 DATA_DIR/workspaces/<tenant>/… │
                         └───────────────────────┬──────────────────────┘
                                                 │ chat completions
                                                 ▼
                                   Model server(s): default model
                                   (+ optional judgement model)
```

| Component | Code | Role |
|---|---|---|
| Web UI | `langchain-ui/` (React 19, Vite, Tailwind, TS) | Start runs (brief upload, mode, review toggles), watch progress (WebSocket), answer approvals and reviews, browse artifacts, delivery panel (decisions, evidence), settings |
| API server | `src/app/server/api.py`, `runs.py`, `settings.py`, `auth.py`, `progress.py` | REST + WebSocket; JWT auth with roles (`admin`, `operator`) and tenants |
| Run orchestration | `src/app/server/runner.py`, `tasks.py` | Create/start/resume/cancel runs, concurrency limit, cost ceiling, orphan recovery |
| Workflow graph | `src/app/graph/` | The company: stages, routing, gates, retries, escalation |
| Agents | `src/app/agents/` | Role prompts, structured outputs (Pydantic), middleware (context, digest, guards) |
| Tools | `src/app/tools/` | Repository read/write/edit tools, sandboxed command execution, journal |
| Analysis | `src/app/analysis/` | Parsers, language services, cross-file checks, file kinds, project memory |
| Acceptance | `src/app/acceptance/` | Criteria, suite lock, JUnit parsing, harness-run suite |
| Stack packs | `src/app/stacks/` | Per product kind × language: scaffold, commands, kept files, guides, release files |
| CI | `src/app/ci.py`, `src/app/graph/engineering.py` | Snapshots, regressions, fix guard (revert), code review |
| Delivery | `src/app/graph/delivery.py`, `src/app/stacks/release.py` | Release gate, evidence, change requests, CI/container files |
| Decisions | `src/app/decisions.py` | Decision records (DR-n) in state and `docs/decision_log.md` |
| Models | `src/app/models/` | Client construction, router/fallback, judgement model, endpoint kind, probes |
| Plugins | `src/app/plugins/` | Framework instructions injected per selected stack (seed + store); a key's runner-setup notes (`<key>:setup`) are left out where a stack pack set the project up |
| Observability | `src/app/observability/` | Transcripts (every model/tool call), metrics, cost tracking |
| Benchmarks | `benchmarks/`, `scripts/bench/score.py` | Briefs with hidden tests; scoring |
| Improvement loop | `scripts/loop/loop.sh`, `docs/HANDOVER.md`, `docs/monitoring-handover.md` | Operating the harness on benchmarks, auditing, deploying |

---

## 3. The workflow (what a run does)

```
 product_manager ─▶ [user_review_product_intake] ─▶ tools_models ─▶ stack_selector
        │
        ▼
 principal_architect ◀──▶ architecture_review ─(converges)─▶ [user_review_specification]
        │  (never converges ─▶ escalation[design]: auto builds from latest spec, risks recorded)
        ▼
 scaffold (stack pack: write files, install, prove smoke tests, write contract)
        ▼
 acceptance_author (QA writes tests per criterion) ◀──▶ acceptance_review (mechanical checks + QA lead)
        ▼ LOCK the suite                                [user_review_acceptance]
 scrum_master (sprints = vertical slices, each owns criteria AC-n)
        ▼
 ┌──────────────── per sprint ─────────────────────────────────────────────────┐
 │ technical_lead (work orders; definition of ready)  ── or: sprint already done │
 │   ▼                                                    (criteria pass) ─▶ accept│
 │ specialist_dispatch ─▶ specialist_worker ×N (parallel or linear) ─▶ gather    │
 │   ▼                                                                          │
 │ ci_gate (commit batch; unit+acceptance; regressions; IDE-grade diagnostics)  │
 │   ▼                                                                          │
 │ code_review (senior reviewer reads the diff)                                 │
 │   ▼                                                                          │
 │ test_and_triage (harness runs locked suite; test round) ◀─▶ defect_remediation│
 │   (fix guard reverts a fix that breaks what passed; broken locked test ─▶ QA)│
 │   ▼                                                                          │
 │ security_review ─▶ milestone_review (cannot accept red due criteria)         │
 │   ▼ accept (decision)  /  revise  /  re-plan  /  escalation                   │
 │ [user_review_sprint] ─▶ sprint_advance  (or change_request ─▶ QA ─▶ re-plan)  │
 └──────────────────────────────────────────────────────────────────────────────┘
        ▼ last sprint
 release (every non-deferred criterion passes; CI + container files added) ─▶ [user_review_release] ─▶ complete
```

`[user_review_*]` nodes only pause when that review point is switched on for the
run; otherwise the harness decides and records a decision. Every node routes by
the `stage` value it returns (`_route_from_stage`), so any node can hand on to
any other (escalation, failure, change request).

### Stage table

| Stage (node) | Who | Model | Produces / does |
|---|---|---|---|
| `product_manager` | Product Manager | default | `product_intake` (requirements, success measures, constraints) → `docs/product_intake.md` |
| `tools_models` | Tools & Models Architect | default | technology comparison → `docs/tools_and_models.md` |
| `stack_selector` | Stack Selector | default | `technology_stack` (language, frameworks, testing, product kind) → picks a **stack pack** |
| `principal_architect` | Principal Architect | judgement | technical specification → `docs/technical_specification.md` |
| `architecture_review` | Senior Architect Reviewer | judgement | approve / changes; ≤ 6 revisions, then escalation (design) |
| `scaffold` | harness | — | writes the pack's files, installs, runs its unit + acceptance smoke tests, writes `.harness/stack-pack.json` |
| `acceptance_author` | QA engineer (testing specialist) | judgement | acceptance tests, ≥1 per criterion, test names carry `[AC-n]` |
| `acceptance_review` | harness + QA lead | judgement | mechanical checks (coverage, runs, tests broken by own code, locators nobody sees, undefined assertions), then reviewer; ≤ 3 rounds; then **lock** |
| `scrum_master` | Scrum Master | default | sprint plan; harness assigns every criterion to exactly one sprint |
| `technical_lead` | Technical Lead | default (judgement on retries) | milestone plan of **work orders** (files, interfaces, steps, test cases, verification); definition of ready |
| `specialist_worker` | ui_ux, backend, database, testing, documentation, security_reliability | default (judgement on retries) | code and unit tests for one work order |
| `ci_gate` | harness | — | commits batch; unit + acceptance snapshot; regressions vs last accepted **and** last measurement; language-service findings → defects |
| `code_review` | senior engineer | judgement | diff vs work orders; blocking/major → defects (later-sprint criteria excluded) |
| `test_and_triage` | test engineer + harness | judgement | harness runs the locked suite; round reports defects; ≤ 3 remediation attempts |
| `defect_remediation` | owning specialist | judgement | one fix per defect; reverted if it breaks what passed |
| `security_review` | Security Reviewer | judgement | findings |
| `milestone_review` | Milestone Reviewer | judgement | accept / revise (≤ 3) / block; gate refuses red due criteria |
| `sprint_advance` | harness | — | Sprint Record, carried-forward items, next sprint |
| `change_request` | harness | — | a reviewer's change → `CR-n` with its own acceptance test, then re-plan |
| `escalation` | harness or person | — | last rung: decide (defer criteria / build from latest design) or ask; ≤ 3 per run |
| `release` | harness | — | release gate (≤ 2 holds) + CI/container files + evidence page |

### Escalation ladder (how stuck work is resolved)
fix → fix again → re-plan the sprint → re-plan on the judgement model →
**escalation**: auto mode defers what fails (if no more than half the criteria
would be undelivered) or builds from the latest design with risks recorded;
approval mode asks the person (`escalation` review point). A run that cannot
deliver most of its criteria is stopped rather than shipped.

---

## 4. Core concepts (glossary)

| Term | Meaning |
|---|---|
| **Run** | One execution of the workflow on one brief; id `run-<uuid>`; a LangGraph thread checkpointed in Postgres |
| **Workspace** | The run's own git repository: `DATA_DIR/workspaces/<tenant>/workspace-<run-id>/` |
| **Project directory** | The product's folder inside the workspace (pinned in `.project-directory`) |
| **Stack pack** | A product kind × language bundle: scaffold files, install/unit/acceptance commands, JUnit report paths, kept files, guides, check families, runtime (`browser`/`node`/`both`), release files. Packs: `browser-javascript`, `browser-react`, `node-http-api`, `fullstack-node`, `python-http-api`, `python-cli`, `python-library` |
| **Project contract** | `.harness/stack-pack.json`: which pack, commands, paths; the harness puts back kept files/scripts a stage changed |
| **Kept files** | Test setup the harness owns (e.g. `playwright.config.js`, `playwright.setup.mjs`, `test-setup.mjs` - a jsdom page for browser unit tests - `scripts/serve.mjs`, `pytest.ini`, `acceptance/conftest.py`); refused to agents, marked in the digest |
| **Acceptance criteria** | `AC-1..n`, numbered from the brief (features + acceptance criteria) or the intake |
| **Acceptance suite** | QA's tests for the criteria, **locked** (checksums + snapshot in `.harness/`) after review: the definition of done. Only QA, via a recorded reopen, may change it |
| **Due criteria** | The criteria a sprint must leave passing: its own plus every earlier sprint's (the last sprint answers for all) |
| **Work order** | One delegated task: role, title, description, files, interfaces, steps, edge cases, test cases, verification |
| **Definition of ready** | Mechanical check on a plan before dispatch (files named, test cases, testing order when behaviour changes, no harness-owned files, carried-forward decisions) |
| **Test round / defect** | A test engineer's round over the sprint; each defect has severity, owner, reproduction |
| **Fix guard** | A fix is measured before/after; one that breaks a passing test is reverted |
| **Decision record** | `DR-n`: point, question, options, decision, rationale, decided_by (`auto`/`user`), affects; in state, `docs/decision_log.md`, API |
| **Review point** | A place a person may be asked: `product_intake`, `technical_specification`, `acceptance_tests`, `sprint`, `release`, `escalation` |
| **Change request** | `CR-n`: a reviewer's requested change, given its own acceptance test |
| **Deferred criterion** | A criterion deliberately not delivered, with a recorded reason (escalation) |
| **Sprint Record** | Per-sprint summary: backlog and outcome, defects, findings and dispositions, carried forward, lessons (`app.sprint.record`) |
| **Judgement model** | Optional stronger model for the judging stages and retries (`JUDGEMENT_*` settings) |
| **Harness run** | A command the harness runs itself (scaffold, suite, CI): never withheld by agent repeat guards (`sandbox._FOR_THE_HARNESS`) |

---

## 5. Modes and controls

- **Auto mode** (default; all review toggles off, `autoApprove` on): every gate
  is decided by the harness and recorded as a decision; no human input needed.
- **Approval mode**: the run's `review_policy` turns on review points; at each
  the run pauses (`awaiting_user_review:<point>`) with a review page; the person
  approves, requests changes (becomes a revision or a change request), or skips.
- **Write approvals**: with `auto_approve` off, each `write_artifact`,
  `edit_artifact`, `replace_lines`, delete/move pauses for approval (`HUMAN_APPROVAL_TOOLS`).
- **Execution mode** (setting `execution_mode`): `linear` (one specialist at a
  time) or `parallel` (LangGraph `Send` fan-out of work orders; file ownership
  per work order is enforced).
- **Thinking**: `thinking_mode` (`default`/`on`/`off`) and `thinking_effort`;
  replies that spend the whole output budget reasoning are retried without reasoning.

---

## 6. Agents, tools and context

- **Construction**: every role is `create_role_agent` → `deepagents.create_deep_agent`
  with a bounded tool set, the built-in filesystem tools denied, structured
  output (Pydantic schema per role), and a middleware chain: summarisation
  (context compaction), workspace digest injection, plugin instructions,
  repeat/notice guards, settled-answer recovery, text-tool-call parsing.
- **Tools** (as the model sees them; built in `app/tools/agent_toolkit.py` and
  `app/agents/workspace_backend.py`): reads `read_file`, `ls`, `grep`, `glob`;
  writes `write_artifact`, `edit_artifact` (find/replace), `replace_lines` (by line
  range), `delete_artifact`, `move_artifact`; commands `run_validation` (tests in
  the project) and `run_terminal_command`; `read_command_output` (a long output by
  reference); `changed_since_sprint`. Which tools a role gets depends on the role.
- **Workspace digest**: every model call carries a map of the workspace (files,
  line counts, purpose line, interface), marking harness-owned files.
- **Project memory**: per-file purpose/interface/last writer, so later stages need
  not re-read files.
- **Context budget**: window-relative budgets (`app/agents/context_budget.py`),
  compaction when ~80% full, per-tool output caps.
- **Plugin instructions** (`app/plugins/`): framework-specific advice injected for
  the selected stack; unknown frameworks get instructions generated once and stored.
- **Document templates** (`app/doc_templates/`): every workflow document is
  rendered from the stage's structured response by Jinja templates, so output
  shape does not depend on the model.

---

## 7. Safety and guards

**Sandbox** (`app/tools/sandbox.py`): commands are argv lists, never shell
strings; the executable must be in the role's allowlist (role set ∪ the toolchain
of every language the stack names); interpreter escapes (`python -c`, `node -e`,
`npm exec`, …) refused; servers refused with advice (the acceptance config starts
the product); resource limits (memory, CPU, processes, file size), minimal
environment, a free `ACCEPTANCE_PORT` per command; timeouts scaled per toolchain.
Modes: `container` (separate container per command; needs a runtime socket, which
is root-equivalent on the host) or `in-container` (inside the worker with rlimits).
Execution is opt-in: Compose defaults to `ALLOW_COMMAND_EXECUTION=false` and
`SANDBOX_EXECUTION_MODE=container`; this deployment's `.env` sets `true` and
`in-container`. Fails closed. **Run readiness:** each worker records at startup
whether it can run commands (`app/server/execution_readiness.py`), and a run is
refused before its first model call when it cannot, naming the setting to change.

**Repository write guards** (`app/tools/repository.py`): paths stay inside the
workspace and project; `docs/` holds only workflow-rendered documents; the locked
suite, `.harness/` and kept files are refused; a file is refused if its language's
parser rejects it (see §8); leaked model control tokens refused; work-order file
ownership in parallel mode; repeat-read withholding; stale-edit detection.

**Auth & tenancy**: JWT access/refresh tokens, roles, per-tenant runs and
workspaces, audit log; provider API keys encrypted at rest (Fernet); hosted vs
self-hosted model endpoints treated differently (`app/models/endpoints.py`).

**Run bounds**: `MAX_CONCURRENT_RUNS`, `MAX_RUN_COST_USD` (pauses naming the spend),
cooperative cancellation at every node, gate and recursion limits.

---

## 8. How the product is known to work (verification layers)

| Layer | When | How |
|---|---|---|
| Syntax | every write/edit | the language's own parser: Python `ast`, `json`, stdlib TOML/YAML/XML, `node --check` (JS), TypeScript compiler parser (TS/JSX), tree-sitter grammars measured exact (Java, Go, Rust, Ruby, PHP, Lua), CSS grammar; brace count only for SCSS/LESS and unmeasured C-family languages. Broken file → **refused** |
| IDE diagnostics | every write/edit (note); CI gate (defect) | TypeScript language service (JS/TS) and Pyright (Python): only run-time failures — undefined names, imports of missing exports/modules (`app/analysis/language_service.py`) |
| Unit tests | work orders, test rounds, CI | the pack's unit command (e.g. `node --test`, pytest) with JUnit reports |
| Acceptance suite | locked before building; run by the harness every round, at CI, at acceptance, at release | the pack's acceptance command (Playwright, pytest+httpx, …); per-criterion results; page check records the page's uncaught errors and accessibility tree; each failing test carries the page it failed on |
| Suite integrity | before lock and after | tests broken by their own code, locators nobody sees, assertions the runner does not define → back to QA; after lock, repaired via recorded reopen (≤ 2) |
| CI regressions | each batch, each fix | snapshot vs last accepted and last measurement; regressions become defects; a regressing fix is reverted |
| Reviews | per batch / sprint | code review, security review, milestone review (findings about later sprints' criteria made minor) |
| Release gate | end | every non-deferred criterion passes |
| Benchmarks | per loop run | hidden tests the harness never sees; score = share passed; a finished run that fails hidden tests is a **false acceptance** (`scripts/bench/report.py`); `scripts/bench/mutate.py` measures the locked suite by breaking the product |

### Support tiers (what a run can promise)

"Technology-agnostic" is the design, not a measured claim. Each run's stack
decision states its tier (`app.stacks.support_tier`):

| Tier | Meaning | Stacks | Measured by a benchmark |
|---|---|---|---|
| **Pack-supported** | the pack's scaffold, install and test commands, and release files (CI; a container definition for a service) | every pack: `browser-javascript`, `browser-react`, `python-http-api`, `node-http-api`, `python-cli`, `python-library`, `fullstack-node` | yes: `web-todo`, `web-todo-react`, `notes-api`, `notes-api-js`, `wordstats-cli`, `textkit-lib`, `fullstack-bookmarks` (each reference scores 100%). No pack has yet passed the loop's gate |
| **Custom stack** | no pack fits: the agents choose the setup and test commands, the locked suite runs on those, and the release has no packaged CI or container files (the release decision says so) | anything else | no |

A custom-stack run still reaches release only when its locked acceptance suite
passes, so a product that was never tested is never handed over as finished. How
well that suite tests the brief is unmeasured outside the benchmarks. Support
grows by adding and measuring packs, not by widening generic checks.

---

## 9. Data and storage

- **Postgres**: `runs` (status, stage, review policy, owner, tenant, cancel flag, model overrides), `users`, `audit_log`, runtime settings & encrypted secrets, plugin instructions, model profiles, LangGraph checkpoint tables (`PostgresSaver`).
- **Redis**: Celery broker; run event stream for the UI.
- **`DATA_DIR` (`/app/data`)**: `workspaces/` (per run), `transcripts/<run>.jsonl` (every model request/response, tool call/result, post-middleware), `ledger/` (every command run: argv, dir, category, exit, duration, who ran it), `journal/`, `context/`, `objects/`, `uploads/`, `prometheus/`.
- **Inside a workspace**:
  - `<project>/` — the product, its tests, the kept test setup;
  - `docs/` — rendered documents (`product_intake`, `tools_and_models`, `technology_stack`, `technical_specification`, `architecture_review`, `sprint_plan`, `milestone_plan`, `security_review`, `milestone_review`, `sprint_N_summary`), `acceptance_criteria.md`, `decision_log.md`, `reviews/*.md` (review pages, `sprint-N-evidence.md`, `release-evidence.md`);
  - `.harness/` (hidden from agents, git-ignored) — `stack-pack.json`, `acceptance.json` (criteria, lock, deferrals, change requests), `acceptance-snapshot/`, `acceptance-result.json`, `ci.json`;
  - `.github/workflows/<project>.yml` and, for services, `<project>/Dockerfile` + `.dockerignore` — added at release.
- **Deleting a run** (`DELETE /api/runs/{id}`, terminal runs only) removes its row,
  workspace, checkpoints, events, uploads no other run shares, transcript, ledger,
  journal entries, and the object store's copies (`runs/<id>/`, `uploads/<name>`).
  Kept: the audit-log line naming who deleted it, and the per-agent compaction
  context (ages out). `RUN_DELETE_KEEPS_RECORDS=true` holds the transcript, ledger
  and journal for an audit trail (`app/server/run_retention.py`). Runs that are never
  deleted are kept indefinitely; the journal alone ages out
  (`CTX_JOURNAL_RETENTION_HOURS`).

---

## 10. API and UI

- **Auth**: `POST /api/auth/token`, `POST /api/auth/refresh`, `GET /api/auth/me`.
- **Runs** (`/api/runs`): `POST ""` create (brief), `POST /{id}/codebase` (seed upload or git URL), `POST /{id}/start`, `/resume`, `/clone`, `/cancel`, `DELETE /{id}`; `GET ""`, `/{id}`, `/{id}/wizard`, `/stages`, `/artifacts`, `/artifacts/download`, `/logs`, `/decisions`, `/evidence`; approvals `GET|POST /{id}/approval`; reviews `GET|POST /{id}/review`; events `POST /{id}/events/ticket`, `WS /{id}/events/stream`, `GET /{id}/events`, `/status`.
- **Settings** (`/api/settings`): `GET`, `PUT`, `POST /detect-context-window`, `GET /models`, `DELETE /models/{id}`.
- **Health/metrics**: `/api/health`, `/api/health/ready`, `/api/health/models`, `/metrics`.
- **UI pages**: Login, Home (new run: brief, review toggles, auto-approve), RunList, RunDashboard (wizard, execution flow, agent activity, approval gate, review panel, artifacts, sprint summary, delivery panel, logs), Settings (models, judgement model, thinking, execution mode).

---

## 11. Configuration

Runtime settings (editable in the UI, stored in Postgres, override env):
`llm_provider` (`local`/`openai`/`anthropic`/`gemini`), `openai_base_url`,
`model_name`, `model_context_window`, `model_max_output_tokens`, `thinking_mode`,
`thinking_effort`, `execution_mode`, `judgement_provider`, `judgement_base_url`,
`judgement_model_name`, `judgement_context_window`, and API keys
(`openai`/`anthropic`/`google`/`judgement`). Notable environment variables:
`DATA_DIR`, `CHECKPOINTER_TYPE` (postgres), `SANDBOX_EXECUTION_MODE`,
`SANDBOX_MEMORY_LIMIT`, `CELERY_CONCURRENCY`, `MAX_CONCURRENT_RUNS`,
`MAX_RUN_COST_USD`, `WORKFLOW_MAX_ARCHITECTURE_REVISIONS`,
`WORKFLOW_MAX_STRUCTURED_RETRIES`, `OPENAI_ENDPOINT_KIND`, `ALLOWED_MODEL_HOSTS`,
`JWT_SECRET_KEY`, `SETTINGS_ENCRYPTION_KEY`.

---

## 12. Technical specifications

| Item | Value |
|---|---|
| Language/runtime | Python ≥ 3.12 (worker 3.12); Node 20 in the image |
| Core libraries | LangGraph (+ Postgres checkpointer), LangChain core/OpenAI/Anthropic/Google, deepagents, FastAPI, Celery, Redis, psycopg 3, Pydantic 2, Jinja2, tree-sitter-language-pack |
| Image tools | TypeScript 6.0.3 and Pyright 1.1.414 (global, for parsing and language services), Playwright 1.63.0 + Chromium (cached in the image) |
| Frontend | React 19, Vite 8, Tailwind 4, TypeScript |
| Default model (current deployment) | set by the owner in Settings and changed often; as of 2026-10-05 `AtomicChat/Ornith-1.5-35B-A3B-GGUF` on `host.docker.internal:8888`, no judgement model set |
| Size | ~72k lines in `src/app`; ~490 test files, ~8,800 tests |
| Limits | architecture revisions 6; acceptance rounds 3; milestone revisions 3; remediation attempts 3; structured retries 2; release holds 2; suite repairs 2; escalations 3 |
| Workflow graph | 33 nodes; state is a `TypedDict` of about 64 keys (`WorkflowGraphState`) |

---

## 13. Repository layout

```
src/app/
  graph/        workflow.py (graph, nodes, routing, gates), acceptance_nodes.py,
                engineering.py (CI, code review, fix guard), delivery.py (release,
                change requests, evidence), escalation.py, checkpointing.py
  agents/       one module per role + role_agent.py (construction), specialists.py,
                context/digest/memory middleware, thinking, settled answers
  tools/        repository.py (file tools + guards), sandbox.py, agent_toolkit.py, journal.py
  analysis/     grammar_parse, javascript_parse, typescript_parse, syntax_balance,
                language_service, integration_checks, file_kinds, project_memory,
                work_orders, local_imports, test_discovery, document_manifest
  acceptance/   criteria.py, suite.py, junit.py, requests.py
  stacks/       __init__.py (StackPack), packs/*.py, scaffold.py, contract.py, release.py
  models/       client construction, endpoints.py, roles.py (judgement), probes, router
  server/       api, runs, settings, auth, progress, runner, tasks, run_store, workspaces, …
  plugins/      middleware, registry, seed.py
  observability/ transcript, metrics, cost_tracker, transcript_metrics
  sprint/       record.py (Sprint Record)
  doc_templates/ Jinja templates for every workflow document
  ci.py  decisions.py  documents.py  state.py  config.py  main.py (CLI)
langchain-ui/   React frontend
tests/          pytest suite (host); brief_low/medium/high.md
benchmarks/     web-todo, notes-api, wordstats-cli, textkit-lib, fullstack-bookmarks
scripts/        loop/loop.sh (operate the improvement loop), bench/score.py, audit_run.py
docs/           PRODUCT.md (this), HANDOVER.md, monitoring-handover.md,
                harness-improvement-plan.md, redesign-software-company.md,
                architecture-decisions.md
```

---

## 14. Development and operations

- **Tests**: `scripts/loop/loop.sh suite` (≈3 min). Green = everything passes
  except three `test_codebase_seeding_api.py` tests that need S3 credentials.
  Tests needing the TypeScript compiler or Pyright skip on a host without them
  and run in the worker image.
- **Deploy**: `scripts/loop/loop.sh deploy` (rebuild + restart app and worker;
  stops any live run). Commit and push to `main` remote, branch
  `harness-hardening-session`.
- **Improvement loop**: start a benchmark run (`loop.sh bench web-todo`), audit it
  (transcripts, logs, DB, tool calls), fix technology-agnostically with tests,
  deploy, repeat. A bug in a run's first 40 minutes (or a major bug any time)
  cancels the run. Status and history: `docs/HANDOVER.md`, `docs/monitoring-handover.md`.
- **Benchmark gate** (`benchmarks/README.md`): a run is clean when its product
  scores 100% on hidden tests and needed no harness fix. Stage 1 web-todo ×2
  clean → stage 2 notes-api, wordstats-cli, textkit-lib ×1 each → stage 3
  fullstack-bookmarks ×2 → then `tests/brief_medium.md`, `brief_high.md` by audit.
  **Current: stage 1, 0 of 2** (one run scored 10/10 but needed a fix).
- **Code rules**: no run ids in code, comments, prompts or tests; language/framework
  guidance only in stack packs or `plugins/seed.py`; agent rules phrased
  product-agnostically (tests ban product words); every rule enforced where it is
  broken, not only stated in a prompt; measure before trusting a checker.

---

## 15. Feature status

### Implemented
- Full company workflow (§3) with auto and approval modes, six review points, write approvals, decision records, change requests, escalation ladder (sprint and design).
- Stack packs (7) with proven scaffolds, project contract, kept files, CI and container release files.
- Locked acceptance suite as definition of done; criteria per sprint; release gate; deferrals with reasons; suite integrity checks before and after lock.
- CI per batch with regressions (vs accepted and last measurement), fix guard with revert, code review, IDE-grade diagnostics as defects.
- Harness-run evidence for agents: page check (uncaught errors + accessibility tree), page at each failure, runtime problems first.
- Sprint shortcuts and integrity: a sprint whose criteria already pass is closed without work (first planning only); later-sprint findings never block; criteria ids in any dash.
- Syntax checking by real parsers; language services (TypeScript, Pyright).
- Judgement model tier; hosted vs self-hosted endpoints; thinking control; context budgets and compaction; text tool-call fallback; structured-answer recovery.
- Sandbox with allowlists, limits, harness-run exemption; repository guards; ownership enforcement at plan time.
- Plugin instruction injection; document templates; Sprint Record; work orders with definition of ready; parallel/linear execution.
- Web UI, REST/WebSocket API, auth/tenancy/audit, metrics, cost tracking and ceiling, concurrency limit, orphan recovery, cancellation.
- Benchmarks with hidden tests and scorer; improvement-loop tooling.

### In progress / next
- Reach the benchmark gate: web-todo ×2 clean, then the Python benchmarks and full-stack.
- Small known wastes: the lead often under-counts carried-forward decisions; agents still try `node -e`; empty "verify tests" work orders.
- Owner decisions pending: which stronger **judgement model** to configure; the **CRITERION severity policy** (minor vs blocking grading).

### Deferred (with what would bring each back) — see `docs/harness-improvement-plan.md` §3
- Language analysers beyond the language services (B1) — a defect only a cross-file check would find.
- Measured chars-per-token (B7), digest by budget (B15) — an overflow or a >40-file product.
- Full model profile probe; notice registry refactor.
- Cross-run agent-written memory store — dropped (injection/drift risk; packs hold what is learned).
- Live documentation / dependency probes (needs sandbox egress), full type checking on plain JS (measured noise), task-list middleware (no measured win).
- Building containers in the sandbox (no container runtime): container files are written, not built; CI targets GitHub Actions only.

---

## 16. Where to read next

| Question | Read |
|---|---|
| Current run, deployment, loop status | `docs/HANDOVER.md`, `docs/monitoring-handover.md` |
| Why the company design | `docs/redesign-software-company.md` |
| What was reviewed, fixed, deferred | `docs/harness-improvement-plan.md` |
| Architecture decisions | `docs/architecture-decisions.md` (ADR-0001…0004) |
| The graph itself | `src/app/graph/workflow.py` (`build_workflow_graph`) |
| A stack pack | `src/app/stacks/packs/browser_javascript.py` (+ `_javascript.py`) |
| How a benchmark is judged | `benchmarks/README.md`, `scripts/bench/score.py` |
