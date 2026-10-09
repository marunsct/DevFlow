# High-Steering Software Company: Architecture & Implementation Specification

**What this is.** A proposed architecture for improving the LangGraph / Deep Agents harness that builds software products from a brief. It describes ways to improve reliability and efficiency across local and hosted models; it does not establish that the proposed runtime targets or savings have been achieved.

**How to use this specification.** Treat [harness-improvement-plan.md](./harness-improvement-plan.md) as the execution backlog and [monitoring-handover.md](./monitoring-handover.md) as the source for current measurements and operating rules. Keep their priorities and implementation status aligned with this document. Several foundations described below already exist in partial form, including pre-lock suite checks, language-service checks at the CI gate, guarded `edit_artifact` and `replace_lines` tools, scope-based sprint caps, and co-defect batching. Extend those mechanisms rather than creating parallel systems. Keep language- and framework-specific behavior in stack packs, and do not automatically change or select the owner's model or settings.

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

### 1.2 Structured Context as a Harness Reliability Tool
Long-running agent workflows can lose track of requirements, repeat exploration, or make unsupported assumptions. Treat these as measurable workflow risks, not fixed traits of a model tier.

**Structured documents are shared working context.** The Technical Specification, Acceptance Criteria, and Work Orders make requirements and ownership explicit. They can help agents keep work bounded, but do not make work deterministic or guarantee success; verify their effect through benchmark quality and cost measures.

### 1.3 The Core Bottlenecks in the Current Architecture
Prior audits identified the following potential sources of run time and failure. Their rates and costs are historical observations, not a current baseline; re-measure them before prioritizing work:
1. **Acceptance-suite defects**: A missing `await` or brittle locator can make a suite fail after it is locked, requiring dispute and repair rounds. Static checks can catch only patterns they can prove.
2. **Tool parameter and path errors**: A wrong workspace-relative path can cause a rejected write and another model/tool round trip. Never trade this error for silently writing to a guessed path.
3. **Edit conflicts**: File changes can make previously read line numbers stale. The current edit tools include guards; measure their remaining failure rate before adding remapping.
4. **Repeated exploration**: Agents may re-read files or search for symbols. Measure repeat reads and prompt size before inlining source into every work order.
5. **Slow test failures**: Test-runner defaults may make repeated failures expensive. Measure startup and failure duration before changing timeout policy.

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
    ├── [PROPOSED] Stack-aware static checks verify known test defects before locking:
    │   ├── Floating promise detector (enforces `await` on helpers)
    │   ├── Semantic role enforcer (bans raw CSS selectors)
    │   └── Prototype method validator
    └── SUITE LOCKED (Known static defects are reduced; runtime disputes remain possible)
         │
         ▼
 3. ADAPTIVE SPRINT PLANNING (The Agile PM & Tech Lead)
    ├── Existing, tested scope-based sprint caps (preserved)
    └── [NEW] Self-Contained Work Orders:
        └── Bundles relevant file snippets & symbol signatures in prompt
         │
         ▼
 4. GUIDED SPECIALIST EXECUTION
    ├── [PROPOSED] Exact workspace-relative path validation (no silent redirection)
    ├── [NEW] Resilient Context-Anchored Editing (no line-offset crashes)
    └── IDE-grade Language Service checks syntax on write
         │
         ▼
 5. AUTOMATED CI GATE & FAST-FAIL VERIFICATION
    ├── Unit and acceptance tests use measured, bounded timeouts
    ├── Breaking changes automatically reverted by harness guard
    └── Verified Co-Defect Remediation:
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

### Pillar 1: Pre-Lock Acceptance Suite Static Checks
- **Target Module**: `src/app/acceptance/suite.py`, `src/app/acceptance/requests.py`
- **Objective**: Catch a measured set of common, statically detectable suite defects before lock. Keep runtime execution and the dispute path as necessary backstops; static checks cannot guarantee zero disputes.
- **Implementation**:
  1. Extend the existing suite checks with a parser-backed validator for the selected stack's test language. Do not use Python's `ast` module or a regex as a substitute for parsing JavaScript or TypeScript. Where the test environment cannot resolve helper definitions, report only patterns the checker can prove:
     - **Floating Promise Check**: For configured JavaScript or TypeScript stacks, use available type information or a stack-pack rule to identify known asynchronous helpers called without `await`. Do not claim general promise analysis when the helper's return type is unknown:
       > *"Line N: Call to async helper `getTaskItemByTitle(...)` is missing `await`. You must await the promise before calling locator methods on it."*
     - **Accessible Locator Guidance**: Prefer role- and label-based queries for interactive controls. Flag only configured, high-confidence brittle patterns; allow justified selectors for cases without an accessible role or label. Feedback should recommend an appropriate semantic query when one is available.
     - **Locator Method Validator**: Reuse the selected stack pack's declared runner contract to check known invalid methods; do not assume one universal Playwright prototype contract for every stack.
  2. Integrate actionable findings into the existing suite review and lock checks. Findings must identify the file, line, and reason. Keep the existing dispute/reopen flow for runtime failures and for cases the static checker cannot prove.
  3. **Stack-Pack Pre-Seeded Test Helpers (`app/stacks/`)**:
     - Provide small, tested helper examples only in stack packs that use them. Do not require every stack to ship JavaScript helpers, and retain tests proving the helpers work with that stack's actual runner.

---

### Pillar 2: Self-Contained Work Orders (Prompt Ingestion over Tool Exploration)
- **Target Module**: `src/app/analysis/work_orders.py`, `src/app/agents/technical_lead.py`
- **Objective**: Test whether bounded, relevant context reduces repeated reads without inflating prompts, becoming stale, or displacing the specialist's own inspection.
- **Implementation**:
  1. If measurements justify it, add bounded context to the work-order dispatch structure:
     ```python
     @dataclass(frozen=True)
     class EnrichedWorkOrder:
         id: str
         title: str
         assigned_specialist: str
         target_files: list[str]
         criteria_addressed: list[str]
         instructions: str
         file_context: dict[str, str]  # {relative_path: bounded, relevant excerpt}
         symbol_signatures: list[str]  # ["function validateTitle(text)", "export function addTask(...)"]
     ```
  2. Start with file paths, relevant symbol signatures, and short excerpts tied to assigned criteria. Include full file contents only when a measured case warrants it and within a token budget.
  3. Capture context from the current workspace at dispatch time, label its source paths, and avoid treating it as authoritative after edits. Specialists must still inspect and validate the current file before editing.
  4. Compare repeated-read rate, prompt size, model calls, and quality against the same brief and configuration. Do not assume inline context eliminates exploration.

---

### Pillar 3: Safe Editing & Explicit Path Validation
- **Target Module**: `src/app/tools/agent_toolkit.py`, `src/app/tools/repository.py`
- **Objective**: Reduce edit failures without silently targeting the wrong file or introducing state that becomes stale after another edit.
- **Implementation**:
  1. **Exact Path Validation**:
     - Keep writes constrained to the workspace and require an unambiguous, repository-relative path. If a path is missing, return likely matches as suggestions only; never silently redirect a write based on a basename such as `package.json`.
  2. **Use Existing Edit Guards First**:
     - The harness already provides exact-passage editing and guarded line replacement. Measure their failure modes on comparable runs before adding another edit API.
     - If a context-anchored edit is still needed, require the expected old text to match uniquely and refuse to change the file when it is absent or ambiguous.
  3. **Do Not Maintain an Offset Map**:
     - Per-stage offsets can go stale after overlapping or external edits. Prefer the current file contents and explicit context guards; add no automatic line remapping unless a replay test proves it is safe for concurrent and repeated edits.

---

### Pillar 4: Measured Test Timeouts and Sandbox Startup Checks
- **Target Module**: `src/app/stacks/`, `src/app/tools/sandbox.py`
- **Objective**: Fail promptly on confirmed startup failures while preserving enough time for slower but valid operations and test environments.
- **Implementation**:
  1. In stack-pack Playwright configurations, make timeouts explicit and configurable. Select separate readiness, action, navigation, assertion, and overall-test limits from representative timing data with a safety margin. Test under the supported execution environment and report which limit expired; do not apply one global, aggressive timeout without evidence.
  2. In `app/tools/sandbox.py`, distinguish a server that is not ready yet from a confirmed connection failure. Use a bounded readiness check and report the URL, check performed, and failure clearly; a `404` can indicate a bad route rather than a stopped server.
  3. Treat a persistent sandbox daemon as a separate experiment. Adopt it only if repeated process-start measurements show material savings, and define isolation, cleanup, cancellation, and recovery behavior before sharing a session across commands.

---

### Pillar 5: Verified Stack-Pack Lessons (Exploratory)
- **Target Module**: `src/app/learning/distiller.py`, `src/app/stacks/seed.py`
- **Objective**: Explore whether verified, stack-specific lessons can reduce repeated mistakes without turning untrusted run output into persistent instructions.
- **Implementation**:
  1. **Candidate Lesson Extraction**:
     - Start as an offline report, not an automatic graph node that changes future prompts.
     - Candidate evidence may include:
       - Recorded Decision Records (`DR-1`..`DR-N`).
       - Harness git reverts (e.g. `Reverted defect_fix_1_10: it broke 14 test(s)`).
       - Fixed lint errors and Playwright runtime errors.
     - A schema validates shape, not truth or safety. Do not persist arbitrary model-written rules; accept a lesson only when a deterministic check or reviewed regression test supports it. Store a small allowlisted record:
       ```json
       {
         "stack_pack": "browser-javascript",
         "version": 1,
         "traps": [
           {
             "category": "acceptance_testing",
             "rule": "Await asynchronous Playwright helpers before using the Locator they resolve to.",
             "evidence": "Regression test: <stable test name>"
           },
           {
             "category": "unit_testing",
             "rule": "A verified, version-scoped stack-pack lesson goes here.",
             "evidence": "Regression test: <stable test name>"
           }
         ]
       }
       ```
  2. **Storage**: Keep approved records versioned with their stack pack, with provenance, review status, and a removal path. Exclude run-specific identifiers, secrets, user-provided instructions, and raw transcript text.
  3. **Injection**: Only after tests show that the records are useful and safe, inject approved stack-specific records through the existing stack-pack mechanism. Treat records as data, not executable instructions; limit their size and make changes reversible.

---

### Pillar 6: Bounded In-Stage Syntax and Diagnostic Feedback
- **Target Module**: `src/app/tools/repository.py`, `src/app/analysis/language_service.py`, `src/app/agents/specialists.py`, `src/app/graph/engineering.py`
- **Objective**: Surface high-confidence, newly introduced syntax and reference errors earlier than the existing CI gate, while retaining CI and test execution as the acceptance authority.
- **Design rationale**: Earlier feedback may reduce the cost of fixing some errors. This is a hypothesis for this harness, not a claim that it matches the behavior or results of another coding tool.
- **Current Behavior and Remaining Gap**:
  - The repository already uses language-service diagnostics at the batch CI gate. The remaining proposal is to test whether a bounded feedback opportunity inside a specialist stage catches newly introduced errors sooner.
  - Do not treat every diagnostic as a defect: compare against the pre-change baseline, scope findings to the files and changes at hand, and account for missing language servers or incomplete project metadata.
- **Implementation**:
  1. **Layer 1: Hard Syntax Rejection at Write Time (`src/app/tools/repository.py`)**:
     - In write tools, run only the parser configured and available for the selected stack (for example, `node --check` for JavaScript or `ast.parse` for Python).
     - If parsing is a required, reliable check for that stack and the content cannot be parsed, reject the edit without modifying the file and return a clear file/line diagnostic:
       ```json
       {"error": "Refusing to save 'ui.js': SyntaxError on line 34: Unexpected token '}'. Fix the syntax and resubmit."}
       ```
     - Prevents corrupted, un-parseable code from ever landing on disk.
  2. **Layer 2: In-Stage Pre-Exit Diagnostic Gate (`src/app/agents/specialists.py`)**:
     - When a specialist (developer or defect fixer) returns `SpecialistOutput` to conclude its stage:
     - Before the graph accepts the output and moves to the next node, run `language_service.underlined_any` over every file touched by that specialist.
     - If a touched file has a newly introduced, high-confidence diagnostic:
       Offer one bounded correction attempt with the exact diagnostic:
       > *"You cannot finish this stage yet. The language service detected 1 error in `ui.js`: Line 42: `renderTasks` is not defined. Fix this error in `ui.js` now before returning."*
     - If the check is unavailable, inconclusive, or still failing after the bounded attempt, report that result and continue through the existing CI and defect process. Do not claim this gate prevents all syntax or runtime defects.
  3. **Formatting**:
     - Run a formatter only when the selected stack pack or project config explicitly identifies it. Avoid silently reformatting files during a write operation.

---

### Pillar 7: Safely Extending Co-Defect Remediation
- **Target Module**: `src/app/graph/workflow.py`
- **Objective**: Measure and improve remediation batching without combining unrelated defects or weakening per-defect verification.
- **Current implementation boundary**:
  - Co-defects are already bundled when they share an owner and the same regression-test requirement. Other open defects still advance through the cursor separately, preserving their individual verification and resume behavior.
  - Broadly grouping all defects by role could combine unrelated or conflicting changes and make it unclear which regression test closes which defect.
- **Implementation**:
  - First measure the existing co-defect batching on comparable runs.
  - Consider widening a batch only when defects have demonstrably shared causes, non-conflicting file ownership, and explicit per-defect regression coverage.
  - Preserve each defect's open/fixed state and evidence independently; rerun the required checks after the batch, and leave any unverified defect open.
- **Impact**: A hypothesis to measure, not a guaranteed stage-count or time reduction.

---

## 4. Runtime Estimates: Hypotheses to Validate

The following table is a planning hypothesis for a 16-criteria `web-todo` run, not a measured result. The phase ranges overlap in cause: for example, suite checks, timeouts, in-stage diagnostics, and remediation batching can all affect the same failure cycle.

| Pipeline Phase | Current Harness Duration | High-Steering Harness Duration | Key Mechanism Enabling Speedup |
|---|---|---|---|
| **Intake & Architecture** | 8–12 mins | 4–6 mins | Fast-path scoping; verified stack pack scaffolds |
| **Acceptance Authoring & Review** | 45–60 mins (historical estimate) | 8–10 mins (target hypothesis) | Stack-aware checks and tested helpers; runtime disputes may still occur |
| **Sprint 1 Development** | 20–35 mins (historical estimate) | 8–12 mins (target hypothesis) | Bounded work-order context and guarded edits; measure re-reads |
| **Sprint 1 CI & Defect Fixes** | 25–40 mins (historical estimate) | 5–8 mins (target hypothesis) | Earlier diagnostics and verified co-defect batching |
| **Sprint 2 Development & Fixes** | 30–50 mins (historical estimate) | 5–8 mins (target hypothesis) | Existing scope caps and measured remediation; sprint count depends on scope |
| **Milestone Review & Release** | 8–12 mins | 3–5 mins | Pack-generated release and CI workflows |
| **Total Wall-Clock Time** | **136–209 mins** | **33–49 mins** | **Planning ranges only; do not claim a saving until measured** |

The totals above are the arithmetic sums of the phase ranges. They imply a gross difference of 87–176 minutes only if phases are independent and comparable, which has not been demonstrated. Validate performance on the same brief, model, endpoint, execution mode, and acceptance criteria; report wall-clock time alongside benchmark score, test outcomes, model/tool calls, and intervention count. Compare multiple runs rather than selecting the fastest run, and reject an optimization that reduces time by lowering product quality or weakening a gate.

---

## 5. Prioritized Implementation Roadmap

| Milestone | Deliverables | Target Modules | Current status / next evidence |
|---|---|---|---|---|
| **M1: Close the pre-lock suite-check gap** | Add narrow, stack-aware checks for proven static failure patterns; retain runtime dispute handling | `src/app/acceptance/suite.py`, `src/app/stacks/` | Partial checks exist. Add only checks with a regression test and a clear false-positive policy. |
| **M2: Validate in-stage diagnostics** | Compare changed-file diagnostics to a baseline; allow at most one bounded correction attempt | `src/app/analysis/language_service.py`, `src/app/agents/specialists.py` | Language-service checks already run at the CI gate. Measure whether earlier feedback shortens recovery without blocking valid work. |
| **M3: Verify co-defect batching** | Preserve owner and regression-test boundaries; independently close only verified defects | `src/app/graph/workflow.py` | Co-defect batching already exists for matching owners and regression-test requirements. Measure it before broadening. |
| **M4: Measure edit and timeout failures** | Use existing guarded edit tools; tune test limits from observed timings | `src/app/tools/repository.py`, `src/app/stacks/` | Edit guards and line replacement exist. Measure current errors and slow-test distributions before adding path resolution or lowering limits. |
| **M5: Test bounded work-order context** | Supply relevant paths, signatures, or small excerpts within a prompt budget | `src/app/analysis/work_orders.py`, `src/app/agents/` | Defer full-file inlining until an experiment shows fewer repeated reads without worse quality or prompt growth. |
| **M6: Evaluate verified stack-pack lessons** | Produce candidate lessons offline; add only reviewed, regression-tested, allowlisted records | `src/app/stacks/` | Deferred until provenance, review, injection safety, versioning, and rollback are implemented. |
| **M7: Evaluate lean-scope workflow changes** | Test stage reduction while preserving acceptance, review, release, and user-approval gates | `src/app/graph/workflow.py`, `src/app/agents/scrum_master.py` | Scope-based sprint caps already exist. Do not infer that criteria count alone justifies bypassing architecture or QA gates. |
| **M8: Specify model-tier behavior** | Document explicit, non-mutating steering differences and their evaluation criteria | `src/app/models/`, `src/app/graph/workflow.py` | This item lacks a detailed design here. Never switch or modify the owner's model, endpoint, or settings automatically. |

---

## 6. Verification & Safety Invariants

1. **Owner Features Preserved**: Dynamic agent instructions, parallel/linear toggles, sprint summaries, and decision records remain untouched.
2. **Deterministic Rules Only**: Stack-specific guidance lives strictly in stack packs (`src/app/stacks/`); core harness graph logic remains framework- and product-agnostic.
3. **No Unstructured Memory Drift**: All self-learning data is validated against a strict schema and verified against run evidence.
4. **Test-First Verification**: Every change to harness logic or tools must include a regression test proven to fail on the old code before deployment.
5. **Quality-Preserving Measurement**: Record the same quality and cost measures before and after an optimization. Runtime improvement alone is not success if acceptance coverage, benchmark score, regression protection, or required reviews decline.
6. **Bounded Recovery**: Give retries and in-stage correction attempts explicit limits and actionable failure outputs; inconclusive checks must not look like successful validation.
