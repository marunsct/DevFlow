# High-Steering Software Company: Architecture & Implementation Specification

**What this is.** The architectural specification and engineering blueprint for the LangGraph / Deep Agents harness that builds software products from a brief. It establishes how to transform the harness into an autonomous **Software Company** capable of delivering production-grade, tested, and verified software in **30–45 minutes** (down from 2–3 hours), with high reliability across both **local / lower-tier models (8B–32B parameters)** and **frontier models (Claude 3.7 Sonnet, GPT-4o, DeepSeek-V3/R1)**.

---

## 1. Executive Summary & Empirical Diagnosis

### 1.1 The Benchmark Reality: 8 Minutes to Build, 114 Minutes of Rework
On 2026-10-09, `run-42b84547-f159-4f2e-9ff8-868afee6e877` was benchmarked on `web-todo` (16 acceptance criteria). An empirical timing audit (`scripts/loop/loop.sh timing`) revealed the exact anatomy of harness execution time:

| Stage Family | Calls | Model Time | Output Tokens | Reasoning % | Wall Clock Reality |
|---|---|---|---|---|---|
| **Specialists (Actual Build)** | **70** | **8 min** | **43,686** | **82%** | **The app was fully built in 8 minutes!** |
| **Acceptance Authoring** | 166 | 15 min | 82,937 | 79% | Authored suite with hidden syntax defect |
| **Technical Lead Replanning** | 27 | 11 min | 73,189 | 91% | Replanned sprint 4 times due to test failures |
| **Defect Remediation** | 313 | 42 min | 246,199 | 88% | 18 defect stages attempting to fix locked suite |
| **Test Rounds & Verification** | 62 | 6 min | 29,254 | 80% | 12 test rounds repeatedly crashing on suite load |
| **Code & Architecture Review** | 41 | 5 min | 32,501 | 90% | Advisory reviews |
| **TOTALS** | **694** | **92 min** | **538,939** | **84%** | **122 min wall-clock before manual cancellation** |

### 1.2 The Root Cause: The "Locked-In Defect" Catastrophe
At minute 122 of `run-42b84547`, inspection of the product (`scripts/loop/loop.sh product`) proved:
1. **The application code was 100% complete and functionally correct**: 249 lines of clean JavaScript and HTML; all **27 unit tests passed with exit code 0** (`pass 27, fail 0`).
2. **The entire run stalled because of a single line in acceptance testing**:
   - During acceptance authoring, QA wrote:
     ```javascript
     const { test, expect } = require('@playwright/test'); // CommonJS
     ```
   - While `package.json` declared:
     ```json
     { "type": "module" } // ES Module
     ```
   - Node and Playwright crashed instantly upon file execution:
     `ReferenceError: require is not defined in ES module scope, you can use import instead`.
3. **The Lock Guard Trapped the System**:
   - The harness locked the acceptance suite into `.harness/acceptance-locks/` without first verifying that the test files could even load!
   - Once locked, the suite was immutable. When developer specialists attempted to fix `package.json` or `todo-misc.spec.js`, the harness write guard and contract checks automatically reverted their edits.
   - Result: 0 tests ran, all 16 criteria were reported as `untested`, 23 defects were opened, and the harness spent **114 minutes** in an endless, unrecoverable defect remediation loop.

---

## 2. SOTA Comparative Research: How Leading Harnesses Solve This

We analyzed the architectural patterns of the top five autonomous coding harnesses: **SWE-agent** (Princeton), **OpenHands / OpenDevin** (All-Hands AI), **Aider** (Paul Gauthier), **DeepSeek Harness**, and **Claude Code** (Anthropic).

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   COMPARATIVE ARCHITECTURE MATRIX                                      │
├──────────────────┬─────────────────┬──────────────────────┬──────────────────────┬─────────────────────┤
│ Capability       │ SWE-agent       │ Aider                │ OpenHands            │ Our Harness Target  │
├──────────────────┼─────────────────┼──────────────────────┼──────────────────────┼─────────────────────┤
│ Tool-Level Parse │ Linter checked  │ Tree-sitter AST parse│ LSP diagnostic hook  │ Immediate Write-Time│
│ Gate             │ on file command │ on every git patch   │ on file save         │ Parse Rejection     │
├──────────────────┼─────────────────┼──────────────────────┼──────────────────────┼─────────────────────┤
│ Stage Exit Gate  │ Bash exit code  │ Reprompts model on   │ Task finish check    │ Pre-Exit Diagnostic │
│                  │ verification    │ linter error         │ against agent state  │ Interceptor (1-turn)│
├──────────────────┼─────────────────┼──────────────────────┼──────────────────────┼─────────────────────┤
│ Acceptance Suite │ Static baseline │ Test command         │ Pre-flight container │ Pre-Lock AST & Dry- │
│ Verification     │ check           │ verification         │ sanity check         │ Run Load Gate       │
├──────────────────┼─────────────────┼──────────────────────┼──────────────────────┼─────────────────────┤
│ Cognitive Memory │ File context in │ Repository map via   │ Working memory doc   │ Self-Contained Work │
│ Scaffolding      │ bash prompt     │ Tree-sitter (ctags)  │ in system prompt     │ Order Context Excerpt│
├──────────────────┼─────────────────┼──────────────────────┼──────────────────────┼─────────────────────┤
│ Defect Batching  │ N/A (single     │ Single conversational│ Multi-turn issue     │ True Role-Based     │
│                  │ agent loop)     │ patch session        │ remediation agent    │ Consolidated Session│
└──────────────────┴─────────────────┴──────────────────────┴──────────────────────┴─────────────────────┘
```

### Key Architectural Insights:
1. **Aider's Syntax Gate Principle**: Aider never allows a broken edit onto the branch. If Tree-sitter detects an incomplete AST or syntax error after applying a replacement, Aider immediately rejects the diff and asks the LLM to provide a valid edit.
2. **SWE-agent's Action Feedback**: Tool feedback in SWE-agent is dense and actionable. When a tool fails or introduces a syntax error, the tool return is an explicit error message rather than an advisory warning.
3. **The Flaw in Our Previous Approach**: In `src/app/tools/repository.py`, `language_service.underlined_any` was returning an *advisory note* appended to successful tool output (`"Notes, never refusals"`). Lower-tier local models (and even reasoning frontier models) routinely ignore text notes when the tool indicates success.

---

## 3. High-Steering Lifecycle Architecture

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
    ├── AST Check: Enforce `await` on helpers & ban brittle locators
    ├── Module System Matcher: Verify `import` vs `require` against `package.json`
    ├── [DRY RUN] `npx playwright test --list`: Ensure specs load cleanly
    └── SUITE LOCKED (Zero syntax or load defects guaranteed before lock)
         │
         ▼
 3. ADAPTIVE SPRINT PLANNING (The Agile PM & Tech Lead)
    ├── Scope-based sprint caps (≤10 AC -> 1 sprint; ≤20 AC -> 2 sprints)
    └── Self-Contained Work Orders:
        └── Bundles relevant file snippets & symbol signatures in prompt
         │
         ▼
 4. GUIDED SPECIALIST EXECUTION ("Fix-Before-Exit")
    ├── Tool-Level Write Gate: Immediate parse check (node --check / py_compile)
    ├── Resilient Context-Anchored Editing: Matching old text uniquely
    └── Stage-Exit Diagnostic Interceptor: Intercepts stage completion if 
        new ReferenceErrors or missing exports exist
         │
         ▼
 5. AUTOMATED CI GATE & CONSOLIDATED REMEDIATION
    ├── Fast-Fail Test Timeouts (3s Playwright action/expect timeout)
    ├── Breaking changes automatically reverted by harness guard
    └── True Role-Based Consolidated Defect Remediation:
        └── Bundles ALL open defects for a specialist role into 1 session
         │
         ▼
 6. RELEASE GATE & SELF-LEARNING DISTILLATION
    ├── Deployment container & CI workflow verified
    └── Post-Run Distillation Node:
        └── Distills run traps and verified patterns into Stack Pack heuristics
```

---

## 4. Detailed Technical Specifications (The 8 Pillars)

### Pillar 1: Pre-Lock Acceptance Suite Static & Load Gate
- **Target Module**: `src/app/acceptance/suite.py`, `src/app/acceptance/requests.py`
- **Objective**: Guarantee that an acceptance suite can compile, import, and execute before it is locked into `.harness/acceptance-locks/`. Eliminate the 114-minute ESM loader failure mode forever.
- **Implementation**:
  1. **Module System Matcher**:
     - Inspect `package.json` in the project root. If `"type": "module"` is present:
     - Scan all test files (`*.spec.js`, `*.test.js`). If any file contains CommonJS `require(` syntax:
       Reject locking immediately:
       > *"Acceptance test file `todo-misc.spec.js` uses CommonJS `require` syntax, but `package.json` specifies `\"type\": \"module\"`. You must use ES module `import { test, expect } from '@playwright/test'`."*
  2. **AST Static Quality Checks**:
     - **Floating Promise Detector**: Detect calls to asynchronous helper functions or locators (e.g. `getTaskItemByTitle(...)`) that are not awaited before chained calls.
     - **Semantic Role Enforcer**: Reject raw CSS selectors (e.g. `.todo-item > div > button.btn-danger`) and require accessible locators (`page.getByRole('button', { name: 'Delete' })`).
  3. **The Dry-Run Collection Gate (`test --list`)**:
     - Before writing locks, the harness executes a dry-run test discovery command in the container sandbox:
       ```bash
       npx playwright test --list
       ```
     - If the command exits with non-zero exit code or prints an uncaught `ReferenceError`, `SyntaxError`, or loader failure:
       **REFUSE TO LOCK**. Pass the exact stderr back to the QA specialist in the authoring loop. The QA agent fixes the import in 5 seconds while authoring is still live.

---

### Pillar 2: Self-Contained Work Orders (Prompt Scaffolding as External Working Memory)
- **Target Module**: `src/app/analysis/work_orders.py`, `src/app/agents/technical_lead.py`
- **Objective**: Provide cognitive scaffolding for lower-tier models (8B–32B) so they do not get lost exploring large codebases, while cutting redundant tool reads from 23% to <3%.
- **Implementation**:
  1. **Enriched Work Order Payload**:
     ```python
     @dataclass(frozen=True)
     class EnrichedWorkOrder:
         id: str
         title: str
         assigned_specialist: str
         target_files: list[str]
         criteria_addressed: list[str]
         instructions: str
         file_context: dict[str, str]  # {relative_path: relevant_symbol_or_excerpt}
         symbol_signatures: list[str]  # e.g. ["function addTask(title, desc)", "export const state = ..."]
     ```
  2. **Context Budgeting**: The Tech Lead extracts relevant function signatures and interface definitions from existing files into the prompt. Specialists receive the exact symbols they must implement or call, eliminating hallucinated function names and redundant `read_file` calls.

---

### Pillar 3: Resilient Context-Anchored Editing & Exact Path Validation
- **Target Module**: `src/app/tools/agent_toolkit.py`, `src/app/tools/repository.py`
- **Objective**: Eliminate edit conflicts, line number drift, and path rejections.
- **Implementation**:
  1. **Context-Anchored Chunk Replacement**:
     - Models often fail at specifying exact line numbers after previous edits change line counts.
     - Provide an edit mode that anchors replacement by matching a unique snippet of preceding and following lines (`context_before`, `old_chunk`, `context_after`), similar to Aider's search-and-replace blocks.
  2. **Exact Workspace-Relative Path Resolution**:
     - Reject tool calls with ambiguous paths (e.g., `src/ui.js` when the file is `simple-to-do-list-app/ui.js`) with an explicit path correction hint:
       > *"Path 'ui.js' does not exist. Did you mean 'simple-to-do-list-app/ui.js'?"*
     - Never silently redirect or guess files without explicit agent confirmation.

---

### Pillar 4: Measured Test Timeouts & Sandbox Startup Optimization
- **Target Module**: `src/app/stacks/browser-javascript/`, `src/app/tools/sandbox.py`
- **Objective**: Prevent failing Playwright assertions from hanging for 30 seconds per test.
- **Implementation**:
  1. **Fast-Fail Playwright Configuration**:
     - In `playwright.config.js` scaffold:
       ```javascript
       export default {
         timeout: 10000,           // 10s max per test (down from 30s)
         expect: { timeout: 3000 },// 3s max per expect (down from 10s)
         use: {
           actionTimeout: 3000,    // 3s max per click/fill
           navigationTimeout: 5000,// 5s max per page.goto
         }
       };
       ```
     - When an element is missing, the test fails in 3 seconds instead of 30 seconds. A 10-test failure round drops from 5 minutes to 30 seconds.
  2. **Sandbox Server Readiness Ping**:
     - Replace static `sleep` calls with active polling against `http://127.0.0.1:<port>` with 100ms intervals, proceeding the instant the HTTP 200 response is received.

---

### Pillar 5: Continuous Self-Learning Engine via Deterministic Distillation
- **Target Module**: `src/app/learning/distiller.py`, `src/app/stacks/seed.py`
- **Objective**: Enable the harness to "learn" across runs without accumulating unstructured prompt drift or hallucinated rules.
- **Implementation**:
  1. **Post-Run Distillation Node**:
     - At the end of every run (successful or failed), execute an offline distillation step that audits:
       - Every git revert performed by `engineering.py` (e.g., `defect_fix_1_10 broke 14 tests`).
       - Every syntax failure caught by the pre-lock AST gate.
       - Every Decision Record (`DR-n`) agreed upon during sprint planning.
  2. **Deterministic Schema Verification**:
     - Distilled heuristics are validated against strict JSON schema:
       ```json
       {
         "stack_pack": "browser-javascript",
         "heuristics": [
           {
             "category": "acceptance_testing",
             "rule": "Always use ES module `import` syntax when package.json contains `type: module`.",
             "evidence_type": "loader_crash_revert"
           }
         ]
       }
       ```
     - Validated heuristics are merged into `src/app/stacks/heuristics/<pack>.json` and injected into stack-pack guidance for future runs. Core harness logic remains 100% agnostic.

---

### Pillar 6: Dual-Track Cognitive Steering (Local Models vs. Frontier Models)
- **Target Module**: `src/app/models/steering.py`, `src/app/agents/`
- **Objective**: Steer local / lower-tier models (8B–32B) through rigorous structural constraints while allowing frontier models (Claude 3.7, GPT-4o) maximum reasoning autonomy.
- **Implementation**:
  1. **Local Model Steering Track (8B–32B)**:
     - **Explicit Step-by-Step Prompt Scaffolding**: Decompose broad tasks into numbered sub-actions (1. Read target function, 2. Make minimal edit, 3. Run unit test).
     - **Structured Tool Grammar**: Enforce strict tool parameter schemas to prevent malformed JSON arguments.
     - **Narrow Work Orders**: Limit work orders for lower-tier models to single files and ≤2 criteria per order.
  2. **Frontier Model Track**:
     - Maintain concise prompts that maximize the model's internal reasoning budget (80%+ reasoning tokens).
     - Group related criteria into broader work orders for efficient implementation.
  3. **Non-Mutating Policy**: Never modify the user's selected model or settings. Steering adaptations are purely prompt- and harness-level structures.

---

### Pillar 7: Immediate In-Stage IDE Linting & Syntax Gate ("Fix-Before-Exit")
- **Target Module**: `src/app/tools/repository.py`, `src/app/analysis/language_service.py`, `src/app/agents/specialists.py`
- **Objective**: Catch syntax, type, and import errors at the moment of creation, resolving them before the agent exits its stage.
- **Implementation**:
  1. **Layer 1: Hard Syntax Rejection at Write Time (`repository.py`)**:
     - When `write_file` or `edit_file` is invoked, execute a syntax check before writing to disk:
       - For JavaScript/TypeScript: `node --check <file>` or TypeScript language service parse.
       - For Python: `python -m py_compile <file>`.
     - If the file cannot be parsed:
       **Reject the tool call**. Return an explicit error:
       ```json
       {
         "error": "SyntaxError in 'ui.js' line 42: Unexpected token '}'. The file was NOT modified. Please correct the syntax and call edit_file again."
       }
       ```
  2. **Layer 2: Pre-Exit Diagnostic Interceptor (`specialists.py`)**:
     - When a specialist agent attempts to complete its stage by returning `SpecialistOutput`:
     - The harness intercepts the exit and runs `language_service.underlined_any` over all files touched by the specialist.
     - If high-confidence diagnostics (ReferenceError, missing exports, undeclared functions) are detected:
       **Pause stage completion and reprompt the specialist (1-turn bound)**:
       > *"Stage completion blocked: The language service detected 1 high-confidence error in `state.js`:\nLine 15: `validateTitle` is imported from `./model.js` but `./model.js` does not export it.\nFix this error in `model.js` or `state.js` before completing your work."*
     - If the specialist resolves it, the stage completes cleanly. If unresolved after 1 turn, the stage completes and the existing CI gate handles triage.

---

### Pillar 8: True Role-Based Consolidated Defect Remediation
- **Target Module**: `src/app/graph/workflow.py`
- **Objective**: Eliminate sequential defect ping-pong. In `run-42b84547`, Sprint 2 ran 9 sequential defect stages, and Sprint 1 attempt 4 started 13 sequential defect stages.
- **Implementation**:
  1. **Role Grouping**:
     - When `test_round` completes with failures, group all open defects by specialist role:
       - `ui_ux_specialist`: Defects #1, #2, #3, #4, #5, #6, #7, #8, #9 (all UI acceptance criteria).
       - `backend_specialist`: Defects #11 (state persistence).
       - `testing_specialist`: Defects #10 (test harness script).
  2. **Consolidated Remediation Invocation**:
     - For each role with open defects, spawn **AT MOST ONE** remediation session per test round.
     - The specialist prompt contains:
       - The consolidated list of all failing criteria for that role.
       - The failure stack trace and DOM snapshot from Playwright.
       - The instructions to fix the implementation and run `npm test` to verify.
  3. **Verification**:
     - A single run of `npm test` and `npm run test:acceptance` verifies all fixes simultaneously.
     - Reduces 10–20 sequential agent invocations down to **1 or 2 consolidated stages**, saving 30–45 minutes of wall-clock time per sprint.

---

## 5. Mathematical Efficiency Model & Expected Runtime Reductions

Based on empirical data from `run-42b84547` and historical runs, we model the wall-clock impact of the 8 Pillars on a standard 16-criteria `web-todo` application:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   WALL-CLOCK EFFICIENCY MODEL                                   │
├───────────────────────────────┬──────────────────────┬────────────────────┬─────────────────────┤
│ Lifecycle Phase               │ Baseline Run         │ High-Steering Run  │ Mechanism           │
├───────────────────────────────┼──────────────────────┼────────────────────┼─────────────────────┤
│ 1. Intake & Architecture      │ 4 min (13 calls)     │ 3 min (8 calls)    │ Scope fast-path     │
├───────────────────────────────┼──────────────────────┼────────────────────┼─────────────────────┤
│ 2. Acceptance Authoring       │ 15 min (166 calls)   │ 8 min (40 calls)   │ AST check + Dry-run │
│    & Quality Lock Gate        │                      │                    │ prevents bad lock   │
├───────────────────────────────┼──────────────────────┼────────────────────┼─────────────────────┤
│ 3. Sprint Planning            │ 11 min (27 calls)    │ 3 min (6 calls)    │ Dynamic sprint cap  │
├───────────────────────────────┼──────────────────────┼────────────────────┼─────────────────────┤
│ 4. Specialist Implementation  │ 8 min (70 calls)     │ 8 min (50 calls)   │ Self-contained WOs  │
├───────────────────────────────┼──────────────────────┼────────────────────┼─────────────────────┤
│ 5. CI Gate & Test Execution   │ 6 min (62 calls)     │ 2 min (15 calls)   │ 3s fast-fail limits │
├───────────────────────────────┼──────────────────────┼────────────────────┼─────────────────────┤
│ 6. Defect Remediation         │ 42 min (313 calls)   │ 8 min (25 calls)   │ True Consolidated   │
│    (Rework Loop)              │ (18 separate stages) │ (2 role sessions)  │ Batching + In-Stage │
├───────────────────────────────┼──────────────────────┼────────────────────┼─────────────────────┤
│ 7. Milestone Review & Release │ 5 min (15 calls)     │ 3 min (6 calls)    │ Direct release gate │
├───────────────────────────────┼──────────────────────┼────────────────────┼─────────────────────┤
│ Overhead / Turn Latency       │ 31 min (idle / wait) │ 5 min              │ Fast-fail timeouts  │
├───────────────────────────────┼──────────────────────┼────────────────────┼─────────────────────┤
│ TOTAL RUNTIME                 │ 122 min (cancelled)  │ 40 min (COMPLETE)  │ 67% Time Reduction  │
└───────────────────────────────┴──────────────────────┴────────────────────┴─────────────────────┘
```

---

## 6. Prioritized Implementation Roadmap

| Milestone | Deliverables | Target Modules | Value & Impact |
|---|---|---|---|
| **M1: Pre-Lock Acceptance Suite AST & Load Gate** | 1. Module System Matcher (`import` vs `require`).<br>2. Floating promise AST detector.<br>3. `npx playwright test --list` dry-run verification before lock. | `src/app/acceptance/suite.py`<br>`src/app/acceptance/requests.py` | **P0 (Critical)**: Eliminates the 114-minute ESM crash that doomed `run-42b84547`. |
| **M2: In-Stage "Fix-Before-Exit" Syntax Gate** | 1. Hard parse rejection on write tool (`node --check` / `py_compile`).<br>2. Pre-exit diagnostic interception in specialist node. | `src/app/tools/repository.py`<br>`src/app/agents/specialists.py` | **P0 (Critical)**: Resolves syntax errors in 1 turn before defect triage starts. |
| **M3: True Role-Based Consolidated Remediation** | Collapse sequential defect cursor into single consolidated remediation session per specialist role. | `src/app/graph/workflow.py` | **P0 (Critical)**: Cuts 10–18 defect stages down to 1–2 stages, saving 35+ mins. |
| **M4: Measured Fast-Fail Test Timeouts** | Explicit 3s Playwright action/expect timeouts and active sandbox readiness polling. | `src/app/stacks/browser-javascript/`<br>`src/app/tools/sandbox.py` | **P1 (High)**: Reduces test failure wait times from 30s to 3s per test. |
| **M5: Self-Contained Work Orders** | Embed file excerpts and symbol signatures into work-order prompts for local model steering. | `src/app/analysis/work_orders.py`<br>`src/app/agents/technical_lead.py` | **P1 (High)**: Prevents local models from getting lost; cuts redundant reads. |
| **M6: Continuous Self-Learning Engine** | Offline distillation of Decision Records and reverts into `src/app/stacks/heuristics/<pack>.json`. | `src/app/learning/distiller.py`<br>`src/app/stacks/` | **P2 (Strategic)**: Safely distills engineering wisdom across runs. |

---

## 7. Verification & Safety Invariants

1. **Owner Features Preserved**:
   - Dynamic agent-instruction injection preserved.
   - Parallel/linear toggles preserved.
   - Sprint summaries and Decision Records preserved.
2. **Technology-Agnostic Core**:
   - All language- and stack-specific rules live strictly in `src/app/stacks/`.
   - Core harness graph logic in `src/app/graph/workflow.py` remains 100% agnostic.
3. **No Run IDs in Code, Prompts, or Tests**:
   - Strictly verified by `tests/test_no_run_ids_in_the_source.py`.
4. **Banned Word Rules in Prompts**:
   - Any new prompt additions tested to ban the whole words `task`, `tasks`, `to-do`, `todo`, `button`, `click`, and `checkbox`.
5. **Test-First Verification**:
   - Every fix verified by a test proven to fail on the old code.
   - Full test suite passing (`scripts/loop/loop.sh suite`).
