# High-Steering Software Company: Architecture & Implementation Specification

**What this is.** The technical implementation specification for optimizing the LangGraph / Deep Agents harness to operate as an autonomous, professional Software Company. It defines how to build verified, production-grade software products from a brief while ensuring that **local and lower-tier models** (8B–32B open-weights running via LM Studio, vLLM, or Ollama) are steered reliably to completion without infinite loops, tool errors, or multi-hour churn, while enabling **frontier models** (Claude 3.5 Sonnet, GPT-4o) to operate at maximum speed.

---

## 1. Vision & Architectural Rationale

### 1.1 The Software Company Operating Model
The harness does not simply generate raw code from a prompt; it emulates the end-to-end discipline of a professional engineering organization:
1. **Product Intake & Requirements Engineering**: Deconstructs a brief into user stories, technical boundaries, and numbered acceptance criteria (`AC-1`..`AC-N`).
2. **Pre-Verified Acceptance Testing**: A dedicated QA role authors an end-to-end acceptance suite *before* implementation begins.
3. **Agile Sprint & Work Order Planning**: The project is split into vertical slices with explicit file and criterion assignments.
4. **Implementation & Unit Testing**: Domain specialists build components, backed by unit tests.
5. **Continuous Integration & Automated Defect Remediation**: Changes are proven by CI before acceptance; breaking changes are automatically rolled back.
6. **Milestone Review & Release Gate**: The product is accepted only when all criteria pass and deployment files are generated.

### 1.2 Cognitive Scaffolding: Why Structured Documentation is Essential
Lower-tier and local models suffer from known cognitive limitations:
- **Attention Drift**: Over long horizons or large context windows, models lose track of edge cases and requirements.
- **Context Contamination**: Unstructured prompts lead to hallucinations where the model invents APIs, dependencies, and file paths.
- **Inability to Plan and Execute Monolithically**: Asking a lesser model to "build this app" in one turn results in incomplete toy code.

**Structured documents are externalized working memory.** The Technical Specification, Acceptance Criteria table, and granular Work Orders anchor the model. They break a complex application into bite-sized, deterministic tasks where even an 8B model can succeed.

### 1.3 The Core Bottlenecks in the Current Architecture
The reason runs currently take 2–4 hours on local models is **not the documentation itself**; it is compounding mechanical friction:
1. **The 45-Minute Acceptance Dispute Loop**: QA authors Playwright tests with un-awaited helper calls (`const item = getTaskItemByTitle(...)`) or brittle CSS selectors. These tests lock, crash during runtime evaluation, trigger the Acceptance Dispute Engine (DR-5, DR-7), and reopen the suite for 6+ QA rounds.
2. **Tool Parameter & Path Rejection**: Local models frequently call `write_artifact("package.json")` instead of `simple-to-do-list-app/package.json`. Each rejection forces a 30-second inference retry.
3. **Line-Number Offset Invalidation**: Calling `replace_lines(10, 15)` shifts the file's line count. Subsequent edits fail with `Line N is not what you expected`, forcing the model to re-read the file and burning its tool budget.
4. **Exploratory Tool Churn**: Developers start work orders with zero context, spending 10–15 tool calls running `ls` and `read_file` to find symbol definitions.
5. **Unbounded Test Timeouts**: Default 30s Playwright timeouts make a single failing acceptance run take 5–8 minutes across 16 tests.

---

## 2. The Target Architecture: High-Steering Lifecycle

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                            HIGH-STEERING LIFECYCLE                               │
└──────────────────────────────────────────────────────────────────────────────────┘

   [ USER BRIEF ]
         │
         ▼
 1. PRODUCT INTAKE & SPECIFICATION
    ├── Product Brief & Tech Spec drafted
    ├── Acceptance Criteria numbered (AC-1..AC-N)
    └── Stack Pack scaffolded & verified by smoke tests
         │
         ▼
 2. PRE-VERIFIED QA SUITE (Deterministic Gate)
    ├── QA Authors Playwright tests
    ├── [NEW] AST Static Linter verifies tests *before* locking:
    │   ├── Floating promise detector (enforces `await` on helpers)
    │   ├── Semantic role enforcer (bans raw CSS selectors)
    │   └── Prototype method validator
    └── SUITE LOCKED (Zero runtime dispute loops guaranteed)
         │
         ▼
 3. ADAPTIVE SPRINT PLANNING (The Agile PM & Tech Lead)
    ├── Scope-based sprint capping (1–2 sprints for <=15 criteria)
    └── [NEW] Self-Contained Work Orders:
        └── Bundles relevant file snippets & symbol signatures in prompt
         │
         ▼
 4. GUIDED SPECIALIST EXECUTION
    ├── [NEW] Fuzzy Path Normalization (auto-resolves workspace paths)
    ├── [NEW] Resilient Context-Anchored Editing (no line-offset crashes)
    └── IDE-grade Language Service checks syntax on write
         │
         ▼
 5. AUTOMATED CI GATE & FAST-FAIL VERIFICATION
    ├── Unit tests & Acceptance tests run with 3s timeouts
    ├── Breaking changes automatically reverted by harness guard
    └── Batch Defect Remediation:
        └── Passes DOM snapshot and Playwright failure trace to fixer
         │
         ▼
 6. RELEASE GATE & SELF-LEARNING DISTILLATION
    ├── Container & CI workflow generated from verified pack
    └── [NEW] Post-Run Distillation Node:
        └── Distills run traps and verified patterns into Stack Pack heuristics
```

---

## 3. Detailed Technical Specifications

### Pillar 1: Pre-Emptive Acceptance Suite AST Linter
- **Target Module**: `src/app/acceptance/suite.py`, `src/app/acceptance/requests.py`
- **Objective**: Prevent flawed acceptance tests from ever being locked, completely eliminating the 45-minute dispute loop.
- **Implementation**:
  1. Add `ast_lint_acceptance_test(code: str) -> list[str]` to `app/acceptance/suite.py`:
     - **Floating Promise Check**: Parse the AST (using Tree-Sitter or regex-guided AST analysis). Identify function calls defined as `async` or returning promises (e.g. `getTaskItemByTitle`). If called without an immediate `await`, flag:
       > *"Line N: Call to async helper `getTaskItemByTitle(...)` is missing `await`. You must await the promise before calling locator methods on it."*
     - **Semantic Role Enforcer**: Scan for locator calls using CSS tag selectors for interactive controls (e.g. `locator('input[type="checkbox"]')`, `locator('button')`). Flag:
       > *"Line N: CSS selector `input[type="checkbox"]` is prohibited for interactive controls. Use semantic Playwright queries: `getByRole('checkbox', { name: '...' })` or `getByLabel('...')`."*
     - **Locator Method Validator**: Verify that chained methods match valid Playwright `Locator` APIs (preventing calls like `locator.find()`).
  2. Integrate into `suite.gaps()` and `acceptance_review`:
     - If any test file contains AST lint errors, the suite is automatically rejected during authoring rounds with the exact line numbers and suggested fixes.
     - The suite cannot transition to `locked` until all AST lint errors are zero.

---

### Pillar 2: Self-Contained Work Orders (Prompt Ingestion over Tool Exploration)
- **Target Module**: `src/app/analysis/work_orders.py`, `src/app/agents/technical_lead.py`
- **Objective**: Eliminate 10–15 exploratory tool calls (`ls`, `read_file`) per specialist, reducing redundant reads to <3% and preserving the model's call budget.
- **Implementation**:
  1. In `app/analysis/work_orders.py`, enrich the work order dispatch structure:
     ```python
     @dataclass(frozen=True)
     class EnrichedWorkOrder:
         id: str
         title: str
         assigned_specialist: str
         target_files: list[str]
         criteria_addressed: list[str]
         instructions: str
         file_context: dict[str, str]  # {relative_path: file_content_or_skeleton}
         symbol_signatures: list[str]  # ["function validateTitle(text)", "export function addTask(...)"]
     ```
  2. When dispatching a work order to a specialist in `app/agents/specialists.py`:
     - Read the target files and their direct dependencies.
     - Embed the current code of target files directly under a `--- Target Files to Edit ---` section in the specialist's prompt.
  3. The specialist receives everything needed to write code on **Turn 1**.

---

### Pillar 3: Resilient Editing & Fuzzy Path Normalization
- **Target Module**: `src/app/tools/agent_toolkit.py`, `src/app/tools/repository.py`
- **Objective**: Eliminate tool-call rejection errors (`failed=35` in audits) caused by path hallucinations and line-number drift.
- **Implementation**:
  1. **Fuzzy Path Normalization**:
     - In `build_artifact_write_tool` and `build_line_replace_tool`, pass `relative_path` through `normalize_workspace_path(repo_root, relative_path)`:
     - If `relative_path` does not exist directly, search the workspace for a unique matching filename (e.g. `package.json` $\rightarrow$ `simple-to-do-list-app/package.json`).
     - If exactly one match exists, transparently resolve to that path and execute the edit.
  2. **Context-Anchored Chunk Replacement**:
     - Provide `replace_chunk(relative_path, anchor_before, target_code, anchor_after)` alongside `replace_lines`:
     - Matches 1–2 lines of context above and below the edit block.
     - Never fails when line numbers shift due to previous edits in the same session.
  3. **Offset-Compensated Line Replacement**:
     - Maintain a per-stage edit offset map. When edit 1 changes the line count by $+k$, automatically adjust line numbers for subsequent calls to `replace_lines` in that stage.

---

### Pillar 4: Persistent Sandbox Daemon & Fast-Fail Test Timeouts
- **Target Module**: `src/app/stacks/`, `src/app/tools/sandbox.py`
- **Objective**: Reduce acceptance test execution time from 5–8 minutes down to 15–25 seconds.
- **Implementation**:
  1. In stack pack Playwright configurations (`playwright.config.js`):
     - Inject aggressive timeouts for harness testing:
       ```javascript
       use: {
         actionTimeout: 3000,     // 3 seconds max per action
         navigationTimeout: 5000, // 5 seconds max per navigation
       },
       expect: {
         timeout: 3000,           // 3 seconds max per assertion
       }
       ```
  2. In `app/tools/sandbox.py`:
     - Pre-flight connection check: Before launching Playwright, poll the local web server port with a 500ms socket probe. If the server is down, fail immediately with an actionable error rather than waiting 30 seconds per test.

---

### Pillar 5: Self-Learning Engine via Deterministic Knowledge Distillation
- **Target Module**: `src/app/learning/distiller.py`, `src/app/stacks/seed.py`
- **Objective**: Enable cross-run learning without the security and prompt-injection risks of unstructured agent memory.
- **Implementation**:
  1. **Post-Run Distillation Node (`app/learning/distiller.py`)**:
     - Executed at the conclusion of every benchmark run.
     - Inspects:
       - Recorded Decision Records (`DR-1`..`DR-N`).
       - Harness git reverts (e.g. `Reverted defect_fix_1_10: it broke 14 test(s)`).
       - Fixed lint errors and Playwright runtime errors.
     - Distills structured heuristics conforming to a strict JSON schema:
       ```json
       {
         "stack": "browser-javascript",
         "traps": [
           {
             "category": "acceptance_testing",
             "rule": "Playwright helper functions returning locators must be async and awaited before invoking locator methods.",
             "evidence_decision": "DR-5"
           },
           {
             "category": "unit_testing",
             "rule": "Node --test runner requires --import ./test-setup.mjs to polyfill window and localStorage when testing DOM modules.",
             "evidence_stage": "specialist_testing_1"
           }
         ]
       }
       ```
  2. **Storage**: Saved to `src/app/stacks/heuristics/<stack-pack>.json`.
  3. **Injection**: In `src/app/stacks/seed.py`, load verified heuristics for the selected stack and inject them under `--- Engineering Guidelines & Known Stack Traps ---` in role prompts.

---

### Pillar 6: Dual-Track Steering (Local vs. Frontier Model Adaptivity)
- **Target Module**: `src/app/models/roles.py`, `src/app/graph/workflow.py`
- **Objective**: Automatically tune harness execution parameters to match the model tier.
- **Implementation**:
  1. Detect model tier:
     - If `OPENAI_BASE_URL` is local loopback/docker host or `MODEL_TIER=local`: activate **High-Steering Track**.
     - If provider is Anthropic/OpenAI hosted or `MODEL_TIER=frontier`: activate **Autonomous Track**.
  2. Parameter Tuning Matrix:

| Feature | Local / Lower-Tier Model Track | Frontier Model Track (Claude 3.5 Sonnet / GPT-4o) |
|---|---|---|
| **Work Order Scope** | Micro work orders (1 file per order) | Macro work orders (multi-file features) |
| **In-Context Snippets** | Pre-fills full target file in prompt | Provides symbol RepoMap outline |
| **Path & Edit Tolerance** | Fuzzy path matching & anchor replacement | Standard strict paths |
| **Sprint Batches** | 1–2 sprints max | Up to 3 parallel sprints |
| **CI Feedback** | Unit test check on every file edit | Full suite at CI batch gate |

---

## 4. Prioritized Implementation Roadmap

| Milestone | Deliverables | Target Modules | Est. Time Savings | Priority |
|---|---|---|---|---|
| **M1: Test Quality & Timeouts** | Pre-Lock AST Acceptance Linter; 3s Playwright timeouts | `src/app/acceptance/suite.py`, `src/app/stacks/` | **45–60 mins** | **P0** |
| **M2: Resilient Tooling** | Fuzzy path normalization; Context-anchored edits | `src/app/tools/agent_toolkit.py` | **15–25 mins** | **P0** |
| **M3: Self-Contained Work Orders** | In-context file and symbol snippets in work order prompts | `src/app/analysis/work_orders.py`, `src/app/agents/` | **15–20 mins** | **P1** |
| **M4: Self-Learning Engine** | Post-run distillation node and heuristics injection | `src/app/learning/`, `src/app/stacks/seed.py` | **15–20 mins** | **P1** |
| **M5: Dual-Track Model Tuning** | Automatic model-tier detection and steering parameters | `src/app/models/`, `src/app/graph/workflow.py` | **10–15 mins** | **P2** |

---

## 5. Verification & Safety Invariants

1. **Owner Features Preserved**: Dynamic agent instructions, parallel/linear toggles, sprint summaries, and decision records remain untouched.
2. **Deterministic Rules Only**: Stack-specific guidance lives strictly in stack packs (`src/app/stacks/`); core harness graph logic remains framework- and product-agnostic.
3. **No Unstructured Memory Drift**: All self-learning data is validated against a strict schema and verified against run evidence.
4. **Test-First Verification**: Every change to harness logic or tools must include a regression test proven to fail on the old code before deployment.
