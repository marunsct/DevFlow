# DevFlow - the product, completely

This is the one document that explains the whole product: what it is for, how it is built, how it works end to end, how
it is run and how it is measured. Someone who reads only this file should understand the product and its
implementation. Where a detail matters, the module that owns it is named so it can be checked. It describes the code as
it is now; history lives in `docs/archive/` (see [ARCHIVE.md](ARCHIVE.md)). What is live and running now is in
[STATE.md](STATE.md); what is still to build is in [improvement-plan.md](improvement-plan.md); how to run, test and
deploy is in [HANDOVER.md](HANDOVER.md).

**In one paragraph.** DevFlow is a multi-agent software-development harness. A person gives it a product brief. A
simulated software company of language-model agents - product manager, architect, reviewers, QA, scrum master, technical
lead, specialist developers, security reviewer - turns the brief into a working, tested product in its own git
workspace, sprint by sprint. An acceptance suite written from the brief is locked before any code, so "done" is defined
by tests the builders cannot change; the harness then runs, probes and fixes the product until the suite passes, and
hands over the code with a record of what was proven and what was not. It runs on a local model server the owner
provides and in Docker; a run takes one to three hours for a small product.

**Contents**

| Part | Sections |
|---|---|
| Purpose and pipeline | 1 Vision and purpose; 2 The pipeline end to end |
| The agents and what they work on | 3 Agents and roles; 4 State, documents and the workspace; 5 Stack packs and the language table |
| Proving and fixing | 6 Acceptance suite and verification; 7 Fix machinery; 8 Tools; 9 Switches and measurement |
| The system | 10 Architecture and deployment; 11 Server and API; 12 The web UI; 13 Data, records and observability |
| Quality and operation | 14 Quality gates and how the product is measured; 15 Security and safety; 16 Backing services and storage; 17 Operating limits and known gaps; 18 Repository map |

---

## 1. Vision and purpose

### 1.1 What DevFlow is

DevFlow is a multi-agent software-development harness. A person writes a product brief (Markdown, plain text, DOCX, PDF or CSV; optionally with an uploaded codebase or git repository to build on). The harness runs a simulated software company of LLM agents - product manager, architect, reviewers, QA, scrum master, technical lead, specialist developers, security reviewer - and returns a working, tested product in its own git workspace, with its unit tests, a locked acceptance suite, generated documents, a decision log, sprint records, CI and (for services) container files.

The harness is a LangGraph `StateGraph` (`app/graph/workflow.py`, nodes in `app/graph/nodes/`, `acceptance_nodes.py`, `engineering.py`, `escalation.py`, `delivery.py`). Each role is a Deep Agent built by one factory (`app/agents/role_agent.py`). Everything the harness can decide without a model - running tests, parsing files, probing a started product, reverting a bad fix - it decides mechanically. Models write and judge; the harness measures.

### 1.2 Who it is for

| Audience | What they get |
|---|---|
| An operator or product owner | Give a brief, pick a delivery mode and review points, receive a product plus the evidence of why it is done. Auto mode needs no human input. |
| A team taking over the product | A handover pack: the product archive with `HANDOVER.md`, process documents under `docs/process/`, the decision log, the acceptance suite the product was held to (`app/sprint/handover.py`, `app/sprint/product_archive.py`). |
| The harness's maintainers | A measured loop: benchmark briefs with hidden tests, an audit of every run, general fixes, switches measured before they are kept (section 9). |

It is built for self-hosted local models on one GPU first (a 35B mixture-of-experts class model is the measured baseline) and also runs on any OpenAI-compatible server, Anthropic or Gemini. Model plumbing is Part 2.

### 1.3 What "done" means

A run is done when its **locked acceptance suite passes**, not when an agent says so.

1. The criteria `AC-1..n` are read from the brief's own words (`app/acceptance/criteria.py`): its acceptance-criteria section, its features, its interface section line by line. The intake's success measures are the fallback only when the brief states none.
2. QA writes at least one test per criterion (test names carry `[AC-n]`), the harness checks the suite mechanically, a QA lead reviews it, and it is **locked** (checksums plus a snapshot in `.harness/`). Writers cannot change it; only QA, reopened through a recorded decision, can.
3. The harness runs the suite itself and reads the runner's JUnit XML. "Which criteria pass" is the runner's record, never a model's summary.
4. Release requires every non-deferred criterion to pass, the product's own unit tests to pass (or be recorded), a handoff (README with run instructions, an API summary for services), and no secret in the code.

Outside the harness the product is scored by **hidden tests** written by a person from the brief and never shown to any run (`benchmarks/<family>/hidden/`), plus a **quality set** that holds the brief to its edges (`benchmarks/<family>/quality/`: malformed input, concurrent writes, ids that do not exist) and a **handoff score** (README, start script reads `PORT`, CI file, no thinking-aloud comments) from `scripts/bench/score.py`. A finished run whose product fails hidden tests is a **false acceptance**; the false-acceptance rate, not the mean score, says whether a finished run can be handed over unread.

A release is never silently "completed". `completion_gaps` lists what the release knew it did not prove; `app/completion_verdict.py` splits the gaps into ones that mean the product may not work (blocking), scope cuts (a criterion shipped deferred) and notes. Any gap kind not listed as a note or cut blocks.

### 1.4 What is good today, what is experimental

`app/stacks/support_matrix.py` is the one place that states support, from scored runs (hidden tests) on a local 35B-class model: a pack is **supported** with at least 5 scored runs and a mean hidden score of at least 0.90; every other pack is **experimental** (it has a pack, its commands are verified, evidence is too thin). A model whose measured tier is "weak" makes every stack experimental.

| Status | Packs (evidence in `support_matrix.EVIDENCE`) |
|---|---|
| Supported | `python-http-api`, `python-cli`, `python-library`, `fullstack-page-fastapi`, `node-http-api`, `node-hono-native-api`, `browser-javascript`, `browser-react`, `fullstack-node` |
| Experimental | every other pack, including the Go, Rust, Java, C#, PHP and Ruby service packs (fewer than 5 scored runs or a lower mean; Rust/Axum is the weakest on the table) and the Vue, Svelte, Angular, Nest, Django, Next and TypeScript/Go/Rust CLI and library packs |
| No pack | any stack no pack covers is **custom**: an agent sets it up and the harness proves the setup (`app/stacks/custom_setup.py`); the release has no packaged CI or container files and says so |

Experimental also covers the harness's optional switches that are still being measured (section 9), hosted-model tuning and the "premium" bundles. The table in `support_matrix.py` is edited by hand when new scored runs move a stack; `support_matrix.for_the_brief` warns before a run starts when the brief names an experimental language.

### 1.5 Principles

| Principle | Where it is enforced |
|---|---|
| **Tests lock the definition of done.** The suite is written from the brief before anything is built, reviewed, locked, and run by the harness. | `app/acceptance/suite.py`, `app/graph/acceptance_nodes.py`, write guards in `app/tools/repository.py` |
| **Every fix is general.** A fix to the harness is technology-, framework- and product-agnostic, carries a test proven to fail on the old code, and names no run. | repository rules (`AGENTS.md`), unit tests |
| **Stack-specific content lives in three places only:** a stack pack (`app/stacks/packs/`), `app/plugins/seed.py`, and per-language tables (`app/stacks/languages.py`, `app/tools/sandbox.py` tables). Core code and shared prompts know no language. | section 5 |
| **Measure before keeping.** A change whose value is in doubt ships behind a switch, off or measured with two runs per family on and off on one harness commit, and is kept only if no hidden or quality score falls and its target KPI moves. | `app/switches.py`, `docs/measuring.md` (section 9) |
| **Bug fixes and quality changes are always on.** Only optional, non-quality improvements keep a switch. | `app/switches.BUILT_IN` |
| **Harness decides, models propose.** Documents are rendered by templates from structured answers; counts, gates and caps are code. | `app/doc_templates/`, `app/graph/` |
| **One writer of each thing.** The suite is QA's, harness files are the harness's, a work order's files are its specialist's. | section 3.4 |
| **Fail loudly, degrade gracefully.** Every terminal state but a clean release writes a marker into the workspace; a check that cannot run says so instead of failing the product. | `app/graph/terminal_state.py`, `app/observability/degraded.py`, `app/acceptance/unmeasured.py` |

---

## 2. The pipeline end to end

### 2.1 How routing works

The graph has one conditional-edge router. Every node returns a `stage` value naming the next node (or a pause value); `_route_from_stage` (`workflow.py`) sends control there. The set of legal targets is `_NODE_NAMES`; a stage name that is not a node is answered `failed` by `_owning_node`, never a `KeyError`. A node can therefore hand to any other node (escalation, change request, back to QA), which is how every loop below is expressed.

- **Entry router** (`_entry_router`): a fresh run enters at `product_manager`; a resumed run enters the node its checkpointed `stage` names. Iterated inner stages (`specialist_backend_0`, `test_round_2`, `defect_fix_1_0`, `acceptance_author_1`) are mapped back to the node that owns the loop by `_ITERATED_STAGE_OWNERS`.
- **Two kinds of pause**: `awaiting_approval:<stage>` (a role agent's gated tool call, such as a write, needs a human) and `awaiting_user_review:<point>` (an optional review gate). A skip is its own status and never looks like an approval; an optional review can never bypass the mandatory architecture gate.
- **Parallel fan-out** (`execution_mode == "parallel"` in settings): the router returns `Send(...)` objects for `specialist_worker` (work orders), `defect_fix_worker` (a batch of defects) and `review_worker` (reviews). The gather nodes are the only writers of `stage` after a fan-out. Width is `concurrent_requests()` = `HARNESS_MAX_PARALLEL` (default 6) bounded by the model server's slots. **Linear** mode runs one at a time. Work orders that share a file are staggered (`_that_do_not_share_a_file`).
- **Per-node wrapper**: every stage node snapshots the workspace under its stage name before it runs (`_snapshotting`, refs under `refs/harness/stages/`), which is what makes rewind possible (section 4.6). Agent nodes carry a LangGraph `RetryPolicy` (3 attempts, 2 s backoff doubling to 30 s) that does not retry a provider out of quota.
- **Review points** (`review_policy`, opt-in per run): `product_intake`, `technical_specification`, `acceptance_tests`, `sprint`, `release`, `escalation`. With none on, the harness decides each gate and records a decision (`app/decisions.py`).

### 2.2 The graph

```
 product_manager ─▶ [user_review_product_intake]* ─▶ tools_models ─▶ stack_selector
                                                                        │
                                                                        ▼
                                              specialist_consultation (one advisor per entry)
                                                                        │
                                                                        ▼
                      ┌─────────────▶ principal_architect  ◀───── changes_required ─┐
                      │                    │                                         │
                      │                    ▼                                         │
                      │             architecture_review ─────────────────────────────┘
                      │                    │ approved (or findings that do not block)
                      │                    ▼
                      │          [user_review_specification]*
                      │                    ▼
   escalation(design) ┘  (revisions spent)  scaffold  ── unproven twice ──▶ escalation
                                           │
                                           ▼
                                   acceptance_author ◀──┐ send-backs (≤3 rounds, harness checks + QA lead)
                                           ▼            │
                                   acceptance_review ───┘
                                           │ LOCK the suite
                                           ▼
                                  [user_review_acceptance]*
                                           ▼
                                      scrum_master  (sprints = vertical slices, each owns AC-n)
                                           ▼
   ┌───────────────────────────── per sprint ──────────────────────────────────────────────┐
   │ technical_lead ──(criteria already pass)──▶ close the sprint with nothing to build     │
   │   │  (dispute due after a failed attempt) ──▶ acceptance_dispute ─▶ back to the lead   │
   │   ▼                                                                                    │
   │ specialist_dispatch ─▶ specialist_worker ×N ─▶ specialist_gather                       │
   │   ▼   (fast delivery: files drafted from the specification first)                      │
   │ ci_gate ─▶ code_review ─▶ test_and_triage ◀──────────────┐                             │
   │                               │ defects                  │ next test round             │
   │                               ▼                          │                             │
   │                       defect_remediation ─▶ (fix guard, revert, best checkpoint) ──────┘│
   │                               │ attempts spent ──▶ re-plan (technical_lead)             │
   │                               │                    ≥ limit ──▶ escalation               │
   │                               ▼ all clear                                              │
   │ security_review ─▶ advice_review ─▶ milestone_review                                   │
   │       (or review_worker ×N ─▶ review_gather)     │ revise ─▶ technical_lead (≤3)       │
   │                                                  ▼ accept                              │
   │                         [user_review_sprint]* ─▶ sprint_advance ─▶ next sprint         │
   └────────────────────────────────────────────────────────────────────────────────────────┘
                                           ▼ last sprint accepted
                                        release ──── held (≤2) ──▶ technical_lead
                                           ▼
                                [user_review_release]* ─▶ complete
   escalation ─▶ (auto) defer criteria and go on / build from latest design / failed
              ─▶ (asked) user_review_escalation ─▶ escalation_accept | escalation_retry
   change_request (a reviewer's change, CR-n) ─▶ acceptance_author ─▶ lock ─▶ technical_lead
   * = pauses only when that review point is switched on for the run
```

### 2.3 Models by stage (summary)

`GraphContext` (`app/graph/context.py`) carries four models: `model` (default), `planning_model`, `judgement_model`, `building_model`. With no judgement model configured, all four are the default. Planning stages (intake, tools, stack, sprint plan, work orders) run on `planning_model`, which is the judgement model when `PLAN_ON_JUDGEMENT_MODEL` is on (default) and delivery is thorough. Judging stages (architect, architecture review, QA lead, test rounds, fixes, code, security and milestone reviews, dispute) run on `judgement_model`. Building stages use `ctx.the_build_model(...)`: the default model (reasoning off in fast delivery), escalating to the judgement model after `ESCALATE_AFTER_ATTEMPTS` (default 2) failed fixes or restarts, after a reverted fix, or on any retried sprint (`the_model_for_this_attempt`: a re-plan, two milestone revisions, a held release or a sprint escalation; design escalations do not count). Details: section 3.3.

### 2.4 Stage reference

For each stage: owner module, what it reads, what it writes, how it fails and where control goes. "Failed" means the `failed` node (`closing.failed_node`), which always records a reason and writes the workspace's terminal marker.

| # | Stage (node) | Owner | Purpose | Inputs | Outputs | Failure and next |
|---|---|---|---|---|---|---|
| 1 | `product_manager` | `nodes/planning.py`, `agents/product_manager.py` | Turn the brief into a structured intake | brief text, repository context | `product_intake` (requirements, success measures, constraints, workflows, open questions); `docs/product_intake.md`; project directory pinned (`.project-directory`) | No structured answer: restart on a fresh conversation (`WORKFLOW_MAX_STRUCTURED_RETRIES`, default 2), then failed. The harness then puts back what the brief states and the model dropped (`with_the_constraints_the_brief_states`, `with_the_measures_the_brief_states`, `with_the_workflows_its_measures_require`, deferrals touching required scope). Next: `tools_models`, or the intake gate when its review is on or `INTAKE_ASKS_FIRST` finds open questions a person answers. |
| 2 | `tools_models` | `nodes/planning.py`, `agents/tools_models.py` | Evidence-based comparison of frameworks, storage, providers | intake | `docs/tools_and_models.md`; the sandbox pins every language the stack names (`pin_project_stack`) | A missing intake sends control back to `product_manager` (bounded), then failed. Next: `stack_selector`. |
| 3 | `stack_selector` | `nodes/planning.py`, `agents/stack_selector.py`, `app/stacks/__init__.py` | One technology stack and the stack pack that fits | intake, tools, the brief's own constraint lines, the list of supported stacks | `stack_selection` (language, framework, testing framework, product kind), `stack_pack` (or None), `docs/technology_stack.md`. A page product that names no browser runner is corrected to one (`the_browser_runner_this_stack_forgot`). | Next: `specialist_consultation`. No pack fits: the stack is custom (section 5.7). |
| 4 | `specialist_consultation` | `nodes/planning.py`, `agents/specialist_advice.py` | One structured answer per needed specialist before the specification: UI/UX when there is an interface, database when it keeps data, backend when it serves requests, security and reliability when it serves requests or handles sign-in, personal data, money or files, testing when there are criteria | brief, intake, stack | `specialist_advice[role]`, items numbered `UX-n`, `DB-n`, `BE-n`, `SR-n`, `TS-n` | One advisor per visit, looping on itself until all are asked. Next: `principal_architect`. |
| 5 | `principal_architect` | `nodes/specification.py`, `agents/principal_architect.py`, `graph/specification_parts.py`, `agents/research_brief.py` | Technical specification and ADRs; adopts or declines every advice item; writes `interface_design` for products with an interface and an `interface_contract` (one strict line per route, control or command, each naming its criterion) | intake, tools, stack, advice, scaffold layout, naming standard, the harness's pre-read of registries and docs (`research_notes`), prior review findings | `technical_specification`, `docs/technical_specification.md` (rendered), `architect_research` kept for retries | Sections left empty are re-asked (`MAX_SPECIFICATION_REPAIRS` = 2); layout and startup problems repaired in place. In fast delivery the core is written first and the other sections at once in parts (`specification_parts`), and a revision rewrites only the sections the review touched. Next: `architecture_review`. |
| 6 | `architecture_review` | `nodes/specification.py`, `agents/architecture_reviewer.py` | Independent review for completeness, feasibility, security, unjustified assumptions | specification, brief, environment | `architecture_review` (status, findings with severity); `docs/architecture_review.md`; a decision record | After the model's verdict the harness adds its own findings (success measure dropped, a brief feature deferred, contract lines nothing can read, the same command in another order, behaviour given to kept files, a kept signature called otherwise) and runs `_a_pass_over_its_own_findings`. Approved, or only non-gating findings: to `scaffold` (or the specification gate). Gating findings: `architecture_revision_count` += 1, back to `principal_architect`. At `MAX_ARCHITECTURE_REVISIONS` (6; `WORKFLOW_MAX_ARCHITECTURE_REVISIONS`; 2 in fast delivery) the run escalates with `kind="design"` (2.8). |
| 7 | `scaffold` | `acceptance_nodes.scaffold`, `app/stacks/scaffold.py` | Set the project up so its tests run before any agent writes code | `stack_pack`, product name, brief | `.harness/stack-pack.json` (the contract), the pack's files, installed dependencies, `scaffold_result`; smoke tests proven then removed | Whole scaffold retried once; unproven twice: escalation with the problem ("nothing is built on an unproven setup"). A seeded codebase with its own manifest is built on as it is. No pack: the custom setup stage (5.7). Next: `acceptance_author`. |
| 8 | `acceptance_author` | `acceptance_nodes.acceptance_author`, `graph/acceptance_batches.py` | QA writes the suite from the numbered criteria and the interface contract | criteria, stack, API reference from the specification, brief, feedback of the last review | test files under the pack's acceptance directory; criteria QA says cannot be automated are deferred with a reason unless a test covers them | May write in batches of criteria for a model that finds the whole suite too much (`BATCH_ACCEPTANCE_AUTHOR`). Next: `acceptance_review`. |
| 9 | `acceptance_review` | `acceptance_nodes.acceptance_review`, `agents/acceptance_reviewer.py` | Mechanical checks, then a QA lead judges whether each test would fail if its criterion were unmet; then lock | the suite, one run of it against the scaffold, brief, specification | `docs/acceptance_tests.md`; `.harness/acceptance-snapshot/`, `.harness/acceptance-locks/vN/` with diffs; the contract recorded at lock; a decision record | Back to `acceptance_author` while problems remain and `acceptance_round < MAX_ACCEPTANCE_ROUNDS` (3; the QA lead reads the suite once even at the limit; fast delivery sends back once). A suite that cannot run or proves nothing is never locked for `rounds < MAX+2` and then fails the run. At the limit, tests too weak, partial, or that no product could pass go back once more (`ONCE_AT_THE_LIMIT`), then lock with the problems open (recorded as gaps). Next: `scrum_master` (or the acceptance gate). Section 6. |
| 10 | `scrum_master` | `nodes/planning.py`, `agents/scrum_master.py` | Split the work into sprints, each a vertical slice owning criteria | specification, success measures, locked criteria | `sprint_plan`, `docs/sprint_plan.md`, a decision record | Measures or criteria left unassigned, or later work built early: asked again once, then continues and the milestone review judges. Sprint count capped from the criteria count (`with_capped_sprint_count`: 1/2/3 sprints for ≤20/≤40/more criteria in fast delivery; 2/3/4 for ≤10/≤15/more in thorough). The harness assigns every non-deferred criterion to exactly one sprint and moves a criterion to the sprint whose tests can pass. A plan assigning nothing fails the run. |
| 11 | `technical_lead` | `nodes/building.py`, `agents/technical_lead.py`, `analysis/work_orders.py`, `graph/planned_work.py` | Plan one sprint as a milestone of work orders | sprint goal, specification, criteria due, carried-forward items, lessons, the last failed attempt, the cause journal, review comments | `milestone_plan` (work orders: role, files, interfaces, steps, edge cases, test cases, verification); `docs/milestone_plan.md`; each file's owner recorded (`.work-order-files.json` at the workspace root) | The **definition of ready** (`readiness_problems`) sends an unready plan back with its problems; the better of the unready attempts is dispatched when attempts run out. A sprint whose due criteria all pass is closed with nothing to build, unless an earlier sprint carried items to take or decline. Fast delivery builds the work orders from the specification itself (`planned_work`). A due dispute (a failed attempt not yet judged) goes to `acceptance_dispute` first. |
| 12 | `specialist_dispatch` / `specialist_worker` / `specialist_gather` | `nodes/building.py`, `agents/specialists.py`, `graph/drafting.py` | Build each work order | work order, specification slice, interface design, project memory, builder facts | changed files, decisions, tests, risks, blockers (one `SpecialistOutput` each) | Fast delivery drafts every file one call at a time from the specification, several at once (optionally in dependency waves, `DRAFTING_IN_WAVES`), with the compiler's word on each draft and up to three repair passes; the agent loop takes what a draft could not do. Context overflow and transient model faults restart the stage on a fresh conversation. Next: `ci_gate`. |
| 13 | `ci_gate` | `engineering.ci_gate`, `app/ci.py` | Commit the batch, run unit and acceptance suites, compare with the last accepted state and the last measurement | workspace | `ci_report`, `ci_batch_commit`; regressions, language-service underlines, interface clashes as `review_defects` | Anything that passed and now fails is a regression defect (at most `MOST_REGRESSION_DEFECTS` = 6 so one broken build is not fifty defects). No project and no suite: skipped. Next: `code_review`. |
| 14 | `code_review` | `engineering.code_review`, `agents/code_reviewer.py` | A senior engineer reads the diff against the work orders and criteria | diff since the last accepted commit, work orders, CI report | blocking and major findings become defects with an owner, each with what shows it | Skipped in fast delivery unless `FAST_CODE_REVIEW`; findings about criteria later sprints deliver are not defects now. Next: `test_and_triage`. |
| 15 | `test_and_triage` | `nodes/triage.py` | One test round: the harness measures the locked suite, runs the unit tests, probes the product, and turns what fails into tracked defects | locked suite, unit tests, review defects | `remediation` cycle (defects with kind, evidence, cause key), `test_round` += 1 | Details 2.5. Defects open: `defect_remediation`. All clear: `security_review`. Remediation attempts spent: `_replan_or_escalate`. |
| 16 | `defect_remediation` (+ `defect_fix_worker`/`defect_fix_gather`) | `nodes/fixes.py`, section 7 | Fix each open defect, measure, keep or revert | defect, its failing output, specification slice, the cause journal | a measured change, an attempt record; `defect_cursor` | Per defect: reverted if it breaks what passed; a locked test blamed twice goes to `acceptance_dispute`. Next: `test_and_triage`. |
| 17 | `acceptance_dispute` | `nodes/reviews.py`, `agents/suite_dispute.py`, `graph/dispute_outcomes.py` | The QA lead names locked tests no right product could pass | failing locked tests with code, criterion, failure and the page | tests sent back to QA through a recorded reopen; `.harness/dispute-outcomes.jsonl` | Section 6.7. Next: back to the round or the lead. |
| 18 | `security_review` / `advice_review` | `nodes/reviews.py`, `agents/security_reviewer.py`, `agents/advice_review.py` | Security and reliability findings; each consulted specialist says which adopted advice this sprint should have built | sprint diff, specification, advice decisions | `security_review`, `advice_findings`, `docs/security_review.md` | Findings feed the milestone review; advice findings join the Sprint Record as minor findings. Parallel mode runs them as `review_worker`s. Next: `milestone_review`. |
| 19 | `milestone_review` | `nodes/milestone.py`, `agents/milestone_reviewer.py` | Accept, request changes or block the sprint | acceptance evidence, due criteria, work orders, findings | `milestone_review`, `docs/milestone_review.md`, a `sprint` decision, `docs/reviews/sprint-N-evidence.md` | A red suite is never accepted whatever the review read. 2.6. |
| 20 | `sprint_advance` | `nodes/closing.py`, `app/sprint/record.py` | Record the sprint and start the next | accepted sprint | Sprint Record, carried-forward items and lessons, counters reset, `current_sprint_index` += 1 | Next: `technical_lead`. |
| 21 | `change_request` | `graph/delivery.py` | A reviewer's requested change becomes `CR-n` with its own acceptance test | review comments | the change request in the suite; QA writes its test; `acceptance_return_to="technical_lead"` | Next: `acceptance_author`, lock, `technical_lead`. |
| 22 | `escalation` (+ `user_review_escalation`, `escalation_accept`, `escalation_retry`) | `graph/escalation.py` | The last rung: a decision | the stuck sprint's failing criteria or the design's open findings | decision records; deferred criteria; `known_issues` | 2.8. |
| 23 | `release` | `graph/delivery.py`, `app/stacks/release*.py` | Final gate and handoff | locked suite, unit tests, production build, probes | CI file, container files for services, README/API summary completion, licences list, evidence page, `completion_gaps`, `docs/reviews/release-evidence.md` | 2.7. |
| 24 | `complete` / `failed` | `nodes/closing.py`, `graph/terminal_state.py` | Terminal | | last sprint summary committed; a marker file in the workspace for any terminal state but a clean release | |

### 2.5 The test round in detail

`test_and_triage` runs after every implementation batch and every fix round. `test_round` gives each round its own inner thread so a test engineer never re-reads a stale conversation.

1. Clear the previous round's throwaway files; put back a deliberate mutation left by a dead worker.
2. `acceptance_nodes.acceptance_for_round` runs the locked suite (once per round, on first entry; a measurement of an unchanged product is reused, `MEASURE_ONCE`). Locked tests that **cannot pass** whatever is built are not product defects: the suite is reopened for QA first (`reopen_the_suite_for`), and once repairs are spent those tests are deferred and named (`beyond_repair`).
3. Who runs the round: the **harness** itself when the evidence is clean (a locked, ran suite passing everything due, unit tests passing, nothing else proven wrong) or always in fast delivery; otherwise the **testing specialist** on the judgement model. No model reads a green round.
4. The round adds the harness's own findings: the product does not start (one defect folding every start, compile, install and unit-compile finding, `graph/start_first.py`), contract server errors, probes on a green suite (concurrent writes, wrong-shape body, edge requests, page probe), the page check's defect, unit tests that fail beside a green suite (set aside or raised, `UNIT_TEST_QUARANTINE`), the scaffold's stub still served, a production build that fails.
5. Defects are de-duplicated (`_each_defect_once`, `_one_defect_per_cause`), one open defect per cause key, and a defect raised again refreshes the open one instead of queueing a second fixer.
6. `record_test_run` charges a round against `max_attempts` (3, `app/sprint/__init__.py`) only when it found a product defect; a round with only mutation findings open, or one whose measurement the harness could not take (`unmeasured`), charges nothing. A hard ceiling of `ROUNDS_PER_ATTEMPT_CEILING` (2) rounds per attempt in all bounds that exemption.
7. Open defects: `defect_remediation`. Nothing open: `is_sprint_acceptable` (regression coverage, accepted risks) then `security_review`.
8. When the fix round before closed nothing on an unchanged product, the attempt ends there (`FIX_STAGES_THAT_CLOSE_NOTHING`).

### 2.6 Sprint, attempt and round vocabulary and caps

| Term | Meaning |
|---|---|
| **Sprint** | One entry of `sprint_plan.sprints`; `current_sprint_index`. Owns criteria; its **due** criteria are its own plus every earlier sprint's (the last sprint answers for all). |
| **Attempt** | One planning of a sprint: the lead's plan, the build, and the test-fix rounds until the attempt ends. A re-plan starts a new attempt (`sprint_replan_count`). Every attempt is appended to `sprint_attempts` and never rewritten. |
| **Test round** | One `test_and_triage` pass (`test_round`). |
| **Fix round** | Every `defect_fix_*` stage between two test rounds. |
| **Milestone revision** | The milestone review sent the plan back to the lead (`milestone_revision_count`). Counted separately from re-plans. |

| Cap | Value | Owner | At the cap |
|---|---|---|---|
| Architecture revisions | 6 (`WORKFLOW_MAX_ARCHITECTURE_REVISIONS`); 2 in fast delivery | `workflow.MAX_ARCHITECTURE_REVISIONS`, `_the_revision_limit` | escalation `kind="design"`: build from the latest specification, open findings recorded as known risks |
| Specification section repairs | 2 | `MAX_SPECIFICATION_REPAIRS` | proceeds to review |
| Acceptance review rounds | 3 (+2 for a suite that cannot run or proves nothing); fast delivery: 1 send-back | `acceptance_nodes.MAX_ACCEPTANCE_ROUNDS` | lock with problems open, or fail when the suite cannot run |
| Suite repairs (reopen after lock) | 2; 4 in all counting tests never sent before | `MAX_SUITE_REPAIRS`, `MAX_SUITE_REPAIRS_IN_ALL` | later failures of those tests are "beyond repair": deferred and named |
| Reclassifications by dispute | max(2, a tenth of the locked tests) | `MOST_RECLASSIFICATIONS` | further rulings are refused |
| Remediation attempts (charged rounds) | 3 | `sprint.DEFAULT_MAX_REMEDIATION_ATTEMPTS` | `_replan_or_escalate` |
| Re-plans of one sprint | 3 re-plans (four attempts); past it the sprint escalates | `MAX_MILESTONE_REVISIONS` used by `_replan_or_escalate` | escalation |
| Milestone revisions | 3 (`MAX_MILESTONE_REVISIONS`); fast: 2 then findings are recorded as risks | `nodes/milestone.py` | escalation (thorough) or "record the findings as risks and go on" (fast) |
| Escalations per run | 3 | `escalation.MAX_ESCALATIONS` | the run fails |
| Release attempts | 2 | `delivery.MAX_RELEASE_ATTEMPTS` | escalation |
| Structured-answer restarts | 2 | `WORKFLOW_MAX_STRUCTURED_RETRIES` | the stage fails the run (or a stage-specific fallback) |
| Model calls per stage | 40 (`MODEL_CALLS_PER_STAGE`); defect-fix stage 16 (`FIX_STAGE_MODEL_CALLS`) | `agents/settled_answer.py` | tools withheld two calls before, the answer is forced or salvaged |
| Model calls per defect across attempts | 60 (`DEFECT_CALLS_AT_MOST`) | `graph/defect_budget.py` | the defect is left open with its attempts as the diagnosis |
| Inner agent supersteps | 160 (`INNER_AGENT_RECURSION_LIMIT` = 40 calls x 4.0); outer graph 100 | `workflow.py` | derived so the call budget binds first |
| Build-model failures before the judgement model | 2 (`ESCALATE_AFTER_ATTEMPTS`) | `models/roles.escalate_after` | the stage or defect moves up a tier |

**End of an attempt** is one decision from one measurement (`graph/end_of_attempt.decide`), in this order: put the **best attempt** back if the product is now worse than the best acceptance count seen (one test fewer is already worse; `KEEP_THE_BEST_ATTEMPT`); **settle** if the due criteria all pass and only the product's own unit tests or findings read from files are open (`SETTLE_WHEN_ACCEPTANCE_IS_GREEN`); **stop** if the last two attempts did not beat the best (`STALL_RULE`), if a near-green sprint was already planned again once (`NEAR_GREEN_REPLANNED_ONCE`) or if the sprint's time budget is past (`SPRINT_TIME_BUDGET`: 30 minutes plus 12 per criterion); otherwise **re-plan**. A stop or settle takes the escalation path with the reason recorded.

### 2.7 Release

`delivery.release` (cancel check first):

1. If the suite is locked: naming problems go back to QA; each deferred criterion with a locked test gets one last single-call rewrite (`LAST_TRY_ON_DEFERRED`); the suite is run; a suite that did not run, proves nothing or could not start the product fails the release.
2. Only if it passes: the project's production build (`app/stacks/production_build.py`), then the product's own unit tests (quarantined ones set aside). A failing unit test blocks unless `release_with_failing_unit_tests.may_ship` allows it (the locked suite passes and the run had already accepted them at an escalation, or release attempts are spent); then it ships recorded.
3. The handoff: `release_docs.complete_the_handoff` writes what can be written; what is still missing (README with run instructions, routes named for an HTTP product) holds the release; `release_audits.secrets_found` holds it for a credential in the code.
4. Held (any failure with `release_attempts` < 2): decision recorded, `release_attempts` += 1, `stage="technical_lead"` with the reason in `revision_comments`, plan cleared, the last sprint goes again on the judgement model. Past two holds: escalation.
5. Passed: clear command lines from code, remove the pack's untouched templates nothing loads, remove data the run's own tests wrote, then assemble `completion_gaps` (deferred criteria, reclassified tests, problems the suite was locked with, plan problems noted at dispatch, shipped failing unit tests, licence gaps, quarantined tests, unproven setup, known issues, risks recorded by reviews, reviews that were not independent, code no review read, probes that still find something at release, mutation gaps), write CI and container files (`app/stacks/release.py` from the pack's `ci_setup`, `ci_prepare` and `release_files`; never over a file the product already has), score screenshots (`SCREENSHOT_RUBRIC`), record the `release` decision, write the evidence page and hand to `complete` or `user_review_release`.

### 2.8 Escalation: the last rung

The ladder, in order, for stuck work:

1. **Fix** the defect (rewrite, candidates or agent loop; section 7).
2. **Fix again**, on the judgement model after two failed fixes or one revert (`the_build_model`).
3. **Dispute**: the QA lead judges the failing locked tests (once per failed attempt) before the sprint is planned again.
4. **Re-plan the sprint**, built on the judgement model from the first re-plan, with the cause journal and what the last attempt did in the lead's request. Best attempt kept (`best_attempt`).
5. **Escalation** (`graph/escalation.py`), which decides rather than stops:
   - `kind="design"` (architecture review never converged): auto mode builds from the latest specification and records the open findings as known risks after `specification_rulings.settle` rules on contradictions; approval mode asks the person (`user_review_escalation`: accept or retry with guidance, resetting the revision count).
   - Sprint kind: with no locked criteria the run stops; if deferring the failing criteria would leave more than half of all criteria undelivered the run stops ("a run that cannot deliver most of its criteria is stopped rather than shipped"); otherwise the failing criteria are deferred with the reason (`suite.defer`), the failed attempt is closed as accepted-at-escalation, unit failures open at that point are recorded as accepted, and the run goes to `sprint_advance` or `release`. Approval mode asks; `escalation_accept` does the same, `escalation_retry` plans the sprint again with the person's guidance and counters reset.
   - More than `MAX_ESCALATIONS` (3): failed.

---

## 3. The agents and roles

### 3.1 Construction

Every role is `create_role_agent` (`app/agents/role_agent.py`) wrapping `deepagents.create_deep_agent`:

- a bounded tool set (3.2); the deepagents built-in write tools are denied at the permission layer as well as absent from the tool list;
- a structured response schema (Pydantic) per role - the answer tool - so the workflow routes on fields, not prose;
- `interrupt_on` for every high-risk tool (`HUMAN_APPROVAL_TOOLS`: `write_artifact`, `edit_artifact`, `replace_lines`, `delete_artifact`, `move_artifact`, `run_terminal_command`, `run_validation`). With `auto_approve` on, the runner answers these automatically; with it off each pauses for a person;
- a middleware chain, outermost first: compaction (keeps the stage's request, summarises the rest, `agents/compaction.py`); transcript; verify-after-write; batch file claims; research share; fresh-conversation reset; gathering (a stage on the judgement model gathers on the build model, `agents/gathering.py`); text-tool-call repair; workspace path normaliser; line batches; environment contract; workspace digest (a map of the workspace with line counts, purpose line, interface, marking harness-owned files); project memory (the project's documents and files handed over current at the start of each call, a read of one already held answered with a pointer; a fixer, and a builder opening on code an earlier stage wrote, get the specification, the acceptance criteria and (a builder) the sprint plan, each long one as a digest of the sections its request points at, the other plans named and the product's code with the rest of the budget); plugin instructions (3.5); filesystem layer; edits-together; repeated-query guard; settled-answer guard (ends a stage once it has answered and stopped progressing; budget 40 calls); optional task list (`HARNESS_TASK_LIST`);
- a checkpointer, so a paused approval resumes the inner agent (`resume_with_decision`) rather than restarting it.

A role whose document the workflow renders has no write tool: the model returns its structured answer and a template renders `docs/*.md`. Reasoning ("thinking") is controlled per model and stage (`agents/thinking.py`): fast delivery runs the build model with reasoning off, a fix reasons as configured, replies that spend the whole reply cap reasoning are salvaged from their own reasoning (`models/reply_salvage.py`). Behind `LONG_REASONING_BEFORE_A_READ` (`agents/deliberated_reads.py`), the reply after one that reasoned 8,000 tokens or more and then only read goes without thinking, for that one reply.

### 3.2 Tool lists

| Role | Tools |
|---|---|
| Read-only roles: product manager, tools and models architect, scrum master, technical lead, architecture reviewer, acceptance reviewer (QA lead), suite dispute, code reviewer, security reviewer, milestone reviewer, advice reviewer, specialist advisor | workspace readers `ls`, `read_file`, `glob`, `grep` (deepagents' filesystem backend wrapped so `.agent-home` is hidden, `agents/workspace_backend.py`); `changed_since_sprint`; the structured answer tool. `can_write=False`. |
| Principal architect, stack selector | the readers plus `look_up_package`, `read_docs`, `search_the_web` and `read_web_page` (when a search is configured), and MCP tools the owner configures (`HARNESS_MCP_SERVERS`) or an official library server found in the MCP Registry. The architect's reading is also done for it before it starts (`agents/research_brief.py`). |
| Specialists (`ui_ux`, `database`, `backend`, `testing`, `documentation`, `security_reliability`) and QA when writing the suite | readers; writers `write_artifact`, `edit_artifact` (find/replace), `replace_lines` (by line range; offered when `line_edits_offered()`), `delete_artifact`, `move_artifact`; `run_terminal_command` (one program with arguments, no shell, role allowlist); `read_command_output` (a long output by reference); `look_up_package`; `module_exports` (what an installed package really exports); `read_docs`; `search_the_web`/`read_web_page`; MCP tools; `use_runtime` (a runtime version the image lacks, per project); `look_at_page` (the running page's accessibility tree, errors and failed requests, for products with a page). The `testing` role also gets `run_validation`. Optional: `code_graph` (`CODE_GRAPH_TOOL`), `ask_specification` (`ASK_SPECIFICATION`). |

`LEAN_TOOL_LISTS` (a switch, on) leaves out the five tools almost never called (`search_the_web`, `read_web_page`, `use_runtime`, `code_graph`, `ask_specification`) except where a stage's request asks for one; `changed_since_sprint` is offered only once a sprint has been accepted; a read-only role on an empty workspace is offered `read_file` alone (`agents/stage_tools.py`). `STABLE_TOOLS` (built in) keeps one tool list for a whole stage visit and refuses a withheld tool's call instead of removing it, so a server's prompt cache stays valid.

### 3.3 The roles

| Role | Prompt/module | Model | Output | May write |
|---|---|---|---|---|
| Product Manager | `agents/product_manager.py` | planning | `ProductManagerOutput` | nothing (document rendered) |
| Tools and Models Architect | `agents/tools_models.py` | planning | `ToolsAndModelsOutput` | nothing |
| Stack Selector | `agents/stack_selector.py` | planning | `StackSelectorOutput` | nothing |
| Specialist advisors `{role}_advisor` | `agents/specialist_advice.py` | judgement (build model in fast delivery) | numbered advice items | nothing |
| Principal Architect | `agents/principal_architect.py` | judgement | `TechnicalSpecificationOutput` with ADRs, file plan, contracts, interface design and contract | nothing |
| Senior Architect Reviewer | `agents/architecture_reviewer.py` | judgement | `ArchitectureReviewOutput` | nothing |
| QA engineer (testing specialist, `writing_the_suite`) | `agents/specialists.py`, `agents/acceptance_reviewer.py`, `acceptance/requests.py` | judgement (default model in fast delivery) | the suite files | acceptance directory only (3.4) |
| QA lead | `agents/acceptance_reviewer.py`, `agents/suite_dispute.py` | judgement (`reviews_without_reasoning` for the review) | approve/findings; dispute rulings | nothing |
| Scrum Master | `agents/scrum_master.py` | planning | `SprintPlanOutput` | nothing |
| Technical Lead | `agents/technical_lead.py` | planning | `MilestonePlanOutput` (work orders) | nothing |
| Specialists (six roles) | `agents/specialists.py` | build model; judgement after failures or on a retried sprint | `SpecialistOutput` | their work order's files |
| Test engineer (testing specialist) | `agents/specialists.py` | judgement | defects | test files only in a test round; nothing else |
| Fixers (the defect's owning specialist) | `agents/specialists.py` + fix request | build model with reasoning on; judgement after 2 failed fixes or a revert | `SpecialistOutput` | files the defect and its mode allow |
| Code Reviewer | `agents/code_reviewer.py` | judgement | findings | nothing |
| Security Reviewer | `agents/security_reviewer.py` | judgement | `SecurityReviewOutput` | nothing |
| Advice reviewers | `agents/advice_review.py` | judgement | adopted advice not built | nothing |
| Milestone Reviewer | `agents/milestone_reviewer.py` | judgement | accepted / changes_required / blocked with findings | nothing |

Common prompt machinery: `agents/lean_prompts.py` (a shorter prompt for a model measured strong), `agents/shared_facts.py` (one account of the facts a sprint is built and judged under, handed to builders and judges alike), `agents/scope_discipline.py` (one rule against inflating scope), `agents/severity.py` and `agents/finding_category.py` (findings that must show evidence to block), `agents/stable_prefix.py`, `agents/stable_memory_order.py` (keep the request prefix byte-stable for server caches), `agents/carry_over.py` (what a dying attempt learned goes to the next on a fresh conversation), `agents/stage_memory.py` (counters that survive approval pauses).

### 3.4 What each role may write: the single-writer rules

Enforced in `app/tools/repository.py` and `app/stacks/contract.py`, not by prompts:

| Rule | Mechanism |
|---|---|
| The **locked suite** is QA's alone. Any write tool refuses it. A command that changes it anyway is undone before the next run. QA, while writing or repairing, may write only the acceptance directory (the product is not QA's to build). | `_the_harness_s_own_or_the_locked_suite`, `suite.is_protected`, `what_a_command_may_not_change` |
| **`.harness/`** is the harness's record; no stage may write it. | same |
| **Kept files** (runner configuration the pack owns: `playwright.config.*`, `pytest.ini`, `acceptance/conftest.py`, the serve script, test setup) and kept manifest scripts and lines are refused to agents and put back if a stage changed them. | `contract.enforce`, `StackPack.kept_files/kept_scripts/kept_lines` |
| **`docs/`** holds only workflow-rendered documents. | repository write guard |
| **A work order's files** belong to its specialist; a path two work orders both list has no single owner and is staggered. A stage refused outside its own files three times is told to stop. | `record_work_order_files`, `_outside_its_own_files` |
| **Fixers of one batch never write the same file**: a fixer's first write claims the file; another's write is refused with what the file needs. | `graph/batch_file_claims.py` |
| A **whole-file write over another stage's file this stage has not read** is refused until it reads it. | `_refuse_a_blind_overwrite_of_another_stage_s_file` |
| A first fix of a failing **unit test** beside a green locked suite writes test files only. | `tools/tests_only_writes.py` (`TESTS_ONLY_WRITES`, built in) |
| A **layered setup stage** writes only the files it was asked for. | `SETUP_SCOPE_GUARD` |
| A file its language's parser rejects, a leaked model control token, a hand-written lock file, a test switched off, a hand-built DOM, an edit that goes backwards again: **refused at the write**. | `_refuse_*` helpers; `analysis/grammar_parse.py` (Python `ast`, `json`, `node --check`, TypeScript parser, tree-sitter grammars measured exact for Java, Go, Rust, Ruby, PHP, Lua, a CSS grammar; brace count only for unmeasured languages) |
| Paths stay inside the workspace and project directory. | repository guard |

### 3.5 Plugin instructions and steering

`app/plugins/` appends framework- and language-specific guidance to each agent's system prompt from the run's chosen stack (`middleware.py`, store `registry.py`, content `seed.py`). A framework the store has never seen gets instructions written once by the model and stored. Approved lessons for the stack (`lessons.py`) are appended in a fixed order so the prefix stays stable; nothing an agent wrote reaches a prompt unapproved. The same mechanism carries the **owner's steering notes** (`app/server/steering.py`, `.harness/steering.json`): a note added mid-run is read by the stage in progress on its next model call, and the transcript records which call read it first. With `STEERING_AT_THE_TAIL` (bundle `PREMIUM_MODEL_TUNING`) the note goes after the transcript as the last message instead of in the system message, keeping the prompt cache valid. Per-model guidance (`app/models/guidance.py`) is a catalogue of `guide:<id>` rows, each its own switch, chosen per model by measured tier.

---

## 4. State, documents and the workspace

### 4.1 Workflow state

`WorkflowGraphState` (`workflow.py`, a `TypedDict`) is the controller's scratchpad; `app/state.WorkflowState` is the separate audit contract for external consumers. Fields by purpose:

| Group | Fields |
|---|---|
| Routing | `stage`, `error`, `pending_approval`, `pending_inner_thread_id`, `pending_decision`, `inner_thread_ids`, `review_policy`, `reviews`, `pending_review`, `pending_review_decision`, `revision_comments` |
| Stage outputs | `product_intake`, `tools_models`, `stack_selection`, `stack_pack`, `specialist_advice`, `technical_specification`, `architecture_review`, `sprint_plan`, `milestone_plan`, `specialist_outputs` (merged per task, reset by an empty update), `remediation` (the `RemediationCycle`), `milestone_review`, `security_review` |
| Counters | `architecture_revision_count`, `specification_repair_count`, `acceptance_round`, `current_sprint_index`, `sprint_replan_count`, `milestone_revision_count`, `test_round`, `defect_cursor`, `suite_repairs`, `suite_reclassified_*`, `escalation_count`, `design_escalation_count`, `release_attempts`, `structured_retries` |
| Sprint memory | `sprint_attempts`, `sprint_earlier_plans`, `sprint_findings`, `carried_forward`, `lessons`, `nothing_left_but_carried`, `sprint_best_history`, `disputed_sprints`, `dispute_returns_to`, `dispute_reason`, `work_order_problems`, `unready_plan`, `best_unready_plan` |
| Fix machinery | `fix_batch`, `fix_batch_started`, `fix_started`, `fixes_tried`, `fixes_one_at_a_time`, `fix_base_commit`, `review_defects`, `review_advice`, `ci_report`, `ci_batch_commit` |
| Parallel | `specialist_pauses`, `queued_decisions`, `reviews_in_flight`, `review_results` |
| Release | `completion_gaps`, `known_issues`, `unit_failures_accepted_at_an_escalation`, `mutation_gaps`, `mutation_probed`, `escalation`, `decisions` |

Reducers: `specialist_outputs`, `specialist_pauses`, `queued_decisions` and `review_results` use `_merge_or_reset` (merge many workers' writes in one superstep; an empty update means start again).

### 4.2 Checkpoints

LangGraph checkpoints the state per superstep (`graph/checkpointing.py`): SQLite under `DATA_DIR` or Postgres (`checkpointer_type`). Deserialisation is pinned to an explicit allowlist of the harness's Pydantic models; a new model stored in state must be added to it. Each stage's inner agent has its own thread id namespaced under the run's thread id. A visit's conversation is written down when it starts and crossed out when it returns, so a stage a worker restart killed carries on in its own conversation (`graph/abandoned_threads.py`).

### 4.3 The workspace

Each run owns a git repository, `DATA_DIR/workspaces/<tenant>/workspace-<run-id>/`, with the product in a **project directory** the intake names once (`.project-directory`; `pin_the_directory_the_product_names`). A product uploaded at the root is moved into it (`stacks/seeded_product.py`). The harness's own HOME for package caches is `.agent-home` inside the workspace (hidden from agent listings).

Commits: one per batch (`ci.commit`), one per accepted sprint with a tag per sprint (`tools/version_control.py`), stage snapshots under `refs/harness/stages/` beside the branch (neither HEAD nor the index moves), best-checkpoint commits during a fix (`graph/best_checkpoint.py`), best-attempt commits (`graph/best_attempt.py`). The release archive keeps git history and leaves out dependency folders, build output and harness files.

### 4.4 Documents a run writes (`docs/`)

Rendered by Jinja templates in `app/doc_templates/templates/` from structured answers, so their shape does not depend on the model: `product_intake.md`, `tools_and_models.md`, `technology_stack.md`, `technical_specification.md`, `architecture_review.md`, `acceptance_criteria.md`, `acceptance_tests.md`, `sprint_plan.md`, `milestone_plan.md`, `milestone_review.md`, `security_review.md`, `sprint_N_summary.md` and the Sprint Record (`app/sprint/record.py`: backlog and outcome, each defect with its cause, fix and verifying command, findings and dispositions, carried-forward items, lessons), `decision_log.md` (`app/decisions.py`, records `DR-n` with point, question, options, decision, rationale, decided_by, affects; also in state and `.harness/decisions.json` whole), `reviews/` (escalation page, `release-evidence.md`, `sprint-N-evidence.md`, review pages), `stage_summaries/`, `third-party-licences.md` (release audits). The release adds the handoff (README, API summary) and the product archive moves process documents to `docs/process/`.

### 4.5 The `.harness/` folder

Agents never see it and no write tool may change it. Principal contents (from `acceptance/suite.py`, `stacks/contract.py`, `ci.py` and the modules named):

| File | Holds |
|---|---|
| `stack-pack.json` | the project contract: pack, commands, report paths, kept files |
| `acceptance.json` | numbered criteria, deferrals, change requests, coverage state |
| `acceptance-snapshot/`, `acceptance-locks/vN/` (+ `vN.diff`) | the locked suite with checksums, every locked version |
| `ci.json` | per-test snapshots (`accepted`, `latest`) |
| `decisions.json`, `steering.json`, `answers.json`, `seeded.json`, `seed-moved.json` | decisions, steering notes, intake answers, seeding records |
| `fix-journal.json`, `kept_candidates.json`, `best-attempt.json`, `fix-round-before.json` | what was tried on each cause, reverted fixes kept as candidates, the best attempt, the round's starting fingerprint |
| `contract-probe.json`, `order_probe.json`, `production-build.json`, `start_breaks.json`, `check-findings.jsonl`, `dispute-outcomes.jsonl`, `screenshot-rubric.json` | probe coverage, probe and build results, every finding a suite check raised, dispute outcomes |
| `project-graph.json`, `specification_rulings.json`, `unit_tests_that_disagree.json`, `quarantined_unit_tests.json`, `equivalent_mutants.json`, `dependency-gate.json`, `runtimes.json`, `mcp-official.json`, `stage-threads.json` | code graph, rulings, quarantined unit tests, remembered equivalent mutants, install gate record, pinned runtimes, MCP registry result, open stage conversations |

A terminal state other than a clean release writes a loud marker at the workspace root (`graph/terminal_state.py`); a clean release clears it.

### 4.6 The defect ledger, transcripts, rewind

- **Defect ledger** (`observability/defect_ledger.py`): one `defect` record per event in the run's transcript - raised, raised again, bundled, fixed, reverted, best checkpoint, left open, lookup, rewrite after surrender - keyed by round and index; `scripts/loop/defects.py` reads it back. A defect carries `kind`, small `evidence` records and a `cause_key` (`app/sprint/cause.py`): two defects with keys are one problem exactly when the keys are equal.
- **Transcript** (`observability/transcript.py`): the complete unclipped record of what each stage was told, replied and did, JSON Lines at `DATA_DIR/transcripts/<run_id>.jsonl`, including notices appended by middleware, each resume after a restart and which call read each steering note.
- **Rewind** (`workflow.rewind_points`, `rewind_to`): each time a stage was entered is a point (the checkpoint just before it). Rewinding makes that checkpoint the run's latest on a branch (history kept), restores the workspace from the snapshot taken for that checkpoint (`restore_snapshot`, refused when none was taken) and clears pause state. Only the start of a stage can be rewound to, and only a paused run.
- **Resume**: an orphaned or paused run resumes from the last checkpoint; the entry router picks the node.

---

## 5. Stack packs and the language table

### 5.1 What a pack is

A pack (`StackPack`, `app/stacks/__init__.py`) holds exactly what differs between kinds of product in a language: layout, install, unit and acceptance commands, report locations, how a test drives the product (a browser for a page, HTTP for a service, a process for a CLI, an import for a library). The workflow around it knows no language. A pack scaffolds because on 46 measured runs 63% of reported defects concerned tests and their setup, none of which needs judgement.

### 5.2 Pack fields

| Field group | Fields |
|---|---|
| Identity | `name`, `title`, `kind` (`browser_app`, `http_api`, `fullstack`, `cli`, `library`), `language`, `frameworks`, `frontend_frameworks`, `stack` |
| Scaffold | `files` (with `{{project}}`, `{{title}}`, `{{package}}`), `install`, `smoke_files` (one unit, one acceptance test, removed once proven), `warm_up` (network commands once tests exist), `fetches_while_building`, `process_memory`, `server_wait_ms` |
| Commands and reports | `unit_test`, `acceptance_test`, `unit_report`, `acceptance_report` (JUnit XML), `unit_dir`, `acceptance_dir`, `unit_pattern`, `acceptance_pattern`, `typecheck`, `production_build`, `list_routes`, `how_it_is_used`, `evidence_dir`, `runtime_report` |
| Kept state | `kept_files`, `kept_scripts`, `kept_lines`, `required_exports`, `required_signatures`, `entrypoint`/`entrypoints` (the stubs the drafted product must replace), `wired_by_imports`, `relative_import_extension` |
| Guidance | `guide` (how tests are written, shown to every writing stage), `acceptance_guide` (to QA), `design_facts` (stated to the architect and reviewer), `data_store`, `known_errors`, `golden_example`, `framework_files`, `proven_code` |
| Checks | `check_families`, `test_bugs`, `locators_nobody_sees`, `locators_that_pick_one`, `locators_that_do_not_exist`, `locators_by_a_missing_name`, `finds_by_name`, many callables that read a test's text (contradicting locators, tests that open no page, storage before page open, unawaited helpers, positions asserted, near misses, assertion names) |
| Release and sandbox | `ci_setup`, `ci_prepare`, `release_files`, `sandbox_image` (one image holding toolchain, runners, Node and browsers, `packs/_sandbox.py`), `unit_mirrors`, `unit_dom`, `code_runs_in`, `data_dir_env` |

Derived: `probe_runner` ("playwright" when the pack ships a Playwright config, "pytest" when the kept conftest starts the service) and `coverage` (what the harness checks for a product on this pack).

### 5.3 Selection and the contract

`choose_pack(stack, text, rationale)` tries the packs in `packs.ALL_PACKS` order and returns the first whose language, product kind and framework fit (`_framework_fits`, `_frontend_fits`, `product_kind`); a stack naming a component framework fits only a pack built with it. A stack the harness aligns to the pack gets its fields corrected (`aligned_stack`). `scaffold` writes the pack to the project directory, runs the install, writes the smoke files, runs the unit and acceptance commands through the same sandbox path every later stage uses, reads the JUnit reports, then removes the smoke tests and reports. Only a scaffold whose smoke tests pass is kept (retried whole once). The result is written to `.harness/stack-pack.json` (`contract.write`). Every later stage reads it (`contract.the_pack`, `describe`); `contract.enforce` puts back kept files, scripts and lines a stage changed (a refusal costs a turn and teaches nothing; putting back keeps the commands meaning what they meant).

### 5.4 Packs (38)

| Kind | Packs (language) |
|---|---|
| Browser apps | `browser-javascript` (JS), `browser-react`, `browser-vue`, `browser-svelte`, `browser-angular` (TS) |
| Node/TS services | `node-http-api` (JS), `node-nest-api`, `node-hono-api`, `node-hono-native-api` (TS) |
| Full stack | `fullstack-node` (JS), `fullstack-react-express`, `fullstack-vue-express`, `fullstack-next` (TS), `fullstack-react-fastapi`, `fullstack-vue-fastapi`, `fullstack-page-fastapi`, `fullstack-django` (Python) |
| Python | `python-http-api`, `python-flask-api`, `python-cli`, `python-library` |
| CLIs and libraries | `node-cli`, `node-library` (JS), `typescript-cli`, `typescript-library`, `go-cli`, `go-library`, `rust-cli`, `rust-library` |
| Other services | `go-http-api`, `go-gin-api`, `java-spring-api`, `csharp-aspnet-api`, `rust-axum-api`, `ruby-sinatra-api`, `ruby-rails-api`, `php-slim-api`, `php-laravel-api` |

Fullstack packs share one shape (`packs/_fullstack.py`): the interface built with Vite into `dist/`, served by the product's own service beside `/api/`, one process on one port, driven by Playwright through the page and `/api/`. Service packs (`packs/_service.py`) are tested from outside with Playwright's `request` fixture or pytest + httpx whatever their language, so QA writes acceptance tests one way and a building stage never runs the service by hand. Web packs start from a shared accessible design token stylesheet (`packs/_design.py`). Support status per pack: section 1.4.

### 5.5 Known errors and the golden example

- **`known_errors`**: a phrase of an error message the stack is known to raise, mapped to its cause. A defect whose text carries the phrase is given the cause (`app/stacks/known_errors.py`). Nothing outside the pack names the stack.
- **`golden_example`**: a small working product in the pack's pinned framework version (shared state reaching a handler, one JSON body read and checked, a 404 and a 400, data in a file under `DATA_DIR`, a unit test calling the service in memory). It is shown to stages that write and fix code as reference and never written into the product (`contract.reference_code`); `scripts/loop/verify_packs.py` compiles it and runs its test. Present on 7 packs (`go-http-api`, `go-gin-api`, `java-spring-api`, `csharp-aspnet-api`, `rust-axum-api`, `ruby-sinatra-api`, `php-slim-api`), where version skew was the measured trap; other packs have none.
- **Naming standard**: one per language, stated in the specification and every draft's request (`app/stacks/naming.py`, `NAMING_STANDARD`).

### 5.6 `seed.py`, the language table and per-language data

- **`app/plugins/seed.py`**: the only place language- or framework-specific instructions for agents belong. Rows are keyed by lower-case names the stack extractor produces (a language, a framework); the middleware appends the rows matching the run's stack. An edited row in the database is never overwritten by re-seeding. `seed.DEVELOPMENT_SERVERS` lists development-server markers a release reads.
- **`app/stacks/languages.py`** (`LanguageSupport`, 10 rows: javascript, typescript, python, go, rust, java, kotlin, csharp, ruby, php). One row per language answers, once, what every mechanism needs: source `suffixes`, `manifests` and `lockfiles`, `installed` folders (known by name), `installed_beside` and `build_output_beside` (known by a manifest next to them, so `vendor` is the product's own unless `composer.json` is beside it), `build_output_by_name`, `test_files` patterns, `check` (the checker that reports undefined names before tests run: `language_service` for JS/TS, `pyright` for Python, a `compiler_check` checker otherwise), `test_totals` (runners whose printed totals the sandbox counts), `runtime_version` (what `tools/runtimes.py` pins), `docs` (the registry `read_docs` reads a README from), `sandbox_toolchain` and `executables` (which image a command runs in), `import_graph`, `development_server`, `package_cache` (the variable and folder when a toolchain keeps its restored packages under the user's home, so a product started as delivered is pointed at the restored cache) and `restores_when_it_starts` (`dotnet run`). A field with no answer is a `Gap` carrying the reason, never omitted; a completeness test holds every pack's language to a full row. Derived constants: `INSTALLED`, `NOT_THE_PRODUCT`, `MANIFESTS`, `LOCKFILES`, `TEST_FILE_PATTERNS`, `is_generated`, `image_for_executable`.
- **Sandbox tables** (`app/tools/sandbox.py`): `TOOLCHAINS` (executables per language, 17 languages incl. swift, dart, elixir, scala, c, cpp), `ROLE_EXECUTABLES` (per-role allowlists keyed `<role>_specialist`), `TOOLCHAIN_TIMEOUT_SCALE`, install grammars per package manager.

### 5.7 Contract helpers: install, versions, start-first, custom stacks

- **Install** (`contract.installed`, `install_if_the_manifests_changed`): reinstall when a manifest changed since the last install; when an installer says a package has no such version, or lacks a feature (Cargo), the failure shown to the fixer carries what the registry actually has (`_the_versions_that_exist`, `_the_features_that_exist`) and the installer's own error lines (`_what_the_installer_said_went_wrong`), never usage text. An untrusted lock file is not relied on (`_a_lock_file_the_installer_cannot_trust`). Installs pass the **dependency gate** (a name the registry lacks or one first published fewer than `DEPENDENCY_MIN_AGE_DAYS` = 14 days ago is refused; `tools/dependency_gate.py`) and the egress check (`tools/install_egress.py`: only package registries and GitHub, plus `INSTALL_ALLOWED_HOSTS`).
- **Compiler help**: `compiler_errors.py` runs the pack's `typecheck` once when the product does not start and adds the errors that name something missing (a name, export, member or module) to the one start defect; `entry_exports.py` raises a defect when a stage drops an export the pack's own files import; `import_extensions.py` / `imports_before_a_run.py` add the `.ts` Node needs to a relative import before the harness measures the product and before a stage's command runs; `production_build.py` runs the declared or manifest build once per product fingerprint.
- **Start-first** (`graph/start_first.py`): at a test round, everything saying why the product does not build or start (start failure, compiler and language-service findings, failed install, a unit run that did not compile) is folded into the one start defect; while it is open the fix round dispatches only it; the others wait until the product starts.
- **Custom stacks** (`stacks/custom_setup.py`): for a stack no pack covers, a setup stage creates the project with the framework's generator on the closest pack's install and runner configuration (`framework_files`, `proven_code`), declares it in `<project>/stack-setup.json`, and the harness proves it exactly as it proves a pack (install, each smoke test through the declared command, JUnit read). Only a setup that passes is recorded as a contract; one that does not is sent back once.
- **Release** (`stacks/release.py`, `release_docs.py`, `release_audits.py`): CI generated from the pack's own commands so it cannot describe a build nobody saw pass; container file for services; README with run instructions and an API summary required (`RELEASE_DOCS_REQUIRED`); secret scan, licence listing and an `AUDIT_COMMANDS` dependency audit step in CI (`RELEASE_AUDITS`). No container is ever built inside the sandbox, and the release record says so.

---

## 6. Acceptance suite and verification

### 6.1 Authoring

`app/acceptance/criteria.py` numbers `AC-n` from the brief; `suite.save_criteria` keeps them in `.harness/acceptance.json`. The QA author (testing specialist with `writing_the_suite=True`) is given the criteria, the pack's `acceptance_guide`, the brief's control names up front, the **API reference** (`acceptance/api_reference.py`: the specification's routes, data shapes and error messages handed over whole, within a bound), the interface contract and testability advice. Each test name carries its criterion tag. A criterion QA says cannot be automated is deferred with a reason only if no test covers it. A change request adds `CR-n`.

### 6.2 Mechanical review (before the QA lead reads anything)

`acceptance_review` runs the suite once against the scaffold and applies about fifty named checks (`suite.py`, `check_findings.py` records every finding with the check that raised it so `scripts/loop/check_precision.py` can measure each check's precision). Families:

| Family | Examples |
|---|---|
| Cannot run or proves nothing | `result.ran`, `vacuous_green`, the test that never finishes, files the runner skips by name (renamed, not sent back) |
| Cannot pass on any product | `tests_that_cannot_pass`, the dry run of a JS suite with the product stood in for (`spec_dry_run.cjs`, `SPEC_DRY_RUN`), a test that reads a literal id and creates nothing first (`IDS_READ_WITHOUT_A_CREATE`), `tests_that_want_json_from_a_204`, success statuses the contract does not give; a test whose pick of its own records misses one it made (`picks_of_their_own_records_that_miss_one`, the pack's `own_records_a_pick_misses`, JavaScript; also handed to a dispute as settling, LF.1237) |
| Passes before the product exists | `tests_that_pass_before_the_product` (first writing only), assertions made only when the answer was good (`tests_guarded_by_the_answer`) |
| Too lenient | locators nobody sees, locators that pick one of many, a control the brief names that no test finds by that name, records never found as the brief shows them, outputs held only in part, whitespace and word-break tests with spaces only, views never acted within |
| Coverage | every criterion has a test; every contract line is exercised by some test (`contract_coverage`, `CONTRACT_LINE_COVERAGE`, a search not a parse) |

A suite under repair is measured first (`_the_repair_measured`): a repair that left the suite worse is put back as locked and the writers are told what it lost; tests a repair changed that were not sent for repair go back as the review approved them.

### 6.3 The QA lead and the lock

When the harness's checks are clear (or at the limit with problems open and no review yet), the QA lead reviews (`agents/acceptance_reviewer.py`): would each test fail if its criterion were unmet, are the QA-deferred criteria's reasons valid. Findings about the product rather than the tests are dropped (`findings_about_the_suite`). Then `suite.lock`: files copied to `.harness/acceptance-snapshot/` with checksums, recorded as `acceptance-locks/vN` with a diff from the previous version quoted by the decision that re-locks it. At lock the interface contract is recorded (`interface_contract.record_at_lock`), contract line coverage recorded, and the contract's own probes run once (`probe_at_the_lock`). The `acceptance_tests` decision states what the lock ran and any problem left open.

### 6.4 Probes against the started product

| Probe | When | What it asserts | Module |
|---|---|---|---|
| **Start probe** | when the suite cannot reach the product (`START_PROBE`, built in) | starts the product as the suite's configuration does (its `start.sh`, a free `PORT`, a fresh empty `DATA_DIR`), polls the readiness URL, reports what the service printed and the URL answered, with the lines stating the error ahead of the stack frames (`what_went_wrong`); in container mode the pack's `list_routes` supplies routes when the readiness route is not served | `acceptance/start_probe.py/.cjs`, `start_output.py` |
| **Interface-contract probes** | at lock, each green round, release | the contract is one strict line per route, control or command (`AC-3 GET /api/notes -> 200`, `AC-1 page /login textbox "Email"`, `AC-5 command notes add milk -> exit 0`), compiled without a model so a repair of the suite cannot loosen them: a bare request must not draw a 5xx, an unparsable body must be refused, a field the criteria refuse empty is refused, non-numeric ids and a record made first where the route has a parameter | `acceptance/interface_contract.py` |
| **Page checks** | before every suite run for page products | loads the page once, records uncaught console errors, axe-core serious and critical rules (accessibility), width at 375 px; defects for a page whose only styling is the scaffold's reset (`analysis/interface_checks.py`) | pack `page_check`, `runtime_report` |
| **Page probe** | green round (`PAGE_PROBE`) | a Playwright spec through the suite's own configuration drives a person adding an item: markup typed into a field must not run as code, no console errors or failed requests, no sideways scroll at 360 px, an item survives a reload where the brief says data persists | `acceptance/page_probe.py` |
| **Edge probe** | green round (`EDGE_PROBE`) | requests compiled from the contract's routes and example bodies: each field missing, null, empty, spaces, wrong type, very long, other script; ids non-numeric, negative, huge, deleted; delete twice. Invariants: never 5xx, a refused create stores nothing, a refused update changes nothing | `acceptance/edge_probe.py` |
| **Concurrent-write probe** | green round (`CONCURRENT_WRITE_PROBE`) | N creates at once each kept with its own id | `concurrent_write_probe.py` |
| **Wrong-shape body probe** | green round (`WRONG_SHAPE_BODY_PROBE`) | valid JSON that is not an object must not make the server fail | `wrong_shape_body_probe.py` |
| **Order probe** | first green round | each file run alone, last first; a test failing only then is recorded | `order_probe.py` |
| **Release re-probe** | release | each probe that applies is asked again; what it still finds is a gap that blocks, in the words the round's defect used | `probes_at_release.py` |
| **Screenshot rubric** | release, only when the judgement model reads images (`SCREENSHOT_RUBRIC`) | a fixed checklist scored 1-5, a score never a gate | `screenshot_rubric.py` |

Supporting: `measured_once.py` (an unchanged product is not measured again), `unstable.py` (a criterion failing in the whole suite and passing alone on the same fingerprint is unstable, not fixed), `per_file.py` (a suite that hangs is run file by file with a short limit), `stray_services.py` (services a test started and left running are stopped after the command), `unmeasured.py` (a measurement the harness could not take, such as the sandbox refusing for memory or an unreachable registry, is not a product failure and charges no round), `sprint_scope.py` (which locked tests belong to later sprints, so a builder is not made to pass them early).

### 6.5 Mutation testing

`acceptance/mutation.py`: small textual changes to the product's source (a comparison turned round, a condition flipped, a constant moved by one), the suite run as the harness runs it, and each change no test notices reported. Each run of the tests with a change in place is held to three times the unchanged run plus 30 s (at least 60 s, `sandbox.capped`); tests that never return count as having noticed the change. With `MUTATION_GAPS_BUNDLED` the findings in one file go to one fixer and each is closed only when `mutation_guided.settled` confirms it. It runs at release when criteria pass, for a suite that drives no browser, about three changes. With `MUTATION_GUIDED_TESTS` (bundle `PREMIUM_DEEP_VERIFICATION`) the same probe runs when a sprint's due criteria all pass, on the sprint's changed source files: a surviving change becomes a finding for the testing role asking for a unit test that fails with the change and passes without it (`mutation_guided.py`). `MUTATION_TEST_RETENTION` (built in) keeps what a fix added only if it earns its place at file granularity. `MUTANT_CHECK_IN_THE_FIX_STAGE` tells the fixer at each write whether its test notices the change; `EQUIVALENT_MUTANTS_REMEMBERED` records a change judged equivalent so it is not raised again (`mutation_equivalents.py`, `.harness/equivalent_mutants.json`). Mutation findings the sprint has no round for are gaps, not a reason to re-plan. `scripts/bench/mutate.py` measures a run's locked suite the same way for the benchmark.

With `CONTESTED_TESTS_CONFIRMED` (off until measured), rulings that quote identical code at fault count as one cause for the cap, and a ruling past the cap reopens a test only after the harness confirms its quoted repair: no line that checks a result changed, the locked test fails alone, a corrected copy beside it passes, and that copy still fails against at least one of up to 3 deliberate changes to the product (`graph/contested_tests.py`).

A finding of the suite's dry run carries the cause when the runner's error is a known one (`spec_dry_run.SUITE_KNOWN_ERRORS`), and is never held back, since it is what running the test's own code did (LF.1183). Any other suite-check finding that comes back with the same check, wording and tests after a repair changed the suite is not sent to the authors again: it goes to the QA lead as a suspected false finding and is recorded (`suspected false finding`, a `withheld` row in `check-findings.jsonl`; LF.1177). The suite writer's system prompt names only its acceptance folder (LF.1178).

A defect holding a release probe's finding leads any merge with failing unit tests and never counts as a unit-test failure, so a green sprint does not settle while a probe still finds what would block release (LF.1186). A 5xx from the edge or server-error probe reaches its fixer with what the server printed for that request (LF.1185; an HTML error page is cut to its title).

A repair of a locked suite keeps one record (`.harness/suite-repair.json`, `acceptance/suite_repair.py`): the tests sent, their code at the start, every measured version and the best. A review that measures the suite worse than the better of its state before the repair and the best version, or a repair that reaches its round limit, puts back the best version; the lock never takes a worse one (LF.1189-1190).

### 6.6 Brownfield: the regression contract

For every seeded run the regression baseline is built in (`REGRESSION_CONTRACT` in `BUILT_IN`), and intake, stack selection, the architect and the lead read a code map of the seeded codebase (`agents/code_map.py`, no model call: every module with its public names up to 80 source files, by directory past that, at most 6,000 characters). With `PULL_REQUEST_DELIVERY` on, the changed product goes back as one commit on the seed's base, pushed as `harness/<slug>-<id8>` with a pull request opened through the host's API (GitHub first, `server/repository_delivery.py`); without a delivery token, or when the push fails, the handover pack carries a git bundle and a patch. The per-project delivery token is sealed with the stored-credentials key, reaches git only through `GIT_ASKPASS`, and is deleted once the pull request is open.

With `REGRESSION_CONTRACT`, a seeded codebase's own green tests and the locked tests that already pass form a baseline taken when the suite is locked; CI raises any that later fail as regressions (`acceptance/regression_contract.py`).

### 6.7 The dispute and reclassification path

1. **Mechanical first.** Tests that cannot pass are named by the checks above and reopened for QA by `reopen_the_suite_for` (the budget: 2 repairs, 4 counting tests never sent before; a test is "sent" once).
2. **The QA lead's dispute** (`acceptance_dispute`) runs when a failed attempt has not yet been judged (`_a_dispute_is_due`, before the re-plan), or mid-attempt when a fix stage left its defect open and blames the locked suite, or two fixes in a row were reverted for breaking the same locked test. The lead is shown each failing locked test with code, criterion, failure and the page it failed on and names only those no product meeting the criterion could pass (`agents/suite_dispute.py`; verdict structured, `STRUCTURED_DISPUTE_VERDICT`).
3. **The harness checks the ruling** before acting: it re-measures the named test alone and with its service (a test that passes alone, or whose service stayed up, is not "wrong"), requires the ruling to quote the test's own criterion (`DISPUTE_QUOTES_THE_CRITERION`) and a standard the specification, brief or contract holds, groups rulings by shared cause (one broken helper is one cause), and applies the **reclassification cap**: `max(2, locked tests // 10)` causes per run (`reclassification_room`). The outcome is one decision plus a line in `.harness/dispute-outcomes.jsonl`.
4. **QA repairs** the named tests only as far as their own code is wrong. A repair is re-measured and judged by the harness's checks; one that changed only the tests it was sent for is re-locked without another QA lead review (`TARGETED_SUITE_REPAIR`).
5. **QA says the product is at fault.** A repair a dispute opened may answer "the test is right, the failure is the product's" (`QA_SAYS_THE_PRODUCT_IS_AT_FAULT`, `graph/product_at_fault.py`); it stands only when the reopen was a dispute's, every sent test is claimed for the first time, the suite is byte for byte its last lock, the harness's checks find nothing, each claimed test fails in the review's own measurement and each claim quotes the standard and the measured failure word for word. Then the suite stays locked, nothing is charged to the repair budget.
6. After the repair the suite is locked again and the sprint goes back to where it was found: the round, or the lead (`acceptance_return_to`); a repaired suite that passes in full beside passing unit tests (or is near green, `NEAR_GREEN_REPAIR_TO_ROUND`) is measured again, not planned again.
7. A test whose repairs are spent and that still cannot pass is **beyond repair**: its criterion is deferred and named, and the release lists reclassified tests as gaps (`suite_reclassified_tests`).

### 6.8 Hidden and quality tests (scoring)

`benchmarks/<family>/` holds `brief.md`, `bench.json` (kind, runner, test count), `hidden/` (never copied into a workspace or the image; the image copies only `src/`), `quality/`, and `reference/` (an implementation that must score 100% to prove the tests right). Families span browser apps, HTTP services in many languages (the `notes-api-*` set share one hidden suite), CLIs, libraries, full-stack pages, an accounts-and-per-user-data service (`tasks-api`) and a brownfield change (`tasks-api-change`: a run starts from the reference base and adds features without breaking the old ten tests). `scripts/bench/score.py` starts the product the way its brief says, runs the hidden and quality tests, computes the handoff score, records the harness's own verdict and marks false acceptances; `scripts/bench/report.py` totals them. Hidden briefs state an Interface section so any implementation can pass.

---

## 7. Fix machinery

### 7.1 The defect ledger and cause keys

Every defect is a record with severity, owner (one of the six specialist roles; spellings like "Testing Specialist" are normalised, `agents/specialist_roles.py`), reproduction, expected and actual behaviour, affected files, `fix_attempts`, `attempts` (per attempt: stage, outcome, files, calls), `caught_by`, `kind`, `evidence`, `cause_key`. Statuses: `open`, `fixed`, `accepted_risk`, `superseded` (closed by a defect raised for the one cause behind several). `app/sprint/cause.py` derives the cause key deterministically from the measurement (a failing test, a compiler error, a probe's request, a start's error line) so two criteria raised from one template are not mistaken for one recurring defect. `observability/defect_ledger.py` writes each event to the transcript.

### 7.2 Grouping and bundling

Defects that share a cause are bundled so one fixer sees all of them (`_bundle_co_defects`; the fixer is told "the harness measures each one after your fix"), and in parallel mode `_defects_to_fix_together` picks as many as can be fixed side by side: files apart, bundles apart, at most `concurrent_requests()`. A file rewritten for one defect is also shown the other open defects that point at it (`CO_DEFECT_FAILURES_IN_REWRITES`), and a defect another fix already resolved is closed before it is dispatched (`_closed_if_an_earlier_fix_resolved_it`). One start defect holds back all others (5.7). A defect whose own tests pass when re-measured alone at dispatch closes (unless the measurement is the unstable kind, 6.4).

### 7.3 Which fix path a defect takes

`nodes/fixes._fix_one` (per defect):

1. Skip if an earlier fix closed it, or the defect has spent `most_calls()` = 60 model calls across attempts (`defect_budget`, left open with its attempts as diagnosis).
2. Pick the model (`the_build_model`, reasoning on for a fix; judgement after 2 failed fixes or a revert).
3. `defect_fix_modes.begin` fixes what the stage may write (`TESTS_ONLY_WRITES`, `MUTATION_TEST_RETENTION`).
4. Before any new call, **replay kept candidates**: a fix reverted for breaking tests whose own defect's tests passed was kept as a patch (`kept_fix_candidates`, `KEPT_FIX_CANDIDATES`); the smallest diff first, composed across attempts when files do not overlap, measured as any fix is.
5. **Diagnose** a cause that has already failed twice with one call that only diagnoses; the hypothesis is kept in the journal and shown to the fixer (`cause_journal.diagnosed`, `DIAGNOSE_AFTER` = 2, `DIAGNOSE_A_RECURRING_CAUSE`).
6. **Rewrite-based fix** (`graph/rewritten_fixes.py`, used by default in fast delivery and after a failed fix in every mode; `bounded_fixes.py`): the harness gathers what failed (the defect's own failing tests first, the failure text with traceback frames outside the project collapsed, `analysis/tracebacks.py`), the files it names and the files the failure points at, the specification's entries for each, and neighbouring files; one call per file asks for the file whole; the compiler's diagnostics on what was written are fed back for up to `MOST_PASSES` = 3 passes and the version with the fewest findings is kept (`graph/fewest_findings.py`). Files too long to return whole are fixed by edits anchored on their own text (`anchored_edits.py`). `LOCALISE_FIRST` asks once, cheaply and without reasoning, which files and symbols (`graph/localisation.py`). After a failed fix, `CANDIDATES` = 3 candidate rewrites are asked of the judgement model (or the fix's own model with the fix cycle on) and the first the defect's tests pass is kept; a rewrite prompt byte-identical to three that already failed is not sent again (`REPEATED_REWRITE_PROMPT_STOP`).
7. **Agent loop** (the specialist with tools) for a defect with no file the harness can name, a mutation finding (the product's source stays as it is), or a rewrite that wrote nothing. It is capped at `FIX_STAGE_MODEL_CALLS` = 16 and not restarted (`AGENT_LOOP_FIX_LIMITS`); the same action repeated with no file change in between is called a loop and the next input says what it already did. Each successful write is followed by the defect's own tests and one line of the result is appended to the write's reply (`verify_after_write`, `VERIFY_AFTER_WRITE`). An answer that changed no file is replaced by the rewrite path once (`surrender_to_rewrite`).
8. **Measure and keep or revert** (`engineering.after_a_fix`): the whole suite and unit tests are measured; anything that passed and now fails reverts the stage to the commit it started from and the defect stays open with what the attempt broke. Exceptions: a fix that gained at least `MIN_GAINED` (3; 4 if it also broke a locked criterion) tests and `RATIO` times as many as it broke, and left the product building and starting, is kept (`net_gain.py`, `KEEP_NET_GAINS`); a fix that makes a locked test pass and breaks only unit tests is kept and each is raised (`unit_tests_disagree.py`); a manifest left unreadable, an install the fix broke, or errors a fix added to the compiler are reasons to revert too (`what_the_fix_made_certain_to_fail`, `what_the_fix_made_the_compiler_report`, `what_the_fix_did_to_the_install`).
9. **Best checkpoint** (`graph/best_checkpoint.py`): a fix alone commits each write whose immediate check finds the defect's own tests passing, beside the branch. When the stage ends worse than that checkpoint, the checkpoint is put back and measured in the stage's place, kept only if that measurement holds. Not used by fixers of a batch (they share a workspace).

### 7.4 Compiler and language-service feedback

`analysis/language_service.py` runs the TypeScript language service (JS/TS) and Pyright (Python) on every written file: names nothing defines, imports of missing exports or modules. Findings are notes at the write and defects at CI (`engineering.underlined_in_the_batch`). `analysis/compiler_check.py` gives compiled languages the compiler as language service (gopls, rust-analyzer, C#/Java servers) where available. `analysis/package_exports.py` (`module_exports`) tells a stage what an installed package really exports before it imports a name. `analysis/dependency_drift.py` bundles imports no manifest declares into one defect; `analysis/reachability.py` finds source files nothing imports (the product's second copy), reported at release as "code the product does not run"; `analysis/integration_checks.py` checks cross-file references written separately.

### 7.5 Known-error causes

A pack's `known_errors` and the harness's recognisers (`app/stacks/known_errors.py`, `acceptance/what_went_wrong.py`, `acceptance_nodes.where_errors_become_5xx` and `the_server_hid_the_cause`) put a stated cause on a defect: the server's real exception when it was hidden behind a generic 500, the error line rather than the end of a stack, a colour that reads for a contrast failure (`a_shade_that_reads`).

### 7.6 The journal, history and stuck lookups

- **Cause journal** (`graph/cause_journal.py`, `.harness/fix-journal.json`): what was tried on each cause across re-plans, rewinds and new fix cycles - files changed, the fixer's own one-line account, how the harness measured it. Fixers and the lead's re-plan request read it back newest first, bounded.
- **Earlier attempts** (`agents/ledger.py`, `DECISION_LEDGER`): each earlier attempt as measured, not a revert sentence; the last permitted attempt is given a different shape of work (`_the_last_attempt_section`).
- **More lookup triggers** (LF.1170): an install or setup error the registry note does not explain (T2) and a compiler error code repeated from the round before (T3) are looked up the same way, once per run per error, one block per fixer; before a dependency manifest is drafted or rewritten, the registry's current release of each dependency the specification names is shown (T4, `graph/registry_versions.py`, registries only - runs under every lookups choice).
- **Web tools after two failed fixes** (LF.1172, `WEB_TOOLS_AFTER_TWO_FAILED_FIXES`, off): once a defect's fixes have failed twice, that fixer alone gets `search_the_web` and `read_web_page`, told so in one sentence; never for a mutation finding or when the run's lookups choice is Off.
- **Lookup sources, order and caps** (LF.1173; one reader since LF.1179, each connection made to the address it checked): Stack Exchange, GitHub issues and the private search first; Context7, Brave and Tavily only when those found fewer than 2 results (Brave and Tavily only with a key). `LOOKUP_ORDER` reorders, `LOOKUP_DAILY_CAPS` sets per-source daily caps (defaults: Stack Exchange 250, GitHub 500, private search 1,000, Context7 100, Brave and Tavily 50). `tools/page_reader.py` reads one page: public addresses only, re-checked on every redirect hop, robots.txt obeyed, main text, paged; no browser render (Playwright for Python is not in the worker image).
- **Internet lookups, chosen per run** (`app/internet_lookups.py`): *Off* sends nothing outside except package registries and official docs; *When stuck* turns on the stuck lookup below; *Always* (the new-run form's default since 2026-11-23, and the deployed default for every run) also offers web search and the page reader to the stages that read docs (`WEB_TOOLS_OFFERED`). The choice is the run's own switches and shows on the run page; the Stack Exchange key and GitHub token are set on the admin page, masked, and never reach a model's environment.
- **Stuck lookups** (`WEB_LOOKUP_WHEN_STUCK` - group "Internet lookups", on by default since 2026-11-23 and set per run; `graph/stuck_lookup.py`, `app/tools/lookups.py`): when a defect is shown to a fixer again after an attempt that did not close it and its text states a concrete error, the harness (not the model) looks the error up once per run: Stack Exchange's API (accepted answers), then GitHub's issue search, then the private SearXNG on developer engines (`web_search.py`). Only the cleaned error line (project and workspace names removed) and the stack's names leave the machine; results are defanged and labelled as leads (`tools/untrusted_text.py`), cached 7 days (`KEPT_DAYS`), and each lookup is a ledger record. Excluded: mutation findings. Optional keys raise limits (`STACKEXCHANGE_KEY`, `GITHUB_TOKEN`). The switch is off in code; the compose file and each run's own setting decide. It is read through `is_on` but is not listed in `observability/provenance.SWITCHES` or the admin groups as of this reading (unverified whether a later change adds it).
- **Research shares**: a stage visit may make at most 8 documentation reads, 12 registry lookups and 8 web lookups (`tools/research.py`); past it the stage is told to write from what it has; what was found is carried to a fresh attempt (`agents/carry_over.py`).

### 7.7 Steering and dynamic instruction injection

Steering and plugin instructions are one mechanism (3.5). `GET|POST /runs/{id}/steering` (Part 2) writes notes to `.harness/steering.json`; the instruction middleware adds the stack's guidance and the run's notes to every model call from the next call on; nothing is interrupted. A build stage, draft or rewrite that drops a declaration the pack holds (for example the build's jar name) is told the file and the exact line to restore before it returns (`entry_exports.what_a_stage_broke`, fed through the same post-write diagnostics as compiler findings). A note's first delivery marks it read by that stage (stream event and `steering_applied` record); a withdrawn note reaches no call. `where_things_stand` (`PH.1`) can add where the sprint stands to a fix request and `project_graph.with_the_neighbourhood` a defect's files' one-hop neighbours.

---

## 8. Tools

### 8.1 Workspace readers and editors (`app/tools/agent_toolkit.py`, `app/tools/repository.py`)

| Tool | Behaviour and guards |
|---|---|
| `ls`, `read_file`, `glob`, `grep` | from the deepagents filesystem backend, wrapped (`workspace_backend.py`) so `.agent-home` and installed-package folders (`vendor`, `node_modules`, `.venv`, `site-packages`) stay out of listings and searches (language-table `installed`). A file under `MOST_LINES_READ_WHOLE` = 400 lines is read whole, a longer one by windows with a note. A read of a version already seen returns the same bytes: after the first repeat the stage is told, then the read tool is withheld (refused when `STABLE_TOOLS`); project memory answers a read of a held file with a pointer; the repeated-query guard (`agents/repeated_queries.py`) covers listings and searches. |
| `write_artifact`, `edit_artifact`, `replace_lines`, `delete_artifact`, `move_artifact` | the single-writer guards of 3.4; a file its language's parser rejects is refused with the parser's location; a stale edit (the file changed after the read) says what changed (`tools/seen_content.py`); a reply's edits to one file that parse only together are made as one edit (`agents/edits_together.py`); an edit batch is grouped per path (`agents/line_batches.py`); `docs/` is the workflow's. Gated by approval when `auto_approve` is off. |
| `changed_since_sprint` | the diff against an accepted sprint's commit |
| `read_command_output` | a long command output kept out of context by reference (`tools/journal.py`, under `DATA_DIR`, not the workspace); a lost reference is answered with this run's own entries; a reference missed twice is refused |

### 8.2 Terminal and validation (`run_terminal_command`, `run_validation`; `app/tools/sandbox.py`)

- Commands are **argv lists, never strings**; no shell, so `&&`, `|`, `;`, `$(...)` reach the program as words and `cd` is not a program (`working_directory` is a parameter).
- The executable must be in the role's allowlist (`ROLE_EXECUTABLES`) united with the toolchain of every language the stack names (`TOOLCHAINS`, pinned by `pin_project_stack`). Argument forms that turn an allowed program back into an arbitrary one (`python -c`, `node -e`, `npm exec`, inline code for any interpreter) are refused with the advice to save a file instead. Servers are refused with advice (the acceptance config starts the product). Variable assignments on the command line are refused with an instruction.
- Containment: no network except the `install` category; bounded memory, CPU, processes, file size; minimal environment; a free `ACCEPTANCE_PORT` per command; timeouts per category (`install` 300 s, `build` 180, `test` 300, `default` 120, `probe` 60, `start` 20, `dry-run` 30) scaled per toolchain (`TOOLCHAIN_TIMEOUT_SCALE`: Rust 4.0, Java 3.0, ...) up to 900 s; a command is refused before it starts when the container lacks memory (`resources.py`), which converts an OOM into a result the model can read. Output is captured as head and tail with a digest, never whole (`bounded_output.py`); a test summary line ends a command early.
- Modes: `container` (a container per command, fails closed with no runtime) or `in-container`. Execution is opt-in (`ALLOW_COMMAND_EXECUTION`). Part 2 covers deployment and security.
- A command that only looks at files while the looking tools are withheld is refused (`_a_look_with_the_looking_tools_withheld`); a harness-run command is never withheld by agent repeat guards.
- Installs: the dependency gate and egress check (5.7). A runtime the image lacks is installed per project by `use_runtime` from the runtime's own distribution, checksum-verified, into a shared cache put first on that project's PATH only (`tools/runtimes.py`).

### 8.3 Package registry, docs, web (`look_up_package`, `read_docs`, `search_the_web`, `read_web_page`)

- `look_up_package(ecosystem, name)` (`tools/package_registry.py`): the registry each ecosystem installs from (npm, PyPI, crates.io, Go proxy, Maven, NuGet, Packagist, RubyGems and the like), fixed host per ecosystem, name validated before it enters a path; returns version, the runtime it needs, peer dependencies, with free text cut to 300 characters, beside the runtime version this environment has.
- `read_docs(name, topic, ecosystem)` (`tools/docs.py`): the project's own `llms.txt` index for frameworks that publish one, else the package's README from its registry (or a Go module's repository); 6,000-character excerpts.
- `search_the_web` / `read_web_page` (`tools/web_search.py`): a private SearXNG on the compose network (`SEARXNG_URL`, off when unset or `WEB_SEARCH_ENABLED` false); a page is read only from a public address; results are defanged. All three outward tools share the stage's research shares (8.1's counterpart in 7.6).
- `module_exports(module)` (`analysis/package_exports.py`): what an installed package really exports.
- **Untrusted text** (docs, pages, search results, MCP answers) is defanged before a model reads it: shapes that look like a tool call or a chat template's special tokens are replaced by a marker (`tools/untrusted_text.py`) and capped.

### 8.4 MCP

`app/tools/mcp_tools.py` gives stages tools from MCP servers: the owner's (`HARNESS_MCP_SERVERS`, one JSON entry per server with transport, URL, headers with `${ENV}` expansion, the tools exposed and the roles that get them, answers capped at 6,000 characters) and the **official** server of a library the product builds on, found in the MCP Registry and verified as the library's own (reverse-DNS namespace checked against its domain or the GitHub account; remote only; only tools that declare themselves read-only; `tools/mcp_registry.py`, `.harness/mcp-official.json`).

### 8.5 Page view

`look_at_page(path, viewport)` (`tools/page_view.py`): starts the product exactly as the acceptance suite does (the project's Playwright configuration and server command, a free port), opens one path in a real browser and returns the accessibility tree (the roles and names a test finds controls by), the page's own errors and failed requests. For a fixer, a build model that reads images is also shown the page screenshot (`agents/page_screenshots.py`, `MODEL_READS_IMAGES`).

### 8.6 Version control, journal, memory

`tools/version_control.py` commits per accepted milestone and per batch and snapshots stages; everything degrades rather than raises (no git, nothing to commit). `analysis/project_memory.py` and `agents/project_memory.py` hold per-file purpose, interface and last writer so later stages need not re-read. `agents/context_budget.py` derives every budget (compaction trigger at about 80% full, tail kept, spec share, per-command output cap, reply ceiling) from one number, the model's context window.

---

## 9. Switches and measurement

### 9.1 How a switch resolves

`app/switches.py` is the registry. `is_on(name, default)` resolves in this order:

1. **Built-in fix** (`BUILT_IN`, 53 names as of this reading): always on; only a host environment variable set off turns one off, logged once; stored admin and per-run settings are not read for them.
2. **The run's own setting** (`for_the_run`): set when the run starts (`loop.sh bench --off NAME`, `SWITCHES_OFF`/`SWITCHES_ON`), read from the run's record by the run the call belongs to (graph config or worker task), cached 30 s. Two runs on one deployed harness can be the two arms of a measurement with no deploy between them.
3. **The admin page's stored setting** (`stored`): stored with the runtime settings and beats the environment in every process within the settings cache's few seconds; read only when `SWITCH_OVERRIDES_FROM_SETTINGS` is on (the compose file turns it on), so tests and scripts never query a database for a switch.
4. **The environment variable** of the switch's name (`on`/`off`, `1`/`0`, `true`/`false`, `yes`/`no`).
5. **The bundle**: a bundled feature follows its bundle's run setting, stored setting or variable.
6. **The module's `ON_BY_DEFAULT`** (`default`).

Each module exposes `enabled()` through `is_on`. `observability/provenance.SWITCHES` maps 117 switch names to the module that reads each, so every run's KPI row records which were on and which fired (`observability/switch_firing.py`, `loop.sh effects`).

### 9.2 Kinds

| Kind | Rule |
|---|---|
| **Built-in** (`BUILT_IN`) | a fix for a demonstrated fault, a saving that changes no outcome, or a check that is quality (it changes what a run proves or how it repairs), always on, no switch, not listed as a switch; owner rule: "if it was a bug, it is fixed, no switch for bugs" |
| **Bundles** (`BUNDLES`, 4) | premium features behind one switch each: `PREMIUM_MODEL_TUNING` (per-model guidance, steering at the tail, reply caps, thinking off where it only burns time, `GUIDE_*`), `PREMIUM_PROJECT_INTELLIGENCE` (shared facts, canonical memory, code graph, lessons, decision ledger, naming standard), `PREMIUM_DEEP_VERIFICATION` (mutation-guided tests, regression contract, screenshot rubric, release audits and documents, assumptions gate, ask-specification), `PREMIUM_CHANGE_REQUESTS` (follow-up runs) |
| **Optional experiments** (`GROUPS`, 29 names in 9 groups) | non-quality improvements, measured: Context and cost, Efficiency, Setup scope, Review gates, Contract probes, Unit test signal, Drafting order, Recurring causes, Internet lookups. Some ship on with a recorded reason (`EXPERIMENTS_ON`) and carry an automatic rule: off at once if a run it fires in loses a hidden test or takes 1.5x its family's five-run active minutes |
| **Independent switches** | read through `is_on` with their own `ON_BY_DEFAULT`, outside the admin groups |

Policy: an efficiency change is kept only with measured no loss; "being measured" verification checks that held moved to `BUILT_IN`; a switch that hurts is reworked or removed; a change that moves no hidden score or KPI is parked.

### 9.3 Measuring register

`docs/measuring.md` is the one list of everything under measurement; STATE, the handovers, the status board and the plan point to it. Its switch table is **generated**: `scripts/loop/loop.sh measuring` runs `scripts/loop/switch_register.py`, which rewrites the block between `<!-- switches:generated -->` markers from the KPI ledger and the scored runs. One row per switch: group, default, runs on, fired, runs off, mean hidden score and active minutes on each side, verdict ("not measured: needs N more on and M more off" until each side has `LEAST_RUNS` = 2 scored runs on one harness commit). Rules in the register:

- A change in doubt is built behind a switch and measured: two runs per family with it on and two with it off on one harness SHA (`loop.sh kpi`, `kpi_ledger.py switch-arms <ledger> <sha> NAME <family>`); a mixed-version run counts for neither arm.
- Measure/Fix: a Measure run is one frozen harness SHA with no deploys into it, two runs per family, scored by hidden tests only; a bug found is filed for the Fix batch. A fix batch that moves no hidden score or KPI is parked. A mid-run deploy marks the run `mixed_versions`.
- Verdict: **kept** (moves to `BUILT_IN`) when no hidden or quality score falls and its target KPI moves; **parked** (off, kept in code) when nothing moves; **removed** when it hurts. Every audit says which arm the live runs are in.
- Start the off arm with `SWITCHES_OFF="NAME" loop.sh bench <family>` (or `SWITCHES_ON` for a switch that ships off) and the other arm without, on one deployed SHA.

Other measurement tools: `scripts/loop/effects.py` (did each fix or switch fire and help), `check_precision.py` (precision of each suite check), `gap_precision.py`, `kpi_ledger.py`, `impact.py`, `disputes.py`, `redundant_reads.py`, `run_timing.py`. The loop procedure and quality gates around them are Part 2.

Prompt size switches (LF.1182, `agents/prompt_size.py`, all off until measured): `QA_PROMPT_TRIMMED` keeps only the stack guidance about tests and the role's own lessons for the suite writer and QA lead; `REVIEWER_SHAPED_PLUGIN_CONTENT` keeps only the review lines for review roles; `LEAD_REPLAN_REQUEST_SMALLER` holds whole only the files the last attempt planned and changed on a re-plan, and is never longer than the request it replaces. Each choice is made once per run so the prompt bytes stay stable.

## 10. System architecture and deployment

### 10.1 Services at a glance

One image (`Dockerfile`, multi-stage) serves both the API and the worker. The web UI is built into it. Compose project root: `docker-compose.yml`, with overlays for dev, prod, sandbox and the owner's local overrides.

| Service | Image / owner file | What it does | Port / exposure |
|---|---|---|---|
| `app` | built from `Dockerfile`; `src/app/server/api.py` (`create_app`) | FastAPI control plane under gunicorn + uvicorn workers (`WEB_CONCURRENCY`, default 4; `WEB_TIMEOUT` 120). Serves REST, the WebSocket event stream, `/metrics`, and the built SPA from `langchain-ui/dist` (catch-all route). | `${APP_PORT:-8000}:8000`; limits 2 CPU / 2 GB |
| `worker` | same image; `src/app/server/tasks.py` | Celery worker (`celery -A app.server.tasks worker`, `--concurrency=${CELERY_CONCURRENCY:-2}`, `--max-tasks-per-child=50`). Runs the LangGraph workflow, calls model servers, runs commands (sandbox), holds the toolchains. | none; limits 2 CPU / 8 GB |
| `db` | `postgres:15-alpine` | Runs table, users, audit log, runtime settings/secrets, model profiles, plugin instructions, LangGraph checkpoints. | data in `${PGDATA_DIR:-./data/postgres}`; 1 GB limit; override publishes `127.0.0.1:5433` |
| `redis` | `redis:7-alpine` | Celery broker and result backend, event history/pub-sub, tickets, rate limits, locks. Password required (`REDIS_PASSWORD`), AOF on, `maxmemory 512mb`, policy `noeviction`. | internal; volume `redisdata` |
| `searxng` | `searxng/searxng` (pinned tag) | Private metasearch for the agents' `web_search` tool; settings in `docker/searxng/settings.yml`. | `expose 8080` only (compose network) |
| sandbox containers | `harness-sandbox-<toolchain>:pw<playwright>`, `mcr.microsoft.com/playwright`, `node:24-slim`, `python:3.12-slim`, `rust:1-slim` | One throwaway container per agent command (section 10.4). Started by the worker through the Docker socket (or a socket proxy). | none |
| `docker-proxy` (sandbox overlay) | `tecnativa/docker-socket-proxy` | Gives the worker a filtered Docker API: `CONTAINERS`, `POST`, `IMAGES`, `INFO`, `VERSION` allowed; `EXEC`, `BUILD`, `NETWORKS`, `VOLUMES`, `SWARM` denied. | internal `2375` |
| `proxy` (prod overlay) | `caddy:2.8.4-alpine`, `deploy/Caddyfile` | TLS front: HSTS, CSP, gzip, reverse proxy to `app:8000`. | `80`, `443` |
| model servers | the owner's, outside compose | LM Studio / llama.cpp-style OpenAI-compatible servers on the host (section 10.5). Never started, loaded or changed by the harness. | host `:1234`, `:8888` |

| preview containers (`PRODUCT_PREVIEW`, off) | the product's own start command, `src/app/server/preview_worker.py` | One container per run's preview, from a scratch copy of the workspace, with the sandbox's flags and a secret-free environment; idle stop after 15 min, orphans cleared at worker start. The product listens on the preview port + 1000; a Node forwarder in the same container serves the preview port on every interface, so a product bound to loopback is reachable. The app starts a preview only while the worker's preview heartbeat (`devflow:preview:worker`) says it runs commands in their own container. Settings: `PRODUCT_PREVIEW_NETWORK`, `_ORIGIN`, `_PORTS`, `_IDLE_MINUTES`, `_TOKEN_MINUTES`, `_START_SECONDS`. | internal network `devflow-preview` (only the app joins it), ports 42000-42019 |

Not in compose: MinIO/S3 (the object store defaults to a local folder, section 16), Prometheus (the app only exposes metrics), and the `sandbox-broker` (built, not wired; section 10.4).

### 10.2 Compose files and overrides

| File | Purpose |
|---|---|
| `docker-compose.yml` | Base. Defines the shared `x-app-env` anchor (every environment variable the app and worker read, with defaults), the five services, volumes `redisdata` and `appdata`. `REDIS_PASSWORD` is mandatory (`${REDIS_PASSWORD:?...}`; `scripts/setup-env.sh` writes `.env`). |
| `docker-compose.override.yml` | Loaded automatically by `docker compose`. Machine-local: publishes Postgres on `127.0.0.1:5433`. Per `docs/STATE.md` it is git-ignored and the owner's; a pre-commit guard (`scripts/loop/install_hooks.sh`, `.githooks/pre-commit`) keeps local compose edits out of commits. |
| `docker-compose.dev.yml` | `ENV=development`, mounts `./src` read-only, runs uvicorn with `--reload`, relaxes secrets (dev-only JWT key, admin password), allows the Vite origins. |
| `docker-compose.prod.yml` | `ENV=production`, closes the app's published port (`ports: !reset []`), adds the Caddy `proxy`. |
| `docker-compose.sandbox.yml` | Container-mode execution: worker gets `SANDBOX_WORKSPACE_VOLUME` (the data volume name), `DOCKER_HOST=tcp://docker-proxy:2375`, `SANDBOX_NODE_IMAGE`; drops the raw socket mount; adds `docker-proxy`. A commented block replaces the proxy with the sandbox broker (10.4). |

Image: `node:24-slim` builds the UI (`npm run build` runs `tsc -b`, so a type error fails the image build) and installs TypeScript 6.0.3 and Pyright globally (used by the write tools to parse agent-written `.ts/.tsx/.jsx` and `.py`). A Python 3.12 builder installs exactly the `uv.lock` versions. The runtime stage adds git, ripgrep, docker-cli, Chromium libraries, Node, JDK 21 + Maven, Rust, Ruby + Bundler, PHP + Composer, Go (with gotestsum), .NET 8, cargo-nextest, and Playwright's Chromium for the non-root `appuser` (uid 10001). `HARNESS_COMMIT` is baked in as a build arg (read by `observability/provenance.py`). The image copies only `src/`, so `benchmarks/*/hidden` never ships in it.

### 10.3 Volumes and data folders

Named volume `appdata` is mounted at `/app/data` in both `app` and `worker` (`DATA_DIR=/app/data`). Host-side `data/` in the repo (git-ignored) is a different thing: the loop's own state. Both are described here.

| Location | Contents | Owner |
|---|---|---|
| `/app/data/workspaces/<tenant>/workspace-<run_id>/` | One working directory per run: the product, `docs/` (rendered documents), `.harness/` (harness records, hidden from agents), `.github/` added at release. Allocated only by `server/workspaces.py` under `WORKFLOW_WORKSPACE_ROOT`; the request may choose a label, never a path. | worker |
| `/app/data/uploads/` | Uploaded briefs and codebase archives, with an owner marker per upload. | app |
| `/app/data/transcripts/<run_id>.jsonl` | Full per-run transcript (section 13). | worker |
| `/app/data/ledger/`, `/app/data/journal/` | Every command run (argv, dir, category, exit, duration); full command outputs (retention `CTX_JOURNAL_RETENTION_HOURS`, default 72). | worker |
| `/app/data/context/` | Compaction context store (`CTX_STORE_ROOT`, retention `CTX_CONTEXT_RETENTION_HOURS`). | worker |
| `/app/data/objects/` | Local object-store copies (default backend). | app/worker |
| `/app/data/model-fitness/` | Per-model measurements: tool diagnosis, reply salvage, deep diagnosis/steering profile, capabilities, sampling (`models/registry.fitness_dir`), plus `_diagnosis-status.json`. | worker |
| `/app/data/downgrades/<run>.txt` | Records that a run's judgement model was replaced by the default (`models/roles.py`). | worker |
| `/app/data/lookups/` | 7-day cache of external error lookups (`tools/lookups.py`). | worker |
| `/app/data/prometheus/` | Multiprocess metrics files. | app |
| `/app/data/loop/gate/` | The model-call gate used by deploys (`models/call_gate.py`: `hold` and `inflight/`). | worker, `loop.sh` |
| `/app/data/ratings`, `notified/`, `corpus/` | Owner ratings, sent-notice markers, harvested reader inputs. | app/loop |
| host `data/postgres` | Postgres files (`PGDATA_DIR`). | db |
| host `data/backups/<date>/` | Nightly `langchain.dump` copies (section 16). | `loop.sh backup` |
| host `data/kpi/` | `<run>.json` per-run KPIs and `ledger.csv` (one row per run, 100+ columns). | `loop.sh kpi` |
| host `data/bench/` | `<run>.json` hidden-test score results; `mutation/` results. | `loop.sh score` |
| host `data/loop/` | Loop state: `current_run.txt`, `ops.env` (git-ignored `BACKUP_DIR`, `RETENTION_DAYS`), `suite.log`, `suite-production.log`, build/deploy/nightly/score logs, `deploy.lock`. | `loop.sh` |
| host `data/corpus`, `data/documents` | Harvested reader inputs the suite replays; generated unit/acceptance-test documents per finished run. | `loop.sh` |
| host `ledger/`, `transcripts/` (repo root) | Leftovers from running tools on the host with `DATA_DIR` unset; git-ignored scratch. | none |

### 10.4 Container-mode sandbox execution

Owner: `src/app/tools/sandbox.py` (`SandboxExecutor`), with `tools/install_egress.py`, `tools/dependency_gate.py`, `tools/runtimes.py`, `tools/resources.py`, `stacks/languages.py`, `stacks/packs/_sandbox.py`.

**Command shape.** Commands are argv lists, never shell strings. The executable is matched exactly against a per-role allowlist (plus the toolchains of the languages the stack names); arguments are screened for forms that turn an allowed program into an arbitrary one (`python -c`, `node -e`, `npm exec`, ...). Servers are refused with advice (the acceptance config starts the product). It fails closed: with no container runtime it raises rather than running on the host.

**Execution modes** (`SANDBOX_EXECUTION_MODE`; compose default `container`; `ALLOW_COMMAND_EXECUTION` defaults false and the deployment turns it on):

| Mode | Behaviour |
|---|---|
| `container` | One `docker run --rm` per command. Needs a Docker endpoint reachable from the worker (the raw socket via `DOCKER_SOCKET`, or `DOCKER_HOST` to the proxy). The harness's own runs of product code (start probe, specs, compiler checks) also go through it (`product_code_runs_in_its_own_container`), so product code never shares the worker's secrets. |
| `in-container` (aliases `local`, `direct`) | The command runs as the unprivileged user inside the worker with rlimits. Weaker: the command can reach what the worker can. `server/process_privacy.py` marks the worker's own processes non-dumpable so a same-user command cannot read their `/proc/<pid>/environ`. |

Each worker records at startup whether commands can run (`server/execution_readiness.py`, in Redis); a run is refused before its first model call when they cannot (`GET /api/health/commands` feeds the start form).

**Container flags** (`SandboxExecutor._run`): `--network none|bridge`, `--memory` and `--memory-swap` equal (no swap), `--cpus` (`SANDBOX_CPU_LIMIT`, 2), `--pids-limit` (`SANDBOX_PIDS_LIMIT`, 512), `--cap-drop ALL`, `--security-opt no-new-privileges`, `--read-only`, `/tmp` as a 256 MB `noexec` tmpfs, the workspace mounted at `/workspace` (a volume sub-path when `SANDBOX_WORKSPACE_VOLUME` is set), `-u uid:gid` of the worker. Memory is `SANDBOX_MEMORY_LIMIT` (1g) or more where a pack says its toolchain needs it; commands that start Node get at least 4 GB (`NODE_TOOLCHAIN_MEMORY`). The environment is minimal: `LANG`, `LC_ALL`, `TZ`, `HOME`/`TMPDIR` inside the workspace, toolchain settings, a free `ACCEPTANCE_PORT`; the worker's secrets are not passed. Before starting, `tools/resources.py` reads the cgroup's free memory and refuses the command when it would not fit (a refusal is a tool result; an OOM kill would orphan the run).

**Images.** Chosen by `_image_for`: the pack's `sandbox_image`; else a version pin from `.harness/runtimes.json`; else by executable: node tools use `SANDBOX_NODE_IMAGE` (default `node:24-slim`; the sandbox overlay sets the Playwright image), Python tools `SANDBOX_PYTHON_IMAGE`, `cargo` `SANDBOX_RUST_IMAGE`, `go` `SANDBOX_GO_IMAGE`, everything else the language table's built image (`stacks/languages.image_for_executable`), last `SANDBOX_BASE_IMAGE` (`debian:12-slim`). Toolchain images are built from `deploy/sandbox-images/{dotnet,go,java,php,python,ruby,rust}/Dockerfile` by `scripts/loop/build_sandbox_images.sh`, tagged `harness-sandbox-<toolchain>:pw<playwright version>` (version read from `stacks/packs/_javascript.py`) and each `FROM` the Playwright image. The proxy refuses builds, so images must be built on the host first; a pack needing only Node uses the Playwright image, pulled on first use. A project that needs another runtime version gets it from `tools/runtimes.py`: downloaded from the runtime's own host (fixed list: nodejs.org, go.dev, dl.google.com, api.adoptium.net, github.com), checksum-verified, cached, and put first on that project's PATH.

**Network categories.** `NETWORK_CATEGORIES = {"install"}`: only install commands get `--network bridge`. A command in another category gets `bridge` only when its stack pack sets `fetches_while_building` (toolchains that restore packages while building or testing) or while the harness starts the delivered product for a toolchain that restores when it starts (`with_a_stranger_s_network`). Everything else gets `none`.

**Egress policy.** There is no network-level egress filter (the planned `net-floor` sidecar is approved but not built). Egress is controlled at the command level:
- `tools/install_egress.py`: every host an install names (command line, `--registry/--index-url/...` flags, `.npmrc`/`pip.conf`/`Gemfile`/`composer.json`/`pyproject.toml`/..., dependency URLs in manifests) must be on `ALLOWED_HOSTS` (npm, PyPI, crates.io, Go proxy, RubyGems, Packagist, NuGet, Maven, Gradle, pub.dev, hex.pm, GitHub/GitLab/Bitbucket) or a subdomain. `INSTALL_ALLOWED_HOSTS` adds hosts; `*` lifts the check. The harness's own service names (`db`, `redis`, `app`, `worker`, `searxng`, `host.docker.internal`, `localhost`, `langchain-*`, `devflow-*`) are refused even with `*`.
- `tools/dependency_gate.py` (always on): before an install, each package is looked up in its registry; a name the registry lacks, or a package first published fewer than `DEPENDENCY_MIN_AGE_DAYS` (14) days ago, is refused. An unreachable registry or an unknown ecosystem lets the install through and records the verdict in `.harness/dependency-gate.json`. `INSTALL_SCRIPTS_SKIPPED` optionally runs installs with dependency scripts disabled.

**Docker API restriction.** The sandbox overlay uses `tecnativa/docker-socket-proxy`, which filters by endpoint only, not by request body. `deploy/sandbox-broker/` (`broker.py`, `validator.py`, stdlib-only) is a stricter replacement: it passes only the calls `docker run --rm` and `docker kill` make and only a create shaped like the sandbox's (allowed image prefixes, non-root user, `CapDrop ALL`, `no-new-privileges`, read-only root, one volume mount of the workspace volume with a relative sub-path, bounded resources, network `none|bridge`). It is built but, in the committed compose, still commented out in `docker-compose.sandbox.yml`.

### 10.5 Model serving

**Where models live.** The harness is a client of OpenAI-compatible servers on the owner's machine, reached from containers as `host.docker.internal`. Two servers take runs: LM Studio on `:8888` (API key required) and `:1234` (no key). Both serve a Qwen3.6-35B-A3B MTP quantised build (per `docs/STATE.md`; the served names are whatever the owner loaded). The harness never loads, unloads or reconfigures a model; `scripts/loop/loop.sh ready` (`model_ready.py`) must print `ALL READY` before any run is started.

**Provider selection** (`config.py`, `models/__init__.py`, `models/endpoints.py`). `LLM_PROVIDER` is `local` (default), `openai`, `anthropic` or `gemini`. `OPENAI_BASE_URL` defaults to `http://host.docker.internal:1234/v1` in compose. `endpoints.is_self_hosted` decides self-hosted vs hosted from the address (loopback/private/CGNAT/`.internal`/single-label names are self-hosted; `OPENAI_ENDPOINT_KIND` overrides). Self-hosted endpoints get chat-template thinking switches and the harness's own retrying client (`CompatibleChatOpenAI`); hosted ones do not. `reached_from_here` rewrites `localhost` to `host.docker.internal` inside a container while keeping the `Host` header the server expects. `ALLOWED_MODEL_HOSTS` (optional) restricts which hosts the settings API accepts. `MODEL_REQUEST_TIMEOUT_SECONDS` is 1800 in compose; `models/__init__._request_timeout` and `paced_timeout` derive timeouts from measured generation pace.

**Settings that describe the model.** `MODEL_CONTEXT_WINDOW` (compose default 100000), `MODEL_MAX_OUTPUT_TOKENS`, thinking mode and effort, `MODEL_READS_IMAGES`. Every context budget derives from the window (`agents/context_budget.py`). `models/server_profile.py` reads the server's `/props` once per run segment (slots, per-slot context, quantisation) so the budget and parallel cap use the per-slot window; `models/window_probe.py` can measure the real window from the limit a deliberately oversized request is refused at; `HARNESS_MAX_PARALLEL` (default 6) caps fan-out.

**Per-run model pinning** (`models/model_pin.py`, `server/run_store.py` columns `model_pinned`, `model_last`). A run records a snapshot of the non-secret model keys it last ran with. Unpinned, it follows the global settings; pinned (`POST /api/runs/{id}/model-pin`, or `pin_model`/`pin_base_url`/`pin_model_name` at start, or `PIN_MODEL=1 PIN_URL=... PIN_MODEL_NAME=...` through `loop.sh`), it keeps its snapshot whatever the settings become. `PinTransport` sits under each client's httpx session and, per request, rewrites base URL, `Host`, `Authorization` and the JSON `model` field only when the run's model differs from what the client was built for. The credential used is the destination endpoint's own; one server's key is never sent to another. The state is cached for 2 s because the API writes the flag and the worker reads it. This is what lets two runs use two ports at once.

**Two tiers: build and judgement** (`models/roles.py`). The default model builds. An optional judgement ("frontier") model, configured through runtime settings `judgement_*` or `JUDGEMENT_MODEL/PROVIDER/BASE_URL/API_KEY/CONTEXT_WINDOW/MAX_OUTPUT_TOKENS`, runs the stages that judge (architect, QA/acceptance, test rounds, fixes, security and milestone reviews, code review). `PLAN_ON_JUDGEMENT_MODEL` (default true) also puts intake, stack, sprint plan and work orders on it. `ESCALATE_AFTER_ATTEMPTS` (default 2) hands a stage or a defect to it after that many failures on the build model. A run started with "use the frontier model" off (`local_only`) keeps every stage on the build model. If the judgement model cannot be built, the run uses the default and records a downgrade (`data/downgrades/`) that surfaces in the run's history and its completion gaps. `models/frontier_check.py` verifies it is configured and answering (a model-list read, never a model call) before a run that asks for it may start.

**Measured model tiers.** Separate from build/judgement. A model not seen before is diagnosed once at its first run segment (`tasks.execute_workflow_run`): tool calling (`models/diagnostics.py`), reply salvage (`reply_salvage.py`), deep diagnosis and steering profile (`deep_diagnosis.py`, `guidance.py`), capabilities (`capabilities.py`), five scripted tool-call checks (`fitness.py`). The result is kept under `data/model-fitness/` against the served name and applied (reply caps, which per-model guides to send). `guidance.tier_of` assigns `strong`, `standard` or `weak`; the supported matrix and guide selection follow the tier. The Settings page can rerun a diagnosis (`POST /api/settings/model/steering/diagnose`, refused while a run is live). Sampling per mode (`sampling_modes.py`) is derived and kept but sent only when the owner turns on "send sampling by mode".

**Hosted-model option and cost tracking** (`observability/cost_tracker.py`, `server/runner.py`). Cost accounting is per run id. A local provider is priced at nothing; a model absent from the price table is counted as unpriced, and every summary reports `priced_requests`, `unpriced_requests`, `fully_priced`. List prices (USD per million tokens, `PRICES_AS_OF`) cover the Anthropic families; `MODEL_PRICES_JSON` corrects rates without a release. `MAX_RUN_COST_USD` (compose default 8) parks a run at status `waiting_for_budget` with a `budget_pause` event; `MAX_RUN_TOKENS` bounds tokens for any model; the pause is resolved by raising the ceiling and resuming, or cancelling. Provider keys are entered on the Settings page (admin) and stored encrypted (section 15). A call refused for exhausted quota or credit is recognised by phrase (`models/quota.py`) and parks the run instead of failing it. Hosted-model runs happen only when the owner starts or instructs them.

### 10.6 Configuration and environment variables that matter

Anything in `x-app-env` is set for both `app` and `worker`. Precedence for model and switch keys: per-run override, then the admin-page stored value (Postgres), then the compose/`.env` environment, then the code default. Secrets are listed by name only.

| Group | Variables |
|---|---|
| Identity and auth | `ENV` (`production` default; `development` relaxes secret rules), `JWT_SECRET_KEY` (32+ chars; known dev values refused outside dev), `ADMIN_PASSWORD`, `ACCESS_TOKEN_EXPIRE_MINUTES` (60), `REFRESH_TOKEN_EXPIRE_DAYS` (7), `ALLOWED_ORIGINS`, `TRUSTED_PROXIES`, `METRICS_SCRAPE_TOKEN` |
| Storage and queue | `DB_URL`/`AUTH_DB_URL` (from `POSTGRES_*`), `REDIS_URL` (from `REDIS_PASSWORD`), `CHECKPOINTER_TYPE` (`postgres` default), `DATA_DIR`, `WORKFLOW_WORKSPACE_ROOT`, `WORKFLOW_UPLOAD_DIR`, `OBJECT_STORE_*`, `PGDATA_DIR` |
| Model | `LLM_PROVIDER`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`/`GEMINI_API_KEY`, `JUDGEMENT_*`, `MODEL_CONTEXT_WINDOW`, `MODEL_MAX_OUTPUT_TOKENS`, `MODEL_REQUEST_TIMEOUT_SECONDS`, `MODEL_PRICES_JSON`, `ESCALATE_AFTER_ATTEMPTS`, `PLAN_ON_JUDGEMENT_MODEL`, `OPENAI_ENDPOINT_KIND`, `ALLOWED_MODEL_HOSTS` |
| Run bounds | `MAX_RUN_COST_USD` (8), `MAX_RUN_TOKENS`, `MAX_CONCURRENT_RUNS`, `WORKFLOW_MAX_GATES` (1000), `WORKFLOW_MAX_GATES_PER_STAGE` (120), `WORKFLOW_MAX_REVIEW_RERUNS` (8), `HARNESS_MAX_PARALLEL` (6), `CELERY_TASK_TIME_LIMIT` (43500 s), `CELERY_TASK_SOFT_TIME_LIMIT` (43200 s), `RUN_SEGMENT_PAUSE_AT`, `RUN_MOST_SEGMENTS` (4), `STALL_MINUTES` (20), `GATE_NOTICE_MINUTES` (30) |
| Execution | `ALLOW_COMMAND_EXECUTION`, `SANDBOX_EXECUTION_MODE`, `SANDBOX_MEMORY_LIMIT`, `SANDBOX_CPU_LIMIT`, `SANDBOX_PIDS_LIMIT`, `SANDBOX_*_IMAGE`, `SANDBOX_WORKSPACE_VOLUME`, `DOCKER_SOCKET`, `DOCKER_HOST`, `SANDBOX_RUNTIMES_ENABLED`, `INSTALL_ALLOWED_HOSTS`, `DEPENDENCY_MIN_AGE_DAYS` |
| Lookups | `PACKAGE_LOOKUP_ENABLED`, `DOCS_LOOKUP_ENABLED`, `WEB_SEARCH_ENABLED`, `SEARXNG_URL`, `HARNESS_MCP_DISCOVERY`, `HARNESS_MCP_SERVERS`, `CONTEXT7_API_KEY`, `STACKEXCHANGE_KEY`, `GITHUB_TOKEN`, `WEB_LOOKUP_WHEN_STUCK` |
| Context | `CTX_COMPACTION_ENABLED`, `CTX_SOFT_TRIGGER_RATIO` (0.8), `CTX_SUMMARY_BUDGET`, `CTX_COMPACTION_MODEL`, `CTX_*_RETENTION_HOURS` (72) |
| Settings store | `SETTINGS_ENCRYPTION_KEY`, `SETTINGS_READ_ONLY`, `SWITCH_OVERRIDES_FROM_SETTINGS` (on in compose) |
| Notifications | `NOTIFY_WEBHOOK_URL`, `NOTIFY_EMAIL`, `SMTP_*` |
| Switches | `PREMIUM_*` bundles, grouped experiment switches, per-switch variables (defaults in compose `x-app-env`; catalogue in section 11.7 and Part 1) |
| Ops | `RECOVER_ORPHANS_ON_START` (true), `RUN_TRANSCRIPT` (true), `RUN_DELETE_KEEPS_RECORDS`, `RUN_EVENT_HISTORY_MAX` (5000), `RUN_EVENT_TTL_SECONDS` (30 d), `RATE_LIMIT_MAX_REQUESTS` (300 per 60 s), `LOGIN_MAX_ATTEMPTS` (5 per 300 s), `BACKUP_DIR`, `RETENTION_DAYS` (host-side, `data/loop/ops.env`) |

Unverified: the compose defaults for optional switches (for example `OBSERVATION_FOLDING` defaults to `on`, `BATCH_ACCEPTANCE_AUTHOR` to `off`) differ in places from the on/off list in `docs/STATE.md`; the host `.env` or the admin page may override them, and I could not read those.

---

## 11. Server and API

### 11.1 Process model

`app.server.api:create_app` builds the FastAPI app with a lifespan that starts the approval-timeout sweeper (`approval_timeouts.sweep_for_ever`) and stall notices (`stall_notices.py`), installs proxy-timeout diagnostics, and closes the Redis and run-store pools on shutdown. Middleware, in order: correlation id (`X-Correlation-ID`, validated, set on log lines), per-caller rate limit (`rate_limit.py`, Redis-backed, fails open; 429 with `Retry-After`), CORS (same-origin by default; credentials only with an explicit origin list), security headers (`nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, COOP). `/docs`, `/redoc` and `/openapi.json` exist only when `ENV` is a development value. `/metrics` (Prometheus) is served only with a `METRICS_SCRAPE_TOKEN` outside development.

Routers: `auth_router` (`auth.py`), `runs_router` (`runs.py`, prefix `/api/runs`), `progress_router` (`progress.py`, same prefix), `settings_router` (`settings.py`, `/api/settings`), `lessons_router` (`lessons_api.py`), `users_router` (`users_api.py`). `create_app` also holds the health routes and the SPA catch-all (`/api/*` and `/metrics*` never fall through to `index.html`).

### 11.2 Route groups

All routes need a bearer token unless noted. "op" = operator or admin, "admin" = admin only; unmarked = any active user. Runs are tenant-scoped: non-admins see only their tenant's runs.

| Group | Routes (file) |
|---|---|
| Auth (`auth.py`, `users_api.py`) | `POST /api/auth/token` (form login, no token), `POST /api/auth/refresh`, `POST /api/auth/logout` (bumps token version: signs out everywhere), `GET /api/auth/me`, `PATCH /api/auth/me/preferences` (appearance), `POST /api/auth/password`; admin: `GET/POST /api/users`, `PATCH /api/users/{username}` |
| Create and start (`runs.py`) | `POST /api/runs` (op; multipart brief documents, validated by `uploads.py`), `POST /api/runs/preview` (brief preview: criteria, ambiguity, supported-matrix note), `POST /api/runs/{id}/codebase` (op; archive for a brownfield run), `POST /api/runs/{id}/start` (op; settings below) |
| Product preview (`runs.py`, `preview.py`; `PRODUCT_PREVIEW`) | `POST/GET/DELETE /api/runs/{id}/preview` (op); `/api/runs/{id}/preview/app/{token}/{path}` (token in the path, no bearer) |
| Reviews mid-run (`runs.py`) | `GET/PUT /api/runs/{id}/review-policy` (op; 422 for an unknown point, 409 for a run not live; audited) |
| Control (op) | `pause` (`?at=boundary&ceiling=`), `resume`, `resume-with-direction`, `rewind-points` (GET) and `rewind`, `cancel`, `DELETE /api/runs/{id}` (terminal runs only), `clone`, `name`, `model-pin` |
| Read | `GET /api/runs` (paged list), `/compare`, `/outcomes`, `/{id}`, `/sprints`, `/usage` (time and tokens by stage), `/kpis`, `/doctor`, `/diagnostic-bundle`, `/transcript`, `/wizard`, `/stages`, `/artifacts` (+ `/download`, `/diff`), `/handover`, `/product` (+ `/summary`), `/how-to-run`, `/logs` (paged events), `/decisions`, `/evidence` (criteria from the harness's own run of the locked suite), `/changes` (+ `/{sha}`: per-stage commits and diffs) |
| Gates (op for writes) | `GET/POST /{id}/approval` (approve or reject a pending write/command), `GET/POST /{id}/review` (approve, request changes, skip; optional edited document upload, size capped), `GET/POST /{id}/steering` (notes), `GET/PUT /{id}/rating` |
| Live (`progress.py`) | `POST /{id}/events/ticket`, `WS /{id}/events/stream`, `GET /{id}/events?since=`, `GET /{id}/status` |
| Settings (`settings.py`) | `GET /api/settings` (op), `PUT` (admin), `POST /detect-context-window`, `PUT /local`, `PUT /frontier`, `GET /frontier/status`, `GET/POST /model/steering...`, `GET/PUT /model/capabilities` (+ `/fill`), `GET/PUT /model/sampling` (+ `/determine`), `PUT /model/steering/guides/{id}`, `GET /switches`, `PUT /switches/{name}`, `GET /models` and `DELETE /models/{id}` (saved profiles) |
| Lessons | `GET /api/lessons`, `POST /{id}/approve`, `POST /{id}/reject` (admin) |
| Health | `GET /api/health` (liveness, no auth), `/api/health/ready` (db, redis, celery ping, slot counts; 503 on error), `/api/health/server` (the build model's `/props`, never a model call), `/api/health/commands`, `/api/health/operator` (op: disk, database, runs/waiting/broker queue, model server, newest backup, harness commit), `/api/health/models` (admin: pings every configured model, billable), `GET /api/support-matrix` |
| Brownfield and change requests | Seeding (`seeding.py`): a workspace is materialised from a git clone (scheme and private-host checks, `SEED_ALLOWED_SCHEMES`, `SEED_ALLOW_PRIVATE_HOSTS`) or an extracted archive (path, link and size guards). Change requests (`change_request_runs.py`, switch `CHANGE_REQUEST_RUNS` under bundle `PREMIUM_CHANGE_REQUESTS`): `start` accepts `{"source": {"type": "run", "run_id": ...}}` naming a completed run of the same tenant; its product and history are copied in, the harness's old records (`.harness`, installs) are left behind, and the new run is a seeded run whose brief is the change. |

`start` body (`models.StartRunRequest`): `auto_approve`, `review_policy`, `reviewer`, `delivery_mode` (`fast`|`thorough`), `use_frontier_model`, `approval_timeout_minutes`, `name`, `switches` (per-run switch overrides `{NAME: bool}`), `pin_model`/`pin_base_url`/`pin_model_name`, `source` (git, archive or run), `workspace_label`, `allow_subdirectories`, provider/model overrides (secrets filtered out before persisting). Starting refuses early when commands cannot run, when a cost ceiling cannot hold, or when the (pinned) model is unreachable.

### 11.3 Run lifecycle

Statuses (`server/runner.py`): `created`, `running` (and `queued`), `waiting_for_approval`, `waiting_for_review`, `waiting_for_budget`, `paused`, `failed`, `cancelled`, `completed`. `RESUMABLE_STATUSES = failed | waiting_for_budget | paused | cancelled`. Every transition is a compare-and-set UPDATE on the `runs` row, so two concurrent actions cannot both win.

| Action | Mechanism |
|---|---|
| Start | `WorkflowRunner.start_run`: checks (commands can run, ceiling can hold, model reachable), persists settings, snapshots the model into the run, CAS `created` to `running`, then `_dispatch` -> Celery task `execute_workflow_run`. If `MAX_CONCURRENT_RUNS` is set and all slots are taken it raises `RunQueueFull` rather than queueing. |
| One segment | `tasks.execute_workflow_run` runs the graph until it pauses or ends. At segment start: server profile read, new-model diagnosis, a `provenance` record (harness commit, model, switches). A timer (`SEGMENT_PAUSE_AT_SECONDS`, derived from the soft time limit minus 2 h) asks the run to pause at its next stage boundary; the task then resumes it in a fresh Celery job, up to `RUN_MOST_SEGMENTS` (4), after which the run is left paused for a person. Celery is `task_acks_late=False`, `prefetch_multiplier=1`, visibility timeout above the task limit, and a Redis-backed first-delivery check drops a duplicate delivery. |
| Pause | `request_pause`: sets a stop flag with reason `pause`. A plain pause also revokes the Celery task (the interrupted stage restarts on resume). `at=boundary` waits for the stage to end, up to `ceiling` seconds, then revokes. The worker stops at a checkpoint boundary and records `paused`. |
| Resume | `resume_run`: refused for a run whose error starts `Interrupted:` (history cannot be trusted; clone instead). Re-checks commands, ceiling and model, then tries each resumable status in turn as a CAS to `running`, clears the stop flag, writes a `resumed` transcript record, and dispatches. If dispatch fails the row is put back. |
| Resume with a direction | Adds a steering note (section 11.6) to the workspace, then resumes. |
| Rewind | `rewind_points` lists each stage entry (one point per time a stage was entered, the checkpoint just before it ran). `rewind_run` needs a stopped or completed run (a running one is paused first), waits for the step in flight to finish (`server/driving.py`), then `graph.workflow.rewind_to`: restores the stage's workspace snapshot (a git snapshot taken at each stage start by `tools/version_control.py`), forgets the stage's conversation threads, clears pending gates, and continues on a new branch from that checkpoint; the old branch stays in history. A `rewound` transcript record makes the KPIs ignore the abandoned branch. Only to the start of a stage. |
| Cancel | Raises the cancel flag and revokes the task. A parked run (`CANCELLABLE_WHILE_PARKED`) is marked `cancelled` at once; a `running` row with no live worker is too. A cancelled run keeps its checkpoints and can still be resumed. |
| Clone | New run from the same documents, carrying the source's settings (auto-approve, delivery mode, model choice); a fresh start. |
| Delete | Terminal runs only; removes row, workspace, checkpoints, events, unshared uploads, transcript, ledger, journal and object-store copies (`run_retention.py`), keeping the audit-log line. `RUN_DELETE_KEEPS_RECORDS=true` holds transcript/ledger/journal. |
| Approval gates | A run with `auto_approve` false stops at gates (`waiting_for_approval`, `waiting_for_review`). `submit_approval` / `submit_review` CAS out of waiting and dispatch with the decision payload. `approval_timeout_minutes` makes a gate approve itself when it expires (swept once a minute); otherwise it waits indefinitely. Loop guards: `_GateCount` stops a stage that re-requests the same write forever (`MAX_IDENTICAL_GATES`), with per-stage (120) and per-run (1000) ceilings. |
| Budget | After each stage the runner checks `MAX_RUN_COST_USD` / `MAX_RUN_TOKENS`; over it, the run parks as `waiting_for_budget`. |

**Orphan recovery and restart.** A worker restart (every deploy) leaves rows `running` with no task. `tasks._recover_runs_their_worker_abandoned` runs on `worker_ready` (unless `RECOVER_ORPHANS_ON_START` is off): one worker takes a Redis lock, waits for the broker, and calls `manage.recover_orphaned_runs`, which marks a run `failed` with the `STOPPED_WORKER_MARKER` text only when a worker answered the broker and did not claim the run's task, and the row was not touched in the last 60 s; a recurring sweep repeats every 90 s on the Celery parent. Rows carrying the marker are then resumed from the last checkpoint, re-running only the interrupted node. If no worker answers, nothing is judged orphaned. `models/call_gate.py` lets a deploy hold new model calls and wait for in-flight ones before restarting. `manage.py` also offers `reconcile-runs`, `recover-orphans`, user administration and workspace/checkpoint retention commands.

### 11.4 Event bus and WebSocket stream

`server/events.py`: every run event is a `RunEvent` (`run_id`, `event_id`, monotonic `sequence`, `timestamp`, `stage`, `event_type`, `message`, redacted `metadata`; `extra="ignore"` so removing a field never breaks stored history). Event types: `stage_change`, `log`, `artifact`, `review_request`, `approval_request`, `approval_auto`, `approval_denied`, `budget_pause`, `error`, `complete`, `agent_message`, `tool_call`, `tool_result`, `review_decision`, `approval_decision`. Agent activity is one event per message or tool call, never per token; text is clipped (the transcript, not the stream, is the complete record).

Storage is Redis: a list per run (trimmed to `RUN_EVENT_HISTORY_MAX`, default 5000, TTL 30 days), a sequence counter (`INCR`), and a pub/sub channel (`CLOSE` ends the stream). Auth for the socket: the client first `POST`s `/events/ticket` with its bearer token and gets a single-use ticket valid 30 s, so no credential goes in a URL; `WS /events/stream?ticket=&last_event_id=` redeems it, re-checks the user and tenant, replays history after `last_event_id`, then streams live, pinging every 20 s. When the run ends the server sends `{"event":"closed"}`. `GET /events?since=` is the polling fallback; `GET /status` is a minimal spinner payload.

### 11.5 Run store schema

Postgres table `runs` (`server/run_store.py`, created and migrated idempotently under an advisory lock, `schema_lock.py`):

`run_id` (PK), `thread_id` (LangGraph thread), `status`, `current_stage`, `stage_meaning`, `created_at`, `updated_at`, `error`, `review_policy` (JSON), `reviewer`, `auto_approve`, `document_names`/`document_paths`, `repo_root`, `owner`, `tenant_id`, `task_id`, `cancel_requested` with `stop_reason` (`cancel`|`pause`), `model_overrides` (public keys only), `delivery_mode`, `local_only` (no frontier model), `approval_timeout_minutes`, `completion_gaps` (JSON: what the release knew it did not prove), `model_pinned`/`model_last`, `run_name`, `switch_overrides` (JSON), `paused_since`/`paused_seconds`. A trigger (`runs_pause_clock`) accumulates time in any stopped status (`paused`, `failed`, `cancelled`, `waiting_for_*`) in the database itself, so "active minutes" excludes every stretch the run was not working, however it was stopped. Indexes: `(tenant_id, created_at DESC)`, `owner`. Other tables: `users`, `audit_log` (`auth.py`), `runtime_settings`, `runtime_secrets` (`runtime_settings.py`), `model_profiles`, plugin instruction rows (`plugin_store.py`), and LangGraph's own checkpoint tables (`graph/checkpointing.py`: `PostgresSaver` with an explicit type allowlist; sqlite or memory only if `CHECKPOINTER_TYPE` says so).

### 11.6 Auth, roles and steering

Local accounts in Postgres, passwords hashed with bcrypt (a dummy hash is checked for unknown users so timing does not reveal them). Login is rate-limited per account and address (`LOGIN_MAX_ATTEMPTS`, in-process fallback if Redis is down). JWT HS256 access (60 min) and refresh (7 days) tokens carry `sub`, `role`, `tenant` and a token version; `logout` bumps the version, invalidating every token of that user. Roles: `operator` (default) and `admin`; `require_operator` admits both, `require_admin` only admin; an admin satisfies any role check. Runs and workspaces are scoped by `tenant_id`. `ENV` must be explicitly a development value to relax secret checks; production refuses a missing, short or published-development `JWT_SECRET_KEY`. Security-relevant actions write to `audit_log` (`record_audit`). The harness loop uses an operator account, never admin (section 15).

Steering (`server/steering.py`): `POST /runs/{id}/steering` stores a note in `.harness/steering.json` (text up to 2000 chars, scope `run` or `next_stage`, audience `all`, a stage group, or one builder role); the instruction-injection middleware (`plugins/middleware.py`) appends the newest (at most 5) to every model call from the next one on. Nothing is interrupted.

### 11.7 Settings, runtime settings and switches

`runtime_settings.py` stores admin-changed settings in Postgres (`runtime_settings`) so every process agrees and changes survive restarts; a stored value beats the deployed environment (`SETTINGS_READ_ONLY` refuses writes instead). Settable keys: provider, base URL, model name, context window, max output, thinking mode/effort, execution mode (linear/parallel), delivery mode, image reading, `judgement_*`, `escalate_after_attempts`, `plan_on_judgement_model`, Anthropic workspace id. Credentials (`openai_api_key`, `anthropic_api_key`, `google_api_key`, `judgement_api_key`, and per-endpoint keys) are write-only, stored Fernet-encrypted in `runtime_secrets` (key from `SETTINGS_ENCRYPTION_KEY`, else derived from the JWT secret); the API never returns one. Processes cache stored settings for `SETTINGS_CACHE_TTL` (5 s). `model_profiles.py` remembers each applied model configuration (keyed by provider, endpoint, name; never credentials) so the page can switch back.

Switches (`switches.py`, `server/switch_catalogue.py`): a feature is a built-in fix (always on, listed in `BUILT_IN`, no switch), a member of a premium bundle (`PREMIUM_MODEL_TUNING`, `PREMIUM_PROJECT_INTELLIGENCE`, `PREMIUM_DEEP_VERIFICATION`, `PREMIUM_CHANGE_REQUESTS`), or a grouped optional experiment (`GROUPS`: Context and cost, Efficiency, Setup scope, Review gates, Contract probes, Unit test signal, Drafting order, Recurring causes). Resolution for a switch, first match wins: the run's own override (`runs.switch_overrides`, read per run with a 30 s TTL), the admin page's stored value, the environment variable, the module's `ON_BY_DEFAULT`. Stored and per-run values are read only where `SWITCH_OVERRIDES_FROM_SETTINGS` is on (compose turns it on). `PUT /api/settings/switches/{name}` (admin) writes the stored value; `observability/provenance.SWITCHES` is the registry each run's KPI row records. The policy: bug fixes and quality changes are always on with no switch; only optional non-quality improvements get one, until measured.

---

## 12. The web UI

### 12.1 Stack and structure

`langchain-ui/`: React 19, TypeScript 6, Vite, Tailwind 4 (tokens mapped in `src/index.css`), react-router 7, axios, react-markdown + remark-gfm, lucide icons; tests with Vitest + Testing Library (44 test files). Built into the image and served by the app; there is no separate web server in production. `src/api/index.ts` is the single API client (`baseURL: '/api'`, bearer token from `localStorage`, one-shot token refresh on 401 via `lib/session.ts`); `src/types/api.gen.ts` is generated from the server's OpenAPI schema (`scripts/ui/openapi_schema.py`).

Routes (`App.tsx`, behind `ProtectedRoute`, which re-validates `/auth/me` every 60 s and adopts the user's saved appearance): `/login`, `/` Home, `/runs`, `/runs/compare`, `/runs/:runId`, `/settings`, `/admin`, `/account`, `/controls`, `/health`, `*` NotFound; `/dev/ui` (component kit page) only in dev builds. `Layout.tsx` is the shell: nav links, the needs-you inbox, theme toggle, command palette, and a server-health dot.

### 12.2 Pages

| Page (file) | What it shows and does |
|---|---|
| Home (`pages/Home.tsx`) | "Start a new run" (or "Request a change" when started from a finished run). Step 1 brief (text or files, name, optional criteria preview via `/runs/preview`, ambiguity and supported-matrix notes); step 2 delivery (fast/thorough); step 3 involvement (auto-approve vs review points, approval timeout, browser notification opt-in); step 4 model (frontier model on/off, pin to the current model); brownfield source (upload an archive or clone a git repository with branch and token, workspace name, subfolders). Shows whether commands can run. |
| RunList (`pages/RunList.tsx`) | Paged runs with status, stage, owner, elapsed active time, name; filters; selection for Compare; `OutcomesPanel` of finished runs (how each ended, time, score). |
| RunDashboard (`pages/RunDashboard.tsx`) | The run's control room (12.3). |
| Compare (`pages/Compare.tsx`) | Two runs side by side: every KPI the ledger keeps, the change, regressions marked by the ledger's own rule. |
| Settings (`pages/Settings.tsx`) | Tabs: Models (build model, frontier model, saved profiles, thinking, parallel/linear execution, model server card, capabilities, sampling and steering panels with "Diagnose this model"), Appearance, Runs (defaults), Lessons (approve or reject proposed lessons), Account/Security/About. Credentials are write-only inputs. Admin-only writes. |
| Admin (`pages/Admin.tsx`) | Every switch with its explanation, current value and where the value comes from; admins toggle, "Docker" clears the stored setting so the deployment decides. Anyone signed in can read it. |
| Controls (`pages/Controls.tsx`) | One list of every control a person has (directions, lessons, parallel/linear, sprint summary, work orders, templates, reviews and involvement, switches, model diagnosis, pause/resume/rewind/clone/cancel, request a change) with where each lives. |
| Health (`pages/Health.tsx`) | The host at a glance from `/api/health/operator`: disk, database, runs and waiting runs, model server, newest backup, version; re-read periodically. |
| Account (`pages/Account.tsx`) | Own password; for admins, user list, creation, role and disable. |
| Login, NotFound | Plain. |

### 12.3 RunDashboard

Header: run name (editable), status badge, figures (`RunFigures`: active time excluding paused time, tokens, cost where priced), the model-pin switch, and the controls available for the status: Pause, Resume, Resume with a direction, Rewind (lists the rewind points, confirms), Clone, Cancel, Delete, Request a change, download the product, how to run it. A banner appears when the run needs you; `GateDeadline` states whether a gate approves itself and when. Two views, remembered per browser: Wizard (`WizardDashboard`: intake, design, sprints, summary phases) and Classic.

Classic is three columns: left, the latest change, model pressure and `ExecutionFlow` (stages with times); centre, tabs **Activity** (timeline plus agent messages and tool calls: each stage visit folded to one line with the newest open, a command shown as `Ran <command>` with its exit status and its output folded, each write linked to that file's diff in the Workspace tab; beside it the plan panel from `GET /{id}/plan` - the sprint's work orders done / working / open, the attempt, the round and the open defects), **Changes** (per-stage commits and diffs from the workspace's git history), **Log** (raw events), **Artifacts** (documents and files, download, diff), **Workspace** (a read-only file tree and highlighted code view of the product as it is written, harness, installed and build folders and credentials hidden, with each file's change since the last accepted sprint; `GET /{id}/files`, `/files/content`, `/files/diff` in `server/workspace_files.py`; reloaded as stages write), **Audit** (`AuditTable`: time and tokens by stage from the transcript), **Doctor** (`RunDoctor`: what happened and what to do next); right, `SprintSummaryPanel` (sprints as milestones with attempts, tests, defects), `DeliveryPanel` (acceptance criteria from the harness's own suite run, screenshots, the decision log) and the owner rating once the run completes. `SteeringBox` sends a direction to a running run.

Preview tab (`PreviewPanel`, with `PRODUCT_PREVIEW` on): start the product (last accepted sprint or live), its status, a sandboxed frame for a web product or a request console for a service, and stop.
Point and say (`PointAndSay`, LF.1181): with pointing on, the frame loads through a pointing link that adds a picker; the person picks an element and writes the change, which becomes a steering note (whole run or the stage working now) or, for a completed run with change requests on, a prefilled change request. The note carries the element's selector, text, a markup excerpt (marked as data from the product, defanged) and up to 3 likely source files with line numbers (`POST /api/runs/{id}/preview/pick`).

### 12.4 Live updates

On mount the page fetches state, then opens the WebSocket (`getStreamTicket` -> `ws(s)://host/api/runs/{id}/events/stream?ticket=&last_event_id=`). Each event is merged into the log; stage changes, artifacts, errors, completion and gate requests schedule a debounced (700 ms) refetch of run state. A dropped socket reconnects with exponential backoff capped at 30 s, resuming from the last sequence; a `closed` message stops reconnecting. The header inbox (`NeedsYouInbox`, `lib/needsYou.ts`) reads the runs list to count live runs waiting at a gate, review or budget and to list recently failed ones; `lib/notify.ts` and `tabBadge.ts` give browser notifications and a tab badge.

### 12.5 Steering, review and approval in the UI

- Approval (`ApprovalGate`): shows the pending write or command and posts approve or reject (with a reason) to `/approval`. Reads are never gated; this applies when the run is not auto-approving.
- Review (`ReviewPanel`, `GateDocument`): the gated document (specification, sprint plan, sprint result) is read in place, with a diff against the previous revision from the second revision on, one comment box, and Approve / Request changes / Skip; replacing the document with an edited copy is folded away. Posts to `/review`.
- Steering (`SteeringBox`): three levels - **This agent** (the stage working now, at its next model call), **The whole run** (every later stage) and **Stop and redirect** (pause at the boundary, then resume with the direction). Each note shows *waiting*, *read by <stage>* (published on the stream by the first model call that reads it) or *withdrawn*; a waiting note can be edited or withdrawn (`PATCH /{id}/steering/{note}`, `POST /{id}/steering/{note}/withdraw`), and a paused run keeps a note for when it resumes.
- Audience and plan gate (LF.1174): a note's audience is chosen when it is written and shown beside who read it. The run's review policy can hold a `sprint_plan` point: after the scrum master the run waits for Go or "Plan again with my comment", and goes on by itself after `PLAN_GATE_MINUTES` (15; the run's own approval timeout first), recorded as decided by the timeout. `RunReviewsControl` changes the reviews while the run is live (`GET/PUT /api/runs/{id}/review-policy`, read at each gate).
- Command palette (`CommandPalette`, Ctrl/Cmd+K, `?` for shortcuts): go to pages, open the newest runs, approve.

### 12.6 Design tokens and themes

`src/index.css` has three layers: per-theme values on `<html data-theme>`; semantic tokens with theme-independent names (`--bg-canvas/surface/raised/inset`, `--fg`, `--fg-muted`, `--border`, `--accent`, `--status-ok|warn|danger|info|attention-{fg,bg,border}`, `--code-*`, `--diff-*`, `--ring`); and the Tailwind mapping, so every utility follows the active theme. Themes: `graphite` (dark default), `paper` (light), `contrast`, and `system` (follows the OS). Appearance (`lib/appearance.ts`, `AppearanceSettings`): theme, accent (`data-accent`), density (`data-density`); applied at once, kept in the browser, and saved to the account (`PATCH /auth/me/preferences`). Fonts: IBM Plex Sans and Mono, self-hosted. The contrast of every token pair is checked by `scripts/ui/theme_contrast.mjs`; `@axe-core/react` runs in dev. Shared primitives live in `src/ui/` (Button, Card, Badge, Dialog, Field, Tabs, Display).

---

## 13. Data, records and observability

### 13.1 Transcripts

`observability/transcript.py`. One JSON object per line at `DATA_DIR/transcripts/<run_id>.jsonl` (`RUN_TRANSCRIPT=false` disables). Every entry has `at` (UTC), `run_id`, `stage`, `kind`, plus fields; one field is capped at 256,000 characters with its original length noted. Writing never raises. It is the complete, unclipped record (the event stream clips at 2,000 chars and carries no prompts).

| Kind | Meaning |
|---|---|
| `model_request` | The messages a call added (`carried` counts earlier messages resent unchanged); every message appears once per stage. |
| `model_response` | Content, tool calls, token usage, finish reason. |
| `tool_call`, `tool_result` | Post-middleware, so injected notices are in the record. |
| `command` | A sandbox command: argv, category, network, result summary. |
| `model_error`, `model_diagnostic` | Failed model calls; start/end/skipped/failed of the new-model diagnosis. |
| `provenance` | One per segment: harness commit, served model and quantisation, switches on (`observability/provenance.py`). |
| `resumed`, `rewound` | Resume (with reason) and rewind (point, files restored); `run_kpis.live_branch` leaves the abandoned branch out of KPIs. |
| `defect` | A defect's life: raised, fixed, closed, closed without a fixer, left open, reverted, deferred (`observability/defect_ledger.py`). |
| `gate`, `steering_applied`, `screenshot_rubric` | Gate decisions, applied direction notes, page-quality scoring. |
| `rule_could_not_apply` | A narrow rule met an input it could not read and did nothing (`observability/rule_coverage.py`). |
| `note` | Anything a stage leaves behind. |

Also per run: `DATA_DIR/ledger/` (every command) and `DATA_DIR/journal/` (full outputs), and inside the workspace `.harness/` records (stack pack, acceptance lock and results, `decisions.json`, `check-findings.jsonl`, `dispute-outcomes.jsonl`, `dependency-gate.json`, `contract-probe.json`, `steering.json`, snapshots, and more) and `docs/` (rendered specification, plans, reviews, `sprint_N_summary.md`, `decision_log.md`).

### 13.2 Defect ledger

`observability/defect_ledger.py` writes a `defect` record per event, keyed by a stable `defect_id` that survives rounds: a defect's measured cause key (`sprint/cause.py`) when it has one, else a hash of its source, owner, criteria and wording with varying values removed. `scripts/loop/defects.py` (`loop.sh defects`) and the run doctor read it back: what raised each defect, what became of it, defects raised again and again.

### 13.3 KPI ledger

`observability/run_kpis.py` computes one run's KPIs from its live-branch transcript: wall and active minutes, orphan gap, model busy share, calls, tokens (input, output, cached share), prefix-cache breaks, reasoning share, lost replies, tool failure/redundant-read/identical-call/unknown-tool rates, guard-layer interventions, test rounds, fix stages, defects raised/fixed/left open, reverted fixes, model errors by cause, salvaged replies, per-accepted-criterion time and tokens, and the harness commits and switches on. `loop.sh kpi <run>` writes `data/kpi/<run>.json` and appends a row to `data/kpi/ledger.csv` (a run already there is replaced); `scripts/loop/kpi_ledger.py` flags any "worse when higher" KPI above 1.5x its mean over the five previous runs. Score columns (`hidden_score`, `quality_score`, `handoff_score`, `mutation_score`, `false_acceptance`, `benchmark`, `owner_rating`, `switches_fired`) are added when a run is scored. The Compare page and `GET /runs/{id}/kpis` read the same numbers. Runs on more than one harness commit are marked `mixed_versions` and left out of comparisons.

### 13.4 Bench scoring

`scripts/bench/score.py` (run in the worker by `loop.sh score`) copies the finished product, starts it the way the brief states, runs the benchmark's hidden tests, and writes `data/bench/<run>.json`: `passed/failed/total/score`, per-test results, quality tests (`quality_*`), `handoff` checks and `handoff_score`, `harness` (status and `completion_gaps` the harness reported), `verdict`, `false_acceptance`, `silent_loss`, `visible_score`, `visible_hidden_gap`, model and endpoint. `scripts/bench/mutate.py` writes the mutation score (section 14). `scripts/bench/report.py` totals results per benchmark, including false acceptances.

### 13.5 Run doctor, audit, effects, defects

| Tool | Reads | Says |
|---|---|---|
| Run doctor (`observability/run_doctor.py`, `GET /runs/{id}/doctor`, UI tab) | live-branch transcript, stage usage, defect records, `degraded` | stages in order with times; defects raised/fixed/left open/reverted and repeated; commands refused for memory or disk; model errors; restarts; mechanisms that did not run; actions that fit (resume with a direction, rewind, check the model server). Read-only, no model calls. `diagnostic-bundle` is downloaded on demand. |
| `loop.sh audit`, `deep-audit`, `scan`, `timing`, `reads`, `patterns`, `stage`, `asked`, `failures` (`scripts/loop/*.py`, `scripts/audit_run.py`) | transcripts, logs, DB | failure and redundancy audits, invariants a run must hold, where the time went, redundant reads, what a stage was told and answered, each failing acceptance test. |
| `loop.sh effects [run]`, `effects gate [N]` (`observability/switch_firing.py`, `switch_gate.py`) | transcript text signals, ledger | whether each fix or switch fired in a run and what it moved; per switch, runs on vs off arm and candidates to park. A switch with no distinctive text signal is reported as "no signal", never idle. |
| Rule coverage (`observability/rule_coverage.py`) | `rule_could_not_apply` records | per check, how often it met an input it could not read; where a rule should move behind the stack-pack interface. |
| Degraded (`observability/degraded.py`), cache report, prefix breaks, direct calls, proxy timeouts, stage usage | transcript | mechanisms that silently did nothing, prompt-cache behaviour, model calls made outside the stage path. |

### 13.6 Provenance, usage, cost, logs

`observability/provenance.py` records per segment the harness commit, served model, quantisation and switches, so a comparison can exclude mixed-version runs. `GET /runs/{id}/usage` and `AuditTable` give time and tokens per stage; `observability/cost_tracker.py` keeps per-run token and dollar totals (priced vs unpriced, section 10.5) and `metrics.py` exposes Prometheus counters. Logs are JSON (`logging_config.py`) with the run id and correlation id on every line; `docker compose logs app worker` is the live view; a Celery task failure marks the run failed with an explained message (`runner._explain_failure`). Notifications for stalled runs (`STALL_MINUTES`) and gates waiting (`GATE_NOTICE_MINUTES`) go to a webhook and/or email once each (`stall_notices.py`). Optional LangSmith tracing is controlled by `LANGSMITH_*`.

---

## 14. Quality gates and how the product is measured

### 14.1 What is measured

The harness is judged by hidden tests a person wrote from each benchmark brief; the harness never sees them. Per scored run (`data/bench/<run>.json`, `data/kpi/ledger.csv`):

| Measure | Definition |
|---|---|
| Hidden score | Share of the benchmark's hidden acceptance tests the delivered product passes (`score.py`), run against the product started the way its brief says (static server, `start.sh`, `python -m`, import). The reference implementation in `benchmarks/<name>/reference/` must score 100%, which proves the tests. |
| Quality score | Share of `benchmarks/<name>/quality/` tests passed: behaviour beyond the brief's listed features (for example concurrent writes, malformed input). |
| Handoff score | Share of applicable file-level checks a stranger would need (`score.handoff`): README exists, says how to start and how to test, names its configuration, start script reads its port, no shipped database file, no thinking-aloud comments, a CI file. |
| Mutation score | Strength of the run's own locked acceptance suite (`scripts/bench/mutate.py`): the share of small source mutations (flipped comparisons, changed constants) the suite turns red. A floor, since equivalent mutants survive. |
| Verdict | The harness's own call on its delivery (`completion_verdict.py`): `delivered`, `delivered with cuts` (a criterion shipped deferred) or `not_deliverable`, from the release's `completion_gaps`. A gap of an unlisted kind blocks. |
| False acceptance / silent loss | The harness finished the run but the product fails hidden tests; silent when the verdict did not warn (`not_deliverable`). The number that says whether "done" can be trusted. |
| Active minutes | Wall time minus every stretch the run was stopped or waiting (the database's pause clock). |
| Other KPIs | Section 13.3: tool-failure and redundant-read rates, cache share, defects fixed/left open, model errors, calls and tokens per accepted criterion. |

### 14.2 Benchmark families (`benchmarks/`)

Each folder has `brief.md` (with an Interface section stating what a user meets: control labels, endpoints and `start.sh`, module name), `bench.json` (`kind`, `runner`, test count; a brownfield bench adds `base`), `hidden/`, `quality/`, `reference/`.

| Family | Kind / stack | Hidden tests |
|---|---|---|
| `web-todo`, `web-todo-react` | browser app (JS, React/TS), Playwright | 10 |
| `notes-api` (+ `-js`, `-hono`, `-falcon`, `-go`, `-rust`, `-java`, `-csharp`, `-php`, `-ruby`) | HTTP service per language/framework, pytest + httpx | 9 each |
| `wordstats-cli`, `textkit-lib` | CLI program, library (Python) | 8 each |
| `fullstack-bookmarks`, `-py` | page with its own service, Playwright | 8 |
| `tasks-api` | service with accounts, tokens and per-user data | 10 |
| `tasks-api-change` | brownfield: change to the `tasks-api` product (`base/`), 10 old + 5 new tests | 15 |
| `shortlinks-api` | held out from tuning | 8 + 4 quality |

The gate order is web-todo x2, then notes-api/wordstats-cli/textkit-lib, then fullstack-bookmarks x2, then the medium and high briefs (`tests/brief_*.md`) by audit; `tasks-api` is the gate for services with accounts. The per-pack evidence table (runs and mean hidden score per stack pack) is hand-maintained in `stacks/support_matrix.py`: a pack is "supported" with at least 5 scored runs and a mean hidden score of at least 0.9; otherwise experimental. It is served at `GET /api/support-matrix` and used at the start form (`for_the_brief`).

### 14.3 The standing improvement loop

Owned by `AGENTS.md` and `scripts/loop/loop.sh` (one entry point; run `loop.sh` with no arguments for the usage block). The cycle: run a benchmark, audit the run, fix the harness in general, add tests, commit/push/deploy, run the next benchmark. Rules:
- The model is the owner's: `loop.sh ready` must report `ALL READY` before a start.
- Fixes are technology-, framework- and product-agnostic. Stack-specific guidance goes only in `plugins/seed.py` or a stack pack. No run ids in code, comments, prompts or tests.
- Every fix gets a test proven to fail on the old code; prompt rules additionally get a test banning the whole words task, tasks, to-do, todo, button, click, checkbox (tests such as `tests/test_banned_words_in_refusal.py`).
- Both suites green before a deploy (14.5). Commit and push after every change; `docs/STATE.md` and the handovers are updated in the same commit.
- Owner features are kept: dynamic instruction injection, the parallel/linear toggle, the sprint summary, work orders, templates and the Sprint Record.

### 14.4 Frozen-version measuring and deploys

Measuring runs on a frozen harness SHA: two runs per family, scored by hidden tests only; a bug found is filed for the next fix batch, not deployed into the batch. Fixes ship in bundles at run boundaries. A deploy into a live run happens only for a bug that changes its outcome, and marks the run `mixed_versions` (excluded from comparisons; UI-only app deploys do not). In a run's first 40 minutes a bug means cancel, fix, deploy, restart; later, fix generally, prove the test fails on old code, run the suite, push, deploy, resume. A fix batch that moves no hidden score or KPI is parked. A switch is judged "drastic" when a run it fired in loses a hidden test or takes 1.5x its family's five-run active minutes; then it goes off and the next run verifies.

**Ship-live** (`loop.sh ship-live`, `ship_live.sh`): builds the images first (a failed build touches nothing), loads the operator login, pauses every running run at its next stage boundary (`at=boundary`, ceiling 600 s; `SHIP_NOW=1` stops at once), runs `loop.sh deploy`, resumes each run it paused, and checks for worker-pool churn and that each resumed run is running a task. `loop.sh deploy` (one at a time via `deploy.lock`): resolves the commit, reuses built or retagged images, waits for a stage boundary, holds new model calls through the gate and waits for in-flight ones, `compose_up.sh app worker` (which starts a container left at `Created` and re-ups a service not on its new image), verifies the running image matches the commit, lists runs orphan recovery revived. `loop.sh deploy-app` restarts only the app (UI/API). `loop.sh resumed` waits up to 10 minutes for orphan recovery to resume a run after a deploy.

**Rewind semantics for the loop**: after a fix, `rewind` the live run to the earliest stage the fix affects (`rewind_point.py` suggests it); a new run is started only if the fix reaches intake or stack. A rewind restores that stage's workspace snapshot and continues on a branch.

### 14.5 Test suites

| Suite | Command | What it does |
|---|---|---|
| Full | `scripts/loop/loop.sh suite` | `pytest tests/` (about 1,590 test files, tens of thousands of cases) with xdist (`SUITE_WORKERS`, default 12; about 1 minute), `ENV=development`, venv on PATH; then the UI type check (`tsc -b`); then every failure again alone (`flaky (passed alone)` vs `FAILED alone too`). Log: `data/loop/suite.log`. Must be fully green. Do not edit `src/` while it runs. |
| Production defaults | `scripts/loop/loop.sh suite-production` | Same suite with every built-in fix on together (`HARNESS_TEST_PRODUCTION_DEFAULTS=1`), as shipped; fails on any failure not in `tests/production_defaults_expected.txt`. |
| UI | `npm test` in `langchain-ui` (Vitest) | Component and page tests. |
| Locked-suite corpus | `tests/test_the_suite_checks_replay_unchanged_on_real_suites.py`, `scripts/loop/locked_suites.py` | Replays the static suite checks over stored real locked suites; fails when any check's findings change until reviewed and accepted. |
| Pack verification | `loop.sh nightly`, `scripts/loop/verify_packs.py` | Verifies every stack pack in the worker, then reports pins a major version behind their registry. Run after any pack template change. |

`tests/conftest.py` starts Postgres and Redis containers (testcontainers), sets `OPENAI_BASE_URL` to a refusing port so no test reaches a real model, turns the dependency gate off, and resets each built-in fix to its off default so a test enables only what it tests. `pyproject.toml` enforces coverage of at least 80% on `src/app` and `asyncio_mode = auto`. CI (`.github/workflows/ci.yml`) runs the backend on Python 3.12 (3.13 informational) and the frontend.

---

## 15. Security and safety

| Concern | Mechanism (owner file) |
|---|---|
| Command execution | argv lists only, exact per-role executable allowlist, interpreter-escape screening, no network unless granted, resource limits, dropped caps, read-only root, non-root user; fails closed (`tools/sandbox.py`). Opt-in: `ALLOW_COMMAND_EXECUTION` defaults false. |
| Product code vs harness secrets | In container mode the harness's own probes and compilers run product code in command containers, which hold none of the worker's secrets; in `in-container` mode the worker's processes are non-dumpable (`server/process_privacy.py`) and a command's environment is filtered. |
| Docker access | The worker holds a root-equivalent capability when it can start containers. The sandbox overlay narrows it with a socket proxy; the body-validating broker (`deploy/sandbox-broker`) is built and not yet wired. |
| Egress | Command-level host allowlist for installs, dependency-name and age gate, fixed hosts for runtime downloads (`install_egress.py`, `dependency_gate.py`, `runtimes.py`). No network-level filter yet (approved, unbuilt). |
| Untrusted text | Fetched docs, search results, MCP answers and lookups are labelled as data and defanged: shapes that look like tool calls or chat-template tokens are replaced by a marker, then capped (`tools/untrusted_text.py`). |
| Web reads | A page is read only from a public address, never a compose-network container, the host or a cloud metadata address (`tools/web_search.py`). Seeding checks git schemes and private hosts (`server/seeding.py`). Only official MCP servers of a library's own namespace are attached, remote only; package servers are never run inside the worker (`tools/mcp_registry.py`). |
| Write boundaries | Paths stay in the workspace and project; `docs/` holds only workflow-rendered documents; the locked acceptance suite, `.harness/` and kept files are refused; a file the language's parser rejects is refused; leaked model control tokens refused; blind overwrites refused; work-order file ownership in parallel mode; stale-edit detection (`tools/repository.py`, `seen_content.py`). TESTS_ONLY_WRITES keeps first fixes of failing unit tests to test files (`tools/tests_only_writes.py`). Workspaces are allocated by the server, never taken from a request (`server/workspaces.py`). |
| Read-only checks | Hidden benchmark tests exist only on the host and are copied into the worker only for scoring, then deleted. The shadow score is operator-only (`LOOP_SHADOW_SCORE`). |
| Secrets | `.env` is git-ignored (`.env.example` lists names). Provider keys are write-only in the UI and stored Fernet-encrypted in a table separate from settings; event metadata passes through `redact_metadata`; model-override secrets are filtered before persisting; cost and settings views never return keys. JWT/admin/Postgres/Redis secrets are required in production and published development values are refused. A model endpoint's key is sent only to that endpoint. |
| Accounts | bcrypt, login throttling, token versioning, roles and tenancy, audit log (section 11.6). Credentials for the loop's operator account are kept outside the code (host-side docs); the loop never uses the admin account. |
| Product preview | Only an operator or admin of the run's tenant starts, reads or stops a preview (audited `run.preview.start/stop`). The link carries a signed, expiring token in the path (a sandboxed frame sends no cookies). The proxy passes content headers only: no cookie, Authorization or X-Forwarded header reaches the product, its Set-Cookie is dropped. The page gets an opaque origin (frame sandbox plus CSP `sandbox` without `allow-same-origin`); with `PRODUCT_PREVIEW_ORIGIN` the proxy answers only that host. Gaps: no WebSocket or hot reload; URLs built at run time are not rewritten; no internet at start. |
| Transport | `deploy/Caddyfile` adds TLS, HSTS and a CSP in production; CORS is same-origin by default; WebSocket auth uses a 30 s single-use ticket. |
| What leaves the machine | Model calls to the configured endpoints (the owner's local servers by default; a hosted provider only if configured). Error lookups send only the cleaned error line and the stack's names to Stack Exchange, GitHub issue search and the private SearXNG, cached 7 days (`tools/lookups.py`, behind `WEB_LOOKUP_WHEN_STUCK`; optional `STACKEXCHANGE_KEY`/`GITHUB_TOKEN`). Package and docs lookups go to the registries and projects' own sites. Install commands fetch from the allowlisted registries. Optional LangSmith traces and webhook/SMTP notices if configured. No brief text is sent to search. |
| Operator rules | The model is the owner's: never load, change or kill model or GPU processes. Never print `.env` values. Report times to the owner in JST (containers log UTC). |

---

## 16. Backing services and storage

**Postgres 15** is the system of record: runs, users, audit, runtime settings/secrets, model profiles, plugin rows, and the LangGraph checkpoints that make resume and rewind possible. Pool and reconnect handling in `server/db_pool.py`; schema creation takes an advisory lock so API and worker starting together do not race (`schema_lock.py`). Files in `data/postgres` (a full disk crashes it; section on hygiene below).

**Redis 7** (password, AOF, `noeviction`, 512 MB) holds: the Celery broker and result backend; per-run event history, sequence and pub/sub (`events.py`); WebSocket tickets (30 s); the rate-limit counters and login throttle; orphan-recovery locks (`harness:recover-orphans`, `:recurring`); the per-run segment count (`run-segments:<id>`, 7 d); first-delivery markers (3 d); each worker's command-readiness record. Losing Redis loses live events and queued dispatches but not run state (Postgres) or work (workspace).

**Object storage** (`server/object_store.py`): a durable side copy of uploads and finished product artifacts with `put_file` after a write and `ensure_local` before a read, so a second node can read what the first wrote. The default `LocalObjectStore` copies under `DATA_DIR/objects`; an S3-compatible backend (`S3ObjectStore`, boto3) is used when `OBJECT_STORE_ENDPOINT` or `OBJECT_STORE_BUCKET` is set. The compose file passes the variables but defines no MinIO service. Workspaces stay on a real filesystem because agents run `ls`, `git` and test runners in them.

**Searxng** is a stateless private metasearch (engines in `docker/searxng/settings.yml`); the general engines often refuse it, so the harness prefers the developer sources first (section 15).

**Backups** (`loop.sh backup`, `nightly`): `pg_dump` custom-format to `data/backups/<date>/langchain.dump` (plus lessons); the three newest are kept locally. With `BACKUP_DIR` set (an external disk, in git-ignored `data/loop/ops.env`) each backup is also copied to `$BACKUP_DIR/daily` (7 kept) and, on Sundays, `$BACKUP_DIR/weekly` (4 kept); a failed copy is loudly reported. `loop.sh backup --check` restores the newest dump into a scratch database and counts its runs (a backup never restored is not a backup); `loop.sh restore <dir> <new-db>` restores into a new database. `/api/health/operator` reports the newest backup's age. The nightly job (host cron, `loop.sh nightly`) runs backup, restore check, pack verification and freshness report, and removes finished runs' checkpoints and workspaces older than `RETENTION_DAYS` (60 on the owner's host; reported only if unset). It is skipped while a run is live.

**Disk hygiene.** A full data disk takes down Postgres. Operator practice: keep `/home` free, clear LM Studio's logs, restart app and worker and resume runs if it happens (`scripts/loop/disk_ready.py`, `resources.py` refuses commands when disk or memory is short). Transcripts, ledgers and journals are the main growth; `CTX_JOURNAL_RETENTION_HOURS` bounds the journal, deleting a run (or retention) removes its records.

---

## 17. Operating limits and known gaps

**Supported matrix.** "Launch" means a private, self-hosted, single-tenant beta for a handful of invited users. Supported (at least five scored runs, mean hidden score at least 0.9, model tier not weak): Python HTTP services, CLIs and libraries, JavaScript/TypeScript browser apps, Node services (Hono and plain), fullstack page-plus-service in Python or Node. Every other pack is experimental on too little evidence or a low score. Per `docs/STATE.md` and `stacks/support_matrix.py`: Go, C#, PHP and Ruby packs have 2-4 scored runs each (all perfect, too few to count); Java has 5 runs at a mean 0.80; local Rust has 6 runs at a mean 0.48. A brief naming a language outside the supported set gets an experimental notice at start. Stacks no pack covers go through the custom-setup stage (agents choose commands; the locked suite must still pass).

**Run times.** Small briefs finish in about 40-130 active minutes on the local model; the services with accounts take 1.5-5 hours; Ruby and Java first runs have taken 4 hours and 2 hours. A Celery task is limited to 12 h soft / 12 h 5 min hard; a run is carried across up to 4 segments (about 10 h each of stage time before a boundary pause) before it is left paused for a person.

**Model dependence.** All reliability evidence comes from one model class: a 35B mixture-of-experts Qwen on LM Studio, 4-bit. Quality depends on a correct context window (the number every budget derives from), enough per-slot context, and the server honouring tool-calling. Each new model is diagnosed on first use and gets a measured tier; a weak tier makes every stack experimental. Two ports run at most two concurrent runs with the default worker concurrency of 2; `MAX_CONCURRENT_RUNS` is off by default. Hosted models are optional and cost money; the cost ceiling default is 8 USD per run and applies only to priced calls (local is unpriced; `MAX_RUN_TOKENS` is the bound for those).

**Known weak spots (from the code and the current status file).**
- Rust on the local model is unreliable (0/9 in four runs); other non-Python/JS stacks have thin evidence.
- Runs can lose attempts to a single mis-chosen dependency or stack decision made before the specification (for example a stack that names one database engine via another's mode); no check sends a contradictory stack decision back.
- A repeated pattern of redundant re-reads after a worker restart appears across runs (the restart re-read pattern), and look-ups of a version before a manifest line are not yet done.
- The locked acceptance suite can encode a wrong expectation; the dispute mechanism can accept contested tests, and "delivered with cuts" runs ship criteria deferred. The hidden-score gap is measured, not eliminated: false acceptance and silent loss are tracked precisely because they occur.
- Sandbox: no network-level egress filter; `bridge` network for installs and for packs that fetch while building is open to the internet at the network layer; the body-validating broker is not yet in the compose chain; `in-container` mode is weaker than `container`.
- Single-tenant: tenancy fields and scoping exist, but isolation between tenants is not a tested product claim; the worker holds the provider keys for all runs.
- External lookups are rate-limited (keyless Stack Exchange 300/day per address); the private search is often refused by general engines.
- Pack versions drift: pins fall behind registries (`loop.sh freshness` reports it).
- Switch state: some optional switches are on in compose and listed off in `docs/STATE.md`; the on/off truth is the stored admin setting, and a new run's `provenance` record is the only reliable per-run source (unverified here).

**Deliberately not done.** No automatic tuning of the harness to hidden tests (the shadow score is operator-only); no changing the owner's models or sampling (sampling is recommended, sent only when the owner opts in); no roles removed without a measured ablation; no network sidecar, service-container broker, Valkey swap, licence-class services, real cloud credentials or Docker Hub login yet (each approved and deferred with a trigger in `docs/owner-decisions.md`); no use of the admin account by the loop; no hosted-model testing unless the owner starts it; no per-token event streaming; no hot-editing of a running stage (a direction applies from the next model call; a deploy waits for a stage boundary or in-flight calls).

---

## 18. Repository map

| Path | What lives there |
|---|---|
| `AGENTS.md`, `CLAUDE.md` | Standing rules of the improvement loop (CLAUDE.md imports AGENTS.md). |
| `README.md`, `docs/` | Project readme; `docs/STATE.md` (live status, at most 150 lines), `HANDOVER.md`, `monitoring-handover.md`, `owner-decisions.md`, `improvement-plan.md` (every fix as an LF row), `measuring.md` (the one register of what is under measurement), `architecture-decisions.md`. |
| `src/app/` | The product (installed as package `app`). |
| `src/app/main.py`, `config.py`, `state.py`, `switches.py`, `delivery.py`, `review.py`, `completion_verdict.py`, `decisions.py`, `documents.py`, `tracing.py` | CLI entry, typed settings, graph state models, switch resolution, delivery modes (fast/thorough), review and verdict logic, document reading, tracing. |
| `src/app/graph/` | LangGraph workflow: `workflow.py` (the graph and stage routing, rewind), `nodes/`, `engineering.py`, `acceptance_nodes.py`, fix machinery (`bounded_fixes`, `defect_budget`, `escalation`, `kept_fix_candidates`, `best_attempt`, ...), `checkpointing.py`. |
| `src/app/agents/` | Role agents, prompts and their per-run context: product manager, architects, reviewers, specialists, memory and context budgeting, compaction, project snapshot/memory, stable tools. |
| `src/app/acceptance/` | Acceptance criteria, locked suite runner, mutation checks, probes (edge, order, page, concurrent-write, contract, start), interface contract. |
| `src/app/analysis/` | Static analysis: language parsers, project graph, manifests, work orders, test discovery, compiler checks, reachability. |
| `src/app/stacks/` | Stack packs (`packs/`), language table (`languages.py`), scaffold, setup scope, custom setup, release docs and audits, compiler error tables, support matrix. |
| `src/app/tools/` | Agent tools and their guards: `sandbox.py`, `repository.py`, `install_egress.py`, `dependency_gate.py`, `runtimes.py`, lookups, docs, web search, MCP, page view, version control, resources. |
| `src/app/models/` | Model construction, endpoints, routing, roles (build/judgement), pinning, capabilities, diagnostics, guidance, reply salvage, sampling, quota, window and server probes. |
| `src/app/server/` | FastAPI app and Celery: `api.py`, `runs.py`, `runner.py`, `tasks.py`, `run_store.py`, `events.py`, `progress.py`, `auth.py`, `settings.py`, `runtime_settings.py`, `manage.py` (CLI), `seeding.py`, `object_store.py`, `steering.py`, `rate_limit.py`. |
| `src/app/observability/` | Transcript, KPIs, defect ledger, run doctor, cost tracker, provenance, switch firing, rule coverage, metrics. |
| `src/app/plugins/` | Dynamic instruction injection (`middleware.py`, `registry.py`), `seed.py` (all stack- and model-specific guidance lives here or in a pack), lessons and distiller. |
| `src/app/sprint/`, `handover/`, `doc_templates/` | Sprint Record and product archive; handover document and facts; Jinja templates for generated documents. |
| `langchain-ui/` | The web UI (`src/pages`, `src/components`, `src/lib`, `src/ui`, `src/api`), Vitest tests beside sources. |
| `tests/` | Python suite (about 1,590 files); fixtures in `tests/fixtures/` (locked-suite corpus); `SKIPS.md` (every skip states a reason); `production_defaults_expected.txt`; shared stubs (`workflow_node_stubs.py`, `the_fix_stage.py`). |
| `benchmarks/` | Benchmark families (brief, `bench.json`, `hidden/`, `quality/`, `reference/`) and a README. |
| `scripts/loop/` | The improvement loop: `loop.sh` and its Python/Bash helpers (audit, KPI, defects, effects, deploy, ship-live, backup, nightly, model readiness and diagnosis, pack verification). |
| `scripts/bench/`, `scripts/ui/`, `scripts/audit_run.py`, `scripts/setup-env.sh` | Scoring, mutation and reporting; OpenAPI type generation and theme contrast checks; run audit; first-time `.env` creation. |
| `deploy/` | `Caddyfile`, `sandbox-images/<toolchain>/Dockerfile`, `sandbox-broker/`. |
| `docker/searxng/` | SearXNG settings. |
| `context/` | Per-role agent context folders (instructions each role starts from). |
| `evaluation/`, `intake-api/`, `ledger/`, `proj/` | `evaluation/evaluate.py` is an evaluation script; `ledger/*.jsonl` are execution-ledger files; `intake-api/` is an early generated sample service kept in the repository (not part of the harness) and `proj/` is an empty folder. None is copied into the image (it copies `src/`, `pyproject.toml` and the UI build). |
| `Dockerfile`, `Dockerfile.test`, `docker-compose*.yml`, `pyproject.toml`, `uv.lock` | Image, CI-equivalent test image, compose files, dependencies (exact versions pinned by `uv.lock`). |
| `data/`, `transcripts/`, `reports/`, `research_notes/`, `*.sqlite` | Git-ignored runtime and local state. |

**Test conventions.** One file per behaviour, named as a sentence (`test_a_blind_overwrite_is_refused.py`). A behaviour fix ships with a test proven to fail on the old code (revert the fix, watch it fail). A prompt or refusal text gets a test that none of the whole words task, tasks, to-do, todo, button, click, checkbox appears in it (case-insensitive, word boundaries), keeping rules product-agnostic. A plain wording or UI-label change needs no test. No run ids anywhere in code, comments, prompts or tests; product words must not spread into the source (`test_product_words_do_not_spread_in_the_source.py`). Skips and xfails name their reason in the call (`test_every_skip_names_its_reason.py`). Flaky-by-order tests are reported separately by `loop.sh suite`, never as fixes' breakage. UI tests live next to their component as `*.test.tsx`.

**Where to start reading.** `docs/STATE.md`, then `src/app/graph/workflow.py` for the pipeline, `src/app/server/runner.py` and `tasks.py` for the run lifecycle, `src/app/tools/sandbox.py` for execution, `scripts/loop/loop.sh` for operations.


---

## Keeping this document true

Any change to how the product works or is built updates this file in the same commit (rule in `AGENTS.md`). Facts are
checked against the code, which wins over this text. Numbers that change quickly (counts of packs, switches and tests,
run times, scores) are given as of the date named beside them; the live figures are in [STATE.md](STATE.md),
`data/kpi/ledger.csv` and the generated [measuring.md](measuring.md).
