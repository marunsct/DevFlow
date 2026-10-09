# Harness Improvement Plan

**What this is.** The master improvement plan for the LangGraph / Deep Agents harness. It incorporates lessons learned from live benchmark runs, audits the status of previous plans (Parts I–III and the 2026-10-04 plan), conducts a comparative architectural benchmark against leading open-source agentic coding frameworks (SWE-agent, OpenHands / OpenDevin, Aider, DeepSeek harness), and lays out an actionable implementation roadmap prioritized by measurable ROI and time savings.

---

## 1. Comparative Architectural Benchmark: Current Harness vs. SOTA Frameworks

To achieve consistent, production-grade performance and reduce benchmark execution times from 2–3+ hours down to 30–60 minutes for standard applications, the harness was evaluated against industry state-of-the-art (SOTA) agentic coding systems:

| Dimension | Current Harness | Leading SOTA Systems (SWE-agent, OpenHands, Aider, DeepSeek) | Architectural Gap & Opportunity |
|---|---|---|---|
| **Organizational Topology** | Rigid 14-stage corporate workflow (Architect → Arch Review → QA Author → QA Review → Scrum Master → Tech Lead → Dev → Test → Code Review → Acceptance → Defect Remediation → Milestone Review → Sprint Summary). 400–600 model calls per run. | **Dynamic / Adaptive Topology** (Aider, OpenHands): Single Planner + Executor loop, or lean Architect + Coder pair. Specialized roles invoked dynamically only when needed. Benchmark runs finish in 15–40 steps. | **High**: Simple applications (e.g. 10–16 criteria) suffer massive roundtrip latency. The harness should dynamically collapse stages for small/medium scopes. |
| **Acceptance Suite Verification** | Suite authoring produces tests with un-awaited promises or CSS selectors. Flaws trigger runtime crashes after development, invoking the **Acceptance Dispute Engine** (reopening suite for 3+ rounds, costing 30–45 mins). | **Pre-Emptive Static AST Validation** (SWE-bench / DeepSeek): Strict linters, AST tree-sitter checks, and floating-promise detectors validate tests *before* suite is accepted or executed. | **Critical (P0)**: Catch test defects statically before locking. Eliminates the multi-round dispute loop entirely. |
| **Context & Repo Representation** | Flat file lists in workspace digest (`MAX_FILES = 40`). High redundant read rate (12–18% of reads spent re-inspecting files). Agents frequently call `read_file` to find symbol definitions. | **Tree-Sitter RepoMap** (Aider): Dense topological map of exported symbols, signatures, and classes generated in <1,000 tokens using Tree-Sitter and PageRank. | **High (P1)**: Provide symbols and signatures in prompt context, slashing redundant tool calls and token spend. |
| **Execution Latency & Sandboxing** | Isolated command execution per tool call; default Playwright locator timeout of 30s causes failing test runs to burn 5–8 minutes per round. | **Persistent Daemon & Fast-Fail Timeouts** (OpenHands, SWE-agent): Persistent shell session with sub-second turnaround; strict 3–5s timeouts on UI element checks. | **High (P1)**: Fast-fail on UI mismatches; persist sandbox environment. |
| **Cross-Run Learning & Memory** | **Tabula Rasa**: Cross-run memory was previously dropped (Phase 4) due to prompt-injection concerns. Agents repeat known framework gotchas (e.g., missing `await` on custom helpers, unconfigured JSDOM globals) on every single run. | **Deterministic Skill & Case Distillation** (Voyager, Reflexion, ExpeL): Post-run reflection distills verified traps, patterns, and templates into deterministic, injection-safe rule stores. | **Critical (P0)**: Implement a Self-Learning Engine that extracts verified rules from Decision Records and saves them into Stack Pack knowledge bases. |

---

## 2. Audit of Existing Plan Items (Status as of October 2026)

Each item from previous plans was re-verified directly against the codebase:

### Completed & Implemented Items
- **R1 — Harness-Owned Files Enforced at Planning (`88356da`)**: Work orders cannot target kept files or locked suites; enforced in `app.stacks.contract.owned_by_the_harness` and workspace digest.
- **R2 — Auto Mode Decides at Sticking Points (`d12b138`)**: Unresolved architecture reviews and assignment stops route through `app.graph.escalation` with automated decision records.
- **R3 — Model Endpoint Handling (`139cf0f`)**: `app.models.endpoints.is_self_hosted` differentiates local vs. hosted OpenAI endpoints; llama.cpp flags and retries apply only to self-hosted servers.
- **R4 — Stack Pack Release Files (`c9b5400`)**: Stack packs declare container and CI workflow files; dead `app/deploy` package eliminated (ADR-0004).
- **R5 — Dead Code Elimination (`05b01a3`)**: Cleaned unused legacy packages (`app/scaffolding`, `app/build/verifier.py`, `app/tools/testing/runner.py`).
- **R6 — Documentation Cleanup**: Obsolete plans and scratch files removed from `docs/`.
- **R7 — IDE-Grade Language Service Checks**: Tree-sitter CSS validation, Pyright for Python, TypeScript compiler service for JavaScript/TypeScript (`app.analysis.language_service`).
- **Dynamic Sprint Count Cap (`0b28a91`)**: Scope-based sprint capping (`_cap_sprints_for_scope` in `scrum_master.py`) ensures <=10 criteria apps run in 1–2 sprints instead of 4.
- **Batch Defect Remediation (`0b28a91`)**: Open defects belonging to the same specialist role are bundled into a single invocation (`_bundle_defects_by_specialist`) instead of sequential 1-defect rounds.
- **Explicit Specialist File Ownership (`0b28a91`)**: Specialist prompts include explicit allowed file targets to prevent work-order rejection churn.
- **Conditional Post-Sprint Reviews (`0b28a91`)**: Security and advice reviews are skipped when sprints touch zero architectural or security-sensitive files.
- **Untested Criteria Dispute Resolution (`2702c9d`)**: Acceptance test requests require explicit criterion tags in titles (`[AC-X]`); dispute engine detects missing/untested criteria and reopens the suite for QA correction rather than deadlocking developers.

### Partially Implemented Items
- **B1 — Cross-File Checks Beyond JavaScript**:
  - *Current Status*: Size counting and CSS/TS/Pyright language checks exist. Multi-file symbol references and imports for Go, Rust, and polyglot setups are still heuristics.
  - *What Needs to be Done*: Extend Tree-Sitter AST symbol resolution across all supported stack languages.
- **Part III 1 — Coverage Omit Filter**:
  - *Current Status*: Per-file omit list exists, but test runner still counts imports inside `tests/` as caller references.
  - *What Needs to be Done*: Filter out `tests/` directory imports when verifying whether application modules are referenced by production code.
- **Pre-Emptive Acceptance Test Linting**:
  - *Current Status*: Some regex and method checks exist (`locators_that_do_not_exist`, invalid role checks), but tests can still be locked with un-awaited promises on async helper functions and brittle CSS selectors.
  - *What Needs to be Done*: Implement AST-level floating-promise checking and CSS selector banning in `app/acceptance/suite.py` before locking (see P0 below).

### Open / Retained Items
- **B7 — Measured Chars Per Token**: Low priority; context compaction has prevented context overflows on current models.
- **B15 — Digest Budget for Large Codebases**: Active when repository exceeds 40 files; small benchmark apps remain well under the ceiling.
- **Fast-Fail on Test Timeouts**: Reduce Playwright default locator timeouts to 3–5 seconds to prevent failed assertions from waiting 30 seconds each.

---

## 3. Prioritized Implementation Plan (Ranked by ROI & Value)

### Tier 1 (P0): Eliminating the Longest Failure Loops (Expected Savings: 60–90 mins)

#### 1. Pre-Emptive Acceptance Suite Static Linting (AST Validation Before Locking)
- **Problem**: In live runs, QA authoring frequently generates Playwright tests with async helper calls missing `await` (e.g. `const item = getTaskItemByTitle(...)` where `item` is a Promise, causing `TypeError: item.getByRole is not a function`) or using brittle CSS selectors (e.g. `locator('input[type="checkbox"]').filter({ hasText: 'Done' })`). Because these flaws are only detected when the product runs, they trigger the **Acceptance Dispute Engine** (DR-5, DR-7), reopening the locked suite and forcing multiple QA authoring rounds that consume 30–45 minutes of model time.
- **Solution**:
  1. Add an AST-based static validator in `app/acceptance/suite.py` that runs during `suite.gaps()` / `acceptance_review`:
     - **Floating Promise Detection**: Parse test files using Tree-Sitter or ESLint to verify that calls to async helper functions are awaited before method chaining.
     - **Locator Contract Enforcement**: Reject raw CSS tag selectors (`input[type=...]`, `div.task`) in favor of accessible queries (`getByRole`, `getByLabel`, `getByText`).
     - **API Method Validation**: Verify all chained locator methods exist on Playwright `Locator` / `Page` prototypes.
  2. If any test violates these rules, reject it immediately during `acceptance_author` rounds with actionable feedback before the suite can ever be locked.
- **Expected Impact**: Completely eliminates acceptance suite dispute reopenings, saving 30–45 minutes per run.

#### 2. Self-Learning Agents: Deterministic Distillation & Stack-Pack Knowledge Store
- **Problem**: Phase 4 cross-run memory was previously dropped because raw agent-written prose shared across runs is vulnerable to prompt injection, hallucination, and behavioral drift. However, operating completely *tabula rasa* forces every run to repeat the exact same discovery mistakes (such as discovering that Node `--test` needs `--import ./test-setup.mjs` for browser globals, or discovering Playwright async helper patterns).
- **Solution**: Implement a **Structured, Injection-Safe Self-Learning Engine**:
  1. **Post-Run Distillation Node (`app/learning/distiller.py`)**:
     - At the end of every run (successful or failed), an automated distillation stage audits the run's Decision Records (`DR-1`..`DR-N`), resolved defect diffs, and lint errors.
     - It extracts structured, schema-validated lessons:
       - `framework_gotchas`: Specific flags or imports required by the toolchain.
       - `test_patterns`: Valid locator idioms and assertion conventions for the stack.
       - `component_templates`: Verified structural patterns that passed acceptance tests.
  2. **Stack-Pack Heuristics Store (`app/stacks/heuristics/<pack>.json`)**:
     - Distilled lessons are validated against an allowlist schema (rejecting arbitrary system prompt overrides) and committed to the stack pack's knowledge store.
  3. **Contextual Heuristics Injection**:
     - When a specialist or QA agent starts a stage, `app/stacks/seed.py` injects only the high-confidence, verified heuristics matching that stack and role.
- **Expected Impact**: Prevents regression loops on known framework quirks, saving 20–35 minutes across development and testing.

#### 3. Adaptive Workflow Complexity (Dynamic Fast-Path for Lean Scopes)
- **Problem**: For simple or focused applications (<=15 acceptance criteria), executing 14 separate corporate stages generates 400+ LLM roundtrips. Raw model inference and tool roundtrip wait times account for 60–90 minutes even when no code bugs occur.
- **Solution**:
  1. Classify project scope during `product_intake`:
     - **Tier 1 (Lean, <=15 criteria)**: Simple utilities, single-page web apps, CRUD tools.
     - **Tier 2 (Standard, >15 criteria)**: Multi-service applications, complex architectures.
  2. For **Tier 1** workflows:
     - Collapse `scrum_master` and `technical_lead` into a unified Single-Sprint Planner (`lean_planner`).
     - Bypass `architecture_review` if the stack pack's standard verified architecture is accepted unchanged.
     - Consolidate development into a Fullstack Specialist invocation with integrated test verification.
- **Expected Impact**: Reduces LLM call count by 40–50%, saving 35–50 minutes per benchmark run.

---

### Tier 2 (P1): Tool Latency & Context Efficiency (Expected Savings: 25–40 mins)

#### 4. Tree-Sitter Repository Map (RepoMap) & Context Compaction
- **Problem**: Agents exhibit a 12–18% redundant read rate, repeatedly invoking `read_file` or `ls` to discover what functions or classes exist across files.
- **Solution**:
  1. Integrate an Aider-style Tree-Sitter RepoMap in `app/analysis/project_memory.py`:
     - Extract all declarations, exported functions, classes, and types with their parameter signatures.
     - Format as a compact hierarchical outline (~500–800 tokens).
  2. Include the RepoMap in the workspace digest so all specialists have immediate visibility into the complete codebase structure without executing exploratory tool calls.
- **Expected Impact**: Reduces redundant reads to <5%, saving 10–15 minutes and ~20% token overhead.

#### 5. Persistent Sandbox Sessions & Fast-Fail Test Timeouts
- **Problem**: Each `run_terminal_command` spawns an isolated subprocess. When Playwright tests fail to find an element, Playwright's default 30-second timeout per test causes a single acceptance run of 16 tests to take 5–8 minutes.
- **Solution**:
  1. Configure harness Playwright templates with aggressive local timeouts:
     - Set `actionTimeout: 3000` (3 seconds) and `expect: { timeout: 3000 }`.
     - Fast-fail immediately if the base URL / server returns connection refused or 404.
  2. Keep a persistent container shell session for sub-second command dispatch.
- **Expected Impact**: Slashes acceptance test execution time from 5–8 minutes down to 10–20 seconds per run, saving 15–20 minutes across multiple test rounds.

---

### Tier 3 (P2): Remediation Precision & Observability (Expected Savings: 15–20 mins)

#### 6. Targeted Test-Driven Defect Remediation with DOM Diffs
- **Problem**: During defect remediation, specialists receive general error messages but lack the exact runtime failure state, leading to speculative code edits.
- **Solution**:
  1. When an acceptance test fails, extract the Playwright call log, the failing assertion line, and the simplified HTML/accessibility snapshot of the page at the exact moment of failure.
  2. Inject this structured failure packet directly into the defect remediation prompt, instructing the agent to fix the specific attribute or event handler.
- **Expected Impact**: Increases first-attempt defect remediation success rate from ~60% to >90%, eliminating second and third remediation cycles.

#### 7. Automated Cross-Run Benchmark Regression Tracking
- **Problem**: Run timing and performance regressions are currently audited manually by checking timing logs after runs conclude.
- **Solution**:
  1. Add an automated regression reporter in `scripts/loop/audit_live.py`:
     - Compare current run metrics (total wall-clock time, model calls per stage, failure rate, redundant read percentage) against moving averages of the last 5 clean runs.
     - Highlight any stage whose call count or duration exceeds 1.5x the baseline.
- **Expected Impact**: Immediate visibility into performance regressions during live monitoring.

---

## 4. Execution Roadmap & Milestones

| Phase | Initiative | Primary Target Modules | Est. Time Savings | Status |
|---|---|---|---|---|
| **Phase 1 (Immediate)** | Pre-Emptive Acceptance Suite AST Linting | `src/app/acceptance/suite.py`, `src/app/acceptance/requests.py` | 30–45 mins | Ready for implementation |
| **Phase 1 (Immediate)** | Fast-Fail Test Timeouts (3s Playwright locators) | `src/app/stacks/`, `src/app/tools/sandbox.py` | 10–15 mins | Ready for implementation |
| **Phase 2 (Near-Term)** | Self-Learning Engine: Deterministic Distillation & Stack Pack Rules | `src/app/learning/`, `src/app/stacks/seed.py` | 20–30 mins | Architecture defined |
| **Phase 2 (Near-Term)** | Adaptive Workflow Complexity (Lean Scope Fast-Path) | `src/app/graph/workflow.py`, `src/app/agents/scrum_master.py` | 30–45 mins | Architecture defined |
| **Phase 3 (Follow-Up)** | Tree-Sitter RepoMap in Workspace Digest | `src/app/analysis/project_memory.py`, `src/app/analysis/digest.py` | 10–15 mins | Design ready |
| **Phase 3 (Follow-Up)** | Targeted Defect Remediation with DOM Snapshots | `src/app/acceptance/failures.py`, `src/app/agents/specialists.py` | 10–15 mins | Design ready |

---

## 5. Development Invariants & Standards

- **Agility without Quality Compromise**: All optimizations preserve the owner's core features (acceptance test definition of done, CI gates, code review, dynamic instructions, parallel/linear modes, decision records).
- **Technology-Agnostic Rules**: Stack-specific rules live strictly in stack packs (`src/app/stacks/`); harness graph logic remains framework- and product-agnostic.
- **Deterministic Self-Learning**: Cross-run learning must use structured schema distillation (traps, flags, linter rules) rather than unstructured prompts to prevent drift and injection risks.
- **Test-First Verification**: Every harness optimization must include a regression test proving the failure on old code before deployment.
