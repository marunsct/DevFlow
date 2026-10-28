# Harness Improvement Plan: High-Quality Product Delivery with Local & MoE Models

> **Unified plan (consolidated 2026-10-19).** This file is the only improvement plan.
> - It carries the original plan (§1–4, Initiatives A–I) and Appendices 1–8
>   (Initiatives J–BL, EF, CM, OS, RL, PH, CG and Appendix 7's MF, RC, IN, BW, PN, OP, CH, EV, SF and Appendix 8's SL, RV, EN, MT, SAP, DT, RD, with the UI parts).
> - **Before implementing: Part 21** is the single implementation order and
>   **Part 22** resolves the contradictions and lists what not to implement.
> - Section E holds the two earlier plan documents, merged here.
> - **Appendix M** at the end indexes every improvement: a short description,
>   its current status and a link to the section that explains it (the
>   reasons and the evidence).
> - Per-item status is kept in the Implementation Progress Ledger tables.
>   Change a ledger row and its Appendix M row in the same commit.
> - Evidence: `docs/review-findings.md`. Research: `docs/research-findings.md`.
>   Decisions: `docs/architecture-decisions.md`.


**Target Architecture:** LangGraph / Deep Agents Benchmark Harness  
**Current Benchmark:** Low Brief (`tests/brief_low.md`) across Fast Mode (`DELIVERY=fast`) & Thorough Mode (`DELIVERY=thorough`)  
**Active Model:** `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` (Local MoE via port 8888, `FRONTIER=false`)  
**Date:** 2026-10-17  

---

## 1. Executive Summary & Objective

The objective of this plan is to **systematically elevate the quality, visual polish, and engineering reliability of generated software products when running on local, quantized, and Mixture-of-Experts (MoE) models**.

Recent benchmark runs have established two critical baselines:
1. **Model Capability vs. Quality**: Large cloud/frontier models (e.g., `openai/gpt-oss-20b` in `run-5aadbddd`) completed in ~80 minutes with high natural semantic reasoning, but wrote plain inline CSS without modern modular structure. Smaller local models (such as `qwen3.8-flash-next-coder-iq1_m` in `run-866e972e` and `run-7bcdda40`) achieved cleaner separation of concerns (`styles.css`, responsive CSS variables, 24/24 unit test passing, 100% acceptance criteria), but faced higher token generation latency and required tight guardrails against runaway tool loops.
2. **Hidden Test Benchmark Gap**: `run-866e972e` achieved a 100% pass rate on all criteria defined in `tests/brief_low.md`, yet scored 5/10 on the hidden `web-todo` benchmark due to implicit UI expectations (checkbox `getByLabel('Done')`, filter buttons vs. select dropdown) that were present in `benchmarks/web-todo/brief.md` but omitted in `brief_low.md`.

By upgrading the harness to supply **deterministic design systems, procedural visual audits, strict contract extraction, and narrow specialist scopes**, lower and MoE models can consistently produce production-grade applications that match or exceed frontier model outputs.

---

## 2. Core Failure Modes on Smaller & MoE Models

To design effective technology-agnostic fixes, we categorize the observed failure modes of lower models:

```mermaid
flowchart TD
    subgraph Model Limitations
        A[Attention Drift on Multi-File Tasks] --> D[Hallucinated Tools or Mixed Concerns]
        B[Spatial / Visual Blindness] --> E[Broken Layouts, Missing Contrast, Overflow]
        C[Context Bloat & Token Degradation] --> F[Slow Prompt Eval & Repeated Answers]
    end
    subgraph Harness Solutions
        D --> G[Narrow Single-File Work Orders]
        E --> H[Procedural Visual & Axe-Core Audits]
        F --> I[Lenient Parser & Tool Withholding]
    end
```

1. **Spatial Blindness**: Language models cannot perceive CSS rendering directly; they frequently produce overlapping flex items, missing focus states, and horizontal scrollbars unless given machine-verifiable layout metrics.
2. **Contract Under-Specification**: When a brief leaves UI controls implicit (e.g. "filter by status"), smaller models select accessible HTML defaults (e.g. `<select>`), which diverge from strict acceptance suites expecting `<button>` elements.
3. **Runaway Unoffered Tool Loops**: Read-only agents often attempt file modifications with varying arguments when frustrated by missing code context.
4. **Syntax & Method Deprecations**: Smaller models frequently interchange assertions (e.g., Node.js `assert.doesNotMatch` vs Chai `assert.notMatch`), burning model calls on syntax fixes.

---

---

## 3. Technology-Agnostic Harness Improvement Initiatives

<a id="plan-a"></a>
### Initiative A: Procedural Design System & Token Seeding (`stacks/packs` & `seed.py`)
- **Reasoning**: Smaller and MoE models suffer from spatial blindness and attention drift; when required to invent CSS styles and design systems from an empty file, they default to primitive browser styling, low color contrast, or unstyled tables. Seeding deterministic design variables ensures instant visual polish without consuming model reasoning tokens.
- **Empirical Evidence**:
  - `run-5aadbddd-7e10-4790-8611-6f3289b015f2`: Early frontier run wrote plain HTML with minimal inline styles, producing an unstyled, raw look.
  - `run-3642baf8-34f7-492d-8667-b64a897b1fd7`: Initial drafted CSS chose a `--primary` color of `#007bff`, which failed the WCAG AA accessibility contrast check on white background (contrast ratio 3.97:1 < 4.5:1 required). This forced an extra defect fix round (`defect_fix_1_1`) to adjust to `#0069d9`.
  - `run-77c6650e-042a-4310-bf72-bb819a8f8fee`: Similarly generated `#007bff` and spent `defect_fix_1_1` fixing color contrast.
- **Harness Mechanism**:
  - In `src/app/stacks/packs/_javascript.py` and `src/app/plugins/seed.py`, embed high-quality baseline CSS custom properties and resets in the project scaffold:
    ```css
    :root {
      --font-sans: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
      --color-bg: #f8fafc;
      --color-surface: #ffffff;
      --color-text: #0f172a;
      --color-text-muted: #64748b;
      --color-primary: #0069d9;
      --color-primary-hover: #0056b3;
      --color-border: #e2e8f0;
      --radius: 0.5rem;
      --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
      --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
    }
    ```
  - Pre-configure accessible focus indicators (`:focus-visible`) and WCAG-compliant contrast pairings.
- **Impact**: Specialists immediately write modern, beautiful, and accessible layouts without burning model cycles or defect rounds on visual primitives.

<a id="plan-b"></a>
### Initiative B: Procedural Visual & Layout Audits (`page_view.py`)
- **Reasoning**: LLMs cannot perceive 2D rendered screens; they only see code text. Without computed layout feedback, models cannot detect when buttons overlap, flex elements wrap undesirably, or mobile viewports trigger horizontal scrolling.
- **Empirical Evidence**:
  - `run-3642baf8-34f7-492d-8667-b64a897b1fd7`: Action buttons (`Edit`, `Delete`) initially caused layout wrapping and overflow on mobile viewports until Playwright checked responsiveness in AC-16.
  - `run-94d2c449-fd88-45dd-91a2-0b9a1a166bb6`: Spent model calls iteratively adjusting CSS padding without knowing exact rendered element bounding boxes.
- **Harness Mechanism**:
  - Automatically invoke `look_at_page` following UI specialist file modifications.
  - Compute layout boundaries via Playwright:
    - Check if `document.documentElement.scrollWidth > window.innerWidth` (flags mobile horizontal overflow).
    - Detect whether clickable targets are smaller than 44x44px.
    - Check for missing `aria-label` or `<label>` associations.
  - Return these computed diagnostics directly into the model's next turn prompt as a feedback notice.
- **Impact**: Eliminates visual trial-and-error by providing instant, machine-verifiable layout feedback.

<a id="plan-c"></a>
### Initiative C: Contract-Strict Interface Extraction in Specification
- **Reasoning**: When a user brief specifies behavior without exact UI element contracts (e.g. "filter by status"), smaller models pick reasonable semantic elements (e.g. `<select>`), whereas hidden acceptance suites expect `<button>` elements or specific `getByLabel` selectors. Extracting a formal DOM contract during architecture aligns implementation and acceptance suites perfectly.
- **Empirical Evidence**:
  - `run-866e972e-c533-4029-9e79-f6211be86dfc`: Scored 5/10 on the hidden `web-todo` benchmark because `tests/brief_low.md` omitted control element types, causing the agent to select `<select>` instead of `<button>` filters.
  - `run-3642baf8-34f7-492d-8667-b64a897b1fd7` & `run-94d2c449-fd88-45dd-91a2-0b9a1a166bb6`: Both scored 1/10 (0.1) on the hidden benchmark due to missing `<label>Title</label>` markup expected by the hidden test suite.
  - `run-77c6650e-042a-4310-bf72-bb819a8f8fee`: Scored **10/10 (1.0 / 100%)** as soon as the explicit `## Interface` contract from `benchmarks/web-todo/brief.md` was provided, proving contract extraction is the single differentiator between 1/10 and 10/10.
- **Harness Mechanism**:
  - In `src/app/agents/principal_architect.py`, ensure `TechnicalSpecificationOutput` requires an explicit `ui_contract` listing every interactive element:
    - Target element tag (e.g. `button`, `input[type="checkbox"]`, `select`).
    - Exact accessible label (`aria-label`, `<label>`, or inner text).
    - Expected ID or data attribute.
- **Impact**: Guarantees that implementation specialists and QA acceptance authors share identical DOM contracts, ensuring 10/10 benchmark scores even on underspecified briefs.

<a id="plan-d"></a>
### Initiative D: Pre-Execution Linter and Assertion Normalizer Gate
- **Reasoning**: Smaller and MoE models frequently mix up assertions across frameworks (e.g., `assert.notMatch` from Chai vs `assert.doesNotMatch` in Node.js `node:test`) or commit minor syntax errors during edits. Catching these via AST before running full test rounds saves container startup overhead.
- **Empirical Evidence**:
  - `run-77c6650e-042a-4310-bf72-bb819a8f8fee`: In `acceptance_author_1`, `edit_artifact` failed with `"Node cannot parse this file on line N: SyntaxError: Identifier 'X' has already been declared"`, requiring a retry turn.
  - `run-77c6650e-042a-4310-bf72-bb819a8f8fee`: In `test_round_1`, the test runner failed with `"describe() in a file that is imported by the configuration file"`, triggering an unnecessary defect round (`defect_fix_2_17`).
- **Harness Mechanism**:
  - In `src/app/tools/sandbox.py`, run a fast AST/linter check on modified test files.
  - Automatically detect and correct deprecated or mismatched assertion calls (e.g., mapping `assert.notMatch` $\to$ `assert.doesNotMatch` in `node:test`).
  - Provide instant error feedback when invalid syntax is detected without waiting for container runner timeouts.
- **Impact**: Prevents wasted test rounds caused purely by framework-assertion syntax mismatches.

<a id="plan-e"></a>
### Initiative E: Narrow, Single-File Work Orders
- **Reasoning**: Smaller models experience rapid attention degradation when asked to implement or edit multiple disparate files in a single prompt turn, leading to hallucinations, partial writes, or overwritten progress. Restricting work orders to single files maintains high code quality.
- **Empirical Evidence**:
  - `run-c2e62179-8b2b-4229-974a-25916a241b99` (notes-api-hono): Took 13.3 hours and generated 2.84M output tokens when agents attempted multi-file modifications per work order across sprints.
  - `run-94d2c449-fd88-45dd-91a2-0b9a1a166bb6`: Took 136 minutes in Thorough Mode (30 minutes in the build phase alone) as `specialist_ui_ux` edited HTML and JS together across multiple turns.
  - `run-77c6650e-042a-4310-bf72-bb819a8f8fee`: Fast Mode direct drafting separated drafting and completed the build phase in only **3 minutes** (saving 27 minutes of wall-clock time).
- **Harness Mechanism**:
  - In `src/app/graph/planned_work.py` and `technical_lead.py`, enforce that a single work order modifies at most one core product file (`app.js`, `index.html`, or `styles.css`) and its paired test.
  - Keep prompt sizes under 4,000 tokens during specialist execution.
- **Impact**: Drastically reduces build-stage duration from 30 minutes to 3 minutes while eliminating cross-file regression errors.

<a id="plan-f"></a>
### Initiative F: Root-Crash & Load-Error Pre-Check Gate (Prevent Defect Sprawl)
- **Reasoning**: When an application has a fatal initialization or script loading error, every single acceptance criterion that touches the UI fails simultaneously. Queueing a separate defect for every individual acceptance test creates massive defect sprawl and redundant fixer executions for what is fundamentally a single root bug.
- **Empirical Evidence**:
  - `run-77c6650e-042a-4310-bf72-bb819a8f8fee`: When `index.html` failed to initialize cleanly on startup, **15 acceptance criteria failed simultaneously** with the message *"The product reports errors by itself while it loads, before any test touches it"*. The harness queued 17 defects (`defect_fix_1_0` through `defect_fix_1_16`). Once `defect_fix_1_2` fixed the root script load error, defects `1_3` through `1_16` were immediately closed without fixers as *"passing since"*.
- **Harness Mechanism**:
  - In `src/app/acceptance/suite.py` and defect queue generation, detect if the application fails to boot, import scripts, or load the DOM cleanly (*"The product reports errors by itself while it loads"*).
  - Treat this root load error as a blocking prerequisite defect. Defer queueing downstream element selector defects (e.g., button, filter, checkbox checks) until the application initializes cleanly.
- **Impact**: Prevents cascading defect sprawl, saving 10–14 redundant fixer invocations and ~20 minutes of wall-clock time per sprint.

<a id="plan-g"></a>
### Initiative G: Lenient Whitespace and Unicode Normalization in `edit_artifact`
- **Reasoning**: Exact substring matching in `edit_artifact` requires identical whitespace and byte-for-byte character equality. Smaller and MoE models frequently emit minor variations in indentation, trailing spaces, or Unicode comment characters (`─` vs `-`), causing avoidable tool failures and retry loops.
- **Empirical Evidence**:
  - `run-77c6650e-042a-4310-bf72-bb819a8f8fee`: In `specialist_testing_1`, the agent failed 2 consecutive tool calls with:
    `{"find": "// ── index.html error handling ────────", "error": "Could not find that text in 'X'. It must match exactly, including whitespace and line breaks"}`.
    Both retries burned ~3,000 output tokens solely due to whitespace/unicode dash differences between generated comments and file contents on disk.
- **Harness Mechanism**:
  - In `src/app/tools/artifacts.py` (`edit_artifact`), when an exact literal string match fails, attempt a **normalized fallback match**:
    - Trim trailing whitespace per line.
    - Normalize Unicode dashes (`─`, `—`, `-`) and curly quotes.
    - Check if a unique normalized block match exists.
  - If a single unambiguous match is found, apply the replacement cleanly.
- **Impact**: Eliminates recurring tool retries in testing specialists and acceptance authoring, saving 2–3 turns per editing stage.

<a id="plan-h"></a>
### Initiative H: Pre-Flight State Verification Before Defect Fixer Dispatch
- **Reasoning**: When multiple defects are logged in a test round, a fix applied by an earlier fixer stage often inadvertently or intentionally resolves defects queued for later stages. If the harness dispatches those subsequent fixers without re-checking the filesystem, the fixer burns model calls inspecting code that is already correct.
- **Empirical Evidence**:
  - `run-77c6650e-042a-4310-bf72-bb819a8f8fee`: `defect_fix_2_17` was invoked to rename `e2e.test.mjs` to `e2e.spec.mjs`. Upon execution, the model logged:
    *"The rename from e2e.test.mjs to e2e.spec.mjs was already applied by a prior stage — confirmed present on disk when this stage started."*
    The node executed 12 model calls just to verify what was already on disk.
- **Harness Mechanism**:
  - In `src/app/graph/engineering.py`, before launching a defect fixer node, execute a lightweight pre-flight check (file existence, AST check, or targeted test rerun).
  - If the requested change is already present, immediately close the defect and advance without launching the model node.
- **Impact**: Saves 10–12 model calls and 3–5 minutes per sprint by bypassing already-resolved defect tickets.

<a id="plan-i"></a>
### Initiative I: Reasoning Token Budget Governor for Synthesis & Planning Roles
- **Reasoning**: When thinking/reasoning is enabled on MoE models, planning stages with broad system instructions can spend their entire output token budget producing verbose internal reasoning chains, leaving 0 tokens remaining to emit the required structured output or tool call.
- **Empirical Evidence**:
  - `run-77c6650e-042a-4310-bf72-bb819a8f8fee`: `technical_lead` spent an entire reply's output budget on reasoning (0 tool calls emitted), triggering the warning:
    `Stage technical_lead spent a whole reply's output budget on reasoning; thinking switched off for the next reply, tools kept`.
  - `run-bf43c7e2-449d-4654-abfa-a7b5d5a683fd`: `principal_architect` similarly exhausted its entire reply budget on reasoning (0 tool calls emitted):
    `Stage principal_architect spent a whole reply's output budget on reasoning; thinking switched off for the next reply, tools kept`.
    Each instance wasted a complete 4,096-token forward pass without advancing tool state.
- **Harness Mechanism**:
  - In `src/app/agents/context_budget.py` and model request parameterization, set a bounded `max_thinking_tokens` (e.g., 2,048 tokens) for stages that require tool invocation (`principal_architect`, `technical_lead`).
- **Impact**: Guarantees the model retains sufficient output budget to emit tool calls in its initial turn, avoiding the zero-call reasoning exhaustion and saving a full 4,096-token cycle per planning stage.

---

## 4. Execution & Benchmark Verification Roadmap

```mermaid
flowchart TD
    subgraph Step 1: Low Brief (Web To-Do)
        L1[Fast Mode run-77c6650e: 10/10 Score, 82m] --> L_DONE[Low Brief Complete]
        L2[Thorough Mode run-94d2c449: 100% Acceptance, 136m] --> L_DONE
    end
    subgraph Step 2: Medium Brief (Task Management Dashboard)
        L_DONE --> M1[Fast Mode run-bf43c7e2: Running]
        M1 --> M2[Thorough Mode: Scheduled]
        M2 --> M_DONE[Medium Brief Complete]
    end
    subgraph Step 3: Hard Brief (Enterprise E-Commerce)
        M_DONE --> H1[Fast Mode: Scheduled]
        H1 --> H2[Thorough Mode: Scheduled]
        H2 --> H_DONE[Hard Brief Complete]
    end
```

### Phase 1: Low Brief Verification (`tests/brief_low.md` & `benchmarks/web-todo/brief.md`) - **COMPLETED**
- **Fast Run (`run-77c6650e`)**: Completed at 00:52 JST in 82 min. 15/15 acceptance tests passed. 38/38 unit tests passed. **Hidden Benchmark Score: 10/10 (1.0 / 100%)**.
- **Thorough Run (`run-94d2c449`)**: Completed at 17:08 JST in 136 min. 9/9 acceptance tests passed. 76/76 unit tests passed. Verified multi-sprint collaboration and release.

### Phase 2: Medium Brief Verification (`tests/brief_medium.md`) - **ACTIVE**
- **Brief Scope**: Task Management Dashboard with JWT authentication, PostgreSQL, RESTful API, team assignments, priorities, categories, and analytics.
- **Fast Run (`run-bf43c7e2`)**: **Currently Running** (started 00:54 JST). Auditing Python/FastAPI/React stack setup, acceptance authoring, direct drafting, and test rounds.
- **Thorough Run**: To be launched immediately following successful completion and audit of Fast Run.

### Phase 3: Hard Brief Verification (`tests/brief_high.md`) - **QUEUED**
- **Brief Scope**: Enterprise E-Commerce Platform with microservices, multi-vendor support, OAuth2/2FA, payment gateways, Redis caching, real-time inventory, and analytics.
- To be executed sequentially across Fast Mode and Thorough Mode following successful completion of Phase 2.


---

<a id="plan-appendix-1"></a>
## Appendix (2026-10-18): Deep Review — Release Integrity, Local-Model Quality, Throughput, UI/UX

> **Implementation status** of every item below is tracked in the
> [Implementation Progress Ledger](#implementation-progress-ledger) at the end
> of this document. The ledger is updated in the same commit as every
> implementation change; a DONE row carries its commit hash.

**Method and evidence base.** This appendix follows a full review of the harness
(core modules read end-to-end; 255 worker transcripts and 9 analyzed in depth;
postgres run/bench data; the live medium-brief run `run-bf43c7e2` observed from
00:54 JST 2026-10-18 through its fix treadmill; three web-research passes on
frontier agent harnesses, local-model serving, and agent-product UI/UX, all
source-verified on 2026-10-17/18). Working notes and both research reports were
kept in `docs/review-findings.md`; the frontier-harness report in full is at
`.langchain/research/frontier-harness-report.md`. Every item below carries its
reasoning and evidence, per the review mandate. All mechanisms are language-,
framework- and product-agnostic at the harness level; anything stack-specific
belongs in `src/app/plugins/seed.py` or a stack pack, per AGENTS.md.

**What the frontier research confirmed.** Claude Code, Codex, Gemini CLI, Jules,
OpenHands, Devin, Amp, Cursor, Cline and the SWE-agent family have converged on
one architecture: harness-managed context budgets with early structured
compaction, minimal bash-centric tool sets with ACI guardrails, plan/todo
artifacts on disk, read-only subagents around a single writer per workstream,
deterministic verification gates that block "done", and role-pinned model
routing. For a 20–40B local MoE this consensus matters *more*, not less — each
mechanism substitutes harness engineering for model capability, and the
benchmark record shows the substitution works (mini-swe-agent's bash-only loop
passes >74% of SWE-bench Verified with a frontier model and runs "literally any
model"; Qwen3-Coder-30B-A3B reaches 60.4% SWE-bench Verified at ~19 GB Q4;
METR finds reliability, not raw reasoning, drives long-task completion —
arXiv:2503.14499). This harness already implements much of the consensus
(verification gates, sandbox, work orders, digests, two-tier models); the
initiatives below extend it where the live evidence and the research agree
there is a gap, and each carries its frontier validation inline.

**Correction to the Phase 1 record above.** The Thorough Run entry for
`run-94d2c449` reads "9/9 acceptance tests passed. 76/76 unit tests passed.
Verified multi-sprint collaboration and release." The bench scorer marked the
same run `false_acceptance: true` with a hidden-test score of **1/10**: the
locked suite was green because five of its failing tests had been reclassified
as "not product defects" after the suite's repair budget was spent
(`Locked tests of AC-1, AC-2, AC-3, AC-5 cannot pass and the suite's repairs are
spent; their failures are not product defects`, ×5 between 06:55–08:05 UTC on
2026-10-17), and the run was then released. This is the concrete instance of
the pattern in `docs/monitoring-handover.md` §5.2 ("every run in this harness's
history that shipped something broken shipped it with a green suite") and the
reason Initiative J below is ranked first.

---

<a id="plan-part-1"></a>
### Part 1 — Systemic gaps: environment, release integrity, and the fix treadmill (P0)

<a id="plan-j"></a>
#### Initiative J: Release-integrity gate — a green suite must be a *verifiably* green suite
- **Reasoning**: The release path trusts one artifact: the locked acceptance
  suite. Three mechanisms can make that suite green while the product is
  broken, and all three have now been observed in production runs: (a) dispute
  repairs reclassify failing locked tests as test bugs once the repair budget
  is spent (`graph/escalation.py` + the dispute engine; the QA-lead opinion is
  taken without an executable counter-check); (b) a runner that executes zero
  tests still exits 0 ("vacuous green"); (c) the suite can be pointed at the
  wrong entrypoint entirely (see Initiative K — the live run's acceptance
  server served a scaffold stub while the real application lived in a
  subdirectory nobody imported). 7 of 33 scored bench runs carry
  `false_acceptance: true`, including two 1/10 releases on 2026-10-17.
  Escalation already refuses to ship when *more than half* the criteria would
  be deferred (`escalation.py`: `after * 2 > len(criteria)` → stop), which is
  the right shape; the hole is that "passing" can be manufactured before that
  arithmetic runs.
- **Empirical evidence**:
  - `run-94d2c449` (thorough, frontier judgement): repairs spent → 5 locked
    tests reclassified → released → hidden score 1/10.
  - `run-3642baf8`: `The unit smoke test did not pass through node --test
    tests/**/*.test.js (exit 0, 0 passed, 0 failed)` — a runner that matched no
    files exits 0; the setup proof caught it but the run continued "left to the
    agents" and released at hidden 1/10.
  - `run-866e972e`: released with the same defect `raised → left open` twice on
    the ledger; hidden score 5/10.
  - `run-bf43c7e2` (live, medium brief): acceptance server ran the pack stub
    (`main.py` health+static) while the drafted application sat unimported in
    `backend/`; 31 of 35 locked tests failed against the stub — the suite was
    honest here only by luck of the stub failing loudly. Had the stub served
    the SPA shell without error, the same wiring gap could have produced a
    vacuous green instead.
- **Harness mechanism** (all pack-contract-level, no stack specifics in core):
  1. **Vacuous-green hard gate**: at every suite run that gates progress
     (lock, test rounds, CI, release), require the parsed report to show
     executed tests ≥ the locked test count, and every locked criterion to be
     covered by at least one executed test (`suite.tests_the_runner_never_ran`
     already computes written-vs-ran; extend it to locked-vs-ran and wire it
     into `AcceptanceResult.ran`). A count mismatch is a failed run, not a
     warning.
  2. **Reclassification budget + second opinion**: cap dispute-driven test
     reclassifications per run (e.g., ≤2 or ≤10% of locked tests). Each
     reclassification after repairs-are-spent must be confirmed by the
     judgement model AND backed by an executable probe: the harness re-runs
     the criterion's own locked smoke example (from `acceptance/requests.py`
     material) against the delivered surface. If the probe passes, the test
     was wrong; if it fails, the product is wrong and the test stays.
  3. **Release-time per-criterion probe**: independent of the suite, the
     release gate runs one harness-generated probe per non-deferred criterion
     (HTTP request / CLI invocation / page interaction, per the pack's
     declared surface) derived from the criterion text locked at authoring
     time. Probes are cheap (seconds, no model calls) and cannot be weakened
     by suite repairs because they are not the suite.
  4. **Honest completion states**: a run released with any deferred criteria,
     reclassified tests, demoted review findings, or unproven setup is
     recorded as `completed_with_gaps` (DB status + delivery panel + bench
     export), never plain `completed`. The loop's audit scripts then have a
     production-visible false-acceptance risk signal without hidden tests.
- **Frontier validation**: the same "block done until a check passes" shape is
  Claude Code's Stop hooks and `/goal` evaluator (a separate evaluator re-checks
  the success condition every turn), Devin's "make tasks easy to verify" +
  recorded proof, and Copilot's coding agent iterating against CI before
  offering the PR. No frontier product lets the worker rewrite its own
  acceptance checks without an independent verifier — J.2/J.3 add exactly that
  separation here (https://code.claude.com/docs/en/best-practices,
  https://docs.devin.ai/get-started/devin-intro).
- **Impact**: Directly targets the 7/33 false-acceptance rate — the single
  worst quality outcome for a product whose promise is "measured, not vibes".
  Items 1 and 4 are days of work; 2 and 3 are a week-scale.
- **Effort**: M (1: S, 4: S, 2: M, 3: M). Sequencing: 1+4 first, then 3, then 2.
- **Antigravity Assessment on Initiative J**:
  > **Strongly Endorsed (P0)**: The vacuous-green gate (J.1) and honest completion state `completed_with_gaps` (J.4) are critical and should be implemented immediately.
  > **Caution on J.3 (Release-time per-criterion probe)**: Probes derived purely from natural-language criterion text without referring to the architect's formal API/DOM contract risk false-negative rejections (e.g. probing `/api/tasks` when the architect specified `/api/v1/tasks`). Probes MUST be compiled from the formal `ui_contract` and API specification rather than raw ungrounded brief text.

<a id="plan-k"></a>
#### Initiative K: Environment-truth contract — the architect, the acceptance author, and the sandbox must agree on what exists
- **Reasoning**: The harness tells the *stack selector* the truth about the
  execution environment — `describe_execution_environment()` in
  `agents/stack_selector.py` says nothing is running, no database server
  exists, and the design must be verifiable without a live one — but grep
  shows that function reaches **only** the selector. The architect, the
  acceptance author, and the pack scaffolder never see it. Result: a live-run
  specification that demanded asyncpg + a PostgreSQL server + startup
  migrations on a machine with no database (`pg_isready` connection refused in
  the sandbox), an acceptance suite written against services that cannot
  start, and a fullstack pack whose generated `main.py` stub was wired to the
  acceptance server while the real drafted application in `backend/` was never
  imported — 31/35 tests failed for a wiring gap no fixer could repair from
  inside its workspace view. Dependency reality drifted the same way: drafted
  imports not in `requirements.txt`, and a sandbox where bare `pip` installs
  into `.agent-home/.local`, invisible to the `.venv/bin/python` the
  acceptance server runs — one fixer burned 30+ calls on `pip install` /
  `pip list` loops without ever changing what the server could import.
- **Empirical evidence**: `run-bf43c7e2` (live, 2026-10-18): spec §database
  demands PostgreSQL; sandbox logs `pg_isready … Connection refused`; no
  `.env`/`DATABASE_URL` ever provisioned; `Draft of backend/models.py left to
  the agent loop: … positional argument follows keyword argument`;
  `defect_fix_1_2`: `pip install httpx>=0.27` ×5 in 20 s, `python3
  tmp-check-deps.py` ×6, `pip list` ×6; ci.json 31 failed / 4 passed against
  the stub entrypoint. Seed contradiction: `plugins/seed.py`'s `postgres` key
  encourages pooled Postgres though the sandbox provisions none, and its
  python key says "always use a virtual environment" while the sandbox's bare
  `pip` goes to the user site.
- **Harness mechanism**:
  1. **One environment contract, delivered to everyone**: move
     `describe_execution_environment()` to a shared module and inject it into
     the architect's, acceptance author's, and QA advisor's request context
     (same append-at-end, byte-stable block used by the workspace digest —
     cache-friendly). Specifications that require a service the environment
     does not provide must say how the product substitutes for it (embedded
     store, adapter + in-memory fake for tests), per the selector's existing
     rule.
  2. **Pack-contract `services:` (opt-in provisioning)**: extend the stack
     contract with a declarative services section (e.g., a database sidecar
     image + readiness probe + connection env var injected into the sandbox
     and the acceptance server). Fullstack packs that genuinely need a server
     get one; everything else keeps the no-services truth. This is the
     alternative to (1)'s adapter-substitution — recommend supporting both:
     provisioning where a pack declares it, enforced substitution elsewhere.
  3. **Entrypoint wiring proof**: the fullstack pack's setup proof must
     exercise the *generated application's* declared entrypoint (from the
     project record), not only the scaffold stub — a smoke request to a
     route only the real app serves. This is the pack-level version of J.3
     and would have caught F1 at scaffold time instead of at release.
  4. **Dependency-manifest drift gate**: after each build stage, a
     deterministic check reconciles first-party imports against the declared
     manifests (per-language import→manifest mapping already exists in
     `analysis/compiler_check.py` shape); missing entries are handed to the
     fixer as one bundled defect, not discovered by a model at 3 a.m.
  5. **Sandbox install coherence**: installs in the sandbox must land in the
     interpreter environment the acceptance server uses (same venv/manifest
     scope), or the seed instructions must match what the sandbox actually
     does. Fix the seed text either way — instructions contradicting the
     environment is the "instructing and then punishing" defect class
     (`docs/monitoring-handover.md` §6.2, 5 recorded instances).
- **Frontier validation**: cloud agents run each task in a fresh, *declared*
  environment and split networked setup from the offline agent phase (Codex
  Cloud environments); Jules documents "broken setup scripts" as a top failure
  cause and proves setup before starting (https://learn.chatgpt.com/docs/
  environments/cloud-environment, https://jules.google/docs/faq/). K.2/K.3 are
  the pack-level version: declare services, prove the wiring, then build.
- **Impact**: Removes the largest unfixable-defect class observed live
  (31/35 failures from one wiring gap; 13 defects from one root cause).
  Without this, medium/hard briefs on service-backed stacks will keep
  producing treadmills the fixers cannot exit — the live run burned its
  whole second half on exactly this.
- **Effort**: M–L. (1) S, (4) S–M, (5) S, (3) M, (2) L (Docker sidecar
  plumbing, per-pack data).
- **Antigravity Assessment on Initiative K**:
  > **Strongly Endorsed**: Delivering environment truth to architect/QA (K.1), entrypoint wiring proof (K.3), manifest drift detection (K.4), and venv coherence (K.5) will resolve the dominant failure mode observed in `run-bf43c7e2`.
  > **Caution on K.2 (Dynamic Docker Sidecar Provisioning)**: Provisioning live database/queue sidecars per run adds host resource contention (competing for RAM against local GPU inference), requires elevated Docker socket permissions, and risks dirty state across test rounds. We recommend prioritizing **in-process or embedded service adapters** (e.g. SQLite in PostgreSQL-compatibility mode, or a single persistent local test Postgres container with per-run isolated schema namespaces) rather than orchestrating dynamic multi-container sidecars per run.

<a id="plan-l"></a>
#### Initiative L: Fix-treadmill circuit breakers — clustering, granularity, dispatch-time truth, escalation
- **Reasoning**: When a real defect exists, the current loop can thrash:
  13 defects queued from one root cause (bundling exists for *identical*
  problems only); every regression reverts the **whole stage's** work via git
  reset (`engineering.after_a_fix` → `ci.revert_to(root, base)`), so a fix
  that broke 4 tests also destroys the other repairs in that stage; fixers
  are dispatched from a test-round measurement that is stale by dispatch time
  (16 "already fixed, closed without a fixer" events in one day, including 9
  fixer stages named and stood down in one run); the test-round model's
  structured report systematically omits failing criteria (up to 15 in one
  event), and the procedural backfill papers over it; identical tool calls
  repeat 3–38× per stage even after pointer-answers and withholding (the live
  run reached a repeated-read tally of 16 *while* its tools were being
  withheld one by one); and both reverted fixes in the live run came from the
  local build model, matching the bench pattern that the local model drafts
  fine but its *fixes and reviews* are the weak link (fast/local web-todo
  scores 0.1/0.1/0.5 in 3 of 4 attempts while frontier-judged notes-api
  scored 1.0).
- **Empirical evidence**: `run-bf43c7e2`: `Reverted defect_fix_1_1: it broke
  4 test(s) that passed before it` (16:55 UTC), `Reverted defect_fix_1_2` +
  `Reverted defect_fix_2_1` (17:07, 17:28), suite locked 16:26 → reopened
  17:08 (~42 min churn), `7 defects describe one problem; merged into one`
  (merge works, but only for identical descriptions), `did not report 13
  failing acceptance criteria; recording them as defects`, budget warnings
  ×47 in one day concentrated in defect_fix stages. `run-77c6650e`: 15 ACs
  omitted by the test-round report, 13 defects closed already-fixed.
- **Harness mechanism**:
  1. **Root-cause clustering before dispatch**: group defects by failing
     surface (file/route/component + first failing layer), not by identical
     description; dispatch one fixer per cluster with all member failures as
     evidence. Extends the existing merge and complements Initiative F's
     load-error pre-check to all common-root patterns (e.g., every API test
     failing behind one auth middleware).
  2. **File-granular revert**: snapshot the fixer's touched files (the ledger
     already records them) and revert only those on regression; keep the
     stage-level git revert as the fallback when the file set is unknown.
     Two consecutive whole-stage reverts destroyed unrelated good work twice
     in one run.
  3. **Re-measure at dispatch**: run the affected tests immediately before
     each fixer spawns (the harness already re-runs them *after*); close the
     defect on a green re-measure without a model call. This deletes the
     stale-queue class entirely (16 events/day).
  4. **Judgement-model escalation after revert**: a defect whose fix was
     reverted goes to the judgement model on the next attempt instead of
     waiting for the generic two-failure escalation — the revert *is* the
     proven failure signal, and the evidence says local-model fixing is the
     weak link. Cap at one escalation per defect to protect cost.
  5. **Hard stop on identical-call loops**: when the repeated-call tally
     crosses a small threshold (the middleware already counts), end the stage
     with a "no progress" outcome deterministically instead of spending the
     remaining budget on pointer-answer turns; route the defect per (4).
     Budget exhaustion warnings (×47/day) show the current soft landing still
     costs most of the stage's calls.
- **Frontier validation**: Claude Code's documented failure handling is "if you
  have corrected the agent more than twice, stop and restart" — the human
  version of L.5's deterministic stop; Gemini CLI ships dedicated loop
  detection (repeated-tool-call detection separate from compression);
  Magentic-One's orchestrator keeps task/progress ledgers and *re-plans* on
  error rather than retrying the same action; Codex pins stronger models and
  higher reasoning effort to reviewer/fixer subagents — L.4's routing
  (https://code.claude.com/docs/en/best-practices, https://arxiv.org/abs/
  2411.04468, https://learn.chatgpt.com/docs/agent-configuration/subagents.md).
- **Impact**: Converts the treadmill (observed: ~90 minutes of reverts,
  reopens and stale dispatches in the live run's second half) into bounded,
  evidence-driven repair. Also the biggest single call-count reducer: the
  defect_fix stages are where duplicate calls (17–47% run-wide) and budget
  exhaustion concentrate.
- **Effort**: M. (3) S, (5) S, (2) M, (1) M, (4) S (routing change).
- **Antigravity Assessment on Initiative L**:
  > **Strongly Endorsed**: Root-cause clustering (L.1), dispatch-time re-measurement (L.3), judgement-model escalation after revert (L.4), and hard stops on identical-call loops (L.5) address the exact runaway dynamics measured in `run-bf43c7e2`.
  > **Caution on L.2 (File-Granular Revert)**: Partial file reverts in multi-file fixes carry high risk of leaving the workspace in an unparseable or broken state (e.g. reverting `models.py` while keeping `routes.py` changes that depend on the reverted schema). File-granular revert MUST run an AST/import coherence check across all touched files before accepting the partial state; if cross-file syntax or import errors are introduced, it must fall back to the atomic stage snapshot.

---

<a id="plan-part-2"></a>
### Part 2 — Local-model output quality (complements Initiatives A–I; no duplication)

Research base: the full local-LLM serving/orchestration report (primary
sources verified 2026-10-17/18) is reproduced in `docs/review-findings.md`
§8; key citations inline below.

<a id="plan-m"></a>
#### Initiative M: Model-profile contract — per-family serving metadata, not per-run improvisation
- **Reasoning**: The harness has accreted ≥6 repair layers for malformed tool
  calls (unwrapped-args, list-it-held, offered-tool-meant, arg-fit name
  mapping, lowercase package retry, transcription repairs) because it treats
  every OpenAI-compatible endpoint the same. The research is unambiguous that
  tool-call reliability is mostly a *server configuration* property: vLLM
  needs the right `--tool-call-parser` per family (qwen3_xml/hermes/glm45/…)
  and offers `--tool-strict-level strict|allowed` to constrain names+args at
  decode time; llama-server needs `--jinja` and has native handlers only for
  specific families; Qwen needs Hermes-style templates and still documents
  malformed-call corner cases; gpt-oss only works in harmony format;
  DeepSeek-R1 distills effectively cannot function-call and need bash-style
  text loops; history hygiene differs per family (gpt-oss: strip prior
  reasoning; MiniMax-M2: never strip it). One hallucinated name (`edit_file`)
  burned 53 calls — 10.5% of a run's tool calls — answering "not a valid
  tool" every time, because the arg-fit mapper did not cover it.
- **Empirical evidence**: A3 counts (edit_file ×53, global_99 ×16,
  run_read_11=File ×11, tools named after file paths); A9 (lenient-JSON reads
  ×6/day; spec revisions blanking whole sections ×10/day); one-string argv
  (`'npm", "run", "build"],category:'`); research §8.1–8.2 (vLLM tool-calling
  + reasoning-outputs docs, llama.cpp function-calling docs, model cards).
- **Harness mechanism**: extend `server/model_profiles.py` into a declarative
  per-family contract the harness *verifies at probe time* (the fitness probe
  already runs): tool-call parser expectation, thinking switch + budget
  parameter names (`chat_template_kwargs.enable_thinking`,
  `reasoning_budget`/`thinking_token_budget`), reasoning-history policy
  (strip/keep), sampling presets (Qwen .7/.8/20/1.05 + presence_penalty for
  loops; GLM/MiniMax 1.0/.95/40), max-output guidance (Qwen3-Coder 65,536),
  and a tool-call smoke assertion (one forced trivial call must parse). On
  probe failure the run says *which server flag is likely missing* instead of
  discovering it over 53 error calls. Keep every client-side repair layer —
  they remain the last line of defense — but grow the arg-fit map into the
  profile (family-typical hallucinations like edit_file→edit_artifact are
  data, not code).
  Two refinements from the frontier research: (a) grammar-enforce the
  *control plane* — plan JSON, structured reports, review verdicts, the finish
  signal — but leave free-form coding turns unconstrained (vLLM's own docs:
  enforcement guarantees parsability, not quality, and aider measured a 10–15%
  quality cost when code itself is wrapped in schema-constrained JSON);
  (b) add a **bash-first degraded execution mode** for profiles whose
  tool-call compliance fails the probe: a mini-swe-agent-style loop where the
  model emits plain-text/YAML commands that the harness parses and executes
  *through the existing argv-only sandbox classifier* — no tool-calling API
  dependency, no shell granted to the model, linear append-only history.
  mini-swe-agent scores >74% SWE-bench Verified this way and runs "literally
  any model"; the caution is that scaffolding×model interactions dominate
  (Qwen2.5-Coder-32B collapses to 9.0% on the bash-only board), so the mode
  is profile-gated and bench-verified per model, never a global default
  (https://mini-swe-agent.com/latest/, https://www.swebench.com/verified.html).
- **Frontier validation**: Amp pins model + effort + prompt bundles per role
  ("The Dial") and keeps small "system models" for mechanical subtasks; Codex
  exposes per-subagent `model` and `model_reasoning_effort`; OpenHands ships
  both rule-based and classifier routers and an `LLM_DROP_PARAMS`-style
  compatibility layer — the model-profile contract is the established shape
  (https://ampcode.com/docs/the-dial, https://learn.chatgpt.com/docs/agent-
  configuration/subagents.md, https://docs.openhands.dev/openhands/usage/llms/
  local-llms).
- **Impact**: Removes the largest call-waste class attributable to format
  (A3+A9 ≈ dozens of calls/run) and makes new local models adoptable in
  minutes via profile data instead of weeks of repair-layer archaeology. The
  bash-first mode additionally unlocks model families (DeepSeek-R1 distills)
  that cannot function-call at all.
- **Effort**: M (profile schema + probe extension + map seeding); bash-first
  mode M and experimental (profile-gated).
- **Antigravity Assessment on Initiative M**:
  > **Strongly Endorsed**: Declarative model profiles with probe-time server capability verification and grammar-enforced control plane JSON are essential best practices for open-weight serving.
  > **Caution on Bash-First Degraded Mode**: We strongly concur with the author's caveat that Qwen-Coder models collapse on bash-only loops (9.0% on SWE-bench). In addition, parsing freeform terminal text introduces fragility and security sandbox classification ambiguities. Bash-first execution should be strictly restricted to models with zero native tool-calling ability (e.g. DeepSeek-R1 raw reasoning models) and should never be enabled for Qwen or Hermes model profiles.

<a id="plan-n"></a>
#### Initiative N: Reasoning-budget guardrails *before* the loss, not after (extends Initiative I)
- **Reasoning**: Initiative I correctly bounds thinking for planning roles
  via context_budget, but today's policy is still reactive at the call level:
  the model spends its **entire 20k-token output budget on reasoning**, the
  reply is discarded, and only *then* does the harness re-ask with thinking
  off. Each event costs two full generations; 40 events in a 14.5 h window ≈
  1.6 GPU-hours of discarded decode (~3 h with the re-asks). Both mainstream servers
  now expose the proactive control: llama-server takes `reasoning_budget` /
  `reasoning_effort` per request; vLLM takes `thinking_token_budget` +
  `--reasoning-config`. The harness already sends `reasoning_effort` via
  extra_body where supported (`agents/thinking.py`) — the missing piece is
  sending a hard *token* budget on thinking models and treating
  `finish_reason=length` with reasoning-only content as a budget signal
  (retry with budget raised modestly or thinking off — the current retry
  halves max_tokens, the wrong direction for this failure).
- **Empirical evidence**: A4/B3 counts (×20+×20 events in one day; 60+
  across 7 transcripts; 200k tokens discarded in `run-3642baf8` alone =
  10×20k exactly); research §8.1 (vLLM reasoning-outputs matrix),
  §8.5 (gpt-oss >20k CoT; R1 guidance); live run repeated the pattern at
  17:18–17:33 UTC inside a single fixer stage.
- **Harness mechanism**: (1) profile-declared thinking-budget parameter
  (Initiative M) sent on every thinking-on call, sized per role (planning
  roles keep a real budget; execution/tool-heavy roles get a small one or
  none — matching the existing ThinkingPolicy tiers); (2) on
  reasoning-only-length replies, retry with thinking off *and* the saved
  budget recorded per stage so repeat offenders in the same run start
  thinking-off (the per-visit switch already exists — make it per-stage
  sticky after N events); (3) never halve max_tokens on a length-finish that
  contains reasoning but no answer — that retry path assumes content, not
  exhaustion.
- **Frontier validation**: vLLM's own Qwen recipe lists `--reasoning-parser`
  as *mandatory* because "think-blocks eat the content budget" otherwise —
  the exact A4 failure, named as a server-config problem upstream; llama.cpp
  exposes `reasoning_effort`/`reasoning_budget` per request plus a realtime
  `reasoning_end` control endpoint; gpt-oss sets reasoning level by a literal
  system-prompt line (https://recipes.vllm.ai/Qwen/Qwen3.8-27B,
  https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).
- **Impact**: Recovers ~1.5–3 GPU-hours/day on the current workload and
  removes the dominant latency spike inside fixer stages (each event ≈3+
  minutes at observed decode speeds, twice).
- **Effort**: S–M (parameter plumbing + retry-path condition).

<a id="plan-o"></a>
#### Initiative O: Context diet and prefix-cache discipline — the harness is prefill-bound
- **Reasoning**: Measured across runs: input:output ≈ 31:1 (88.2M in / 2.8M
  out in one run; avg request 53–70k tokens), model wait is 85–93% of wall
  time, p50 latency grows 55 s → 75 s from <10k to 60–120k prompts, and
  cache hits are only 45–73% — so 2.4–15M tokens/run are re-prefilled from
  scratch. Research says effective context should be capped ~32–64k even on
  126k-window models (context rot measured on Qwen3-class models; RULER decay
  ~97@32k→82.5@256k; multi-turn instruction-following drops ~39% on average)
  and that KV-cache hit rate is "the most important metric" for production
  agents (Manus). Two harness-side leaks: (a) the shared spec block is
  front-loaded — `text_budget.excerpt()` cuts `text[:budget]`, so the
  judgement stages see the spec's head and the tail is dropped wholesale
  (a 241k-char scrum_master request ≈80k tokens; 203k for acceptance
  review), and section-aware selection would fit the *relevant* sections in
  half the bytes; (b) anything dynamic early in the prompt (timestamps,
  tool-list changes from withholding, digest reordering) invalidates the
  server-side prefix cache for everything after it — the digest's
  append-at-end placement is already correct and should become the stated
  rule for all injected context (Manus: mask-don't-remove tools; the
  harness's tool withholding changes the schema mid-stage, which both
  invalidates cache and confuses weaker models — prefer instruction-level
  withholding first, schema removal as the last resort).
- **Empirical evidence**: B1/B2/B4/B5 measurements (duplicate calls 17–47%
  of all tool calls ≈ 3–17M wasted prefill tokens/run; 395 pointer-answers
  to redundant reads in 8 runs; project_memory deployment grew average
  requests 44k→95k tokens); F8 (judgement-stage prompt sizes); F15 (excerpt
  front-loading; stale `DEFAULT_SPECIFICATION_BUDGET=150_000` with a wrong
  "15k tokens" docstring); research §8.4 (Chroma context rot incl. Qwen3-32B;
  lost-in-the-middle; aider 2k-window collapse 72.2%→51.9%).
- **Harness mechanism**:
  1. **Section-aware spec distribution**: reuse the digest/section machinery
     (`project_memory.digest_of` parses the same markdown structure) to send
     each stage the spec sections its role consumes (fixers: the criteria +
     contracts for the files they touch; UI specialist: the UI contract) +
     a whole-spec pointer artifact it can read on demand. Byte-stable
     rendering per (section, revision) so identical selections cache.
  2. **Effective-context ceiling for build calls**: derive from the profile,
     not only the window probe — cap routine build-stage requests at
     ~32–64k tokens of input (compaction thresholds already exist in
     ContextBudget; tighten the ceiling and keep must-follow constraints at
     the END of the assembled prompt per lost-in-the-middle).
  3. **Cache-stability rule + measurement**: declare the byte-stable prefix
     rule (static system + tools + spec block first; volatile state last).
     The measurement half is nearly free: transcript usage records already
     carry cached-token counts (this review measured 45–73% hits from them;
     no `src/app` code reads them), so surface cache-hit % as a first-class
     KPI in `scripts/loop/run_timing.py` (F18) and add a probe-time
     `timings.cache_n` read where the server API exposes it.
  4. **Compaction timing as a profile knob, A/B-verified**: `SOFT_TRIGGER_RATIO
     = 0.8` has a documented budget history behind it, so do not move it
     globally — declare usable-window and trigger ratio per model profile.
     Frontier products compact late (Claude ~95%, Codex at 95% effective,
     Anthropic's compaction API defaults to ≥150k tokens) because frontier
     models tolerate long context; the research for small models points the
     other way (trigger ~50–60% of the *usable* window; context rot measured
     on Qwen3-class models; OpenHands requires ≥22k usable and recommends
     32,768 for exactly this model class). Adopt two Claude Code details
     regardless of trigger point: write the compaction summary *for the LLM
     that resumes the task* (Codex's framing) and re-inject from disk after
     compacting (project memory, the active work order, and the N most
     recently modified files as paths + short excerpts — the summarization
     middleware already keeps AI/Tool pairs; the re-injection list is the
     addition). Offload oversized tool outputs to a file + preview instead of
     inlining them (Claude Code does this past 10k chars; LangChain ships
     `ClearToolUsesEdit` keep-last-3 as the same idea).
  5. Fix the stale budget constant/docstring (F15) while touching
     text_budget.
- **Frontier validation**: Claude Code budgets its startup context token by
  token (~4.2k system prompt, tool *names only* with schemas deferred, memory
  index capped at 25KB, skill bodies loaded on use) and re-reads at most the
  5 most-recently-modified files after compaction; aider sends a ~1k-token
  tree-sitter repo map instead of files; Manus calls KV-cache hit rate "the
  most important metric" for production agents and Cursor's router prices
  cache misses when switching models (https://code.claude.com/docs/en/
  context-window, https://aider.chat/docs/repomap.html, https://manus.im/
  blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus,
  https://cursor.com/blog/how-cursor-router-works). The harness's digest +
  snapshot machinery is the same idea; this initiative puts it on a measured
  budget like the frontier products do.
- **Impact**: At 45–73% cache hits and 31:1 asymmetry, a 30% input diet plus
  cache discipline plausibly cuts model-wait (85–93% of wall) by a third —
  hours per run — *and* improves quality (context rot is a quality effect,
  not just a speed effect). This is the core "performance without
  compromising quality" lever.
- **Effort**: M (1: M, 2: S–M, 3: S, 4: M, 5: S).
- **Antigravity Assessment on Initiative O**:
  > **Strongly Endorsed**: Section-aware spec distribution (O.1) and byte-stable cache prefix placement (O.3) are high-impact architectural wins that will directly cut prefill latency without information loss.
  > **Caution on O.4 (Compaction Trigger at 50–60% of Window)**: Lowering the compaction trigger to 50–60% on a 32k window triggers compaction every ~16k tokens, burning high output generation tokens on generating summaries repeatedly and dropping recent conversational context. We recommend keeping the trigger at `0.75–0.80` while using O.1 (section slicing) to prevent requests from ever bloating near the trigger threshold.

<a id="plan-p"></a>
#### Initiative P: Edit-tool reliability — demote `replace_lines`, escape the parser-refusal trap (reinforces Initiative G)
- **Reasoning**: `replace_lines` fails 40–68% of calls across five runs
  (68% worst) while `edit_artifact` fails 0–20% — the line-number interface
  is the wrong ACI for weak models (stale line numbers after every prior
  edit) and its safety check creates a trap: it refuses to edit a file the
  language cannot parse — but unparseable files are exactly what fixers are
  dispatched for. Initiative G's lenient matching helps `edit_artifact`;
  this item handles the other half: remove the worse tool from weak-model
  toolsets (or gate it behind a fresh-read requirement with server-side line
  validation), and give the parser-refusal case an explicit escape: when the
  target file does not parse, offer whole-file rewrite (the drafting path
  already does compile-and-repair re-drafts successfully — same mechanism,
  fixer context). Research alignment: aider recommends architect/editor
  splits and simpler edit formats precisely "with models that have trouble
  following edit format instructions"; SWE-agent's ACI paper is the canonical
  evidence that edit-interface design is a first-class capability lever.
- **Empirical evidence**: A2 counts (58/85, 50/79, 15/36, 25/62);
  parser-refusal quotes (`Refusing to change 'notes-api/src/store.ts':
  TypeScript cannot parse this file on line 116`); monitoring-handover §8.1
  (58.7% earlier, re-measurement requested — now done, unchanged); live run
  redraft loop (`backend/models.py … positional argument follows keyword
  argument` → 3 files re-drafted) proving whole-file regeneration works.
- **Harness mechanism**: (1) toolset policy per profile: weak-editor profiles
  get `edit_artifact` (with Initiative G leniency) and whole-file rewrite,
  not `replace_lines`; (2) when a file fails its language parse check, the
  fixer's request says so and offers the rewrite path explicitly; (3) keep
  line-anchored edits for strong profiles where they are measurably cheaper.
- **Frontier validation**: aider's edit-format leaderboard is the direct
  evidence — whole-file format compliance is ~100% at 32B-class models while
  diff-style formats sit near ~73%, and aider's remedy for weak editors is
  exactly this: default to the simpler format, feed the format error back,
  ask for a corrected copy once (https://aider.chat/docs/leaderboards/edit.
  html, https://aider.chat/docs/more/edit-formats.html). SWE-agent's ACI
  paper rejects syntactically invalid edits *at the tool boundary* with the
  error as feedback, windows reads to 100 lines, keeps search output terse,
  and returns an explicit "ran successfully, no output" message instead of
  empty strings — cheap micro-guardrails worth adopting in the sandbox's
  result formatting alongside this initiative (https://swe-agent.com/latest/
  background/aci/, https://arxiv.org/abs/2405.15793).
- **Impact**: 40–68% → 0–20% error rate on the most failure-prone tool;
  fewer burned calls in the stages that already exhaust their budgets.
- **Effort**: S–M.

<a id="plan-q"></a>
#### Initiative Q: Route the weak links to the judgement model — fixing, reviewing, test-round reporting
- **Reasoning**: The two-tier design (local build + judgement) already exists
  with escalation after 2 failed attempts; the new evidence says the *roles*
  are mis-assigned for local models: drafting works (fast-path builds
  complete in minutes), but fixes and reviews are where local-only runs die
  (both live-run reverts were specialist_backend fixes; fast/local web-todo
  scored 0.1/0.1/0.5 while frontier-judged runs scored 1.0; the test-round
  model omitted up to 15 failing ACs from its structured report — a
  judgement-grade reading task). Research: aider's architect/editor split
  improved *every* pairing (85.0% vs 79.7% best solo); Cognition's finding
  that small models are reliable for narrow mechanical subtasks and
  unreliable as open-ended decision-makers; FrugalGPT/RouteLLM show
  verifier-gated cascades cut cost without quality loss. The harness's own
  data now identifies exactly which nodes are "open-ended decisions" on weak
  models.
- **Empirical evidence**: C8 bench pattern; A6 omission counts (×4
  events/day); `run-bf43c7e2` reverts; `PLAN_ON_JUDGEMENT_MODEL` precedent
  (planning already routes this way and thorough runs benefit).
- **Harness mechanism**: extend the existing roles/escalation machinery with
  per-node routing policy (profile data, Initiative M): (1) defect fixes that
  follow a revert or a second failure run on the judgement model (L.4);
  (2) test-round *reports* (not test execution) summarized/verified by the
  judgement model when the build model's report disagrees with the measured
  suite — or skip the model report entirely and build the defect queue
  procedurally from the JUnit XML + criterion mapping, using the model only
  for root-cause narrative (the backfill already proves the measurement is
  the reliable part); (3) dispute reclassifications confirmed by the
  judgement model (J.2). Cost stays bounded because these are the rare paths
  — the treadmill events, not the happy path.
  One rubric refinement from the frontier research: Claude Code's adversarial
  reviewer pattern runs in a *fresh context* against the plan and is
  explicitly restricted to **correctness gaps only**, because unrestricted
  reviewers over-report — which matches the observed milestone-review noise
  ("gating finding(s) naming no criterion or test case while every test
  passes" ×2 in one day, then demoted to minor by the cap). Reviewer prompts
  should require every finding to anchor to a criterion, a test, or a
  runnable check — the harness's `what_shows_it` gate already enforces this
  shape for some findings; make it universal for review stages.
- **Frontier validation**: Cursor's Router routes to the strong model only
  when a complexity predictor clears a measured uplift bar, at −68% cost
  above baseline satisfaction; Amp pins per-role models and effort; Codex
  gives reviewer subagents high reasoning effort; the SWE-bench
  "mini-roulette" experiment (heterogeneous model switching per instance)
  *beat* either model alone — routing weak-link nodes to the judgement model
  is the same bet, made deterministically instead of randomly
  (https://cursor.com/blog/how-cursor-router-works, https://ampcode.com/docs/
  models-and-subagents, https://www.swebench.com/post-250820-mini-roulette.html).
- **Impact**: Attacks the false-acceptance and treadmill patterns at their
  measured weak point without giving up local-model economics on the 90% of
  calls (drafting, mechanical edits) where the local model demonstrably
  works.
- **Effort**: S–M (routing policy + one new call site class).

---

<a id="plan-part-3"></a>
### Part 3 — Throughput without quality loss

<a id="plan-r"></a>
#### Initiative R: Duplicate-call elimination at the source (recitation + fresh-state digests)
- **Reasoning**: 17–47% of all tool calls are exact duplicates (same stage,
  tool, args) — 3–17M wasted prefill tokens per run — and 395 pointer-answers
  to redundant file reads in 8 runs show the model keeps asking for state it
  already has. Pointer-answers and withholding treat the symptom; the
  research (Manus recitation; BFCL V3 "poor environment-state tracking" as
  *the* canonical small-model multi-turn failure) says the fix is keeping
  current state in recent attention: the workspace digest already exists and
  is cache-friendly — extend it with what the stage itself has already
  learned (files read this stage + content hash + "unchanged since you read
  it", commands run + exit codes, last N results), so the repeated call
  becomes unnecessary rather than punished. Recitation of the current work
  order/goal at the tail of each request (lost-in-the-middle placement) is
  the second half.
- **Empirical evidence**: B1 (per-run duplicate rates incl. live 38%), B5
  (reads ≈70% of calls; 55% of reads ask for untouched files), A5 (live
  repeated-read tally 16 while tools were being withheld), BFCL V3 taxonomy
  (research §8.3).
- **Harness mechanism**: (1) per-stage "already known" block in the digest:
  path→hash/mtime of files read this stage, commands+exit codes, one-line
  results of the last N tool calls; (2) recite the active work order +
  remaining goal at the request tail (byte-stable within a turn); (3) keep
  repeated-query middleware as the backstop, but lower its patience (hard
  stop per L.5) since the digest removes the legitimate reasons to re-read.
  Relationship to the existing opt-in task list: `agents/task_list.py`
  (`HARNESS_TASK_LIST`, experiment pending per its docstring) is the
  *model-owned* variant — `write_todos` costs calls from the stage budget.
  Recitation of the harness-owned work order is the zero-model-call
  complement, and the two can be A/B'd in the same experiment.
- **Frontier validation**: Cline's Focus Chain generates a todo list at task
  start and re-injects it every ~6 messages specifically because "attention
  isn't enough" on long threads; Codex's compaction summary preserves pending
  tasks for the resuming model; Magentic-One keeps task/progress ledgers as
  orchestrator state and re-plans from them; Manus recites the plan into
  recent attention every step (https://docs.cline.bot/features/focus-chain,
  https://arxiv.org/abs/2411.04468, https://manus.im/blog/Context-
  Engineering-for-AI-Agents-Lessons-from-Building-Manus).
- **Impact**: A 15–25% cut in tool calls and their prefill is plausible from
  the duplicate rates alone — hours per run on a prefill-bound server — and
  the same blocks improve answer quality (state tracking is the measured
  weakness — BFCL V3 names poor environment-state tracking as *the*
  canonical small-model multi-turn failure).
- **Effort**: M (digest extension + placement rule).

<a id="plan-s"></a>
#### Initiative S: Server-side throughput checklist (owner-operated; harness verifies)
- **Reasoning**: With one shared slot, parallel mode measured only ~1.0–1.3×
  overlap — the harness fans out 6 specialists against a server that
  serializes them, and every call queues. The model in use is an **MTP**
  (multi-token-prediction) GGUF — i.e., speculation-ready — yet nothing in
  the loop verifies whether speculation, prompt caching (`--cache-prompt` is
  default-on in llama-server but `timings.cache_n` is never read by the
  harness), continuous batching, or slot count match the workload. Research
  quantifies the available wins: OpenHands documents ~2× from suffix
  speculation on Qwen3-Coder; llama.cpp `-np` slots with continuous batching
  and `--cache-ram` reuse across slots; vLLM chunked prefill +
  `--max-num-batched-tokens` + expert parallelism for MoE + APC. KV/weight
  quantization guardrails matter for quality: q4_0 KV "significantly
  degrades tool calls"; q2_K weights cost ~10 points on aider polyglot.
  AGENTS.md forbids touching the owner's model/settings — so this initiative
  is a *measurement and recommendation* surface, not a control surface.
- **Empirical evidence**: F10 (parallel overlap measurement), D1 (40 s →
  ~5 min per call when the server is shared; LM Studio "context exceeded" at
  ~54k despite a 131k setting — a server-config truth the harness's window
  probe should detect and report), B4 (p50 by prompt size), research §8.4.
- **Harness mechanism**: (1) extend the endpoint/fitness probes to read
  server-reported facts where the API exposes them (slots, cache reuse via
  `timings.cache_n` on a probe call, real context ceiling vs configured) and
  record them in the run's model profile + a pre-run `loop.sh ready` line:
  "1 slot; parallel mode will serialize — consider -np N"; (2) publish the
  checklist in docs (speculation/MTP draft, cache-ram, KV dtype, slot sizing
  vs VRAM, batching flags per server) with the measured latency table as
  motivation; (3) align `HARNESS_MAX_PARALLEL` guidance with measured
  overlap so parallel mode is only recommended when the server can actually
  overlap (a 6-way fanout on 1 slot mostly adds queueing and cache thrash —
  every stage switch evicts prefixes).
- **Frontier validation**: OpenHands' 2026 local-LLM guide — written for this
  exact model class (its first recommendation is Qwen3.6-35B-A3B) — prescribes
  the whole checklist: ≥22k usable context required (4096 defaults "break the
  agent"), 32,768 + flash attention recommended, `--enable-prefix-caching`,
  speculative decoding for up to ~2× (https://docs.openhands.dev/openhands/
  usage/llms/local-llms). The owner's model choice is validated by the
  independent benchmark record (Qwen3.6-35B-A3B: Terminal-Bench 24.6%, the
  24GB-VRAM champion; aggregator mirror of official boards,
  https://llmrun.dev/benchmark/terminalbench) — the gap is serving
  configuration, not model selection.
- **Impact**: Up to ~2× decode throughput (speculation, documented) and
  large prefill savings (cache reuse across the fanout) — owner-side, zero
  quality risk, and it makes the harness's own parallel feature honest.
- **Effort**: S (probe reads + docs + advisory wiring).

<a id="plan-t"></a>
#### Initiative T: Re-test streaming on current langchain versions
- **Reasoning**: Streaming is disabled harness-wide (`models/__init__.py`
  `_request_timeout` docstring) because of a documented langchain
  incompatibility, and every call is paced by a worst-case token-rate
  timeout instead. Streaming would give (a) first-token watchdogs that
  detect a wedged server in seconds instead of a 30-minute timeout (one
  historical call held 1800 s), (b) accurate paced timeouts from real decode
  rate, (c) the option of token-level UI later (the UI deliberately
  simulates streaming today). Dependency versions have moved since the
  incompatibility was recorded.
- **Empirical evidence**: F9; D3 (wedged call, OpenAITimeoutError ×2,
  connection-error retries); UI research C11 (simulated streaming trade-off
  documented in `useStreamedText.ts:3-18`).
- **Harness mechanism**: a timeboxed spike: current `langchain-openai`
  against the local endpoint with the harness's retry/repair layers; if the
  old incompatibility persists, capture the minimal repro in the docstring
  and close; if it works, gate streaming behind a profile flag and start
  with non-tool text stages.
- **Impact**: Watchdog latency 1800 s → seconds on wedged calls; unlocks UI
  fidelity later. Bounded spike, cheap either way.
- **Effort**: S (spike) / M (rollout).

---

<a id="plan-part-4"></a>
### Part 4 — UI/UX (owner request: "improve the UI and UX as much as possible")

The full audit (28 files line-by-line, live DOM probes, axe-core scan, 9
screens, ~40 Vercel Web Interface Guidelines violations with file:line, and
12 research-backed opportunities with verified competitor sources) is in
`docs/review-findings.md` §7. Condensed plan:

**What's already strong (protect during the work):** the plain-English
activity narration (`lib/activity.ts` — better UX writing than most frontier
products), the WebSocket layer (ticket auth, backoff, resume, coalescing —
stronger than competitors'), evidence-first DeliveryPanel, honest cost
accounting, thoughtful empty states.

**Headline gaps (measured):** zero live regions / ARIA roles on the live
dashboard (screen readers cannot monitor a run at all); 197 color-contrast
violations (3.4:1 muted text at 10–12 px — the design's load-bearing
metadata); 218 unlabeled buttons; modal without dialog semantics; a
transient poll failure blanks the entire live dashboard; no virtualization
for up to 5,000 events (whole-tree re-render per WS message); gates arrive
silently (no notification/title/favicon — a gate self-approves after
`approval_timeout_minutes` and nothing told anyone); reviews require
download → external edit → re-upload because the artifact is not rendered
in-app; intake is one dense form for a decision that launches a 7–20 h run;
no mid-run steering despite the harness supporting dynamic instruction
injection; parallel mode (the flagship feature) renders as one interleaved
scroll.

**Phase 1 — remove harm (days; mostly <20-line diffs):** live-region pass;
contrast tokens ≥4.5:1; labels/aria-label/expanded/current + keyboard
dropzone + app-wide focus-visible; toast+dialog primitives replacing
alert/confirm (delete gets undo); stale-while-error dashboard + reconnecting
chip + ticking elapsed clock; tab hygiene (visibilitychange polling pause,
title/favicon badges, browser Notifications on gates/failures/completion);
render the reviewed artifact inline + show the auto-approve countdown;
shell fixes (color-scheme, real product title, theme-color, font
preconnect/self-host for offline, content-visibility:auto on feed rows,
delete dead code: `wizardData.ts`, `DynamicWorkflowUI.tsx`, `App.css`).

**Phase 2 — structural (1–3 weeks each):** design-system primitives
(Button/Card/Badge/Tabs/Modal-with-focus-trap/Disclosure/Toast) + off-palette
hex cleanup; virtualized transcript + memoized children + capped buffer +
parallelized fetch + AbortController; URL state (deep-linkable
view/section/tab; wizard follows live unless overridden); artifact
versioning + diff viewer + screenshot lightbox (artifacts already track
`revision`); cost/budget cockpit (spend-vs-ceiling, per-stage breakdown,
`waiting_for_budget` recovery flow); intake redesign (3-step wizard with
draft persistence and a start-summary + ETA screen — the existing forecast
line "typically 7.6 h over 5 runs" is a gem to promote); command palette +
gate keyboard shortcuts.

**Phase 3 — differentiators (1–2 months):** mid-run steering composer via
the existing dynamic-instruction-injection hook (Devin Side Chats / Claude
Code steering parity — the single biggest product leap); checkpoint timeline
with scrubbing on top of existing rewind snapshots (LangGraph time-travel
pattern); parallel-agent lanes with per-specialist status and feed filters
(events already carry stage identity — no backend change); post-run Insights
panel + cross-run comparison (OutcomesPanel is the seed); mobile monitoring
PWA with one-tap gate actions (directly reduces idle gate time on 7–20 h
runs — runs parked 12–13 h in awaiting_approval were observed in the run
data); i18n extraction + light theme via the token layer.

**Backend enablers the UI phases need** (small, listed here so the parts
connect): `completed_with_gaps` status from Initiative J.4; gate-deadline
timestamp in the run payload (approval timeout exists in state); a steering
endpoint wrapping dynamic instruction injection; per-stage token/cost
rollups for the cockpit (transcript metrics already compute most of it).

---

<a id="plan-part-5"></a>
### Part 5 — Benchmarks and measurement (so the loop can verify all of the above)

<a id="plan-u"></a>
#### Initiative U: Benchmark corpus gaps + KPI extensions
- **Reasoning**: The corpus (web-todo, notes-api ×3, wordstats-cli,
  textkit-lib, fullstack-bookmarks, web-todo-react) never exercised a
  fullstack **Python** brief or a service-backed brief — which is exactly
  the class that detonated live (`run-bf43c7e2`: stub-entrypoint wiring,
  database demands with no database, venv-invisible pip). The medium brief
  found in one live run what six benchmark families never surfaced.
  Meanwhile the loop's measurement tooling (run_timing, redundant_reads,
  model_fitness, defects, failures, stage_trace) has no KPI for the failure
  classes this review quantified by hand.
- **Empirical evidence**: F17 (corpus inventory), F1/F2 (live failures in
  the unbenchmarked class), F18 (existing tooling to extend), B1–B8
  (hand-measured KPIs that should be automatic).
- **Harness mechanism**: (1) add a fullstack-python bench and a
  service-backed bench (declared via the Initiative K.2 pack `services:`
  contract) with hidden tests in the existing format; (2) extend
  `scripts/loop` reports with the now-defined KPIs: duplicate-call rate per
  stage, per-tool error rates (replace_lines vs edit_artifact), cache-hit %
  (from transcript usage), reasoning-exhaustion events + discarded tokens,
  stale-fixer dispatches, vacuous-green detections, reverts/run,
  reclassification events, prefill:decode ratio; (3) wire the same KPIs into
  `evaluation/evaluate.py` datasets so harness changes are A/B-able against
  the bench scores.
- **Frontier validation**: Terminal-Bench/Harbor exist precisely because the
  same model scores differently under different harnesses — measure on your
  own scaffold, not public leaderboards; the mini-roulette result (model×task
  interactions beating either model) is another argument for per-node KPIs on
  the house corpus (https://github.com/laude-institute/harbor,
  https://www.swebench.com/post-250820-mini-roulette.html).
- **Impact**: Every initiative above gets a measurable acceptance criterion;
  the improvement loop's step 2 ("audit the run") stops depending on
  one-off manual forensics like this review.
- **Effort**: M (bench authoring is the long pole; KPIs are mostly
  transcript-metrics plumbing).

---

### Sequencing summary

| Priority | Items | Why first |
|---|---|---|
| P0 | J.1 vacuous-green gate, J.4 honest completion states, K.1 environment contract to architect/QA, L.3 dispatch-time re-measure, L.5 identical-call hard stop | Days-scale, each closes a measured runaway path (false accept, unfixable-defect treadmill, stale dispatches) |
| P1 | J.2/J.3 release probes + reclassification cap, K.3–K.5 wiring proof/drift gate/sandbox coherence, L.1/L.2/L.4 clustering + file-granular revert + judgement escalation, M model-profile contract, N reasoning budgets, Q routing | The quality core: release integrity + local-model reliability; mostly S–M effort with direct evidence |
| P2 | O context diet + cache discipline, R duplicate-call elimination at the source, S server checklist, T streaming spike, UI Phases 1–2 | Throughput and UX; O/R are the "performance without compromising quality" main levers and need the P1 profile work as a base |
| P3 | UI Phase 3 (steering, timeline, lanes, insights, PWA), U bench corpus + KPIs (start KPI plumbing earlier if convenient — it validates everything else), K.2 services provisioning | Differentiators and the longest builds; U's KPIs ideally land alongside P1 to measure it |

Cross-cutting rule honored throughout: every mechanism is expressed at the
contract/pack/profile level; stack-specific data (parsers, sampling presets,
services, smoke shapes) lives in packs/profiles/seed, never in core prompts
or code paths.

### Coverage check and addenda (appended same day, post-opinion review)

The review opinion named eight structural gaps. Mapping to this appendix:

| Gap (as stated in the opinion) | Where addressed | Status |
|---|---|---|
| Release path gameable by the measured (false acceptances, vacuous green, reclassify-to-ship) | J.1–J.4 | Covered |
| No single source of environmental truth (architect uninformed, sandbox/venv seam, stub entrypoint) | K.1–K.5 | Covered |
| Catches failure but terminates it badly (whole-stage reverts, stale queues, loops surviving withholding, late escalation) | L.1–L.5, Q | Covered, with one addendum below (L.6) |
| Mitigations fighting each other; complexity accretion without marginal-value accounting | M (repair layers → profile data), O (leaks), R (root causes), U.2 (measurement) | **Was partial — addendum V below** |
| Budgets context like a frontier harness (prefill economics) | O, R, S, T | Covered |
| Model report treated as primary where deterministic measurement exists | Q.2, L.3 | Covered |
| The loop's audits depend on manual forensics | U.1–U.3 | Covered |
| The plan's own records can log a false acceptance as a verified success | J.4 gives the status; record-keeping rule was missing | **Addendum J.5 below** |

<a id="plan-v"></a>
#### Initiative V: Layer-economics audit — every mitigation proves its marginal value or goes
- **Reasoning**: The repair layers, middlewares and guards each earned their
  place individually, but nothing ever measures them *in aggregate*: project
  memory cut redundant reads and grew average requests 44k→95k tokens on a
  prefill-bound server; tool withholding changes the tool list mid-stage,
  invalidating prefix cache and confusing weak models; pointer-answers to
  repeated reads still cost a full model turn each. The opinion review called
  this "mitigations fighting each other"; the honest fix is a periodic
  delete-or-keep verdict per layer, with the same evidence standard the
  codebase already applies to fixes. The same audit should address
  maintainability seams: `graph/workflow.py` is ~10.5k lines and the
  middleware×graph interactions are becoming a bug surface of their own.
- **Empirical evidence**: B2 (avg request growth after project_memory), B1
  (duplicate rates despite three anti-duplicate layers), A5 (loops surviving
  withholding, live tally 16), O/R reasoning above; task_list.py's own
  docstring is the model to follow ("no measurement supports it yet, and this
  module says so").
- **Harness mechanism**: (1) once U.2's KPIs land, produce a per-layer
  ledger: token cost added to average requests, calls saved, errors
  prevented, cache-hit delta — one table, regenerated each loop cycle from
  transcripts; (2) any layer whose measured marginal value is negative or
  indistinguishable from noise gets simplified, profile-gated, or removed
  (the task_list `HARNESS_TASK_LIST` opt-in pattern is the template); (3) a
  bounded refactor track for workflow.py seams (module extraction along the
  existing `graph/` package lines — no behavior change, suite-proven).
- **Impact**: Stops the ratchet where every fix adds context and every added
  context slows the prefill-bound loop; keeps the codebase's evidence culture
  applied to the harness itself, not only to generated products.
- **Effort**: M, recurring (the ledger is the deliverable; the refactor track
  is separately scoped).

<a id="plan-j-5"></a>
#### Addendum J.5: Records cite the verdict, not just the suite
- Every durable record of a run's outcome — this plan's phase notes, the
  handovers, the delivery panel, the bench export — must state the
  *independent* verdict alongside the suite state: hidden-test score where
  one exists, `completed_with_gaps` markers where not, and reclassification /
  deferral counts always. A green suite alone is never recorded as
  "verified" again. (Process rule, zero code beyond J.4's status plumbing;
  the corrected 94d2c449 entry above is the worked example.)

<a id="plan-l-6"></a>
#### Addendum L.6: The last attempt changes strategy, not just model
- L.4/L.5 change *who* fixes (judgement model) and *when the loop stops*, but
  the opinion review's sharper point was "terminate with a different
  strategy." So: when a defect reaches its final permitted attempt (post-
  revert, post-escalation), its work order must also change *shape* — e.g.,
  whole-file rewrite of the implicated files instead of a patch (P's rewrite
  path), or the cluster is handed to sprint re-planning with the two failed
  attempts attached as evidence — instead of a third variation of the same
  instruction. Frontier parallel: Magentic-One re-plans from its progress
  ledger on error rather than retrying; Claude Code's documented human
  heuristic is "corrected twice → restart," not "correct a third time."
- **Effort**: S (work-order shaping at the dispatch site L.3 already touches).

Sequencing for the addenda: J.5 and L.6 join P0/P1 with their parents; V
starts as soon as U.2's KPIs exist (P2), with the ledger published each loop
cycle thereafter.

### Coverage completion pass (second addendum, same day)

The first addendum closed the three gaps from the opinion review. This pass
sweeps the *full* evidence inventory — the forensics report (A1–A9 failure
modes, B1–B8 waste patterns, C1–C8 local-model issues, D1–D7 infra, E1–E8
quality compromises), the review findings ledger (F1–F18), and both research
reports' recommendation lists — against every initiative in this document
(A–I pre-existing, J–U + V from this appendix). Result: 12 residual items,
closed below as new sub-items or explicit amendments. Everything else maps to
an existing initiative, was already fixed in code, or is accepted design
(table at the end).

<a id="plan-j-6"></a>
#### J.6: Terminal-state hygiene — the workspace must tell the truth after the run ends
- **Gap (E8, parked items)**: failed runs' workspaces are not marked
  non-deliverable (monitoring-handover §8.3); release evidence (suite report,
  ci.json, decision log) is uncommitted in every finished run; stage notes
  (`blocker.txt`, `verification.log`) shipped inside stored products (4 files
  across 199 products, parked).
- **Mechanism**: (1) any terminal state other than a clean release writes a
  machine-readable non-deliverable marker into the workspace root, surfaced
  in the UI run card and the handover zip; (2) at release, commit the
  evidence bundle (final suite report, ci state, decisions.json, gap markers
  from J.4) into the repository so the handover is self-proving; (3) extend
  `_clear_the_throwaways` to the parked stage-note patterns so scratch files
  never ride along in a delivery.
- **Why it belongs to J**: a `completed_with_gaps` status that lives only in
  the database is half an honesty mechanism; the artifacts themselves must
  carry it. Effort: S.

<a id="plan-j-1-amendment"></a>
#### J.1 amendment: the vacuous-green gate covers the scaffold setup proof too
- **Gap (E5, C6)**: `run-3642baf8`'s setup proof caught the zero-test smoke
  (`exit 0, 0 passed`) and then continued "left to the agents"; the run
  released at 1/10. Unproven setups also lose kept-file protection (parked
  §0.5.1).
- **Amendment**: J.1's executed-tests ≥ locked-tests rule applies at *every*
  gate including the scaffold/setup proof, and a zero-test or count-mismatch
  smoke fails closed (retry the proof, then escalate/stop) — never "left to
  the agents". Stack-specific runner pitfalls that cause silent zero-test
  runs (e.g., a glob the runner's runtime does not expand) are pack data per
  K.6, detected at proof time by the count rule itself. Effort: S (folds
  into J.1's implementation).

<a id="plan-k-6"></a>
#### K.6: Stack-shaped checks become pack data — every stack gets the visual/interface guarantees
- **Gap (F11, C6)**: `analysis/interface_checks.py` and the integration
  checks are JS/browser-shaped; products on other stacks get no equivalent
  of the unstyled-page, overflow, or console-error checks, so Initiatives
  A/B's visual guarantees silently apply to one ecosystem. Runner-quirk
  knowledge (glob expansion, test discovery paths) likewise lives in nobody's
  head until a run dies on it.
- **Mechanism**: extend the pack contract with (a) per-stack check
  declarations — the observable failure signatures the pack's surface can
  exhibit (unstyled rendering, layout overflow, console/runtime errors,
  failed requests) and how to detect them for that stack — and (b) runner
  notes consumed by the acceptance author and the setup proof. Core stays
  agnostic; the JS implementations become the browser packs' data.
- **Impact**: makes the existing visual/interface loop language-agnostic, as
  the product requires. Effort: M (contract + port existing checks to data).

<a id="plan-l-7"></a>
#### L.7: Plan-validator-first repair — stop the ping-pong before it starts
- **Gap (B7, E3)**: `Milestone plan is not ready… sending it back to the
  lead` ×5 in one day with the *same* structural cause across three runs
  ("No testing work order"); history: a lead sent back 3× returning the same
  plan (~40 min); plans then dispatch "with the problems noted" and the
  problems go nowhere.
- **Mechanism**: (1) the deterministic readiness validator's exact failing
  rules ride along in the *first* planning request (rules as prompt data,
  byte-stable — cache-friendly), so the common structural failures never
  happen; (2) on a send-back, the validator auto-repairs what is
  deterministically repairable (a missing standard work order it can itself
  construct — fast mode's harness-made work orders already prove the
  pattern) and records the repair; only semantic problems go back to the
  model; (3) a plan still dispatched "with problems noted" writes those
  problems into known_issues and the delivery evidence (J.6), so a shipped
  plan's known holes are visible at release instead of lost.
- **Impact**: removes ~10-minute round-trips that recur identically across
  runs; the validator, not the model, owns what the validator can decide.
  Effort: S–M.

<a id="plan-p-4"></a>
#### P.4: Lookup-tool hygiene — no more 404 round-trips for deterministic mistakes
- **Gap (B8)**: 29 registry 404s in one day: capitalized package names
  (`Playwright` ×9), README casing ladders (`README.md|Readme.md|readme.md`
  ×12), concept lookups as package names (`pypi.org/pypi/PostgreSQL` ×2);
  history: lookups of `already`, `build`, `package.json`, `Node.js`.
- **Mechanism**: in `look_up_package` (and registry lookups generally):
  normalize case before querying; run one casing fallback ladder internally
  instead of returning intermediate 404s to the model; when the term is not
  a plausible package name (a technology or concept word — data lives in the
  pack's ecosystem vocabulary), return guidance ("no package by this name;
  the driver for <technology> in this stack is typically …" from pack data)
  rather than a 404 the model will retry. Each 404 avoided is a saved model
  turn, since the tool result is what the model reacts to.
- **Effort**: S.

<a id="plan-q-4"></a>
#### Q.4: Write-receipt reconciliation — phantom claims answered deterministically, not with a model call
- **Gap (A8)**: ×11/day `Stage X reported changing <files>, which nothing in
  it wrote; asking it once to make the change or say what it did` — the
  clarification itself is a full model call, and two stages doubled down
  anyway (`still reports changing…, recorded without them`).
- **Mechanism**: the harness already knows the ground truth (write receipts
  from the sandbox/edit tools). Reconcile the stage's claimed changed-files
  against receipts *deterministically*: claims with receipts pass silently;
  claims without receipts are dropped and recorded as "claimed, not written"
  with no model call; a stage whose claim rate is pathological gets the
  discrepancy stated in its next request (one line, not a turn). The pattern
  count joins U.2's KPI ledger as a per-model honesty signal — relevant to
  profile selection (M) and routing (Q).
- **Effort**: S (replaces an existing model-call path with code).

<a id="plan-q-amendment"></a>
#### Q amendment: optional judgement-model diff review in fast mode
- **Gap (E1)**: fast mode skips model code review entirely (`Code review left
  to the tests and checks (fast delivery)`), and the tests are exactly what
  A1 showed can be weak. Thorough mode's reviews exist but are the local
  model's — the measured weak link (C8).
- **Amendment**: an owner-tunable flag (default off, benchmarked before any
  default change) adds one judgement-model review pass per milestone over
  the *diff since the last accepted state* — bounded cost, fresh context,
  findings anchored per the Q rubric refinement (correctness gaps only, each
  naming a criterion/test/check). This is the cheapest place to spend
  judgement-model tokens in fast runs, and U's KPIs will show whether it
  moves hidden-test scores.

<a id="plan-o-1-amendment"></a>
#### O.1 amendment: section-scoped spec revisions, and file bodies never inside grammar-enforced JSON
- **Gap (A9, B7-history)**: spec *revisions* regenerate whole documents and
  blank entire sections ×10/day (`error_catalogue, implementation_order,
  test_cases, configuration, library_usage, decisions` — restored from the
  previous answer, at full generation cost); history: revisions cut at
  103k chars costing ~1h49m. Separately, research (aider, vLLM docs) says
  code wrapped in schema-enforced JSON loses 10–15% quality.
- **Amendment**: (1) a revision request carries only the sections the review
  flagged plus their dependencies, and the response is per-section — smaller
  generations, no whole-document blanking, byte-stable unchanged sections
  (helps the O.3 cache rule); (2) wherever the harness generates file bodies
  (drafting, redrafts, whole-file rewrites from P), the body travels as a
  plain-text field outside any grammar enforcement — enforcement stays on
  the control plane per M.

<a id="plan-m-amendment"></a>
#### M amendment: drafting excluded from enforcement (explicit)
- Recorded here so M's refinement (a) is unambiguous at implementation time:
  grammar/structural-tag enforcement applies to tool-call envelopes and
  structured control-plane schemas only; code-generation calls are
  unconstrained plain text (see O.1 amendment, research §8.1/8.7 item 5).

<a id="plan-s-amendment"></a>
#### S amendment: mid-run endpoint health telemetry
- **Gap (D3)**: connection errors, a model server serving a different model
  than the run expects (LM Studio 404 "downloaded but not loaded" ×6), and a
  wedged 1800 s call were all discovered by failures, not monitoring.
- **Amendment**: the call layer already sees every error class; emit a
  health signal (consecutive connection errors, latency-vs-prediction drift,
  model-identity mismatch from the endpoint probe re-run) into the run's
  event stream, where the UI's notification path (Part 4 Phase 1 item 6) can
  alert the operator instead of the run silently burning retries. Effort: S.

<a id="plan-u-4"></a>
#### U.4: Retention policy for transcripts and run data
- **Gap (D7)**: transcripts reach 181 MB/run; `data/postgres` is at 4.0 GB
  and growing with every run's events — unbounded on a single machine.
- **Mechanism**: after a run reaches a terminal state and its KPI extract
  (U.2) is written, compress the transcript (or keep head+tail+KPI extract
  per a retention tier the owner sets); prune/aggregate the events table on
  the same tier; never prune bench-scored runs' evidence bundles (J.6
  commits them into workspaces, which have their own lifecycle). Effort: S.

<a id="plan-part-4-enabler"></a>
#### Part 4 enabler amendment: stalled-gate visibility
- **Gap (D5)**: runs parked 12–13 h in `awaiting_approval` with
  `approval_timeout_minutes` NULL — no UI surface distinguishes "waiting for
  you indefinitely" from "auto-approves in 4 minutes".
- **Amendment**: the gate-deadline enabler already listed gains: NULL
  timeouts render as "waits indefinitely — nobody will be notified" with the
  notification path (Phase 1 item 6) firing once on entry; an optional
  per-run default timeout becomes an intake setting (Phase 2 item 14). This
  also protects against the paused-run resurrection competing for worker slots
  noted in the forensics (D5).

<a id="plan-sweep"></a>
#### Sweep table — every remaining evidence item and its disposition

| Evidence item | Disposition |
|---|---|
| A1 false acceptances | J.1–J.4, J.5 (+ J.1 amendment) |
| A2 replace_lines | P.1–P.3 |
| A3 hallucinated tool names | M (profile + arg-fit map as data) |
| A4/B3 reasoning exhaustion | N |
| A5/B1/B5/B6 loops, duplicates, re-reads, budget exhaustion | R, L.5 |
| A6 stale defect queues | L.3, Q.2 |
| A7 suite churn, reverts | L.2, J.2 (reopen mechanism itself is accepted design — it is the correction path working) |
| A8 phantom write claims | **Q.4 (new)** |
| A9 structured-output degradation | M, N, **O.1 amendment (new)**; section-restore mitigation already in code |
| B2/B4 prefill dominance, model wait | O, S, T |
| B7/E3 plan ping-pong, dispatch-with-problems | **L.7 (new)** |
| B8 lookup 404s | **P.4 (new)** |
| C1–C5, C7 | M, N, P, existing compiler-check/redraft loop (working as designed — bf43c7e2's redrafts succeeded) |
| C6 framework/runner mixes | J.1 amendment + K.6 (runner notes); existing Initiatives D/F cover suite strength |
| C8 quality cliff | Q (+ Q amendment) |
| D1/D2 shared server, prefill latency | S (+ S amendment) |
| D3 connection/wedge failures | T (watchdog), S amendment, existing probes/call-gate |
| D4 Celery limit kill | Already fixed in code (limits raised to 12 h) — no action |
| D5 approval stalls | Part 4 Phase 1/3 notifications + **enabler amendment (new)** |
| D6 msgpack serialization | Already fixed in code (`_StorableSerializer`, 0 recurrences) — no action |
| D7 disk growth | **U.4 (new)** |
| E1 fast-mode review skip | **Q amendment (new)** — owner-tunable, benchmarked |
| E2 review caps → risks | Q rubric refinement + J.4 (demoted findings count toward gaps) — caps themselves are accepted design (bounded revision loops) |
| E4 reclassify-to-ship | J.2 |
| E5 unproven setups | J.1 amendment, K.3 |
| E6 auto-decisions unattended | Accepted design (unattended mode is the product); transparency via J.4/J.5 + decision log |
| E7 defects left open at completion | J.4 (`completed_with_gaps`), J.6 (marker in workspace) |
| E8 notes shipped, evidence uncommitted, failed-workspace marking | **J.6 (new)** |
| F1–F6, F8–F10, F12–F13, F15, F17–F18 | K, O, L, S, T, U (as mapped in the first addendum's table) |
| F7 reasoning exhaustion (live) | N |
| F11 JS-shaped checks | **K.6 (new)** |
| F16 visual-loop depth | Pre-existing Initiatives A/B (not duplicated, per mandate); K.6 extends them to all stacks |
| Local-LLM research recs 1–12 | M(1,3,5,11), N(2), Q(4,12), O(6,7), S(8,10), existing graph determinism(9) |
| Frontier top-15 #1–#15 | #1 M, #2 M bash-mode, #3/#4 P (+P.4), #5/#6 O(.4 + amendment), #7 existing CI/compiler gates, #8 R (task_list experiment noted), #9 existing single-writer work orders, #10 Q/M, #11 existing work-order flow, #12 pre-existing Tier 2 repo-map item in docs/improvement-plan.md (reinforced, not duplicated), #13 existing locked-suite/dispute, #14 O.3, #15 existing sandbox (stricter than bash) |
| UI audit B1–B7, C1–C12 | Part 4 Phases 1–3 (complete by construction — the roadmap was built from the audit) |

With this pass, every item in the review's evidence inventory is either an
initiative, an amendment, an explicit "already fixed in code", or an explicit
"accepted design with a transparency mechanism". Nothing observed is left
unmapped.

---

<a id="plan-ledger"></a>
### Implementation Progress Ledger

Started 2026-10-18 (JST). Rules: update this ledger in the same commit as
every implementation change; DONE rows carry the date (the commit is the one whose message names the row); BLOCKED rows
carry the reason. Priorities are from the sequencing table; the Antigravity
cautions (recorded inline on Initiatives J/K/L/M/O above) are binding
implementation constraints and are restated in the Notes column.

| Item | Priority | Status | Notes |
|---|---|---|---|
| J.1 vacuous-green hard gate | P0 | DONE 2026-10-18 | `suite.vacuous_green` (zero tests, no criterion named, declared test never collected) enforced at lock (never waivable by round count), test rounds (suite defect → repair flow), and release (held even with all criteria deferred); tests in `tests/test_a_suite_that_proved_nothing_is_not_green.py`; documented in monitoring-handover §0.10. setup-proof amendment: a pack scaffold that cannot be proven is retried whole once, then the run escalates (parked attended / failed unattended) instead of continuing "left to the agents"; pack-less custom stacks keep their documented escape (`custom_setup` already requires >=1 passing smoke test). Refined 2026-10-18: zero tests because the product never started (the runner's web server exited or its build failed - `suite.the_product_did_not_start`) is not vacuous green: it is recorded as the run's problem and raised as one blocking product defect carrying the build error (owner by the file it names), never a suite repair - run-8b0c94df's suite was sent back to QA over `"App" is not exported by "src/App.tsx"` |
| J.4 `completed_with_gaps` status | P0 | DONE 2026-10-18 | Implemented as `completion_gaps` on the run record rather than a new status value (the enum's own comment warns an unaccepted status breaks *reading* a run; the gaps list carries strictly more). Sources: deferred criteria, problems the suite was locked with, plan problems noted at dispatch, an unproven setup, no locked suite. Surfaces: runs row + migration, run-status API, run dashboard panel, outcomes dashboard rows, `loop.sh score` export (bench + outcomes JSON), release decision rationale. Reclassification counts and demoted findings arrive via deferrals/open problems until J.2 tracks reclassifications explicitly. Added 2026-10-18 (deep analysis): a product whose unit command ran no test at all is a gap (`delivery._no_unit_tests_ran`) - run-8b0c94df's 2,863-line product had none and `npm test` exited 0 |
| J.5 records cite the verdict | P0 | DONE 2026-10-18 | Release decision cites the suite's counts and every gap; the evidence page carries "Measured by the harness" counts plus a Completion gaps section; bench export carries the harness verdict and gaps; rule documented in monitoring-handover §0.10 |
| K.1 environment contract to architect/QA | P0 | DONE 2026-10-18 | `describe_execution_environment()` moved to `app.agents.environment_contract`; every role agent now gets a derived, byte-stable contract block appended ahead of the workspace digest (middleware, so all thirteen request builders are reached): commands from the allowlist, browser truth, no network, nothing running + the adapter-substitution rule, containers written-not-built, installs must land where the product's commands read. Selector keeps its fuller text. Kill switch `ENVIRONMENT_CONTRACT=0` |
| L.3 dispatch-time re-measure | P0 | DONE 2026-10-18 | `_closed_if_an_earlier_fix_resolved_it` re-measures now: when no stored measurement settles a defect, the harness runs `_the_defect_s_tests_pass` (the same per-file acceptance probe the post-fix check uses) at dispatch before spawning a fixer; a green probe closes the defect "already fixed when it came up for dispatch" with a `closed without a fixer` ledger note, a probe that cannot answer dispatches the fixer exactly as before. Tests in `tests/test_a_defect_whose_own_tests_pass_at_dispatch_never_reaches_a_fixer.py`; the cheaper stored answers still come first |
| L.5 identical-call hard stop | P0 | DONE 2026-10-18 | `settled_answer._decide` ends a stage deterministically when its conversation shows `SAME_CALLS_BEFORE_ENDING_THE_STAGE` (12) identical nothing-new calls - counted from the read-refusal, same-answer and identical-failure markers, not the shared tally that was measured counting the run - and no structured answer was written; the stop carries `BUDGET_STOP_MARKER` (so recovery skips the nudge and retries on a fresh conversation) plus a distinct `NO_PROGRESS_MARKER` for logs and routing. Tests in `tests/test_a_stage_making_the_same_calls_ends_with_no_progress.py` |
| L.6 final attempt changes strategy | P0 | DONE 2026-10-18 | `_the_last_attempt_section` appends a differently-shaped order to a defect's fix request once `failed_fix_tries` reaches `escalate_after()`: rewrite the implicated files whole rather than patching lines, with a named blocker as the way out when the specification cannot produce a passing file - a third variation of the instruction that failed twice is no longer what the last rung asks for. Banned-word-clean; tests in `tests/test_a_defect_s_last_attempt_changes_shape.py` |
| Q.4 write-receipt reconciliation | P1 | DONE 2026-10-18 | Phantom claims are dropped from the record deterministically - the "asking it once" clarification was itself a full model call (×11/day) and two measured stages doubled down anyway; `_claims_dropped_from_the_record` keeps only what receipts show was written. The warning "claimed N file(s) nothing in it wrote ... dropped from the record" is the counting line for the per-model claim rate; the one-line notice to a pathological stage and the KPI itself land with U.2's ledger, which owns the per-model honesty signal |
| J.2 reclassification cap + second opinion | P1 | DONE 2026-10-18 | Three legs now stand: the dispute stage already ran on the judgement model (its second opinion); `acceptance_nodes.tests_that_fail_alone` re-measures every disputed test executable - its own file, run alone against the delivered surface in the project's own runner, no model - and a test that passes alone stays locked (the suite run failed it for order or state); `within_the_cap` caps dispute-driven reclassifications per run at max(2, locked tests // 10), tracked in the new `suite_reclassified_tests` state key, recorded by `reopen_the_suite_for(..., reclassifying=True)` and named in the release's `completion_gaps` (closing J.4's note that reclassifications reached gaps only via deferrals). Tests past the cap stay failing and ride to the release. The spec-compiled per-criterion probe (formal contracts, not brief text) is J.3's compiler and reuses this wiring; tests in `tests/test_a_disputed_test_is_re_measured_and_reclassifications_are_capped.py` |
| J.3 release-time per-criterion probe | P1 | DONE 2026-10-18 (Playwright packs) | `acceptance/interface_contract.what_the_contract_checks_find`: at release, the locked contract's HTTP and page lines are compiled into a Playwright spec under a generated config that reuses the pack's own (`import base from './playwright.config.js'`, same server start), run by the suite's runner, then removed. A failed check is a completion gap (owner: gap for the first 2 runs, then blocker if accurate). Verified on a copy of a live fullstack workspace: the server started, a page control passed, a made-up route failed. Not yet for non-Playwright runners (command lines are parsed and kept, not run) |
| J.6 terminal-state hygiene | P1 | DONE 2026-10-18 | `app.graph.terminal_state` writes `NON-DELIVERABLE.json` into the workspace root for every terminal state but a clean release (failed, cancelled, completed-with-gaps) and a clean release clears it; the run-status API reports what it says (`non_deliverable`) and the run dashboard shows it in a red panel. Sweeper extension: `blocker.txt` and `verification.log` - the stage notes measured shipping inside stored products - join `SCRATCH_NAME`. The committed-evidence leg was already shipped (`test_a_completed_run_leaves_nothing_uncommitted` pins the "Run complete:" commit carrying the decision log, evidence pages and sprint records; J.5 put the gaps in the evidence page). Tests in `tests/test_a_workspace_tells_the_truth_after_the_run_ends.py` |
| K.3 entrypoint wiring proof | P1 | DONE 2026-10-18 | `StackPack.entrypoint` declares the file the drafted service's routes live in (pack data: node-http-api and fullstack-node `src/app.js`, node-nest-api `src/app.module.ts`, go-http-api `server.go`, rust-axum-api `src/lib.rs`; `service_pack` forwards it). `scaffold.entrypoint_is_still_the_stub` compares it byte for byte against the rendered scaffold stub, and both harness measurement rounds - the file-by-file diagnosis and the fast-delivery round with failing due criteria - append `_the_served_app_is_the_scaffold_s_stub`, one bundled defect naming the wiring gap itself instead of its 31 symptoms. The executable smoke-request leg against a live server rides J.3's serving machinery when it lands. Tests in `tests/test_a_served_app_that_is_still_the_scaffold_s_stub_is_named_as_such.py`. Extended 2026-10-18: packs may declare several stub files (`StackPack.entrypoints`; every fullstack pack declares its page component and its service module, e.g. `src/App.tsx` + `{{package}}/main.py`), and the specification is sent back when its file plan names none of the served files (`_the_served_files_the_plan_leaves_out`) - run-8b0c94df planned the product in `frontend/` + `backend/app/`, nothing drafted was served, every page test failed its first control |
| K.4 dependency-drift gate | P1 | DONE 2026-10-18 | `app.analysis.dependency_drift.undeclared` reconciles the code's third-party imports against the manifests - `package.json` (dependencies, dev, peer, optional) for JavaScript/TypeScript, `requirements*.txt`/`pyproject.toml` (project + poetry) for Python, with the alias table (`yaml`→`pyyaml`) and the dash-suffix rule (`psycopg2-binary` declares `psycopg2`); a language without a manifest is never reconciled. The CI gate (`underlined_in_the_batch`) bundles every gap into one `the_bundled_defect` after the underline cap, so the fixer declares the dependency instead of a model discovering it in a failing runner. The measured case: `jsdom` imported under an empty `devDependencies` with a full `node_modules` - a clean `npm ci` provides none of it. Tests in `tests/test_an_import_no_manifest_declares_is_one_bundled_defect.py` |
| K.5 sandbox install coherence | P1 | DONE 2026-10-18 | `_the_project_virtualenv` finds the project's virtualenv through the contract record - the same `.venv/bin` the pack's own install, unit and serve argv use - and `_child_environment` puts it in front of every sandbox command's PATH, so a bare `pip install` lands where the acceptance server's interpreter reads it. Before this, the environment contract said "installs must land where the product's commands read" and the sandbox contradicted it (§6.2's instructing-and-punishing class). Tests in `tests/test_a_sandbox_install_lands_where_the_product_reads.py`. Completed 2026-10-18: the executable lookup searches the same PATH, virtualenv first - `pytest` in `.venv/bin` had been answered "not installed in this environment" five times in one stage |
| K.6 stack-shaped checks as pack data | P1 | DONE 2026-10-19 `503a4f0`, with AW | Built once with AW (Part 22.2). The visual half's premise no longer holds: all 12 packs that serve a page already ship the browser page check (`playwright.setup.mjs`: unstyled page, overflow, load errors), which is stack-agnostic; service-only packs have no page to check. The test-file names moved to pack data under AO.10 |
| L.1 root-cause clustering | P1 | DONE 2026-10-18 | `_one_defect_per_root_error` clusters defects by first failing layer and common surface; refined 2026-10-18: only whole-product layers (`_WHOLE_PRODUCT_LAYERS`: connection-refused, unauthorized) merge wholesale - a 404/500/timeout on different routes stays one defect per route. Tests in `tests/test_defects_failing_at_one_layer_are_one_fixer_s_work.py`; and a control the page never showed (`locator.<action>: Timeout`) is its own whole-product layer, `control-never-shown` - run-8b0c94df's round 1 queued 13 defects, every one failing its first locator at 3 s |
| L.2 file-granular revert | P1 | DROPPED 2026-10-18 (validation) | Premise does not hold: one fixer stage makes one fix, so a stage revert removes only that fix; reverting "only the files the stage touched" is the same set as the whole-stage revert. The half-built version (reverted every file changed since the stage's base, with a bracket-count "parse" and a Python import check that could not fail) was set aside, not committed. A useful version would need a culprit search (revert one file at a time and re-measure the broken tests) - worth it only if measurement shows multi-file fixes whose parts are independent |
| L.4 judgement escalation after revert | P1 | DONE 2026-10-18 | `_a_revert_escalates_this_fix(cycle, index)` reads the defect's own notes - exactly one revert note (the single-fix wording `_REVERTED_FOR` matches, or the batch wording) escalates the next attempt; `_the_build_model(..., after_a_revert=...)` routes it to the judgement model before the generic `escalate_after()` rung, and both fix dispatch sites (the single fixer and the batched one) pass the signal. The cap is the shape: a second revert has already pushed `failed_fix_tries` to the generic rung, so L.4 adds at most one escalation per defect. Evidence: both reverted fixes in the live run came from the local build model. Tests in `tests/test_a_reverted_fix_goes_to_the_judgement_model_next.py` |
| L.7 validator-first plan repair | P1 | DONE 2026-10-18 | (1) the lead's prompt names every rule the checker sends a plan back for (adds the scope-names-a-file and harness-kept-file rules); (2) `work_orders.with_a_testing_work_order` builds the missing testing work order deterministically from the stack contract's unit directory + pattern and the code orders' test_cases/interfaces - the recurring "No `testing` work order" send-back; joins the existing deterministic repairs (`with_test_cases_from_its_criteria`, `with_named_tests_given_to_testing`); (3) noted problems already flow to `completion_gaps` via J.4. Tests in `tests/test_a_plan_with_code_and_no_testing_work_order_gets_one.py` |
| M-bash bash-first degraded mode | P3 | NOT STARTED | **Antigravity constraint**: strictly for models with zero native tool-calling; never Qwen/Hermes profiles; executes through the argv-only sandbox |
| N reasoning-budget guardrails | P1 | N.2 DONE 2026-10-18; N.1 measure-first; N.3 premise false | Live run-8b0c94df: 20 replies spent the full 20,000-token budget with no answer (~400k tokens; the lead lost 5 in 23 min of one visit) - the server reports no reasoning tokens, so `run_timing` shows them as spirals. Cause: "thinking stays off after a second loss" counted lost replies from the history, and compaction removed them, so the count never reached two. N.2: the settled-answer middleware now counts each lost reply once by message id (`lost_before`), so thinking stays off for the rest of the visit. N.3: the only cap-halving is for timeouts/proxy cut-offs, never a reasoning-only finish. N.1 (per-request thinking token budget) waits for proof the owner's server honours one. Tests: `tests/test_a_lost_reply_does_not_end_the_stage.py`. Extended 2026-10-18 (deep analysis): the count also carries across a stage's visits (`_LOST_ACROSS_VISITS`, keyed by run + graph stage) - a retry or resume reset it, and run-8b0c94df lost 37 replies of 20,000 tokens (~40% of all output), two or more in eleven fix stages and eight in one planning stage. A lower reply cap was measured and rejected: 33 of 1,049 successful fix replies exceeded 12k tokens |
| P.1 demote `replace_lines` | P1 | DONE 2026-10-18 | Re-measured across four runs: replace_lines 51/81 failed (62%) vs edit_artifact 6/82 and write_artifact 7/90 (7%). Off unless `LINE_EDITS=on` (`agent_toolkit.line_edits_offered`): not in `writing_tools`, and `role_agent.without_line_edits` removes it from every system prompt and the near-miss hint. Tests in `tests/test_line_number_edits_are_offered_only_when_switched_on.py` |
| P.2/P.3 parser-refusal escape | P1 | ALREADY IN CODE (validated 2026-10-18) | Both edit paths let an edit to an already-broken file through and report what remains as a note (`_what_is_structurally_wrong(original)` guard, `"you are part-way through a repair"`); only an edit that breaks a healthy file is refused |
| P.4 lookup-tool hygiene | P1 | MOSTLY DONE 2026-10-15 | Registry lookups retry a capitalised 404 in lowercase; the pre-architect research looks up only package-shaped names (no runtimes, files, built-ins, versions, sentence words) and reads docs only for names the registry knows (`research_brief.libraries_of`); README casing is an internal ladder, not model-visible |
| Q.1 route fixes to judgement model | P1 | COVERED by L.4 + `escalate_after()` | Post-revert fixes go to the judgement model (L.4); second failures already escalate generically |
| Q.2 procedural test-round reports | P1 | DONE in substance (verified 2026-10-18) | Fast delivery's round is the harness's own; in thorough, `failing_due_defects(state, reported)` adds every measured failure the model's report left out, so the queue is the measurement's. The model call in thorough stays: it is the owner's mode |
| Q.3 dispute routing + rubric anchoring | P1 | DONE in substance (verified 2026-10-18) | Code-review findings become defects only when `what_shows_it` finds a failing criterion, test or diagnostic; milestone-review gating findings naming no criterion/test while every test passes are made minor (`_findings_no_measure_holds`); with tests failing, those tests gate anyway |
| Q-amend fast-mode diff review flag | P2 | DONE 2026-10-19 `534cbb4`, default off | `FAST_CODE_REVIEW` (compose and `.env.example`, default false; `delivery.reviews_code_when_fast`): set, fast delivery runs the judgement model's code review over each batch's diff since the last accepted state instead of leaving it to the tests and checks. Benchmark before any default change. Test `tests/test_fast_delivery_can_be_told_to_review_code.py` (2 of 3 fail on the old code). Group 1 |
| O.5 stale budget constants | P2 | DONE 2026-10-18 | `DEFAULT_SPECIFICATION_BUDGET` docstring corrected (150k chars is ~40-50k tokens, not 15k); the value is unchanged until O.1's section selection can shrink it without cutting the specification's tail |
| R duplicate-call elimination | P1 | DONE 2026-10-18 (`3c9c931`) | The digest tail lists files read in this conversation (and whether a write here changed them since) and commands run with exit codes, from the messages alone (`ALREADY_KNOWN=0` for the A/B). With the pointer count (9d637fe) and held-back reads (326570e) feeding the read rung. Recitation of the work order not added: it is in the opening request, and the memory now stays stable there |
| S server checklist + health telemetry | P2 | DONE 2026-10-19 `f4a62d6` | `loop.sh ready` reads a llama.cpp-style server's `/props`: slot count and the context it was started with. Finished 2026-10-19: mid-run health - every model call goes through `server_profile.check_again`, which asks the server again at most every 5 minutes, uses changed facts from the next call, and records `server_changed` / `server_unreachable` / `server_reachable` in the transcript (`loop.sh kpi` counts the first two); the owner's checklist (context per slot, slots, cache reuse, KV and weight bits, thinking, speculation) with its measurements is in `docs/PRODUCT.md` §14. Test `tests/test_the_model_server_is_watched_during_a_run.py` (all 6 fail on the old code). Group 1 |
| T streaming re-test spike | P2 | DONE 2026-10-19 `97b49d7` (spike); rollout is group 2 | `scripts/loop/streaming_spike.py` reproduces the path that killed a run - `create_agent`, a tool call, the harness's `CompatibleChatOpenAI` - against a local fake OpenAI-compatible server (no model time): PASS on langchain 1.4.0, langchain-core 1.6.1, langchain-openai 1.6.0, langgraph 1.2.11, openai 3.8.0, on the host and in the worker image. The old "got Stream" incompatibility is gone; `models/__init__.py` records it. Turning streaming on (behind a setting, text stages first, with a first-token watchdog) changes run behaviour and is group 2. Guard: `tests/test_streaming_through_the_agent_path_works.py` |
| U.2 KPI plumbing | P2 | DONE 2026-10-18 via W.4 | Corrected (W.5): `audit_live.py` counted replayed call ids and redundant reads only; the identical-call measure lived in `scripts/audit_run.py`, which the loop never ran. `run_timing.py` prints the cache share and per-tool error rates. W.4's `scripts/loop/kpi.py` now computes all of them per run (identical calls by `audit_run`'s definition), plus reverts, defects left open, closed-without-a-fixer and replies lost to length, into `data/kpi/`. Still not counted: vacuous-green detections and reclassifications (no transcript record yet) |
| U.4 retention policy | P2 | NOT BUILT 2026-10-18 (owner decision) | Deleting a run already removes transcript, ledger, journal and stored copies (`run_retention`). Automatic age-out would delete the owner's runs and the loop's evidence; offer it only if the owner asks |
| UI Phase 1 harm removal | P2 | MOSTLY DONE 2026-10-18 | Measured with `scripts/ui/axe_measure.mjs` on Home/Runs/Settings/run dashboard: axe violations 455 -> 5. Contrast tokens; live regions on the feed and log; focusable scroll regions; skip link; aria-current; focus-visible ring; reduced motion; keyboard dropzone; named Settings controls; heading order; row actions on focus-within; title + color-scheme + theme-color. Resilience: stale-while-error (a failed refresh keeps the last state with a notice), a reconnecting notice while the stream is down, a ticking elapsed clock, polling paused in hidden tabs (runs list, sprint summaries). Gates: tab title names the run's state ("Needs you" / Done / Failed); the run payload carries `gate_deadline` + `approval_timeout_minutes` and a waiting gate says when it approves itself or that it waits indefinitely. Dialogs: all 17 alert()/confirm() replaced by an accessible toast + confirm dialog (focus held, Escape, restore; destructive starts on Cancel); the artifact viewer is a real dialog. Validated against the audit: "218 unlabeled buttons" was wrong (they have text names). Open: browser Notifications (needs a user-granted permission control), favicon badge, inline artifact rendering in review gates, delete-undo |
| UI Phase 2 structural | P2 | PARTLY DONE 2026-10-18 (owner scope) | Owner scope: diff viewer, criteria panel, URL state first. Done: a Changes view of the run's workspace history (`GET /runs/{id}/changes`, `/changes/{sha}`, read-only git, hash-only argument; `server/changes.py`, `ChangesPanel.tsx`); each criterion in the delivery panel opens to its tests and first failure line; the dashboard's view and chosen change live in the URL (`?view=changes&change=<sha>`). Not yet: log virtualization, intake wizard |
| UI Phase 3 differentiators | P3 | STEERING DONE 2026-10-18 | Steering is built on the owner's instruction injection (`server/steering.py`: notes in the run's `.harness/steering.json`, `GET|POST /runs/{id}/steering`; `plugins/middleware.py` appends the newest 5 to every later call; `SteeringBox.tsx` on a live run). Owner scope keeps timeline next and drops PWA and i18n. Originally: Steering, timeline scrubbing, agent lanes, Insights panel, PWA, i18n/light theme. Validation (second review G7/G8): no steering endpoint exists (the instruction injection is per-stack framework guidance), and artifact revisions are hard-coded to 1 - both need backend enablers first |
| Part 4 backend enablers | P2/P3 | NOT STARTED | `completed_with_gaps` in payload (with J.4), gate-deadline timestamp + NULL-timeout stall alerting (amendment), steering endpoint, per-stage token rollups |
| U.1 bench corpus additions | P3 | DONE 2026-10-19 `6e98110` | `fullstack-bookmarks-py` (2026-10-18, `1ef5dd8`). The service-backed bench was to declare a database through K.2's `services:` contract, which K.2's decision (embedded database by default) never built; built instead as `benchmarks/tasks-api`: accounts, a sign-in token, items per person, persistence across a restart, and a service started from `PORT` and `DATA_DIR` alone - the class run-846b8d62 failed on (a required secret, tables never created). 10 hidden tests (pytest + httpx); a standard-library reference scores 10/10, checked by the suite. KPI side: the KPI JSON gains `tool_failure_rate_by_tool`; the rest of the list (identical calls per stage, cache share, lost replies and their output, reverts, closed without a fixer, prefill:decode) was already there. Tests: `tests/test_the_tasks_api_bench_reference_scores_full.py` (fail on the old code). Group 1 |
| U.3 A/B wiring | P3 | DONE 2026-10-18 (`3d8789f`) | `kpi_ledger.py compare A.json B.json`: every KPI of two runs with the change. Not wired into `evaluation/evaluate.py` datasets: the loop's A/B is run-vs-run |
| V layer-economics ledger | P3 | MEASURING since 2026-10-18 (`3d8789f`) | `kpi.py` counts each guard layer's interventions per run (memory pointers, read refusals/hold-backs, edit repairs, unchanged writes, diagnostics, command refusals, and tools withheld - from the requests' tool lists). Medium run: 495 pointers, 93 withholdings, 85 held-back reads. Keep-or-delete verdicts need A/B runs (the switches exist since W.3) |
| K.2 services provisioning | P3 | OPTION A DONE 2026-10-18 (owner: embedded first) | The environment contract every stage gets now says a product that stores data runs on an embedded database by default, in a file under `DATA_DIR` (the acceptance server gets a fresh one per run), with the brief's server kept as the production target behind one connection setting. No compose change; a Postgres service (option b) only when a brief demands it, and with the owner's yes. Originally: **Antigravity constraint**: prefer embedded/in-process adapters or one persistent shared service with per-run schema isolation over dynamic per-run sidecars |

Committed plan artifacts: appendix + addenda + this ledger live in
`docs/improvement-plan.md`; the evidence archive is `docs/review-findings.md`;
the frontier research report is `.langchain/research/frontier-harness-report.md`
(git-ignored, local only).

---

<a id="plan-appendix-2"></a>
## Appendix 2 (2026-10-18, second review session): Measurement-first hardening, local-model interface quality, throughput, release-integrity residuals, UI/UX

> **Status tracking**: new rows for every item below are appended to the
> [Implementation Progress Ledger](#implementation-progress-ledger) in the
> "Appendix 2 rows" block at the end of this document. Same rules as before:
> a DONE row carries its date and names the test that fails on the old code.

**Method and evidence base.** This appendix is a *further* pass over the
harness after the Appendix 1 P0/P1 wave landed (ledger rows dated
2026-10-18). It does not restate Initiatives A–V. Evidence: a fresh read of
the codebase at `3fcd36d`/`3435fb0` (four cheap-model inventories covering
agents/models, graph/acceptance/tools, UI+API, run history/packs/loop
scripts, each verified by hand where cited); the run record as the docs
carry it (no transcripts were reachable from the review sandbox — see
`docs/review-findings.md` §13 for the per-finding ledger G1–G27); the
external reviewer's report (formerly `docs/logs.md`, removed 2026-10-19; summarised in Part 22.4); and a fresh web-research pass
on frontier harnesses, local-model serving and agent UI/UX (primary sources
dated 2025-06 → 2026-10; summarised in `docs/research-findings.md` Part R2 (§13.6)).
Findings are cited as **G-numbers**; research items as **R-numbers**.

**What the research adds to Appendix 1's consensus.** Since the first pass,
the frontier harnesses have published the shape of their long-running loops
in detail, and it is simpler than this harness: *one writer, many advisors*.
Anthropic's long-running-agent harness is an initializer that writes a JSON
feature list with every feature `passes: false`, then one feature per fresh
context, tests first, commit, progress log (R1, Nov 2025); its later
planner/generator/evaluator harness negotiates "sprint contracts" of
testable criteria and has the evaluator *drive the running app* (R2, Mar
2026). Cognition's 2026 follow-up to "Don't build multi-agents" reports
that multi-agent *writing* is still fragile, multi-agent *reviewing* works
(a clean-context reviewer catches ~2 bugs/PR even on Devin's own work), and
that a weak primary model with a strong advisor fails because "the quality
ceiling was set by the primary" (R3). MAST measured ChatDev at 33% correct
and attributed 42% of multi-agent failures to specification/design and 21%
to verification (R4). For local models the research is blunt that failures
are *interface* failures — tool-call format, edit format, context
truncation, quantization — more than reasoning failures: INT4 doubled
out-of-list tool-call names (19.5%→38.3%) while benchmark scores stayed
flat (R5); Ollama's VRAM-based default context silently truncates (R6);
Cline keeps native tool calling off for non-frontier families and local
users loop on format mismatches (R7); Aider defaults unknown models to
whole-file edits because it is the easiest format to comply with (R8);
JetBrains found LLM summarisation *lengthened* trajectories 13–15% vs
observation masking, which halves cost at equal solve rate (R9).

This harness already has the artifacts (intake → spec → work orders →
locked suite → sprint record) and the single-writer work orders. The gaps
this appendix closes are: it still lets the model's word stand in for a
measurement at one critical point (G19); its prompts and tool schemas
disagree (G1/G21/G22); its prefix-cache layout is inverted (G2); its
parallelism is nominal (G23); and — the governing problem — nothing after
the P0 wave has been *scored*, and the one quality inference the earlier
plan leaned on (local fixes/reviews are the weak link) rests partly on a
brief/suite mismatch (G12/G13). So this appendix is ordered
measurement-first.

---

<a id="plan-part-6"></a>
### Part 6 — Measurement first (P0): nothing else in this appendix can be verified without it

<a id="plan-w"></a>
#### Initiative W: Score the harness as it is now, and make every later claim falsifiable
- **Reasoning**: The P0/P1 wave shipped ~18 behaviour changes on
  2026-10-18; the only run after them (run-8b0c94df) has no recorded brief,
  mode, model, duration or outcome, and K.3-ext/L.1-refinement were written
  *because* of it (G13). The medium brief has 0 completions in 9 attempts;
  the hard brief has never run; the stage-2 bench gate has no result. The
  earlier hidden-score evidence is confounded: brief_low runs were scored
  against the web-todo hidden suite, whose tests need `## Interface` labels
  that only `benchmarks/web-todo/brief.md` contains — the one run given the
  real brief scored 10/10 (G12). And every "A/B-verified" clause in
  Appendix 1 is unexecutable because `docker-compose.yml`'s `x-app-env`
  does not pass the toggles (`LINE_EDITS`, `ENVIRONMENT_CONTRACT`,
  `WORKSPACE_DIGEST`, `PROJECT_MEMORY`, `HARNESS_TASK_LIST`, `JUDGEMENT_*`,
  `ESCALATE_AFTER_ATTEMPTS`, `MODEL_MAX_OUTPUT_TOKENS`) (G14). U.2's ledger
  entry over-reports: the identical-call measure lives in
  `scripts/audit_run.py`, which `loop.sh` never calls (G15).
- **Mechanism**:
  1. **Bench-brief integrity rule**: a run is scored against a hidden
     suite only if it was started from that benchmark's own brief; any
     other pairing is exported with `brief_mismatch: true` and excluded
     from false-acceptance statistics. Re-tag the three brief_low runs.
  2. **Post-P0 baseline**: one fast + one thorough run per stage-1 bench
     (web-todo, notes-api) on the real briefs with the current code, before
     any Appendix-2 behaviour change — the control every later item is
     measured against. (Owner-operated; AGENTS.md rules apply.)
  3. **Toggles through compose**: pass every harness flag listed in
     `map-agents.md` §7 through `x-app-env` with `${VAR:-default}`; unify
     `SANDBOX_MEMORY_LIMIT` (4g/1g/2g today); default
     `MODEL_CONTEXT_WINDOW` from the server's `/props` when readable (S
     already reads it); default `HARNESS_MAX_PARALLEL` to the slot count.
  4. **Per-run KPI JSON + cross-run ledger**: `loop.sh score` writes one
     JSON per run with the U.2 KPIs *plus* the ones G15 found missing
     (identical-call rate from `audit_run.py` wired into the loop,
     reasoning-exhaustion events by *reply shape* since the owner's server
     reports no reasoning tokens, stale dispatches, reverts, reclassifications,
     vacuous-green detections, prefill:decode ratio, cached-token share, edit
     well-formedness per tool, out-of-list tool-name rate); a
     `data/kpi/ledger.csv` accumulates them; `audit_live.py` flags any
     stage >1.5× its 5-run moving average (the old plan's Tier-3 #7).
  5. **Ledger honesty**: add rows for pre-ledger Initiatives A–I with their
     real status (G: in code; C `ui_contract`: no trace; etc.) and correct
     the U.2 row.
- **Frontier validation**: Terminal-Bench/Harbor and the SWE-bench
  "mini-roulette" result exist because scores are harness-specific; the
  research's #20 recommendation is "select and measure on your own harness
  with mini-SWE-agent as control" (R10). OpenHands keeps an event-sourced,
  replayable log precisely so condensation and routing changes can be
  evaluated after the fact (R11).
- **Impact**: Turns the rest of this appendix from opinion into
  experiments; also fixes the one piece of evidence the earlier plan
  over-read. **Effort**: S–M (compose: S; KPI JSON: M; baseline runs: owner
  wall-clock).

---

<a id="plan-part-7"></a>
### Part 7 — Local-model interface quality (P0/P1)

<a id="plan-x"></a>
#### Initiative X: Prompt-contract integrity — what the prompt names, the schema must offer; what the code does, the prompt must say
- **Reasoning**: The harness's largest format-waste class (A3: `edit_file`
  ×53, tools named after file paths) has a prompt-side cause that Appendix 1
  did not find: read-only roles are *told* to call `write_artifact` while
  `can_write=False` removes it from their tools (`product_manager.py:352-360`
  vs `:391`; `tools_models.py:322-333` vs `:363`); the specialist prompt says
  "ONE single write_artifact call, no follow-up edits" while `_WRITING_RULES`
  teaches `edit_artifact`; ui_ux is told both "do not run tests" and "prove
  your work by running it" (G1). The milestone-review schema tells the model
  `blocked` ends the run while the workflow re-plans on it (G21). The
  `run_terminal_command` description claims network-off for everything but
  installs, which is false in container mode (G22). Prompts also carry
  maintenance prose ("Measured across the stored runs…", ALL-CAPS/CRITICAL)
  that costs tokens on every call and is exactly the style the small-model
  research says to avoid (G5). A weak model follows the prompt; when the
  prompt and the schema disagree, the hallucinated tool name is the model
  doing as it was told.
- **Mechanism** (all deterministic, all testable):
  1. **Tool-name/offer test**: a suite test that every tool name mentioned
     in any role's rendered system prompt is in that role's offered tool
     set (same shape as the banned-words tests); fix the four instances now.
  2. **Verdict-semantics test**: each structured-output enum value's
     description must match a routing table the graph exports (the
     `blocked` case first).
  3. **Mode-rendered tool descriptions**: tool text that states a policy
     (network, cwd, venv) is rendered from the active sandbox mode, never a
     constant.
  4. **Prompt diet**: move "why" prose to module docstrings (where this
     codebase already keeps it well), keep rules imperative and short, one
     example per format; budget each role's static prompt (chars) in the
     KPI JSON so growth is visible. Target: no role prompt above ~6k chars
     without a measured reason.
- **Frontier validation**: "remove tools instead of forbidding them" is a
  top-20 research recommendation (plan mode exposes read-only tools only,
  R12); Cline's "Compact Prompt" is its maintainers' recommendation for
  local models (R7); hooks-over-prompts for invariants because small-model
  prompt compliance is weaker (R13).
- **Impact**: removes a *cause* of A3 rather than another repair layer; the
  prompt diet is the cheapest prefill cut available. **Effort**: S.

<a id="plan-m-concrete"></a>
#### Initiative M (made concrete): the model-profile contract, step by step
Appendix 1's M is NOT STARTED and is still the highest-leverage local-model
item. Concrete scope, ordered so each step is independently shippable:
  1. **Probe-time capability detection** (extend the existing fitness/window
     probes; `models/fitness.py` is currently unwired — G3): one forced
     trivial tool call (does it parse natively?), one `response_format:
     json_schema` request (does the server honour schema-constrained
     decoding? llama.cpp converts JSON Schema→GBNF; vLLM/SGLang have
     guided decoding — R14), one `cached_tokens`/`timings.cache_n` read
     (does the server report prefix-cache hits?), effective context vs
     configured (Ollama's VRAM-based default is the #1 silent local failure
     — R6). Record all four in the run's profile and in `loop.sh ready`.
  2. **Control-plane enforcement where the probe says yes**: send the
     response schema as `response_format` (json_schema) for the answer tool
     of every *structured* stage (intake, spec sections, plan, reports,
     review verdicts, finish signal) — never for file bodies (O.1
     amendment stands). Where the probe says no, keep the forced-tool
     strategy + the existing repair ladder. This retires the 59× one-char
     truncation class (`settled_answer._repair_json`) at the source on
     servers that support it.
  3. **Sampling presets per family** sent per request (`temperature`,
     `top_p`, `top_k`, `presence_penalty`, `seed` for reproducible
     benchmarking) — today nothing is sent (G3), so behaviour depends on
     server launch flags. Model-card values live in profile data.
  4. **Reasoning policy per family and role** (N.1's prerequisite):
     parameter name + budget + history policy (strip/keep) in the profile;
     N.1 ships when the probe shows the owner's server honours a budget.
  5. **Arg-fit/hallucination map as profile data** (unchanged from
     Appendix 1).
  6. **Quantization advisory** (new, R5): the profile records the served
     quant when the server exposes it (llama.cpp `/props`); `loop.sh
     ready` warns when the *tool-calling* model is ≤4-bit (research: INT4
     doubles out-of-list tool names while scores stay flat; community
     reports of Q4 Qwen3.6 breaking tool JSON/diffs past ~30k context) and
     the KPI JSON tracks the out-of-list tool-name rate so the owner can
     see the effect on their own hardware. Advisory only — the model is the
     owner's.
- **Effort**: M total; steps 1–3 are each S–M and can land one at a time.

<a id="plan-y"></a>
#### Initiative Y: Edit-ACI calibration — pick the edit format per model from a replay bench, not by argument
- **Reasoning**: Appendix 1 demoted `replace_lines` (P.1, 62% failure) and
  kept `edit_artifact` + whole-file rewrite; the repair chain in
  `tools/repository.py` records that of 330 failed edits, 294 were on a
  file the stage had *already read* — "reproducing bytes from context is
  the hard part" — and that transcription repair had reached its limit
  (7/75 on replay). So the remaining question is empirical per model: at
  what file size does whole-file beat SEARCH/REPLACE for *this* model at
  *this* quant? Aider answers it with a per-model edit-format table and a
  separately-reported well-formed-edit rate (R8); Devin's lesson was that a
  small model rewriting a whole file from a markdown explanation beat a
  large model emitting a diff (R15).
- **Mechanism**:
  1. **Replay corpus**: the transcript archive already holds every failed
     and successful edit with the file state; extract (file, intended
     change, model, outcome) into a fixture set (no run ids in code; the
     corpus is data under `benchmarks/edits/`).
  2. **Calibration run** per profile: well-formed rate and
     applied-correctly rate for whole-file vs SEARCH/REPLACE vs (optional)
     line-range, bucketed by file size; the profile records the crossover
     size and the harness picks the format per edit from it. Default for an
     unprofiled model: whole-file under the crossover, SEARCH/REPLACE above
     only once its well-formed rate is ≥95% (research #8).
  3. **Architect/editor split as a profile option**: the strong (judgement)
     model writes the change as prose + target lines; the local model
     applies it as a whole-file rewrite — Aider's `--architect` /
     `--editor-model` (R8). Bench-gated like everything else.
  4. **KPI**: well-formed-edit rate per tool per model is a first-class
     line in the KPI JSON (W.4).
- **Impact**: converts the biggest single tool-failure class into a
  measured, per-model setting; also the prerequisite for any claim about
  "local models can't edit". **Effort**: M.

<a id="plan-z"></a>
#### Initiative Z: Compaction that keeps state — mask first, summarise with a template, reset at boundaries
- **Reasoning**: Compaction today is deepagents' `SummarizationMiddleware`
  with the *run's own model* as summariser at 0.8×ceiling, args truncated
  first (`role_agent.py:385-411`), library default summary prompt. On a
  prefill-bound local server, summarising ~55k tokens is itself a long
  decode, and JetBrains measured LLM summarisation *lengthening*
  trajectories 13–15% versus simply masking old observations, which halved
  cost at equal solve rate (R9). OpenHands' condenser reports up to 2×
  per-turn cost reduction but is event-sourced and replayable (R11).
  Anthropic found context *resets* with handoff files necessary even for
  frontier models (R2); the Ralph loop's whole premise is fresh context per
  feature with state in files (R16). This harness already has fresh
  conversations per stage and work orders on disk — the pieces of a reset
  design — but compacts *within* a stage by summarising.
- **Mechanism**:
  1. **Observation masking before summarisation**: replace old tool
     *results* (not calls) with one-line stubs ("read src/app.js, 212
     lines, unchanged since") once they are older than N turns — the
     digest's "already known" block (R) supplies the facts. Summarise only
     when masking is not enough.
  2. **Structured summary template** when summarising: files touched,
     decisions, failing tests, open items, next step — written "for the
     model that resumes" (Codex framing, Appendix 1 O.4); re-inject the
     active work order + the N most recently modified paths after
     compaction.
  3. **Reset instead of compact** for build stages: when a specialist's
     context crosses the trigger mid-work-order, end the stage with a
     handoff note (same shape as 2) and restart it on a fresh conversation
     with the note — the harness's existing restart path, used
     deliberately. Profile knob; A/B against in-stage summarisation on the
     W baseline.
  4. **Summariser routing**: the compaction model is already a policy
     field; set it to the cheapest adequate model (Aider `--weak-model`,
     R8) rather than the build model by default.
- **Impact**: cuts the second-largest decode cost per stage and attacks
  context rot at its root; makes compaction events replayable in the KPI
  log. **Effort**: M. **Constraint (Antigravity, O.4) stands**: trigger
  stays 0.75–0.80; this initiative changes *what happens* at the trigger,
  not where it is.

---

<a id="plan-part-8"></a>
### Part 8 — Throughput without quality loss (P1)

<a id="plan-aa"></a>
#### Initiative AA: Prefix-cache layout — stable first, volatile last, measured every call
- **Reasoning**: Project memory is spliced into the *opening* human message
  and rewritten from disk on every call, up to 30% of the window
  (`project_memory.py:312-321`): any file write changes the first message,
  so the server's prefix cache misses for the whole history on the next
  call — and it pushes the brief itself behind ~30k tokens (G2). Meanwhile
  the byte-stable environment contract and the digest are appended *after*
  the growing history (`environment_contract.py:253`,
  `workspace_digest.py:526`), so the stable block is re-prefilled every
  turn. Mid-stage tool-list changes (settled-answer withholding,
  research-share cap) change the prefix too (G4). This is the inverse of
  O.3's rule, and it is the harness-controlled part of the 45–73% cache
  hit rate measured in Appendix 1. Nothing reads `cached_tokens` (G3).
- **Mechanism**:
  1. Layout: `[system prompt + tool schemas] [environment contract]
     [project memory snapshot, byte-stable for the stage] [brief/work
     order] … history … [digest + already-known block, volatile]`.
     Memory updates land in the digest tail during a stage and roll into
     the stable snapshot at the next stage boundary.
  2. Mask, don't remove: withholding sets a one-line instruction and
     returns a refusal from the tool; the schema list stays constant
     within a stage (Manus; R17).
  3. KPI: `cached_tokens` share per call and per stage in the KPI JSON
     (W.4), with the layout change A/B'd on the baseline.
- **Frontier validation**: "keep system prompt + tool schemas + rules
  byte-identical; put volatile content at the end" is the research's #13
  recommendation and Manus's stated most-important production metric (R17);
  Cline measured −15% tokens/request just from moving tool definitions into
  API parameters (R7).
- **Impact**: on a prefill-bound server with 31:1 input:output, a 20-point
  cache-hit gain is worth more wall-clock than any decode speed-up the
  owner could buy. **Effort**: S–M.

<a id="plan-ab"></a>
#### Initiative AB: Honest parallelism — fan-out equals server slots
- **Reasoning**: `HARNESS_MAX_PARALLEL=6` by default; a per-workspace command
  lock serialises every sandbox command (`sandbox.py:3732`);
  `fix_by_candidates` fires 3× the file count of concurrent model calls
  (`rewritten_fixes.py:278`); the owner's server has one slot. Measured
  overlap 1.0–1.3× (F10). Against one slot, fan-out is queueing plus
  KV-cache thrash from interleaved prefixes (G23).
- **Mechanism**: default `max_parallel` = slots from `/props` (S already
  reads it), cap candidate fan-out by the same number, and gate the
  parallel/linear toggle's *recommendation* in the UI on the measured
  slot count (the toggle itself stays — owner feature). Keep the
  per-workspace command lock (it is correct) but document it as the reason
  parallel mode cannot overlap sandbox work.
- **Frontier validation**: Cursor's 8-way parallel agents and Codex
  threads assume cloud concurrency; the research's adapt note is explicit
  that on a single local GPU best-of-N costs throughput and belongs only
  at the planning stage (R18). **Effort**: S.

<a id="plan-ac"></a>
#### Initiative AC: Deterministic gating of review/testing model calls, and check caching
- **Reasoning**: Thorough mode runs a judgement-model testing agent every
  round although the fast "harness round" gathers the same measurements;
  architecture and milestone reviews run when the harness found no
  breakage and the suite is green; `what_the_files_already_prove` (49
  checks) is recomputed several times per round with no cache (G24).
  Anthropic found its evaluator "unnecessary overhead" for tasks within the
  generator's ability (R2) — the inverse holds for local models (more
  lift), so the right move is not to drop reviews but to *gate* them on
  deterministic signals and cache the deterministic part.
- **Mechanism**: (1) test-round report built procedurally from JUnit (Q.2)
  in both modes; the model narrates only when the procedural queue is
  non-empty; (2) reviews run on a diff-since-last-accepted basis with
  skip-when-nothing-relevant-changed (verify the existing conditional
  security/advice skips are reached); (3) memoise whole-workspace checks
  on the workspace tree hash within a round. **Effort**: S–M.

---

<a id="plan-part-9"></a>
### Part 9 — Release-integrity residuals (P0/P1)

<a id="plan-ad"></a>
#### Initiative AD: Measure at settlement — the mirror of L.3
- **Reasoning**: `_settle_the_fix` (`workflow.py:8895-8960`) marks a defect
  fixed when the fixer names a test and no blocker; `verified_by` — what
  the execution ledger confirms ran and passed — is an info log that
  "does not gate the transition". `after_a_fix` reverts a fix that broke
  *other* tests, but nothing checks that the defect's *own* tests pass
  until the next round, which then counts it as another failed attempt.
  The rewrite fixers hard-code the regression-test string
  (`rewritten_fixes.py:207,306`) and `fix_by_candidates` keeps a candidate
  when the check could not run (`:296`) (G19). Yet `_the_defect_s_tests_pass`
  (`workflow.py:2615`) exists and L.3 runs it at dispatch. This is the last
  place in the loop where the model's self-report stands in for a
  measurement — and the research's single strongest multi-agent finding is
  that verification must check the *requirement*, not just "does it compile"
  (R4), with the evaluator separate from the generator (R2/R3).
- **Mechanism**: a defect closes only on a green `_the_defect_s_tests_pass`
  probe at settlement; a red probe records the attempt as failed
  immediately (saving a round); a probe that cannot answer keeps today's
  behaviour but is counted in the KPI JSON. `fix_by_candidates` treats
  "could not run" as not-passed. Keep the fixer's named test as narrative
  only. **Effort**: S. **Impact**: closes the self-report hole and
  shortens every treadmill by one round.

<a id="plan-ae"></a>
#### Initiative AE: One "cannot pass" list; gaps completeness; release re-checks
- `acceptance_nodes.py:376-401` (18 checks) vs `:1141-1153` (11): repaired
  tests re-enter through the shorter list, so a test only the long list
  catches can be locked and later charged to the product (G20) → one
  function, both call sites. `completion_gaps` never receives fast-mode
  findings recorded as risks, escalation `known_issues`, or defects
  accepted as risk, and release does not re-run compiler/dependency-drift/
  integration checks (G25) → add the three sources; run the deterministic
  checks once more at release and record them in the evidence page (J.5).
  **Effort**: S.

<a id="plan-af"></a>
#### Initiative AF: Suite-strength probe — mutation testing the locked suite
- **Reasoning** (external review item 2, Part 22.4; `agents/testability.py` docstring already
  argues it: "a mutation has to change what a function DOES"): criterion
  coverage is checked by `[AC-n]` tags in test names, which proves a label
  exists, not that the test fails when the behaviour is absent. A suite
  that cannot fail is the vacuous-green class J.1 could not see.
- **Mechanism**: at lock time, for a sample of criteria, apply one
  deterministic behavioural mutation to the product's pure logic (return
  first argument / invert a comparison / drop a branch — language-agnostic
  AST edits via the existing tree-sitter/language-service layer) and
  require at least one locked test to fail; a criterion whose tests survive
  every mutation is a suite defect routed to the acceptance author with the
  surviving mutant as evidence. Stack-specific mutation operators are pack
  data (K.6). **Effort**: M. **Impact**: the first *independent* measure of
  suite strength; feeds `completion_gaps` when sampling cannot run.

<a id="plan-ag"></a>
#### Initiative AG: Capability tiers at intake (the honest language-agnostic claim)
- 35 packs, but only two declare `entrypoints` for K.3; ten service packs
  have empty `check_families`; dependency-drift covers JS/TS+Python only;
  the compiler check is a silent no-op without a toolchain; no pack for
  Kotlin/Swift/Dart/Elixir/Scala/C++; the bench corpus is JS+Python (G16).
  Until K.6 lands, intake should classify the chosen stack as
  *pack-supported / custom (agents supply setup + test contract) /
  unverified*, show the tier on the run card and in the release evidence,
  and have the stack selector prefer a pack-supported stack when the brief
  allows (external review item 3, Part 22.4). Each pack's verification coverage becomes a
  one-line declared field so the UI can render it. **Effort**: S (tiering)
  + the K.6 work it motivates.

<a id="plan-ah"></a>
#### Initiative AH: Promises that match guarantees — cost cap, retention/deletion, reviewer completeness
(from the external review, items 4–6, Part 22.4; none covered by Appendix 1)
- **Cost cap**: `_budget_exceeded` compares only priced spend; unpriced
  calls do not count toward `MAX_RUN_COST_USD`. Label the cap "known spend
  only" in UI and run record, and offer an independent hard bound (max
  model calls / max tokens) that *is* enforced. **S**.
- **Retention/deletion contract**: `delete_run` removes uploads, workspace,
  checkpoints and events but not the transcript or the durable object-store
  copy of an upload; define what delete removes, what is retained for audit
  and for how long, and make transcripts part of it (extends U.4). **S–M**.
- **Reviewer completeness**: a configured judgement model that fails to
  build silently falls back to the default model; the security reviewer's
  source is capped at 24k chars without a completeness report. Record the
  downgrade as a completion gap, and have every review emit reviewed/skipped
  file lists. **S**.
- **Run-readiness check before model calls** (external review item 1, Part 22.4): `loop.sh ready`
  covers the model; add command-execution readiness (sandbox mode available,
  runtime reachable) and label a deployment with execution disabled as
  planning-only. **S**.

---

<a id="plan-part-10"></a>
### Part 10 — Cross-run learning (P2)

<a id="plan-ai"></a>
#### Initiative AI: Structured, provenance-tagged lesson store
- **Reasoning**: Cross-run memory was dropped once over prompt-injection
  risk; the only survivor is `scripts/loop/lessons.py`, a human-driven
  proposer. The old plan's Tier-1 #2 (deterministic distillation into pack
  knowledge) is still open. Every frontier harness now has some form of
  it: Claude Code auto-memory/CLAUDE.md, Codex AGENTS.md layering, OpenHands
  microagents, Cursor memories; Anthropic's guidance is plain markdown
  navigated with file tools (R19); the research recommends a `LESSONS.md`
  the reviewer appends to and the planner reads (R19).
- **Mechanism**: lessons are *schema-validated records*, not prose:
  `{stack, role, trigger (tool+error shape), rule (≤2 lines), evidence
  (count of runs), source: harness|operator}`; produced by `lessons.py`'s
  grouping (≥MIN_RUNS) and confirmed by a person or the judgement model;
  injected by the existing plugin middleware per stack and role, capped per
  stage, byte-stable (AA). Operator-authored rules carry provenance and can
  be disabled per run; nothing agent-written reaches a prompt without the
  confirmation step. **Effort**: M.

<a id="plan-aj"></a>
#### Initiative AJ: Test Subprocess Lifecycle & Async Connection Disposal — eliminate non-daemon thread hangs in unit test runners
- **Reasoning (given by Antigravity)**: When service unit tests utilize async databases or connection pools (such as `sqlite+aiosqlite:///:memory:` or async SQLAlchemy engines), background worker threads like `aiosqlite`'s `_connection_worker_thread` remain alive unless the engine is explicitly disposed (`await engine.dispose()`) or connection pooling is disabled (`poolclass=NullPool`). Because Python waits for all non-daemon threads to terminate during interpreter shutdown, a test run that completes in 0.25s hangs indefinitely at exit in `futex_do_wait`. Furthermore, scaffolded test runners (`scripts/unit-tests.mjs`) call `spawnSync` without an internal execution timeout. This forces the test runner to stall until the outer harness sandbox hits its maximum 300-second category timeout (`Command timed out after 300 seconds`), burning 5–10 minutes per defect attempt, triggering conversation budget exhaustion, and forcing fresh retries.
- **Empirical Evidence**:
  - `run-8b0c94df-eff4-47f2-82c8-0ad06b7c5285` (Medium Brief, Fast Mode):
    - At 12:20:41 UTC, testing specialist in `defect_fix_2_4` executed `.venv/bin/python -m pytest tests/test_auth.py -v --tb=short`. Pytest finished executing all tests in 0.25 seconds (`2 warnings, 7 errors in 0.25s`), but hung in `futex_do_wait` on thread `Thread-1 (_connection_worker_thread)` for 300 seconds until the sandbox timeout killed it at 12:25:41 UTC.
    - At 12:27:00 UTC, `npm test` running `scripts/unit-tests.mjs` spawned `.venv/bin/python -m pytest tests -q --junitxml=test-results/unit-service.xml`. Pytest wrote `test-results/unit-service.xml` completely in sub-second time, but `spawnSync` hung waiting for `.venv/bin/python` to exit due to the undisposed `_connection_worker_thread`.
- **Harness Mechanism**:
  1. **Subprocess Lifecycle in Unit Test Runner (LANDED `2f68304`)**: In `src/app/stacks/packs/_fullstack.py` (`UNIT_TESTS`), child runner processes are monitored and terminated (`SIGKILL` on child process group) once the JUnit XML report is settled and complete (`SETTLED_MS = 3000`). Verified with `tests/test_a_unit_runner_that_lingers_after_its_report_is_ended.py`.
  2. **Async Engine Teardown & NullPool Seeding**: While `2f68304` secures `npm test`, direct terminal invocations (`run_terminal_command`) by specialist agents still execute raw `.venv/bin/python -m pytest ...`, which still hangs on `threading._shutdown()` if worker threads linger. In Python stack packs (`_python.py`, `_fullstack.py`), configure `poolclass=NullPool` for SQLite test engines and seed a clean session teardown fixture:
     ```python
     @pytest_asyncio.fixture(scope="session", autouse=True)
     async def _cleanup_database_engines():
         yield
         # Dispose async engine connections so worker threads terminate immediately
     ```
  3. **Timeout Stdout Diagnostics**: When `run_terminal_command` encounters a category timeout (e.g. 300s), ensure captured stdout/stderr is returned prominently in the tool result (as done in `sandbox.py:4418-4422`) so agents do not hallucinate failure causes or guess wrong `read_command_output` references.
- **Impact**: Eliminates 300-second dead-wait intervals during both automated test rounds and manual specialist terminal invocations, turning test-cycle turnarounds from 5+ minutes into sub-second iterations.
- **Effort**: S.

---

<a id="plan-part-11"></a>
### Part 11 — UI/UX, second pass

**Corrections to Appendix 1 Part 4 (from the code, G7–G11):**
- "Mid-run steering via the existing dynamic-instruction-injection hook" —
  that hook is `plugins/middleware.py`, which injects *framework* guidance
  per stack; there is **no** user→run instruction path and the WebSocket is
  read-only. Steering needs a backend enabler: a per-run steering queue, a
  middleware that appends the operator's note as a trailing message at the
  next stage boundary (AA-compatible), and an event in the log so the
  timeline shows it (Copilot "mission control", R20).
- "Artifact versioning + diff viewer (artifacts already track revision)" —
  `server/runs.py:1704-1713` hard-codes `revision=1`. The real history is
  the workspace git log (every stage commits); expose per-path commits and
  diffs from it first.
- Concurrent commit `3435fb0` landed most of Phase 1's accessibility items
  (455→5 axe violations, `scripts/ui/axe_measure.mjs`). Still open from
  Phase 1: toast/dialog primitives (17 native `alert/confirm`), modal
  role/focus trap, title/favicon badges + browser Notifications,
  stale-while-error dashboard, WS→poll fallback, hidden-tab polling pause,
  log virtualization + buffer cap, `waiting_for_budget` styling,
  "Documents N produced" counting code files, dead code (`wizardData.ts`
  694 lines, `DynamicWorkflowUI.tsx`, `App.css`, template assets).
- API/UI contract drift to fix in one pass (G11): `document_names` vs
  `document_name`; `approval_timeout_minutes` absent from `RunStatusResponse`;
  token counts/`reviews[]`/`remediation` typed but unrendered;
  `delivery_mode`/`use_frontier_model`/`auto_approve` absent from the UI type;
  missed refetch on `budget_pause`/`approval_denied`/`review_decision`;
  stream never re-attached after `closed`; brownfield endpoints unreachable
  from the UI; `createRun`→`startRun` failure orphans a run; 60-min token
  with no refresh forces a reload mid-run. Add a generated TS client from
  the FastAPI OpenAPI schema so this class cannot recur.

**The design plan (what "great" looks like for this product).** The research
on professional developers and agents is consistent: they "control the
agents through planning and supervision", prefer collaboration over full
delegation, and the main cost of delegation is maintaining enough
understanding of work they did not write (R21). The UI's job is therefore
*legibility of plan, evidence and diff*, not a prettier spinner. Every
frontier product converges on the same six surfaces (R20): editable plan
approval, live step timeline, mid-run steering, per-file diff review, live
preview with versioned rollback, and ask-user notifications.

1. **Plan-first intake (Phase 2, revised)**: brief (free text *and*
   documents), capability tier shown as the stack is chosen (AG), ETA from
   the forecast, then the *intake and specification as an editable plan*
   with the acceptance criteria listed as the run's feature list
   (`passes: false` until the suite proves them — R1). Approval is of the
   plan, not of a form.
2. **Run page = timeline + evidence + preview**: left, a virtualized
   step timeline grouped by sprint/stage with the plain-English narration
   (keep `lib/activity.ts`; move its regexes behind a typed event schema
   so server format changes cannot break it silently); centre, the
   artifact/diff pane (per-file diff from workspace git, accept/reject at
   gates; Devin Review-style grouping and confidence labels — R20);
   right, the criteria list flipping to pass with the test that proved it,
   plus a live preview iframe of the acceptance server when the pack
   declares a page surface.
3. **Steering composer** (needs the enabler above): queue a note for the
   next stage; show it in the timeline; show what the model did with it.
4. **Gates that cannot be missed**: countdown from `approval_timeout_minutes`,
   "waits indefinitely" when NULL, title/favicon badge, browser
   Notification, one-tap approve from the run list and from a mobile-width
   layout (runs parked 12–13 h in `awaiting_approval` were observed).
5. **Cost/throughput cockpit**: spend (labelled "known spend"), model
   calls, cache-hit %, prefill:decode, reasoning-lost replies, per stage —
   straight from the KPI JSON (W.4) so the UI and the loop audit read the
   same numbers.
6. **Design system**: tokens (already started in `3435fb0`) → primitives
   (Button/Card/Badge/Tabs/Dialog-with-focus-trap/Toast/Disclosure) →
   light theme from the token layer → i18n extraction. Replace the 31 hex
   literals and 115 raw slate/white classes as each screen is touched.
7. **Resilience**: stale-while-error, reconnecting chip, WS→poll fallback,
   hidden-tab pause, buffer cap; token refresh; orphan-run cleanup on
   failed start.

Sequencing: contract drift + Phase-1 remainder (days) → design-system
primitives + run page (2–3 weeks) → plan-first intake + gates (1–2 weeks)
→ steering + preview + cockpit (needs enablers; 2–4 weeks).

---

<a id="plan-part-12"></a>
### Part 12 — Refactor evidence for Initiative V

`build_workflow_graph` is one 3,672-line closure registering 46 nodes,
string-routed through `_route_from_stage` on 35 of them;
`_review_the_milestone` (463 lines) repeats its revise-or-escalate branch
5×; `_run_gated_agent` (440) duplicates its failure block;
`_closed_if_an_earlier_fix_resolved_it` repeats its close block 4×; two
defect clusterers share scaffolding; `MAX_*` caps are read at import time;
`settled_answer.py` keeps process-wide failure globals that parallel stages
can read across (G6, G26). V's bounded refactor track should start with:
(1) the per-stage failure carrier (correctness under parallel mode),
(2) extracting the milestone-review and gated-agent branches into one
function each (suite-proven, no behaviour change), (3) moving node
registration to a table so routing is data. No rewrite; the external review
and Appendix 1 agree a broad rewrite before a working bench gate is the
wrong order.

---

<a id="plan-appendix-2-2"></a>
### Appendix 2 sequencing

| Priority | Items | Why |
|---|---|---|
| P0 | W (bench-brief rule, baseline runs, toggles via compose, KPI JSON), X (prompt-contract tests + four fixes), AD (measure at settlement), AE (one list; gaps sources) | Days each; W makes everything measurable, X/AD/AE close self-report and instruct-then-punish holes with deterministic code |
| P1 | M steps 1–3 (probe, control-plane schema, sampling), AA (cache layout + KPI), AB (parallel = slots), AC (gating + check cache), AH (honest cap/retention/completeness/readiness), AG (tiers), UI contract drift + Phase-1 remainder | Local-model interface quality and the throughput levers; mostly S–M |
| P2 | Y (edit calibration bench + architect/editor option), Z (mask-first compaction, reset at boundaries), M steps 4–6, AF (mutation probe), AI (lesson store), UI design system + run page | Need W's baseline to A/B; medium builds |
| P3 | UI plan-first intake, steering (with enabler), preview, cockpit; Part 12 refactor track; K.6/U.1 as before | Differentiators and long builds |

Cross-cutting rules unchanged: every mechanism at the contract/pack/profile
level; stack-specific data in packs/profiles/seed; every change with a test
that fails on the old code; no run ids in code or prompts.

### Research citations (R-numbers; full notes in `docs/research-findings.md` Part R2 (§13.6))
R1 Anthropic, "Effective harnesses for long-running agents" (2025-11-26) ·
R2 Anthropic, "Harness design for long-running apps" (≈2026-03-24) ·
R3 Cognition, "Multi-agents: what's actually working" (2026-04-22) and
"Don't build multi-agents" (2025-06-12) · R4 MAST, arXiv 2503.13657 ·
R5 "Flat score, amplified failures", arXiv 2607.27275 · R6 Ollama context
defaults (commit 0334ffa6, 2026-02) · R7 Cline v3.35 blog (2025-10-31),
issues #7424/#10843/#13008 · R8 aider edit-format leaderboard + HISTORY ·
R9 JetBrains Research, "The Complexity Trap", arXiv 2508.21433 ·
R10 mini-SWE-agent README; SWE-bench mini-roulette · R11 OpenHands
condenser docs; SDK paper arXiv 2511.03690 · R12 Claude Code best
practices (plan mode) · R13 Claude Code hooks reference · R14 vLLM tool
calling + structured outputs; llama.cpp function-calling.md (lazy
grammars, PR #9639) · R15 Cognition edit-apply lesson (2025-06-12) ·
R16 Huntley, Ralph loop (2025-07-14) · R17 Manus context engineering;
Anthropic "Effective context engineering" (2025-09-29) · R18 Cursor 2.0
changelog (2025-10-29) · R19 Anthropic memory-as-files guidance; research
rec. (f) · R20 Jules docs/changelog, Devin Review (2026-01-21), Copilot
mission control (2025-10-28), Lovable/Bolt/v0 version history ·
R21 Huang et al., arXiv 2512.14012 (2025-12-16); "The Work Behind
Delegation", arXiv 2609.24234.

<a id="plan-ledger-a2"></a>
### Appendix 2 rows (Implementation Progress Ledger continuation)

| Item | Priority | Status | Notes |
|---|---|---|---|
| W.1 bench-brief integrity rule | P0 | DONE 2026-10-18 (`a98d9ec`) | `loop.sh score` compares the run's uploaded document with `benchmarks/<name>/brief.md` by content; `score.py` exports `brief`/`brief_mismatch`; `report.py` counts mismatches apart. All 33 local exports re-tagged: the three brief_low runs (3642baf8, 866e972e, 94d2c449) and one notes-api run (992b132c) are `other` |
| W.2 post-P0 baseline runs | P0 | DONE 2026-10-19 (3 of 3 scored) | Owner-ordered. 1) fast notes-api-hono run-419b8ff6 (on `e608003`): 9/9 hidden tests (1.0), completed with 3 gaps, KPIs in `data/kpi/`; it was paused 14:25-14:27 JST by the owner, so read `active_minutes`. 2) fast fullstack-bookmarks-py run-c00868a9 (on `e608003`): **failed** 15:53 JST after 5 acceptance rounds ("no command is known for this suite": QA's `run.json` held a `commands` list; the custom setup was never proven - flat-layout install failure), 0/8 hidden tests (no `start.sh`), 80 min wall, reasoning 78% of output. 3) thorough notes-api-hono run-606ff231: completed 16:47 JST, 9/9 hidden tests, 11/11 locked, 46 min wall, 2 gaps (no unit tests; 1 of 3 deliberate changes unnoticed); sprint 1 accepted without new work because the setup stage wrote the product, so no review ran. KPIs in `data/kpi/`; the ledger flags `tool_failure_rate` 5.4% against baseline 1's 1.1% |
| W.3 toggles through compose + config unification | P0 | DONE 2026-10-18 (`54ab3bd`) except `/props` defaults | Six switches passed with empty defaults (no behaviour change; every read site treats empty as unset). JUDGEMENT_* and MODEL_MAX_OUTPUT_TOKENS left out on purpose: model settings and derived budgets are the settings page's (compose's own note). SANDBOX_MEMORY_LIMIT 1g everywhere. MODEL_CONTEXT_WINDOW / HARNESS_MAX_PARALLEL from `/props` moved to M.1 / AB, where the probe lives |
| W.4 per-run KPI JSON + cross-run ledger + regression flag | P0 | DONE 2026-10-18 (`bdc464c`) | `loop.sh kpi` (and every `score`): `data/kpi/<run>.json` + `data/kpi/ledger.csv`, regression flag at 1.5x the 5-run mean. Live run-8b0c94df: identical-call rate 23.9% (agrees with `audit_run.py`: 527/2190), 431 of them `read_file` - a lead for the next audit. The flag runs in `loop.sh`; `audit_live.py` itself is unchanged |
| W.5 ledger rows for Initiatives A–I; correct U.2 row | P0 | DONE 2026-10-18 | Rows below, each from a grep of the code; U.2 row corrected |
| A design tokens seeded by pack | pre-ledger | DONE 2026-10-18 (owner decision) | `stacks/packs/_design.py` `DESIGN_TOKENS`: an accessible colour set (AA contrast, tested, light and dark), spacing and type scales, and a visible focus ring, as CSS custom properties. Every web pack's stylesheet starts with it; the product may change the values. Test: `test_every_web_product_starts_with_design_tokens.py` |
| B procedural visual/layout audits | pre-ledger | DONE 2026-10-19 `864bdd6` | The suite's runtime report measures phone-width overflow (`phone_overflow`) and axe accessibility (`_read_accessibility`). Finished 2026-10-19: the page check also measures, at 375px, controls drawn over each other (a quarter of the smaller one covered) and controls under 24x24px (WCAG 2.5.8; a link in running text exempt), prints them in the suite's output where the agents read it, and keeps them on the result (`overlaps`, `small_targets`). Feedback, not new defects. Tests: `tests/test_the_page_check_measures_overlaps_and_small_targets.py` (a real headless browser measures a page with two overlapping controls and a 16px one; the whole rendered script must parse) - fail on the old code. Group 1 |
| C contract-strict interface extraction | pre-ledger | DONE 2026-10-18 | `TechnicalSpecificationOutput.interface_contract`: strict lines, one per route (`AC-3 GET /api/notes -> 200`), page control (`AC-1 page /login textbox "Email"`) or command (`AC-5 command notes add milk -> exit 0`), in a fast spec part and the spec document. The acceptance author is shown it and told to use exactly those paths and names; `record_at_lock` keeps it beside the locked suite |
| D pre-execution linter / assertion normalizer | pre-ledger | DONE in substance | Parse checks at the write (`javascript_parse`, `typescript_parse`, pack hooks); `suite.assertions_that_do_not_exist` at review and every round |
| E narrow single-file work orders | pre-ledger | DONE 2026-10-18 (owner decision), MEASURE over 2 runs | A soft cap, not one file: `drafting.in_work_orders_of_at_most` splits a fast work order of more than 3 files (`MOST_FILES_PER_WORK_ORDER`) into parts of 3 with the same owner and contract; the worker logs each split. Fast also keeps up to 5 of the lead's test files when the file plan names none (`MOST_UNPLANNED_TEST_FILES`, owner decision) |
| F root-crash / load-error gate | pre-ledger | DONE | One whole-product defect for a product that reports errors as it loads; L.1 whole-product layers (`_WHOLE_PRODUCT_LAYERS`) |
| G lenient whitespace in `edit_artifact` | pre-ledger | DONE 2026-10-19 `f7dc835` | 4 of 280 'Could not find that text' misses carried a curly quote/dash/NBSP. Unicode half built 2026-10-19 (Part 21 stage 8): after the whitespace and transcription repairs fail, `_typography_insensitive_span` maps curly quotes, dashes, box-drawing rules and non-breaking spaces one character for one, so positions stay the file's; a passage found exactly once is applied with a note saying which characters differed. A box-drawing run of a different length is still a miss (no 1:1 mapping). Test `tests/test_an_edit_differing_only_in_typography_is_applied.py` (2 of 4 fail on the old code) |
| H pre-flight verification before a fixer | pre-ledger | DONE | L.3: `_the_defect_s_tests_pass` at dispatch, "closed without a fixer" |
| I reasoning budget governor | pre-ledger | DONE | A reply spent on reasoning switches thinking off for the next reply; N.2 counts the lost replies across visits |
| X.1 tool-name/offer test + four prompt fixes | P0 | DONE 2026-10-18 (`5c74429`) | `tests/test_prompt_names_only_offered_tools.py` builds every role agent (all 15 factories, specialists/advice per role) and checks each tool its final prompt names is offered: found exactly product_manager and tools_models_architect (`write_artifact` with `can_write=False`). Specialists: the leftover one-document "no follow-up edits" rule removed (they are taught `edit_artifact`). ui_ux: "do not run tests" replaced by "do not write or change test files; running the tests that check your work is how you prove it" - it now owns page-file defects (K.3), so it must run the failing test |
| X.2 verdict-semantics test (`blocked`) | P0 | DONE 2026-10-18 (`3af2de9`) | Validated: since the owner's sprint re-run (`baf753d`) `blocked` records the sprint failed and the Technical Lead plans it again; the schema and its refusal still said "the run ENDS HERE". `milestone_reviewer.BLOCKED_MEANS` feeds both texts; `workflow.MILESTONE_REVIEW_NEXT_STAGE` routes it; a test holds them together |
| X.3 mode-rendered tool descriptions | P1 | DONE 2026-10-18 (`9aaaaf4`) | The command tool's network sentence is rendered from the sandbox mode; it claimed networking disabled in container mode, which the deployment uses |
| X.4 prompt diet + prompt-size KPI | P1 | DONE 2026-10-18 (`8cacab9`), partly | Evidence prose moved to comments; per-role ceilings in `test_no_role_s_prompt_grows_unseen.py` (specialists ~12.7k, not cut to 6k: byte-stable and cached, and a rewrite risks behaviour no test sees). Found on the way: a scaffolded project's prompt now names its served files instead of the generic 'backend/ frontend/ per tier' - the cause of the medium run's duplicate tree |
| M.1 probe-time capability detection | P1 | DONE 2026-10-18 (`adcc719`), narrowed | `models/server_profile.py`: one `/props` GET per run segment in the worker (no model call): slots, per-slot context, quantisation. Bounds the window (O.2) and each fan-out wave (AB); `loop.sh ready` prints it and warns at <=4-bit. Not built: the forced-tool and json_schema model-call probes (see M.2); cache reporting was already measured (`cache_read`, 72% on the medium run) |
| M.2 control-plane `response_format` where supported | P1 | DROPPED 2026-10-18 (premise false here) | Measured: ~55 structured answers on the medium run, none failed to parse; the "59x truncation" was a JSON *file* write, not an answer. llama.cpp already grammar-constrains a forced tool call (the 3 'peg-native format' errors are that grammar). `response_format` with tools present would also suppress tool calls. Revisit only on a server without grammar-forced tool calls |
| M.3 sampling presets per family | P1 | DROPPED 2026-10-18 (owner rule) | Sampling values are the launch flags of the owner's server; sending per-request overrides changes the owner's model settings |
| O.1 (amended) spec excerpt keeps every section | P1 | DONE 2026-10-18 (`b04b688`) | `text_budget.excerpt` and the architect's revision excerpt share the budget evenly across sections (measured: ~106k-char specs cut to 75k lost their last ~31k whole on every judgement stage). Per-role section selection not built: the judgement stages need the whole spec |
| O.2 effective context ceiling | P1 | DONE 2026-10-18 (`adcc719`) | Window = min(setting, server's per-slot context). Measured: ~45 'Context size has been exceeded' at 20-48k input under a 100k setting, in parallel waves |
| O.3 / AA prefix-cache layout | P1 | DONE 2026-10-18 (`d2c48b2`, `58f3bfa`) | Project memory taken once per stage visit, byte-stable; changes named in a note at the end. Environment contract in the system prompt. AA.2 (mask, don't remove tools) NOT built: measured, refusals did not stop reading loops and removal did (`test_the_read_tool_is_taken_away.py`). AA.3 cache share already in W.4's KPI |
| O.4 / Z compaction | P1 | NOT BUILT 2026-10-18 (measured) | Compaction ~never fires: no summary in the last 10 runs; the largest request per run 73-101k against an 80k trigger. Masking old results would break the prefix cache O.3 stabilised; one local model, so no cheaper summariser. Revisit if KPI shows compaction |
| AB fan-out = server slots | P1 | DONE 2026-10-18 (`adcc719`) | `concurrent_requests()` = min(HARNESS_MAX_PARALLEL, slots) sizes each wave; whether to fan out stays the owner's mode |
| M.4–M.6 reasoning policy, arg-fit map, quant advisory | P2 | DONE 2026-10-19 `0015cd1` for M.5/M.6; M.4 measured, any change is group 2 | The out-of-list tool-name KPI exists (`unknown_tool_name_rate`); M.6 shows as an advisory on `loop.sh ready`. M.5 (2026-10-19): tool names models learned elsewhere are registry data (`registry.TOOL_ALIASES`: `edit_file`, `str_replace`, `create_file` with their argument names), taken as the offered tool only when it is offered and given all it requires - `edit_file` was refused 209 times in four stored runs; a failed fitness probe names the server setting the family needs (its parser; `--jinja` / `--tool-call-parser`). M.4: AR measured that the server honours only thinking on/off; fast build stages already run with it off, and a per-role policy change is a behaviour change for group 2. Tests: `tests/test_a_tool_known_by_another_name_is_taken_as_the_one_offered.py` (2 of 3 fail on the old code) |
| Y edit-ACI calibration bench + architect/editor option | P1 | MEASURED 2026-10-18, no change | Across all transcripts: 5,556 edits, 21.7% refused - mostly the guards working (unparseable code, another work order's file); rewrites get a diagnostic note 15-17% regardless of file size, so no size crossover to calibrate. Architect/editor needs a second model; local-only runs have one |
| AC deterministic gating of reviews/test agent; check memoisation | P1 | DONE in substance / AC.3 DROPPED (measured 2026-10-18) | AC.1 = Q.2; the round's agent is already skipped when the suite and unit tests pass or a file-by-file diagnosis stands. AC.3: `what_the_files_already_prove` takes 0.9 s on the medium run's workspace, at most 3x a round - not worth a cache. The non-model time (~130 min) is the harness's real test runs |
| AD measure at settlement | P0 | DONE 2026-10-18 (`e8593db`) | Redesigned to cost nothing: `after_a_fix` has just run both suites, so `_the_defect_s_tests_in` reads the defect's own tests (criteria tags, else unit) from that snapshot, by its label; red leaves it open and counts the attempt now, a snapshot from another moment keeps today's behaviour. `_settle_the_fix` lifted to module level (tested). `fix_by_candidates` half dropped: a candidate kept with nothing to check it is measured at settlement anyway |
| AE one cannot-pass list; gaps sources; release re-checks | P0 | DONE 2026-10-18 (`d3962eb`, `372ff53`) | G20 premise corrected: repairs re-enter through the review, but a review that spent its rounds locks with problems open. `suite.tests_that_cannot_pass` is the one list (round gained unstated-order, contradicting locator, module mismatch, unawaited helper); too-lenient checks stay review-only. Gaps: escalation `known_issues`, fast-mode `RECORDED_AS_RISKS` decisions, and a release re-read with `problems_that_break_the_product`. Dropped: accepted-risk defects (`accept_risk` has no caller); compiler/dependency-drift re-run (no whole-project check exists; the suites cover the build) |
| AF mutation probe for suite strength | P2 | DONE 2026-10-18 (redesigned) | Premise corrected: the suite is locked against the scaffold, before the build, so every test fails at lock and no break could be noticed. The probe runs at release instead (`acceptance/mutation.what_the_suite_does_not_notice`): up to 3 textual breaks of the product's own source (owner's budget), suites that drive no browser only, each file put back. An unnoticed break is a completion gap. `scripts/bench/mutate.py` shares the core for the loop's offline score. Operators as pack data waits for K.6 |
| AG capability tiers at intake + per-pack coverage field | P1 | DONE in substance 2026-10-18 (`115282c`) | `support_tier` was already stated in the stack decision; now on the review and release evidence page too. Deliberately not a completion gap: a custom stack with a proven setup and passing suite is a real completion (an unproven setup is already a gap). Per-pack coverage field not added |
| AH.1 honest cost cap + independent hard bound | P1 | DONE 2026-10-18 (`f227a69`) | Partial-total labelling and refusal-at-start for unpriced models already existed; added `MAX_RUN_TOKENS`, counting every call priced or not, pausing at a stage boundary |
| AH.2 retention/deletion contract incl. transcripts | P1 | ALREADY DONE (premise stale) | `run_retention.purge_run_records` removes transcript, ledger, journal and object-store copies; `RUN_DELETE_KEEPS_RECORDS` keeps the audit trail |
| AH.3 reviewer completeness + judgement-model downgrade as gap | P1 | DONE 2026-10-18 (`5c0ba55`) | A judgement model that could not be built is a completion gap. The security reviewer already lists the files its budget left out and is told to open each |
| AH.4 execution-readiness check in `loop.sh ready` / run start | P1 | DONE 2026-10-18 (`6dccea0`) | Run start already refused a worker that cannot run commands; `loop.sh ready` now prints `READY commands (...)` and counts it toward ALL READY |
| AI structured lesson store | P2 | DONE 2026-10-18 (owner approves) | `plugins/lessons.py`: records {id, stack, role, trigger, rule (2 lines, 300 chars, no banned words), evidence_runs, source, status} in `$DATA_DIR/lessons.json`. Only `approved` lessons reach a prompt, appended to the stack's instructions by `plugins/registry.py`, 5 a call, in id order (byte-stable). `scripts/loop/lessons.py list|propose|approve|reject` in the worker; the loop lists new proposals in each run's report for the owner. Role-scoped injection not yet: the plugin middleware knows the stack, not the role |
| AJ test subprocess lifecycle & async engine cleanup | P1 | ITEM 1 DONE 2026-10-18 (`2f68304`, `4abd460`) | The kept runner ends a runner whose report is complete and the sandbox ends a test run that printed its summary and did not exit. Open: fixture seeding that disposes an async engine, and stdout diagnostics on a timeout (AV) |
| Part 12 refactor track (V) | P3 | NOT STARTED | Per-stage failure carrier first (parallel-mode correctness) |

> **Appendix 2 note (18:15 JST)**: commits `a35cce9` and `72d2cf9` (another
> session, same day) closed more of the Part 11 "still open" list — toasts
> and dialogs replace `alert/confirm`, a waiting gate shows its
> self-approval time, the tab title names the run state, polling pauses in
> hidden tabs, the run page keeps its last state on a failed refresh and
> shows a reconnecting indicator, and the clock ticks. Remaining from that
> list: title/favicon badge + browser Notifications, WS→poll fallback, log
> virtualization + buffer cap, `waiting_for_budget` styling, "Documents N
> produced" count, dead-code deletion, modal focus trap (verify), and the
> API/UI contract drift items. Ledger row "UI contract drift + Phase-1
> remainder" is scoped to that remainder.

### Owner decisions 2026-10-18 (20:55 JST): every recommendation accepted

1. Fast keeps up to 5 of the lead's test files when the plan names none: done.
2. Model time between runs for measurement work (AF, T, A/B): up to about an hour, only when no run waits and never during an owner run.
3. K.2: an embedded database first (no compose change); a Postgres service in compose only when a brief demands it, and with the owner's yes.
4. C + J.3: a formal interface contract, locked like the suite; a failed release check is a completion gap for the first 2 runs, then a blocker if accurate.
5. AI: the owner approves each lesson from a short list after each run; nothing agent-written reaches a prompt unapproved.
6. UI: diff viewer, criteria panel and URL state first, then steering built on the existing instruction injection; no PWA or i18n.
7. A: design tokens in every web pack: done.
8. E: a soft cap of 3 files per fast work order, measured over 2 runs: done.
9. W.2: after the current run, Fast notes-api-hono then fast fullstack-bookmarks-py on the same code; Thorough after.
10. K.6: after the W.2 baselines.
11. AF budget: about 3 sampled criteria at release (not at lock: the suite locks before the build), logic breaks the unit tests check in seconds, no browser runs.
12. M.3 (sampling) stays dropped; U.4 (automatic deletion) stays unbuilt.

---

<a id="plan-appendix-3"></a>
## Appendix 3 (2026-10-18, third review session): Review of the day's implementations, remaining gaps, and the UI/UX revamp with a multi-theme design system

> **Status tracking**: rows for every item below are in the "Appendix 3
> rows" block at the end. Evidence ledger: `docs/review-findings.md`
> §14 (findings H1–H33, each with file:line; ✓ marks what this session
> verified by reading the code). The live Docker app could not be reached
> from the review session (no shell/file bridge; the Chrome extension was
> not connected), so UI findings are from the code; 15.7 lists the
> screenshot pass that should confirm them.

**Where the harness stands tonight.** Between 18:30 and 23:00 JST the driver
session implemented most of Appendix 2 and all twelve owner decisions (119
files, +5.5k lines, each with a test), and dropped several items on
measurement with reasons recorded in the ledger (M.2, M.3, Z/O.4, Y, AA.2,
AC.3). That is the right behaviour of the loop. Two things follow for this
appendix: first, **none of the ~25 changes has run on a product yet** (H9),
so W.2's baseline is still the gate and every item below is a hypothesis
with its measurement named; second, a same-day code review of the
implementations found three high-severity defects and ~15 medium ones
(H16–H33) — the kind a suite of focused unit tests does not catch because
they are *lifecycle* and *interaction* bugs (process restarts, crashes
mid-probe, two middlewares writing the same digest). Part 13 is those fixes,
ranked; Part 14 is the remaining harness gaps; Part 15 is the UI/UX revamp
the owner asked for, with the multi-theme design system; Part 16 is the
detailed implementation sequence.

**Format of every item below** (the owner asked for a *detailed*
implementation plan): Goal → Evidence → Files → Steps → Tests (the
failing-first test, named) → Acceptance (how the loop knows it worked) →
Effort → Depends on.

---

<a id="plan-part-13"></a>
### Part 13 — Fix what today built (P0 before the W.2 baseline, so the baseline measures the intended code)

<a id="plan-ak"></a>
#### Initiative AK: Run-wide budgets survive the process — `MAX_RUN_TOKENS` / `MAX_RUN_COST_USD`  **[DONE 2026-10-19]**
- **Goal**: a token or cost ceiling bounds the *run*, not the current worker
  segment.
- **Evidence (H16 ✓)**: `observability/cost_tracker.py:195-215` keeps
  `_RUN_COSTS` in process memory; `server/runner.py:307 _budget_exceeded`
  reads it; `loop.sh deploy` and orphan recovery restart the worker → 0.
  `cost_from_transcript` (`cost_tracker.py:350`) already reconstructs the
  total from the transcript but only feeds the dashboard (`runs.py:1864`).
- **Files**: `src/app/observability/cost_tracker.py`,
  `src/app/server/runner.py`, `src/app/server/run_store.py` (or the runs
  table), migration.
- **Steps**:
  1. Persist the running total: on every priced/unpriced call, add the
     delta to a `run_usage` row (`run_id, prompt_tokens, completion_tokens,
     cached_tokens, requests, unpriced_requests, cost_usd`) with an
     `UPDATE … SET x = x + ?` (no read-modify-write), batched per stage end
     at most every N calls to keep the DB write rate low.
  2. On worker start / orphan recovery, seed `_RUN_COSTS[run_id]` from the
     row; if the row is missing (pre-migration runs), seed from
     `cost_from_transcript`.
  3. `_budget_exceeded` reads the persisted total + in-memory delta since
     the last flush.
  4. The pause message names the persisted total and the segment delta.
- **Tests**: `tests/test_a_run_s_token_ceiling_survives_a_worker_restart.py`
  — spend 60% in one tracker instance, drop it, create a new one for the
  same run, spend 50% more → `_budget_exceeded` is True (fails on old code:
  new instance starts at 0).
- **Acceptance**: a deploy mid-run on the W.2 baseline shows a continuous
  token total in the run status; W.4's KPI `tokens.input` equals the
  persisted total ± the last flush interval.
- **Effort**: S–M. **Depends on**: nothing.

<a id="plan-al"></a>
#### Initiative AL: The mutation probe cannot leave a broken product behind  **[DONE 2026-10-19]**
- **Goal**: AF's deliberate breaks are impossible to ship.
- **Evidence (H17 ✓)**: `acceptance/mutation.py:175` — `original =
  apply(project, site)` precedes the `try`; `finally` restores in-process
  only; a death mid-probe leaves the mutated file, and orphan recovery
  re-enters release on the broken tree. CRLF→LF on restore; sites inside
  docstrings/comments produce false "unnoticed" gaps.
- **Files**: `src/app/acceptance/mutation.py`, `src/app/graph/delivery.py`
  (release entry), `src/app/graph/terminal_state.py`.
- **Steps**:
  1. **Journal before mutate**: write `.harness/mutation-in-flight.json`
     `{file, original_sha, original_bytes_path}` and a byte copy of the
     original under `.harness/mutation-backup/` *before* `apply()`; delete
     the journal after a verified restore (compare sha).
  2. **Recovery**: at release entry (and in orphan recovery), if the journal
     exists → restore from the backup, log "a probe was interrupted;
     restored", then continue. Add the journal path to the harness-owned
     set so no agent touches it.
  3. Restore bytes, not text (`write_bytes` of the backup) — fixes CRLF.
  4. **Site selection**: skip lines inside comments/docstrings using the
     existing language-service/tree-sitter layer (`analysis/grammar_parse`)
     where available; otherwise skip lines that the language's comment
     prefix starts. Keep the budget (≤3 sites) and the non-browser rule.
  5. Prefer mutating a **copy**: when the pack's unit command can run from a
     temp copy of the project (`contract.unit` is argv-only), run the probe
     against `shutil.copytree(project, tmp, ignore=node_modules/.venv)` and
     never touch the workspace; fall back to in-place+journal only when the
     command depends on the workspace path.
- **Tests**: `tests/test_an_interrupted_mutation_probe_is_restored_at_release.py`
  (simulate: write journal+backup, mutate file, call release entry →
  original bytes back, journal gone; fails on old code — nothing restores);
  `tests/test_a_mutation_never_lands_in_a_comment.py`.
- **Acceptance**: zero `NON-DELIVERABLE` workspaces with a lingering
  `mutation-in-flight.json`; AF gap rate on the W.2 baseline reported with
  the site list so false positives can be read.
- **Effort**: S–M. **Depends on**: nothing.

<a id="plan-am"></a>
#### Initiative AM: One owner of a file's "seen" digest  **[DONE 2026-10-19]**
- **Goal**: the edit tool's view of what the model last saw is never
  overwritten by the memory middleware.
- **Evidence (H18)**: `agents/project_memory.py:383-386` calls
  `remember(held_path, held_content)` with the visit-start content on every
  call; `tools/repository.py:3619` sets the same digest after an edit → a
  later failed `edit_artifact` can be blamed on "a command you ran". The
  visit-start note "read it for the current text" conflicts with read
  withholding (`9d637fe`, `8ed63b2`).
- **Files**: `src/app/agents/project_memory.py`, `src/app/tools/seen_content.py`,
  `src/app/tools/repository.py`.
- **Steps**:
  1. `remember()` becomes *first-writer-wins per stage visit* for memory
     (`remember_if_unseen`) while the edit tool keeps `remember()` (always
     wins); or key the digest by `(path, source)` and have the edit error
     path consult the edit source first.
  2. When memory's note says a file changed since the visit started, and
     the read tool is withheld, the note must *include the current excerpt
     of the changed region* (the harness has the bytes) instead of asking
     for a read the stage cannot make.
  3. Add a middleware-order comment and a test that pins the order:
     memory → (model) → edit → next call's memory does not clobber.
- **Tests**: `tests/test_an_edit_s_own_digest_is_not_overwritten_by_memory.py`
  (edit a held file, run the memory middleware once more, fail an edit with
  stale `find` → the error names the model's own edit, not a command).
- **Acceptance**: on the W.2 baseline, zero occurrences of "a command you
  ran rewrote it" immediately after a successful `edit_artifact` on the same
  path (W.4 can count this pair).
- **Effort**: S. **Depends on**: nothing.

<a id="plan-an"></a>
#### Initiative AN: Correctness of the measurement layer (W.4 / W.1 / loop.sh)  **[DONE 2026-10-19]**
- **Goal**: the KPIs the loop now depends on count what they claim.
- **Evidence (H10 ✓, H11 ✓, H28)**: `scripts/loop/kpi.py:123,134` scan only
  `text[:600]` for guard markers while the harness appends notes *after*
  content; `prefill_decode_ratio` uses total input (cached inflates it);
  `reasoning_chars`, `invalid_tool_calls` recorded but unused; no per-stage
  KPI; `kpi_ledger.py` `mean > 0` guard never flags 0→n; benches mixed in
  the 5-run window; wall time includes orphan gaps; CSV non-atomic;
  `loop.sh:222` clobbers `data/kpi/<run>.json` when the worker fails;
  `loop.sh:294` passes one arg to `lessons.py`; W.1's byte-exact `cmp`
  excludes near-identical briefs from false-acceptance stats.
- **Files**: `scripts/loop/kpi.py`, `scripts/loop/kpi_ledger.py`,
  `scripts/loop/loop.sh`, `scripts/bench/score.py`.
- **Steps**:
  1. Guard markers: search the whole result, or better, read the structured
     marker the harness already attaches (make `repeated_queries` /
     `seen_content` emit a one-token tag at the *start* of the note and
     match that).
  2. Ratios: `prefill_decode_ratio = (input − cached) / output`; add
     `effective_input_tokens`.
  3. Per-stage block: `stages[{name, calls, input, cached, output,
     identical_calls, redundant_reads, lost_replies, tool_errors}]`.
  4. New counters: `lost_replies` by reply shape (length finish + no answer
     + no tool call — the owner's server reports no reasoning tokens),
     `phantom_write_claims` (Q.4 line), `compactions`, `stale_dispatches`
     ("closed without a fixer"), `reverts`, `reclassifications`,
     `vacuous_green`, `edit_wellformed_rate` per tool, `prompt_chars` per
     role (X.4), `steering_notes`.
  5. Ledger: flag when `value > max(1.5×mean, floor)` with a per-KPI floor;
     window per benchmark name; wall time from stage spans, orphan gaps
     separately; write CSV via temp+rename.
  6. `loop.sh kpi`: write to a temp file, move on success only; `lessons`:
     pass `"${@:2}"`.
  7. W.1: compare *normalised* brief text (whitespace, line endings) and
     report similarity; `brief_mismatch` only below a threshold, with the
     ratio in the export.
- **Tests**: `scripts/loop/tests/test_kpi_counts_appended_guard_notes.py`,
  `test_ledger_flags_zero_to_many.py`, a shell test for the temp-file
  write.
- **Acceptance**: `redundant_read_rate` and `identical_call_rate` agree on
  the medium run's transcript within 2 points; the ledger flags a seeded
  0→3 revert regression.
- **Effort**: S–M. **Depends on**: nothing; do before W.2 so the baseline
  is measured correctly.

<a id="plan-ao"></a>
#### Initiative AO: Lifecycle correctness of today's medium items (bundle)  **[AO.1-AO.4, AO.6-AO.8 DONE 2026-10-19; AO.5, AO.9, AO.10 PARTLY]**
One commit each, in this order; all S:
1. **AD edge cases (H27)**: `skipped` ≠ failed for the defect's own tests;
   unit fallback scoped to tests whose names/paths match the defect's
   affected files when tags are absent, else "cannot answer"; test keys use
   the real ` > ` separator; add `defects_left_open` to the KPI *before*
   the baseline so the jump is expected, not flagged.
2. **M.1 fail-closed semantics (H24)**: when `/props` is absent (vLLM,
   Ollama, LM Studio) log "server reports no slot/context facts; using the
   setting" once per run; when the slot context is *below*
   `MIN_VIABLE_WINDOW`, warn loudly and keep the smaller truth rather than
   raising the window above the slot.
3. **E split parts (H25)**: a part carries only the steps/interfaces/
   verification lines that name its files; sibling files listed as
   "written by a parallel part — do not wait on them"; parts of one order
   run *sequentially* unless the pack marks them independent.
4. **X.3 on Python 3.13 (H20)**: match the dedented sentence (or render
   the tool description from a template instead of replacing text); CI
   runs the suite on 3.12 and 3.13.
5. **AE reopen triggers (H26)**: a heuristic that joins the round list
   gains a precision measurement from the transcript archive (the loop's
   `check_precision.py` exists); any check under 90% precision stays
   review-only; add the missing test for the `ea714bc` filter.
6. **K.2 fresh `DATA_DIR` for every pack (H19)**: move the per-run data
   dir into the pack contract's acceptance argv/env (`contract.acceptance.
   env.DATA_DIR = <run tmp>`) so all ~20 service/fullstack packs get it;
   test iterates every pack; fix `seed.py`'s postgres row to say
   "embedded by default; PostgreSQL only when the brief demands it".
7. **AH.3 downgrade memory (H31)**: persist the judgement-downgrade fact
   on the run record when it happens; the gap stands even if the server
   returns.
8. **Changes API hygiene (H22)**: `asyncio.to_thread` for git calls, a
   timeout with a 504 body, `--no-textconv --no-ext-diff`, and refuse
   agent writes under `.git/` in the sandbox write guard.
9. **R digest precision (H21)**: record offset/limit and truncation in the
   "already held" line ("lines 1–200 of 640"); include files written by
   commands (the sandbox knows its write receipts).
10. **Repo-rule drift (H32)**: move Playwright/npx specifics out of
    `interface_contract.py` and the conftest/test-name heuristics out of
    `stacks/scaffold.py` into pack data; add banned-word tests for the X.3
    sentence, AA note and AE.2 gap strings; replace the two tests that pass
    on old code.

<a id="plan-ap"></a>
#### Initiative AP: Ledger and handover hygiene (process, half a day)  **[DONE 2026-10-19]**
- Remove the duplicate NOT STARTED rows (M L1348; O.1–O.4 L1358–1361;
  Z/AA/AB L2022–2024; UI rows L2036–2040); AJ row → "item 1 DONE
  (`2f68304`, `4abd460`); fixture seeding and timeout diagnostics open";
  M.4–M.6 row: `unknown_tool_name_rate` exists; HANDOVER §2 table and
  header date; AF decision text says "at release" (H14); record
  run-8b0c94df's outcome (H9) the moment it is known.

---

<a id="plan-part-14"></a>
### Part 14 — Remaining harness gaps (after the baseline)

<a id="plan-aq"></a>
#### Initiative AQ: The 431 repeated reads — instrumented hypotheses, not another guard
- **Evidence (H12, H15)**: 24% identical calls on the medium run, 431 of
  them `read_file`, *after* pointers (495), withholdings (93) and held-back
  reads (85). Two unconfirmed causes: the first repeat gets no notice
  (`REPEATS_BEFORE_SAYING_SO`=2, and notes are appended after content); memory
  pointers cover whole files ≤60k only. R's recitation landed after the run.
- **Steps**: (1) with AN.3's per-stage KPI, measure repeated reads per stage
  on the W.2 baseline *with R on*; (2) if still >10% in build stages, A/B
  `REPEATS_BEFORE_SAYING_SO=1` with the note *prepended* (one-line tag
  first, content after — also fixes AN.1's marker position); (3) windowed
  pointers: a repeated `read_file(offset,limit)` over an unchanged file
  answers with "unchanged; lines a–b are in your context above" instead of
  the bytes; (4) stop condition stays L.5.
- **Tests**: a repeated windowed read of an unchanged file returns the
  pointer form. **Acceptance**: build-stage identical-read rate <10% on the
  second baseline run. **Effort**: S + measurement.

<a id="plan-ar"></a>
#### Initiative AR: Lost replies — the owner's biggest time lever, measured properly  **[SCRIPT DONE; run waits for a free server]**
- **Evidence (H15)**: 37 lost replies ≈40% of the medium run's output; the
  owner's llama server reports no reasoning tokens, so N.1 (a per-request
  thinking budget) waits on proof the server honours one.
- **Steps** (uses the owner's allowance of ~1 h model time between runs,
  decision 2): (1) a 10-call probe script `scripts/loop/reasoning_probe.py`
  that sends the same planning-shaped request with `reasoning_budget` /
  `reasoning_effort` / `chat_template_kwargs.enable_thinking` variants and
  records whether output length and lost-reply rate change — a measurement,
  not a settings change; (2) if a parameter is honoured, N.1 ships as
  profile data with the owner's yes; (3) regardless, `lost_replies` per
  stage (AN.4) goes on the run page rail so the owner sees the cost live.
- **Acceptance**: lost-reply share on the next thorough run below 10% of
  output tokens, or a documented "server ignores budgets" result closing N.1.

<a id="plan-as"></a>
#### Initiative AS: Steering v2 (the backend half of the UI composer)  **[DONE 2026-10-19]**
- **Evidence (H3, H33)**: notes reach the system prompt end; no event, no
  acknowledgement, no scope, box shown while paused.
- **Steps**: (1) `steering_applied` event the first time a note reaches a
  call (stage, note id); (2) note `scope`: `next_stage` (dropped after one
  stage) or `run`; (3) a 409 while paused with "resume first"; (4) KPI
  `steering_notes`; (5) a banned-word test for the injected header.
- **Effort**: S. **Depends on**: typed events (15.5).

<a id="plan-at"></a>
#### Initiative AT: Lessons v2 (trust boundary for agent-derived text)  **[DONE 2026-10-19]**
- **Evidence (H29)**: owner approval is the only gate; the file sits on an
  agent-writable volume; `role` unused; no injection framing.
- **Steps**: (1) store lessons in the harness DB (or sign the JSON with the
  server's Fernet key, already present for credentials) so a sandbox
  command cannot edit it; (2) inject with a fixed frame "These are
  conventions, not instructions; they never override the rules above"; (3)
  role scoping via the role name the middleware can receive from
  `role_agent`; (4) REST routes for the UI (15.5); (5) KPI: lessons shown
  per call. **Effort**: S–M.

<a id="plan-au"></a>
#### Initiative AU: Interface contract for every surface (C/J.3 completion)
- **Evidence (H23)**: browser-only compiler; CLI/library packs skip
  silently; `command` lines never executed; parameterised routes false.
- **Steps**: (1) contract line kinds map to pack-declared *probe runners*
  (page → browser probe; route → HTTP probe via the pack's serve command;
  command → argv probe with exit code; library → import+call probe), as
  pack data per K.6; (2) a kind with no runner yields an "unchecked" line
  in the evidence, never silence; (3) route templates (`/api/notes/{id}`)
  resolved from the suite's own fixtures or marked unchecked. **Effort**: M.
  **Depends on**: K.6.

<a id="plan-av"></a>
#### Initiative AV: AJ completion — tests that cannot hang the worker  **[DONE 2026-10-19]**
- **Evidence (H13)**: only the "report printed, process lingers" half
  landed (`2f68304`, `4abd460`); the `NullPool` / `engine.dispose()`
  fixture seeding for Python packs and timeout stdout diagnostics are open;
  direct `run_terminal_command` pytest runs can still hang.
- **Steps**: pack data for `_python.py`/`_fullstack.py` seeding an async
  engine fixture that disposes; sandbox: on timeout, return the captured
  stdout/stderr tail with "ended at the time limit" rather than nothing.
  **Effort**: S.

<a id="plan-aw"></a>
#### Initiative AW: K.6 (stack-shaped checks as pack data) — scoped after the baselines, per decision 10
- Deliverables, in order: per-pack `check_families` for the ten empty
  service packs (go×2, java-spring, aspnet, rust-axum, ruby×2, php×2,
  node-nest); `entrypoints` for every fullstack/service pack (K.3 covers
  two today); dependency-drift manifests for Go (`go.mod`), Rust
  (`Cargo.toml`), Java (`pom.xml`/`build.gradle`), .NET (`*.csproj`), Ruby
  (`Gemfile`), PHP (`composer.json`); a per-pack `coverage` field rendered
  by AG's tier on the evidence page and in S3. **Effort**: M–L, incremental.

<a id="plan-part-15"></a>
### Part 15 — UI/UX revamp: "the control room", with a multi-theme design system

**Why a revamp and not more patches.** Phase 1 removed the measured harms
(455→5 axe violations, toasts/dialogs, countdown, stale-while-error) and
`ef982a2` added the three owner-priority views (Changes, criteria→tests,
steering). What remains is structural: one real primitive module
(`Feedback.tsx`), eight copies of the status colour map, hand-rolled
spinners ×7, dark-only tokens with `color-scheme: dark` hard-set, Google
Fonts over the network on an offline product, no empty/loading states on
the evidence panels, and a run page whose workspace sits below the fold at
768 px because four panels stack above it (H1–H7). The research is explicit
about what this UI must do: professional developers *control* agents through
planning and supervision and the cost of delegation is "maintaining enough
understanding of work they had not written" (R21) — so the job of the UI is
legibility of plan, evidence and diff, and getting the owner back to the one
thing that needs them.

<a id="plan-ui-15-1"></a>
#### 15.1 Design brief and plan (reviewed against the generic default)

- **Subject**: a self-hosted "AI software company" control room. One owner
  (sometimes a second operator) supervises multi-hour builds on a local
  model, approves gates, judges evidence, steers, and reads history.
- **Primary job of each screen**: Home — start a build with confidence;
  Runs — find the run that needs you; Run — know in five seconds whether it
  needs you, what it is doing, and what has been proven; Evidence — decide
  whether to ship; Settings — make the model and appearance yours.
- **Identity device (spend the boldness here)**: *the ledger*. The product's
  promise is "measured, not vibes", so the hero of the run page is the
  acceptance-criteria ledger: each criterion a row that flips from "not yet"
  to "proven" with the test that proved it, the commit that made it pass,
  and the time. Everything else is quiet. The current UI spends its boldness
  on glass blur, animated gradient buttons and glow badges (`index.css:
  118-160`) — the SaaS-kit default the brief rejects — and those go.
- **Type**: **IBM Plex Sans** (UI) + **IBM Plex Mono** (identifiers, paths,
  diffs, log, numbers in the ledger), both self-hosted woff2 under
  `langchain-ui/public/fonts/` with `font-display: swap`. One family in two
  clearly distinct cuts; the mono is part of the identity because half the
  content *is* code and run ids. Scale (1.25 ratio, 14 px base): 12 / 13 /
  14 / 16 / 20 / 25 / 31; line-height 1.5 body, 1.25 headings; measure ≤ 72
  characters in prose panels. No tracked-out all-caps eyebrows; labels are
  sentence case.
- **Layout concept** (run page): a persistent left *status rail*, a centre
  *work area* with tabs, and the *ledger* on the right; gates and steering
  dock at the bottom of the work area as a composer, never above the fold.

  ```
  ┌──────────── header: DevFlow · Runs · Start a build · Settings · [needs you ●2] ─────────┐
  │ RAIL (18rem)       │ WORK AREA (fluid)                           │ LEDGER (24rem)        │
  │ run name, brief    │ [Activity] [Changes] [Evidence] [Artifacts] │ 12 of 15 proven       │
  │ fast · local       │  …tab content…                              │ ✓ AC-1 Add item  t1   │
  │ ● needs you: gate  │                                             │ ✓ AC-2 …              │
  │ stage stepper      │                                             │ ○ AC-7 Filter… (fix 2)│
  │ 2h14m · $0 · 1.2M  │                                             │ ⚠ AC-9 deferred       │
  │ model · slots      ├─────────────────────────────────────────────┤ gaps: 1               │
  │ [pause] [cancel]   │ composer: gate decision / steering note     │ support tier: pack    │
  └────────────────────┴─────────────────────────────────────────────┴───────────────────────┘
  <1024 px: rail collapses to a top strip; ledger becomes a tab. <640 px: single column,
  "needs you" pinned bottom with one-tap approve.
  ```
  Alignment: left-aligned throughout; numbers right-aligned in the ledger
  and cost rows; no centred hero text anywhere.
- **Palette**: three theme families with full semantic token sets (15.2),
  one accent spent on "needs you" and primary actions only. Neutral
  graphite surfaces, not blue-tinted slate; no alpha-white overlays as a
  colour system (they are what breaks light mode today).
- **Motion**: two moments only — a feed entry arriving (already exists,
  `activity-in`) and the "needs you" indicator's single pulse on arrival.
  No hover lifts, no gradient animation, no glow. `prefers-reduced-motion`
  stays honoured.
- **Copy**: plain verbs, sentence case, the same word through a flow
  ("Approve plan" → toast "Plan approved"). Errors say what happened and
  what to do; empty states are invitations ("No runs yet. Start a build.").
  The narration module (`lib/activity.ts`) is kept and extended to cover all
  stages (H6).
- **Review against the generic default**: the obvious design for "AI agent
  dashboard" is dark slate + indigo + glass cards + a KPI stat row on top —
  which is the current UI. Changed on purpose: graphite neutrals over
  blue-slate; Plex over Inter; the criteria ledger as the hero instead of a
  stat row; the accent reserved for attention instead of brand decoration;
  density control instead of fixed card padding; light and high-contrast
  as first-class families, not a `dark:` afterthought.

<a id="plan-ui-15-2"></a>
#### 15.2 The theme system (multiple theme options)

**Mechanism** (H1 makes this cheap: Tailwind 4 keeps `@theme` variables as
CSS custom properties, so redefining them re-themes ~830 class sites with no
component edits).

1. **Three token layers in `index.css`**:
   - *Primitive scales per theme* under `:root[data-theme="graphite"]`,
     `[data-theme="paper"]`, `[data-theme="contrast"]` (and `@media
     (prefers-color-scheme)` blocks used only when `data-theme="system"`).
   - *Semantic tokens* (theme-independent names, defined per theme):
     `--bg-canvas --bg-surface --bg-raised --bg-overlay --bg-inset`,
     `--fg --fg-muted --fg-subtle --fg-on-accent`, `--border --border-strong
     --border-focus`, `--accent --accent-hover --accent-soft --accent-fg`,
     `--status-ok-fg/-bg/-border`, `--status-warn-*`, `--status-danger-*`,
     `--status-info-*`, `--status-attention-*` (needs-you), `--code-bg
     --code-fg`, `--diff-add-bg --diff-add-fg --diff-del-bg --diff-del-fg
     --diff-hunk-bg`, `--shadow-1 --shadow-2`, `--ring`.
   - *Tailwind mapping* in `@theme inline { --color-surface: var(--bg-surface);
     --color-text-primary: var(--fg); … }` so every existing `bg-surface`,
     `text-text-primary`, `border-border` utility follows the active theme.
2. **Attributes on `<html>`**: `data-theme` (`graphite | paper | contrast |
   system`), `data-accent` (`blue | violet | teal | amber | rose | neutral`),
   `data-density` (`comfortable | compact` → spacing scale and row heights),
   plus `color-scheme` set to match so native controls and scrollbars follow.
3. **No flash**: a 10-line inline script in `index.html` reads
   `localStorage.devflow.appearance` → falls back to `system` → sets the
   attributes before first paint. A `<meta name="theme-color">` per theme.
4. **Persistence across devices**: `GET /auth/me` returns `preferences:
   {theme, accent, density}`; `PATCH /auth/me/preferences` stores them per
   user (new column on the users table + migration). localStorage is the
   fast path; the server value wins on login.
5. **Contrast as a test, not a hope**: `scripts/ui/theme_contrast.mjs`
   computes WCAG ratios for every declared (fg, bg) pair in every theme and
   fails under 4.5:1 (7:1 for `contrast`); `scripts/ui/axe_measure.mjs`
   runs once per theme. Both run in the UI CI step.
6. **Codemod for the outliers** (~210–230 sites, 22 files): `text-white` →
   `text-text-primary` (headings/body) or `text-accent-fg` (on accent fills);
   `bg-white/5|10` and `bg-black/40` → `bg-overlay` / `bg-inset`; raw
   `slate-*` → semantic; `bg-[#hex]` → the matching token; the unlayered
   `.text-primary` / `.text-danger` overrides deleted in favour of
   `--status-*-fg` tokens; the 8 status maps collapse into
   `lib/status.ts` (one map from run/stage status → label, token class,
   icon, narration). `ErrorBoundary`'s inline `#f4f4f4` goes.
7. **Theme families (initial values; the contrast script is the authority)**

   | Token | Graphite (default dark) | Paper (light) | Contrast (dark, AAA) |
   |---|---|---|---|
   | bg-canvas | `#15171C` | `#F4F5F7` | `#000000` |
   | bg-surface | `#1C1F26` | `#FFFFFF` | `#0A0A0A` |
   | bg-raised | `#242830` | `#EEF0F3` | `#141414` |
   | border | `#343945` | `#D7DBE2` | `#8A8A8A` (2 px) |
   | fg | `#E8EAEF` | `#1B1F27` | `#FFFFFF` |
   | fg-muted | `#9AA3B2` | `#5B6474` | `#D0D0D0` |
   | accent (blue) | `#6E8BFF` | `#3350D6` | `#9DB4FF` |
   | status-ok-fg / bg | `#3FB68B` / `#163A2E` | `#1E7F5A` / `#DDF3EA` | `#5CE0A8` / `#002B1C` |
   | status-warn-fg / bg | `#E2A33A` / `#3B2E12` | `#9A6700` / `#FBEFD3` | `#FFD166` / `#2E2200` |
   | status-danger-fg / bg | `#E5605C` / `#3D1C1B` | `#B42318` / `#FBE3E1` | `#FF7B74` / `#330B09` |
   | status-attention | accent at full strength; the only saturated fill on a quiet screen |

   Accent variants redefine `--accent*` only. `neutral` accent exists for
   owners who want zero colour except status.
8. **Where the owner picks**: a sun/moon/system toggle in the header (one
   click, cycles), and *Settings → Appearance*: three theme cards with a
   live miniature of the run page, accent swatches, density, and "follow
   system motion setting" (read-only, informational). Keyboard: `t` cycles
   theme when no input is focused (listed in the shortcuts sheet, 15.4).
9. **Generated products are not themed by this**: Initiative A's pack design
   tokens stay separate; a product never inherits the control room's theme.

**Deliverables and order (UI-T1…T6)**: T1 token layers + attributes + boot
script + self-hosted Plex (1–2 days); T2 codemod + status map (1–2 days);
T3 contrast + axe per theme in CI (half a day); T4 Appearance settings +
header toggle + server preference (1 day, needs the small API); T5 Paper
and Contrast tuning against the contrast script (1 day); T6 screenshots of
each theme into `docs/ui/` for the handover (half a day).

<a id="plan-ui-15-3"></a>
#### 15.3 Primitives (UI-P): the component kit the revamp is built from

`langchain-ui/src/ui/` — one file each, all token-only, all with keyboard
and ARIA done once: `Button` (primary/secondary/quiet/danger; sizes;
loading state; icon slot), `IconButton` (requires `aria-label`), `Card`
(surface/raised; header/body/footer slots; no shadow by default), `Badge`
(status map driven), `Tabs` (roving tabindex, `role=tablist/tab/tabpanel`,
URL-synced), `Dialog` (built on the existing confirm's focus trap; sizes;
`aria-modal`), `Drawer` (artifact/diff on narrow screens), `Toast`
(existing, moved), `Field`/`Input`/`Select`/`Textarea`/`Checkbox` (label,
hint, error, `aria-describedby`), `Skeleton`, `EmptyState` (icon, one
sentence, one action), `Stat` (number + source line — every number in the
UI says where it came from), `Kbd`, `Tooltip` (hover + focus), `Progress`
(determinate/indeterminate, `aria-valuenow`). `CredentialField`/`InfoRow`
move out of the Settings render (H2). Each primitive gets a Storybook-free
"kitchen sink" route `/dev/ui` (dev build only) used by axe and the theme
screenshots.

<a id="plan-ui-15-4"></a>
#### 15.4 Screens (UI-S), in build order

- **S1 Shell + navigation**: header = DevFlow, *Runs*, *Start a build*,
  *Settings*, a **needs-you indicator** (count of runs in
  `awaiting_approval`/`waiting_for_budget`/`failed` since last seen; click
  → list), theme toggle, user menu with sign out. 404 route; post-login
  redirect to the page asked for; token refresh via `/auth/refresh` 5 min
  before expiry (no more reload mid-run). Command palette (`⌘K`): go to
  run, start a build, approve the waiting gate, switch theme. Shortcuts
  sheet (`?`).
- **S2 Runs list**: a table, not cards: status (badge + plain words), name,
  brief, mode (fast/thorough), model (local/judgement), started, elapsed,
  proven x/y, gaps, needs-you. Filters by status; search; "needs you" rows
  first; row actions visible (not hover-only) and keyboard reachable;
  pagination at 50; polling pauses when hidden (exists) and uses
  `/events?since` on reconnect. Empty state: "No runs yet — Start a build".
- **S3 Start a build (plan-first intake)**: three steps with a draft saved
  in localStorage: (1) *Brief* — free text **and/or** documents (fixes H7:
  documents-only today), with the brief's acceptance criteria extracted
  live as a preview list; (2) *How* — stack suggestion with **support tier**
  (pack-supported / custom / unverified, from AG) and what each tier
  verifies; mode fast/thorough with the measured typical duration ("fast
  web builds have taken 1.4–2.5 h over the last 5 runs"); model (shows the
  probed server: slots, context, quant from M.1; a warning when nothing is
  configured with a link to Settings); gates (auto-approve or ask, timeout
  with its consequence spelled out); budget caps (`MAX_RUN_TOKENS`,
  known-spend cap labelled honestly); (3) *Review* — the plan page: what
  will be built, the criteria ledger pre-populated as "not yet", the ETA,
  and one button, **Start build**. `createRun`+`startRun` become one
  endpoint call or the failure path deletes the orphan (G9). Brownfield:
  "Start from an existing repository" uses the unused `/codebase` route.
- **S4 Run page (the control room)**: rail / work area / ledger as drawn.
  Tabs: *Activity* (virtualized feed, grouped by stage, narration first,
  raw event on expand, filter by agent in parallel mode — "lanes"),
  *Changes* (commit list + per-file tree + diff with syntax colours via
  tokens; file filter; "jump to criterion's commit"), *Evidence* (the
  release decision page rendered natively: suite counts, completion gaps as
  a structured list, mutation probe results, interface-contract check
  results, support tier, reviewer completeness — all from new endpoints,
  15.5), *Artifacts* (inline render of markdown/code/images; version list
  per path from git; download), *Log* (virtualized, 5,000-row buffer,
  search). Composer at the bottom: gate decisions with the countdown and
  "waits indefinitely" (H8 — payload already has it), steering with
  acknowledgement (the next `steering_applied` event, 15.5) and note
  history; hidden when the run is terminal. Rail: stage stepper from the
  typed event schema (replaces title-case fallbacks, H6), elapsed (ticks),
  tokens and known spend with per-stage breakdown on hover, model and
  slots, pause/cancel/rewind. Title and favicon badge for needs-you;
  browser Notification on gate/failure/completion (opt-in in Appearance).
- **S5 Settings**: *Models* (build/judgement endpoints with the live probe
  result and a "test call" button), *Appearance* (15.2), *Runs* (defaults
  for mode, gates, caps), *Lessons* (the AI store: proposals with evidence
  counts → approve/reject; today CLI-only), *Account*.
- **S6 Insights** (after W.2 data exists): per-run KPI card from
  `data/kpi/<run>.json` and the cross-run ledger: identical-call rate,
  cache share, lost replies, reverts, gaps; regression flags; two runs side
  by side (U.3's compare already exists as a script).

<a id="plan-ui-15-5"></a>
#### 15.5 Backend enablers the screens need (small, listed so the parts connect)

| Enabler | Shape | Needed by |
|---|---|---|
| Typed event schema | `events` carry `kind`, `stage`, `agent`, `payload` with a published JSON schema; `STAGE_COPY` generated from the graph's node list so no stage lacks copy | S4 rail/feed, H6 |
| `steering_applied` event | emitted by the instruction middleware the first time a note reaches a call; `steering` notes get `id` and optional `until` (next stage / run end) | S4 composer, H3 |
| Preferences | `GET/PATCH /auth/me/preferences` | 15.2 |
| Structured evidence | `GET /runs/{id}/evidence` → `{suite, completion_gaps[], mutation[], interface_contract[], support_tier, reviewers[]}` | S4 Evidence |
| Per-stage usage | `GET /runs/{id}/usage` → per stage tokens in/out/cached, calls, known cost | S4 rail, S6 |
| KPI | `GET /runs/{id}/kpi` (the W.4 JSON) and `GET /kpi/ledger` | S6 |
| Lessons | `GET /lessons`, `POST /lessons/{id}/approve|reject` (wraps `plugins/lessons.py`) | S5 |
| Artifact versions | `GET /runs/{id}/artifacts/{path}/versions` from git log; replaces the hard-coded `revision=1` | S4 Artifacts |
| Start | `POST /runs/start` (create+start) or compensating delete | S3 |
| Generated client | TS client + types generated from the FastAPI OpenAPI schema at build (`openapi-typescript`), replacing hand-kept `types/` — ends the `document_names` class of drift | all |

<a id="plan-ui-15-6"></a>
#### 15.6 Quality floor and measurement

- axe per theme per page ≤ 5 violations, none colour-contrast; keyboard-only
  run of the three main flows recorded; Lighthouse performance ≥ 90 on the
  run page with 5,000 events; bundle split per route; fonts self-hosted;
  works offline after first load for cached screens (no PWA install — owner
  decision 6 — just correct caching headers); UI tests: Vitest + Testing
  Library for primitives and the status map, Playwright for the three
  flows (start a build, approve a gate, review evidence).

<a id="plan-ui-15-7"></a>
#### 15.7 Order and effort

| Step | Scope | Effort |
|---|---|---|
| UI-0 | Phase-1 remainder (H5) + contract drift via generated client | 2–3 days |
| UI-T1–T3 | Token layers, Plex, codemod, status map, contrast/axe per theme | 3–4 days |
| UI-P | Primitive kit + `/dev/ui` | 3–4 days |
| UI-S1, S2 | Shell, needs-you, palette, runs table | 3 days |
| UI-S4 | Control room (rail/work area/ledger, virtualized feed, Changes per-file, Evidence, composer) + enablers | 2–3 weeks |
| UI-T4–T6, S5 | Appearance settings, server preference, theme tuning, Settings rework incl. Lessons | 4–5 days |
| UI-S3 | Plan-first intake + start endpoint + brownfield | 1 week |
| UI-S6 | Insights (after W.2 data) | 3–4 days |

---

<a id="plan-part-16"></a>
### Part 16 — Implementation sequence (detailed)

| Wave | Items | Gate to next wave |
|---|---|---|
| 0 (now, before any run) | AN (measurement correctness), AK, AL, AM, AO.1–AO.2, AP | suite green on 3.12 + 3.13; `loop.sh kpi` on run-8b0c94df's transcript reproduces agreeing rates |
| 1 (owner) | **W.2 baselines** in the decided order: fast notes-api-hono → fast fullstack-bookmarks-py → thorough | scored, KPI JSON + ledger rows, outcome recorded in HANDOVER §2 and the plan |
| 2 | AO.3–AO.10, AQ (measure → A/B), AR probe, AS, AT, AV | per-stage KPIs on both baselines; lost-reply share and identical-read rate reported |
| 3 (UI, can run in parallel with 2 by a second session) | UI-0 → UI-T1–T3 → UI-P → UI-S1/S2 → UI-S4 (+15.5 enablers) → UI-T4–T6/S5 → UI-S3 → UI-S6 | axe per theme ≤5; contrast script green; three Playwright flows green; screenshots per theme in `docs/ui/` |
| 4 | AU, AW (K.6), M.4–M.6, U.3 A/B wiring on the ledger | second bench family (fullstack-python) scored under the same KPIs |

Rules unchanged: every change with a test that fails on the old code; no
stack specifics outside packs/seed/profiles; no run ids in code; both
handovers updated in the same commit; the model and its settings are the
owner's.

<a id="plan-ledger-a3"></a>
### Appendix 3 rows (Implementation Progress Ledger continuation)

| Item | Priority | Status | Notes |
|---|---|---|---|
| AK run-wide budgets persisted | P0 | DONE 2026-10-19 (`a276433`) | Redesigned: no `run_usage` table. A handler built in a fresh process takes what the run spent before that moment from the transcript (`seed_from_the_transcript`; the cut by timestamp is exact), once per process. Test: `test_a_run_s_token_ceiling_survives_a_worker_restart.py` |
| AL crash-safe mutation probe | P0 | DONE 2026-10-19 (`b18425e`) | Journal and a byte copy before the break; bytes back (CRLF kept); `restore_an_interrupted_probe` at the top of `release`; docstrings and block comments never broken. Mutating a copy was not done: the in-place journal covers the failure, and a copy changes how the pack's commands resolve paths |
| AM one owner of the seen digest | P0 | DONE 2026-10-19 (`7207531`) | `seen_content.remember_if_unseen` for the memory; when reading is withheld the change note shows a capped diff instead of asking for a read |
| AN measurement correctness | P0 | DONE 2026-10-19 (`f724c00`, `804e29a`) | Guard words searched at both ends; effective-input prefill ratio; reasoning, lost-reply share and invalid-call counters; a block per stage; orphan gaps apart; ledger floors, 0-to-n, same-benchmark window, atomic writes; `loop.sh kpi` atomic, `lessons` gets every argument; W.1 compares normalised text with a similarity. Not counted (no event to count them from): phantom write claims, compactions, prompt chars per role |
| AO.1 AD edge cases | P0 | DONE 2026-10-19 (`094fbfd`) | Skipped is neither failure nor proof; unit tests scoped to the defect's files; tests use the real separator. Also (`9e4c056`): a criterion the locked suite measured green needs no named regression test, and a fix stage that spends its calls is recorded from its writes instead of started over twice more |
| AO.2 M.1 fail-closed semantics | P0 | DONE 2026-10-19 (`dc31ad0`) | A slot below the floor is the window (warned once); a server with no `/props` is noted once |
| AO.3 E split parts | P1 | DONE 2026-10-19 (`AO.3` commit) | A part carries only the lines about its own files, and is told its siblings' files belong to a parallel part. Sequential running was not added: drafting is per file and the one-slot server already serialises it |
| AO.4 X.3 on 3.13 + CI matrix | P1 | DONE 2026-10-19 | The network sentence is found by its words; CI runs 3.12 (gating) and 3.13 (informing) |
| AO.5 AE reopen precision | P1 | DONE 2026-10-19 `448f182` | The missing test for the release re-read's locked-suite filter is added. Precision is measured without labels: `loop.sh checks --write` copies the host's scored runs into the worker, grades each check's findings as the rounds do, and counts a check that called a product broken when every hidden test of it passed as wrong (checks about the tests themselves are left out: the hidden tests judge the product). `integration_checks.checks_too_imprecise_to_block` reads `DATA_DIR/loop/check_precision.json`; a check under 0.9 over 5 or more scored products is graded a hint. First measurement (2026-10-19): "the ids and data attributes scripts reach for against the page" 0.43 over 7 - review-only; the others fired on too few scored products. Re-run after each scored run. Test `tests/test_a_check_measured_imprecise_cannot_block.py` (fails on the old code). Group 1 |
| AO.6 K.2 DATA_DIR for every pack + seed text | P1 | DONE 2026-10-19 | Premise corrected: the shared Playwright configuration and the Python packs' conftest already give a fresh DATA_DIR; a test now pins it for every service and full-stack pack, and the seeded postgres guidance says embedded by default |
| AO.7 AH.3 persisted downgrade | P1 | DONE 2026-10-19 | `roles.remember_the_downgrade` keeps the fact per run; the release reads it |
| AO.8 changes API hygiene + `.git/` write guard | P1 | DONE 2026-10-19 | git runs in a thread without textconv or an external diff, 504 on a timeout. The `.git/` write refusal already existed (`test_nothing_is_written_where_a_tool_installs`) and is now also pinned for hooks |
| AO.9 R digest precision | P1 | DONE 2026-10-19 `32d0f81` | The already-known list names the lines each read covered. Since 2026-10-19 a command's result carries `files_changed` (`sandbox.files_changed_since`, dependency and runner output pruned, 20 named), and a file read before a command rewrote it reads "changed by your command at call N"; the list's exit codes now parse the sandbox's quoted `returncode`. Test `tests/test_a_file_a_command_rewrote_is_not_called_held.py` (both fail on the old code) |
| AO.10 repo-rule drift | P1 | DONE 2026-10-19 `28a60ca` | The contract checks name no tool: the pack declares `probe_runner` and the checks look it up; banned-word tests for the network sentence, memory note and gap strings. Finished 2026-10-19: the unit-test names and fixture files the served-code check reads are pack data (`StackPack.unit_test_names`, `test_helpers`; pytest's names and `conftest.py` in `_python`, a fullstack pack's from its page and its service), and `stacks/scaffold.py` names no test convention. Test `tests/test_unit_test_names_are_pack_data.py` (3 of 4 fail on the old code). Group 1 |
| AP ledger/handover hygiene | P0 | DONE 2026-10-19 | Duplicate NOT STARTED rows removed (M, O.1-O.4, Z/AA/AB, UI); AJ and M.4-M.6 rows corrected; decision 11 says "at release". run-8b0c94df's outcome (H9): cancelled 07:11 JST at 9 of 30 locked tests after 24 h; recorded in HANDOVER §2.3 and `data/kpi/` |
| AQ repeated-read hypotheses | P1 | PARTLY 2026-10-19 | Measured on run-8b0c94df: 48% of reads redundant; one fix stage spent 70 reads and 4 writes in 40 calls because the project memory could not hold the two-copy project. Done: a copy of the app nothing serves now ranks after the served files in the memory (`scaffold.folders_nothing_serves`). Step 3 done 2026-10-19 `4e7c9bb`: the same window of an unchanged file asked for again is answered with where its lines are, not the bytes (`WINDOWED_REPEATS_BEFORE_POINTING = 1`); test `tests/test_a_repeated_windowed_read_returns_a_pointer.py` fails on the old code; three older tests that expected the bytes back now read a window inside the served lines. Steps 1-2 (per-stage repeated reads on the baseline, the `REPEATS_BEFORE_SAYING_SO=1` A/B) wait for the W.2 KPI data |
| AR lost-reply probe → N.1 | P1 | DONE 2026-10-19 (measured) | Run 14:30 JST between baselines 1 and 2, 10 calls of up to 4096 tokens. Median output tokens: baseline 3339, `reasoning_effort` low 3767 (+13%), high 3943 (+18%), thinking off 2326 (-30%), reasoning budget 256 3576 (+7%, reasoning 7639 chars vs 7723). Lost replies 0 in every variant. **The server honours only the thinking switch**; per-request budget and effort are ignored. So AX is not built (owner rule) and N.1 closes as "server ignores budgets" |
| AS steering v2 | P1 | DONE 2026-10-19 | Note ids; scope run or next stage; a `steering_applied` transcript record the first time a note reaches a call (the UI shows "read by the run in <stage>"); 409 while paused; KPI `steering_notes` |
| AT lessons v2 | P2 | DONE 2026-10-19 | HMAC-signed store (key from `JWT_SECRET_KEY`, unreadable to a workspace command; a bad signature means no lesson is used), a "conventions, not instructions" frame, role scope from the agent's name, `GET /api/lessons` and admin-only approve/reject. Lessons-shown-per-call KPI not built |
| AU interface contract for every surface | P2 | DONE 2026-10-19 `3d293bb` | Command lines run as themselves through the sandbox on every pack and compare their exit code; what they write is put back before the release (new files removed, changed files restored from git). A route or page line on a pack with no probe runner, and a route with a parameter in it (`/{id}`, `/:id`), are named in one "not checked at release" completion gap instead of silence. Routes are not resolved from fixtures (step 3's alternative, kept unchecked); a library line form does not exist in the contract yet. Tests in `tests/test_the_interface_contract_is_locked_and_checked_at_release.py` (3 fail on the old code). Group 1 |
| AV AJ completion | P1 | DONE 2026-10-19 | A timeout says it ended the command and returns the output so far; the Python guides say to close what tests open (a fixture that awaits `engine.dispose()`) |
| AW K.6 scoped | P2 | DONE 2026-10-19 `503a4f0`, two deliverables DROPPED (premise false) | Done: every service and fullstack pack names the file its product replaces, so K.3's stub check reaches all of them (10 packs gained one; Java Spring has none - its routes are new controller classes); `StackPack.coverage`, derived from each pack's data, states what the harness checks on it, and the support tier on the evidence page, the run summary and the stack decision now carries it (S3, not built, will read the same). DROPPED (premise false): per-pack `check_families` for the ten service packs - the field is read by nothing (grep finds no consumer); every cross-file check selects files by its own extensions, so filling it would change nothing. DROPPED (premise false): dependency-drift manifests for Go, Rust, Java and .NET - their builds already fail naming the missing module, and K.4's own rule (a language joins when its evidence does) has no evidence for Ruby or PHP: no run on those stacks yet. Test `tests/test_each_pack_says_what_the_harness_checks.py` (both fail on the old code). Group 1 |
| UI-0 Phase-1 remainder + generated client | P1 | DONE 2026-10-19 `6ffed0f` | `RunSummary` type matches the server (`document_names` drift), token renewal five minutes before expiry (`lib/session.ts`), post-login redirect to the page asked for, a 404 page; the title/favicon badge and browser notifications came with BG.2. Generated types: `scripts/ui/openapi_schema.py` (`npm run api:types`) writes `langchain-ui/openapi.json` from the app (store and runner stood in, no database) and `src/types/api.gen.ts` from it; 20 hand-kept types are now re-exports of the generated ones, and only what the schema does not describe (the event stream, the review form) is written by hand. Not `openapi-typescript`: it supports TypeScript 5 only (the UI is on 6), and a generator in Python lets the suite check the files with no Node - FastAPI's schemas use a handful of keywords. In a response every property is present (a model serializes every field); in a request only `required` ones. The switch found one more drift: the settings view reports thinking mode, effort and execution mode as text while the update accepts only listed values; the form now narrows them. Tests: `tests/test_the_ui_s_api_types_are_current.py` (the committed schema is the server's, the types are generated from it, the present/optional rule) |
| UI-T1–T3 theme system (tokens, Plex, codemod, contrast CI) | P1 | DONE 2026-10-19 | `index.css`: three themes (graphite, paper, contrast) plus system, six accents, two densities, as tokens any element can carry; Plex Sans and Mono self-hosted (no Google Fonts); ~230 colour classes codemodded to tokens, a test bans raw colours in components; `scripts/ui/theme_contrast.mjs` checks 650 pairs over 13 theme/accent sets; axe per theme: 0 violations on Home, Runs, Settings and a run, in all three themes |
| UI-P primitive kit | P1 | DONE 2026-10-19 `d81c1a6` | `langchain-ui/src/ui/`: Button (4 variants, 2 sizes, loading, icon), IconButton (label required), Card (header/body/footer), Badge + StatusBadge (status map), Tabs (one tab stop, arrows/Home/End, URL-synced by `param`), Dialog + Drawer (focus trap, Escape, focus returned, `aria-modal`), Field/Input/Select/Textarea/Checkbox (label, hint, error via `aria-describedby`, `aria-invalid`), Skeleton, EmptyState, Stat (number + source), Kbd, Tooltip (hover and focus), Progress (determinate/indeterminate), InfoRow. The Settings credential field and info row moved out of the render (H2): typing a key no longer loses focus, and the inputs now have labels. `/dev/ui` (dev build only) shows the kit; `scripts/ui/axe_kit.mjs` measures it: 0 axe violations in graphite, paper and contrast (page and open dialog); `theme_contrast.mjs` 650 pairs hold. Tests: `src/ui/ui.test.tsx` (11), `src/pages/Settings.test.tsx` (fails on the old code). Deployed with stage 1, after the W.2 baselines |
| UI-S1/S2 shell + runs table | P1 | DONE 2026-10-19 `2e25e60` | The runs table (status, run, brief, mode, model, elapsed, proven x of y, gaps, labelled row actions), search and filters kept in the address, the runs that need the owner first, the needs-you inbox (BG.2), a theme toggle with the key `t`. Then: pages of 50 (`?page=` in the address, "Runs 51-100 of 120", Newer/Older; before, a run older than the newest 50 could not be reached from the list; search and filters say they look at the page shown), the command palette on `Ctrl K`/`⌘K` (`components/CommandPalette.tsx`: go to any of the 20 newest runs, approve a waiting gate or review - each naming where it waits and when it approves itself - start a build, runs, settings, switch the theme; a combobox with a listbox, arrows and Enter; a header control opens it too) and the shortcuts sheet on `?` (not while typing in a field). The events-since reconnect was already there: the run page reconnects its stream with `last_event_id` set to the last sequence it merged (`RunDashboard.tsx`) and the server replays the history after it (`server/progress.py`). axe 0 per theme with the palette and the sheet open (`scripts/ui/axe_kit.mjs` measures both now). Tests: `pages/RunList.test.tsx` (the page in the address, the pager; fail on the old code), `components/CommandPalette.test.tsx` |
| UI-S4 control room + 15.5 enablers | P1 | DONE 2026-10-19 `d61c1f8f` | Done: a Changes view of the workspace history, criteria opening to their tests, "what this release did not prove" (completion gaps and support tier from `/evidence`), steering with an acknowledgement and scope, the run summary enabler. Since: the composer and document versions (BG.3), the rail/work-area/ledger layout (BG.4), per-stage usage (BG.7). Last: the feed shows its newest 300 entries and earlier ones on request, 300 at a time, and a timeline jump to an older moment widens it to reach it - measured live, 876 entries were 10,361 elements, nine in ten of the page, rebuilt each time the tab opened; a full virtualiser needs a library and variable-height rows, and the window does the same job. The event schema is published: `/logs` answers `EventPage` with `RunEvent` (its closed set of event types), and the page's event type is the generated one, so a type added on the server reaches the page's build (`tests/test_the_event_schema_is_published.py`, fails on the old code). |
| UI-T4–T6 / S5 appearance + settings | P2 | DONE 2026-10-19 `2bd8155b` | The Appearance panel (theme cards with live miniatures, accents, density), `PATCH /api/auth/me/preferences` with the stored choice winning on sign-in, screenshots of each theme in `docs/ui/`, the Lessons panel (approve/reject); Settings in tabs (BG.5). Run defaults: the start form's choices - delivery mode, model, unattended, approval, the approval timeout, writing in sub-folders, each review point - are kept with the user's preferences when a run starts (`RunDefaults`, known values only), and the form opens with them on any browser (`lib/runDefaults.ts`); Settings → Runs says them in words and can forget them. Not built: the test-call button (see BG.5: no bound below the model's output limit, on a server a live run uses; the status read says whether it is up). Tests: `tests/test_the_start_form_remembers_how_runs_are_started.py` (fails on the old code), `lib/runDefaults.test.ts` |
| UI-S3 plan-first intake | P2 | DONE 2026-10-19 `46e65503` | The start page takes the brief as text, beside its documents or instead of them (H7: documents only before), sent to the run as `brief.md` and kept as a draft in the browser until a run starts; while it is written, "What the run will be held to" lists the acceptance criteria the run will number from it, each "not yet" (`CriteriaPreview.tsx`, `POST /api/runs/preview` - `criteria.number`, the run's own numbering, no model call; a brief listing fewer than two behaviours is told the run will draw them from the product intake); an optional archive of existing code is uploaded to the unused `/codebase` route before the run starts (brownfield); a run created but unable to start is deleted, not left in the list (G9); above Start, a pre-flight line (the model server's own account of itself, BG.5) and one line of what is about to start (delivery and its typical time here, model, supervision, existing code). The choices the page already had stay where they were - run defaults (UI-S5) open it as last used. Not built: three separate steps - the page shows the brief, the criteria, the choices and the summary at once, and a step order would hide the criteria behind a click; a stack suggestion with its support tier before the run - the stack is chosen by the run's first stages from the brief; one `POST /runs/start` - the failure path deletes the orphan instead, which is what G9 asks. Tests: `tests/test_a_brief_shows_its_criteria_before_the_run.py` (fails on the old code), `pages/Home.test.tsx` |
| UI-S6 insights | P3 | DONE 2026-10-19 `c2eca784` | The KPIs every change is measured against were computed by `scripts/loop/kpi.py` inside the worker and kept in the host's `data/kpi/`, outside the API's reach. The computation is in the application now (`observability/run_kpis.py`, moved unchanged; the script imports it, so the ledger's numbers do not move - a test holds `kpi.kpis is run_kpis.kpis`), and the API answers it: `GET /runs/{id}/kpis` from the run's transcript, and `GET /runs/compare?a=&b=` - every numeric KPI of two runs with the change and a `worse` mark by the ledger's own rule (more-is-worse list, 1.5× and its floor; a test holds the application's copy equal to `kpi_ledger.py`'s, which runs on the host without the package). The run page's Audit tab opens with the measures that most often say a run went wrong (identical calls, cache share, lost replies, reverts, defects left open, failed calls) and "Compare with another run"; `/runs/compare` (`pages/Compare.tsx`, also from the palette) shows two runs side by side in words, the worse rows marked. Not built: the ledger's five-run window on the page - the ledger lives on the host, and two runs side by side is what a gate compares. Deploy note: `loop.sh kpi` pipes `kpi.py` into the worker, which needs this module - deploy the worker before the next `loop.sh kpi`. Tests: `tests/test_a_run_s_kpis_are_on_the_page.py` (fails on the old code), `pages/Compare.test.tsx`, `components/AuditTable.test.tsx` |

---

<a id="plan-appendix-4"></a>
## Appendix 4 (2026-10-19, fourth review session): local models on complex products

Evidence base: `docs/review-findings.md` §15 (findings I1–I12),
`data/kpi/run-8b0c94df….json`, the 33 scored runs in `data/bench/`, and the
web research in `docs/research-findings.md` Part R1 (and §15.3 of the review findings). Every initiative below states what KPI (W.4) it
moves and by how much, so the W.2 baseline runs can confirm or refute it.
Format per the owner's request: Goal → Evidence → Files → Steps → Tests
(failing-first, named) → Acceptance → Effort → Depends on. Initiatives
continue the lettering from AW: **AX … BK**. Nothing here re-proposes a
DROPPED item.

<a id="plan-part-17"></a>
### Part 17 — Where the next 10× is (reading the medium run)

On the 1-slot local server the run clock is the model's **decode** time
(I4): 5.22M output tokens ≈ 870 of the ~1,060 model-minutes. Of those output
tokens, 35% were lost replies (I1) and 32% reasoning. Of the 2,593 calls, 87%
were defect-fix loops that fixed 8 of 62 defects (I2). So the order of
attack is:

| lever | finding | expected effect on brief_medium | initiative |
|---|---|---|---|
| stop generating tokens nobody keeps | I1, I6 | −30–40% output tokens, −20% wall | AX, BB |
| stop making calls that fix nothing | I2, I3, I10 | fix-stage calls 100–200 → ≤30 per defect | AY, BC |
| build complex products in slices so the fix loop has a target | I5 | the medium brief converges; defects per round single-digit | AZ |
| re-prefill less | I3, I7 | cached share 0.73 → ≥0.85 | BA |
| keep every request inside the model's effective context | I3, I5, G2 | p95 request input ≤32k tokens | BJ |
| spend less wall time outside the model | I8 | non-model time −50% | BE |
| give an all-local run two tiers | I9 | escalation buys a different behaviour, not a replay | BD |
| know the model you serve; edit the way it can | tool failures 7.3%, P.1 | tool failures ≤3% | BH |
| verify the hard cases with a rubric, never narration | I2 | second-failure fixes > 0 | BI |
| measure composition per call | I11 | makes the above falsifiable | BF |
| UI/UX | I12 | (Part 19) | BG |

<a id="plan-part-18"></a>
### Part 18 — Initiatives

<a id="plan-ax"></a>
#### AX. Reasoning budget per role, enforced by the server per request (N.1 made concrete) — P0

- **Goal.** No reply is ever lost to a reasoning spiral. Each role gets a
  thinking budget in tokens, sent on every request; when the budget is
  reached the server closes the reasoning block and the model answers.
- **Evidence.** I1: 92 lost replies, 1.84M tokens, ≈21% of wall. llama.cpp
  honours per-request `reasoning_budget_tokens` and `reasoning_budget_message`
  since b9982 (PR #23116); `--reasoning-budget` has existed since #13771.
  The owner's rule "launch flags are the owner's" is respected: this is a
  request field, like `max_tokens`, and the owner's server default stands
  for any call that sends none. Caveat from PR #25961's measurements: hard
  cut-offs occasionally fail on some models; the harness must still keep its
  lost-reply fallback (thinking off after the budget is exceeded twice).
- **Files.** `src/app/agents/thinking.py` (budget in `ThinkingPolicy`,
  `openai_arguments(local=…)` adds `extra_body.reasoning_budget_tokens`),
  `src/app/models/server_profile.py` (read `/props` build number; feature flag
  `supports_reasoning_budget`), `src/app/models/roles.py` (per-role budget
  table: build/draft/fix 2–4k, lead/architect 8k, reviews 6k; overridable
  by `THINKING_BUDGET_<ROLE>`), `src/app/agents/settled_answer.py`
  (`LOST_REPLIES_BEFORE_THINKING_STAYS_OFF` becomes "budget exceeded twice"),
  `scripts/loop/reasoning_probe.py` (AR: measure adherence per budget).
- **Steps.** (1) Probe: run `loop.sh reasoning-probe` with budgets 1k/4k/8k on
  the owner's server; record reply length and answer validity. (2) Add the
  capability flag from `/props` (build ≥ b9982 → per-request; older → log a
  one-line advisory naming `--reasoning-budget`). (3) Send the role's budget
  on every call where thinking is on; keep `max_tokens` = budget + answer
  room (`MIN_ANSWER_TOKENS`). (4) On a reply that still ends with
  `finish_reason: length` and only reasoning, retry once at half budget,
  then thinking off for the visit (existing path). (5) KPI: add
  `reasoning_budget_hits` and keep `replies_lost_to_length`.
- **Tests.** `tests/test_a_reasoning_budget_is_sent_per_request.py` (payload
  carries `reasoning_budget_tokens` only when the server profile says so;
  fails on old code because `openai_arguments` never emits it);
  `tests/test_a_role_s_budget_fits_its_reply_ceiling.py` (budget + answer ≤
  ceiling); banned-words test on any new prompt text.
- **Acceptance.** On the next brief_medium run: `replies_lost_to_length ≤ 5`
  and `lost_reply_output_share ≤ 0.05` (from 92 / 0.35); hidden score not
  lower than the baseline.
- **Research backing.** Effort is a real dial on open models (gpt-oss low/medium/high = 37/53/61 SWE-bench Verified; DeepSeek V4 Flash non-think → think-max +5 pts) *and* unbounded default thinking scored worst in Aider's Qwen3 run (49.8%, 58 malformed outputs, ~3× cost); every 2026 harness sets thinking per role/turn (§15.1).
- **Effort.** S (2 days incl. probe).  **Depends on.** server build check;
  AR probe.

<a id="plan-ay"></a>
#### AY. The fix cycle: localise → rewrite → verify, bounded per defect — P0

- **Goal.** A defect costs ≤30 model calls in total and either passes its
  own tests or is left open with a diagnosis; the 40-call agent loop is the
  last resort, not the second step.
- **Evidence.** I2 (8/62 fixed; 100–200 calls per defect; candidates gated
  on a judgement model), I3 (47% redundant reads inside those loops), I10
  (budget re-armed per attempt). The best-performing open harnesses on
  SWE-bench-class tasks all separate *localisation* (where) from *repair*
  (what) and select among several short candidates by running the tests
  (Agentless; the "rollouts + test selection" pattern of 2026 leaderboard
  entries — §15.1). The harness already has every piece: `files_to_fix`,
  `fix_by_rewriting`, `fix_by_candidates`, `_the_defect_s_tests_pass`,
  the language service diagnostics, `after_a_fix`.
- **Files.** `src/app/graph/rewritten_fixes.py`, `src/app/graph/workflow.py`
  (`_fixed_by_rewriting`, `_fix_one`), `src/app/agents/specialists.py`
  (`build_defect_fix_request`), `src/app/sprint/__init__.py` (per-defect call
  ledger), `src/app/agents/settled_answer.py`.
- **Steps.**
  1. **Localise with a cheap structured call before any rewrite**: one
     non-thinking call (≤1.5k output) that returns `{files: [...], symbols:
     [...], hypothesis: "..."}` from the failure text, the stack trace and
     the project map (`project_memory.map_of`), when `files_to_fix` names
     nothing or more than 2 files. Grep the named symbols to confirm.
  2. **Candidates from the same model**: drop the `judgement_model is not
     model` gate; ask 3 candidates with different seeds (llama.cpp honours
     `seed` per request) and `temperature` left at the server's default;
     apply each, run *only the defect's tests* (`_the_defect_s_tests_pass`)
     plus the compiler check, keep the first green, put back otherwise.
  3. **Verify after every write inside the agent loop**: when the loop is
     reached, wrap `write_artifact`/`edit_artifact` so that the defect's own
     test command runs after each successful write and its one-line result
     is appended to the tool result (no model call; the loop sees pass/fail
     immediately instead of running the whole suite itself).
  4. **Per-defect ledger**: a hard cap of 60 calls per defect across all
     attempts (configurable); the target is a mean of ≤ 30 per fix stage
     (Acceptance). When exhausted, record the localisation's hypothesis as
     the defect's diagnosis and leave it open — no fourth conversation.
  5. **Read tool not offered to a fast fix stage whose files are in its
     request** (they are: `fix_request` carries the files and the memory);
     offer `grep` only. The tool list is fixed from the visit's first call
     and never changes mid-visit (BA; Part 22.1 #3).
  6. **One attempt order per defect** (Part 22.1 #4): (1) localise +
     same-model candidates; (2) a fresh-context agent loop with
     verify-after-write; (3) the L.6 whole-file rewrite on the judgement tier
     (BD), fresh context; then open with its diagnosis. L.4's escalation
     after a revert jumps straight to (3).
- **Research backing.** Repair gains come in the first 2–3 attempts and decay 60–80% after (Debugging Decay Index; "How Many Tries"; "Is Three the Magic Number"); fresh-context restarts beat continued debugging (Llama 3.1 8B 72.6→82.8%); test-selected rollouts lift small models 10+ pts without training (R2E-Gym hybrid 34→51; Agentic Rubrics Best@16 on Qwen3-Coder-30B-A3B 39.6→54.2); Factory Droid's minimal tool set is the single biggest harness win measured at fixed model (§15.1).
- **Tests.** `tests/test_a_defect_is_localised_before_it_is_rewritten.py`
  (fails on old code: no localisation call exists);
  `tests/test_candidate_fixes_run_without_a_judgement_model.py`;
  `tests/test_a_write_in_a_fix_loop_is_followed_by_the_defect_s_test.py`;
  `tests/test_a_defect_s_calls_are_bounded_across_attempts.py`.
- **Acceptance.** brief_medium: `defects_fixed / defects_raised ≥ 0.5`,
  mean calls per fix stage ≤ 30, `redundant_read_rate ≤ 0.15`. No
  regression on web-todo (10/10, ≤ 90 min).
- **Effort.** M (1 week).  **Depends on.** AX (budgets) for the loop's
  remaining calls; BF for measurement.

<a id="plan-az"></a>
#### AZ. Walking skeleton first, then vertical slices (complexity scaling) — P0

- **Goal.** A complex brief is built as an ordered list of slices; slice 0 is
  a proven walking skeleton (server starts, one page renders, one route
  round-trips, both test runners run); each later slice owns a few
  acceptance criteria, gets its own slice-scoped specification excerpt and
  drafts, and must be green (its criteria + no regression) before the next
  slice starts. The locked suite stays locked once; only the *scheduling* of
  criteria changes.
- **Evidence.** I5 (30 tests failing at once; fix loop on a broken
  foundation; two app layouts), I2 root cause 4; web-todo's 82-minute
  success is a one-slice product. Anthropic's long-running-agent guidance,
  Codex/OpenHands task decomposition, and SWE-agent's "small, verifiable
  steps" all converge on this (§15.1).
- **Already partly done upstream.** `2d94b84` (every stage told it starts from PORT and DATA_DIR alone) and `99e2fb7` (a shell builtin refused with its reason) cover part of the PATH/"command not found" class; the skeleton proof reuses them (Part 20 note).
- **Research backing.** Anthropic's long-running harness (JSON feature ledger, `init.sh`, session-start smoke test, one feature per session, only the verifier flips `passes`); Terminal-Bench failure taxonomy (PATH/"command not found" 24% of failures — the skeleton proof catches it first); NoLiMa/RULER/Context Rot show open models' effective context is a fraction of the window, so ≤24–32K live context per turn must come from scoping, not compaction (§15.1).
- **Files.** `src/app/agents/scrum_master.py` (`max_sprints_for_criteria_count`
  → slice planner), `src/app/graph/planned_work.py`, `src/app/graph/drafting.py`,
  `src/app/acceptance/sprint_scope.py` (criteria due per slice),
  `src/app/graph/acceptance_nodes.py` (skeleton proof after scaffold),
  `src/app/stacks/contract.py` (the pack's layout is the plan's layout —
  refuse a plan whose top-level folders differ from the scaffold's),
  `src/app/agents/project_memory.py` (focus = slice files first),
  `src/app/agents/specialists.py` (`specification_for_the_work_order` scoped to
  the slice's sections).
- **Steps.** (1) Skeleton proof: after `scaffold`, the harness itself starts
  the product the way the brief says, requests one route/page, runs both
  runners on the smoke tests — a failure here is fixed before any work order
  (fast: by rewriting). (2) Slice plan: the scrum master (build model, no
  thinking) orders criteria into slices of ≤6 with a one-line dependency
  rationale; fast delivery keeps one *sprint record* but runs the build/test
  loop per slice. (3) Slice-scoped requests: drafts and fixes receive only the
  specification sections and memory files that name the slice's files
  (`digest_of` focus) — target ≤15k tokens of spec per request; O.1's
  even sharing applies across the sections the slice keeps (Part 22.1 #5).
  (4) Gate: the
  next slice's drafting starts only when the current slice's due criteria
  pass and no earlier criterion regressed; otherwise the fix cycle (AY) runs
  on the slice's ≤6 defects. (5) Layout coherence: a work order naming a file
  outside the scaffold's top-level folders is rewritten to the scaffold's
  layout before dispatch (planner-side, product-agnostic: the rule is "the
  scaffold's folders", not any framework's).
- **Tests.** `tests/test_a_skeleton_is_proven_before_the_first_work_order.py`,
  `tests/test_a_complex_brief_is_planned_in_slices.py` (fails on old code:
  one sprint for 30 criteria), `tests/test_a_slice_s_request_holds_only_its_sections.py`,
  `tests/test_the_next_slice_waits_for_green.py`,
  `tests/test_a_plan_outside_the_scaffold_s_layout_is_corrected.py`; banned
  words on every new prompt line.
- **Acceptance.** brief_medium completes (status completed, no false
  acceptance) in ≤ 8 h on the local model; acceptance per round rises
  monotonically; `defects_raised` per test round ≤ 8. web-todo unchanged.
- **Effort.** L (2–3 weeks).  **Depends on.** AY; the W.2 baselines for a
  before/after.

<a id="plan-ba"></a>
#### BA. Prefix-cache discipline on a 1-slot server — P1

> **2026-10-22:** absorbed by [PX (Appendix 9)](#plan-px), which keeps this goal and adds the request-layout breaks found in the code (clock in the snapshot, request-dependent memory order, sliding argument truncation, reasoning carry, steering in the system prompt). BF, its dependency, is done.

- **Goal.** `cached_token_share ≥ 0.85` on the local server without touching
  the owner's launch flags.
- **Evidence.** I3 (158 tool-list changes; each one re-renders the system
  prompt on llama.cpp), I7 (conversation interleaving on one slot). The
  llama-server tutorial (#13606) documents prefix-similarity slot selection,
  LRU eviction and the `/slots` save/restore API.
- **Files.** `src/app/agents/settled_answer.py` (withholding: keep the tool
  in the list, refuse at `wrap_tool_call` — note AA.2 dropped *masking*
  because refusals did not stop loops; this is different: refuse *and*
  end the turn with the answer-only notice, so the loop ends while the
  prefix stays stable), `src/app/graph/workflow.py` (serialise
  conversation-switching work while `slots == 1`: fix batches, review
  workers), `src/app/models/server_profile.py` (`/slots` capability),
  `src/app/models/__init__.py` (optional `id_slot` + save/restore around a
  stage visit when `--slot-save-path` is advertised), `src/app/tools/
  agent_toolkit.py` (tool descriptions byte-stable per run).
- **Steps.** (1) Measure: BF's composition record + the server's
  `prompt_cache` usage fields per call. (2) Stable tool list per stage visit;
  withholding becomes a refusal + turn end. (3) Extend AB's rule (fan-out =
  server slots) to every fan-out — drafting, fix workers, review workers —
  so one slot never interleaves conversations; the parallel/linear toggle
  stays as it is (Part 22.1 #7). (4) Slot save/restore when available (advisory to the owner:
  `--slots --slot-save-path /path`; 2–3 slots of ~40k if VRAM allows, for
  the drafting pool). (5) Advise `--cache-reuse 256` for the compaction case.
- **Tests.** `tests/test_a_withheld_tool_does_not_change_the_tool_list.py`
  (fails on old code), `tests/test_fix_batches_run_in_sequence_on_one_slot.py`.
- **Acceptance.** `cached_token_share` 0.73 → ≥ 0.85 on brief_medium;
  effective input tokens −40%.
- **Effort.** M.  **Depends on.** BF.

<a id="plan-bb"></a>
#### BB. The lead plans in parts — P1

- **Goal.** No lead reply carries more than one work order.
- **Evidence.** I6 (364k output tokens, 12 lost replies in one stage; the
  specification already moved to parts and its lost replies stopped).
- **Files.** `src/app/agents/technical_lead.py`, `src/app/graph/workflow.py`
  (`technical_lead_node`), `src/app/graph/planned_work.py`.
- **Steps.** (1) Outline call (no thinking): `[{title, files, owner,
  criteria}]`. (2) One work order per call, several at once on a multi-slot
  server, in sequence on one slot; each validated (definition of ready) on
  arrival and re-asked alone if invalid. (3) The sprint record is rendered
  from the parts, unchanged in shape.
- **Tests.** `tests/test_the_lead_s_plan_is_asked_for_one_order_at_a_time.py`
  (fails on old code: one structured call), definition-of-ready tests
  unchanged.
- **Acceptance.** `technical_lead` lost replies 12 → 0; output tokens per
  plan −50%.
- **Effort.** S–M.  **Depends on.** AX.

<a id="plan-bc"></a>
#### BC. Stop stalls one call earlier — P1

- **Goal.** A repeated read, listing or search is answered *and the turn
  ends with the answer-only notice* instead of costing further calls.
- **Evidence.** I3: 774 pointer answers, 170 held-back reads, each a full
  prefill + reply; stall rules fire at 3/5/8/12.
- **Files.** `src/app/agents/settled_answer.py` (`NOTHING_NEW_BEFORE_THE_ANSWER`
  5 → 2 for a stage whose project memory holds the file; the pointer reply
  carries the answer-only notice), `src/app/agents/project_memory.py`.
- **Tests.** `tests/test_a_second_pointer_answer_ends_the_turn.py` (fails on
  old code).
- **Acceptance.** `identical_call_rate` 0.12 → ≤ 0.05; `redundant_read_rate`
  0.47 → ≤ 0.15 (with AY).
- **Effort.** S.  **Depends on.** —.

<a id="plan-bd"></a>
#### BD. Two tiers from one local server (and a model recommendation to the owner) — P1

- **Goal.** An all-local run escalates to a *different behaviour*: the same
  weights with a larger reasoning budget (AX), or a second model process
  when the owner runs one. Sampling values stay the owner's: no temperature
  or other sampling field is sent (ADR-0008; Part 22.1 #1).
- **Evidence.** I9; HANDOVER §2 notes qwen cloud quota exhausted, so the
  local tier is the real one.
- **Files.** `src/app/models/roles.py` (judgement profile = default endpoint +
  `JUDGEMENT_THINKING_BUDGET`), settings UI (profile
  picker already exists), `docs/HANDOVER.md` §5 (advice).
- **Owner-facing advice (not code):** for the build tier a *non-thinking
  coder* model (e.g. Qwen3-Coder-30B-A3B-Instruct, 256k context, native tool
  calling) and for the judgement tier the thinking model with an 8k budget —
  to be A/B'd on web-todo + notes-api-hono with `loop.sh fitness` and KPIs.
  Rationale: fast delivery's build stages already run with thinking off; a
  model trained for that mode spends no tokens pretending.
- **Tests.** `tests/test_an_all_local_judgement_tier_differs_from_the_build_tier.py`.
- **Acceptance.** escalation success rate measurable (defects fixed after
  escalation > 0 on brief_medium).
- **Effort.** S.  **Depends on.** AX.

<a id="plan-be"></a>
#### BE. One sandbox container per run — P2

- **Goal.** Command start-up cost paid once per run, with isolation kept by
  explicit guards. One container per run would let processes and files
  outside the workspace persist between commands, so (Part 22.1 #8): the
  command's process group is killed after each command, only the workspace
  is mounted, the same limits apply, and each stage gets a fresh container.
  Per-command mode stays a setting. Confirm the live mode first: Compose
  defaults to `container`.
- **Evidence.** I8.
- **Files.** `src/app/tools/sandbox.py` (`docker create … sleep infinity`
  per run with the same flags, `docker exec` per command, removed at run
  end/orphan reclaim), `src/app/server/runner.py` (lifecycle), `scripts/loop/
  run_timing.py` (tool-time by command category).
- **Steps.** measure tool time per category first (BF); implement; keep the
  per-command mode as a fallback setting.
- **Tests.** `tests/test_commands_of_one_run_share_one_container.py`,
  `tests/test_the_run_s_container_is_removed_at_the_end.py`.
- **Acceptance.** non-model wall share 27% → ≤ 15% on brief_medium.
- **Effort.** M.  **Depends on.** BF (tool time by command category).

<a id="plan-bf"></a>
#### BF. Per-call prompt composition in the transcript — P1 (first, cheap)

- **Goal.** Every `model_request` record names its blocks and their sizes:
  system prompt, tool schemas, project memory, spec excerpt, carried notes,
  conversation; plus the server's cache fields.
- **Evidence.** I11.
- **Files.** `src/app/observability/transcript.py`, `src/app/agents/
  project_memory.py`, `src/app/agents/environment_contract.py`, `scripts/
  loop/kpi.py` (new KPIs: `prompt_block_share_*`, `cache_miss_after_tool_change`).
- **Tests.** `tests/test_a_request_record_names_its_blocks.py`.
- **Acceptance.** the next KPI JSON carries block shares; BA/AY/AZ cite them.
- **Effort.** S.  **Depends on.** —.

<a id="plan-bj"></a>
#### BJ. One budget for everything a call carries: memory, rules, plugin instructions and the specification — P1 (after BF)

- **Goal.** Every model request has one input budget for what the harness
  injects, sized for the served model's *effective* context, not its
  advertised window. Project memory, role rules, plugin instructions, the
  environment contract, the workspace digest and the specification excerpt
  share that budget in a fixed priority order; whatever does not fit is
  dropped lowest-priority first and named in one line ("left out: …, ask
  with read_file"), never cut silently.
- **Why.** Each block has its own ceiling today, but nothing caps their sum.
  AZ caps only the specification slice (≤15k tokens). Project memory alone may
  take 30% of the window (`MEMORY_SHARE = 0.3`, up to `MOST_CHARACTERS =
  240_000`); the specification excerpt has a 150k-character default
  (`text_budget.DEFAULT_SPECIFICATION_BUDGET`); role rules and plugin
  instructions sit on top (X.4 measured specialists at ~12.7k characters of
  prompt before any memory). The medium run's largest requests were 73–101k
  tokens (ledger row O.4/Z), far past where open models stay reliable.
- **Evidence.**
  - Research (`docs/research-findings.md` Part R1, techniques #4 and #12):
    open models' effective context is a fraction of the advertised window.
    Qwen3-30B-A3B's RULER effective length is about 64K. NoLiMa and Chroma's
    "Context Rot" show focused short inputs beating long ones on every model
    tested. Frontier harnesses cap injected instructions: Codex
    `project_doc_max_bytes` (32 KiB), Windsurf rule caps, Cline's compact
    prompt for local models (~10% of the full prompt).
  - Review finding G2 (`docs/review-findings.md` §13): memory at the head of
    the conversation was the largest prefix-cache leak and sat in front of
    the brief.
  - Findings I3 and I5: reading is half of the fix loop's work, and the
    medium run's foundation was built from a ~200k-character specification.
- **Files.** `src/app/agents/context_budget.py` (one `InputBudget` per
  request: `effective_window = min(setting, server slot, model registry
  effective length)`, target ≤ 32k tokens for ≤35B models unless measured
  otherwise), `src/app/agents/project_memory.py` (memory takes what is left
  after higher-priority blocks, not a fixed 30%),
  `src/app/plugins/middleware.py` (plugin instructions under a cap, with
  role- and path-scoped selection), `src/app/agents/text_budget.py`,
  `src/app/agents/role_agent.py` (a compact rules variant for local models,
  chosen by the BH registry, not by model name in code).
- **Steps.** (1) BF first: record each block's size per call. (2) Set the
  priority: work order and failing evidence > role rules > environment
  contract > specification slice > memory of named files > plugin
  instructions > rest of memory > digest tail. (3) Enforce the sum in
  middleware; name what was left out. (4) Add the compact rules variant and
  A/B it with `kpi_ledger.py compare`.
- **Tests.** `tests/test_no_request_carries_more_than_its_input_budget.py`
  (builds a role agent with a large memory, many plugin keys and a long
  specification; fails on the old code where the sum exceeds the budget);
  `tests/test_what_the_budget_leaves_out_is_named.py`. Each new prompt line
  is tested against the banned words (task, tasks, to-do, todo, button,
  click, checkbox).
- **Acceptance.** injected blocks (everything but the conversation) ≤ 16k
  tokens on every request of brief_medium, with no rise in
  `redundant_read_rate` and a fix ratio not lower than the baseline. The p95
  *total* request input is reported with a target of ≤ 32k, reached through
  AY's bounded attempts and AZ's slices, not compaction (Z stays not built
  unless BF shows conversation growth dominates; Part 22.1 #6). Judged on at
  least two runs (Part 20 rule).
- **Effort.** M.  **Depends on.** BF; works with AZ (slice scope) and BA
  (stable block order).

<a id="plan-bk"></a>
#### BK. A release without its packaged CI or container files is a completion gap — P1

- **Goal.** When the release files a stack pack provides could not be
  written, the run finishes as completed *with gaps*, not plain completed.
  The handoff then says what is missing in the same place every other gap is
  listed (`completion_gaps`, the evidence page, the bench export). A
  custom-stack run (no pack) is unchanged: its support tier is already
  stated on the evidence page (AG), and it was never promised release files.
- **Why.** The external review of 2026-10-17 (item 6, recorded in Part 22)
  found that release packaging is best-effort. It was checked against the
  code on 2026-10-19:
  - `stacks/release.py` catches the error and fills `outcome.missing`.
  - `graph/delivery.py` puts that text into the release *decision's*
    rationale only.
  - `completion_gaps` is computed *before* the release files are written, so
    a failed packaging step never reaches it. The run reads as plain
    `completed`, and so do the run list, the evidence page's "Completion
    gaps" section and the bench export.
  - This is the J.4/J.5 rule ("records cite the verdict") applied to the
    last step of the run.
- **Evidence.** `src/app/stacks/release.py` (`write`, the `except` branch at
  "a release is not held back by its packaging"); `src/app/graph/delivery.py`
  (`release`: gaps assembled, then `release_files.write(root).describe()`).
- **Files.** `src/app/graph/delivery.py` (write the release files before the
  gaps are stored, and add `outcome.missing` to `gaps` when set),
  `src/app/stacks/release.py` (unchanged behaviour: never hold the release
  back).
- **Tests.** `tests/test_a_release_whose_files_failed_is_completed_with_gaps.py`
  (makes a file write inside `release.write` fail; fails on the old code because
  `completion_gaps` stays empty).
- **Acceptance.** a forced packaging failure shows in `completion_gaps`, the
  evidence page and `score.py`'s export. No change on a clean release.
- **Effort.** S.  **Depends on.** —.

<a id="plan-bh"></a>
#### BH. Model registry: parser, template, sampling, thinking and edit format per model family, measured by `fitness` — P1

- **Goal.** The harness knows, per served model, which tool-call protocol the
  server parses (hermes / qwen3_coder XML / mistral / glm / harmony), which
  thinking switch and budget it honours, its recommended sampling per mode (advisory only: printed by `ready`, never sent — ADR-0008),
  and — **measured, not assumed** — its well-formed rate for whole-file
  replies vs search/replace edits; `write_artifact` vs `edit_artifact` are
  then *preferred* per model (whole-file below ~300 lines when search/replace
  well-formed rate < 95%).
- **Evidence.** HANDOVER §2 "returns an invented tool name even with
  `tool_choice: required`"; `replace_lines` 40–68% failed (P.1); Aider:
  `whole` 100% well-formed vs `diff` 92–95% on Qwen3-235B, lenient matching
  ≈9× fewer edit errors; vLLM/llama.cpp require the family's parser and warn
  "protocol adherence isn't guaranteed"; Kilo/Cline: local models are "more
  prone to loops, tool-use failures, and syntax errors" (§15.1).
- **Files.** `src/app/models/fitness.py` (extend the five scripted calls with
  a 10-edit well-formed probe: whole vs search/replace on 3 sample files),
  `src/app/models/server_profile.py` (family detection from `/props` model
  name + template), new `src/app/models/registry.py` (data file, per family:
  parser, thinking switch, budget support, sampling-by-mode advisory, edit
  preference), `src/app/agents/role_agent.py` (`_WRITING_RULES` rendered per
  edit preference — "revise by rewriting the whole file" for a model whose
  edits malform), `src/app/plugins/seed.py` untouched (no stack specifics).
- **Steps.** (1) registry data + detection; (2) fitness probe writes the
  measured rates to `/app/data/model-fitness/<model>.json`; (3) tool
  preference and prompt text follow the measurement; (4) `loop.sh ready`
  prints the profile (family, parser, thinking budget support, edit
  preference, context ≥ 32k).
- **Tests.** `tests/test_a_model_s_edit_preference_follows_its_measured_rate.py`
  (fails on old code: no preference exists), `tests/test_an_unknown_family_gets_the_generic_profile.py`.
- **Acceptance.** `tool_failure_rate` 0.073 → ≤ 0.03; `layer_edit_*`
  interventions −50%.
- **Effort.** M.  **Depends on.** —.

<a id="plan-bi"></a>
#### BI. Rubric-graded verification for the hardest work orders — P2

- **Goal.** For a work order or defect that failed twice, the architect
  writes a repo-grounded weighted rubric (file-change / spec-alignment /
  integrity / runtime axes) at dispatch; k=2–3 short candidates are graded
  by the deterministic tests first and the rubric second (thinking judge,
  pairwise); the judge never marks anything passing alone.
- **Evidence.** Agentic Rubrics: rubric + weak judge is the best verifier
  (+4 pts Best@16 over tests alone at ~half the cost); execution-free judges
  overweight the agent's narration; CodeJudgeBench: thinking judges, pairwise
  > pointwise (§15.1). The harness already distrusts narration (Q.4 write
  receipts, J.1 vacuous-green gate).
- **Files.** `src/app/agents/principal_architect.py` (rubric field per work
  order, strict lines), `src/app/graph/rewritten_fixes.py` (`fix_by_candidates`
  ranks by tests then rubric), new `src/app/agents/rubric_judge.py`.
- **Tests.** `tests/test_a_rubric_never_passes_a_candidate_the_tests_fail.py`,
  `tests/test_candidates_are_ranked_by_tests_then_rubric.py`.
- **Acceptance.** on brief_medium, defects fixed after a second failure > 0;
  no rise in false acceptance (W.1 rule).
- **Effort.** M.  **Depends on.** AY.

<a id="plan-bg"></a>
#### BG. UI/UX — see Part 19.

<a id="plan-part-19"></a>
### Part 19 — UI/UX (fourth pass): from a status page to a control room

Evidence: §15.2 (I12.1–I12.12). Effort S ≤ 1 day, M 2–4 days, L ≥ 1 week.
"Backend" names the 15.5 enabler or the new route an item needs. Items refine
or pull forward the open UI-S/UI-0/UI-P rows; none duplicates a DONE row.

<a id="plan-bg-1"></a>
#### BG.1 Progress, tokens and "not priced" in the summary card — P1, S, no backend now
- **Goal.** Above the fold: "Sprint 1 of 3 · Testing (round 2) · 2 h 14 m
  elapsed · typically 7.6 h for fast runs here (1.4–12.7)"; a token `Stat`
  pair ("1.2 M tokens · 0.9 M in · 0.3 M out") and "Spend: not priced (local
  model)" when `!fully_priced`; a budget bar when `MAX_RUN_TOKENS` /
  `MAX_RUN_COST_USD` are set (ceiling added to the run payload, S backend).
- **Files.** `RunDashboard.tsx:656-699`, `SprintSummaryPanel.tsx:77`,
  `types/index.ts:41-44`, `api/index.ts:118`; later `/usage` (15.5).
- **Tests.** Vitest: summary renders tokens and "not priced" for an unpriced
  run; forecast line uses `/outcomes` medians. **Acceptance.** a 19-hour
  screenshot answers "how far, how long, how much" without scrolling.

<a id="plan-bg-2"></a>
#### BG.2 Needs-you inbox + notifications — P1, M, no backend (completes UI-0, UI-S1)
- Dropdown with one actionable row per waiting run ("run-8b0c… · Release
  review · approves itself at 09:40", one-tap Approve); count only live runs
  (`useNeedsYou.ts:40`); favicon badge (canvas); opt-in browser
  `Notification` on `waiting_*`, `failed`, `completed` from any page.
- **Tests.** count excludes terminal/dismissed runs; notification requested
  only after opt-in. **Acceptance.** a self-approving gate is never silent.

<a id="plan-bg-3"></a>
#### BG.3 Gates as a composer with the artifact inline — P1, M (UI-S4 composer, pulled forward)
- Render the reviewed document in place (`fetchArtifactContent`, `Markdown`/
  `ArtifactViewer`), revision diff when `revision > 1` (artifact versions
  endpoint, 15.5), comment box, approve / request changes / skip as the
  composer; steering folded into the same composer with the upcoming stage
  named and the note echoed in the feed when `applied_stage` is set.
- **Files.** `ReviewPanel.tsx`, `ApprovalGate.tsx`, `SteeringBox.tsx`.
- **Acceptance.** no gate asks for download→edit→re-upload.

<a id="plan-bg-4"></a>
#### BG.4 Rail / work area / ledger layout with real tabs — P1, L (= UI-S4 layout)
- Left rail: run identity, progress strip (BG.1), stage stepper with
  per-stage time (+ tokens once `/usage` exists), newest-commit chip from
  `/changes` ("3 files · +120/−8"); centre: tabs (Activity / Changes / Log /
  Artifacts / Audit) with `role=tablist` + arrow keys; right: the criteria
  ledger (Delivery) and decisions; gates render as a banner above the work
  area. Collapse steering to a one-line "Steer…" until BG.3 lands.
- **Acceptance.** everything actionable visible at 1366×768 without scroll;
  axe ≤ 5 per theme kept.

<a id="plan-bg-5"></a>
#### BG.5 Model-server surface — P1, S UI + S backend (refines UI-S5)
- New read-only `GET /api/health/server` returning the cached `/props` probe
  (model, quant, slots, context as started, last probe time, which run holds
  the slot) — no model call. Header dot + tooltip; Settings → Models first
  (tabs: Models / Appearance / Runs / Lessons / Account) with a "Test call"
  button; intake and run page say "waits for run X to free the model" when
  slots = 1 and another run is `running`.
- **Files.** `src/app/models/server_profile.py`, `src/app/server/api.py`,
  `Settings.tsx`, `Layout.tsx`, `Home.tsx`.

<a id="plan-bg-6"></a>
#### BG.6 Fix-loop and sprint data from structured endpoints — P1, S UI + S backend (new row)
- Render `RemediationInfo` ("Fix attempt 2 of 3 · 23 defects, 9 open · tests
  4/30 → 9/30") while `current_stage` matches `defect_fix*`/`test_round*`;
  label the sprint-row icons; replace `parseSummary` with
  `GET /runs/{id}/sprints` (the engine renders the summary — emit the JSON
  it is rendered from).

<a id="plan-bg-7"></a>
#### BG.7 Audit tab — P2, M UI (refines UI-S6; pull the per-run half forward)
- Stage × (wall, model-busy, calls, in/out/cached tokens, lost replies,
  redundant reads, tool failures) from `/usage` + `/kpi` (15.5), worst cell
  per column highlighted; "Download transcript" beside "Handover pack"
  (`GET /runs/{id}/transcript`); "Open in transcript" per feed row. This is
  the UI for AX/AY/BA/BF's acceptance numbers.

<a id="plan-bg-8"></a>
#### BG.8 Feed: live classification and lanes — P2, S, no backend (new)
- Classify tool results with the `LAYERS` markers (shared constant): muted
  "held back: already read", "reply cut off" chips; lane chips "backend ·
  frontend · testing" filtering by the event's `stage` prefix; render
  `review_decision` events in order ("chose FastAPI because …").

<a id="plan-bg-9"></a>
#### BG.9 Changes per file + criterion link — P2, M (= UI-S4 Changes, extended)
- File tree per commit, collapsible hunks, syntax colouring; link from a
  criterion's first passing test to the commit (commit↔criterion mapping
  from the suite result timestamps, S backend).

<a id="plan-bg-10"></a>
#### BG.10 Plan-first intake with pre-flight — P2, L (= UI-S3)
- Brief as text and/or files; pre-flight card from `/health/ready` +
  `/settings` ("Build model … 1 slot, 126 k context — ready"); review step
  showing the criteria ledger as "not yet" rows and the slice plan (AZ)
  before Start; one `POST /runs/start`.

<a id="plan-bg-11"></a>
#### BG.11 Copy and stage names from the graph — P2, S (= UI-S4 open)
- `STAGE_COPY` generated from the graph's node list so no H1 renders a raw
  stage id; product vocabulary (brief, build, run, gate) across screens.

<a id="plan-bg-12"></a>
#### BG.12 Visual residue — P2, S (refines UI-T5)
- Remove `.glass-card`/`backdrop-filter`/`.gradient-btn`/hero; type scale
  12 px floor; contrast theme borders only interactive/container elements;
  every number labelled with its source.

<a id="plan-bg-13"></a>
#### BG.13 Accessibility and polling — P2, S
- Real tabs; `group-focus-within` on hover-only affordances;
  `aria-expanded` on disclosure rows; `aria-live` off on the log with a
  separate live region for `agent_message` headlines and status; label the
  rewind control; `/events?since` on reconnect only and no `/logs` paging
  after replay; one `/runs/{id}/summary` aggregate replacing four panel
  polls; `loading="lazy"` on screenshot thumbnails.

<a id="plan-bg-14"></a>
#### BG.14 Timeline scrubber / replay — P3, M, no backend (new)
- Stage ticks, gate markers, steering notes, rewind points above the feed;
  clicking scrolls the feed and filters Changes to that moment.

<a id="plan-bg-15"></a>
#### BG.15 Context pressure and throughput — P3, S UI (refines UI-S6)
- "Last call used 94 k of 126 k context" (red > 90%), output tok/s sparkline
  over the last hour, "model busy 71% of the last 10 min" in the rail — needs
  per-call fields in `/usage`.

<a id="plan-bg-16"></a>
#### BG.16 Command palette, shortcuts, cross-run compare — P3, M (= UI-S1, UI-S6)

**Housekeeping.** Regenerate `docs/ui/*-runs.png`; `vite.config.ts:11` →
:8000; delete `wizardData.ts`, `DynamicWorkflowUI.tsx`, `App.css`;
`Home.tsx:84` reviewer hard-code.

<a id="plan-part-20"></a>
### Part 20 — Implementation sequence

Prerequisites: the W.2 baselines and the AR probe (Part 21, stage 0). The
single order for all open items is Part 21.

| wave | items | gate |
|---|---|---|
| 0 (1 week) | BF, AX, BC | brief_medium KPI: lost replies ≤5, identical calls ≤5% |
| 1 (1–2 weeks) | AY, BB, BD, BH, BJ | fix ratio ≥0.5, lead lost replies 0, tool failures ≤3%, p95 request input ≤32k tokens |
| 2 (2–3 weeks) | AZ, BA, BG.1–BG.6 | brief_medium completes ≤8 h, cache ≥0.85 |
| 3 | BE, BI, BG.7–BG.16 | non-model share ≤15% |

**How a wave's gate is judged (added 2026-10-19).** Agent runs on the same
brief vary widely: the scored results in `data/bench/` differ a lot between
runs of the same benchmark, and model sampling alone changes a run's path.
A single run therefore cannot pass or fail a wave. Each gate needs **at least two runs** of
brief_medium on the new code, compared with the W.2 baselines through
`kpi_ledger.py compare`. A KPI counts as moved only when both runs move it in
the same direction, past the 1.5× regression band W.4 already uses. When the
two runs disagree, a third run decides. Model time is the owner's: these
runs follow owner decision 2 (between owner runs, never during one).

**Already partly done upstream (2026-10-19).** Two commits after this review
close part of the largest Terminal-Bench failure class ("command not found" /
PATH, 24% of failures). "every stage is told it starts from PORT and
DATA_DIR alone" (`2d94b84`) tells every stage it starts with PORT and
DATA_DIR only. "A shell builtin is refused with the reason" (`99e2fb7`)
explains why a shell builtin carries nothing to the next command. AZ's
skeleton proof should reuse these messages rather than add new ones.

<a id="plan-part-21"></a>
### Part 21 — One implementation order for every open item (2026-10-19)

This order replaces the separate sequences in §4 (the original roadmap),
Part 16 (Appendix 3) and Part 20 (Appendix 4); their gates still apply.
Items marked done, dropped or not built in Appendix M are not listed. A
stage starts when its prerequisites are met. The UI track can run beside
stages 1–5 in a second session.

| Stage | Items (in order) | Prerequisite | Gate to the next stage |
|---|---|---|---|
| 0 Baseline (owner) | **W.2** baselines in the decided order: fast notes-api-hono → fast fullstack-bookmarks-py → thorough; **AR** reasoning probe between runs | `loop.sh ready` = ALL READY | KPI JSON and ledger rows for each baseline; AR's table says whether the server honours a per-request budget |
| 1 Measure, then cheap fixes | **BF** → **BC** → **BK** → **AQ** (instrumented reads) → **AO.9**, **AO.10** remainders → **AO.5** (needs the baseline data) | stage 0 | composition shares in the KPI JSON; identical-call rate ≤ 5% |
| 2 Tokens nobody keeps | **AX** (only if AR shows the budget is honoured; otherwise advisory to the owner) → **BB** → **BH** → **BD** | BF, AR | lost replies ≤ 5; lead lost replies 0; tool failures ≤ 3% |
| 3 The fix loop | **AY** → **BI** | AX, BF | fix ratio ≥ 0.5; mean calls per fix stage ≤ 30 |
| 4 Context and cache | **BJ** → **BA** | BF, AY | injected blocks ≤ 16k tokens per request; cached share ≥ 0.85 |
| 5 Complex products | **AZ** | AY, BJ, W.2 | brief_medium completes in ≤ 8 h with no false acceptance |
| 6 Packs and contracts | **K.6 = AW** (one item, two rows) → **AU** → **B** remainder (overlap audit) → **U.1** service-backed bench | stage 5 gate, owner decision 10 | a second bench family scored under the same KPIs |
| 7 Infrastructure | **BE** → **T** spike → **S** remainder (mid-run health telemetry) → **M.4–M.6** remainders | BF (tool time by category) | non-model wall share ≤ 15% |
| 8 Optional | **Q-amend** (default off; benchmark before any default change); **G** Unicode half (4 of 280 misses, small) | — | — |
| Last | **Part 12 / V** refactor track | two clean benchmark families | no behaviour change (suite green, KPIs within band) |
| UI track | **UI-0** remainder → **UI-P** primitive kit → **UI-S1/S2** remainder → **BG.1, BG.2, BG.5, BG.6** with the Part 4 and 15.5 backend enablers → **UI-S4 = BG.3 + BG.4** (one piece of work) → **UI-T4–T6/S5** remainder → **BG.7–BG.9, BG.11–BG.13** → **UI-S3 = BG.10** → **UI-S6 + BG.14–BG.16** | UI-P before any new screen | axe ≤ 5 per theme; contrast script green; Playwright flows of Part 15.6 |

Every stage keeps the standing rules (`AGENTS.md`):
- every fix has a test proven to fail on the old code;
- no stack specifics outside packs and `plugins/seed.py`;
- no run ids in code, comments, prompts or tests;
- banned words tested on every new prompt line;
- both handovers updated in the same commit;
- the model and its settings stay the owner's.

Each stage's gate is judged by the two-run rule (Part 20).

*Added 2026-10-22 (Appendix 8, customer stacks, SAP, templates, legacy docs):*
- **Group 1, now:** SL.1–SL.4, SL.6–SL.8, RV.1–RV.6, EN.2–EN.6, EN.8–EN.11 (EN.1 via MT), MT.1–MT.10 in the MT sequence when the owner schedules it, SAP.6–SAP.7, DT.1–DT.4, DT.6, RD.2, RD.4, RD.7.
- **Group 2, behind switches:** SL.5, EN.7, SAP.1 → SAP.2 → SAP.3, SAP.4 → SAP.5, DT.5, RD.1, RD.3, RD.5, RD.6.

*Added 2026-10-21 (Appendix 7, the discipline layer):*
- **Group 1, now, before the next Measure cycle:** MF.1–MF.6 → RC.1–RC.3 → OP.1–OP.4 → CH.1–CH.3 → IN.2, BW.3, EV.1, SF.1–SF.2.
- **Group 2, after the measured runs:** IN.1, BW.1–BW.2, PN.1–PN.2, EV.2.
- **CH.4** after the first clean Measure cycle.

*Added 2026-10-21 (Appendix 6):*
- **PH.2**, **PH.3** → stage 3 after AY.
- **PH.1**, **CG.1–CG.2** → stage 4 after BJ and CM.2.
- **RL.1–RL.3** → stage 7; **RL.4** from now.
- **CG.3–CG.4**, **PH.4** → stage 8.
- **CG.5** → UI track after BG.3/BG.4.

*Added 2026-10-20 (Appendix 6):*
- **CM.1** → stage 1.
- **CM.2**, **CM.3** → stage 4 after BJ.
- **CM.4** → stage 8.
- **OS.0–OS.6** → stage 7.

<a id="plan-part-22"></a>
### Part 22 — Consistency review before implementing everything (2026-10-19)

The whole plan was read for contradictions before the owner implements it.
Each contradiction below has been resolved in the item's own text, so the
initiative sections are the ones to follow.

#### 22.1 Contradictions found and how each is resolved

| # | Contradiction | Resolution (edited in place) |
|---|---|---|
| 1 | **BD** gave the judgement tier "lower temperature", and **AY** asks for candidates with different seeds. Per-request sampling was dropped by owner rule (M.3, decision 12). | ADR-0008 now lists which per-request fields the harness may send: `max_tokens`, the thinking switch and effort (already sent), a reasoning budget (AX) and `seed`. Temperature, top-p/k, min-p and penalties are never sent. BD's temperature is removed. BH's sampling-per-mode stays advisory only (printed by `ready`, never sent). |
| 2 | **AY**'s Goal says ≤ 30 calls per defect, but its step 4 says ≤ 60. | A hard cap of 60 calls per defect across attempts; the target is a mean of ≤ 30 per fix stage (the acceptance). |
| 3 | **AY** step 5 withholds the read tool from a fix stage, while **BA** requires a stable tool list. | Allowed when the list is fixed from the visit's first call. A tool is never removed mid-visit; mid-visit withholding is a refusal plus turn end (BA). |
| 4 | **AY**'s "fresh context after 2–3 attempts" overlapped with L.6 (the last attempt changes strategy), L.4/`escalate_after()` (judgement escalation) and the existing retries. | One order per defect, written into AY: (1) localise + same-model candidates; (2) a fresh-context agent loop with verify-after-write; (3) the L.6 whole-file rewrite on the judgement tier (BD), fresh context; then the defect stays open with its diagnosis. |
| 5 | **AZ** gives each request only the slice's specification sections (≤ 15k tokens), while **O.1** (done) shares the excerpt evenly across *every* section. | O.1 applies inside the slice: every section that names the slice's files is kept, sharing the slice budget evenly. A one-slice product keeps O.1 as built. |
| 6 | **BJ** set p95 request input ≤ 32k tokens, but compaction (Z/O.4) is deliberately not built, so a long fix conversation could not meet it. | BJ's gate is on what the harness injects (≤ 16k tokens per request). The 32k p95 is a reported target, reached through AY's bounded attempts and AZ's slices. Z is revisited only if BF shows conversation growth dominates. |
| 7 | **BA** step 3 "serialise when slots == 1" read as switching parallel mode off, and the parallel/linear toggle is an owner feature. | BA extends AB's existing rule (fan-out = server slots) to every fan-out: drafting, fix workers, review workers. The toggle stays and nothing is removed. |
| 8 | **BE** says "same isolation", but one container per run lets processes and files outside the workspace persist between commands. | BE now states the trade-off and its guards. Kill the command's process group after each command, mount only the workspace, keep the same limits, and give each stage a fresh container. Per-command mode stays a setting. Depends on BF. |
| 9 | **Part 20** wave 0 could start before the W.2 baselines exist, so the two-run comparison would have nothing to compare against. | Part 21 stage 0 makes W.2 and AR prerequisites. |
| 10 | **AX** (budget on every request) vs fast delivery ("build stages run with reasoning off") and BB's outline call (no thinking). | No conflict once stated: AX's budgets apply only where thinking is on. Fast build stages and BB's outline stay off; the build/draft budget applies in thorough delivery and to fixes. |
| 11 | **PRODUCT.md §7** said the deployment runs commands in-container. Compose and `.env.example` default to `container`, and the X.3 ledger row says the deployment uses container mode. **BE** depends on which one is true. | PRODUCT §7 corrected: container mode by default. The owner confirms the live `.env` with `loop.sh ready` before BE. |
| 12 | Three sequences (§4, Part 16, Part 20) disagreed on order. | Part 21 is the single order. |

#### 22.2 Duplicates — implement once

| Same work | Rows |
|---|---|
| Stack-shaped checks as pack data | K.6 and AW |
| Control room layout and gate composer | UI-S4 and BG.3, BG.4 |
| Plan-first intake | UI-S3 and BG.10 |
| Insights, palette and cross-run compare | UI-S6 and BG.7, BG.14–BG.16 |
| Reasoning budget | N.1 (measure-first), AR (probe) and AX (the build) |
| Candidate fixes | E1 #6 / pillar 8 history, AY step 2 and BI (BI ranks AY's candidates when tests cannot choose) |
| Repeated reads | AQ (hypotheses), BC (stall stop) and AY step 5 |

#### 22.3 Do not implement (rejected by measurement or by the owner)

These stay in the plan for their history, but implementing them would
contradict a recorded decision:
- **L.2** file-granular revert (premise false);
- **M.2** control-plane `response_format` (no parse failures measured);
- **M.3** sampling presets (owner rule);
- **AC.3** check memoisation (measured);
- **AA.2** tool masking (refusals did not stop loops; BA's refusal + turn end replaces it);
- **O.4/Z** compaction (never fires; would break the prefix cache) unless BF reverses that;
- **Y** edit-format change (measured, no change; BH replaces it with a measured per-model preference);
- **N.3** (premise false);
- **U.4** automatic retention (owner decision 12).

**M-bash** stays parked: it is only for models with no native tool calling,
and the owner's current model has native tool calling.

Superseded items of section E (E1 #2, #3; E2 pillars 5, 8) are built in
their later form: AI/AT, fast delivery, L.1/AY.

#### 22.4 The external review of 2026-10-17 (formerly `docs/logs.md`)

The owner removed `docs/logs.md` on 2026-10-19. It held an external code
review; every recommendation in it is covered here:

| # | Recommendation | Covered by | Status |
|---|---|---|---|
| 1 | Fail early when a run cannot run commands; label planning-only deployments | AH.4 run-readiness check; `loop.sh ready` prints `READY commands` | DONE |
| 2 | Independent test strength: mutation testing, hidden human-written tests, false acceptance measured, a broader corpus | AF mutation probe; `benchmarks/` hidden tests; `bench/report.py`; U.1 | DONE; U.1 PARTLY (stage 6) |
| 3 | State the supported boundary as capability tiers | AG support tiers | DONE |
| 4 | Partial pricing is not a hard cap | AH.1 labelled cap + `MAX_RUN_TOKENS` | DONE |
| 5 | Deletion and retention cover transcripts and object-store copies | AH.2 (`run_retention`), U.4 not built by owner decision | DONE |
| 6a | A judgement model that failed to build must show as a downgrade | AH.3, AO.7 | DONE |
| 6b | The security review must report what it skipped | AH.3 (it lists the files its budget left out) | DONE |
| 6c | Release packaging is best-effort and not reported as a gap | **BK** | DONE 2026-10-19 `1d6a4e1` |
| — | No broad rewrite before the benchmark gate holds; refactor later behind typed contracts | Part 12 / V, last in Part 21 | NOT STARTED (by design) |

<a id="plan-ledger-a4"></a>
### Appendix 4 rows (Implementation Progress Ledger continuation)

| Item | Priority | Status | Notes |
|---|---|---|---|
| AX reasoning budget per role | P0 | NOT BUILT 2026-10-19 (AR: no per-request budget) | AR showed the server ignores a per-request reasoning budget and effort. Advice to the owner, not code: a server-wide reasoning budget is a server flag (the owner's), or a server build that honours a per-request budget (the plan names build ≥ b9982); then re-run `loop.sh reasoning-probe run` and AX can be built as profile data. Fast build stages already run with thinking off, the one switch the server honours |
| AY bounded fix cycle | P0 | NOT STARTED | |
| AZ skeleton + slices | P0 | NOT STARTED | after AY |
| BA prefix-cache discipline | P1 | ABSORBED 2026-10-22 by PX (Appendix 9) | after BF (done) |
| BB lead plans in parts | P1 | NOT STARTED | |
| BC stalls end one call earlier | P1 | DONE 2026-10-19 `f47f685` | two pointer answers in a row (`POINTERS_BEFORE_THE_ANSWER = 2`, `settled_answer._pointed_lately`) stall the stage: a writer keeps only its writers, a reader only its answer; the pointer itself now says a second one ends reading. Test `tests/test_a_second_pointer_answer_ends_the_turn.py` (the two stall tests fail on the old code); `test_a_few_pointers_take_nothing_away` now spaces its pointers with writes. Deployed after the W.2 baselines |
| BD two local tiers + model advice | P1 | NOT STARTED | owner's A/B |
| BE one container per run | P2 | NOT STARTED | |
| BF prompt composition record | P1 | DONE 2026-10-19 `ab2afae` | every `model_request` carries `blocks` (system, environment_contract, tool_schemas, project_memory, workspace, specification, request, notes, conversation; characters, summing to the request); the memory marks its length in `additional_kwargs` (never sent); `kpi.py` adds `prompt_block_share_*` and `cache_miss_after_tool_change`. Test `tests/test_a_request_record_names_its_blocks.py`: 4 of 5 fail on the old code. Deployed after the W.2 baselines |
| BH model registry + measured edit preference | P1 | PARTLY 2026-10-19 `9339c7d`: registry and measurement DONE (group 1); the preference applied to tools and prompts waits for group 2 | `app.models.registry`: per family (qwen3, qwen3-coder, mistral, glm, gpt-oss, llama, deepseek; generic otherwise) the server parser, the thinking switch, whether a per-request budget is known honoured, and the makers' sampling as advice never sent. `fitness.edit_probe` asks 3 sample files x 2 rounds as whole-file writes and as find-and-replace edits and keeps the well-formed rates under `DATA_DIR/model-fitness/` (`loop.sh fitness --edits`, between runs only); `registry.edit_preference` reads them (whole files below 95% well-formed edits). `loop.sh ready` prints a MODEL line with all of it. Not yet: `_WRITING_RULES` and tool preference following the measurement (step 3) - a behaviour change, group 2. Tests: `tests/test_a_model_s_edit_preference_follows_its_measured_rate.py`, `tests/test_an_unknown_family_gets_the_generic_profile.py` (fail on the old code) |
| BI rubric-graded candidates | P2 | NOT STARTED | after AY |
| BG.1 progress/tokens in summary | P1 | DONE 2026-10-19 `b96ee212` | The run page's summary card (`components/RunFigures.tsx`, `lib/runSummary.ts`): tokens with in and out ("1.2 M", "900.0 k in · 300.0 k out"); the spend as "not priced" when no call had a known price, never "$0.00", and "$1.50 + 3 unpriced" when some had; under the elapsed time, "typically 7.6 h for fast runs here (1.4-13 h, 5 runs)" from `/runs/outcomes`; a bar for each ceiling the deployment sets. Small backend: the run payload carries `max_run_tokens` and `max_run_cost_usd` (null when unset; the API reads the same environment as the worker). Not built here: "Sprint 1 of 3" - the payload has no sprint index; it comes with BG.6's sprint endpoint. Tests: `lib/runSummary.test.ts`, `components/RunFigures.test.tsx`, `tests/test_the_model_server_s_health_is_read_without_a_model_call.py` (the ceilings on the payload; fails on the old code) |
| BG.2 needs-you inbox + notifications | P1 | DONE 2026-10-19 `6ffed0f` | The header's needs-you pill is now an inbox (`components/NeedsYouInbox.tsx`): one row per live waiting run - which run, the stage, and what happens next on its own line, never cut ("approves itself at 09:40" in the warning colour, "waits for you", "stopped at its budget") - with one-tap Approve for a gate or a review and Open for a budget stop; then the runs that failed since the Runs page was opened; a row can be hidden until its run moves. The count is live waiting runs only (a failed run waits for nothing). `/api/runs` carries each run's `gate_deadline`, so one list call fills it. The count goes on the tab (`(2) …` in the title, kept in front of any page's own, and a canvas dot on the favicon, `lib/tabBadge.ts`). Browser notifications on waiting, failed and finished are off until the owner ticks them, and the permission prompt comes only from that tick (`lib/notify.ts`); once on, the poll goes on at 60 s while the tab is hidden. The panel is on `/dev/ui` with sample runs: axe 0 in every theme, contrast 650 pairs hold, no horizontal scroll at 375 px. Tests: `lib/needsYou.test.ts` (count excludes terminal and dismissed runs; the deadline is never cut), `lib/notify.test.ts` (no prompt before the opt-in), `lib/tabBadge.test.ts`, `components/NeedsYouInbox.test.tsx`; `tests/test_a_waiting_gate_says_when_it_approves_itself.py` (the list carries the deadline; fails on the old code) |
| BG.3 gates as composer, artifact inline | P1 | DONE 2026-10-19 `b96ee212` | A review is a composer (`components/ReviewPanel.tsx`): the reviewed document in place (`GateDocument.tsx`, markdown rendered), and from revision 2 a "What changed" tab with the diff since the version before; one comment box; Approve, Request changes (needs a comment or an edited copy), Skip. Replacing the document with an edited copy is folded under "Replace it with your own version" - no review asks for download, edit, upload. Backend: the review payload names its document (`_the_review_document`: the workspace file the workflow wrote for that review point), and `GET /runs/{id}/artifacts/diff?path=` (`changes.document_diff`) gives one file's change since its newest committed version that differs from it now - read-only git, the path checked to stay in the workspace and taken literally, never as a pattern; this is the "artifact versions" enabler, from the history every stage already commits. The diff view is shared with the Changes tab (`DiffText.tsx`). Steering: kept as its own box (dynamic instruction injection unchanged), folded to one line until opened, naming the stage that reads a note next; each note already says the stage it was read in. Tests: `tests/test_a_review_shows_its_document_and_what_changed.py` (fails on the old code) |
| BG.4 rail/work-area/ledger + real tabs | P1 | DONE 2026-10-19 `034c0ce6` | The classic run page is a rail, a work area and a ledger: the rail has the newest change (`LatestChange.tsx`: its message, "3 files · +120/−8", opening Changes on it) above the stage stepper with each stage's time; the work area is real tabs - Activity (default), Changes, Log, Artifacts - with `role=tablist` and arrow keys (the kit's `Tabs`, now with a controlled mode so the page keeps `?view=` and `?change=`); the ledger is the criteria and decisions (Delivery) then the sprints. At desktop width each column fills the row and scrolls inside it, so no column's length sets the page's height: on the live shakedown run the page went from 5,890 px tall to 918 at 1366×768 and 1,083 at 1920×1080, with the actions, steering and the tabs above the fold. Gates stay a banner above the work area; steering is one line until opened (BG.3); the wizard view keeps the sprints and criteria above it. Found while measuring: the header overflowed a 375 px screen once the inbox was added (the mark alone shows there now, the server dot and palette control from the small width up, with an accessible name on the mark), the runs table's hidden header label widened the page by 243 px (its scroller is now positioned), and the stepper's scroll region was not focusable. Measured live through a dev server on the deployed API: axe 0 on home, runs, settings and the run page in all three themes; no horizontal scroll at 375 px on any of them. Not built: an Audit tab - that is BG.7. Tests: `ui/ui.test.tsx` (the controlled tabs), `components/LatestChange.test.tsx` |
| BG.5 model-server surface | P1 | DONE 2026-10-19 `b96ee212` | `GET /api/health/server` (`server/server_health.py`): the API reads the server's `/props` itself - the worker's reading lives in the worker's process - with one request, never a model call, kept for a minute; it answers the model file, quantisation, requests at once, context per request, when it was read, and the runs on it now; a hosted API says it has nothing to read. `ServerProfile` names the model file. The header has a server dot (`components/ServerDot.tsx`: state as a colour, the whole line as its name and tooltip, a link to the model settings); Settings is in tabs (Models first, with a model-server card, then Appearance, Lessons, Account; the tab is in the address); the start page and a live run page say "the model serves one request at a time and run X is on it" when that holds. Not built: the "Test call" button - `/api/health/models` pings with no bound below the model's own output limit, on the server a live run is using, and the status read already says whether the server is up and what it holds; a "Runs" settings tab - there is no run setting to put in it. Tests: `lib/serverHealth.test.ts`, `tests/test_the_model_server_s_health_is_read_without_a_model_call.py` (read at most once a minute, runs always current, hosted and silent servers, the route; fails on the old code) |
| BG.6 fix-loop + sprints structured | P1 | DONE 2026-10-19 `b96ee212` | `GET /runs/{id}/sprints` serves each attempted sprint as figures (`sprint_summary.sprint_views`): the same `sprint_attempts` and sprint plan the summary document is rendered from, read from the run's graph state, so older runs have it too and no file is added. The document's attempt lines and the route's come from one helper (`_attempt_history`). The sprint panel draws from the route and reads the documents only when the route has nothing; its row icons are labelled for a screen reader. The run payload's fix loop counts its open defects (`open_defects`), and the run page says "2 of 3 fix cycles run · 23 defects, 9 open · 7 test runs" while a test round or a fix runs (`attempt` counts cycles run, so the line does not guess which is current). The sprint summary itself is unchanged. Tests: `tests/test_the_sprints_are_served_as_figures.py` (fails on the old code), `components/SprintSummaryPanel.test.tsx`, `lib/runSummary.test.ts` |
| BG.7 Audit tab | P2 | DONE 2026-10-19 `51a1589f` | The run page's work area has an Audit tab (`AuditTable.tsx`): one row per stage - wall time, time waiting on the model, replies, tokens in / cached / out, replies lost to the output limit, reads answered with "you already have this", failed or refused tool calls - with the worst cell of each column marked, and each column header saying what it counts. Backend: `GET /runs/{id}/usage` (`observability/stage_usage.py`, from the transcript both containers read; 0.07 s for the shakedown run's 2,000 records) and `GET /runs/{id}/transcript` (the whole transcript as text, audited), downloaded from a "Transcript" control beside "Handover pack". On the shakedown run: 3.8 h of model time over 36 stages, 26.3 M tokens in with 62 % cached, the architect 23 min of model time for 189 k output tokens over 13 replies, 21 lost replies, 133 redundant reads, 91 of 492 tool calls failed. Not built: "Open in transcript" per feed row - there is no transcript view to open into, and the download and the stage rows answer what it was for; the `/kpi` half is the loop's own ledger (`kpi_ledger.py`), which compares runs rather than describes one. Tests: `tests/test_a_run_s_usage_is_shown_stage_by_stage.py` (fails on the old code), `components/AuditTable.test.tsx` |
| BG.8 feed: classification and lanes | P2 | DONE 2026-10-19 `2456b9b2` | The activity feed (`AgentActivity.tsx`) shows a result the harness gave instead of what was asked - a read of what the agent already has, a listing after reading is done - as a muted "held back: already read" chip on its action, not as a failure; the owner's review and approval decisions appear in their place ("You asked for changes to Technical Specification" with the comment); lane chips (`laneOf` in `lib/activity.ts`: the role in parallel mode, else planning, testing, fixes) filter the feed when it has more than one lane; an action's detail control shows on keyboard focus as well as on hover. Not built: "reply cut off" chips - the event stream carries no reply's finish reason; the Audit tab counts them per stage (BG.7). Tests: `components/AgentActivity.test.tsx` (fails on the old code) |
| BG.9 changes per file + criterion link | P2 | DONE 2026-10-19 `cd5b07ce` | A commit in the Changes tab reads file by file (`FileDiffs.tsx`): each file folds under its path with the lines it added and removed, all open up to six files and folded beyond, a one-file change shown as it is. Each acceptance criterion in the ledger says after which step it first passed and when ("first passed after Defect Fix 1 0, 10:00"), with "see the change" opening Changes on the first commit made from that moment. Backend: each CI snapshot records when a test first passed and after which step (`ci.save`, `first_passed` in `.harness/ci.json`; a test that fails again keeps its first time), and `/evidence` maps them to criteria by the ids in the test names (`ci.first_passes`). Not built: syntax colouring - it needs a highlighter library, and a diff reads without it. Tests: `tests/test_a_criterion_is_traced_to_the_change_that_made_it_pass.py` (fails on the old code), `components/FileDiffs.test.tsx`, `components/DeliveryPanel.test.tsx` |
| BG.10 plan-first intake (= UI-S3) | P2 | DONE 2026-10-19 `46e65503` | See UI-S3 |
| BG.11 copy and stage names from the graph | P2 | DONE 2026-10-19 `cd5b07ce` | 21 of the graph's 42 nodes had no words on the page and numbered stages fell back to their identifier ("Defect Fix 2 12" as a run page's heading). Every node now has a title and a line in `STAGE_COPY` (`lib/activity.ts`), and the stages a run numbers as it goes have their own words: "Fixing problem 13 (test round 2)", "Testing, round 1", "Revising the acceptance tests (pass 2)", "Asking the interface specialist". `tests/test_every_stage_has_words_on_the_page.py` reads the graph's nodes from `workflow.py` and fails when one has no words - the table is held to the graph rather than generated from it, which keeps its plain-language wording. Not built: the product-wide vocabulary pass (brief, build, run, gate) - it belongs with BG.12's restyle of the same screens. Tests: that file (fails on the old table), `lib/status.test.ts` |
| BG.12 visual residue | P2 | DONE 2026-10-19 `c6e4fe85` | Already so before this item: `.glass-card` is a plain surface with a border and no blur, `.gradient-btn` one solid accent - only the class names remain, kept so no component needed an edit. Done here: the contrast theme gave every element a border width (`[data-theme="contrast"] *`), which with the preflight's solid borders boxed each heading, label and icon - 134 text elements on the kit page; now only operable controls (buttons, fields, tabs, summaries) get it, and containers keep their own (10 left, all badges). A 12 px type floor: 76 uses of 10-11 px text are `text-xs` (no text under 12 px on the kit page); the kit's tab row wraps on a narrow screen instead of widening it. Measured: axe 0 on the kit page and on home, runs, settings and the run page in all three themes; contrast 650 pairs hold; no horizontal scroll at 375 px; the run page 917 px tall at 1366×768. Not built: renaming the card classes (a rename across 20 files for no change on screen); "every number labelled with its source" stays a rule of new work (`Stat`, the Audit columns) rather than a sweep |
| BG.13 accessibility and polling | P2 | DONE 2026-10-19 `1522cdf4` | Real tabs came with BG.4. Here: the run page pages `/logs` only while the live stream is down - an open stream replays everything after the last event it saw, so each refresh's page of the same events cost a request and gave nothing (`streamOpen` in `RunDashboard.tsx`); the activity feed's log region no longer announces every action (`aria-live=off`), and a status line announces the newest progress update instead; every disclosure row says whether it is open (`aria-expanded` on the sprint rows, the ledger and its decisions, the failure reason); the rewind select has a name; screenshots and document images load lazily; an action's detail control shows on keyboard focus (BG.8). Polling: the sprint panel's 30-second poll is gone - it reads the sprints again when the run moves to another stage, as the ledger already did; the other panels never polled, so the `/runs/{id}/summary` aggregate the plan names would replace nothing and is not built. Tests: `pages/RunDashboard.test.tsx` (the first test of the run page: no `/logs` paging once the stream is open; fails on the old page), `components/AgentActivity.test.tsx` (what a screen reader hears) |
| BG.14 timeline scrubber / replay | P3 | DONE 2026-10-19 `b64ca7e5` | Above the activity feed, the run's span as a line (`Timeline.tsx`, `lib/timeline.ts`): a tick where each stage began, a dot where the owner answered a gate, a diamond where a direction was sent, each at its share of the run and named in words; choosing one scrolls the feed to its first entry from that moment (`focusAt` on the feed). Not built: rewind points on the line - they are read from the checkpointer only when the owner opens Rewind, and a rewind is chosen there by stage; filtering Changes to the moment - a criterion's "see the change" (BG.9) and the latest-change chip already open a commit by time. Tests: `lib/timeline.test.ts`, `components/Timeline.test.tsx` |
| BG.15 context pressure and throughput | P3 | DONE 2026-10-19 `203bbfac` | The run page's rail has a "Model pressure" card (`ModelPressure.tsx`, `pressure` in `lib/runSummary.ts`): "Last call used 118 k of 126 k context" with a bar, red above 90 % - a call near the edge is the next to be cut; "Busy 50 % of the last 10 min"; the last reply's tokens per second and a sparkline of the hour's. Read every minute while the run is live and the tab visible. Backend: `/usage` also returns the run's model calls of its last hour (`recent_calls`: when, stage, tokens in and out, seconds; at most 300), and the slot's size comes from the server's own status (BG.5). Tests: `tests/test_a_run_s_usage_is_shown_stage_by_stage.py` (the last hour of calls; fails on the old code), `lib/runSummary.test.ts` |
| BG.16 palette, shortcuts, cross-run compare + housekeeping | P3 | DONE 2026-10-19 | The palette and the shortcuts sheet came with UI-S1/S2. Housekeeping done: the dev server proxies to port 8000, where the app and its API answer (it pointed at 8001, where nothing listens); `wizardData.ts`, `DynamicWorkflowUI.tsx` and `App.css` deleted - nothing imported them; the start page names the signed-in user as the run's reviewer instead of "Product Manager". Cross-run compare came with UI-S6. The `docs/ui/` screenshots of every page in every theme were taken again from the live app after the app deploy of `c6e04398`: axe 0 on all twelve |
| BJ one input budget per request | P1 | NOT STARTED | after BF; added 2026-10-19 from the research coverage check |
| Part 20 two-run gate rule | P0 (process) | ADOPTED 2026-10-19 | each wave gate judged on ≥2 runs against the W.2 baselines |
| BK release packaging failure is a completion gap | P1 | DONE 2026-10-19 `1d6a4e1` | the release files are written before `completion_gaps` is stored, and `ReleaseFiles.a_gap` (the failure text, never for a product no pack covers) joins the gaps, so the evidence page and the bench export carry it. Test `tests/test_a_release_whose_files_failed_is_completed_with_gaps.py` (2 of 3 fail on the old code). From the external review (Part 22.4, item 6c) |
| BL code is reviewed before a sprint is accepted on its suite alone | P1 | DONE 2026-10-19 `089b8f6` | Owner's yes, 2026-10-19, from the W.2 baseline-1 analysis: the custom setup stage wrote the whole product, sprint 1 was accepted without new work, and no review ran. Now (1) a sprint whose criteria pass while no security or milestone review has run goes to the reviews with a plan of no work orders (decision "review it before accepting"; sprint 1 shows the reviewers the whole product); (2) the setup request asks for only the smallest app the smoke tests need; (3) a setup is not proven while a smoke test sits outside its runner's directory or any test file sits outside both. Tests: `test_a_sprint_no_review_has_read_is_reviewed_before_it_is_accepted.py`, `test_a_setup_keeps_every_test_where_its_runner_collects_it.py` (each fails on the old code). Deployed after the W.2 baselines |
| Part 21 one implementation order | P0 (process) | ADOPTED 2026-10-19 | replaces §4, Part 16 and Part 20 ordering |
| Part 22 consistency review | P0 (process) | ADOPTED 2026-10-19 | 12 contradictions resolved in place; do-not-implement list |

---

<a id="plan-e-2"></a>
## Appendix 5 (2026-10-20): efficiency audit - time saved without lowering quality

Owner, 2026-10-20: "research the code and audit the run ... identify the performance improvement and
efficiency possible without sacrificing the quality", and make such suggestions unasked from now on.
Measured on the findings run run-e601377f (246 min, 370 calls) and clean gate run 1 run-01a1ab9c
(first 99 min). The model server reads a prompt at about 2,243 tokens/s and writes at about 122
tokens/s; on the findings run prompt reading was 67 of 164 model-minutes, writing 96.

| ID | Waste, measured | Change | Quality risk | Status |
|---|---|---|---|---|
| EF.1 | A partial loop-breaker rung (the looking tools, the read tool, one repeated tool) takes tools off the offered list for a call and puts them back the next; the chat template puts the tool list first, so each change re-reads the whole prompt (about 70k tokens, 30 s): 44 re-reads, 22 min on the findings run; 31, 15 min in gate run 1's first 99 min | Keep the offered list as it is for the partial rungs and refuse a withheld tool when it is called (the refusal and the notices exist); only the answer-only rung still empties the list | Low - a weak model calls unoffered tools anyway, which is why the refusal exists; to be measured | Planned: after gate run 2, measured against the gate runs |
| EF.2 | One model call at a time ("parallel overlap 1.0x") while the server has 2 slots: linear execution mode | The owner's parallel/linear toggle set to parallel for testing (the owner's 2026-10-12 direction was parallel first): independent work orders and consults use both slots | Low-medium - file conflicts are refused by work-order ownership | The owner's setting: suggested |
| EF.3 | Writing is 59% of model time and 78% of the findings run's output was reasoning; 10 replies lost to the length cap held 28% of all output | The thinking budget per stage (M.4): low or off for fix and acceptance-writing stages | Medium - measured as group 2's M.4 | Accepted by the owner; group 2 |
| EF.4 | 25-45% of wall time shows as "neither": the specification's parts and revisions and fast drafting are model calls outside any stage, unrecorded | Record them in the transcript | None to the product; changes what the KPIs count | Accepted; after the gate comparison |
| EF.5 | The project memory is 34% of every request's characters (about 113k); each full re-read pays for it, and it brings compaction nearer | Measured on the findings run: 114k characters, about 29k tokens of an 80k compaction trigger, re-sent on every call, so a fix stage that reads three files compacts every call or two (LF.81). Measure a smaller `MEMORY_SHARE` (0.3 now) against the reads it then costs | Medium - the memory saves reads | Proposed: measured |
| EF.6 | A builder asked again and again to change another work order's file (14 refused calls, about 5 min, in gate run 1) - and the change was needed: it was the `get_async_session` alias in `database.py` the routers import, so after the refusals the product could not start (`ImportError ... get_async_session`) and the fix waited for a test round and the fix loop. In linear mode the owning work order had already finished, so the refusal protected nothing. After the re-plan the refusal also put bad code in the product: `patch_database.py`, a module that sets `database.get_db` at import, "a workaround because database.py is locked to specialist_backend_0". And it cost hours: the product ended with three names for one session dependency (`get_db`, `get_session`, `get_async_session`, two of them aliases a builder could add only by patching from outside the file) and the unit tests' database override missed the one the sign-in routes use - "no such table: users" survived six fix stages | In linear mode, let a later work order add to a finished work order's file what its own files need (an export, an alias), recorded for review; keep the refusal in parallel mode and for anything that rewrites the other work order's code | Low-medium - the milestone review and CI still see the change | Proposed: after gate run 2 |
| EF.7 | Each bug in a live run cost a new run (four restarts on 2026-10-20, 30-90 min each, plus one 4-hour run) | `loop.sh rewind` after the deploy (LF.57); pause, deploy, rewind instead of a 30-minute boundary wait | None | DONE (LF.57); first used 07:35 JST, kept about 80 min of work |
| EF.8 | The loop's suite took about 290 s per fix | `pytest-xdist`, 12 workers: 64 s, same result | None | DONE (LF.58) |
| EF.9 | Compactions every one or two calls after LF.36 | Carry budget and hysteresis (LF.47): 1-4 per stage since | None measured | DONE (LF.47) |
| EF.10 | Validating a general fix only on 6-hour brief_medium runs | Between gate runs, check general fixes on `notes-api-hono` (about 40 min, scored by hidden tests) | None | Suggested |
| EF.11 | Builders are never shown the interface contract - the locked lines (`AC-1 page /login textbox "Email"`, `AC-3 GET /api/notes -> 200`) the suite is written from and the release checks - only their work order's criteria as prose (`specialists._DETAIL_SECTIONS`), so a label, route or command the suite looks for is a guess | Give each builder the contract lines for its criteria and files, as decided like the rest of its specification | None: the same locked lines, shown earlier | BUILT 2026-10-21 as CM.2's first entry type, behind `DECISION_LEDGER` (every line to every builder: a contract is at most a few kilobytes) |
| EF.12 | The suite is written before any code exists, so its author cannot see a page, a route or a message, and a failing test leaves the fixer unsure whether the test or the product is wrong; the suite then needs repair rounds | Owner's proposal, 2026-10-20: the criteria and the interface contract stay locked at the specification (the definition of done); the suite is written once the sprint's unit tests pass, from the locked criteria and contract and the running product's surface (the rendered page, its routes, the command's help) - never its source - then run on its own. Every test names its criterion; a criterion without a test, or a test that contradicts its contract line, stops the lock. Replaces R2 and R3 of the acceptance-first review | Tests shaped to the code as built; guarded by the source being withheld, the locked contract and the per-criterion coverage | Planned, group 2, after EF.11 is measured |
| EF.13 | A product that does not start fails one name per test round (three rounds in gate run 1, one missing import each) | Attach every name the language service underlines to the start defect, so one fix stage sees them all | None | Planned; LF.59 already reads every file at the gate |
| EF.14 | Builders that spend their 40 model calls without answering are started over on a fresh conversation, up to three times, re-reading what the first wrote - measured on the findings run: two testing work orders, six attempts, about 50 minutes, each attempt ending at the budget. Fix stages are recorded from their writes instead (`workflow._a_fix_recorded_from_its_writes`, deliberately fix stages only) | Measure recording a builder from its writes after its first budget stop, with the CI gate and the test round deciding, against today's three attempts | A half-built work order goes to the fix loop rather than to its own author | Proposed: group 2, measured |

<a id="plan-appendix-6"></a>
## Appendix 6 (2026-10-20): agent-to-agent communication and object storage

Owner's questions, 2026-10-20:
- Would communication between the specialist agents improve effectiveness, efficiency and performance?
- What replaces MinIO, which is no longer open source?

Owner's questions, 2026-10-21:
- Is a "recursive learning harness" a valid feature here? ([RL](#plan-rl))
- Can agents see the exact progress before their work and leave a work summary for the next? ([PH](#plan-ph))
- Can a graph of the code behind each feature (file, block, wiring) let an agent understand at once when something goes wrong? ([CG](#plan-cg))

Full assessments, with evidence and sources:
- [`docs/agent-communication-feasibility.md`](agent-communication-feasibility.md)
- [`docs/object-storage-plan.md`](object-storage-plan.md)

Research: [R7](research-findings.md#r7), [R8](research-findings.md#r8), [R9](research-findings.md#r9), [R10](research-findings.md#r10). Decisions (proposed): ADR-0012 and ADR-0013 in `docs/architecture-decisions.md`.

<a id="plan-cm"></a>
### CM — Agent communication through harness-owned records, not peer messages

**Finding.** Agents never talk directly. Each stage gets one prompt assembled from state.
- Of 15 documented failures traced, about 11 were one agent missing a fact another agent or the harness already had: LF.24, LF.25, LF.40, LF.42, LF.44, LF.80/82, LF.90, spec-name drift, unread specialist outputs, sprint scope, contradicted advice.
- Each was patched one at a time.
- A builder's `decisions`/`blockers` reach only the milestone reviewer (`milestone_reviewer.what_the_specialists_reported`).

**Research.** Free peer messaging and debate do not pay:
- CooperBench (2026): paired coding agents lost nearly half a single agent's capability, and real-time messaging had almost no effect.
- MAST (NeurIPS 2025): protocol fixes are insufficient on their own.
- Google/MIT (2026): sequential tasks degrade 39–70% under every multi-agent variant.
- Debate ≈ majority voting.

Structured, harness-controlled hand-off does pay (MetaGPT, blackboard-with-controller), and bounded clarification questions gained about +14 points on underspecified SWE-bench Verified.

| ID | Change | Model calls added | Measure | Priority | Status |
|---|---|---|---|---|---|
| CM.1 | Fact parity: every judging stage (architecture, security, acceptance and milestone reviews, disputes) is given the same environment contract, data-store facts, scaffold layout and sprint scope as the builder it judges. One function feeds both prompts, and a parity test fails when they diverge | 0 | reviewer findings withdrawn or contradicted by the environment; reverted fixes | P0 | BUILT 2026-10-21, behind `SHARED_FACTS` (off until the gate run ends, then measured): `app.agents.shared_facts` - one function writes the layout, a served stub and the code the product does not run; every judge (acceptance, advice, milestone, security, code review, dispute) and builder (work orders, test rounds, fixers, one-shot drafts and rewrites; the stages still building get the layout alone) request ends with it, and the architect's layout lines are the same function. Parity test: `tests/test_judges_read_the_facts_the_builders_were_given.py` (fails on the old code) |
| CM.2 | Typed decision-and-contract ledger (builds Pillar 9). Harness-written entries `interface_contract`, `decision`, `blocker`, `known_trap`, `requirement` come from existing structured outputs. Role-sliced, ≤4k chars per stage under BJ, dropped entries named. Never reasoning or model-written notes. Start with EF.11's contract lines | 0 | contract-mismatch defects per milestone; fix attempts per defect; spec/code name drift | P1 | PARTLY 2026-10-21, behind `DECISION_LEDGER` (off until the gate run ends): `app.agents.ledger` (typed `Entry`, `the_slice` by role and files, `rendered` within 4,000 characters naming what it left out); its first entry type, the interface contract (EF.11), reaches every builder and fixer through `specification_for_the_work_order`. Decisions and blockers come with CM.3. Test: `tests/test_builders_read_the_interface_contract.py` (fails on the old code) |
| CM.3 | Route blockers and interface-changing decisions to the work order that can act on them: at its next visit in linear mode, at the gather join in parallel mode, where two work orders changing one interface become a defect at once. Complements EF.6 | 0 | fix rounds per milestone; time from blocker to fix | P1 | PARTLY 2026-10-21, behind `DECISION_LEDGER`: linear mode - a finished work order's blocker or decision that names a planned file reaches the next work order owning that file (`ledger.from_the_builders`, `ledger.with_the_reports`); one naming no planned file stays the milestone review's. Open: the parallel-mode check at the gather join. Fast delivery's one-shot drafts report nothing, so it shows in thorough runs and agent-built work orders |
| CM.4 | Bounded `ask_specification` tool for builders and fixers, behind a flag, off by default. Answers by retrieval from spec, ledger and locked suite first; one architect-role call only when retrieval misses. Answer stored in the ledger; ≤2 per work order, 1 per fix, a per-run ceiling | ≤2 per work order, only on a retrieval miss | questions per work order; share answered by retrieval; underspecification defects | P2 | PROPOSED: measure on the owner's model first (over-asking risk) |
| CM.5 | Reviewers keep a clean context: artefacts and facts, never the builder's reasoning or transcript | 0 | — | P0 (process) | ADOPTED as a principle |

**Rejected:**
- a peer mailbox;
- specialist debate or negotiation rounds;
- broadcasting builders' reasoning;
- parallel builders coordinating edits by message (the write guards and file holdback already do this deterministically).

**Kill rule:** an item that raises tokens per accepted criterion by more than 5% without lowering at least one defect metric is turned off (ADR-0010, two-run rule Part 20).

<a id="plan-os"></a>
### OS — S3-compatible object storage: SeaweedFS replaces MinIO

**Finding.**
- MinIO's community edition stopped binaries and images in Oct 2025, went into maintenance mode in Dec 2025, and was archived in 2026. Its free tier is commercial and single-node.
- In DevFlow the `minio` service is commented out. The Local backend therefore writes its "durable copy" to `DATA_DIR/objects` on the **same** `appdata` volume as the workspaces.
- Archived artifacts are never read back: `download_artifact` reads the workspace only.

**Choice.** SeaweedFS (Apache-2.0, since 2015), single-process `weed mini`, as an opt-in compose profile.
- Runner-up: RustFS. It is Apache-2.0, but reached GA on 16 Sep 2026 and had critical CVEs in Dec 2025 and Jul 2026. Re-evaluate around Q2 2027.
- Not chosen: Garage (AGPL, no versioning or object lock, CLI bootstrap), Ceph RGW (too heavy for one host).

**Priority:** P2. It protects run output and enables multi-node workers; it does not change build quality.

| ID | Change | Status |
|---|---|---|
| OS.0 | Spike: SeaweedFS against the existing store tests. Check boto3 1.43 default checksums, bucket create, pagination past 1,000 keys, non-ASCII keys, and the health endpoint | PROPOSED |
| OS.1 | `seaweedfs` compose service under profile `storage`: bind mount `./data/seaweedfs`, admin UI on loopback only, 1 GB limit, healthcheck; `depends_on ... required: false` | PROPOSED |
| OS.2 | Rename `MINIO_*` settings to `OBJECT_STORE_ACCESS_KEY/SECRET_KEY`, `SEAWEED_ADMIN_PORT` (old names read for one release); remove the commented MinIO blocks | PROPOSED |
| OS.3 | Harden `object_store.py`: checksum mode, timeouts, connection pool ≥ `HARNESS_MAX_PARALLEL`; refuse an S3 endpoint with empty credentials (allow-all mode); storage status on the health page; archive metrics; skip unchanged files | PROPOSED |
| OS.4 | Read-back: `download_artifact` falls back to `runs/<id>/<path>` in the store when the workspace file is gone; listing from the store for pruned runs | PROPOSED |
| OS.5 | `manage.py object-store backfill` and `verify` (uses `iter_missing`); import the Local backend's `DATA_DIR/objects` | PROPOSED |
| OS.6 | Store tests parametrised over both backends (S3 variant marked, runs when an endpoint is set); new tests for read-back, empty-secret refusal and degraded health, each failing on the old code | PROPOSED |
| OS.7 | Docs: ADR-0012, R8 and this appendix done 2026-10-20; HANDOVER operations section (enable, rotate, back up, restore, roll back) at implementation | PARTLY (docs) |
| OS.8 | Optional: off-site `rclone` mirror, bucket lifecycle matching run retention, RustFS re-evaluation | PROPOSED |

**Acceptance criteria:**
1. The default `up` without the profile is unchanged.
2. A run's files appear under `runs/<id>/`.
3. A pruned workspace still downloads from the run page.
4. Deleting a run deletes its objects.
5. A store outage never fails a run and shows as degraded.
6. `down -v` leaves `./data/seaweedfs`.

**Rollback:** leave `OBJECT_STORE_BUCKET` unset.

**Placement in Part 21:**
- **CM.1** joins stage 1 (cheap fixes).
- **CM.2** and **CM.3** join stage 4 after BJ, since they share its input budget.
- **CM.4** joins stage 8 (optional, flag-gated).
- **OS.0–OS.6** join stage 7 (infrastructure).

*Owner, 2026-10-20 22:20 JST:* CM.1–CM.5 are implemented with group 2 (Part 21's validated items), in the
stage order above; OS.0–OS.8 are implemented later, after group 2.

<a id="plan-rl"></a>
### RL — Recursive learning: finish the lessons engine, keep the human gate (2026-10-21)

**What the term means in 2026** ([R9](research-findings.md#r9)). Three different things are called a recursive or self-improving harness:
1. *Memory-level*: lessons, procedures or playbooks distilled from runs and injected into later runs (ACE, RSIAgent, Reflexion/ExpeL). No weights change.
2. *Harness-code-level*: an agent reads benchmark failures and edits the harness's own code and prompts, a human reviewing the result (Cline, July 2026: Kimi K3 on Terminal-Bench 2.1 from 77.5% to 88.8% after a GPT-5.6 leader agent spent about $680 rewriting harness code).
3. *Model-level*: fine-tuning on the harness's own trajectories (HELIX). Not applicable to a GGUF the owner does not train.

**What exists.**
- Level 1: the lessons store (AI, AT: DONE). Records are schema-checked, HMAC-signed, stack- and role-scoped, injected five per call in a fixed order, and only once the owner approves. Within a run, `sprint/record.lessons_from` already feeds the next sprint's lead.
- Level 2: the standing loop in `AGENTS.md` (benchmark → audit → fix → test → deploy), gated by the KPI ledger (ADR-0010) and the two-run rule (Part 20). The LF rows in Appendix M are its output.
- Not built: Pillar 5's post-run distiller (`src/app/learning/` does not exist). `store.propose()` is called only by hand (`loop.sh lessons`); the plan's line "the loop lists new proposals in each run's report" is not true of the code. No evidence that `data/lessons.json` has ever held a proposal.

**Verdict.** Valid, as *finishing level 1 with deterministic distillation and uptake measurement*; level 2 stays human-gated as it is. Not valid on a local model: agents rewriting their own prompts or harness code unsupervised (STOP-style self-optimisation degraded weaker models; the one working result used a frontier leader model), or free-text memory the model edits itself (the drift-and-poison problem that caused the earlier drop, and R7's conclusion).

| ID | Change | Model calls added | Measure | Priority | Status |
|---|---|---|---|---|---|
| RL.1 | Deterministic distiller (Pillar 5, bounded): after every run, propose lessons from harness-recorded signals only — a fix reverted for breaking tests, a CI-gate cause, a defect that needed more than two attempts, an advice "not built" finding, a recurring refused-call shape (what `loop.sh lessons` finds today). Each proposal names the stack, role, trigger, evidence runs and a rule of ≤2 lines; never model-written reflection | 0 | proposals per run; share approved | P1 | BUILT 2026-10-21 behind `LESSON_DISTILLER` (off): `app/plugins/lesson_distiller.py` proposes one lesson per kind from the transcript's defect records (a fix reverted for breaking tests, a package no manifest declares, a defect fixed more than twice) for the run's pack; `loop.sh kpi` runs `loop.sh lessons distil`; nothing is shown until the owner approves |
| KB.1 | a sprint planned again starts from the best product it has had. Measured on a gpt-oss-20b run (notes-api-hono): the first attempt ended at 14 of 18 acceptance criteria passing, remediation was exhausted, the sprint was planned again, and the new drafting rewrote working files; the next rounds measured 0 of 18 with no test reaching the product, and every attempt after it started from that. Nothing kept the 14. `best_attempt` (switch `KEEP_THE_BEST_ATTEMPT`, off in code, on in compose): each round that passes more acceptance tests than any before is committed and remembered (`.harness/best-attempt.json`); when a sprint is about to be planned again or escalated and the product passes at least 2 fewer tests than that best, its files are put back as they were at the best commit - except the locked suite and the harness's own files. Off, nothing changes. Extended 2026-10-25 (after the best is put back the suite is measured again: a run was stopped for "21 failing criteria" read from the wrecked product's saved result, with its best product, 12 of them passing, already back on disk; re-plan or escalation: one test fewer than the best is put back, after a run that had passed all 18 criteria released at 17 with AC-14 deferred; the redraft check keeps a margin of two) (`after_a_redraft`): at the first test round of a re-planned sprint, a redraft that left the product clearly worse than its best (3 runs in one night: 14 of 18 criteria to 0, 17 to 12, 4 tests to 0) is undone at once and the sprint is planned again, instead of after a whole round of fixers on the wreck; a redraft as good or better stays (one took a product from 1 to 12 criteria), and the re-plan bound is the existing one. Tests `test_a_sprint_planned_again_starts_from_the_best_product_it_has_had.py`. To measure: runs that re-plan - criteria passing after the re-plan against before | BUILT 2026-10-24, owner away: switch on, tell the owner | [monitoring handover §0](monitoring-handover.md) |
| WM.1 | a name an import asks of a package that does not have it comes back with what the package really exports (switch `PACKAGE_EXPORTS_NAMED`, off in code, on in compose; owner 2026-10-25: tune the harness for weaker models, step A1). A small model imported `createClient` and `createTestClient` from `hono/testing`, which exports one name, `testClient`; the compiler said which name was missing and not which exist, so each rewrite guessed again and four Hono runs ended with a product that did not build. `app.analysis.package_exports` reads the package's own type file (the manifest's `exports` entry for the subpath, then `types`, following `export * from` to three files) or, for Python, the top level of the installed module's `__init__.py` (`__all__` when present) - statically, nothing of the package runs - and the existing machinery for the project's own modules (`language_service.what_the_module_defines`, the stage-exit note, the defect built from the finding) now says "`hono/testing` is a package; it exports only: testClient" and does not ask for a name to be added to it. Tried on the real installed `hono`, `@hono/node-server`, `fastapi` and `jwt`. Tests `test_a_name_a_package_does_not_have_comes_back_with_the_names_it_does.py`. A2: a read-only `module_exports` tool offered to the specialists (the same switch), so a model can look before it writes; A3 (switch `PACK_ENTRY_EXPORTS_KEPT`): a pack names the exports of its entry files that its own smoke test and start file import (`StackPack.required_exports`; the Hono pack: `createApp` in `src/app.ts`), and a test round that finds one dropped raises a defect naming file and export before the importers' errors arrive one by one (`app.stacks.entry_exports`, `acceptance_nodes.pack_contract_defects`). Tests `test_a_pack_s_entry_file_that_stops_exporting_what_the_scaffold_imports_is_a_defect.py` | BUILT 2026-10-25, shipped not deployed (a run is live) | [monitoring handover §0](monitoring-handover.md) |
| WM.2 | a simpler TypeScript toolchain for weaker models, as a measured arm (owner 2026-10-25, step B; switch `HONO_NATIVE_TEST_RUNNER`, off in code and in compose). Five runs of a small model on the Jest pack ended with a product that did not build: ts-jest, a build step and Jest's configuration were each a way to fail beyond the model's own code. The pack `node-hono-native-api` runs the service with `node src/main.ts` (Node 24 strips the types), tests with Node's own `node:test`, and uses `tsc --noEmit` only as a check (`erasableSyntaxOnly`, `allowImportingTsExtensions`); its guide limits the syntax to types and nothing else, names the `.ts` extension on relative imports, and points the model at `npm run typecheck` and the `module_exports` tool. Scaffolded for real with `scripts/loop/verify_packs.py` (install, unit and acceptance smoke pass). Tests `test_hono_has_a_measured_arm_that_node_runs_itself.py`. To measure: three Hono runs with the switch on against the five Jest runs (hidden 1, 0, 0, 0, 0 of 9), then decide; the price is a narrower TypeScript | BUILT 2026-10-25, shipped not deployed, arm off | [monitoring handover §0](monitoring-handover.md) |
| WM.3 | the harness adds the `.ts` a relative import lacks, for the pack that Node runs itself. On the first run of the `node-hono-native-api` arm (WM.2) the model wrote `./middleware/bodyLimit` although the guide says to name the extension, Node answered `ERR_MODULE_NOT_FOUND`, TypeScript advised `.js` (which would not load either), and the service did not start in three rounds: 0 of 18 criteria with 0 tests. Which file an extensionless import means is not a judgement: if `<spec>.ts` or `<spec>/index.ts` exists, that is the file. `StackPack.relative_import_extension` (".ts" for that pack only) makes `contract.enforce`, which runs before every measurement the harness makes, rewrite such imports in `src/` and `test/` (`app.stacks.import_extensions`: also `.js` to `.ts` where the `.ts` exists; packages, `.json` and unresolved paths are left). Tests `test_a_relative_import_without_its_extension_is_given_one_for_node.py` | BUILT 2026-10-25, deployed with the arm | [monitoring handover §0](monitoring-handover.md) |
| WM.4 | a path an installed package does not export comes back with the paths it does (the same switch as WM.1). On the first arm run the model imported `hono/middleware`, which Hono does not export; the compiler said only "cannot find module", Node `ERR_PACKAGE_PATH_NOT_EXPORTED`. `package_exports.package_paths` reads the manifest's `exports` keys and `language_service.the_names_the_module_has` and the batch defect add "`hono/middleware` is not a path that package exports; the paths it exports are: hono, hono/body-limit, hono/cors, ...". Tests added to `test_a_name_a_package_does_not_have_comes_back_with_the_names_it_does.py` | BUILT 2026-10-25, shipped not deployed (arm run 1 is live) | [monitoring handover §0](monitoring-handover.md) |
| LF.275 | a fix that edits a manifest into one nothing can install stayed, and the next five fixers worked on a project nothing could install. gpt-oss-20b on tasks-api: a fix pinned `python-jose==4.3.0` (the registry has up to 3.5.0); every pip install after it failed; the five fixers after it each ended "its own tests still fail" for the rest of the round, and the defect carrying the registry's answer (LF.267) was raised only when the round ended. The regression gate could not see it: nothing passed before, so nothing could break. `engineering.what_the_fix_did_to_the_install`: when the fix's working tree differs from its base in a manifest file and the suite's saved install note says the install failed, the fix is reverted at once with the installer's words and the registry's current release; an install that was already failing is not the fix's, and NG.1 never keeps such a fix. Tests `test_a_fix_that_makes_the_install_fail_is_reverted_at_once_with_the_reason.py` | BUILT 2026-10-25, shipped not deployed | [monitoring handover §0](monitoring-handover.md) |
| LF.276 | a suite whose web server timed out (`Timed out waiting 60000ms from config.webServer.`) ran no test and was read as a suite that proved nothing: QA was sent back five rounds in twenty minutes for a start script it does not own. The wording is now one of the ways a product never started, so it is raised as the product's defect. Test `test_a_web_server_that_timed_out_is_a_product_that_did_not_start.py`. | done |
| LF.277 | the team's own `start.sh` (the suite runs it when the project has one) ran the module that defines the application and never listens. Every service pack with a one-line start command now writes `start.sh` from that command and keeps it (put back if changed or missing), as the Python packs do. Test `test_a_service_pack_writes_and_keeps_the_start_script_the_suite_runs.py`. | done |
| LF.278 | the tests a fixer is told "still fail" after a write ran before the harness put its files right: a fixer wrote `./app.js` for `./app.ts` (Node runs the `.ts` itself), the check failed on that import alone, and the stage went on the same edit. The after-write check now runs `contract.enforce` first, as the suite's run does. Test `test_a_fixer_s_tests_are_run_after_the_harness_puts_its_files_right.py`. | done, shipped not deployed |
| LF.279 | every sprint plan was sent back to the lead three times (about two minutes of model calls each sprint) for "the sprint's scope names technical_specification.md and no work order lists it": the document lives in the workspace's `docs/`, not the project folder the check looked in. The harness's own documents in `docs/` now count as existing. Test `test_a_scope_that_names_the_specification_does_not_need_a_work_order_for_it.py`. | done, shipped not deployed |
| LF.280 | in three Native-TS Hono runs the team rewrote `src/main.ts` (host `127.0.0-1`, a call to a `startServer` that was not exported, an import of a missing module) and the product did not start for the first half hour. The Native-TS pack now keeps `src/main.ts` (put back if changed); the application stays the team's, in `src/app.ts`. Test `test_a_native_hono_service_keeps_the_pack_s_server_bootstrap.py`. | done, shipped not deployed |
| LF.281 | the "product does not start" defect carried only the runtime's first crash (a path Hono does not export, then a name `node:fs/promises` lacks, then a mistyped host), a fix and a round apart, while `tsc --noEmit` listed 14 errors at the first round. A pack that declares `typecheck` (the Native-TS Hono pack: `npm run typecheck`) has it run when the product fails to start, and the errors that name a missing name, module, export or member (not implicit-any or type mismatches) go with the defect, up to 12, with the exports each package really has. Behind `START_DEFECT_NAMES_COMPILER_ERRORS` (compose on). Measure on the next two Hono runs: minutes until the product first starts, fixers reverted before that. A package path the package does not export (`Cannot find module 'hono/middleware'`) comes back with the paths it does (seen in the first live run). Run 9 showed two limits: the model rewrote `tsconfig.json` (`module`), so `tsc` reported only the configuration and no compiler error reached the fixers - the Native-TS pack now keeps `tsconfig.json`; and a router handed to `app.use` instead of `app.route` made every request throw, which `tsc` reports as TS2769/TS2345, so those two codes are kept too, the product's files before the tests'. Test `test_a_product_that_does_not_start_carries_the_compiler_s_missing_names.py`. | done |
| LF.282 | the language service read none of Node's own type declarations (`types: []`), so every `node:` import was unresolved and left alone: `import { promises } from 'node:fs/promises'` and `import { expect } from 'node:test'` were found only when the product crashed. With `PACKAGE_EXPORTS_NAMED` on and the project's `@types/node` present, the built-in modules are checked for the names an import asks, and the finding lists the value names the module does export (near matches first). Checked on three stored workspaces: found `afterAll`, `expect` and `net.address` that `tsc` also reported, and nothing else. Test `test_a_name_a_node_built_in_module_lacks_is_underlined_with_the_names_it_has.py` (needs a TypeScript beside Node; skipped where there is none). | done, shipped not deployed |
| LF.283 | the Native-TS Hono arm (`HONO_NATIVE_TEST_RUNNER`) is on by default in compose from 2026-10-26 02:00 JST. Evidence, same model (gpt-oss-20b), notes-api-hono: Jest pack 1, 0, 0, 0, 0 of 9; arm 0 (mixed versions; start path fixed mid-run), 9, 9, 9, 8, 9. Not measured on a stronger model; the code default stays off and the switch brings the Jest pack back. | done |
| LF.284 | a sprint whose acceptance suite was fully green (18 of 18 criteria from the eighteenth minute) was planned, drafted and measured again for 40 minutes because one unit test the model wrote kept failing. From the second exhaustion on, when the suite ran, every acceptance test passed and every open defect is a failing unit test, the sprint goes where the re-plan limit sends it: the escalation, which accepts it with the problem recorded (and the release records the failing unit test, RL.1). Behind `SETTLE_WHEN_ACCEPTANCE_IS_GREEN` (compose on). Test `test_a_sprint_with_a_green_acceptance_suite_is_not_planned_again_for_a_unit_test.py`. | done, shipped not deployed |
| LF.285 | a criterion about data surviving a restart could not be tested by QA ("the server runs once per suite") and shipped deferred in at least five runs; in run-ba177ced the product lost its notes on a restart, the hidden test failed (8/9) and the locked suite was green. Every Node-run service pack now writes and keeps `acceptance/service.cjs`, which starts the project's own `start.sh` on a free port and a data folder the test names (`startService({ dataDir })`, `.stop()`), and the QA guide says a restart criterion is tested with it, not deferred. Checked for real in a test (start, write, stop, restart on the same folder, read; a fresh folder reads nothing). The Express pack (`node-http-api`, notes-api-js) has its own definition and was missed at first: QA there again deferred persistence ("restarting the service between tests is not supported"); it now keeps its `start.sh` and the helper too. Test `test_a_service_pack_gives_qa_a_way_to_restart_the_service.py`. | done |
| LF.286 | stall rule: a browser app (fullstack-bookmarks, 15 of 18 for over 40 minutes), a service (Hono run 4) and tasks-api (20 of 21 for 50 minutes) were drafted, fixed and planned again while the best product was already kept. Each re-plan now writes down the best acceptance-test count so far; when the last two attempts each failed to beat the best before them, the sprint goes where the re-plan limit sends it, the escalation. Needs the best-attempt record; without one the rule never applies. Behind `STALL_RULE` (compose on). Test `test_a_sprint_whose_attempts_stop_beating_the_best_goes_to_the_escalation.py`. | done, shipped not deployed |
| LF.287 | builder facts: the drafting stage, which writes most of the product one file per call, was never shown the stack pack's guide or the installed packages' real exports - only the agent loop and the fixers were, a round later - and its compile check read the language service, which misses a router handed to `app.use`. With `BUILDER_FACTS` on (compose on) each draft request carries the pack's guide (at most 2,500 characters), each declared package's real exports and import paths (tooling left out; a cut list says how many more), and the redraft adds the pack's own `typecheck` errors on the file. About 3,500 characters on the Hono project. Measured arm: off = run-3dea8a44 (the run live when it was built); on = the next Hono runs; compare minutes until the product first starts, defects in the first test round, hidden score. Test `test_the_drafting_builder_is_given_what_a_fixer_learns_after_a_failure.py`. | done, shipped not deployed |
| LF.288 | the restart helper (LF.285) started `start.sh` detached and a test that failed before `stop()` left the service running; after a morning of runs 130 orphaned services (about 4 GB) were alive in the worker and its process was killed with SIGKILL mid-run (14:31 JST). The helper now unrefs and tracks every service it starts and stops them all when its process exits (and on SIGINT/SIGTERM), and marks each with `HARNESS_SERVICE_OF`; after every sandbox command the harness stops any orphan carrying the mark under that workspace. Real-process test: a test that never calls `stop()` leaves no service behind. Test `test_a_service_a_test_never_stopped_does_not_outlive_its_test.py`. | done |
| LF.289 | two 9/9 products were stopped as failed because the locked suite passed Playwright's `request` fixture a fetch-style `body:` (the API takes `data`), so every write got 400; the restart helper's guide (LF.285) had said "write with fetch" and QA started its own service in most tests. The review now finds a `body:` beside `method:`/`headers:` in a file using the fixture (directly or through a helper) as a test that cannot pass, with the correction; the guide keeps the helper to the restart criterion and says `data: { ... }`. Deep review 2026-10-26, F1 (a)(b). Test `test_a_test_that_passes_a_fetch_body_to_the_request_fixture_cannot_pass.py`. | done |
| LF.290 | the suite ran two or three times a round on an unchanged product (after each fix in `ci.take`, as the round opened, and the unit tests again on the fast path). With `MEASURE_ONCE` on (compose on): when nothing was put back or installed, the saved run's fingerprint equals the product's, the command is the same and its report is on disk, the saved run stands and is judged again against the criteria as they are now; a change to the product or the suite runs it again. Deep review 2026-10-26 §5 item 1. Test `test_a_product_the_suite_has_measured_is_not_measured_again_until_it_changes.py`. | done, shipped not deployed |
| LF.291 | a defect fixed as a side effect of fixes run side by side was never closed without a fixer: `passing_since_reported` accepted `before/after defect_fix_{round}_{n}` and the batch is measured as `defect_fix_{round}_batch`. The batch label now counts. Independent code review 2026-10-26 item 8. Test in `test_a_defect_an_earlier_fix_resolved_is_closed.py`. | done |
| LF.292 | the dispute's re-measure ran every acceptance file alone though only the disputed tests matter (a service suite starts a server per file). `tests_that_fail_alone` now passes the disputed tests' criterion tags as `naming`, so only their files run. Independent code review 2026-10-26 item 5. Test in `test_a_disputed_test_is_re_measured_and_reclassifications_are_capped.py`. | done |
| LF.293 | after the host moved to Python 3.14 (Ubuntu 26.04 release upgrade, 2026-10-26) the JSON trailing-comma repair stopped working: 3.13+ reports "Illegal trailing comma before end of object/array" and points at the comma, where 3.12 said "Expecting property name" after it. Both wordings are recognised. Test in `test_a_json_edit_s_commas_are_put_right.py`. | done |
| LF.294 | the settings page's general Save wrote the frontier (judgement) model from whatever the page held; on 2026-10-26 a general save six seconds after the owner saved Qwen3.6 as the frontier model wrote it empty and turned it off (audit log 15:09:19 and 15:09:25 UTC). The general save now writes the frontier fields only when it carries a frontier model; clearing is the frontier section's own "No model" (`PUT /settings/frontier`). Test `test_a_judgement_model.py`. | done |
| LF.295 | RD.1, built: a re-plan's redraft rewrote every planned file (`draft_work_orders` had no "already there and passing" gate) and the best-attempt undo had to put the product back in about half the runs of a day (16 tests to 15, 7 to 0, 3 to 0, 24 to 23), each after a test round on the wreck. On a re-plan whose best product passes at least half of the suite, a planned file still exactly as it was at the best commit is not drafted again; its work order counts as done with the file named in its decisions. New and changed files are drafted; a product under half keeps the full redraft. Refined after its first run (run-eabc53e3: at 8 of 9 tests it kept one file because the fixers had improved the others since the best commit, redrafted five, and the product fell to 2 of 10): when the product as it stands passes at least as many tests as the best, every existing planned file is kept as it is now. Behind `KEEP_THE_BEST_ON_A_REPLAN` (compose on). Independent code review 2026-10-26 item 2. Test `test_a_re_plan_does_not_redraft_what_the_best_product_already_has.py`. | done |
| LF.296 | the product's fingerprint (`unstable.fingerprint`, which `MEASURE_ONCE` relies on) listed untracked files by name only, so a new file changed again before anything committed it read as unchanged and a stale measurement could stand. Untracked files' contents are now hashed in (at most 2,000 files, 1 MB each). Found while auditing the first runs with `MEASURE_ONCE`; not seen to cause a wrong result. Test `test_a_new_file_changed_before_a_commit_changes_the_fingerprint.py`. | done |
| LF.297 | start probe: a product whose `/health` answered 503 while its data folder did not exist made the suite's web server time out for 40 minutes and three sprint attempts; the defect said only "Timed out waiting 60000ms" because Playwright does not pass on the service's output or the readiness answer. When the product does not start, the harness now starts it the suite's way (`sh start.sh`, free `PORT`, a fresh `DATA_DIR` that does not exist yet), polls the readiness URL from the kept Playwright configuration for 12 seconds, stops the process group, and adds what the service printed and what the URL answered to the start defect (with what a 4xx/5xx there means). Behind `START_PROBE` (compose on). Test `test_a_product_that_does_not_start_is_started_the_suite_s_way_and_reported.py`. | done |
| LF.298 | a stage's own commands ran on imports the harness would only repair when it measured: on a small-model Hono run the drafted tests imported `../src/datastore.js` where `src/datastore.ts` existed, and the two testing work orders ran `npm test`, read ERR_MODULE_NOT_FOUND and spent 55 calls (30 refused) writing a `.js` re-export and editing files another work order owned; the harness then added the extensions at its first measurement. `imports_before_a_run.put_right` (switch `EXTENSIONS_BEFORE_A_RUN`, off in code, on in compose) adds the `.ts` the scaffolded pack needs before any command a stage runs, before the files the command may not change are noted, and the command's note says so. Packs without `relative_import_extension` are untouched. Test `test_a_command_a_stage_runs_sees_the_imports_node_will_load.py`. | done |
| LF.299 | the start defect's compiler list dropped a type imported as a value: on a small-model Hono run the service stopped with "'./models.ts' does not provide an export named 'Note'" (an interface imported without `type`), `tsc` reported it as TS1484, and the defect listed only an unrelated TS2339. `compiler_errors.parse` now keeps TS1484/TS1485 (`_A_TYPE_IMPORTED_AS_A_VALUE`), the errors Node's type stripping turns into a crash. Test added to `test_a_product_that_does_not_start_carries_the_compiler_s_missing_names.py`. | done |
| LF.300 | a locked test read the `request` fixture's response `status` without calling it: on a small-model Hono run `expect(response.status).toBe(201)` sat beside `expect(resp.status()).toBe(200)` in the same suite, a comparison of a function with 201 that fails on every product and that no check named (the reopen named only the restart tests' `resp.status is not a function`). `suite.responses_read_without_the_call` finds a name assigned from `await request.<verb>(` read as `.status`, `.ok`, `.statusText` or `.headers` with no call, and is one of `tests_that_cannot_pass`; a plain `fetch` response is left alone. Test `test_a_response_status_read_without_the_call_cannot_pass.py`. | done |
| LF.301 | a TypeScript file Node runs as it is was parsed only by the compiler's parser, which does not report a name declared twice: on a small-model Hono run two rewrite fixes in a row declared `const body` twice in one handler, the write passed, the service did not start (`Identifier 'body' has already been declared`), and both were reverted for breaking 25 tests. `node --check` on a `.ts` module does not parse function bodies either, so in a pack whose TypeScript Node runs itself (`relative_import_extension == '.ts'`) `javascript_parse.parse_error` now removes the types the way Node does (`module.stripTypeScriptTypes`, lines kept) and checks the JavaScript beside the real file; syntax Node cannot strip (`enum`) is named too. A pack that compiles its TypeScript keeps the compiler's parser only. Test `test_a_typescript_file_node_runs_itself_is_parsed_by_node.py`. | done |
| LF.302 | QA rewrote a working `request.post(path, { data: note })` as `{ json: note }` on a small-model Hono run; Playwright's request fixture has no `json` option (only `route.fulfill` does), so the request sends no body and fails on every product, and the fetch-body check (LF.289) looked only for `body:`. `requests_with_a_fetch_body` now also finds a `json:` key opening the options object handed straight to `request.<verb>(`, and its message says a `json:` option is not read either; `route.fulfill({ json })` and a note with a field called `json` are left alone. Test added to `test_a_test_that_passes_a_fetch_body_to_the_request_fixture_cannot_pass.py`. The message names `json:` when that is the only misuse in the file (it first said `body:`, which QA could not find). | done |
| LF.303 | settle-when-green (LF.284) recognised a unit-test defect only by the harness's own opening words "The unit tests fail."; a test round's model words the defect itself ("the error handler answers with a body where the test expects none"). Measured on a small-model Hono run: 18 of 18 criteria passed for three rounds and the sprint was planned again twice for two such defects. `settle_when_green._a_unit_test_failure` also counts an open defect that carries the test command the round left failing (`caught_by`), when that command is not the acceptance suite's and the defect names no failing criterion; an opinion with no failing command still keeps the sprint open. Tests added to `test_a_sprint_with_a_green_acceptance_suite_is_not_planned_again_for_a_unit_test.py`. | done |
| LF.304 | the release's interface-contract check reported false gaps in two runs in a row, both on products that passed every hidden test. On one run every contract line was written quoted whole (`"AC-1 POST /notes -> 201"`), so none followed a form and all 8 went unchecked. On the other, `AC-1 POST /notes -> 201` was probed with a bare request and failed for the 422 a product that checks its input rightly answers. `interface_contract.parse` now removes a quote that wraps the whole line (a page line's `"Email"` stays). A `POST`/`PUT`/`PATCH` line with a 2xx status is now listed as unchecked ("a write that succeeds only with a body") instead of failed; a line that says a write is refused (`-> 422`) is still probed. Tests added to `test_the_interface_contract_is_locked_and_checked_at_release.py`. | done |
| LF.305 | a compiler error in a file the harness keeps pointed the fixers at a file they may not change. On a small-model Hono run `createApp` was made `async`, so the kept `src/main.ts` handed `serve` the `fetch` of a Promise and `/health` answered 500. The compiler's error was `main.ts` line 7 (TS2339 `fetch` on `Promise<Hono>`), and two fixes left the product unstarted. `compiler_errors.the_errors` now adds to such a line that the file stays exactly as it is, with its text, and that what it uses is to change in the product's own files. Test added to `test_a_product_that_does_not_start_carries_the_compiler_s_missing_names.py`. | done |
| LF.306 | the redraft after a re-plan wrote `async createApp()` again, so the cause behind LF.305 recurred: no service pack's guide said the factory its kept start file calls returns the application itself. `_service.FACTORY_GUIDE` (stack guidance, in the packs) is added to the Hono native, Hono and Node HTTP packs: not `async`, never a Promise, and data loaded inside the handlers or on the first request. `builder_facts.MOST_GUIDE_CHARACTERS` goes from 2,500 to 3,000 so the native pack's guide (now 2,525) still reaches the builders whole. Test `test_a_service_pack_says_its_factory_is_not_async.py`. | done |
| LF.307 | LF.305's note said a kept file stays, but it named no product file. The rewrite fixer works on the files a defect names, so two more fixes rewrote `routes/notes.ts` and were reverted while `createApp` stayed `async`. The note now names where each name on that line comes from, read from the kept file's own imports: "`createApp` in `notes-api/src/app.ts`", workspace-relative, the form the fixer's file picker reads. Test updated in `test_a_product_that_does_not_start_carries_the_compiler_s_missing_names.py`. | done |
| LF.308 | the net-gain rule (NG.1) weighed every test alike. On a small-model Hono run a fix that brought up a product that had not started for an hour made 15 tests pass and broke 8 of the workers' unit tests. It was reverted because 15 is under 3 × 8, and the product went back to not starting. `net_gain.keeps` now keeps a fix that makes at least `MIN_GAINED` locked acceptance tests pass and breaks only unit tests, whatever the ratio; the locked suite is the definition of done, and the next round raises the broken unit tests. Unit-only gains still answer to the ratio, and a lost criterion still needs the larger gain. Tests in `test_a_fix_that_gains_much_and_breaks_one_unit_test_is_kept.py`. | done |
| LF.309 | a factory made `async` stopped a product for its whole run. On a small-model Hono run the first draft wrote `export async function createApp()`, and the kept `src/main.ts` served `createApp().fetch` (undefined on a Promise), so every request answered 500. Four sprint attempts, LF.305-307's notes and LF.306's guide line did not bring the model to undo it, and the run failed with hidden 0/9 and 10 reverted fixes. The native Hono pack's kept start file now does `const app = await createApp();` (an ES module, so top-level await), which serves either form; its smoke test awaits the factory too. Measured on that run's product: started this way it answered `/health` 200 and `POST /notes` 201, and `tsc` reports nothing on `main.ts`. Test in `test_a_service_pack_says_its_factory_is_not_async.py`. | done |
| LF.310 | a criterion the locked suite has no test for went round as a product defect for ever. On a small-model Hono run the suite was locked with AC-15 untested (QA judged it not testable through the request fixture but did not defer it). Every round raised it for the product, the dispatch closed it at once because none of its tests failed, and the sprint was planned again: four rounds and a re-plan in two minutes at 17 of 18 with every test passing. `acceptance_for_round` now adds the suite's own gap message for each due criterion with no test to the tests that cannot pass, so the round reopens the suite for QA to write or defer it, within the same repair budget. Test `test_a_due_criterion_with_no_test_goes_back_to_qa.py`. | done |
| LF.311 | the pack contract's finding (PACK_ENTRY_EXPORTS_KEPT: `src/app.ts` no longer exports `createApp`) was merged under the round's "The unit tests fail" defect and lost its lead. On a small-model Hono run the draft wrote `export default function createApp(storageService)`, the service could not start (`does not provide an export named 'createApp'`), and the fixers read only the generic symptom. `_names_a_cause` now counts the `pack contract` source as a cause like the language service's, so its description leads the merged defect. Test added to `test_one_defect_per_cause.py`. | done |
| LF.312 | keep-the-best on a re-plan (LF.295) left a product under half the suite to a full redraft on every re-plan. On a small-model Hono run, at 4 of 11 tests two re-plans in a row redrafted every planned file and each fell to 0. The undo put 3 files back each time, and the escalation stopped the run (hidden 5/9, the best product's). From the second re-plan (`AFTER_A_FULL_REDRAFT = 2`) a best product above 0 keeps its files too: one full redraft has already been tried. Test added to `test_a_re_plan_does_not_redraft_what_the_best_product_already_has.py`. | done |
| LF.313 | two runs in a row drafted `export default function createApp(<a parameter>)` (`storageService`, then `dataDir`), and the kept `src/main.ts` could not load the product (`does not provide an export named 'createApp'`). The native Hono pack's start file now imports the module whole and serves `createApp` or the default export, awaited (checked in the worker: a named async factory and a default export both answer `/health` 200; `tsc` reports nothing on `main.ts`). `_service.FACTORY_GUIDE` now says the factory is a named export that takes no parameters and reads `DATA_DIR` and the like from the environment. A factory that needs an argument cannot be bridged, so it stays a defect; the pack-contract check still asks for the named export. Tests in `test_a_service_pack_says_its_factory_is_not_async.py`. | done |
| LF.314 | a worker that found the orphan-recovery lock taken skipped recovery for good. After a host Docker restart, the worker that came up took the two-minute lock and was replaced by a deploy within it; its sweep died with it, the new worker logged "Another worker is recovering abandoned runs; skipping", and the live run sat at `running` for 11 minutes until the worker was restarted by hand. `_recover_runs_their_worker_abandoned` now starts `_sweep_when_the_lock_lapses`, which waits out the lock, takes it and sweeps unless another worker has it again; the sweep only touches runs no live worker claims, so a second look is safe. Test added to `test_orphan_recovery_on_start.py`. | done |
| LF.315 | owner request 2026-10-27: an admin page (`/admin`, nav "Admin") lists every switch in `provenance.SWITCHES` with what it does. The explanation comes from the switch's own documentation: its object's `explanation`, a guide's title and line, its `enabled` docstring, else its module docstring; the rest of that docstring is behind a details toggle. Each switch is set On, Off or Docker. The stored setting (`runtime_settings.save_switch`, rows `switch:<NAME>`) beats the deployed environment, which beats `ON_BY_DEFAULT`; `app.switches.is_on` reads it through the 5-second settings cache when `SWITCH_OVERRIDES_FROM_SETTINGS` is on (compose: on), so a change reaches every process and a live run within seconds. `GET /api/settings/switches` for anyone signed in; `PUT /api/settings/switches/{name}` for an administrator, audited and refused under `SETTINGS_READ_ONLY`. Tests `test_switches_are_set_on_the_admin_page.py` and `langchain-ui/src/pages/Admin.test.tsx`. | done |
| LF.316 | measured on one run: the product's unit tests spawned children with a working directory given relative to the wrong folder; Node reported `spawn /bin/sh ENOENT`; the harness's own unit run became the defect without the note a stage's own command gets for that output (`sandbox._a_missing_path_that_is_here`), and two fixes concluded the shell was missing, changed nothing, and the sprint was planned again twice. `workflow._the_unit_tests_fail` now adds that note to the defect when the output names a path that exists here as missing. Test `test_a_failing_unit_run_that_calls_a_present_program_missing_says_so.py`. | done |
| LF.317 | measured on one run: a suite repair turned nine tests into `test.skip('[AC-n] ...', async () => {})` with empty bodies (155 lines of checks deleted) and the review locked it, since each criterion still had a test of its name. Every round charged those criteria to the product, and the dispatch re-measure closed each without a fixer because a skipped test counted as passed; the sprint was planned again with nothing fixed. `suite.tests_the_runner_skipped` (in `vacuous_green`, so the review never locks it, a test round sends it to QA and release refuses it): a criterion's test the runner reports skipped, when the text writes it skipped or no test failed. `per_file._its_own_tests` returns `skipped`, not `finished`, when none of a defect's own tests passed. Test `test_a_skipped_acceptance_test_proves_nothing.py`. | done |
| LF.318 | the same run: the stubs came from the repair guard - a repair refused for removing tests it was not sent for wrote them back as empty `test.skip(...)`, keeping only their names; sent back for the stubs, every rewrite was refused again for removing them, and QA wrote three new spec files beside the file instead. `suite.tests_a_repair_would_drop` no longer holds a test the locked file only skips, and counts a kept test made into a skipped one as removed. Test `test_a_suite_repair_may_drop_a_skipped_stub_but_not_skip_a_test.py`. | done |
| LF.319 | the same run, rewound on LF.318: QA (whose stubs said "skipped due to incomplete implementation") had written the criteria's real tests in a new file and left the stubs, and LF.317 refused the suite for the stubs alone round after round. `suite.tests_the_runner_skipped` now names a skipped test only for its criteria no other test ran for. Test case in `test_a_skipped_acceptance_test_proves_nothing.py`. | done |
| LF.320 | the same run: the product answered `/health` 500, and each fixer write was followed by its defect's tests run file by file (VERIFY_AFTER_WRITE); each of five files waited out the runner's 60-second server wait - five minutes a write. `per_file.each_file` stops running files once one's output shows the product never started (`suite.the_product_did_not_start`) and gives the rest that file's outcome, saying why they were not run. Test `test_a_product_that_does_not_start_is_not_waited_for_once_per_file.py`. | done |
| LF.321 | LF.320 never fired live: one acceptance file's run (`probe`, 60 s) had the same limit as the pack's suite wait for the server (60 s), so the sandbox stopped each run just before Playwright said the server never came up. `StackPack.server_wait_ms` (set by `_service.service_pack` from `server_timeout_ms`); `sandbox.timeout_for("probe")` gives at least that wait + 15 s. Test `test_one_acceptance_file_is_given_longer_than_the_suite_waits_for_its_server.py`. | done |
| LF.322 | the same run: four fixes in a row were made, measured and reverted because the product died at start with `ReferenceError: NoteStore is not defined` - `import type { NoteStore }` and then `new NoteStore(dataDir)`; the types are stripped with the import. The language service reports it as TS1361 (1362 for `export type`), which was not among the codes it treats as certain, so the write was not refused. Both added to `language_service` NAMES. Test `test_a_type_only_import_used_as_a_value_is_underlined.py` (needs the worker's TypeScript; proven failing on the old code and passing on the new in the worker). | done |
| LF.323 | measured on one run: the product served none of its routes, `await res.json()` on its text `404 Not Found` threw `SyntaxError: Unexpected non-whitespace character after JSON`, and the JavaScript pack's test-bug pattern read every `SyntaxError` as the test's own error - the locked suite was reopened for fourteen right tests. A SyntaxError naming JSON is no longer a test bug (`_javascript.TEST_BUGS`). Test `test_a_response_that_is_not_json_is_the_product_s_not_the_test_s.py`. | done |
| LF.324 | the same run: QA was refused an edit of the product's `src/app.ts`, and the check that asks a stage once to fix certain errors in files it touched counted the refused call, so QA was asked to fix the product's missing import and spent sixteen more refused writes. `_diagnostics_in_files_touched` counts only writes whose result succeeded. Test `test_a_stage_is_not_asked_about_a_file_it_was_refused.py`. | done |
| LF.325 | the same run: with the suite's repairs spent, the test round still reported "Acceptance test all_ops.spec.js uses fetch and expects listRes.status()" - testing-owned, naming no criterion - and two fix stages each answered that the locked suite was wrong and changed nothing. `_defects_only_about` also sets aside a testing-owned finding that names only the locked suite's files (and no criterion outside those beyond repair). Test case in `test_a_locked_test_beyond_repair_goes_to_no_fixer.py`. | done |
| LF.326 | the same run: AC-6/AC-17's only test was beyond repair, the round set aside the model's own reports about them, but its backstop (`failing_due_defects`) raised "the acceptance suite says this does not work yet" for each every round, and the sprint was planned again three times (about an hour) for criteria no fix could prove. `acceptance_nodes.defer_what_is_beyond_repair` defers them with why once the suite may not be repaired again, and the backstop's defects for them are set aside in that round. Test case in `test_a_locked_test_beyond_repair_goes_to_no_fixer.py`. | done |
| LF.327 | owner 2026-10-27 ("yes" to the proposal): settle-when-green applies from the first exhaustion (`AFTER_REPLANS = 0`). Measured on one run: the one re-plan it waited for redrafted a product whose 12 acceptance tests all passed, for the model's own unit test, and the escalation then accepted it as it was (about 7 minutes). Test `test_a_sprint_with_a_green_acceptance_suite_is_not_planned_again_for_a_unit_test.py` (`test_the_first_exhaustion_settles_too`). | done |
| LF.328 | measured on two runs in a row: the acceptance test that restarts the service calls `fetch` itself, and wrote it the request fixture's way - `data: {...}` as the body (fetch sends none; 400) in one, `res.status()` on a fetch response in the other. Each was found only after the suite was locked, cost repairs, and (in the first) shipped AC-6/AC-17 unproven. `suite.fetch_calls_written_like_the_fixture`, among the checks that keep a suite from locking and reopen it (`tests_that_cannot_pass`): a top-level `data:` in a plain `fetch(` call's options with no `body:`, and `status`/`ok`/`statusText` called on a fetch response. Test `test_a_fetch_call_written_like_the_request_fixture_cannot_pass.py`. | done |
| LF.329 | measured on one run: a spec named a fixture response `getResp` in one test and a `fetch` response `getResp` in the restart test. The response checks bound a name to one kind for the whole file, so the restart test's correct `getResp.status` was called the fixture's misuse, and its correct `fetch(..., { body })` a fetch-style body handed to the fixture (any file using the fixture). QA was sent to "repair" right lines - it changed a correct `createResp.status` to `createResp.status()` - and the suite went round its review without locking. Each read is now judged by the last assignment of its name before it (`suite._the_kind_assigned`), and a `body:` in a plain `fetch(` call's own options is left alone (`_the_start_of_the_object_around`). Test `test_a_name_reused_for_fetch_and_the_fixture_is_judged_by_its_own_assignment.py`. | done |
| LF.330 | measured on one run: the health handler built its answer with `c.body('OK', ...)` and returned nothing (typed `void`); every request failed inside `@hono/node-server` with `TypeError: res.body.getReader is not a function`, which names neither the handler nor the missing `return`, and the product never started across two sprint attempts. Both Hono packs' guides now say to return the answer the context builds and name that error. Test `test_a_hono_pack_says_a_handler_returns_its_answer.py`. | done |
| LF.331 | the same run: a second health route in `app.ts` (`(c) => { c.text('OK', ...) }`) still returned nothing; the start defect carried the compiler's "app.ts line 42: No overload matches this call." but not the innermost line of its explanation, "Type 'void' is not assignable to type 'HandlerResponse<any>'", which names the fault. `compiler_errors.parse` appends each error's innermost explanation line. Test `test_a_compiler_error_carries_its_innermost_reason.py`. | done |
| LF.332 | measured on one run: the draft wrote `import { Router } from 'hono/router'` and `new Router()`, Express's way; Node stopped at start ("does not provide an export named 'Router'") and two fixes were refused or reverted for importing a `Router` from `hono` in turn. Both Hono guides now say an area's routes are their own `new Hono()` and that there is no `Router`. Test `test_a_hono_pack_says_an_area_is_its_own_hono.py`. | done |
| LF.333 | measured on one run: both AC-15 tests read `request.baseURL` - Playwright's request fixture has no such property (`undefined`) - and one compared it with `process.env.PORT ?? '3000'`, which the suite gives only to the server it starts. Both failed on every product and went to the fixers. `suite.reads_of_what_the_test_does_not_have`, among `tests_that_cannot_pass` (keeps the suite from locking, reopens it), names each with the `baseURL` test argument as the way. Test `test_a_test_reading_what_the_fixture_does_not_have_cannot_pass.py`. | done |
| LF.334 | owner 2026-10-27 ("implement your best suggestion" on mutation-guided tests): `MUTATION_GUIDED_TESTS` was on all day and never probed - it asked that every unit test pass first, and a unit test the model wrote nearly always failed; and it ran only with nothing open. The unit tests are now measured as the set that passes (from their JUnit reports; a bare pass/fail stays as before): a change is noticed when a passing unit test fails with it, a finding is settled when a test passes without the change and fails with it. The probe also runs, once an attempt, when the due criteria pass and every open defect is a failing unit test, so its findings join that fix round. Tests in `test_mutation_guided_tests.py`. | done |
| LF.335 | owner 2026-10-27 ("implement your best suggestion" on re-reads): measured on one run, 28 of 197 model calls were reads of files already in the stage's opening memory, each answered with a pointer that brought nothing back. Behind `FIRST_REREAD_ANSWERED` (compose on): a stage's first read of a held, unchanged file of up to 400 lines gets its numbered lines; a second read gets the pointer, as before. Test `test_a_first_re_read_of_a_held_file_gets_its_lines.py`. | done |
| LF.336 | measured on one run: `app.get('/health', () => ({ status: 'ok' }))` returned a plain object; `@hono/node-server` read it as a response whose status is `ok`, every request failed with `RangeError: Invalid status code: ok`, and the product did not start through the first sprint attempt. Both Hono guides now say a handler that returns a plain object fails with `Invalid status code` (beside LF.330's missing `return`); the typecheck aside was trimmed to keep the guide under 3,000 characters. Test `test_a_hono_pack_says_a_handler_returns_its_answer.py`. | done |
| LF.337 | deep review F3 (owner 2026-10-27: build the review's items): of 5 false acceptances over 19 runs, 4 shipped the failing behaviour as a deferred criterion. `LAST_TRY_ON_DEFERRED` (compose on): before release each deferred criterion with a locked test (at most 3) gets one single-call rewrite aimed at it (`rewritten_fixes.fix_by_rewriting` with its tests' failures); kept, and the criterion taken off the deferred list (`suite.undefer`), only when its tests pass and every test that passed still passes, else its files are put back. Test `test_a_deferred_criterion_gets_one_last_try_before_release.py`. | done |
| LF.338 | deep review F7: 295 edit refusals in 20 runs for an anchor that matched nowhere or several times. An anchor that matches once with all spacing left out (20+ characters) is applied, saying so; and an edit whose `replace` keeps the anchor and adds new lines after it, where the last occurrence ends the file, is an addition at the end (QA adding a test after `});` was refused nine times in one run). A change to one of several matches is still refused. Test `test_an_edit_anchor_off_only_by_spacing_or_appending_at_the_end_is_applied.py`. | done |
| LF.339 | deep review F9: the ledger recorded a defect's description and outcome, not what each fixer was shown. `defect_ledger.shown` records, as each fix request is built, a fingerprint of the request, its size and its sections. Test `test_the_ledger_records_what_each_fixer_was_shown.py`. | done |
| LF.340 | measured on several runs of one day: `GET /notes/:id -> 200 or 404`, `PUT /notes/{id} -> 200 or 400/422 or 404`, `DELETE /notes/:id -> 204 or 404` went unchecked at every release ("follows none of the contract's three forms", "a route with a parameter in it"). The contract reads `A or B` and `A/B` as the statuses allowed (`Check.statuses`); a route with a parameter, or a bare write that succeeds only with a body, is checked when its line allows a 4xx - probed with a record that does not exist (`999999999`); the compiled check accepts any allowed status. Reader corpus accepted (only the new `statuses` field). Test `test_a_contract_line_with_alternatives_or_a_parameter_is_checked.py`. | done |
| LF.341 | measured on one run: two fixers reported `sqlite3` could not be imported as an ES module, changed nothing, and one ran to the 60-call cap; `await import('sqlite3')` loaded it. A fix stage that changes nothing and names a declared dependency with import/module/resolve wording gets it loaded by the harness through a per-runtime table (`_LOAD_A_PACKAGE`, Node now); the defect then carries "`X` loads in this project ... the cause is elsewhere" (or the real load error) for the next fixer. Test `test_a_fixer_s_claim_that_a_package_cannot_load_is_checked.py`. | done |
| LF.342 | LF.339's ledger entry was written on every resume of a fix stage (a gated tool call pauses and resumes the graph, and the request is built again): every 6 to 10 seconds for one fixer on the first run after it shipped. Recorded only on the stage's first entry (no `pending_inner_thread_id`). Test in `test_the_ledger_records_what_each_fixer_was_shown.py`. | done |
| LF.343 | backlog B8, measured on one run: told that two tests read `request.baseURL` and `process.env.PORT`, QA's repair fixed one and kept the other, the suite's repairs were spent and the criterion shipped deferred. The checks that know the exact correction (an uncalled fixture `.status`, a called `fetch` `.status()`, `request.baseURL`) now quote each line they name with the line as it should read (`suite._the_lines_corrected`, up to 4 lines). Test `test_a_check_that_knows_the_fix_gives_the_corrected_line.py`. | done |
| LF.344 | measured on one run: a fixer wrote `notes-api/tmpCheckMultiple.js` to probe an import; the revert gate read the language service's error in it as the fix breaking the product and put the whole fix back. `file_kinds.SCRATCH_NAME` knew `tmp_check.js`, not camelCase: `tmp`/`scratch` followed by a capital (case kept) is scratch now; `temp`/`debug` camelCase stay product (`tempConverter.js`, `debugLogger.ts`), since the sweeper deletes what matches. Test `test_a_camel_case_throwaway_is_scratch.py`. | done |
| LF.345 | backlog B11, measured on one run: mutation-guided tests (QM.2, LF.334) had the testing role write three unit tests, each proven to fail with its change, and the run's mutation score still read 0.583 - `scripts/bench/mutate.py` counted only the locked suite. It now runs the product's unit tests beside the suite for each change (`mutation_guided._run_the_unit_tests`, by passing names) and adds `caught_with_unit_tests` and `score_with_unit_tests`; `score` stays the suite's, for comparison across runs. Test `test_the_mutation_score_counts_the_unit_tests_too.py`. | done |
| LF.346 | measured on one run: `healthRouter.get('/health')` mounted with `app.route('/health', healthRouter)` served `/health/health`; the start defect said the readiness route was not served (LF.297) but never which routes were, and the product did not start through two rounds of fixes. `StackPack.list_routes` (the native Hono pack prints `app.routes` of `createApp()`, one `METHOD /path` a line); `start_probe` adds them when the readiness route answers 404, with the note that a mounted router's route is served under the mount's path. Test in `test_a_product_that_does_not_start_is_started_the_suite_s_way_and_reported.py`; checked on the live workspace (`GET /health/health`). | done |
| LF.347 | measured on two runs (identical calls 6.3% and 6.6%, mean 3.4%): QA re-sent one edit of a line every test repeats, each refused as ambiguous with the lines named. The refusal now gives, for each copy (at most 4), the `replace_lines` arguments that change it alone (`start_line=N, end_line=M`). Test in `test_an_edit_anchor_off_only_by_spacing_or_appending_at_the_end_is_applied.py`. | done |
| LF.348 | measured on one run: a unit test wrapped the promise-based `sqlite` API in callbacks that never fire; its promise never settled and `node --test` ran to the sandbox's 300-second limit on every unit run the harness made (two in a row, ten minutes, with the suite already 17/0). Every pack that runs Node's own test runner (unit and acceptance scripts) now passes `--test-timeout=20000` (`_javascript.TEST_TIMEOUT`), so a hang fails in seconds and names its test. Test `test_a_unit_test_that_never_settles_fails_in_seconds.py`. | done |
| LF.349 | the same run: in one test round, with no fix between, the harness ran the same `npm test` four times (the round's checks each ask), five minutes each on a unit test that never settled - twenty minutes on an unchanged product with the suite at 17/0. Under `MEASURE_ONCE` the harness's unit run is kept with the product's fingerprint (`unstable.fingerprint`) and command in `.harness/unit-result.json`, and stands while both are unchanged. Test `test_an_unchanged_product_s_unit_tests_are_run_once.py`. | done |
| LF.350 | LF.349 still ran an unchanged product's unit tests again: the fingerprint began with HEAD's commit id, and the harness commits its own records (decision log, summaries) between measurements. `unstable.fingerprint` now hashes the product's files as committed (`git ls-tree -r HEAD`, less `.harness/`, `docs/`, test results and caches) instead of the commit id - for the suite's MEASURE_ONCE too. A commit of nothing is the same product (test updated). Test `test_a_commit_of_only_the_harness_s_records_leaves_the_product_fingerprint.py`. | done |
| LF.351 | measured on one run: `POST /notes` answered 500, every test that created a note failed on `res.json()` of "Internal Server Error", and the server had logged `Error: Internal server error at NotesRepository.save (src/services/persistence.ts:44)` in the suite's output under Playwright's `[WebServer]` prefix - no fixer was shown it, and five in a row changed nothing or chased the tests. `acceptance_nodes.what_the_server_logged` keeps the server's error lines and their frames in the product's own files (not `node_modules`, not Node internals), and each failing criterion's defect carries them (LF.274 did this for the Python service packs' log). Test `test_a_failing_criterion_carries_what_the_product_s_server_logged.py`. | done |
| LF.352 | the same run: the logged frame (LF.351) was `throw new Error('Internal server error')` inside `catch (_)` - the real cause, a data folder the constructor never made (`mkdirSync(dirname(dir))`), was thrown away, and nine fixers saw only the replacement. `acceptance_nodes.what_the_logged_frames_hide`: when the first product frame logged is a `throw new ...Error(`/`raise X(` line just below a handler that does not pass on what it caught, the defect says so and how to let the cause through. Tests in `test_a_failing_criterion_carries_what_the_product_s_server_logged.py`; checked on the live workspace. | done |
| LF.353 | measured on one run: QA wrote five suite files `<x>_spec.js` where the runner collects `*.spec.js`; told each time that the name was the reason, it wrote right-named copies of three and left two, and after five rounds the run failed ("the acceptance suite proves nothing"). `suite.rename_files_the_runner_skips`, at the start of the review: a file whose name ends in `_` or `-` plus the pattern's suffix (`*.<suffix>` patterns only) is renamed to the pattern's form when that name is free. Test `test_a_suite_file_the_runner_skips_by_its_name_alone_is_renamed.py`. | done |
| LF.354 | measured on one run: the start-script test's `fetch` got no answer - the service it started had not come up - and `TypeError: fetch failed` reopened the locked suite as an error in the test's own code (the JavaScript pack read every `TypeError` so). Node's network failure is no longer a test bug in `_javascript.TEST_BUGS`, beside LF.323's JSON parse. Test in `test_a_response_that_is_not_json_is_the_product_s_not_the_test_s.py`. | done |
| LF.355 | LF.351 read the server's errors from the saved output, which is its last 3,000 characters: on the next run the error behind `POST /notes` answering 500 had been logged early in a long run and was cut, and the defects showed a later `NotFoundError` instead. The suite now takes `server_log` from the whole output as it runs (`suite.what_the_server_logged`, moved from `acceptance_nodes`), saves it with the result and keeps it when a saved run is reused (MEASURE_ONCE); the defects read it first. Test in `test_a_failing_criterion_carries_what_the_product_s_server_logged.py`. | done |
| LF.356 | backlog B13, measured on one run: every fix of AC-5 (DELETE answers 204) was reverted for breaking AC-7's "DELETE returns JSON", five times over two attempts, and the dispute for a test two reverted fixes broke (`_a_locked_test_two_fixes_broke`) was never held: its gate asked whether the *failing* tests could be repaired again - they had been - and not the contested one, passing and never sent. `_a_dispute_may_be_held_now(state, also=[contested])` counts the contested test too, so `may_repair` allows it up to the overall repair limit. Test `test_two_locked_tests_that_contradict_are_judged_after_repairs_are_spent.py`. | done |
| LF.357 | backlog B13b, measured on one run: the brief says `DELETE /notes/{id}` answers 204, AC-7's test asserted a JSON content type on every response (a successful delete included), and each fix that made the delete criterion pass broke that one test and was reverted - eight times over four attempts - with the suite past its overall repair limit, so no dispute could judge it (LF.356). `workflow._a_contested_test_past_repair`: a passing locked test that three reverted fixes broke, and that the suite may no longer be repaired for, is passed to `engineering.after_a_fix(contested=...)`, which keeps a fix whose only casualty is that test, that made other tests pass and leaves the product running; the contested test then fails openly and the release names it. Test `test_a_contested_test_past_repair_does_not_revert_a_fix_alone.py`. | done |
| LF.358 | LF.357 never fired live: its three reverts were counted within one attempt's fix cycle, which a re-plan starts afresh, and the run's attempts had two each while the same test reverted eight fixes over four. `REVERTS_BEFORE_A_TEST_IS_CONTESTED` is two, the evidence a dispute is held on. Test updated in `test_a_contested_test_past_repair_does_not_revert_a_fix_alone.py`. | done |
| LF.359 | backlog B14, measured on one run (hidden 5/9): AC-7's test looped over every endpoint, the DELETE included, asserting a JSON content type; the contract said `DELETE /notes/{id} -> 204 or 404`, and every fix that made delete right broke it and was reverted, eight times. `suite.tests_that_want_json_from_a_204`: a test that asserts a JSON content type on a DELETE (the fixture's call, or a table entry a loop sends) where the contract's DELETE succeeds only with 204 cannot pass - at the review against the specification's contract (before it is recorded), and among `tests_that_cannot_pass` against the locked one. Checked on the failed run's file. Test `test_a_test_wanting_json_from_a_204_cannot_pass.py`. | done |
| LF.360 | measured on one run: the CommonJS-in-a-module check told QA to "use `import` (`import { test, expect } from '@playwright/test';`)" about a `const { startService } = require('./service.cjs')` inside one test whose name line 2 already imported; QA kept it through three review rounds and the suite locked with it. `_javascript._the_import_instead`: the exact correction - the line to delete when every name it binds is already imported from that module, else the `import` to write at the top - and whether the file throws as it loads or only the test around the call fails. Test `test_a_require_in_a_module_names_its_exact_correction.py`. | done |
| LF.361 | backlog B15, measured on one run: the restart test wrote its record through the `request` fixture (the suite's own server and data folder), started a service on a fresh folder, stopped it, restarted on that folder and read the record: 404 on every product, the only acceptance test left failing. `suite.tests_that_restart_on_data_they_never_wrote`, among `tests_that_cannot_pass`: a service started without `dataDir` whose `baseURL` the test never uses, restarted on its `dataDir`. And `_service.RESTART_GUIDE` showed only `require('./service.cjs')`, which QA wrote inside a test of an ES module: it now loads the helper at the top the way the file loads `@playwright/test`. Test `test_a_restart_test_on_data_it_never_wrote_cannot_pass.py`. | done |
| LF.362 | measured on one run: the unit tests called the product's factory as it was before a fix made it asynchronous; two fixes of "the unit tests fail" in turn changed the product to suit them, broke three and then seven passing acceptance tests, and were reverted, and the sprint was planned again. `workflow._the_unit_tests_are_out_of_date`: a failing-unit-tests defect whose fix is reverted for breaking acceptance tests is told the unit tests are out of date - change them to use the product as it now is, keep their names, leave the product. Test `test_a_unit_test_fix_that_breaks_the_suite_is_told_the_unit_tests_are_out_of_date.py`. | done |
| LF.363 | measured on one run: a defect's re-measure at dispatch ran the one suite file naming its criteria, and its report replaced the suite's; the round reused the saved measurement (MEASURE_ONCE) with that report - 10 tests where the suite ran 13, all passing - read the other three as "written but never run", and reopened a green suite for repair. `per_file.each_file` puts the suite's report back after its runs (none, when there was none), and `measured_once.saved_run_if_unchanged` measures again when the report's counts are not the saved run's. Test `test_one_file_s_run_leaves_the_suite_s_report_as_it_was.py`. | done |
| LF.364 | measured on two runs: unit tests named "AC-1 CreateNoteTest" put criterion ids in the failing-unit-tests defect, so the dispatch re-measure (`_the_defect_s_tests_pass`) ran the acceptance files of those criteria instead of the unit tests; they passed, the defect was "closed without a fixer" every round with four unit tests still failing, and the previous run shipped eleven failing. A failing unit run is now answered by the unit tests alone, whatever ids their names carry. Test in `test_a_fixer_s_tests_are_run_after_the_harness_puts_its_files_right.py`. | done |
| LF.365 | backlog B17, measured on two runs: the unit tests that shipped failing asserted a key order, a count other tests' data changed, and an empty 404 body the interface does not give, while the locked suite passed in full; the fixers changed the product for them and were reverted. `workflow.BESIDE_A_GREEN_SUITE`: the fast round's failing-unit-tests defect, when no due criterion fails and the saved run failed nothing, says the unit test may assert what the specification does not - correct it, keeping its name, and change the product only for a failure the specification backs. Test `test_a_unit_failure_beside_a_green_suite_may_be_the_test_s.py`. | done |
| LF.366 | measured on two runs: told the exact lines to change, QA left `request.baseURL` (`undefined` on every product) through three review rounds and the suite was locked with it. `suite.correct_reads_of_the_fixture_s_baseurl`, at the start of `acceptance_review` beside LF.353's renames: each test that reads `request.baseURL` reads `baseURL`, added to its destructured fixtures where missing; a test whose fixtures it cannot read is left to the review's finding. Test `test_the_harness_corrects_reads_of_the_fixture_s_baseurl.py`. | done |
| LF.367 | backlog B20, measured on two runs: unit tests named "AC-1 CreateNoteTest" made `rewritten_fixes.files_to_fix` read the failing-unit-tests defect as one the suite judges, so every test file was left out; both fixes rewrote product files (despite LF.365's note), broke 20 and 6 other unit tests and were reverted, and four wrong unit tests shipped failing. A failing unit run is never the suite's, whatever ids its tests' names carry: its test files may be rewritten. Test in `test_a_defect_is_fixed_by_rewriting_its_files.py`. | done |
| LF.368 | backlog B18 (second half), measured on two runs: the QA lead's dispute set tests aside for what the product does - "the implementation includes createdAt and updatedAt, which are not part of the criterion" (a criterion listing the record's three fields; QA then loosened the tests), and "responds with 200 instead of the 415 the specification defines". The prompt said the code is not the standard; nothing checked the answer. `suite_dispute.judged_by_the_code`: a reason whose clauses attribute the failure to what the implementation/product/response does, with no clause saying the test asks for what the criterion does not, names nothing - the test stays locked and the product keeps the defect. Test `test_a_dispute_ruling_made_by_the_code_keeps_the_test_locked.py`. | done |
| LF.369 | measured on one run: the dispute's by-the-code check (LF.368) missed "the product never loads the existing notes.json on startup, so no data is persisted as the test expects" - its verb list had `does not` but not `never loads`/`fails to` - and a locked restart test the brief requires was reopened for loosening. `_THE_PRODUCT_DOES` now takes `never <verb>`, `fails to`, `cannot`, `did not` and the verbs of doing (loads, reads, writes, persists, stores, saves, ignores, throws, crashes). The run was rewound to the dispute. Test in `test_a_missing_export_of_a_module_that_exists_is_refused_once_the_milestone_is_written.py`. | done |
| LF.370 | measured on one run: three fixes in a row rewrote a route importing `{ StorageService }` from a module that exports only a default instance; the write guard `_refuse_if_it_adds_errors` excused every "has no exported member" finding as "another file may not be written yet", each fix was committed, broke the start, and was reverted (three fix slots and ~3 min each). `_another_file_not_written_yet`: the excuse holds only while the module the finding names does not exist, or a planned work-order file is still unwritten; otherwise the write is refused with the checker's own hint (`Did you mean import X from ...`). Same test file. | done |
| LF.371 | measured on one run, twice: rewound to its dispute after LF.369, the QA lead re-worded the same reason with the product's own symbol as subject - "StorageService.load() is never called, so data is not loaded on startup" - and LF.368/369's pattern, which needs "the implementation"/"the product" named, let it through. `_A_PRODUCT_PREDICATE`: the predicate decides whatever the subject - `is never/not <done>`, `never called/runs/loads/persists...`, `is missing/undefined` - still only when no clause says the test asks for what the criterion does not. Rewound again to the dispute. Test in `test_a_dispute_ruling_made_by_the_code_keeps_the_test_locked.py`. | done |
| LF.372 | backlog B24, measured on one run: a milestone review's revision batch (five findings, 13 files) took a green product from 16 locked tests to 4 at round 4 of an attempt with no re-plan; `best_attempt.after_a_redraft` undoes a wrecking redraft only at a re-plan's first round (`test_round == 0 and replans > 0`), so the best (16, on record) stayed unused, twelve per-defect fixes could not reach the cause (6 reverted), the attempt exhausted, and the next re-plan restored it - ~20 min and every mutation round. `_the_head_is_a_batch`: the first measurement after any `Work orders:` batch is judged the same way. Test in `test_a_sprint_planned_again_starts_from_the_best_product_it_has_had.py`. | done |
| LF.373 | measured on one run: a locked test read `./start.sh` and expected it to match `/DATA_DIR/`; the harness's start file reads nothing but its service and `contract.enforce` puts it back before every run, so the test failed on every product and no fixer could reach it. `suite.tests_that_assert_a_kept_file_s_text`, among `tests_that_cannot_pass`: a test that reads a kept file (`contract.kept_paths`) and asserts in the same block is told to prove the criterion through the service, not the file. Test `test_a_test_that_asserts_a_kept_file_s_text_cannot_pass.py`. | done |
| LF.374 | measured on LF.373's first run: the check reopened a green suite (19/0) for a test of the start file's text that QA had already made pass; a repair (2 of 4) and three QA rounds went on it and the suite was locked with the finding open. A passing test of a kept file proves nothing but costs nothing: `tests_that_assert_a_kept_file_s_text(repo_root, result)` counts only a test the suite's result shows failing. Test in `test_a_test_that_asserts_a_kept_file_s_text_cannot_pass.py`. | done |
| LF.375 | measured on one run: the worker container was OOM-killed (8 GiB) mid test round and the run sat `running` 14 min (the periodic orphan check saw a live task). Cause: unit tests posting megabyte bodies to the product's default data directory on every round grew `data/notes.json` to 205 MB (24 records), the service parsed all of it per request in the same container. The acceptance configuration gives the service a fresh `DATA_DIR`; the unit command had none. `StackPack.data_dir_env` (the two service packs: `DATA_DIR`) and `sandbox._a_fresh_data_directory`: every test-category command gets a fresh directory under the project's git-ignored `test-results/` in that variable unless the caller set it. Test `test_a_unit_run_gets_a_fresh_data_directory.py`. | done |
| LF.268 | a suite that "proves nothing" because QA wrote its tests in a file the runner does not collect failed a run after five rounds of advice that never named the file: a TypeScript service's QA wrote `api.spec.ts` where the runner collects `*.spec.js`, and every round said only "make it a test of its own". The message now says when the file's name does not match the runner's acceptance pattern (from the stack's contract) and what the pattern is (`suite._a_file_the_runner_does_not_collect`); a file that does match keeps the general advice. Tests added to `test_a_test_the_runner_never_collects_goes_back_to_qa.py`. Open: whether the TypeScript packs should collect `.spec.ts` too | BUILT 2026-10-24 | [monitoring handover §0](monitoring-handover.md) |
| NG.1 | a fix that made many tests pass and broke one unit test was reverted whole. Measured on a gpt-oss-20b tasks-api run: one fix made 12 tests pass and broke 1 unit test (a sign-up test the same model had written), and was reverted; four more fixes that each repaired a criterion and broke that test were reverted too, six reverts of the same test, and the sprint went round again with nothing gained. The fix gate protected what passed before and did not weigh what the fix gained. `net_gain` (switch `KEEP_NET_GAINS`, off in code, on in compose): a fix stays when it gained at least 3 tests and 3 times as many as it broke, and left the product able to build and start (if it also broke a locked acceptance test it must have gained at least 4, changed 2026-10-25: a fix that made 5 pass and broke 1 criterion was reverted whole in a later run, a net gain of four thrown away); the snapshot kept is the one after the fix, so the next test round raises the broken unit test as an ordinary defect. Off = the old gate. Tests `test_a_fix_that_gains_much_and_breaks_one_unit_test_is_kept.py`. To measure: reverts that would have gained N, and whether the kept fix's broken test is then repaired | BUILT 2026-10-25, owner away: switch on, tell the owner | [monitoring handover §0](monitoring-handover.md) |
| LF.269 | a locked suite carrying a bug in its own code kept a finished product from releasing. gpt-oss-20b on tasks-api: **hidden 10 of 10**, yet the locked suite read 14 passed / 7 failed for over two hours and the sprint went through four re-plans, 62 defects left open and 18 reverted fixes. Five of the seven failing criteria were tests whose own line was `json={{"title": ""}}` (double braces: a set holding a dict), which raises `TypeError: unhashable type: 'dict'` before any request, so no product could pass them; one tested a path relative to the wrong folder and one reused names the earlier tests had taken. The harness has a check for errors in a test's own code (`tests_that_broke_themselves`, which reopens the locked suite) but the Python patterns did not know this error; it cannot show at lock time because the first request fails before the bad line, so it shows once the product runs. The Python packs' `TEST_BUGS` now include `TypeError: unhashable type: dict/list/set`. Tests `test_a_test_that_builds_a_set_holding_a_dict_is_the_test_s_bug.py`. Open: the other two classes (a path relative to the wrong folder; a test reusing a name an earlier test took) | BUILT 2026-10-25 | [monitoring handover §0](monitoring-handover.md) |
| LF.270 | a test whose name carries a per-run value was a new test on every run, so every fix "broke" it. gpt-oss-20b on tasks-api: an acceptance test parametrized on a random user name (`test_ac1_signup[user_02dc5292-password123]`) was named differently by each measurement; the fix gate saw the test that passed before the fix as lost and reverted seven fixes in one run, one of which had made three tests pass. `ci.stable` replaces a uuid or a run of eight or more hex digits in a test's key with `~`, in `outcomes_of` and in the lookup, so a snapshot kept before this change still matches. A test that really stops passing is still a regression. Tests `test_a_test_named_with_a_random_value_is_the_same_test_on_every_run.py` | BUILT 2026-10-25 | [monitoring handover §0](monitoring-handover.md) |
| RD.1 | a re-planned sprint's redraft rewrites working files and the product gets worse. Seen three times with gpt-oss-20b in one night: Hono (14 of 18 criteria to 0 after the first re-plan), tasks-api (4 of 25 tests to 0 of 25 at the start of attempt 2), notes-api (17 to 12, recovered). Drafting writes each file of the new plan's work orders in one model call from the specification, over files that already work. KB.1 puts the best product back, but only at the next re-plan, and the next redraft can do the same again. Candidate: the redraft leaves a file alone when it exists and the last measurement was no worse than the best, except files named by an open defect; or drafts into a copy and swaps a file in only when the suite does not pass fewer tests. To weigh against what the re-plan is for (new scope the working files do not cover) | FILED 2026-10-25, from run-0f1f5e4e and run-a6ed6fee |
| LF.271 | a command-line acceptance test and the program it runs did not share a working directory. gpt-oss-20b on wordstats-cli: nine of ten locked tests wrote their input file by a relative name (`pathlib.Path('test.txt').write_text(...)`), which landed in the project folder, then ran the program through `run_cli`, whose working directory is pytest's `tmp_path`, where the file was not; the program reported it could not open the file and exited 2. None could pass whatever was built: the run stopped at 4 of 14 criteria, hidden 5 of 8, after three re-plans. The Python CLI pack's `run_cli` fixture (harness-owned) now changes the test's own directory to `tmp_path` too, and its guide says so, so a file the test writes by a relative name is the one the program finds. Tests `test_a_cli_test_and_the_program_share_one_working_directory.py` (runs pytest on a tiny project with the pack's fixture, and with the old one). Open: the Node, Go and Rust CLI packs, whose fixtures were not read for the same fault | BUILT 2026-10-25 | [monitoring handover §0](monitoring-handover.md) |
| LF.272 | a model request the server never answers kept the configured thirty-minute limit when the model has no reply ceiling. gpt-oss-20b on LM Studio (no ceiling: its replies are short): one request was never answered while the same server answered a new one in 0.3 s, and the run sat on it for 13 minutes before this was found. The deadline is shortened by `paced_timeout` only when the call's reply length is known (its cap, else the model's ceiling); with neither it kept `request_timeout`, 1800 s. `expected_reply_tokens` now falls back to the longest real reply (`LARGEST_LEGITIMATE_OUTPUT_TOKENS`, 13,000), so once the server's pace is measured a wedge is caught in minutes (twice the time that reply needs at the slowest recent pace, never under 180 s); before it is measured the configured limit stands. Tests `test_a_request_the_server_never_answers_is_not_waited_on_for_thirty_minutes.py` | BUILT 2026-10-25 | [monitoring handover §0](monitoring-handover.md) |
| LF.273 | a finished product scored hidden 0 of 9 because its `start.sh` had been rewritten. gpt-oss-20b on notes-api, repeated: the same brief and pack that scored 9 of 9 earlier completed (locked suite 17 passed, 2 failed, the unit-test gap and a deferred AC-15 recorded) and the hidden tests failed all nine at setup: `sh start.sh` died with `No module named 'sqlalchemy'`. The pack's `start.sh` (`cd "$(dirname "$0")" && exec .venv/bin/python -m uvicorn ...`) was written without the execute bit; two fixers for the criterion "the project has a start.sh that starts the service" replaced it with `exec python3 -m uvicorn ...` and made it executable. Inside the locked suite it worked, because the suite runs under the project's virtual environment; started from outside, `python3` is the system's and lacks the dependencies. `start.sh` is now a kept file of the Python HTTP and Flask packs (a stage's change is put back and the fences refuse it), and the scaffold gives any script a pack writes (a file starting `#!`) the execute bit, so the criterion needs no edit. Tests `test_a_pack_s_start_script_is_kept_and_runs_by_its_name.py`. Open: a release check that starts the product by `start.sh` from a bare environment, so any drift of this kind is a gap whatever caused it | BUILT 2026-10-25 | [monitoring handover §0](monitoring-handover.md) |
| LF.274 | a fixer was never shown why the service answered 500. gpt-oss-20b on tasks-api (hidden 1 of 10, locked 0 of 21): sign-up answered 500 and every test said `assert 500 == 201`; the service had logged `TypeError: 'password' is an invalid keyword argument for Account` (a route and a model that disagreed on a field's name), which the fixers never saw, and five rounds of rewrites did not find. The Python service packs' `acceptance/conftest.py` now writes everything the service prints to `test-results/service.log` (a file, not the unread pipe that could also fill and stop the service), and `suite.the_errors_a_service_logged` reads the last two distinct tracebacks (exception line and the project's frame that raised it) and adds them to each failing test whose message shows a 5xx (`_with_the_errors_the_service_logged`). Scaffolded for real with `scripts/loop/verify_packs.py` (both Python service packs pass). Tests `test_a_failing_test_that_met_a_server_error_carries_what_the_service_logged.py`. Open: the same log for the PHP, Node and full-stack packs, whose conftests have their own `Service` classes | BUILT 2026-10-25 | [monitoring handover §0](monitoring-handover.md) |
| NM.1 | a missing name is answered with the names that exist, in every language the harness reads. Name mismatches between files were 31 of 288 defects (11%) over last night's 16 runs by their message alone, and sat upstream of far more: a missing export stops the product starting, then every criterion reads as failing (the Hono runs sat at 0 of 18 for hours on `createApp` imported from a module that exported `app`; a tasks-api router imported `create_access_token` from a module that defined `create_token`). The compiler names the missing name and not the existing ones, so each writer guesses again. Python had the answer at the gate (`what_the_module_defines`); TypeScript and JavaScript had none, and neither the drafting repair nor a stage's exit check carried it for any language. Now: a TypeScript/JavaScript reader (relative `from './m'` / `require`, `.js` for `.ts`, `export` forms, `export { a as b }`, default), `language_service.the_names_the_module_has` adds `` `src/app.ts` defines: ... `` to a missing-name finding, the gate's per-module bundling accepts TypeScript's wording, and `_diagnostics_in_files_touched` (drafting repair, stage exit check) appends the note. Always on: it only adds a fact to a message. Not covered: a package outside the project (`hono` has no `createMiddleware`), which needs the package's own exports. Tests `test_a_missing_name_is_answered_with_the_names_the_module_has.py` | BUILT 2026-10-25 | [monitoring handover §0](monitoring-handover.md) |
| NM.2 | one naming standard per language, in the architect's request and every draft's (switch `NAMING_STANDARD`, on in compose, off in code): the language's conventions from a table (`app.stacks.naming.CONVENTIONS`) and the rule that one concept has one name everywhere, imported as defined and never renamed. A specification section that fixes names (`function_contracts`, `error_catalogue`, `implementation_order`) that comes back empty is asked for once more: the stored specification of a failing tasks-api run read "Function Contracts: Not specified" and "Data Contracts: Not specified", leaving each writer to invent its own names. Tests `test_one_naming_standard_is_stated_for_the_architect_and_every_draft.py`. To measure: name-class defects per run, with and without | BUILT 2026-10-25, at the owner's request | [monitoring handover §0](monitoring-handover.md) |
| LF.267 | a fixer pinned a package version the registry lacks (`async-mutex@^2.3.0`), the installer said no such version existed, and every rewrite of the manifest from that message pinned another missing version: the product never installed (first Hono run with a pack). The installer's message names the missing version, not the existing ones. A failed install's note now carries the registry's current release of each package an installer says has no such version (npm `No matching version found`, pip `No matching distribution found` / `Could not find a version that satisfies`), looked up by the harness (`contract._the_versions_that_exist`, through `package_registry.look_up`); without a registry the note is as before. The registry's answer comes right after the command, before the installer's own lines, because the defect built from the note keeps its first 900 characters. Tests added to `test_a_changed_manifest_is_installed_before_it_is_measured.py` | BUILT 2026-10-24 | [monitoring handover §0](monitoring-handover.md) |
| RL.2 | Uptake measurement: KPI `lessons_shown_per_call` (AT's open item), and per lesson whether its trigger shape recurs in later runs on the same stack (the only proof a lesson works). A lesson whose trigger recurs for three runs after approval is flagged for review | 0 | recurrence after approval | P1 | BUILT 2026-10-21 behind `LESSON_DISTILLER`: KPI `lessons_shown_calls`; an approved lesson proposed again counts `recurred_runs` (`lessons.recurred`) |
| RL.3 | Proposals surfaced: `loop.sh report` lists new proposals with their evidence, and `GET /api/lessons` already serves them to the UI (S5); an owner approval is one click there | 0 | — | P2 | BUILT 2026-10-21: `loop.sh lessons` (list, or distil <run>); `GET /api/lessons` already serves proposals |
| RL.4 | Scoring guard: distillation and the loop are judged on the hidden test families (`web-todo`, `notes-api-hono`) and never on a brief's own suite, so the loop cannot learn to pass the acceptance tests (J.1 guards the vacuous-green form) | 0 | hidden-test score across runs | P1 (process) | ADOPTED |
| RL.5 | Not done: agents editing prompts, stack packs or harness code; model-written memory files; a reflector call on the local model | — | — | — | REJECTED |

**Kill rule:** a lesson that raises the identical-call rate or tokens per accepted criterion on its stack without stopping its trigger is rejected (ADR-0010).

<a id="plan-ph"></a>
### PH — Progress in, work summary out (2026-10-21)

**What exists** (checked 2026-10-21).
- Harness-written records of what every stage did: `docs/sprint_N_summary.md` (the Sprint Record: work-order outcomes, defect log, findings, carried-forward, lessons), `docs/stage_summaries/<stage>.md` (every `SpecialistOutput` field), `decision_log.md`.
- **But none of them is handed to a later agent.** `project_memory._RECORDS` deliberately leaves them out (they appear only as names under "Not included here"). The Sprint Record reaches the next *lead* (carried-forward, what went wrong) and feeds `fixes_to_keep`; a builder's request has no "what the earlier work orders of this sprint did" section; a fixer sees earlier attempts on its defect only as a revert note appended to `actual_behavior`.
- The frontier pattern ([R9](research-findings.md#r9), Anthropic's long-running-agent harness, Nov 2025): a JSON feature list the agent may only mark `passes` (DevFlow's locked acceptance suite is this), one feature per session (AZ, NOT STARTED), a progress file read at start and written at the end, and a start-of-session check that the product still runs before new work.

**Verdict.** A good feature, and mostly a routing change: the summaries exist, the readers do not. The lift is to hand each agent a *bounded, harness-written* progress block, not a document to read.

| ID | Change | Model calls added | Measure | Priority | Status |
|---|---|---|---|---|---|
| PH.1 | "Where things stand" block at the start of every builder and fixer request, harness-written and ≤2k chars under BJ: the sprint's finished work orders (files changed, one-line decisions), open blockers addressed to this role (from CM.2's ledger), the last CI-gate and test-round verdicts, and the live product's state (`_where_the_product_stands`, today fixers only). Replaces reading `sprint_N_summary.md` | 0 | redundant reads (AQ); fix attempts per defect | P1 | BUILT 2026-10-21, behind `WHERE_THINGS_STAND` (off): `app.agents.where_things_stand` opens every builder and fixer request with the sprint's finished work orders (files, first decision), the blockers they left, the last CI gate's verdict and the suite's last measurement, at most 2,000 characters; shared switch helper `app.switches.is_on` |
| PH.2 | Structured attempt record per defect: each fix attempt leaves `{files changed, what it did (from `decisions`), outcome: fixed / reverted (what broke) / blocked (why)}` in the ledger; the next fixer of the same defect gets the list, not a revert sentence inside `actual_behavior`. Builds on `_the_last_attempt_section` | 0 | repeat attempts that redo a reverted change (LF.80/82 class) | P1 | BUILT 2026-10-21 behind `DECISION_LEDGER` |
| PH.3 | Work summary out, enforced: a builder's `SpecialistOutput.decisions` must name every interface it added, removed or renamed (the readiness check already refuses a thin answer); the ledger (CM.2) takes these as `decision` entries, which is what the next agent's PH.1 block shows. Stage summaries stay as the audit copy | 0 | unread-decision failures (the `window.todoApp` class) | P1 | BUILT 2026-10-21, behind `INTERFACE_CHANGES_NAMED` (off): the harness reads each changed file's definitions against the last commit (`reachability.FAMILIES`, every language with a pattern) and adds any added or removed interface the builder's decisions do not name - read, not asked for |
| PH.4 | Start-of-work check for builders: the product-start and unit-test state at dispatch (the CI gate's last result, re-run only if files changed since) is in the PH.1 block, so a builder does not start on a product that no longer starts | 0–1 sandbox run | fix rounds caused by a sibling's break | P2 | BUILT 2026-10-21 behind `STATE_AT_DISPATCH` (off, inside PH.1's block): the files changed since `ci_batch_commit` are named and the CI verdict marked as possibly stale; no sandbox run |
| PH.5 | One slice per visit (AZ) stays the way to keep progress legible; PH does not change it | — | — | — | see AZ |

**Not done:** a free-text progress file the model writes (the summaries are harness-written from structured output; R7's drift finding applies), and a new document agents must read (budget).

<a id="plan-cg"></a>
### CG — A map of the code behind each feature (2026-10-21)

**What exists** (checked 2026-10-21).
- Pieces of a graph, none joined: `analysis/project_memory.py` (per file: purpose, ≤8 signatures by regex, who wrote it; feeds `workspace_digest`), `reachability.py` (import graph from the pack entrypoints), `local_imports.who_would_break` (importers of a written file), `language_service.what_the_module_defines` (Python/TypeScript), tree-sitter for parse faults only (`grammar_parse.py`), ~40 wiring detectors in `integration_checks.py`.
- No criterion → files map is stored: a fix derives it on the fly from the suite's AC tags through the specification.
- Pillar 10 (Code and Test Index) and E1 #4 (repository map) are NOT BUILT; their gate is "measure redundant reads first" (AQ: PARTLY).
- Measured cost of agents not knowing where code is: 24% identical calls on the medium run, 431 of them reads (AQ); 43% redundant reads, 40 of 57 after a compaction (LF.63); a fix stage re-reading the same three files 27 times in 36 calls (LF.81); three rounds rewriting importers instead of the module that lacked the name (LF.100, LF.105); `ui.js` read 60 times, 82% of 911 calls reads and listings (`project_snapshot.py`).

**Research** ([R10](research-findings.md#r10)). Graph-guided localisation lifts file-level accuracy to about 94% and cuts localisation cost about 86% (LocAgent), with a fine-tuned 32B open model matching a frontier model, and about +12% relative on downstream resolution. A Feb 2026 study found graph navigation wins on *hidden-dependency* tasks (99% vs 76% coverage) but not on simple ones, and that the agent skipped the graph tool in 58% of trials even when told to use it: **inject the neighbourhood, do not rely on a tool**. Local graph indexes (tree-sitter, SQLite, incremental by file hash) report 35–360× fewer tokens than reading the corpus, with the caveat that graph context can cost more than a plain read for a one-file edit, and that a stale index is worse than a slow search.

**Verdict.** A good feature for the *fix loop and reviews* first, built from the pieces that exist, injected rather than offered as a tool, and kept incremental. The "feature" axis is the locked criteria: each AC-n maps to its tests, the files those tests touch, and the work orders that own them.

| ID | Change | Model calls added | Measure | Priority | Status |
|---|---|---|---|---|---|
| CG.1 | One harness-owned index per workspace (`.project-graph.json`, beside `.project-memory.json`): nodes = files and the definitions `project_memory` already extracts; edges = imports (`reachability`, `local_imports`), defines/exports (`what_the_module_defines` where a language service exists, regex elsewhere), test → criterion (junit AC tags) and test → file (what the test imports or requests), work order → files. Updated on every write by file hash (the write guard already sees every write); never model-written. Language-agnostic: regex signatures for every language, parsers where the harness has them | 0 | index build time; staleness (a renamed definition disappears on the next write) | P1 | BUILT 2026-10-21: `app.analysis.project_graph.build` - files, definitions and imports per language family (`reachability`), imported-by, and the criteria each acceptance test file's names carry; written to `.project-graph.json`, computed from the files, never model-written |
| CG.2 | Fix request gets the 1-hop neighbourhood of the defect's files from CG.1: who imports them, what they import, which definitions each exports, which tests and criteria reach them — ≤1.5k chars under BJ. Where a traceback names an importer, the defining module is listed first (LF.100/101 in general form). Reviews get the same for the files they judge | 0 | fix stages that rewrite the wrong file; redundant reads in fix stages | P1 | BUILT 2026-10-21, behind `PROJECT_GRAPH_FIXES` (off): the fix request gets the defect's (and its bundled defects') files' one-hop neighbourhood, at most 1,500 characters |
| CG.3 | Builders get their work order's slice: the files it owns, what imports them and what they import, and the criteria they serve, in place of the flat digest for those files | 0 | redundant reads in builder stages | P2 | BUILT 2026-10-21, behind `PROJECT_GRAPH_BUILDERS` (off): each work order's request (linear and parallel) gets its files' neighbourhood |
| CG.4 | Read-only `where_is(name)` / `who_uses(path)` tool answered from CG.1 (Pillar 10 step 3), offered after CG.2 is measured; expected low uptake, so it is not the primary channel | 0 (a tool call replaces reads) | tool uptake; reads replaced | P3 | BUILT 2026-10-22 behind `CODE_GRAPH_TOOL` (off): one read-only `code_graph` tool for specialists - `where_is_name` (files defining it, exactly or by a part) or `who_uses_path` (importers, definitions, acceptance tests and criteria) |
| CG.5 | Criterion view in the UI: each AC-n with its tests, files and work orders from CG.1, and a failing test's path to its files on the run page (UI track; pairs with BG.3/BG.4) | 0 | — | P3 | PROPOSED |
| CG.6 | Gate (Pillar 10's): CG.2 ships only if AQ's redundant-read share in fix stages falls on the same brief; a neighbourhood that costs more than the reads it replaces is cut to the defining-module line | — | AQ ledger row | process | ADOPTED |

**Not done:** an external graph database or MCP server (one JSON per workspace is enough at this size), embeddings (exact names are what fixes need), and a graph the model maintains.

**Placement in Part 21 (added 2026-10-21):**
- **PH.2**, **PH.3** join stage 3 (the fix loop) after AY.
- **PH.1**, **CG.1–CG.2** join stage 4 after BJ and CM.2 (they share the ledger and the input budget).
- **RL.1–RL.3** join stage 7 (infrastructure); **RL.4** applies from now.
- **CG.3–CG.4**, **PH.4** join stage 8.
- **CG.5** joins the UI track after BG.3/BG.4.

<a id="plan-appendix-7"></a>
## Appendix 7 (2026-10-21): the discipline layer — measurement, provenance, intake, operations

Owner, 2026-10-21 13:49 JST: "other than the improvement plans made, what else can be done?"
Evidence: `docs/review-findings.md` §16 (the structural review of the run history and the
plan's coverage). Nothing here repeats an item above; neighbours are named.

**The finding.** The loop is spending almost all of its effort fixing the harness, and nothing
measures whether that works: 137 LF rows in three days (37, 70, 30 — accelerating), every
quality lever built but off, no clean gate run since 10-11, no run ever on one harness version
(8–17 deploys and up to 11 rewinds each), `brief_medium` without hidden tests, and no run
recording the harness commit or the served model. Fix stages take 80–90% of model minutes and
22–47% of output is lost at the cap. The plan has enough features; what is missing is the
discipline around them.

**Grouping (owner's rule of 2026-10-19):** *group 1* = needs no before/after run, built now;
*group 2* = changes run behaviour, behind a switch, validated against the measured runs.
Every item below carries its group.

<a id="plan-mf"></a>
### MF — Measurement first, for real (ADR-0010 made operational)

| ID | Change | Group | Priority | Status |
|---|---|---|---|---|
| MF.1 | Provenance on every run: harness commit SHA (and every SHA deployed into the run, so a mixed run is marked `mixed_versions`), served model id from the server (`/v1/models` or `/props`, not the client class name the transcript records today), quantisation and slots (already read by `server_profile`), the sampling parameters as sent, delivery and execution mode, and every flag on — into `runs`, the KPI JSON and `ledger.csv`. A leaderboard keyed by SHA falls out of it | 1 — now | P0 | BUILT 2026-10-21: `observability/provenance.py` writes a `provenance` record per run segment (harness commit from the image's `HARNESS_COMMIT`, served model, quantisation, slots, reply ceiling, thinking and execution mode, delivery mode, switches on); the KPIs carry `harness_commits`, `mixed_versions`, `served_model`, `switches_on`; `loop.sh deploy` builds the commit into the image. Test: `tests/test_every_run_records_what_it_ran_on.py` |
| MF.2 | Hidden tests for the gate brief: either `tasks-api` (10/10 reference, "the class the medium brief failed on") becomes the medium gate, or `benchmarks/<medium>/hidden/` is written from `brief_medium`'s Interface section with a reference implementation that scores 100%, as every other family has. Until then a medium result is a hand audit | 1 — now | P0 | DECIDED 2026-10-21 (owner): `benchmarks/tasks-api` is the gate brief - its hidden suite and a reference scoring 10/10 exist (`tests/test_the_tasks_api_bench_reference_scores_full.py`); gate runs from the next one: `loop.sh start benchmarks/tasks-api/brief.md`, `DELIVERY=fast FRONTIER=false`, scored with `loop.sh score <run> tasks-api` |
| MF.3 | Two KPIs that do not exist: `wall_clock_per_accepted_criterion` and `tokens_per_accepted_criterion` (`run_kpis.py` has no criteria fields), plus `gate_wait_minutes` (human-gate waiting is noted ad hoc only) | 1 — now | P0 | BUILT 2026-10-21: `gate_wait_minutes` from `gate` transcript records the runner now writes (opened, answered); `accepted_criteria`, `wall_clock_per_accepted_criterion`, `tokens_per_accepted_criterion` from the run's last acceptance result (`kpi.py`) |
| MF.4 | The Measure/Fix cycle, as process: **Measure** = one SHA, flags fixed, no deploys, two runs per family, scored by hidden tests only; a bug found is filed, not deployed. **Fix** = the batch, each fix with its failing test, suite green, then Measure again. A mid-run deploy into a long run is allowed only under the 40-minute rule and marks the run `mixed_versions`, excluded from comparisons. **Stop rule:** a fix batch that moves no hidden score, false-acceptance rate or MF.3 KPI on the next Measure cycle is parked or reverted, not kept | 1 — now (process) | P0 | ADOPTED 2026-10-21 (owner), from the run after gate run 3: run 3 (run-f4f0030b) ends under the old deploy-and-rewind rule; Measure cycles after it run on one frozen SHA with no mid-run deploys |
| MF.5 | `kpi_ledger.compare` takes a minimum n (two runs per arm, Part 20) and reports the spread, not only the mean; the 1.5× regression flag stays | 1 — now | P1 | BUILT 2026-10-21: `kpi_ledger.py arms <ledger> <commit-a> <commit-b> [benchmark]` compares two harness versions on runs of exactly one commit (mixed runs left out), each arm at least two runs, each KPI's mean and min-max |
| MF.6 | Session cost of the loop itself: `docs/STATE.md`, at most 150 lines — what is live, what is off, the last three run results, the next action — as the only mandatory read at session start; run narratives older than a week move to `docs/archive/`; `tokens_per_fix` recorded per session in the handover. Today a session reads about 12,000 lines (~150k tokens) before acting, and the plan grows ~30 rows a day | 1 — now | P1 | BUILT 2026-10-21: `docs/STATE.md` (81 lines; a test holds it at 150 or fewer and AGENTS.md sends a session there first); handover sections before 2026-10-14 moved to `docs/archive/` (629 lines); the loop's cost per session is a table in STATE.md. Test: `tests/test_the_state_file_is_the_one_mandatory_read.py` |

<a id="plan-rc"></a>
### RC — Reader-regression corpus from real transcripts

Twelve-plus LF rows are a reader misreading real model output (LF.43, 92, 104, 108, 109, 127,
129, 130 — 32 of 58 contract lines unparsed), each fixed against the one sample that failed.
75 test files already carry hand-copied transcript snippets. Neighbour: Y's edit-replay corpus
covers edits only.

| ID | Change | Group | Priority | Status |
|---|---|---|---|---|
| RC.1 | Harvest: after every run, every structured answer, tool-call envelope, file plan, contract line, verification claim and settled answer is extracted from the transcript into `data/corpus/<kind>/<hash>.json` with the reader's current result (accepted / repaired / refused) | 1 — now | P1 | BUILT 2026-10-21: `observability/reader_corpus.py` keeps each input four readers took (contract lines, file plans, drafted replies, tool calls written as text) with the reader's result, after every run (`loop.sh kpi` runs `loop.sh corpus harvest`) |
| RC.2 | Replay test: the suite replays the whole corpus through today's readers and fails on any sample whose outcome changed; a reader fix is then tested against hundreds of real samples offline, without the GPU or a live run | 1 — now | P1 | BUILT 2026-10-21: `tests/test_the_reader_corpus_replays_unchanged.py` replays `data/corpus` through today's readers and fails naming each changed sample; `loop.sh corpus accept` keeps a change made on purpose |
| RC.3 | Corpus hygiene: samples are redacted of workspace paths and secrets at harvest; the corpus is `DATA_DIR` state, never committed; a `loop.sh corpus` command lists sizes and the readers each kind exercises | 1 — now | P2 | BUILT 2026-10-21: samples redacted at harvest (workspace paths, key- and token-shaped strings); `DATA_DIR` state, never committed; `loop.sh corpus` lists sizes and what changed |

<a id="plan-in"></a>
### IN — Intake: confirm assumptions before the run spends hours

`product_manager` already produces `open_questions` and `evidence_vs_assumptions`; nobody is
asked to answer them (`workflow.py:4000` excludes `open_questions` from checks; the intake gate
shows a document). The medium runs' worst failures were spec-level (LF.40, LF.42, LF.90), and
brief_low scored 5/10 against web-todo because the brief left UI controls implicit. The
clarification research behind CM.4 (+14 points on underspecified tasks) applies here at zero
per-run model cost. Neighbours: UI-S3 plan-first intake, CM.4 (questions *during* the run).

| ID | Change | Group | Priority | Status |
|---|---|---|---|---|
| IN.1 | Assumptions gate: before the specification, one screen listing each open question with the PM's default answer; the owner confirms or edits each; in auto mode the defaults are recorded as decisions (`decision_log.md`) and shown on the run page. Behind `ASSUMPTIONS_GATE` | 2 — after measured runs (it changes what the architect receives) | P1 | BUILT 2026-10-21 behind `ASSUMPTIONS_GATE` (off): `app/agents/assumptions.py` - the product manager writes `question -> assumed: answer`; each is a `product_intake` decision (decision log, run page); the architect's request carries them as answers to build to. The owner sees them at the intake review when it is on; a dedicated screen is UI work, not built |
| IN.2 | Ambiguity score at preview: `POST /api/runs/preview` reports the count of criteria without an interface line and of brief features the PM marked as assumptions, so a thin brief is seen before the run, not at sprint 3 | 1 — now (read-only) | P2 | BUILT 2026-10-21: `app/acceptance/ambiguity.py`; `POST /api/runs/preview` answers `without_an_interface_line` (criteria no line of the brief's interface section speaks to) and `vague_phrases`, and the criteria preview shows both - `tests/brief_medium.md` has 13 of 13 without an interface line, `tasks-api` 2, `web-todo` 1. The PM's assumptions are not counted: they exist only after intake, and the preview makes no model call |

<a id="plan-bw"></a>
### BW — Brownfield: an existing codebase as the normal case

Seeding works (`seeding.py`, `/codebase`), then the pipeline treats the repository as greenfield:
no baseline of its existing tests, no protection of existing behaviour, no "new run against a
previous product with a change request", and all 10 benchmarks are greenfield.

| ID | Change | Group | Priority | Status |
|---|---|---|---|---|
| BW.1 | Regression contract at intake: on a seeded workspace the harness runs the existing test suite once; the green set is locked beside the acceptance suite, and a sprint that turns any of it red is sent back like a failed criterion | 2 | P1 | BUILT 2026-10-21, behind `REGRESSION_CONTRACT` (off): seeding writes `.harness/seeded.json`; on a seeded workspace the baseline taken at the suite's lock is the seeded product's own measurement (its unit tests and the locked suite's tests that already pass), so the CI gate raises any of them that later fails as a regression defect |
| BW.2 | Change-request run: `POST /runs` from a finished run's workspace (or an upload) with a change brief; the product's locked suite and BW.1's contract carry over; the specification is a delta | 2 | P1 | BUILT 2026-10-22 behind `CHANGE_REQUEST_RUNS` (off): `WorkspaceSource` type `run` with `run_id` - a completed run of the caller's tenant; `app/server/change_request_runs.py` copies its product and `.git`, leaving `.harness` and install/test output behind; the run is seeded, so BW.1's contract holds its green tests. The old locked suite carries as files, not as a lock |
| BW.3 | Brownfield benchmark family: a previous run's product plus a change brief, hidden tests for the old and the new behaviour, a reference that scores 100% | 1 — now (benchmark only) | P1 | BUILT 2026-10-21: `benchmarks/tasks-api-change` - `base/` is the tasks-api reference, the brief adds due dates, a done filter and a summary; hidden = tasks-api's 10 tests + 5 new; the base scores 10/15 (every old, no new), the reference 15/15 and reads the base's data; `loop.sh bench` uploads `base` into the workspace (`SEED=<dir>` for `start`) |

<a id="plan-pn"></a>
### PN — Non-functional checks on the *product*

The harness CI audits the harness (pip-audit, bandit, secret scan, image scan); the generated
product CI has none of it. `document_manifest.py` allows a README and checks nothing.

| ID | Change | Group | Priority | Status |
|---|---|---|---|---|
| PN.1 | Per pack, as data: the ecosystem's dependency audit (`npm audit`, `pip-audit`, `cargo audit`, `govulncheck`, …), a secret scan and a licence listing; the release stage runs them once and files findings as defects; the generated CI carries the same steps | 2 (adds defects) | P2 | BUILT 2026-10-21 behind `RELEASE_AUDITS` (off): `app/stacks/release_audits.py` - a credential of a never-placeholder shape holds the release back like PN.2, then is a gap; installed packages' licences are listed in `docs/third-party-licences.md`, strong copyleft a gap; the ecosystem's audit (per-language table, a pack's `audit` overriding) is a step of the generated CI, since the sandbox's network is for installs only |
| PN.2 | A README with run instructions and, for a service, an API summary are required release artifacts; the release check fails without them (the documentation specialist already produces the material) | 2 | P2 | BUILT 2026-10-21 behind `RELEASE_DOCS_REQUIRED` (off): `app/stacks/release_docs.py` - no README, a README naming none of the pack's commands (or `start.sh`, an entrypoint), or a locked HTTP route no product document names hold the release back while attempts remain, then are gaps |

<a id="plan-op"></a>
### OP — Operations: the manual steps that cost the owner hours

15–25 human interventions a day on the gate runs: `POST /resume` after a host restart, crons
re-created by hand after a session restart, rewinds by checkpoint id, deploy markers removed by
hand, two sessions deploying at once leaving `Created` containers; gates and stalls notify the
browser only; no backup of Postgres or `runs.db` exists (OS.8 mirrors the object store only).

| ID | Change | Group | Priority | Status |
|---|---|---|---|---|
| OP.1 | Resume on boot: the worker's orphan recovery also re-creates its own schedules and resumes runs it finds paused by a restart, so a power loss needs no hand | 1 — now | P1 | BUILT 2026-10-21: the worker's startup sweep also resumes a run recovery marked failed for a stopped worker within the last 12 hours whose resume was lost (`manage.runs_a_restart_left_failed`); a paused run, or one failed for any other reason, is never touched. Schedules: the API's once-a-minute sweep carries OP.2; the loop's crons stay in the operator session |
| OP.2 | Stall detector and notifications: a run `running` with no model or tool activity for N minutes, or a gate waiting longer than M minutes, posts to a webhook URL and an email (`NOTIFY_WEBHOOK_URL`, `NOTIFY_EMAIL`); the browser notification stays | 1 — now | P1 | BUILT 2026-10-21: `server/stall_notices.py`, in the API's minute sweep: a running run whose transcript has been quiet `STALL_MINUTES` (20), or a gate waiting `GATE_NOTICE_MINUTES` (30), is sent once to `NOTIFY_WEBHOOK_URL` (JSON) and `NOTIFY_EMAIL` (with `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`); nothing is sent when neither is set |
| OP.3 | Nightly `pg_dump` and a copy of `runs.db` and `lessons.json` to the object store (or `./data/backups` until OS lands), with a restore command in `manage.py` and a tested restore | 1 — now | P1 | BUILT 2026-10-21: `loop.sh backup` (compressed `pg_dump` - 1.8 GB against 15 GB as plain SQL - and `lessons.json`, three days kept), run by `loop.sh nightly` even beside a live run; `loop.sh backup --check` restores the newest into a scratch database and counts its runs (272 of 272 on 2026-10-21); `loop.sh restore <dir> <new-database>` never restores over the live one |
| OP.4 | `loop.sh deploy` takes a lock and refuses a second concurrent deploy; `loop.sh rewind` has a timeout and takes a stage name, resolving the checkpoint itself | 1 — now | P2 | BUILT 2026-10-21: `loop.sh deploy` takes a lock (`data/loop/deploy.lock`) and refuses a second; `loop.sh rewind <stage>` already resolved the checkpoint from a stage name, and both its calls now time out (`REWIND_TIMEOUT`, 600 s) |

<a id="plan-ch"></a>
### CH — Harness code health, the cheap part now

`workflow.py` 11,912 lines, `repository.py` 7,550, `integration_checks.py` 7,133,
`sandbox.py` 4,976; most LF fixes land in these. No ruff, mypy or pyright on the harness; no
Dependabot; CI runs the suite serially (`ci.yml:39`, 290 s against 64 s with xdist); 34
skip/xfail; root clutter. Part 12/V (the decomposition) stays last.

| ID | Change | Group | Priority | Status |
|---|---|---|---|---|
| CH.1 | Delete the clutter: `Test Product Intake/`, `test_file`, `test_symlink -> nonexistent_dir`, `.github/*.docx` (none is referenced by a test) | 1 — now | P2 | BUILT 2026-10-21: `Test Product Intake/`, `test_file`, `test_symlink`, `.github/*.docx` removed (in git history if wanted) |
| CH.2 | CI: `pytest -n auto`, `ruff check`, `pyright` on `src/app` (warnings first, errors gated once clean), a Dependabot config for pip and npm | 1 — now | P2 | BUILT 2026-10-21: CI runs `pytest -n auto`; `ruff check src/app` and `pyright src/app` run and report without gating until clean; `.github/dependabot.yml` for pip, npm and Actions |
| CH.3 | The 34 skips and xfails each name their reason and an owner; the timing-flaky test (`HANDOVER.md` L593, overlapping parts) is fixed or quarantined | 1 — now | P3 | BUILT 2026-10-21: `tests/test_every_skip_names_its_reason.py` fails on any skip or xfail without a reason (a bare `@pytest.mark.skip` included); `tests/SKIPS.md` names each kind's owner; `loop.sh suite` re-runs every failure but the S3 three alone and reports `flaky (passed alone)` or `FAILED alone too` - the order-dependent tests are told apart, not hidden |
| CH.4 | Part 12/V, first mechanical step only: `workflow.py` split by stage node into `graph/nodes/*.py` with no behaviour change, the suite as the guard — after the first clean Measure cycle so the split is not itself a variable | after MF.4's first cycle | P3 | PROPOSED |

<a id="plan-ev"></a>
### EV — Evaluation depth

Hidden tests are functional only; nothing scores a product's UI quality (the vision path exists
only for the reviewer); no owner rating is captured per delivered product.

| ID | Change | Group | Priority | Status |
|---|---|---|---|---|
| EV.1 | One-click owner rating (1–5 and a line) on a delivered run, stored with its KPI row; `bench-report` shows it beside the hidden score | 1 — now | P2 | BUILT 2026-10-21: a delivered run's page offers 1-5 and a line (`OwnerRating`); `PUT`/`GET /api/runs/{id}/rating` keep it in `DATA_DIR/ratings/` (only a completed run is rated; rating again replaces it); `loop.sh kpi` writes `owner_rating`/`owner_note` into the KPI row (re-run it after a rating: the row is replaced); `bench-report` shows each benchmark's mean rating and how many were rated beside the hidden score |
| EV.2 | Screenshot rubric for browser products, judged by the judgement model on a fixed checklist (layout, contrast, empty states, error states), recorded as a score, never as a gate | 2 | P3 | BUILT 2026-10-22 behind `SCREENSHOT_RUBRIC` (off): `app/acceptance/screenshot_rubric.py` - when the judgement model reads images, the release shows it the page probe's screenshots with a fixed 4-item checklist (layout, contrast, empty states, error states); 1-5 per item and the mean go to `.harness/screenshot-rubric.json`, the transcript and KPI `screenshot_rubric`; never a gate |

<a id="plan-sf"></a>
### SF — Execution safety

| ID | Change | Group | Priority | Status |
|---|---|---|---|---|
| SF.1 | The "install" command category's network goes through a registry allowlist (the package registries and GitHub), the same egress pattern the harness already uses for seeding; today the grant is unrestricted | 1 — now | P2 | BUILT 2026-10-21: `app/tools/install_egress.py` - every host an install names, on its command line (URLs, `--registry`, `--index-url`, `--trusted-host`, git addresses) or in the files it reads there (`.npmrc`, `.yarnrc*`, `pip.conf`, `package.json` dependency values, `requirements*.txt`, ...), must be a package registry or a source host on `ALLOWED_HOSTS`; `INSTALL_ALLOWED_HOSTS` widens it, `*` lifts it. The sandbox refuses before anything runs, for the harness's own installs too. An install by name goes to its manager's default registry, which is on the list. A network-level egress proxy is not built: this checks what an install is told to fetch, as seeding does |
| SF.2 | Fetched docs, search results and MCP text keep their "data, not instructions" label and are additionally capped and stripped of tool-call-shaped text before injection | 1 — now | P3 | BUILT 2026-10-21: `app/tools/untrusted_text.defanged` replaces tool-call wrappers, unclosed wrapper tags, chat-template special tokens and JSON call heads with a marker before the cap, in `read_docs`, web search results and pages, and every MCP answer; the harness's own text-call reader finds no call in the result |

### Noted, not planned
- Product kinds: five kinds and 30 packs; no mobile, desktop, worker/bot or data-pipeline kind. Strategic, not urgent.
- Design assets: tokens only; icons, favicon and images would be a small pack-level addition.
- A small cheap model for classification and summaries would free the main slot; BD (two local tiers) is the neighbour and is not started.
- Constrained decoding (M.2) stays on Part 22's do-not-implement list; with 22–47% of output lost at the cap, it is re-measured on the current server only if N and AX do not close that number.

**Placement in Part 21 (added 2026-10-21, this appendix):**
- **MF.1–MF.6**, **RC.1–RC.3**, **OP.1–OP.4**, **CH.1–CH.3**, **IN.2**, **BW.3**, **EV.1**, **SF.1–SF.2** are group 1: built now, in that order, before the next Measure cycle.
- **IN.1**, **BW.1–BW.2**, **PN.1–PN.2**, **EV.2** are group 2, after the measured runs, each behind its switch.
- **CH.4** after the first clean Measure cycle.

<a id="plan-appendix-8"></a>
## Appendix 8 (2026-10-22): customer stacks and conventions, SAP (CAP, Fiori, RAP), document templates, documenting legacy code

Owner's questions, 2026-10-22 10:50 JST. Evidence: the code as read on 2026-10-22 (`stack_selector.py`,
`stacks/__init__.py`, `plugins/*`, `doc_templates/*`, `acceptance/suite.py`, `ci.py`, `seeding.py`,
`analysis/project_graph.py`); research [R11](research-findings.md#r11). Groups as in Appendix 7:
*group 1* = built now, no before/after run (most items here are off until a customer configures them);
*group 2* = changes a run that is not configured, validated on measured runs.

<a id="plan-sl"></a>
### SL — Locked stacks and organisation conventions (Q1)

**What exists.** The stack is chosen by a model (`stack_selector`) from the brief's constraint sections;
`choose_pack()` then matches a pack; nothing can force one — `StartRunRequest` has no stack field, the
settings have no allowed-stacks key, and the only lever is wording in the brief. Organisation-level
instruction channels: plugin instructions (per framework, in Postgres, seeded from `plugins/seed.py`,
**no API or UI**), lessons (owner-approved, no create endpoint), steering (per run only). Nothing is
tenant-scoped; no custom-instructions, naming-convention or coding-standards field exists.

**Does it add value?** Yes, twice over. A customer with a mandated stack (an existing platform, a
support contract, a skills base) cannot use a harness that may pick another; and a locked stack
removes a model decision — `run-d1899b44` was cancelled because the selector left the frontend
unstated — and makes the prefix byte-stable. Conventions matter the same way: a product in the
customer's naming and layout is one they can maintain. Rule for the design: **what can be checked is
checked by the harness; the model is told, not trusted.**

| ID | Change | Group | Priority | Status |
|---|---|---|---|---|
| SL.1 | Stack policy, as a setting and a per-run override: `allowed_packs` (multi-select from `ALL_PACKS`), `default_pack_per_kind`, `custom_stacks_allowed` (whether a stack no pack covers may go to custom setup). `StartRunRequest.stack` (optional) names a pack outright. Enforcement is deterministic: `choose_pack()` filters by the policy before matching; the selector's note changes from "choose one of these unless the brief requires something else" to "choose among these"; with a single allowed pack per kind the selector call is skipped. A brief whose constraints name a stack outside the policy stops at the intake gate with the conflict named (auto mode: the policy wins and the decision is recorded) | 1 — now, inactive until configured | P1 | PROPOSED |
| SL.2 | Organisation profile, per tenant: free-text instructions (≤4k chars), structured naming rules (file names, identifier case per language, test file pattern, folder layout, commit message form), coding-standard documents (`.md`, ≤3 files), licence policy (allowed licences for product dependencies; PN.1 enforces). Stored beside plugin instructions, tenant-scoped (`tenant_id` exists on users and runs) | 1 — now | P1 | PROPOSED |
| SL.3 | Delivery of the profile: the free text and standards reach every call through the plugin-instructions middleware under one byte-stable header (prefix cache, ADR-0011), role-sliced under BJ; the **naming rules compile to checks**: a write-time refusal for a file name or identifier that breaks a rule (the write guard already sees every write), a CI-gate finding for the rest, and the lead's readiness check applies the layout rule to the plan's paths. The model is told the rule once; the harness holds it | 1 — now | P1 | PROPOSED |
| SL.4 | UI and API: Settings → *Stacks* (policy) and *Organisation* (profile) tabs; `GET/PUT /api/settings/stack-policy`, `/api/settings/organisation`; plugin instructions get a read/edit API and a tab (today a DB edit); `POST /api/lessons` for operator-written lessons (the store already supports `source="operator"`); the run-start form shows the lock and `preview` names a conflict | 1 — now | P1 | PROPOSED |
| SL.5 | Workspace conventions read from the repo: on a seeded codebase, `AGENTS.md`, `CONTRIBUTING.md`, `.editorconfig`, linter configs and the dominant file-naming pattern become profile proposals the owner confirms (nothing read from a workspace reaches a prompt unconfirmed) | 2 | P2 | PROPOSED |
| SL.6 | Stack-wise naming defaults as pack data: `StackPack.naming` — file-name case, identifier case per kind (module, class, function, constant, variable), test-file pattern (today's `unit_pattern`), folder layout, and the stack's own object names — Python modules `snake_case` / classes `PascalCase`; TypeScript files `kebab-case` with React components `PascalCase.tsx`; Go packages lower-case single words; Java/C# `PascalCase` classes in package directories; Rust `snake_case` modules; Rails/Django model and table names; CAP entities `PascalCase` plural with `camelCase` elements and `…Service` services in a lower-case dotted namespace; Fiori app ids reverse-DNS; ABAP objects with a customer namespace or `Z`/`Y` prefix, type prefixes (`ZCL_`, `ZIF_`, `ZI_`/`ZC_`/`ZR_` for CDS and RAP views, `ZBP_` behaviour pools) and the 30-character limit that is a hard error in-system. Today packs carry only test-file patterns and a prose line or two in `seed.py`; the rest is left to the model | 1 — now | P1 | PROPOSED |
| SL.7 | Enforcement through each ecosystem's own linter where one exists, the harness's regex check otherwise: the profile's rules (SL.2) override the pack's defaults (SL.6) per stack, and the pack maps the merged rules into the linter's configuration file at scaffold — `ruff` `N` (pep8-naming) rules, `@typescript-eslint/naming-convention`, `golangci-lint`/`revive` naming, checkstyle `*Name` checks, `abaplint.json` `object_naming` and `local_class_naming` with the customer's prefixes and namespace; the linter runs at the CI gate as a check family and its findings are defects; file and folder names are checked at write time by the write guard (SL.3). The model reads the merged rules once in its instructions; the linter holds them | 1 — now | P1 | PROPOSED |
| SL.8 | Rules the harness cannot lint are still structured, not prose: database table and column case, route and endpoint case (`/kebab-case` vs `/snake_case`), environment-variable prefix, commit-message form — kept in the profile as named fields, checked by the harness's own detectors where it already reads those surfaces (the integration checks read routes; the environment contract reads variables), reported as findings elsewhere | 1 — now | P2 | PROPOSED |

<a id="plan-rv"></a>
### RV — Organisation review policy and a learned review checklist (Q1, continued 11:09 JST)

**What exists.** Five reviewer roles with fixed prompts: `code_reviewer` (the batch against its
work orders and criteria; findings `{work_order, severity, file, problem, …}` become defects or
advice), `security_reviewer` (with `SECRETS_HERE` and the source under review), `architecture_reviewer`,
`acceptance_reviewer`, `milestone_reviewer`. Finding categories and severities are normalised
(`finding_category.py`, `severity.py`); every finding's disposition is recorded in the Sprint Record
(`with_dispositions`: fixed, superseded, open, sent back). There is no place for a customer's review
policy, and nothing accumulates what reviews keep finding.

**Design.** Two stores, one mechanism. A *policy* is what the organisation says must be reviewed; a
*checklist* is the policy plus what the harness has learned the reviewer keeps finding. Both are
structured items, never prose; an item is either a **check** the harness runs or a **judgement** the
reviewer must answer per item with a citation — and the harness verifies the answer's shape, as it
already does for specialist advice (`unanswered()`).

| ID | Change | Group | Priority | Status |
|---|---|---|---|---|
| RV.1 | Review policy in the organisation profile (SL.2), per reviewer stage: items `{id, text, stage: code|security|architecture|acceptance|milestone, severity_floor, applies_to: stacks/kinds, kind: check|judgement, check: linter rule / integration-check family / regex (for `check` items)}`; a `.md` policy document may be uploaded and is split into proposed items the owner confirms. Injected into the reviewer's request as one numbered, byte-stable "Organisation review policy" block (ADR-0011) | 1 — now, inactive until configured | P1 | PROPOSED |
| RV.2 | Reviewer answers per item: each reviewer's output gains `policy: [{id, result: met|not_met|not_applicable, file, evidence}]`; the harness refuses an answer that skips an item (the `specialist_advice` pattern); a `not_met` becomes a finding at the item's severity floor, through the existing defect/advice split. Items of kind `check` are run by the harness at the CI gate and never asked of the model | 1 — now | P1 | PROPOSED |
| RV.3 | Learned checklist: every review finding is normalised to a shape (stage, category, the problem's form with paths and names blanked, stack) and counted across runs; a shape found in ≥3 runs — or found and *fixed* in ≥2 — becomes a *proposed* checklist item with its evidence runs, in a signed, owner-approved store like the lessons' (`plugins/lessons.py` pattern: proposed → approved → rejected, never injected unapproved). The owner adds and edits items in the same store. Approved items join the policy block for that stage and stack | 1 — now | P1 | PROPOSED |
| RV.4 | Checks beat judgement: for a proposed item whose shape matches a known deterministic family (an unreached export, a secret without a default, an unrouted endpoint, a naming rule, a licence) the harness proposes it as a `check` bound to that detector or linter rule, so it leaves the model's prompt and runs at the gate; the family table lives beside the integration checks, stack specifics in packs | 1 — now | P2 | PROPOSED |
| RV.5 | Precision loop: an item whose findings the owner marks "not a problem" at review gates three times is flagged for retirement; an item whose findings are fixed is kept; both from `with_dispositions`, shown beside each item with its hit and fix counts | 1 — now | P2 | PROPOSED |
| RV.6 | Checklist report per run: every policy and checklist item with its result, evidence (file, finding, check output) and who decided it (harness check or reviewer), in the sprint evidence page, in `DocumentFacts` (DT.1) for a *code review report* document type (DT.3), and on the review gate's page; Settings → Organisation gets a *Review policy* tab with the proposals inbox | 1 — now | P1 | PROPOSED |

**Why structured items on a local model:** a free-text policy pasted into a reviewer prompt is read
once and partly; numbered items the reviewer must answer one by one, with the harness checking that
each was answered, are what made specialist advice stick (the architect's adopted/declined record).
Effort: RV.1–RV.2 1½ days, RV.3 1 day, RV.4 1 day, RV.5–RV.6 1½ days.

<a id="plan-en"></a>
### EN — What an organisation expects beyond the build (research, 2026-10-22 11:14 JST)

Research [R12](research-findings.md#r12): enterprise evaluation checklists for AI coding agents,
governance guides, the EU AI Act's August 2026 obligations, and supply-chain practice (SBOM, SLSA,
AI-BOM). Mapped against the code: `tenant_id` and `role` on users and runs, an `audit_log` table,
rate limits, a deletion contract, Prometheus metrics — and MF.1 (provenance), OP.2 (webhooks),
OP.3 (backups), PN.1 (audits, licences), SF.1 (egress), SL/RV (conventions, review policy) above.
Each row names what is still missing.

| ID | Expectation → change | Group | Priority | Status |
|---|---|---|---|---|
| EN.1 | **Identity** — *via Matura, see MT.1–MT.4*: SSO (OIDC and SAML) and SCIM provisioning; roles `viewer / operator / approver / admin` with per-gate approval rights; tenant isolation proven by tests (a user of one tenant cannot list, read or approve another's runs, documents, policies or lessons). Today: local accounts, two roles, tenant columns with no isolation tests | 1 — now | P1 | PROPOSED |
| EN.2 | **Audit and evidence** — *shape and export now, ingest via Matura later (MT.6)*: a tamper-evident audit log (hash-chained rows) that links every change to its ticket, run, stage, model id and version, prompt hash, commit, test results, review findings, policy version and the named human approver (the EU AI Act's deployer logging: input, output, timestamp, user, exact model version — MF.1 gives the model); export on demand as JSONL and to a SIEM endpoint; retention per tenant; the export tested | 1 — now | P1 | PROPOSED |
| EN.3 | **Supply chain**: a CycloneDX (or SPDX) SBOM per release from the lock files, tagged with commit and run id, in the handover and the release artifacts (PN.1 produces the licence listing from the same data); a **run manifest** — models and versions, quantisation, MCP servers and tools used, prompt-template versions, flags — as a CycloneDX ML-BOM/agent-BOM document; agent-authored commits carry trailers (`Run-Id`, `Model`, `Stage`); release artifacts signed (Sigstore keyless in the generated CI where the host supports it) | 1 — now | P1 | PROPOSED |
| EN.4 | **SDLC integration**: delivery as a pull request to the customer's git host (GitHub, GitLab, Azure DevOps) on a branch, respecting branch protection and CODEOWNERS (never a push to a protected branch); ticket linkage — a run started from a Jira/ADO work item carries its key, posts status and the PR link back, and the brief may come from the ticket; the webhook events of OP.2 cover `gate_waiting`, `run_finished`, `pr_opened` | 1 — now | P1 | PROPOSED |
| EN.5 | **Approvals as policy** — *roles and segregation via Matura (MT.5)*: an approval matrix per gate (which roles may approve release, which may approve a write to a customer system — SAP.4); segregation of duties (the requester is never the sole approver of release); protected paths in the organisation profile (`auth/`, `payments/`, migrations) whose writes pause for a human even in auto mode; an exceptions register (approver, reason, scope, expiry, compensating control); a per-tenant kill switch that pauses every run at the next boundary | 1 — now, inactive until configured | P1 | PROPOSED |
| EN.6 | **Data handling** — *vault via Matura when its BYOK API exists (MT.8)*: the deployment is self-hosted and the default model local, so "no training, no residency question" is a stated property — made checkable: a per-tenant allowlist of model endpoints and MCP servers (SF.1's egress allowlist extended), secrets from a vault (HashiCorp Vault, Azure Key Vault, AWS Secrets Manager) instead of `.env` for provider keys, object-store and ADT credentials, optional PII detection on uploaded briefs and codebases with a redaction report, retention per tenant on top of the deletion contract | 1 — now | P2 | PROPOSED |
| EN.7 | **Quality gates as policy**: coverage threshold, complexity ceiling and duplicate-code limit per stack from the organisation profile, enforced as a CI-gate check family; results of an external scanner (SonarQube, CodeQL) consumed as findings when the customer runs one; WCAG AA (axe, serious and critical) as a release gate for browser products; a performance budget check (startup time, a request-rate smoke) as pack data | 2 (adds defects) | P2 | PROPOSED |
| EN.8 | **Compliance posture**: a `compliance/` bundle per run — audit export, SBOM, run manifest, checklist report (RV.6), documents (DT), the risk-classification note (deployer under the EU AI Act, feature class, which providers see which data) and an Article 50 disclosure in generated READMEs ("built with DevFlow, model X, human-reviewed at gates …"); a model inventory per tenant; an ISO/IEC 42001-shaped records template, filled from the facts | 1 — now | P2 | PROPOSED |
| EN.9 | **Cost and chargeback**: tokens, model minutes and wall-clock per tenant, team and run; a priced local model (GPU-hour rate in settings, since the cost tracker reports "not priced" for local); budgets and alerts per tenant on top of the per-run ceilings (AH.1, AK); a monthly report | 1 — now | P2 | PROPOSED |
| EN.10 | **Operability for the customer's IT**: Helm chart and Kubernetes manifests beside compose; a versioned database migration path and an upgrade note per release; a redacted support bundle (logs, config without secrets, run KPIs) for incidents; HA guidance (two workers, the storage of OS) | 1 — now | P3 | PROPOSED |
| EN.11 | **Governance of the customisations themselves** — *tenant rows under MT.3, role changes audited by Matura*: the organisation profile, stack policy, review policy, templates and lessons are versioned with author, approver and change history; export/import between environments; a change to policy is itself an audited, approvable event (a policy edit can weaken every later review) | 1 — now | P2 | PROPOSED |

**Not planned:** IP indemnity and certifications (SOC 2, ISO 27001, ISO 42001) are commercial and
organisational matters, not harness features; the harness supplies the evidence (EN.2, EN.3, EN.8).

<a id="plan-mt"></a>
### MT — DevFlow on Matura: identity, tenants, roles, audit and compliance come from the platform (2026-10-22 11:33 JST)

**Matura** (`github.com/marunsct/Platform`, Apache-2.0, "make any open-source app enterprise-ready") is the
owner's control plane: Keycloak for sign-in, SSO (SAML/OIDC), SCIM, MFA and passkeys; tenants, workspaces,
memberships and per-app roles; OpenFGA for fine-grained permissions; a hash-chained audit log with SIEM
sinks; entitlements; agent identity (service accounts, agents as revocable members, delegated tokens);
readiness controls, evidence and a trust page; SDKs for Python, TypeScript and Go; a conformance kit.
Its app-integration contract (spec 03, v0.1, 2026-10-16) names **DevFlow as the first app**, and its
delivery plan holds a sprint for it (TS7d). Read 2026-10-22 at `bc5770e`; research
[R13](research-findings.md#r13). **Owner, 2026-10-22 11:40 JST:** the hold on DevFlow changes in Matura's
handover was for the owner's own testing of Matura; the owner will schedule this integration. The plan
below is therefore ready to be scheduled, not on hold.

**Decision.** EN.1, EN.2 (partly), EN.5 (partly), EN.6 (partly), EN.8 (partly) and EN.11 are **not built
in DevFlow**; they are taken from Matura through its SDK and contract, and DevFlow becomes a conformant
Matura app. What Matura does not yet offer an app (audit ingest, secrets/BYOK, usage metering, the
no-code gateway) DevFlow keeps for now, shaped so it can be handed over later.

| ID | Change | Group | Priority | Status |
|---|---|---|---|---|
| MT.1 | Manifest and client: `matura/manifest.json` for DevFlow — permission catalogue (`run.read`, `run.start`, `run.approve`, `run.review`, `run.delete`, `lesson.approve`, `settings.read`, `settings.write`, `secrets.write`, `policy.write`, `template.write`), starter roles `admin / operator / approver / viewer`, `auth.resources` for any MCP endpoint DevFlow exposes, `conformance.resources` (runs) — uploaded with `PUT /admin/v1/apps/devflow`; a `devflow` client in the realm (none exists today) | 1 — now (no run behaviour) | P1 | PROPOSED, to be scheduled by the owner |
| MT.2 | Token verification: `MaturaFastAPI(Verifier)` replaces `get_current_user`; every route checks `perms`, never role names (ADR 0008/0009); `require_admin`/`require_operator` become `require_permission(...)`; the password login and HS256 tokens stay behind `LEGACY_LOGIN` for one release (contract §9); the UI signs in with OIDC PKCE against the `matura` realm and keeps no token in `localStorage`; `users.preferences` moves to `devflow_user_settings(tenant_id, user_id, …)` | 1 — now | P1 | PROPOSED |
| MT.3 | Contract tables and tenancy: the SDK migration creates `matura_*`; `tenant_id` becomes a uuid foreign key to `matura_tenant` on runs, audit_log, runtime_settings, runtime_secrets, model_profiles, plugin_instructions, the organisation profile, review policy, templates and lessons (lessons leave the JSON file for a table); the `'default'` tenant is migrated as a real tenant; `tenant_segment` uses the uuid; the webhook receiver `/matura/events` and `Sync.catch_up` at start-up and hourly keep the tables current; a `tenant.deleting` event purges runs, workspaces, object-store keys (OS keys gain a tenant prefix) and lessons; `user.deleted` pseudonymises actors | 1 — now | P1 | PROPOSED |
| MT.4 | Isolation proven: RLS on every tenant table (`FORCE ROW LEVEL SECURITY`, `current_setting('matura.tenant_id')`), a per-transaction `set_config` in the session factory (the SDK's `tenant_session` is not written yet — DevFlow writes it or contributes it), the app role without `BYPASSRLS`, the admin cross-tenant bypass in `runs.py` removed (platform operators use Matura's console, not DevFlow), the `matura-conformance` kit green in CI (401/403 cases, cross-tenant create/list/read, webhook idempotency and signatures) — this is EN.1's isolation test | 1 — now | P1 | PROPOSED |
| MT.5 | Roles and approvals from the platform: gate approval rights are permissions (`run.approve` per gate kind, `release.approve`); the reviewer on a run is a `matura_user` id; segregation of duties (EN.5) checks `sub` of the requester against the approver; agents appear as members: a run's model calls that act for a person carry the delegated token's `act.sub` into DevFlow's audit ("the agent did this for Ana"); per-run reviewer relations in OpenFGA optional | 1 — now | P1 | PROPOSED |
| MT.6 | Audit: DevFlow's `audit_log` stays (Matura records only its own changes; an app audit-ingest API is not yet specified) but takes the contract's shape now — uuid actor and tenant, `kind`, `act.sub`, policy version, run and commit — and a hash chain per tenant, so that it can be streamed to Matura's sinks or handed to its ingest API when one exists. Export as NDJSON (EN.2) | 1 — now | P1 | PROPOSED |
| MT.7 | Entitlements: read `GET /v1/tenants/{tid}/entitlements` and enforce the keys Matura keeps for apps — `max_concurrent_runs`, `frontier_model`, `max_runs_per_month`, `storage_gb` — answering 402 `plan-limit` as Matura does; cost stays in `cost_tracker` until Matura has a usage-ingest API (then EN.9 reports through it) | 1 — now | P2 | PROPOSED |
| MT.8 | Secrets: Matura has no app secrets/BYOK API yet (OpenBao/KMS is on its roadmap); DevFlow's Fernet store is split from the JWT secret and made per tenant now (EN.6), with a `SecretsBackend` seam so the Matura/OpenBao backend is a configuration change later | 1 — now | P2 | PROPOSED |
| MT.9 | Consoles and settings: in `matura` mode no DevFlow users page — members, invitations, roles, SSO and SCIM are Matura's portal (in `oidc`/`legacy` mode the small Members page of MT.13 remains); DevFlow's Settings keeps model, runtime, stacks (SL), organisation profile (SL/RV), templates (DT); the organisation profile, policy and templates are tenant rows under MT.3; `/portal/` linked from the shell | 1 — now | P2 | PROPOSED |
| MT.10 | Deployment: a compose overlay joining `matura_default` (issuer `localhost:8180/realms/matura`, JWKS at `keycloak:8180`), a webhook registration for `http://app:8000/matura/events`, Helm values for EN.10 referencing the Matura chart; the HANDOVER gains the two-stack bring-up and the issuer/JWKS pitfall | 1 — now | P2 | PROPOSED |
| MT.11 | Asks of Matura (filed in the Platform repo when the owner opens TS7d): an app audit-ingest endpoint and schema; an app secrets/BYOK API; a usage-ingest endpoint for metering; `tenant_session` (RLS `set_config` + placement routing) and the Alembic `matura_tenant_table` operation in the Python SDK; app-level readiness controls (human-approval log, restore-test evidence) so DevFlow's EN.8 bundle can feed the trust page | — | P1 | PROPOSED |

#### Any identity provider, not only Matura (owner, 2026-10-22 11:44 JST)

Matura is one provider behind a seam, not the only one. A customer that already runs Entra ID, Okta,
Auth0, Ping, Google Workspace or a standalone Keycloak connects it directly; a customer on Matura gets
the same through Matura, which also brokers *their* SAML/OIDC IdP and SCIM per tenant. The seam is the
one place that differs; everything downstream (permissions, tenancy, audit, approvals) is the same.

| ID | Change | Group | Priority | Status |
|---|---|---|---|---|
| MT.12 | `IdentityProvider` seam with three modes, chosen by `AUTH_MODE`: `legacy` (today's local users and HS256, kept for single-operator installs), `oidc` (any OIDC provider: `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`, optional client secret for the code flow, scopes), `matura` (the SDK: `perms` from the token, contract tables, events). Every route checks permissions through the seam's `Principal` (`has(perm)`), so the handlers never know which mode is on; the UI's sign-in uses the discovery document of whichever issuer is configured (PKCE for `oidc` and `matura`, the password form for `legacy`) | 1 — now | P1 | PROPOSED |
| MT.13 | Claims mapping for `oidc` mode, as configuration: which claim carries the tenant (`tid`, `tenant`, a group prefix, or a fixed tenant for a single-tenant install), which carries groups or roles (`groups`, `roles`, Entra `roles`/`wids`, Okta `groups`), and a `groups → DevFlow roles` map; DevFlow's own `role → permission` table (the same catalogue as the Matura manifest, kept in one file so the two cannot drift) expands roles to permissions; **JIT provisioning** creates the tenant, user and membership rows from the first verified token and updates them on later ones (versioned by `iat`), so no SCIM is needed to start; optional SCIM 2.0 endpoint for `oidc` mode later (Matura already has SCIM). **Role assignment** has two sources with a precedence rule: *IdP-managed* — the groups mapping recomputes roles on every token, so a group removal takes effect on the next request — wins whenever a mapping is configured for the tenant; otherwise *DevFlow-managed* — a tenant admin sets roles on a Members page (list, set role, deactivate) that exists only in `oidc`/`legacy` mode (the portal owns it in `matura` mode). **Bootstrap:** a JIT user gets the tenant's default role (`viewer`); admin comes from `BOOTSTRAP_ADMINS` (emails or a domain), the groups mapping, or the `legacy` admin promoting the first user of a fresh install. **Deactivation:** a Members-page or SCIM deactivate marks the membership (tokens merely stop arriving otherwise); an admin delete runs the same pseudonymisation hook as Matura's `user.deleted` | 1 — now | P1 | PROPOSED |
| MT.14 | SAML and other non-OIDC IdPs: not implemented in DevFlow; served through a broker — Matura's Keycloak (identity brokering per tenant) or a standalone Keycloak/Dex the customer runs — which presents OIDC to DevFlow; the HANDOVER documents the two broker set-ups | 1 — now (docs) | P2 | PROPOSED |
| MT.15 | Tenancy independent of the provider: the uuid `tenant_id`, RLS and the conformance-style isolation tests (MT.3–MT.4) apply in every mode; in `oidc` mode DevFlow owns the `tenant`/`user`/`membership` tables (same DDL as the Matura contract, so switching a customer to Matura later is a data move, not a schema change); deletion and pseudonymisation hooks are called from JIT updates or an admin command instead of Matura events | 1 — now | P1 | PROPOSED |
| MT.16 | Agent identity in `oidc` mode: a run's model calls act under a service identity DevFlow names in its audit (`kind=agent`, `act_sub` = the person who started the run), the same columns MT.6 adds, so the audit trail reads identically whether delegated tokens come from Matura or DevFlow records the delegation itself | 1 — now | P2 | PROPOSED |

#### Identity process review: the fallback rule and the gaps (owner, 2026-10-22 11:48 JST)

**Owner's decision:** roles are IdP-managed, with DevFlow-managed roles as the fallback. Precisely
(MT.17): per tenant, `role_source = idp_then_devflow` (the default), `idp` or `devflow`. Under the
default, a token whose mapped groups yield at least one DevFlow role sets the member's roles from the
IdP and DevFlow's own assignments for that member are ignored (not added); a token with no mappable
groups — claim absent, empty, or nothing matched — leaves DevFlow's assignments in force. An optional
`additive` flag unions the two for tenants that want it. The Members page shows, per member, which
source is in force and why.

Walking the lifecycle end to end — configure, sign in, create, map, approve, run, change, leave, break —
found these gaps; each has an item.

| ID | Gap | Change | Group | Priority | Status |
|---|---|---|---|---|---|
| MT.17 | The fallback was a sentence, not a rule | `role_source` per tenant as above; `roles_source` and `roles_seen_at` stored on the membership; a token that changes a member's effective roles writes an `identity.roles_changed` audit row with before/after and the source — so gaining `run.approve` through an IdP group is visible in DevFlow's audit even though the change happened elsewhere | 1 — now | P1 | PROPOSED |
| MT.18 | One issuer per install; a multi-tenant install has customers on different IdPs | Per-tenant identity configuration (issuer, audience, JWKS, claims mapping, groups map, `role_source`) with home-realm discovery by email domain on the sign-in page; a platform-level default; in `matura` mode Matura brokers per tenant and this is unused | 1 — now | P1 | PROPOSED |
| MT.19 | Provider quirks break the generic path silently: Entra access tokens for another audience, Okta custom claims only from a custom authorization server, Entra **groups overage** (groups omitted above 200, `_claim_names` instead), group ids vs names | Provider recipes as data (`identity/recipes/{entra,okta,auth0,ping,google,keycloak}.json`: expected claims, audience advice, overage handling); overage handled by preferring app roles over groups and, when only groups exist, a documented Graph lookup or the fallback role; `loop.sh auth-check` validates discovery, JWKS and a sample token's mapping as a dry run, and the Settings *Identity* tab has the same *Test* button | 1 — now | P1 | PROPOSED |
| MT.20 | No service accounts in `oidc` mode: CI, the loop's operator account (`LOOP_USER/PASSWORD`) and API integrations have no user | Client-credentials tokens map to a `kind=service` principal by `azp`/`client_id` with roles from a per-tenant service map; the loop moves from password login to a client credential (or stays on `legacy`, which remains supported); every service action is audited with `kind=service` | 1 — now | P1 | PROPOSED |
| MT.21 | Background work has no principal: Celery tasks, schedulers (retention, backups, stall detector, feed catch-up) run for every tenant | A `system` principal that may only iterate tenants explicitly and sets `matura.tenant_id` per tenant inside the loop — never a `BYPASSRLS` session; a test asserts no scheduled job runs a query without a tenant set; approval timeouts that auto-approve are audited as `system` | 1 — now | P1 | PROPOSED |
| MT.22 | Revocation latency and sessions: a disabled IdP account keeps a valid token until expiry; the UI session outlives it | Short access tokens (≤15 min) in the recipes; OIDC back-channel logout (`sid`) and front-channel logout supported by the UI; a *Deactivate now* on the Members page that blocks `sub` immediately regardless of token validity (a small denylist with TTL = token lifetime) | 1 — now | P2 | PROPOSED |
| MT.23 | Account linking: a legacy user and an IdP user are the same person; `sub` is the key and email can change | One-time link by verified email (`email_verified` required) on first IdP sign-in, after which `sub` is authoritative; an unverified email never links; an admin can link or unlink on the Members page; audited | 1 — now | P2 | PROPOSED |
| MT.24 | A person in several tenants: tenant choice and tenant switching | Membership in many tenants from several mapped groups; a tenant selector after sign-in and `X-DevFlow-Tenant` on every API call, checked against the membership (never trusted from the token alone unless it carries `tid`); the UI shows the active tenant in the shell | 1 — now | P2 | PROPOSED |
| MT.25 | Roles before first login: an admin wants to grant `approver` to someone who has not signed in yet (invitations exist only in Matura) | Pending grants by email, applied at JIT creation and then subject to `role_source`; shown as pending on the Members page | 1 — now | P2 | PROPOSED |
| MT.26 | Lockout when the IdP or the mapping is misconfigured | Break-glass: the `legacy` signer stays available at `/api/auth/break-glass` for `BOOTSTRAP_ADMINS` only, bound to loopback or an allow-listed network, rate-limited, every use audited and shown on the health page; the auth-check of MT.19 runs before a mode switch is saved | 1 — now | P1 | PROPOSED |
| MT.27 | Identity has no settings surface or observability | Settings → *Identity* tab (platform admin: mode, per-tenant issuer and mapping, groups map, `role_source`, bootstrap admins, service accounts, test); metrics for verification failures by reason, JIT creations, role changes, JWKS refresh failures (keys cached with TTL; an unknown `kid` triggers one refresh, then fails closed) | 1 — now | P2 | PROPOSED |
| MT.28 | Tests cover three issuers but not the quirks | The issuer matrix gains Entra-shaped (`roles`, `tid`, overage) and Okta-shaped (`groups`, custom authorization server) fakes, service-account and `system` principals, back-channel logout, linking, multi-tenant switching and break-glass; the isolation tests run in each | 1 — now | P1 | PROPOSED |

Conformance test matrix: the MT step-2 and step-6 tests run against the issuers of MT.28 — `FakeIssuer`
(Matura), Entra- and Okta-shaped OIDC fakes, and the legacy signer — and the same 401/403/isolation
expectations must hold in all of them.

**What this changes in EN:** EN.1 → MT.1–MT.4 (Matura) or MT.12–MT.15 (direct IdP); EN.2 → MT.6 (ingest pending Matura); EN.5 approvals and
segregation → MT.5 (protected paths, exceptions and the kill switch stay in DevFlow); EN.6 vault → MT.8;
EN.8 model inventory and readiness → via Matura's evidence once app controls exist; EN.9 budgets → MT.7;
EN.11 → tenant rows under MT.3 with Matura's audit of role changes. EN.3, EN.4, EN.7, EN.10 are unchanged.

#### MT implementation sequence (for the owner's scheduling)

Each step is one branch, one commit series, tests proven to fail on the old code, suite green, both
handovers and `STATE.md` updated; the old login stays usable until step 8.

| Step | Work | Files (DevFlow) | Test that proves it | Days |
|---|---|---|---|---|
| 0 | Bring-up: Matura compose beside DevFlow's; `devflow` client with the Matura mapper in `keycloak/realm/matura-realm.json` (Platform repo); DevFlow compose overlay joining `matura_default` with `MATURA_ISSUER`, `MATURA_JWKS_URL`, `MATURA_AUDIENCE=devflow`, `MATURA_WEBHOOK_SECRET`, `MATURA_APP_CLIENT_ID/SECRET` | `docker-compose.matura.yml`, `.env.example`, `docs/HANDOVER.md` | `loop.sh ready` reports the issuer reachable and the JWKS key id | ½ |
| 1 | Manifest: `matura/manifest.json` (permissions, roles, resources, `conformance.resources`); `manage.py matura register` uploads it (`PUT /admin/v1/apps/devflow`) and the webhook (`/admin/v1/apps/devflow/webhooks`) | `matura/manifest.json`, `server/manage.py` | manifest validates against Matura's schema; every route's permission appears in the catalogue (a test walks the FastAPI routes) | ½ |
| 2 | Verification through the `IdentityProvider` seam (MT.12): `AUTH_MODE=legacy|oidc|matura`; `oidc` = generic JWKS verifier + claims mapping + JIT provisioning (MT.13); `matura` = the SDK's `Verifier`; `get_current_user` returns a `Principal`; `require_admin/operator` → `require_permission`; the role→permission catalogue is one file shared with the manifest | `server/identity/{base,legacy,oidc,matura}.py`, `server/auth.py`, `server/api.py`, every router's dependencies, `pyproject.toml` | the three-issuer matrix: 401 (no token, expired, wrong `aud`, unknown kid, wrong issuer), 403 (missing perm), 200 with perm, in `legacy`, `oidc` (Entra-shaped claims) and `matura` modes; JIT creates tenant and user rows from a first token | 2 |
| 2b | Identity hardening (MT.17–MT.21, MT.26): `role_source` and roles-changed audit, per-tenant configuration, provider recipes and `auth-check`, service accounts, the `system` principal, break-glass | `server/identity/*`, `server/tasks.py`, `scripts/loop/*` | the MT.28 matrix; no scheduled job queries without a tenant; break-glass refused off the allow-list | 2 |
| 3 | UI: OIDC PKCE (`oidc-client-ts`) against whichever issuer `GET /api/auth/config` names (Matura's realm or the customer's IdP); token kept in memory with silent renew; `/portal/` link in the shell; the login page shows "Sign in with Matura" and, under the flag, the password form | `langchain-ui/src/lib/session.ts`, `api/index.ts`, `pages/Login.tsx`, shell | Playwright: sign-in redirects to Keycloak and back; a 401 triggers renew, not a logout; no token in `localStorage` | 1 |
| 4 | Contract tables and tenancy: the contract DDL in every mode (SDK migration in `matura` mode, DevFlow-owned in `oidc`/`legacy`, MT.15); `tenant_id uuid` FK on `runs`, `audit_log`, `runtime_settings`, `runtime_secrets`, `model_profiles`, `plugin_instructions`, the organisation profile, review policy, templates; `lessons` move from `DATA_DIR/lessons.json` to a table (signature kept); migration of `'default'` to a real tenant; `tenant_segment` on the uuid; `devflow_user_settings` | `server/run_store.py`, `runtime_settings.py`, `plugin_store.py`, `plugins/lessons.py`, `workspaces.py`, Alembic migrations | migration round-trips a fixture database; every table with tenant data has the FK (a test lists tables) | 1½ |
| 5 | Events and feed: `webhook_router` at `/matura/events`; `Sync.bootstrap` at start-up and `catch_up` hourly (Celery beat); `tenant.deleting` → purge runs, workspaces, object-store keys (tenant prefix), lessons; `user.deleted` → pseudonymise actors | `server/matura_events.py`, `server/tasks.py`, `run_retention.py`, `object_store.py` | signed event applied once (idempotent), stale signature refused, version rule (older event ignored), deletion purges everything the retention contract names | 1 |
| 6 | Isolation: `FORCE ROW LEVEL SECURITY` on tenant tables; session factory sets `matura.tenant_id` per transaction from the `Principal` (Celery tasks carry the tenant explicitly); the app role without `BYPASSRLS`; the admin cross-tenant bypass in `runs.py` removed; `matura-conformance` in CI | `server/db.py` (or the session factory), `run_store.py`, `runs.py`, `.github/workflows/ci.yml` | conformance kit green; a test proves a worker task without the tenant set reads zero rows rather than every row | 1½ |
| 7 | Roles, approvals, audit: gate approvals check `run.approve` / `release.approve`; `reviewer` becomes a `matura_user` id; segregation of duties; `audit_log` gains `actor_id uuid`, `tenant_id uuid`, `kind`, `act_sub`, `policy_version`, `run_id`, `commit`, `prev_hash`/`hash` (chain per tenant), NDJSON export; delegated-agent `act.sub` recorded on model calls made for a person | `server/auth.py` (record_audit), `runs.py`, `lessons_api.py`, `observability/*` | approval by the requester refused when SoD is on; chain verifies and a tampered row breaks it; export matches the contract's test vectors | 1½ |
| 8 | Entitlements, secrets, cleanup: read `/v1/tenants/{tid}/entitlements` and enforce `max_concurrent_runs`, `frontier_model`, `max_runs_per_month`, `storage_gb` (402 `plan-limit`); `SecretsBackend` seam with per-tenant Fernet; remove the users admin from `manage.py` CLI except for break-glass; `LEGACY_LOGIN` default off one release later | `server/entitlements.py`, `runtime_settings.py`, `manage.py` | over-limit start answers 402; a tenant cannot read another's secret rows | 1½ |
| 9 | Docs and asks: HANDOVER two-stack bring-up and the issuer/JWKS pitfall; `STATE.md`; ADR-0014 *DevFlow is a Matura app*; MT.11 asks filed as issues in the Platform repo (audit ingest, app secrets/BYOK, usage ingest, `tenant_session` + Alembic op, app readiness controls) | `docs/*`, Platform issues | — | ½ |

**Effort:** about 13½ days in sequence; steps 2–3 and 4–5 can run in parallel; MT.22–MT.25 and MT.27 follow as a second identity batch (about 3 days). The order keeps a
working login at every step and lands isolation (step 6) before approvals depend on it. **Risks:** the contract is v0.1 *proposed* and Matura is early (tokens live 5 min, no
instant revocation; portal pages for SSO/SCIM/agents/audit not built); DevFlow's psycopg pools need the
per-transaction `set_config` or RLS silently sees nothing; the issuer/JWKS host mismatch in compose.

<a id="plan-sap"></a>
### SAP — CAP, Fiori and RAP as stacks (Q2)

**Research summary** ([R11](research-findings.md#r11)). Three different situations:
- **CAP (Node.js)** builds and runs entirely in the sandbox: `cds init`, `cds watch`, SQLite in memory
  or a file, OData V4 at `/odata/v4/...`, tests with `@cap-js/cds-test` (Jest or Mocha), `cds build`
  for release. Official MCP `@cap-js/mcp-server` (Apache-2.0): `search_model` over the compiled CDS
  model, `search_docs` with local embeddings — both offline.
- **Fiori elements / UI5** builds in the sandbox on top of CAP or an OData metadata file. Official
  `@sap-ux/fiori-mcp-server` has `generate_fiori_app_cap`, `generate_fiori_app_odata` and a
  list/get/execute flow for page and manifest changes; `@sap/generator-fiori` is interactive (Yeoman)
  with no documented headless mode. Tests: OPA5/QUnit via karma, wdi5 (WebDriver), or the harness's
  own Playwright against the served page. `@ui5/mcp-server` and `ui5-linter` cover freestyle UI5.
- **RAP (ABAP)** cannot be compiled, activated or run outside an SAP system (BTP ABAP Environment,
  S/4HANA Cloud, or on-premise ≥2022). Development happens in-system through ADT; abapGit serialises
  objects to files. Off-stack: `abaplint` lints and syntax-checks against a target release, and the
  abaplint transpiler runs ABAP Unit for pure-ABAP logic on Node (no CDS, RAP or database). SAP lists
  an official ADT MCP server (Help Portal) and there are a dozen community ADT MCP servers (MIT/Apache)
  that read, write, activate and run ABAP Unit/ATC on a live system.

**Decision.** CAP and Fiori are ordinary packs; RAP is a new class of stack — a *connected* stack whose
verification runs on a customer system through MCP — and needs one architectural seam before any pack.
Order: CAP → Fiori elements on CAP → UI5 freestyle → RAP.

| ID | Change | Group | Priority | Status |
|---|---|---|---|---|
| SAP.1 | `sap_cap_node` pack (kinds `http_api` and `fullstack`): scaffold `cds init` + `cds add sqlite,…`; Node ≥20; `PORT` honoured by CAP, `DATA_DIR` → SQLite file via `cds.requires.db`; start `cds serve`; unit tests `@cap-js/cds-test` with Jest; the compiler check is `cds compile srv --to json`; acceptance over HTTP (httpx) against OData V4; release `cds build` + Dockerfile + optional `mta.yaml`; plugin instruction seed for CDS modelling, annotations and service handlers; `@cap-js/mcp-server` registered as a read-only tool for the architect and the backend specialist (`search_docs`, `search_model`) | 2 (a new pack is validated on its benchmark) | P1 | PROPOSED |
| SAP.2 | `sap_fiori_elements_cap` pack (kind `fullstack`): the UI is generated by the harness as a scaffold step, not by the model — a spike decides between `@sap-ux/fiori-mcp-server generate_fiori_app_cap` called by the harness and a pinned `@sap/generator-fiori` driven non-interactively; served by `cds watch` under `app/<name>/webapp`; page checks and hidden tests with Playwright, waiting for UI5 readiness and using role/text locators; OPA5 optional; the pack opts out of the harness's CSS design tokens (UI5 themes own the look); annotations (`@UI.*`) are the model's work, checked by `cds compile` and the served page | 2 | P1 | PROPOSED, after SAP.1 |
| SAP.3 | `ui5_freestyle` pack (kind `browser_app`): `@ui5/cli`, `ui5 serve`, `ui5-linter`, QUnit via karma; `@ui5/mcp-server` for the UI specialist | 2 | P3 | PROPOSED |
| SAP.4 | Connected-stack seam: a pack may declare that build, activate, unit-test and lint steps run through named MCP tools instead of sandbox commands (`StackPack.remote_verification`); results come back as the same `VerificationRun`/junit shapes the CI gate reads; credentials are a tenant setting never shown to a model; every write to a customer system is a gated action (approval mode by default, auto only on a system the owner marks *development*); the workspace keeps abapGit-serialised files as the source of truth | 2 | P2 | PROPOSED |
| SAP.5 | `sap_rap_abap` pack on SAP.4: file formats `.ddls.asddls`, `.bdef.asbdef`, `.abap` (behaviour implementation, unit tests), `.srvd.srvdsrv`, `.srvb.srvbsrv`, `.ddlx.asddlxs`; local checks `abaplint` (target release, Clean Core / ABAP Cloud rules, and the customer's naming from SL.6/SL.7) in the sandbox; off-stack ABAP Unit for pure-logic classes via the abaplint transpiler; in-system push, activate, ABAP Unit and ATC through an ADT MCP server (SAP's official one when available to the customer, else a vetted community server); acceptance through the exposed OData service (httpx), so hidden tests stay black-box. Needs an SAP system the owner provides; without one the pack is lint-only and says so | 2 | P2 | PROPOSED, after SAP.4 |
| SAP.6 | MCP and skills policy for SAP: official SAP servers (Apache-2.0) first — `@cap-js/mcp-server`, `@sap-ux/fiori-mcp-server`, `@ui5/mcp-server`; `mcp-sap-docs` (Apache-2.0) as the docs source for `DOCS_LOOKUP`; each exposed to a stage as the few tools it needs (tool count is coordination cost, R7); SAP's Apache-2.0 skill repos (capire CAP skills, CAP Agentic Engineered Skills, UI5 plugins) are read into plugin-instruction seeds, GPL skill repos are not | 1 — now (policy and registry entries) | P1 | PROPOSED |
| SAP.7 | Benchmarks: `bookshop-cap` (OData V4 service, hidden httpx tests, CAP reference), `bookshop-fiori` (list report + object page on the same service, hidden Playwright tests), and a RAP family only once SAP.5 has a system | 1 — now (benchmarks only) | P1 | PROPOSED |

**Effort:** SAP.1 2 days + bench; SAP.2 spike ½ day then 2 days; SAP.4 3 days; SAP.5 3 days plus the
customer system; SAP.3 1 day. **Risks:** UI5 pages render late and heavily (Playwright timeouts, page
checks); the Fiori generator's headless path is undocumented (the spike decides); RAP cannot be
scored without a system; CAP Java is a separate pack (Maven) and is not planned.

<a id="plan-dt"></a>
### DT — Customer document templates with test results and evidence (Q3)

**What exists.** Twelve Jinja2 Markdown templates (`doc_templates/templates/*.md.j2`) render the
harness's own documents; `read_document` reads `.docx`/`.pdf` for input only; there is **no DOCX or
PDF output and no uploaded-template support**. The data for a test report already exists:
`.harness/acceptance-result.json` (per criterion: status, tests, outcomes, messages, output tail,
accessibility, overlaps), `.harness/ci.json` (per unit and acceptance test outcome, commit, label),
JUnit XML under `test-results/`, screenshots (flat list, on failure by default), the evidence pages,
the decision log, the sprint record. Missing: a per-test link to its screenshot.

**Decision (the owner left it to judgement).** The harness keeps its own structured facts as the
source of truth and **renders the customer's template from them deterministically**; the model fills
only prose placeholders that have no harness data, from the facts, in one bounded call per document,
and never writes a result. A template is a view, not a workflow change.

| ID | Change | Group | Priority | Status |
|---|---|---|---|---|
| DT.1 | Document facts: one `DocumentFacts` model assembled by the harness at release — product, stack, specification sections, architecture decisions, file map with purpose and interfaces (`project_graph`, `project_memory`), criteria with their tests, outcomes, messages, output and evidence paths, unit tests from JUnit/`ci.json` with per-test outcome and duration, coverage when the runner reports it, defect log, sprint record, commit, environment, timestamps | 1 — now | P1 | BUILT 2026-10-22, on demand (not yet at release, so runs are unchanged): `app/handover/facts.py` `document_facts(root)` - product, pack, commit, both commands, criteria with status, tests, interface lines and deferrals, unit tests from the JUnit report, decisions, completion gaps; read-only, never raises |
| DT.2 | Evidence per test: Playwright `screenshot: 'on'` and `trace` on failure into `test-results/evidence/<test>/`, JUnit attachments; `acceptance-result.json` tests gain `evidence: [paths]`; the page probe's `page-desktop/phone.png` attach to their criteria. Unit-test evidence is the runner's output per test | 1 — now | P1 | PROPOSED |
| DT.3 | Template registry, per tenant: upload `.docx` (placeholders in `{{ }}` and loops, read with `docxtpl`) or `.md`/`.html` (Jinja2, the existing renderer); document type (technical_design, unit_test_report, acceptance_test_report, release_notes, custom); on upload the harness lists the template's variables and classifies each — *harness-filled* (a `DocumentFacts` field or an alias from a small mapping table), *prose* (filled by DT.5), *unknown* (shown to the uploader to map or drop). Fixed built-in templates ship for the three named types so a customer without a template still gets them | 1 — now | P1 | PROPOSED |
| DT.4 | Rendering and delivery: `docxtpl` for `.docx` (tables for test cases, images for evidence), Markdown → `.docx` via `python-docx` for `.md` templates, PDF through LibreOffice headless in the worker image behind `PDF_EXPORT` (image size cost); documents are produced at release (and on demand for a finished run), stored under `docs/deliverables/`, listed by `GET /api/runs/{id}/documents`, downloadable singly and in the handover zip; a *Documents* tab on the run page | 1 — now | P1 | PROPOSED |
| DT.5 | Prose fill: for placeholders classified *prose* (design rationale, scope summary, known limitations) one bounded model call per document receives the facts and the placeholder names and returns text per placeholder; the harness refuses an answer that cites a test, file or number not in the facts; every placeholder left empty is listed in the document's front matter, never silently blank | 2 (adds a model call) | P2 | PROPOSED |
| DT.6 | Test documents in detail: the unit-test document lists each test with file, name, outcome, duration, failure message and the command and commit it ran under; the acceptance-test document lists each criterion, its tests, steps (from the scenario text the suite already renders), expected vs actual (contract line vs outcome), evidence images, and the run's summary (passed/failed/skipped, support tier, deferred items, completion gaps); both are harness-written, no model | 1 — now | P1 | BUILT 2026-10-22, on demand: `app/handover/test_documents.py` (unit-test and acceptance-test documents, Markdown, failures first, a criterion no test carries said so); `loop.sh documents <run>` writes them with `facts.json` to `data/documents/<run>/`. Evidence images wait for DT.2 |

**Effort:** DT.1–DT.2 1½ days, DT.3–DT.4 2 days, DT.6 1 day, DT.5 1 day. `docxtpl` (MIT) is a
`python-docx` extension; LibreOffice adds ~300 MB to the image, hence the switch.

<a id="plan-rd"></a>
### RD — Technical specification, unit-test and acceptance-test documents for an existing repository (Q4)

**What exists.** Seeding (`seeding.py`: git, archive, or a previous run behind `CHANGE_REQUEST_RUNS`),
the regression contract (BW.1, behind `REGRESSION_CONTRACT`: the seeded product's own tests run and
locked), the project graph (CG.1), per-file purpose and interfaces (`project_memory`), reachability,
integration checks and the language services. **A brief is always required and the graph always starts
at `product_manager`**; the architect has no "describe what exists" mode; `test_discovery` is lint only.

**Decision.** A third run kind, *document*, beside *build* and *change request*: the harness surveys
the repository deterministically, the architect role recovers the design from the survey under a
citation rule the harness verifies, the existing tests are run and become the unit-test document, an
acceptance suite is derived from the product's surface and run, and DT renders the three documents.
Where there are no tests, characterisation tests are written (group 2).

| ID | Change | Group | Priority | Status |
|---|---|---|---|---|
| RD.1 | Run kind `document`: `POST /api/runs` with a seeded codebase and no brief (or a one-line purpose); graph path `repo_survey → architecture_recovery → test_catalogue → acceptance_recovery → documents → user_review_release`; stack detected from manifests (pack or custom setup, as a seeded build run does) | 2 | P1 | PROPOSED |
| RD.2 | `repo_survey` (harness, no model): manifests and versions, entrypoints, the project graph, file purposes and interfaces, routes/endpoints and pages (the integration checks' detectors), CLI commands (`--help`), database schema (migrations, models), configuration and environment variables read, existing tests found and their runner, licences (PN.1's audit) — written as `docs/repository_survey.md` and as facts for DT | 1 — now (read-only) | P1 | PROPOSED |
| RD.3 | `architecture_recovery`: the architect role in *describe-what-exists* mode — inputs are the survey and the digest; it may not propose or invent; every statement carries a citation `path:symbol` or `path:line`, and the harness checks each against the graph and the files — an uncited or unverifiable statement is marked *unverified* in the document and counted; the output fills the technical-specification facts (components, data model, interfaces, flows, decisions inferred, known gaps) | 2 | P1 | PROPOSED |
| RD.4 | `test_catalogue`: the existing tests run once (BW.1's mechanism), each test mapped to the files it reaches (graph) and the features they belong to; the result is the unit-test document (DT.6) with per-test outcome; a repository with no runnable tests gets that stated, not invented | 1 — now (read-only) | P1 | PROPOSED |
| RD.5 | `acceptance_recovery`: criteria derived from the product's surface — each route, page action, CLI command — in the harness's criterion form, confirmed by the owner at a gate (auto mode: all kept); the QA role writes the acceptance suite against the running product as a build run does; the run's result is the acceptance-test document with evidence (DT.2, DT.6) | 2 | P1 | PROPOSED |
| RD.6 | Characterisation tests where none exist: for each entrypoint or module without a test, the testing specialist writes golden-master tests from observed behaviour (not from the spec), under the usual readiness and vacuous-green gates; they ship as the repository's first unit-test document and become the regression contract for later change-request runs | 2 | P2 | PROPOSED |
| RD.7 | Benchmark: two small open-source repositories with hand-written reference documents; deterministic score — share of files, endpoints and commands the specification names, citation validity rate, unverified-statement rate, tests run vs tests present | 1 — now (benchmark only) | P1 | PROPOSED |

**Why this shape on a local model:** recovery is where a model invents most; the survey gives it facts
and the citation check makes invention visible and countable. Effort: RD.2 1 day, RD.1+RD.3 2 days,
RD.4 ½ day, RD.5 1½ days, RD.6 2 days, RD.7 1 day.

**Placement in Part 21 (added 2026-10-22, this appendix):**
- **Group 1, now:** SL.1–SL.4, SL.6–SL.8, RV.1–RV.6, EN.2–EN.6, EN.8–EN.11 (EN.1 via MT), MT.1–MT.10 in the MT sequence when the owner schedules it, SAP.6–SAP.7, DT.1–DT.4, DT.6, RD.2, RD.4, RD.7.
- **Group 2, after the measured runs, each behind its switch:** SL.5, SAP.1 → SAP.2 → SAP.3, SAP.4 → SAP.5 (needs the owner's SAP system), DT.5, RD.1, RD.3, RD.5, RD.6.
- Dependencies: DT before RD's documents; SAP.4 before SAP.5; BW.1/BW.2 and CG.1 (built) under RD.

## Appendix 9 (2026-10-22): prefix-cache discipline — the stable-prefix request layout

Owner's question, 2026-10-22 12:18 JST: *can the code base be kept as key/value pairs
in RAM beside llama.cpp so it is read, not recomputed?* Answer: that is the attention
KV cache, llama-server already keeps it (`cache_prompt`, `--cache-reuse`, `/slots`
save/restore), and it only pays off when the cached bytes are a **literal, byte-identical
prefix** of the next request. The harness decides whether they are. This appendix absorbs
[BA](#plan-ba) (NOT STARTED; its dependency BF is DONE since `ab2afae`) and turns it into
a request-layout rule with the places the code breaks it today. No launch flag of the
owner's is touched; server-side items are advice.

**Evidence.** Code as read on 2026-10-22 (branch `harness-hardening-session`):
`agents/role_agent.py:662-752`, `agents/project_memory.py:136-155, 366-385, 484-516`,
`agents/project_snapshot.py:111, 150`, `agents/where_things_stand.py:144-149`,
`agents/workspace_digest.py:556-599, 641-650`, `agents/settled_answer.py:1746-1822,
2086-2149`, `agents/compaction.py:82-88, 202-255`, `plugins/middleware.py:552-606`,
`server/steering.py:97-106`, `models/__init__.py:437-599, 617-665`,
`graph/workflow.py:1194-1209, 3847-3864`, `observability/run_kpis.py:161-189`.
Measured: `cached_token_share` 0.726 on brief_medium (I3/I7), 158 tool-list changes in
that run; `cache_miss_after_tool_change` is already counted (BF).

### 9.1 What one request looks like today, and where the prefix breaks

The live order is: **system message** (role prompt + rules → deepagents base text →
environment contract → plugin/framework instructions → steering notes) → **first human
message** (project memory prepended to the first of: carry-over note / project snapshot /
stage request, with the `where_things_stand` block before the request text and the
held-files line after it) → **transcript** (append-only) → **per-call tail** (workspace
digest with call numbers, memory `changes_since` note, settled-answer notices — request
overrides only, never stored).

That is already close to the right shape. The prefix is broken by:

| # | Break | Where | How often |
|---|---|---|---|
| 1 | Tool list changes inside a stage: research share spent, read tools withheld, one repeated tool dropped, all look-only tools dropped, `tools=[]` | `tools/research.py:94-104`, `settled_answer.py:2086-2140` | 158 times on brief_medium; each re-prefills the whole context because tools are rendered into the system prompt by the chat template |
| 2 | Steering notes are rendered **in the system message** and re-read every call | `plugins/middleware.py:583-606`, `steering.py:97-106` | once per note added mid-stage, every stage thereafter until its scope ends |
| 3 | `enable_thinking` / `reasoning_effort` toggled after a lost reply or a spiral | `settled_answer.py:1746-1771`, `thinking.py:134-152` | per lost reply; whether the template change lands in the prefix or only in the generation prompt depends on the model's template (**verify per model**, PX.2 step 4) |
| 4 | `time.strftime('%H:%M:%S')` in the project snapshot (second opening message) | `project_snapshot.py:111, 150` | every stage visit; parallel siblings and retries can never share past this byte |
| 5 | The memory's file order depends on the request text: rank −1 for files the request names, and `digest_of` picks spec sections by focus | `project_memory.py:139-143, 163-203` | every fan-out: six builders in one sprint render six different memories of the same code base |
| 6 | Argument truncation rewrites older tool calls as the keep window slides | `role_agent.py:422-426` (deepagents `truncate_args`) | every call above 0.5 × ceiling: a message sent whole on call N is shortened on call N+1 |
| 7 | Reasoning carry: the last 800 chars of reasoning copied into earlier tool-calling assistant messages, dropped again when a prose reply appears | `models/__init__.py:617-665` | per prose reply |
| 8 | Compaction replaces everything before the cutoff with one head message | `compaction.py:202-255` | once per 0.8 × ceiling; unavoidable, but the tail after the cut is recoverable with `--cache-reuse` |
| 9 | Slot eviction: `concurrent_requests = min(6, total_slots)` but compaction summaries, gathering calls, keyword extraction and other runs share the same slots; nothing pins a thread to a slot | `workflow.py:1194-1209`, `call_gate.py:151-170` | unmeasured — PX.1 makes it visible |

Items 4–7 are the ones no earlier session named; BA covered 1 and 9.

### 9.2 The rule (ADR candidate: *request layout for a prefix cache*)

A request has four zones, in this order, and nothing moves between them:

1. **Run-stable**: system message = role prompt + rules + base text + environment
   contract + plugin instructions + tool schemas. Byte-identical for every call of a role
   in a run.
2. **Visit-stable**: the opening messages = canonical project memory + snapshot + request.
   Byte-identical for every call of one stage visit; identical across parallel siblings
   up to the request text.
3. **Append-only transcript**: a stored message is never rewritten after the call that
   produced it. Anything that must shorten it (cut replies, long arguments) is shortened
   **at store time, once**, or at compaction, never on a sliding window.
4. **Volatile tail**: everything that changes per call — digest, call numbers, budget
   warnings, steering notes, corrections, `changes_since`, carried reasoning — goes after
   the transcript as request overrides.

Test shape for every PX item: serialise two consecutive requests of one thread (BF's
`blocks` record), assert the common prefix covers zones 1–3 of the earlier one.

<a id="plan-px"></a>
### PX — Initiatives

<a id="plan-px-1"></a>
#### PX.1 Measure where the prefix breaks — P1, group 1

- **Goal.** Every model call records why its prefix did not match the previous call of
  the same thread, so PX.2–PX.8 are ordered by measured cost, not by guess.
- **Evidence.** BF records block sizes and `cache_miss_after_tool_change`; nothing
  records the other eight breaks, and `cached_token_share` is a run total.
- **Files.** `src/app/models/__init__.py` (per-call hook: hash the serialised request at
  the boundaries system / tools / opening messages / each history message, keep the
  previous hashes per thread in `stage_memory`), `src/app/observability/run_kpis.py`
  (`prefix_break_reason` counter: `tools_changed`, `steering_changed`,
  `thinking_toggled`, `snapshot_clock`, `memory_order`, `args_truncated`,
  `reasoning_carry`, `compaction`, `evicted` — identical prefix hash yet
  `cache_read == 0` — and `other`; plus `uncached_tokens_by_reason`),
  `scripts/loop/kpi_ledger.py` (the columns), `scripts/loop/patterns.py` (per-stage
  family).
- **Steps.** (1) Hash boundaries from BF's `blocks` plus one hash per history message.
  (2) Classify the first differing boundary. (3) Read llama-server's `timings`
  (`prompt_n`, `cache_n` where present) beside `input_token_details.cache_read` and keep
  both. (4) Run `loop.sh kpi` on the two Measure pair 3 runs (no deploy needed — the
  hook is read-only and can be a post-hoc replay over the stored requests if the records
  carry the full messages; otherwise the next Fix batch).
- **Tests.** `tests/test_a_prefix_break_is_classified_by_its_first_difference.py`
  (fails on old code: no reason recorded).
- **Acceptance.** A table "uncached tokens by reason" for one tasks-api run and one
  brief_medium run.
- **Effort.** S.  **Depends on.** BF (done).

<a id="plan-px-2"></a>
#### PX.2 Tool list and template settings constant per stage visit — P1, group 2 (`STABLE_TOOLS`)

- **Goal.** Zero `tools_changed` breaks inside a stage visit; the withholding behaviour
  stays, as a refusal at `wrap_tool_call` that ends the turn with the answer-only notice
  (BA step 2, Part 22.1 #7 unchanged: the parallel/linear toggle is untouched).
- **Evidence.** 158 changes on brief_medium; I3 names the mechanism (tools are in the
  system prompt).
- **Files.** `src/app/agents/settled_answer.py:2086-2140` (keep `request.tools` as
  bound; move each drop into a refusal map consulted by `wrap_tool_call`),
  `src/app/tools/research.py:94-104` (same: refuse docs/web calls over the share with the
  existing "share spent" wording), `src/app/agents/thinking.py` + `settled_answer.py:
  1746-1771` (the thinking toggle after a lost reply becomes a **tail instruction plus a
  lower `max_tokens`** when the model's template renders `enable_thinking` into the
  prefix; stays a template kwarg when it only changes the generation prompt),
  `src/app/agents/gathering.py:142` (a call routed to another model is its own thread
  id, so it never counts as a break of the stage's thread).
- **Steps.** (1) Refusal map. (2) `ResearchShare` to refusal. (3) Tool order asserted
  stable across a visit (MCP tools sorted by name at bind time). (4) Per-model check of
  what `chat_template_kwargs.enable_thinking` does to the rendered prompt (Qwen3-family
  templates put the empty think block in the generation prompt, i.e. the tail; confirm on
  the owner's served model with `/apply-template` before choosing step 4's branch).
- **Tests.** `tests/test_a_withheld_tool_does_not_change_the_tool_list.py` (BA, fails on
  old code), `tests/test_a_spent_research_share_refuses_instead_of_unbinding.py`,
  `tests/test_tool_order_is_the_same_on_every_call_of_a_visit.py`.
- **Acceptance.** `prefix_break_reason.tools_changed` = 0 on tasks-api; the loop
  counters (`layer_tool_withheld`, stall rules) unchanged in behaviour.
- **Effort.** M.  **Depends on.** PX.1.

<a id="plan-px-3"></a>
#### PX.3 The clock and the request text leave the visit-stable zone — P1, group 2 (`CANONICAL_MEMORY`)

- **Goal.** Parallel siblings of one fan-out share the whole system message and the
  whole project memory; retries share it with the first attempt.
- **Evidence.** Break 4 (clock) and 5 (request-dependent file order). On a 2-slot server
  running 6 builders the slots are reassigned between siblings; today every reassignment
  is a full re-prefill of ~60k tokens even though five sixths of the bytes are the same
  files in a different order.
- **Files.** `src/app/agents/project_snapshot.py:111, 150` (drop the clock, or move the
  "as of" line to the tail digest), `src/app/agents/project_memory.py:136-155` (the
  ranking loses the request-dependent `-1` group: order = documents → application/config
  → other docs → tests → records, ties by path, **independent of the request**; the
  files the request names become one line *after* the memory, "start with: a, b, c",
  which is the same pointer the held-files line already gives), `:163-203` (`digest_of`:
  render the specification digest **after** the canonical code block, so the
  request-dependent section choice sits behind the shared bytes), `src/app/agents/
  carry_over.py:91` (the carry-over note moves after the request, before the transcript),
  `src/app/agents/where_things_stand.py:144-149` (the block stays before the request —
  it is per sprint, not per call — but is rendered once per sprint and reused byte-for-
  byte by every builder of the wave; today it is rendered per call site).
- **Steps.** (1) Clock out. (2) Canonical ranking behind a switch; keep the old order
  as the fallback for one measured pair. (3) `where_things_stand` cached per sprint.
  (4) Carry-over after the request.
- **Tests.** `tests/test_two_siblings_of_one_wave_share_the_same_memory_bytes.py`
  (fails on old code: different order), `tests/test_the_snapshot_carries_no_clock.py`,
  `tests/test_a_retry_shares_the_first_attempt_s_opening_bytes.py`.
- **Acceptance.** `prefix_break_reason.snapshot_clock + memory_order` = 0; on a 2-slot
  server with a 6-way fan-out `cached_token_share` for builders rises (expected: the
  memory block, ~40% of the request per BF's `prompt_block_share_project_memory`, becomes
  shared). Quality guard: the AQ limited-memory behaviour (served files first within the
  budget) is kept by the rank order, so no file that was in memory before falls out.
- **Effort.** S–M.  **Depends on.** PX.1.

<a id="plan-px-4"></a>
#### PX.4 The transcript is append-only — P1, group 2 (`APPEND_ONLY_HISTORY`)

- **Goal.** No stored message changes after the call that produced it.
- **Evidence.** Breaks 6 and 7. Argument truncation above 0.5 × ceiling (i.e. the second
  half of every long stage, where fix stages live) shortens a different message on each
  call; the reasoning carry rewrites every tool-calling assistant message when a prose
  reply lands.
- **Files.** `src/app/agents/role_agent.py:422-426` (replace the sliding
  `truncate_args` with store-time truncation: when a tool result lands, the stored call's
  arguments are shortened to `MAX_TOOL_ARG_CHARS` **once, immediately**, since the file is
  on disk the moment the call returns — the comment at `:420` already says so; the
  `keep` window then has nothing to do), `src/app/models/__init__.py:617-665`
  (`with_the_reasoning_carried`: carry into the **stored** assistant message once, at
  the time the reply is stored, instead of re-deriving the set on every call; or carry
  only into the last assistant message as a tail override), `src/app/agents/
  settled_answer.py:1807-1822` (`_with_cut_replies_shortened` applied at store time for
  the same reason; it is already deterministic).
- **Steps.** (1) Store-time truncation. (2) Reasoning carry persisted or tail-only (A/B
  on one lost-reply-heavy stage: the carry exists to stop re-reasoning, so the tail
  variant must be shown not to raise lost replies). (3) Cut-reply shortening at store
  time.
- **Tests.** `tests/test_a_stored_message_never_changes_after_its_call.py` (fails on old
  code), `tests/test_long_arguments_are_shortened_once_when_the_result_lands.py`.
- **Acceptance.** `args_truncated + reasoning_carry` = 0; lost replies not up.
- **Effort.** M (deepagents' `truncate_args` is theirs; the store-time version is a
  small middleware of ours and the setting is removed).  **Depends on.** PX.1.

<a id="plan-px-5"></a>
#### PX.5 Steering notes move to the tail — P2, group 1

- **Goal.** A note added mid-stage costs one tail block, not a system-prompt rewrite.
- **Evidence.** Break 2. Dynamic agent-instruction injection is an owner feature and
  stays; only its position changes. Plugin/framework instructions stay in the system
  message (they are stable per run).
- **Files.** `src/app/plugins/middleware.py:583-606` (split `_with_instructions`:
  plugin text stays; steering text becomes a tail user message in the same wording,
  after the digest), `src/app/server/steering.py` (unchanged).
- **Tests.** `tests/test_a_steering_note_does_not_change_the_system_message.py` (fails
  on old code), existing steering tests pass unchanged.
- **Acceptance.** `steering_changed` = 0.
- **Effort.** S.  **Depends on.** —.

<a id="plan-px-6"></a>
#### PX.6 Compaction that keeps what it can — P2, group 2

- **Goal.** After compaction the run-stable zone and the memory are byte-identical to
  before (they are today — verify with PX.1), and the server can recover the transcript
  tail by position shift.
- **Evidence.** Break 8; llama.cpp `--cache-reuse N` reuses chunks ≥ N tokens found at a
  different position by RoPE-shifting them, which is exactly the shape a compacted
  transcript has (head replaced, tail unchanged).
- **Files.** `src/app/agents/compaction.py:218-255` (the summary head message is placed
  **after** the memory, which the memory middleware already does by prepending — assert
  it with a test), `docs/HANDOVER.md` §5 (owner advice: `--cache-reuse 256`; nothing in
  code).
- **Tests.** `tests/test_compaction_leaves_the_opening_bytes_unchanged.py`.
- **Acceptance.** `compaction` breaks carry only the summary head's cost; with
  `--cache-reuse` advised and adopted by the owner, uncached tokens on the first call after
  compaction fall from "whole context" to "memory + summary".
- **Effort.** S.  **Depends on.** PX.1; owner for the flag.

<a id="plan-px-7"></a>
#### PX.7 Slot affinity and the pause (BA steps 3–4) — P2, group 2 (`SLOT_AFFINITY`)

- **Goal.** One stage visit keeps one slot; side calls do not evict it; a visit paused at
  an approval gate comes back to a warm slot when the server allows.
- **Evidence.** Break 9. llama-server picks the slot by prefix similarity and evicts LRU;
  a thread that waits behind a compaction summary or a gathering call can come back to
  find its slot reused.
- **Files.** `src/app/models/__init__.py` (`extra_body.cache_prompt = true` always —
  explicit, so a server whose default differs still caches — and `extra_body.id_slot =
  hash(inner thread id) mod total_slots` when `server_profile.slots` is known),
  `src/app/graph/workflow.py:1194-1209` (side calls — compaction summariser, gathering,
  keyword extraction — take the slot of the thread they serve, never a free one; the
  fan-out rule "fan-out = server slots" extends to every fan-out as BA step 3 says, the
  toggle untouched), `src/app/models/server_profile.py` (record whether `/slots` answers
  and whether save/restore is enabled — `--slot-save-path` is not in `/props`, so the
  probe is a `GET /slots` plus one `POST /slots/0?action=save` only **with the owner's
  consent**, since it writes a file on the owner's disk), `src/app/agents/approval.py`
  (save before a gate wait longer than N minutes, restore on resume, when enabled).
- **Steps.** (1) `cache_prompt` explicit. (2) `id_slot` affinity. (3) Side calls follow
  their thread. (4) Save/restore around gates, advisory first.
- **Tests.** `tests/test_a_visit_s_calls_carry_the_same_slot.py` (fails on old code: no
  field), `tests/test_a_side_call_takes_its_thread_s_slot.py`.
- **Acceptance.** `evicted` share of uncached tokens −50% on a 2-slot server with
  `HARNESS_MAX_PARALLEL=6`.
- **Effort.** M.  **Depends on.** PX.1, PX.3.

<a id="plan-px-8"></a>
#### PX.8 The code-base snapshot store (the owner's side-car) — P3, decision gate

- **Goal.** Decide, from PX.1's numbers, whether a content-addressed store of saved slot
  states (key = hash of the canonical run-stable + visit-stable zones; value = the file
  `/slots/:id?action=save` writes) is worth building beside llama-server.
- **Evidence.** It is a thin orchestration layer (restore the snapshot whose key matches
  the next request's prefix hash, LRU on disk), a few hundred lines, and it only pays
  when the same prefix is **revisited after eviction**: several sprints of builders over
  the same code base on a server with fewer slots than threads. KV size is the limit —
  per token it is 2 × layers × kv-heads × head-dim × bytes (take layers and kv-heads
  from the model card or `/props`; q8_0 KV halves it), so a 60k-token memory is
  gigabytes per snapshot and only a handful fit on fast disk.
- **Gate.** Build only if, after PX.2–PX.7 are on, `uncached_tokens_by_reason.evicted`
  is still ≥ 15% of input tokens on brief_medium. If it is below, close the item with the
  measurement. The owner's launch flags are never changed by the harness; the store
  would be a separate process with its own flag advice.
- **Effort.** M if built.  **Depends on.** PX.1, PX.7, owner.

### 9.3 Order and placement in Part 21

PX.1 (measure, group 1) → PX.5 (steering, group 1, no behaviour change) → PX.3 →
PX.2 → PX.4 → PX.6 → PX.7 → PX.8 (decision). PX.2–PX.4 and PX.7 are group 2 switches
(`STABLE_TOOLS`, `CANONICAL_MEMORY`, `APPEND_ONLY_HISTORY`, `SLOT_AFFINITY`) measured as
one arm after the AY arm, since they change bytes every stage sees. The BA row in
Appendix 4's ledger becomes "absorbed by PX (Appendix 9)"; BA's acceptance
(`cached_token_share` 0.73 → ≥ 0.85, effective input tokens −40%) is PX's.

### Appendix 9 rows (Implementation Progress Ledger continuation)

| Item | Priority | Status | Notes |
|---|---|---|---|
| PX.1 prefix-break reasons | P1 | BUILT 2026-10-22, measurement only (no switch: it changes no request) - `app/observability/prefix_breaks.py`, KPIs `prefix_break_<reason>` and `uncached_tokens_<reason>`, read from the existing `model_request` records. Measured post hoc on Measure pair 2 run 2 and pair 3 run 1: uncached input by first break - tools changed 30-31%, first call of a stage 26-28%, opening messages changed 18-25%, new messages 18-21%, system message 1-2%, history rewritten 1% | after BF (done) |
| PX.2 stable tools per visit | P1 | BUILT 2026-10-22 behind `STABLE_TOOLS` (off): `app/agents/stable_tools.py`; the settled-answer guards (read tool, a repeated tool, looking tools, answer-only) and the research share leave the bound list as it is, the withheld names go to the existing `wrap_tool_call` refusal and the call is told which are refused. Thinking-toggle and MCP sort (steps 3-4) not yet | absorbs BA step 2; the largest measured break |
| PX.3 canonical memory, no clock | P1 | BUILT 2026-10-22 behind `CANONICAL_MEMORY` (off): `app/agents/canonical_memory.py` - the snapshot says "as this stage started" instead of the time, the memory's order no longer puts the request's files first, and a document digested by the request's words follows the code. Steps 3-4 (where-things-stand cached per sprint, carry-over after the request) not yet | second largest measured break |
| PX.4 append-only transcript | P1 | NOT STARTED (group 2, `APPEND_ONLY_HISTORY`, owner 2026-10-22: build now, off) | measured 1% of uncached input on tasks-api |
| PX.5 steering at the tail | P2 | BUILT 2026-10-22 behind `STEERING_AT_THE_TAIL` (off): `app/plugins/steering_at_the_tail.py`; plugin instructions stay in the system message, the owner's direction becomes the call's last message in the same words | system-message changes measured 1-2% |
| PX.6 compaction keeps the opening | P2 | NOT STARTED (group 2) | `--cache-reuse 256` is owner advice |
| PX.7 slot affinity, save/restore | P2 | NOT STARTED (group 2, `SLOT_AFFINITY`, owner 2026-10-22: build now, off) | absorbs BA steps 3–4 |
| PX.8 snapshot side-car | P3 | DECISION GATE | build only on PX.1's eviction share |

## E. Earlier plans, merged into this document on 2026-10-19

Two separate plan documents predate the appendices above. They are kept
here in full, so the history and the reasons stay in one place, and code
comments that cite "the hardening plan" still resolve. Status was
re-assessed on 2026-10-19 against the code and the ledger. Where an item
was later absorbed by a lettered initiative, the row points to it.

<a id="plan-e1"></a>
### E1. Harness Improvement Plan (October 2026; formerly `docs/harness-improvement-plan.md`)

Status of its items (2026-10-19):

| Item | Status | Where it went |
|---|---|---|
| R1–R7 (harness-owned files, auto decisions, endpoint handling, pack release files, dead code, docs cleanup, language services) | DONE | E1 §2 below; ADR-0004 |
| Sprint cap, batch remediation, file ownership in prompts, conditional reviews, untested-criteria disputes | DONE (`0b28a91`, `2702c9d`) | E1 §2 below |
| B1 cross-file checks beyond JavaScript | PARTLY | K.6 / AW (stack-shaped checks as pack data) |
| Part III 1 coverage omit filter | PARTLY | — |
| #1 Acceptance suite static linting before lock | DONE in substance | D, J.1 (suite integrity checks before lock, `assertions_that_do_not_exist`) |
| #2 Self-learning engine | SUPERSEDED → DONE | AI, AT (owner-approved, signed lesson store) |
| #3 Adaptive workflow complexity (lean scopes) | SUPERSEDED → DONE | fast delivery (ADR-0007), sprint cap; AZ for complex scopes |
| #4 Tree-sitter repository map | OPEN | E2 pillar 10 gate; AQ (repeated reads) measures first |
| #5 Fast-fail test timeouts | DONE | JavaScript packs set 3 s action/expect timeouts (`stacks/packs/_javascript.py`) |
| #5 Persistent sandbox session | OPEN | BE (one sandbox container per run) |
| #6 Failure packets with the page | DONE in substance | each failing test carries the page it failed on (`docs/PRODUCT.md` §8) |
| #7 Cross-run regression tracking | DONE | W.4 (KPI ledger, 1.5× flag) |
| B7 measured chars per token, B15 digest budget | OPEN, low | BJ (one input budget) |

**What this is.** The master improvement plan for the LangGraph / Deep Agents harness. It incorporates lessons learned from live benchmark runs, audits the status of previous plans (Parts I–III and the 2026-10-04 plan), conducts a comparative architectural benchmark against leading open-source agentic coding frameworks (SWE-agent, OpenHands / OpenDevin, Aider, DeepSeek harness), and lays out an actionable implementation roadmap prioritized by measurable ROI and time savings.

---

#### 1. Comparative Architectural Benchmark: Current Harness vs. SOTA Frameworks

To achieve consistent, production-grade performance and reduce benchmark execution times from 2–3+ hours down to 30–60 minutes for standard applications, the harness was evaluated against industry state-of-the-art (SOTA) agentic coding systems:

| Dimension | Current Harness | Leading SOTA Systems (SWE-agent, OpenHands, Aider, DeepSeek) | Architectural Gap & Opportunity |
|---|---|---|---|
| **Organizational Topology** | Rigid 14-stage corporate workflow (Architect → Arch Review → QA Author → QA Review → Scrum Master → Tech Lead → Dev → Test → Code Review → Acceptance → Defect Remediation → Milestone Review → Sprint Summary). 400–600 model calls per run. | **Dynamic / Adaptive Topology** (Aider, OpenHands): Single Planner + Executor loop, or lean Architect + Coder pair. Specialized roles invoked dynamically only when needed. Benchmark runs finish in 15–40 steps. | **High**: Simple applications (e.g. 10–16 criteria) suffer massive roundtrip latency. The harness should dynamically collapse stages for small/medium scopes. |
| **Acceptance Suite Verification** | Suite authoring produces tests with un-awaited promises or CSS selectors. Flaws trigger runtime crashes after development, invoking the **Acceptance Dispute Engine** (reopening suite for 3+ rounds, costing 30–45 mins). | **Pre-Emptive Static AST Validation** (SWE-bench / DeepSeek): Strict linters, AST tree-sitter checks, and floating-promise detectors validate tests *before* suite is accepted or executed. | **Critical (P0)**: Catch test defects statically before locking. Eliminates the multi-round dispute loop entirely. |
| **Context & Repo Representation** | Flat file lists in workspace digest (`MAX_FILES = 40`). High redundant read rate (12–18% of reads spent re-inspecting files). Agents frequently call `read_file` to find symbol definitions. | **Tree-Sitter RepoMap** (Aider): Dense topological map of exported symbols, signatures, and classes generated in <1,000 tokens using Tree-Sitter and PageRank. | **High (P1)**: Provide symbols and signatures in prompt context, slashing redundant tool calls and token spend. |
| **Execution Latency & Sandboxing** | Isolated command execution per tool call; default Playwright locator timeout of 30s causes failing test runs to burn 5–8 minutes per round. | **Persistent Daemon & Fast-Fail Timeouts** (OpenHands, SWE-agent): Persistent shell session with sub-second turnaround; strict 3–5s timeouts on UI element checks. | **High (P1)**: Fast-fail on UI mismatches; persist sandbox environment. |
| **Cross-Run Learning & Memory** | **Tabula Rasa**: Cross-run memory was previously dropped (Phase 4) due to prompt-injection concerns. Agents repeat known framework gotchas (e.g., missing `await` on custom helpers, unconfigured JSDOM globals) on every single run. | **Deterministic Skill & Case Distillation** (Voyager, Reflexion, ExpeL): Post-run reflection distills verified traps, patterns, and templates into deterministic, injection-safe rule stores. | **Critical (P0)**: Implement a Self-Learning Engine that extracts verified rules from Decision Records and saves them into Stack Pack knowledge bases. |

---

#### 2. Audit of Existing Plan Items (Status as of October 2026)

Each item from previous plans was re-verified directly against the codebase:

##### Completed & Implemented Items
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

##### Partially Implemented Items
- **B1 — Cross-File Checks Beyond JavaScript**:
  - *Current Status*: Size counting and CSS/TS/Pyright language checks exist. Multi-file symbol references and imports for Go, Rust, and polyglot setups are still heuristics.
  - *What Needs to be Done*: Extend Tree-Sitter AST symbol resolution across all supported stack languages.
- **Part III 1 — Coverage Omit Filter**:
  - *Current Status*: Per-file omit list exists, but test runner still counts imports inside `tests/` as caller references.
  - *What Needs to be Done*: Filter out `tests/` directory imports when verifying whether application modules are referenced by production code.
- **Pre-Emptive Acceptance Test Linting**:
  - *Current Status*: Some regex and method checks exist (`locators_that_do_not_exist`, invalid role checks), but tests can still be locked with un-awaited promises on async helper functions and brittle CSS selectors.
  - *What Needs to be Done*: Implement AST-level floating-promise checking and CSS selector banning in `app/acceptance/suite.py` before locking (see P0 below).

##### Open / Retained Items
- **B7 — Measured Chars Per Token**: Low priority; context compaction has prevented context overflows on current models.
- **B15 — Digest Budget for Large Codebases**: Active when repository exceeds 40 files; small benchmark apps remain well under the ceiling.
- **Fast-Fail on Test Timeouts**: Reduce Playwright default locator timeouts to 3–5 seconds to prevent failed assertions from waiting 30 seconds each.

---

#### 3. Prioritized Implementation Plan (Ranked by ROI & Value)

##### Tier 1 (P0): Eliminating the Longest Failure Loops (Expected Savings: 60–90 mins)

###### 1. Pre-Emptive Acceptance Suite Static Linting (AST Validation Before Locking)
- **Problem**: In live runs, QA authoring frequently generates Playwright tests with async helper calls missing `await` (e.g. `const item = getTaskItemByTitle(...)` where `item` is a Promise, causing `TypeError: item.getByRole is not a function`) or using brittle CSS selectors (e.g. `locator('input[type="checkbox"]').filter({ hasText: 'Done' })`). Because these flaws are only detected when the product runs, they trigger the **Acceptance Dispute Engine** (DR-5, DR-7), reopening the locked suite and forcing multiple QA authoring rounds that consume 30–45 minutes of model time.
- **Solution**:
  1. Add an AST-based static validator in `app/acceptance/suite.py` that runs during `suite.gaps()` / `acceptance_review`:
     - **Floating Promise Detection**: Parse test files using Tree-Sitter or ESLint to verify that calls to async helper functions are awaited before method chaining.
     - **Locator Contract Enforcement**: Reject raw CSS tag selectors (`input[type=...]`, `div.task`) in favor of accessible queries (`getByRole`, `getByLabel`, `getByText`).
     - **API Method Validation**: Verify all chained locator methods exist on Playwright `Locator` / `Page` prototypes.
  2. If any test violates these rules, reject it immediately during `acceptance_author` rounds with actionable feedback before the suite can ever be locked.
- **Expected Impact**: Completely eliminates acceptance suite dispute reopenings, saving 30–45 minutes per run.

###### 2. Self-Learning Agents: Deterministic Distillation & Stack-Pack Knowledge Store
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

###### 3. Adaptive Workflow Complexity (Dynamic Fast-Path for Lean Scopes)
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

##### Tier 2 (P1): Tool Latency & Context Efficiency (Expected Savings: 25–40 mins)

###### 4. Tree-Sitter Repository Map (RepoMap) & Context Compaction
- **Problem**: Agents exhibit a 12–18% redundant read rate, repeatedly invoking `read_file` or `ls` to discover what functions or classes exist across files.
- **Solution**:
  1. Integrate an Aider-style Tree-Sitter RepoMap in `app/analysis/project_memory.py`:
     - Extract all declarations, exported functions, classes, and types with their parameter signatures.
     - Format as a compact hierarchical outline (~500–800 tokens).
  2. Include the RepoMap in the workspace digest so all specialists have immediate visibility into the complete codebase structure without executing exploratory tool calls.
- **Expected Impact**: Reduces redundant reads to <5%, saving 10–15 minutes and ~20% token overhead.

###### 5. Persistent Sandbox Sessions & Fast-Fail Test Timeouts
- **Problem**: Each `run_terminal_command` spawns an isolated subprocess. When Playwright tests fail to find an element, Playwright's default 30-second timeout per test causes a single acceptance run of 16 tests to take 5–8 minutes.
- **Solution**:
  1. Configure harness Playwright templates with aggressive local timeouts:
     - Set `actionTimeout: 3000` (3 seconds) and `expect: { timeout: 3000 }`.
     - Fast-fail immediately if the base URL / server returns connection refused or 404.
  2. Keep a persistent container shell session for sub-second command dispatch.
- **Expected Impact**: Slashes acceptance test execution time from 5–8 minutes down to 10–20 seconds per run, saving 15–20 minutes across multiple test rounds.

---

##### Tier 3 (P2): Remediation Precision & Observability (Expected Savings: 15–20 mins)

###### 6. Targeted Test-Driven Defect Remediation with DOM Diffs
- **Problem**: During defect remediation, specialists receive general error messages but lack the exact runtime failure state, leading to speculative code edits.
- **Solution**:
  1. When an acceptance test fails, extract the Playwright call log, the failing assertion line, and the simplified HTML/accessibility snapshot of the page at the exact moment of failure.
  2. Inject this structured failure packet directly into the defect remediation prompt, instructing the agent to fix the specific attribute or event handler.
- **Expected Impact**: Increases first-attempt defect remediation success rate from ~60% to >90%, eliminating second and third remediation cycles.

###### 7. Automated Cross-Run Benchmark Regression Tracking
- **Problem**: Run timing and performance regressions are currently audited manually by checking timing logs after runs conclude.
- **Solution**:
  1. Add an automated regression reporter in `scripts/loop/audit_live.py`:
     - Compare current run metrics (total wall-clock time, model calls per stage, failure rate, redundant read percentage) against moving averages of the last 5 clean runs.
     - Highlight any stage whose call count or duration exceeds 1.5x the baseline.
- **Expected Impact**: Immediate visibility into performance regressions during live monitoring.

---

#### 4. Execution Roadmap & Milestones

| Phase | Initiative | Primary Target Modules | Est. Time Savings | Status |
|---|---|---|---|---|
| **Phase 1 (Immediate)** | Pre-Emptive Acceptance Suite AST Linting | `src/app/acceptance/suite.py`, `src/app/acceptance/requests.py` | 30–45 mins | Ready for implementation |
| **Phase 1 (Immediate)** | Fast-Fail Test Timeouts (3s Playwright locators) | `src/app/stacks/`, `src/app/tools/sandbox.py` | 10–15 mins | Ready for implementation |
| **Phase 2 (Near-Term)** | Self-Learning Engine: Deterministic Distillation & Stack Pack Rules | `src/app/learning/`, `src/app/stacks/seed.py` | 20–30 mins | Architecture defined |
| **Phase 2 (Near-Term)** | Adaptive Workflow Complexity (Lean Scope Fast-Path) | `src/app/graph/workflow.py`, `src/app/agents/scrum_master.py` | 30–45 mins | Architecture defined |
| **Phase 3 (Follow-Up)** | Tree-Sitter RepoMap in Workspace Digest | `src/app/analysis/project_memory.py`, `src/app/analysis/digest.py` | 10–15 mins | Design ready |
| **Phase 3 (Follow-Up)** | Targeted Defect Remediation with DOM Snapshots | `src/app/acceptance/failures.py`, `src/app/agents/specialists.py` | 10–15 mins | Design ready |

---

#### 5. Development Invariants & Standards

- **Agility without Quality Compromise**: All optimizations preserve the owner's core features (acceptance test definition of done, CI gates, code review, dynamic instructions, parallel/linear modes, decision records).
- **Technology-Agnostic Rules**: Stack-specific rules live strictly in stack packs (`src/app/stacks/`); harness graph logic remains framework- and product-agnostic.
- **Deterministic Self-Learning**: Cross-run learning must use structured schema distillation (traps, flags, linter rules) rather than unstructured prompts to prevent drift and injection risks.
- **Test-First Verification**: Every harness optimization must include a regression test proving the failure on old code before deployment.

---

<a id="plan-e2"></a>
### E2. High-steering specification (2026-10-09; formerly `docs/high-steering-software-company-implementation.md`)

The principles behind this specification are recorded as ADR-0006 in
`docs/architecture-decisions.md`. Its comparison of other harnesses (its
§2) is in `docs/research-findings.md`, Part R6. Its diagnosis, lifecycle,
pillars, roadmap and invariants follow.

Status of its pillars (2026-10-19):

| Pillar | Status | Where it went |
|---|---|---|
| 1 Pre-lock suite static and load gate | DONE in substance | suite integrity checks before lock: tests broken by their own code, Playwright's refusals of a spec's shape, tests the runner never ran (`docs/PRODUCT.md` §8); J.1 vacuous-green gate |
| 2 Self-contained work orders | DONE in substance | work orders carry files, interfaces, steps and test cases; fast mode drafts each file from the specification (ADR-0007); AZ adds slice scope |
| 3 Context-anchored editing, exact paths | DONE | `edit_artifact` find/replace with lenient whitespace (G); P.1 demoted `replace_lines`; workspace path middleware |
| 4 Fast-fail timeouts, readiness polling | DONE (timeouts) | JavaScript packs: 3 s action/expect |
| 5 Self-learning by distillation | DONE (redesigned) | AI, AT |
| 6 Dual-track steering by model capability | PARTLY | `fitness` probe, two tiers (ADR-0008); BD, BH |
| 7 Fix-before-exit (parse refusal, diagnostics) | DONE | parser refusal at every write; language-service diagnostics as notes, and as defects at CI |
| 8 Consolidated role-based remediation | CHANGED | one fix per defect, run as a fan-out (`defect_fix_worker`), clustered by root error (L.1); AY bounds each defect's cycle |
| 9 Curated context bus | NOT BUILT | project memory and carry-over cover most of it; BJ budgets it |
| 10 Code and test index | NOT BUILT (gated on measurement) | AQ measures repeated reads first |

**What this is.** The architectural specification and engineering blueprint for the LangGraph / Deep Agents harness that builds software products from a brief. It establishes how to transform the harness into an autonomous **Software Company** capable of delivering production-grade, tested, and verified software in **30–45 minutes** (down from 2–3 hours), with high reliability across both **local / lower-tier models (8B–32B parameters)** and **frontier models (Claude 3.7 Sonnet, GPT-4o, DeepSeek-V3/R1)**.

---

#### 1. Executive Summary & Empirical Diagnosis

##### 1.1 The Benchmark Reality: 8 Minutes to Build, 114 Minutes of Rework
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

##### 1.2 The Root Cause: The "Locked-In Defect" Catastrophe
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

#### 2. (moved) Comparative research

Now in `docs/research-findings.md`, Part R6.

#### 3. High-Steering Lifecycle Architecture

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

#### 4. Detailed Technical Specifications (The 8 Pillars)

##### Pillar 1: Pre-Lock Acceptance Suite Static & Load Gate
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

##### Pillar 2: Self-Contained Work Orders (Prompt Scaffolding as External Working Memory)
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

##### Pillar 3: Resilient Context-Anchored Editing & Exact Path Validation
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

##### Pillar 4: Measured Test Timeouts & Sandbox Startup Optimization
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

##### Pillar 5: Continuous Self-Learning Engine via Deterministic Distillation
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

##### Pillar 6: Dual-Track Cognitive Steering (Local Models vs. Frontier Models)
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

##### Pillar 7: Immediate In-Stage IDE Linting & Syntax Gate ("Fix-Before-Exit")
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

##### Pillar 8: True Role-Based Consolidated Defect Remediation
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

##### Pillar 9: Curated Context Bus (idea 1, evaluated: GOOD, as a small extension)
- **Verdict**: Sound, but most of it already exists. Work orders (`analysis/work_orders.py`), the workspace digest, the project snapshot, `carry_over.py` (facts, not reasoning, survive a restart) and `stage_memory.py` already pass context to agents. What is missing is one *versioned, role-scoped* record of the facts that must never be lost between stages.
- **Design (proposed)**: a small harness-owned file of typed entries: `requirement`, `decision`, `interface_contract`, `convention`, `known_trap`. Each entry has an id, a source artifact, a version and the roles that need it.
  1. Entries are written only by the harness from harness-owned artifacts (the locked acceptance suite, Decision Records, stack-pack conventions), never from `docs/` text a run can rewrite.
  2. Each stage receives only its slice, with a hard character budget, ranked by role relevance and recency. Over budget: drop lowest rank and name what was dropped.
  3. A trap is added only after the same failure class recurs; stack-specific traps live in the stack pack, not core.
- **Why not a free-form shared memory**: unvalidated notes drift and poison weaker models. Carrying prior *reasoning* between stages was measured and rejected.
- **Success criterion**: fewer repeated tool calls and fewer "contract mismatch" defects against the current baseline on the same brief. **Rollback**: a flag that disables injection; stages fall back to work orders alone.

##### Pillar 10: Code and Test Index (idea 2, evaluated: GOOD if kept bounded)
- **Verdict**: `analysis/project_memory.py` already is a language-agnostic file index (purpose, up to 8 signatures per file, who created or changed each file). The proposal is to extend it, not build a second index.
- **Evidence**: Aider sends a compact repository map (files plus key symbols with signatures, extracted with tree-sitter), ranks it with a graph algorithm when the repository is large, and lets the model request specific files afterwards (https://aider.chat/2023/10/22/repomap.html). This supports an outline plus on-demand reads. The repo's own measurement rejects whole-file inlining (only 13% of reads are whole small files).
- **Delta (proposed)**:
  1. Import and reference edges between files (reuse `analysis/local_imports.py`).
  2. A test-to-criterion-to-file map (reuse `analysis/test_discovery.py` and the acceptance suite) so a defect points at the files and tests involved.
  3. A ranked, size-capped outline per stage, and a read-only `find_symbol` style query tool. Regex extraction stays the fallback where no tree-sitter grammar exists.
- **Gate before building**: measure the current share of read and search calls that return nothing used. Build only if it is large; otherwise the digest already suffices.
- **Rollback**: outline injection behind a flag; the index file is advisory and never blocks a stage.

##### Tiered Steering by Model Capability
Plan-first structure stays for every model, because a short plan before execution helps weaker ones. Steering intensity varies by a *measured* signal, not a model name:
- **Strong tier** (few repeated calls, parses structured output first time): compact work orders, fewer gates.
- **Weak tier** (restarts, repeated identical calls, parse failures): full work order with excerpts and signatures, in-stage syntax gate, tighter retry budget, smaller scopes per stage.
The tier is chosen per stage from `stage_memory` counters, can move up or down mid-run, and never changes the owner's model or settings.

##### Efficiency for Long Runs
Bounded retries and time budgets per stage; stage collapsing for small scopes (exists: `_cap_sprints_for_scope`); one remediation session per role (Pillar 8); and a context budget that stays flat as the project grows (outline, not file dumps).

---

#### 5. Efficiency Model (HYPOTHESES, NOT MEASURED)
> The table below is an estimate built from one run. Every "High-Steering Run" figure is an unverified target. Replace each with a measured value from `scripts/loop/audit_live.py` after the pillar ships, or delete it. Do not quote the 67% figure.


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

#### 6. Prioritized Implementation Roadmap

| Milestone | Deliverables | Target Modules | Value & Impact |
|---|---|---|---|
| **M1: Pre-Lock Acceptance Suite AST & Load Gate** | 1. Module System Matcher (`import` vs `require`).<br>2. Floating promise AST detector.<br>3. `npx playwright test --list` dry-run verification before lock. | `src/app/acceptance/suite.py`<br>`src/app/acceptance/requests.py` | **P0 (Critical)**: Eliminates the 114-minute ESM crash that doomed `run-42b84547`. |
| **M2: In-Stage "Fix-Before-Exit" Syntax Gate** | 1. Hard parse rejection on write tool (`node --check` / `py_compile`).<br>2. Pre-exit diagnostic interception in specialist node. | `src/app/tools/repository.py`<br>`src/app/agents/specialists.py` | **P0 (Critical)**: Resolves syntax errors in 1 turn before defect triage starts. |
| **M3: True Role-Based Consolidated Remediation** | Collapse sequential defect cursor into single consolidated remediation session per specialist role. | `src/app/graph/workflow.py` | **P0 (Critical)**: Cuts 10–18 defect stages down to 1–2 stages, saving 35+ mins. |
| **M4: Measured Fast-Fail Test Timeouts** | Explicit 3s Playwright action/expect timeouts and active sandbox readiness polling. | `src/app/stacks/browser-javascript/`<br>`src/app/tools/sandbox.py` | **P1 (High)**: Reduces test failure wait times from 30s to 3s per test. |
| **M5: Self-Contained Work Orders** | Embed file excerpts and symbol signatures into work-order prompts for local model steering. | `src/app/analysis/work_orders.py`<br>`src/app/agents/technical_lead.py` | **P1 (High)**: Prevents local models from getting lost; cuts redundant reads. |
| **M6: Continuous Self-Learning Engine** | Offline distillation of Decision Records and reverts into `src/app/stacks/heuristics/<pack>.json`. | `src/app/learning/distiller.py`<br>`src/app/stacks/` | **P2 (Strategic)**: Safely distills engineering wisdom across runs. |

---

#### 7. Verification & Safety Invariants

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

---

#### 8. Sources and Open Verification
- Verified: Aider repository map (https://aider.chat/2023/10/22/repomap.html).
- Unverified, treat as hypotheses until sourced: SWE-agent agent-computer interface, OpenHands, persistent sandbox startup, DOM-snapshot failure packets, all runtime-reduction numbers.
- Order of work: measure (read churn, context-miss failures) then Pillars 1, 7, 8, then 9, then 10.

---

<a id="plan-appendix-m"></a>
## Appendix M — Master index of every improvement (2026-10-19)

One row per improvement, taken from the ledger tables above (Appendices 1–4)
and the earlier plans (section E). The link goes to the section that explains
the item: what it changes, why, and the evidence (review findings in
`docs/review-findings.md`, research in `docs/research-findings.md`).

- **Status vocabulary:** DONE (with date and commit), PARTLY, NOT STARTED,
  DROPPED or NOT BUILT (with the measurement or owner decision that stopped
  it), MEASURING, ADOPTED (process rules).
- **Keeping it current:** update the ledger row first, then this index, in
  the same commit. **Every completed fix gets a row here** (owner,
  2026-10-19): plan items in the table below, and fixes found by the loop's
  audits (no plan item of their own) in *M.2 Fixes from the loop's audits* at
  the end, with the commit, in the fix's own commit.

| ID | Improvement (short description) | Priority | Status | Detail |
|---|---|---|---|---|
| J.1 | vacuous-green hard gate | P0 | DONE 2026-10-18 | [J.1](#plan-j) |
| J.4 | `completed_with_gaps` status | P0 | DONE 2026-10-18 | [J.4](#plan-j) |
| J.5 | records cite the verdict | P0 | DONE 2026-10-18 | [J.5](#plan-j-5) |
| K.1 | environment contract to architect/QA | P0 | DONE 2026-10-18 | [K.1](#plan-k) |
| L.3 | dispatch-time re-measure | P0 | DONE 2026-10-18 | [L.3](#plan-l) |
| L.5 | identical-call hard stop | P0 | DONE 2026-10-18 | [L.5](#plan-l) |
| L.6 | final attempt changes strategy | P0 | DONE 2026-10-18 | [L.6](#plan-l-6) |
| Q.4 | write-receipt reconciliation | P1 | DONE 2026-10-18 | [Q.4](#plan-q-4) |
| J.2 | reclassification cap + second opinion | P1 | DONE 2026-10-18 | [J.2](#plan-j) |
| J.3 | release-time per-criterion probe | P1 | DONE 2026-10-18 (Playwright packs) | [J.3](#plan-j) |
| J.6 | terminal-state hygiene | P1 | DONE 2026-10-18 | [J.6](#plan-j-6) |
| K.3 | entrypoint wiring proof | P1 | DONE 2026-10-18 | [K.3](#plan-k) |
| K.4 | dependency-drift gate | P1 | DONE 2026-10-18 | [K.4](#plan-k) |
| K.5 | sandbox install coherence | P1 | DONE 2026-10-18 | [K.5](#plan-k) |
| K.6 | stack-shaped checks as pack data | P1 | DONE 2026-10-19 `503a4f0`, with AW | [K.6](#plan-k-6) |
| L.1 | root-cause clustering | P1 | DONE 2026-10-18 | [L.1](#plan-l) |
| L.2 | file-granular revert | P1 | DROPPED 2026-10-18 (validation) | [L.2](#plan-l) |
| L.4 | judgement escalation after revert | P1 | DONE 2026-10-18 | [L.4](#plan-l) |
| L.7 | validator-first plan repair | P1 | DONE 2026-10-18 | [L.7](#plan-l-7) |
| M-bash | bash-first degraded mode | P3 | NOT STARTED | [M-bash](#plan-m) |
| N | reasoning-budget guardrails | P1 | N.2 DONE 2026-10-18; N.1 measure-first; N.3 premise false | [N](#plan-n) |
| P.1 | demote `replace_lines` | P1 | DONE 2026-10-18 | [P.1](#plan-p) |
| P.2/P.3 | parser-refusal escape | P1 | ALREADY IN CODE (validated 2026-10-18) | [P.2/P.3](#plan-p) |
| P.4 | lookup-tool hygiene | P1 | MOSTLY DONE 2026-10-15 | [P.4](#plan-p-4) |
| Q.1 | route fixes to judgement model | P1 | COVERED by L.4 + `escalate_after()` | [Q.1](#plan-q) |
| Q.2 | procedural test-round reports | P1 | DONE in substance (verified 2026-10-18) | [Q.2](#plan-q) |
| Q.3 | dispute routing + rubric anchoring | P1 | DONE in substance (verified 2026-10-18) | [Q.3](#plan-q) |
| Q-amend | fast-mode diff review flag | P2 | DONE 2026-10-19 `534cbb4`, default off | [Q-amend](#plan-q-amendment) |
| O.5 | stale budget constants | P2 | DONE 2026-10-18 | [O.5](#plan-o) |
| R | duplicate-call elimination | P1 | DONE 2026-10-18 (`3c9c931`) | [R](#plan-r) |
| S | server checklist + health telemetry | P2 | DONE 2026-10-19 `f4a62d6` | [S](#plan-s) |
| T | streaming re-test spike | P2 | DONE 2026-10-19 `97b49d7` (spike passes); rollout is group 2 | [T](#plan-t) |
| U.2 | KPI plumbing | P2 | DONE 2026-10-18 via W.4 | [U.2](#plan-u) |
| U.4 | retention policy | P2 | NOT BUILT 2026-10-18 (owner decision) | [U.4](#plan-u-4) |
| UI Phase 1 | harm removal | P2 | MOSTLY DONE 2026-10-18 | [UI Phase 1](#plan-part-4) |
| UI Phase 2 | structural | P2 | PARTLY DONE 2026-10-18 (owner scope) | [UI Phase 2](#plan-part-4) |
| UI Phase 3 | differentiators | P3 | STEERING DONE 2026-10-18 | [UI Phase 3](#plan-part-4) |
| Part 4 | backend enablers | P2/P3 | NOT STARTED | [Part 4](#plan-part-4-enabler) |
| U.1 | bench corpus additions | P3 | DONE 2026-10-19 `6e98110` | [U.1](#plan-u) |
| U.3 | A/B wiring | P3 | DONE 2026-10-18 (`3d8789f`) | [U.3](#plan-u) |
| V | layer-economics ledger | P3 | MEASURING since 2026-10-18 (`3d8789f`) | [V](#plan-v) |
| K.2 | services provisioning | P3 | OPTION A DONE 2026-10-18 (owner: embedded first) | [K.2](#plan-k) |
| W.1 | bench-brief integrity rule | P0 | DONE 2026-10-18 (`a98d9ec`) | [W.1](#plan-w) |
| W.2 | post-P0 baseline runs | P0 | DONE 2026-10-19 (3 of 3 scored) | [W.2](#plan-w) |
| W.3 | toggles through compose + config unification | P0 | DONE 2026-10-18 (`54ab3bd`) except `/props` defaults | [W.3](#plan-w) |
| W.4 | per-run KPI JSON + cross-run ledger + regression flag | P0 | DONE 2026-10-18 (`bdc464c`) | [W.4](#plan-w) |
| W.5 | ledger rows for Initiatives A–I; correct U.2 row | P0 | DONE 2026-10-18 | [W.5](#plan-w) |
| A | design tokens seeded by pack | pre-ledger | DONE 2026-10-18 (owner decision) | [A](#plan-a) |
| B | procedural visual/layout audits | pre-ledger | DONE 2026-10-19 `864bdd6` | [B](#plan-b) |
| C | contract-strict interface extraction | pre-ledger | DONE 2026-10-18 | [C](#plan-c) |
| D | pre-execution linter / assertion normalizer | pre-ledger | DONE in substance | [D](#plan-d) |
| E | narrow single-file work orders | pre-ledger | DONE 2026-10-18 (owner decision), MEASURE over 2 runs | [E](#plan-e) |
| F | root-crash / load-error gate | pre-ledger | DONE | [F](#plan-f) |
| G | lenient whitespace in `edit_artifact` | pre-ledger | DONE 2026-10-19 `f7dc835` | [G](#plan-g) |
| H | pre-flight verification before a fixer | pre-ledger | DONE | [H](#plan-h) |
| I | reasoning budget governor | pre-ledger | DONE | [I](#plan-i) |
| X.1 | tool-name/offer test + four prompt fixes | P0 | DONE 2026-10-18 (`5c74429`) | [X.1](#plan-x) |
| X.2 | verdict-semantics test (`blocked`) | P0 | DONE 2026-10-18 (`3af2de9`) | [X.2](#plan-x) |
| X.3 | mode-rendered tool descriptions | P1 | DONE 2026-10-18 (`9aaaaf4`) | [X.3](#plan-x) |
| X.4 | prompt diet + prompt-size KPI | P1 | DONE 2026-10-18 (`8cacab9`), partly | [X.4](#plan-x) |
| M.1 | probe-time capability detection | P1 | DONE 2026-10-18 (`adcc719`), narrowed | [M.1](#plan-m) |
| M.2 | control-plane `response_format` where supported | P1 | DROPPED 2026-10-18 (premise false here) | [M.2](#plan-m) |
| M.3 | sampling presets per family | P1 | DROPPED 2026-10-18 (owner rule) | [M.3](#plan-m) |
| O.1 | (amended) spec excerpt keeps every section | P1 | DONE 2026-10-18 (`b04b688`) | [O.1](#plan-o) |
| O.2 | effective context ceiling | P1 | DONE 2026-10-18 (`adcc719`) | [O.2](#plan-o) |
| O.3 | / AA prefix-cache layout | P1 | DONE 2026-10-18 (`d2c48b2`, `58f3bfa`) | [O.3](#plan-o) |
| O.4 | / Z compaction | P1 | NOT BUILT 2026-10-18 (measured) | [O.4](#plan-o) |
| AB | fan-out = server slots | P1 | DONE 2026-10-18 (`adcc719`) | [AB](#plan-ab) |
| M.4–M.6 | reasoning policy, arg-fit map, quant advisory | P2 | DONE 2026-10-19 `0015cd1` for M.5/M.6; M.4 is group 2 | [M.4–M.6](#plan-m) |
| Y | edit-ACI calibration bench + architect/editor option | P1 | MEASURED 2026-10-18, no change | [Y](#plan-y) |
| AC | deterministic gating of reviews/test agent; check memoisation | P1 | DONE in substance / AC.3 DROPPED (measured 2026-10-18) | [AC](#plan-ac) |
| AD | measure at settlement | P0 | DONE 2026-10-18 (`e8593db`) | [AD](#plan-ad) |
| AE | one cannot-pass list; gaps sources; release re-checks | P0 | DONE 2026-10-18 (`d3962eb`, `372ff53`) | [AE](#plan-ae) |
| AF | mutation probe for suite strength | P2 | DONE 2026-10-18 (redesigned) | [AF](#plan-af) |
| AG | capability tiers at intake + per-pack coverage field | P1 | DONE in substance 2026-10-18 (`115282c`) | [AG](#plan-ag) |
| AH.1 | honest cost cap + independent hard bound | P1 | DONE 2026-10-18 (`f227a69`) | [AH.1](#plan-ah) |
| AH.2 | retention/deletion contract incl. transcripts | P1 | ALREADY DONE (premise stale) | [AH.2](#plan-ah) |
| AH.3 | reviewer completeness + judgement-model downgrade as gap | P1 | DONE 2026-10-18 (`5c0ba55`) | [AH.3](#plan-ah) |
| AH.4 | execution-readiness check in `loop.sh ready` / run start | P1 | DONE 2026-10-18 (`6dccea0`) | [AH.4](#plan-ah) |
| AI | structured lesson store | P2 | DONE 2026-10-18 (owner approves) | [AI](#plan-ai) |
| AJ | test subprocess lifecycle & async engine cleanup | P1 | ITEM 1 DONE 2026-10-18 (`2f68304`, `4abd460`) | [AJ](#plan-aj) |
| Part 12 | refactor track (V) | P3 | NOT STARTED | [Part 12](#plan-part-12) |
| AK | run-wide budgets persisted | P0 | DONE 2026-10-19 (`a276433`) | [AK](#plan-ak) |
| AL | crash-safe mutation probe | P0 | DONE 2026-10-19 (`b18425e`) | [AL](#plan-al) |
| AM | one owner of the seen digest | P0 | DONE 2026-10-19 (`7207531`) | [AM](#plan-am) |
| AN | measurement correctness | P0 | DONE 2026-10-19 (`f724c00`, `804e29a`) | [AN](#plan-an) |
| AO.1 | AD edge cases | P0 | DONE 2026-10-19 (`094fbfd`) | [AO.1](#plan-ao) |
| AO.2 | M.1 fail-closed semantics | P0 | DONE 2026-10-19 (`dc31ad0`) | [AO.2](#plan-ao) |
| AO.3 | E split parts | P1 | DONE 2026-10-19 (`AO.3` commit) | [AO.3](#plan-ao) |
| AO.4 | X.3 on 3.13 + CI matrix | P1 | DONE 2026-10-19 | [AO.4](#plan-ao) |
| AO.5 | AE reopen precision | P1 | DONE 2026-10-19 `448f182` | [AO.5](#plan-ao) |
| AO.6 | K.2 DATA_DIR for every pack + seed text | P1 | DONE 2026-10-19 | [AO.6](#plan-ao) |
| AO.7 | AH.3 persisted downgrade | P1 | DONE 2026-10-19 | [AO.7](#plan-ao) |
| AO.8 | changes API hygiene + `.git/` write guard | P1 | DONE 2026-10-19 | [AO.8](#plan-ao) |
| AO.9 | R digest precision | P1 | DONE 2026-10-19 `32d0f81` | [AO.9](#plan-ao) |
| AO.10 | repo-rule drift | P1 | DONE 2026-10-19 `28a60ca` | [AO.10](#plan-ao) |
| AP | ledger/handover hygiene | P0 | DONE 2026-10-19 | [AP](#plan-ap) |
| AQ | repeated-read hypotheses | P1 | PARTLY 2026-10-19 | [AQ](#plan-aq) |
| AR | lost-reply probe → N.1 | P1 | DONE 2026-10-19 (server honours only thinking on/off) | [AR](#plan-ar) |
| AS | steering v2 | P1 | DONE 2026-10-19 | [AS](#plan-as) |
| AT | lessons v2 | P2 | DONE 2026-10-19 | [AT](#plan-at) |
| AU | interface contract for every surface | P2 | DONE 2026-10-19 `3d293bb` | [AU](#plan-au) |
| AV | AJ completion | P1 | DONE 2026-10-19 | [AV](#plan-av) |
| AW | K.6 scoped | P2 | DONE 2026-10-19 `503a4f0`; check_families and compiled-language drift DROPPED (premise false) | [AW](#plan-aw) |
| UI-0 | Phase-1 remainder + generated client | P1 | DONE 2026-10-19 `6ffed0f` | [UI-0](#plan-part-15) |
| UI-T1–T3 | theme system (tokens, Plex, codemod, contrast CI) | P1 | DONE 2026-10-19 | [UI-T1–T3](#plan-ui-15-2) |
| UI-P | primitive kit | P1 | DONE 2026-10-19 `d81c1a6` | [UI-P](#plan-ui-15-3) |
| UI-S1/S2 | shell + runs table | P1 | DONE 2026-10-19 `2e25e60` | [UI-S1/S2](#plan-ui-15-4) |
| UI-S4 | control room + 15.5 enablers | P1 | DONE 2026-10-19 `d61c1f8f` | [UI-S4](#plan-ui-15-4) |
| UI-T4–T6 | / S5 appearance + settings | P2 | DONE 2026-10-19 `2bd8155b` | [UI-T4–T6](#plan-ui-15-2) |
| UI-S3 | plan-first intake | P2 | DONE 2026-10-19 `46e65503` | [UI-S3](#plan-ui-15-4) |
| UI-S6 | insights | P3 | DONE 2026-10-19 `c2eca784` | [UI-S6](#plan-ui-15-4) |
| AX | reasoning budget per role | P0 | NOT BUILT (AR: server ignores per-request budgets; advice to the owner) | [AX](#plan-ax) |
| AY | bounded fix cycle | P0 | PARTLY (steps 1-4 built, each behind its own switch; step 5 deferred - project memory already answers a re-read of a file it holds with a pointer, and withholding the read tool also stops a fixer reading what is not in its request; step 6 orders steps 1-4 and waits for their measurement) 2026-10-21: step 1 (one reasoning-free call of at most 1,500 tokens names files, symbols and a hypothesis when the failure names no file or more than 2; a file kept only if it exists, may be written and holds a named symbol) behind `LOCALISE_FIRST` (2026-10-22); step 2 (candidates from the fix's own model when the run has no judgement model of its own) behind `FIX_CYCLE`; step 3 (each write in a linear fix stage followed by the defect's own tests, one line in the write's reply, at most 6 per stage; on a pass it says to answer now and leave other failures to their fixers) behind `VERIFY_AFTER_WRITE` (2026-10-22); step 4 (each attempt's model calls kept on its attempt record; a defect and the one it recurs from that spent 60, `DEFECT_CALLS_AT_MOST`, is left open with its attempts as the diagnosis) behind `DEFECT_CALL_CAP` (2026-10-22); all off | [AY](#plan-ay) |
| AZ | skeleton + slices | P0 | NOT STARTED | [AZ](#plan-az) |
| BA | prefix-cache discipline | P1 | ABSORBED 2026-10-22 by PX (Appendix 9) | [BA](#plan-ba) |
| BB | lead plans in parts | P1 | NOT STARTED | [BB](#plan-bb) |
| BC | stalls end one call earlier | P1 | DONE 2026-10-19 `f47f685` | [BC](#plan-bc) |
| BD | two local tiers + model advice | P1 | NOT STARTED | [BD](#plan-bd) |
| BE | one container per run | P2 | NOT STARTED | [BE](#plan-be) |
| BF | prompt composition record | P1 | DONE 2026-10-19 `ab2afae` | [BF](#plan-bf) |
| BH | model registry + measured edit preference | P1 | PARTLY 2026-10-19 `9339c7d`: registry + measurement done; preference applied waits for group 2 | [BH](#plan-bh) |
| BI | rubric-graded candidates | P2 | NOT STARTED | [BI](#plan-bi) |
| BG.1 | progress/tokens in summary | P1 | DONE 2026-10-19 `b96ee212` | [BG.1](#plan-bg-1) |
| BG.2 | needs-you inbox + notifications | P1 | DONE 2026-10-19 `6ffed0f` | [BG.2](#plan-bg-2) |
| BG.3 | gates as composer, artifact inline | P1 | DONE 2026-10-19 `b96ee212` | [BG.3](#plan-bg-3) |
| BG.4 | rail/work-area/ledger + real tabs | P1 | DONE 2026-10-19 `034c0ce6` | [BG.4](#plan-bg-4) |
| BG.5 | model-server surface | P1 | DONE 2026-10-19 `b96ee212` | [BG.5](#plan-bg-5) |
| BG.6 | fix-loop + sprints structured | P1 | DONE 2026-10-19 `b96ee212` | [BG.6](#plan-bg-6) |
| BG.7 | Audit tab | P2 | DONE 2026-10-19 `51a1589f` | [BG.7](#plan-bg-7) |
| BG.8 | feed: classification and lanes | P2 | DONE 2026-10-19 `2456b9b2` | [BG.8](#plan-bg-8) |
| BG.9 | changes per file + criterion link | P2 | DONE 2026-10-19 `cd5b07ce` | [BG.9](#plan-bg-9) |
| BG.10 | plan-first intake (= UI-S3) | P2 | DONE 2026-10-19 `46e65503` | [BG.10](#plan-bg-10) |
| BG.11 | copy and stage names from the graph | P2 | DONE 2026-10-19 `cd5b07ce` | [BG.11](#plan-bg-11) |
| BG.12 | visual residue | P2 | DONE 2026-10-19 `c6e4fe85` | [BG.12](#plan-bg-12) |
| BG.13 | accessibility and polling | P2 | DONE 2026-10-19 `1522cdf4` | [BG.13](#plan-bg-13) |
| BG.14 | timeline scrubber / replay | P3 | DONE 2026-10-19 `b64ca7e5` | [BG.14](#plan-bg-14) |
| BG.15 | context pressure and throughput | P3 | DONE 2026-10-19 `203bbfac` | [BG.15](#plan-bg-15) |
| BG.16 | palette, shortcuts, cross-run compare | P3 | DONE 2026-10-19 | [BG.16](#plan-bg-16) |
| BJ | one input budget per request | P1 | NOT STARTED | [BJ](#plan-bj) |
| Part 20 | two-run gate rule | P0 (process) | ADOPTED 2026-10-19 | [Part 20](#plan-part-20) |
| BK | release packaging failure is a completion gap | P1 | DONE 2026-10-19 `1d6a4e1` | [BK](#plan-bk) |
| BL | review before a sprint is accepted on its suite alone | P1 | DONE 2026-10-19 `089b8f6` | [BL](#plan-ledger-a4) |
| Part 21 | one implementation order for every open item | P0 (process) | ADOPTED 2026-10-19 | [Part 21](#plan-part-21) |
| Part 22 | consistency review: contradictions, duplicates, do-not-implement, external review coverage | P0 (process) | ADOPTED 2026-10-19 | [Part 22](#plan-part-22) |
| E1 | Harness Improvement Plan (October): RepoMap, persistent sandbox, linting before lock, self-learning, lean scopes | — | mostly DONE or superseded; see its status table | [Section E1](#plan-e1) |
| E2 | High-steering pillars 1–10 (pre-lock gate, self-contained work orders, fix-before-exit, consolidated remediation, context bus, code index) | — | mostly DONE in substance; 9 and 10 not built | [Section E2](#plan-e2) |
| CM.1 | fact parity: reviewers get the builder's environment facts | P0 | BUILT 2026-10-21 behind `SHARED_FACTS`, off until the gate run ends | [CM](#plan-cm) |
| CM.2 | typed decision-and-contract ledger (Pillar 9) | P1 | PARTLY 2026-10-21: the ledger and its interface-contract entries (EF.11), behind `DECISION_LEDGER` | [CM](#plan-cm) |
| CM.3 | blockers and interface decisions routed to the work order that can act | P1 | BUILT: linear mode behind `DECISION_LEDGER` (2026-10-21); the join check behind `INTERFACE_CLASH_CHECK` (2026-10-22): before the CI gate commits a batch, a definition one work order removed that another's file still names is a defect owned by the latter | [CM](#plan-cm) |
| CM.4 | bounded ask-the-specification tool (flag, off by default) | P2 | BUILT 2026-10-22 behind `ASK_SPECIFICATION` (off): retrieval from earlier answers, the specification and the locked criteria first; on a miss one call to the stage's model as the architect, kept in `.harness/answers.json`; 2 per builder stage, 1 per fix, 12 per run | [CM](#plan-cm) |
| CM.5 | reviewers keep a clean context | P0 (process) | ADOPTED 2026-10-20 | [CM](#plan-cm) |
| OS.0–OS.6 | SeaweedFS object storage replacing MinIO (spike, compose profile, config, hardening, read-back, backfill, tests) | P2 | PROPOSED 2026-10-20 | [OS](#plan-os) |
| OS.7 | object-storage docs and operations handover | P2 | PARTLY 2026-10-20 (ADR, research, plan) | [OS](#plan-os) |
| OS.8 | off-site mirror, lifecycle, RustFS re-evaluation | P3 | PROPOSED 2026-10-20 | [OS](#plan-os) |
| RL.1 | deterministic lesson distiller from harness-recorded signals (Pillar 5, bounded) | P1 | BUILT 2026-10-21 behind `LESSON_DISTILLER` (off) | [RL](#plan-rl) |
| RL.2 | lesson uptake: shown-per-call KPI and trigger recurrence after approval | P1 | BUILT 2026-10-21 behind `LESSON_DISTILLER` (off) | [RL](#plan-rl) |
| RL.3 | proposals surfaced in the run report and the lessons UI | P2 | BUILT 2026-10-21 (`loop.sh lessons`) | [RL](#plan-rl) |
| RL.4 | learning judged on hidden test families only | P1 (process) | ADOPTED 2026-10-21 | [RL](#plan-rl) |
| RL.5 | agents editing prompts, packs or harness code; model-written memory | — | REJECTED 2026-10-21 | [RL](#plan-rl) |
| PH.1 | "where things stand" block in every builder and fixer request | P1 | BUILT 2026-10-21 behind `WHERE_THINGS_STAND` (off) | [PH](#plan-ph) |
| PH.2 | structured attempt record per defect for the next fixer | P1 | BUILT 2026-10-21, behind `DECISION_LEDGER`: `Defect.attempts` (stage, files, what it did, how it ended), recorded by the controller on every revert and settlement; the next fixer of the defect - or of one it recurs from - reads them (`ledger.earlier_attempts`). Test: `tests/test_the_next_fixer_reads_each_earlier_attempt.py` | [PH](#plan-ph) |
| PH.3 | builders' decisions must name interface changes; ledger takes them | P1 | BUILT 2026-10-21 behind `INTERFACE_CHANGES_NAMED` (off) | [PH](#plan-ph) |
| PH.4 | builders told the product's start and test state at dispatch | P2 | BUILT 2026-10-21 behind `STATE_AT_DISPATCH` (off) | [PH](#plan-ph) |
| CG.1 | harness-owned code graph per workspace (files, definitions, imports, test→criterion→file, work order→files), incremental by hash | P1 | BUILT 2026-10-21 (`.project-graph.json`) | [CG](#plan-cg) |
| CG.2 | fix requests and reviews get the defect's 1-hop neighbourhood, defining module first | P1 | BUILT 2026-10-21 behind `PROJECT_GRAPH_FIXES` (off) | [CG](#plan-cg) |
| CG.3 | builders get their work order's slice of the graph | P2 | BUILT 2026-10-21 behind `PROJECT_GRAPH_BUILDERS` (off) | [CG](#plan-cg) |
| CG.4 | read-only `where_is` / `who_uses` tool from the graph | P3 | BUILT 2026-10-22 behind `CODE_GRAPH_TOOL` (off) | [CG](#plan-cg) |
| CG.5 | criterion → tests → files view on the run page | P3 (UI) | PROPOSED 2026-10-21 | [CG](#plan-cg) |
| CG.6 | gate: ships only if redundant reads fall (AQ) | process | ADOPTED 2026-10-21 | [CG](#plan-cg) |
| MF.1 | provenance on every run: SHA(s), served model, quantisation, slots, sampling, flags | P0 | BUILT 2026-10-21 (group 1) | [MF](#plan-mf) |
| MF.2 | hidden tests for the gate brief (tasks-api as the medium gate, or a medium hidden suite) | P0 | DECIDED 2026-10-21 (owner) | [MF](#plan-mf) |
| MF.3 | KPIs: wall-clock and tokens per accepted criterion; gate wait | P0 | BUILT 2026-10-21 (group 1) | [MF](#plan-mf) |
| MF.4 | Measure/Fix cycle on a frozen SHA with a stop rule | P0 (process) | ADOPTED 2026-10-21 (owner), from the run after gate run 3 | [MF](#plan-mf) |
| MF.5 | ledger compare with minimum n and spread | P1 | BUILT 2026-10-21 (group 1) | [MF](#plan-mf) |
| MF.6 | `docs/STATE.md` as the only mandatory session read; archive; tokens per fix | P1 | BUILT 2026-10-21 (group 1) | [MF](#plan-mf) |
| RC.1 | reader corpus harvested from every run's transcript | P1 | BUILT 2026-10-21 (group 1) | [RC](#plan-rc) |
| RC.2 | corpus replay test for every reader | P1 | BUILT 2026-10-21 (group 1) | [RC](#plan-rc) |
| RC.3 | corpus hygiene and `loop.sh corpus` | P2 | BUILT 2026-10-21 (group 1) | [RC](#plan-rc) |
| IN.1 | assumptions gate before the specification | P1 | BUILT 2026-10-21 behind `ASSUMPTIONS_GATE` (off) | [IN](#plan-in) |
| IN.2 | ambiguity count at preview | P2 | PROPOSED 2026-10-21 (group 1, now) | BUILT 2026-10-21 (group 1) |
| BW.1 | regression contract from a seeded codebase's own tests | P1 | BUILT 2026-10-21 behind `REGRESSION_CONTRACT` (off) | [BW](#plan-bw) |
| BW.2 | change-request run from a finished product | P1 | BUILT 2026-10-22 behind `CHANGE_REQUEST_RUNS` (off) | [BW](#plan-bw) |
| BW.3 | brownfield benchmark family | P1 | PROPOSED 2026-10-21 (group 1, now) | BUILT 2026-10-21 (group 1) |
| PN.1 | dependency audit, secret scan and licence listing on the product, as pack data | P2 | BUILT 2026-10-21 behind `RELEASE_AUDITS` (off) | [PN](#plan-pn) |
| PN.2 | README and API summary as required release artifacts | P2 | BUILT 2026-10-21 behind `RELEASE_DOCS_REQUIRED` (off) | [PN](#plan-pn) |
| OP.1 | resume on boot, schedules re-created by the worker | P1 | BUILT 2026-10-21 (group 1) | [OP](#plan-op) |
| OP.2 | stall detector; webhook and email notifications for stalls and gates | P1 | BUILT 2026-10-21 (group 1) | [OP](#plan-op) |
| OP.3 | nightly Postgres and runs.db backup with a tested restore | P1 | BUILT 2026-10-21 (group 1) | [OP](#plan-op) |
| OP.4 | deploy lock; rewind by stage name with a timeout | P2 | BUILT 2026-10-21 (group 1) | [OP](#plan-op) |
| SL.1 | stack policy: allowed packs, default per kind, per-run override, deterministic enforcement | P1 | PROPOSED 2026-10-22 (group 1, inactive until configured) | [SL](#plan-sl) |
| SL.2 | organisation profile per tenant: instructions, naming rules, standards, licence policy | P1 | PROPOSED 2026-10-22 (group 1) | [SL](#plan-sl) |
| SL.3 | profile delivered byte-stable; naming rules compiled to write-time and CI checks | P1 | PROPOSED 2026-10-22 (group 1) | [SL](#plan-sl) |
| SL.4 | Settings tabs and APIs for stacks, organisation, plugin instructions, operator lessons | P1 | PROPOSED 2026-10-22 (group 1) | [SL](#plan-sl) |
| SL.5 | conventions proposed from a seeded repo's own files, owner-confirmed | P2 | PROPOSED 2026-10-22 (group 2) | [SL](#plan-sl) |
| SL.6 | stack-wise naming defaults as pack data (files, identifiers, objects, CAP/Fiori/ABAP names) | P1 | PROPOSED 2026-10-22 (group 1) | [SL](#plan-sl) |
| SL.7 | naming enforced through each ecosystem's linter config from the merged rules; CI-gate check family | P1 | PROPOSED 2026-10-22 (group 1) | [SL](#plan-sl) |
| SL.8 | non-lintable naming rules (tables, routes, env vars, commits) as structured fields checked by existing detectors | P2 | PROPOSED 2026-10-22 (group 1) | [SL](#plan-sl) |
| RV.1 | organisation review policy per reviewer stage, structured items, byte-stable block | P1 | PROPOSED 2026-10-22 (group 1, inactive until configured) | [RV](#plan-rv) |
| RV.2 | reviewers answer every policy item; harness verifies; `check` items run at the gate | P1 | PROPOSED 2026-10-22 (group 1) | [RV](#plan-rv) |
| RV.3 | learned checklist from recurring review findings, owner-approved, plus owner items | P1 | PROPOSED 2026-10-22 (group 1) | [RV](#plan-rv) |
| RV.4 | checklist items promoted to deterministic checks where a detector exists | P2 | PROPOSED 2026-10-22 (group 1) | [RV](#plan-rv) |
| RV.5 | precision loop from dispositions: retire noisy items, keep fixed ones | P2 | PROPOSED 2026-10-22 (group 1) | [RV](#plan-rv) |
| RV.6 | checklist report per run; code-review report document; Review policy tab | P1 | PROPOSED 2026-10-22 (group 1) | [RV](#plan-rv) |
| EN.1 | SSO/SCIM, four roles with per-gate rights, tenant isolation tests | P1 | PROPOSED 2026-10-22 (group 1) | [EN](#plan-en) |
| EN.2 | tamper-evident audit log linking change → model → commit → approver; SIEM export | P1 | PROPOSED 2026-10-22 (group 1) | [EN](#plan-en) |
| EN.3 | SBOM, run manifest (ML/agent BOM), commit trailers, signed artifacts | P1 | PROPOSED 2026-10-22 (group 1) | [EN](#plan-en) |
| EN.4 | PR delivery to the customer's git host; ticket linkage; richer webhooks | P1 | PROPOSED 2026-10-22 (group 1) | [EN](#plan-en) |
| EN.5 | approval matrix, segregation of duties, protected paths, exceptions register, kill switch | P1 | PROPOSED 2026-10-22 (group 1, inactive until configured) | [EN](#plan-en) |
| EN.6 | endpoint allowlists, vault secrets, PII detection, retention per tenant | P2 | PROPOSED 2026-10-22 (group 1) | [EN](#plan-en) |
| EN.7 | coverage/complexity gates, external scanner results, WCAG and performance gates | P2 | PROPOSED 2026-10-22 (group 2) | [EN](#plan-en) |
| EN.8 | compliance bundle per run, EU AI Act disclosure and classification note, model inventory | P2 | PROPOSED 2026-10-22 (group 1) | [EN](#plan-en) |
| EN.9 | cost and chargeback per tenant/team; priced local model; budgets | P2 | PROPOSED 2026-10-22 (group 1) | [EN](#plan-en) |
| EN.10 | Helm/Kubernetes, migrations and upgrade notes, support bundle, HA guidance | P3 | PROPOSED 2026-10-22 (group 1) | [EN](#plan-en) |
| EN.11 | versioned, approvable customisations with export/import | P2 | PROPOSED 2026-10-22 (group 1) | [EN](#plan-en) |
| MT.1 | DevFlow manifest (permissions, roles, resources) and realm client | P1 | PROPOSED 2026-10-22 (group 1; owner schedules the MT sequence) | [MT](#plan-mt) |
| MT.2 | Matura token verification and `perms` checks; OIDC PKCE in the UI; legacy login behind a flag | P1 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.3 | contract tables; uuid `tenant_id` everywhere incl. lessons; events and feed; deletion handling | P1 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.4 | RLS, per-transaction tenant setting, no admin bypass, conformance kit in CI | P1 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.5 | gate approvals as permissions; reviewer as matura user; delegated-agent `act` in audit | P1 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.6 | audit log in the contract's shape with a hash chain, ready for Matura ingest | P1 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.7 | entitlements read and enforced (concurrent runs, frontier model, quotas) | P2 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.8 | per-tenant secrets store behind a backend seam for Matura/OpenBao later | P2 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.9 | no DevFlow users page; portal linked; tenant-scoped settings | P2 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.10 | compose overlay and Helm values joining a Matura install | P2 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.11 | asks of Matura: audit ingest, app secrets/BYOK, usage ingest, SDK `tenant_session`, app readiness controls | P1 | PROPOSED 2026-10-22 (filed at MT step 9) | [MT](#plan-mt) |
| MT.12 | `IdentityProvider` seam: `legacy` / `oidc` (any provider) / `matura` modes behind one `Principal` | P1 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.13 | claims mapping, shared role→permission catalogue, JIT provisioning for direct IdPs | P1 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.14 | SAML and other IdPs through a broker (Matura's Keycloak or a standalone one) | P2 | PROPOSED 2026-10-22 (docs) | [MT](#plan-mt) |
| MT.15 | tenancy, RLS and isolation tests identical in every mode; contract DDL owned by DevFlow when not on Matura | P1 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.16 | agent identity recorded the same way in every mode | P2 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.17 | `role_source` per tenant (idp_then_devflow default); roles-changed audit | P1 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.18 | per-tenant identity configuration and home-realm discovery | P1 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.19 | provider recipes, groups overage, `auth-check` dry run | P1 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.20 | service accounts via client credentials; the loop's account | P1 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.21 | `system` principal for background work; no BYPASSRLS | P1 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.22 | short tokens, back-channel logout, deactivate-now denylist | P2 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.23 | account linking by verified email | P2 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.24 | multi-tenant users and tenant switching | P2 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.25 | pending role grants by email | P2 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.26 | break-glass login for bootstrap admins | P1 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.27 | Identity settings tab and auth observability | P2 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| MT.28 | issuer and scenario test matrix | P1 | PROPOSED 2026-10-22 (group 1) | [MT](#plan-mt) |
| SAP.1 | `sap_cap_node` pack with `@cap-js/mcp-server` | P1 | PROPOSED 2026-10-22 (group 2) | [SAP](#plan-sap) |
| SAP.2 | `sap_fiori_elements_cap` pack, UI generated by the harness | P1 | PROPOSED 2026-10-22 (group 2, after SAP.1; spike first) | [SAP](#plan-sap) |
| SAP.3 | `ui5_freestyle` pack | P3 | PROPOSED 2026-10-22 (group 2) | [SAP](#plan-sap) |
| SAP.4 | connected-stack seam: verification through MCP tools on a customer system, gated writes | P2 | PROPOSED 2026-10-22 (group 2) | [SAP](#plan-sap) |
| SAP.5 | `sap_rap_abap` pack: abaplint locally, ADT MCP in-system, OData acceptance | P2 | PROPOSED 2026-10-22 (group 2, needs an SAP system) | [SAP](#plan-sap) |
| SAP.6 | SAP MCP and skills policy: official Apache-2.0 servers and skills, few tools per stage | P1 | PROPOSED 2026-10-22 (group 1) | [SAP](#plan-sap) |
| SAP.7 | benchmarks `bookshop-cap`, `bookshop-fiori` | P1 | PROPOSED 2026-10-22 (group 1) | [SAP](#plan-sap) |
| DT.1 | `DocumentFacts`: one harness-assembled fact model per run | P1 | BUILT 2026-10-22 (on demand; at release with DT.4) | [DT](#plan-dt) |
| DT.2 | evidence per test: screenshots and traces linked to each test and criterion | P1 | PROPOSED 2026-10-22 (group 1) | [DT](#plan-dt) |
| DT.3 | template registry: uploaded `.docx`/`.md` templates, variables classified | P1 | PROPOSED 2026-10-22 (group 1) | [DT](#plan-dt) |
| DT.4 | rendering to docx/md/pdf; Documents tab, API and handover | P1 | PROPOSED 2026-10-22 (group 1) | [DT](#plan-dt) |
| DT.5 | prose placeholders filled by one bounded call, facts-checked | P2 | PROPOSED 2026-10-22 (group 2) | [DT](#plan-dt) |
| DT.6 | unit-test and acceptance-test documents, harness-written with results and evidence | P1 | BUILT 2026-10-22 (on demand: `loop.sh documents <run>`) | [DT](#plan-dt) |
| RD.1 | run kind `document` for a seeded repository without a brief | P1 | PROPOSED 2026-10-22 (group 2) | [RD](#plan-rd) |
| RD.2 | `repo_survey`: deterministic inventory of a repository | P1 | PROPOSED 2026-10-22 (group 1) | [RD](#plan-rd) |
| RD.3 | `architecture_recovery` with harness-verified citations | P1 | PROPOSED 2026-10-22 (group 2) | [RD](#plan-rd) |
| RD.4 | `test_catalogue`: existing tests run and mapped; the unit-test document | P1 | PROPOSED 2026-10-22 (group 1) | [RD](#plan-rd) |
| RD.5 | `acceptance_recovery`: criteria from the product's surface, suite written and run | P1 | PROPOSED 2026-10-22 (group 2) | [RD](#plan-rd) |
| RD.6 | characterisation tests where none exist | P2 | PROPOSED 2026-10-22 (group 2) | [RD](#plan-rd) |
| RD.7 | legacy-documentation benchmark with deterministic scoring | P1 | PROPOSED 2026-10-22 (group 1) | [RD](#plan-rd) |
| CH.1 | delete root clutter | P2 | BUILT 2026-10-21 (group 1) | [CH](#plan-ch) |
| CH.2 | CI: xdist, ruff, pyright, Dependabot | P2 | BUILT 2026-10-21 (group 1) | [CH](#plan-ch) |
| CH.3 | skips and xfails named and owned; flaky test fixed | P3 | BUILT 2026-10-21 (group 1) | [CH](#plan-ch) |
| CH.4 | `workflow.py` split by stage node, no behaviour change | P3 | PROPOSED 2026-10-21 (after the first clean Measure cycle) | [CH](#plan-ch) |
| EV.1 | owner rating per delivered run beside the hidden score | P2 | PROPOSED 2026-10-21 (group 1, now) | BUILT 2026-10-21 (group 1) |
| EV.2 | screenshot rubric score for browser products | P3 | BUILT 2026-10-22 behind `SCREENSHOT_RUBRIC` (off) | [EV](#plan-ev) |
| SF.1 | registry allowlist for the install category's network | P2 | PROPOSED 2026-10-21 (group 1, now) | BUILT 2026-10-21 (group 1) |
| SF.2 | fetched text capped and stripped of tool-call shapes | P3 | PROPOSED 2026-10-21 (group 1, now) | BUILT 2026-10-21 (group 1) |
| PX.1 | prefix-break reason per model call (tools, steering, thinking, clock, memory order, truncation, reasoning carry, compaction, eviction) | P1 | NOT STARTED 2026-10-22 (group 1) | [PX.1](#plan-px-1) |
| PX.2 | tool list and template settings constant per stage visit; withholding becomes a refusal | P1 | NOT STARTED 2026-10-22 (group 2, `STABLE_TOOLS`) | [PX.2](#plan-px-2) |
| PX.3 | canonical project-memory order independent of the request; no clock in the snapshot; siblings share the prefix | P1 | NOT STARTED 2026-10-22 (group 2, `CANONICAL_MEMORY`) | [PX.3](#plan-px-3) |
| PX.4 | transcript append-only: arguments and cut replies shortened once at store time; reasoning carry persisted | P1 | NOT STARTED 2026-10-22 (group 2, `APPEND_ONLY_HISTORY`) | [PX.4](#plan-px-4) |
| PX.5 | steering notes rendered at the tail, not in the system message | P2 | NOT STARTED 2026-10-22 (group 1) | [PX.5](#plan-px-5) |
| PX.6 | compaction keeps the opening bytes; `--cache-reuse` advised to the owner | P2 | NOT STARTED 2026-10-22 (group 2) | [PX.6](#plan-px-6) |
| PX.7 | `cache_prompt` explicit, `id_slot` affinity per visit, side calls follow their thread, slot save/restore around gates | P2 | NOT STARTED 2026-10-22 (group 2, `SLOT_AFFINITY`) | [PX.7](#plan-px-7) |
| PX.8 | code-base snapshot side-car beside llama-server | P3 | DECISION GATE 2026-10-22 (on PX.1's eviction share) | [PX.8](#plan-px-8) |

<a id="plan-m-2"></a>
### M.2 Fixes from the loop's audits (no plan item of their own)

Each found by a routine audit or a deep analysis of a live run, fixed in
general with a test that fails on the old code. The measured cause and the
run are in `docs/monitoring-handover.md` §0 under the day.

| ID | Fix | Status | Detail |
|---|---|---|---|
| LF.1 | a fix stage that has read for twelve calls and changed nothing has its looking tools withheld (write-forcing rung) | DONE 2026-10-19 `9275b8f` | [monitoring handover §0](monitoring-handover.md) |
| LF.2 | a fix for a failing unit-test run, measured green, needs no named regression test | DONE 2026-10-19 `ca0bb47` | [monitoring handover §0](monitoring-handover.md) |
| LF.3 | a shell builtin (`export`, `set`, `source`, `unset`) is refused with the reason: there is no shell | DONE 2026-10-19 `99e2fb7` | [monitoring handover §0](monitoring-handover.md) |
| LF.4 | a product that cannot start says why from the end of its traceback; every stage is told it starts from `PORT` and `DATA_DIR` alone | DONE 2026-10-19 `2d94b84` | [monitoring handover §0](monitoring-handover.md) |
| LF.5 | a refused credential file says where the setting goes: a development default in the settings code | DONE 2026-10-19 `f194f91` | [monitoring handover §0](monitoring-handover.md) |
| LF.6 | the product audit runs the product's tests in a stage's environment; the acceptance reviewer does not judge built code; `NAME=value` before a command is said to set nothing | DONE 2026-10-19 `1f52757` | [monitoring handover §0](monitoring-handover.md) |
| LF.7 | `env` in front of a command is refused with the same reason | DONE 2026-10-19 `be96b76` | [monitoring handover §0](monitoring-handover.md) |
| LF.8 | a "product does not start" defect is dispatched to a fixer, and passing unit tests close only a defect raised from failing unit tests | DONE 2026-10-19 `373ffd4, e608003` | [monitoring handover §0](monitoring-handover.md) |
| LF.9 | a release says when no unit test file exists for the runner to collect, and when no review read the code | DONE 2026-10-19 `0970364` | [monitoring handover §0](monitoring-handover.md) |
| LF.10 | a failed custom-setup install names its cause (the most telling error line plus the end); Python setups are told how a setuptools install names its package | DONE 2026-10-19 `a3c24a6` | [monitoring handover §0](monitoring-handover.md) |
| LF.11 | a suite's `run.json` in the wrong shape is refused as written, and the send-back names the shape | DONE 2026-10-19 `c6c3284` | [monitoring handover §0](monitoring-handover.md) |
| LF.12 | a custom setup writes its declaration first and keeps it current | DONE 2026-10-19 `b5c2f30` | [monitoring handover §0](monitoring-handover.md) |
| LF.13 | how a disabled control looks is not read as advice to disable it | DONE 2026-10-19 `4cdddf5` | [monitoring handover §0](monitoring-handover.md) |
| LF.14 | BF's record: an opening request in several messages is all request; the specialists' advice is not the specification | DONE 2026-10-19 `765173d` | [monitoring handover §0](monitoring-handover.md) |
| LF.15 | a local-only run revises its specification in place, and every section in parts when none can be named | DONE 2026-10-19 `dc7eeae` | [monitoring handover §0](monitoring-handover.md) |
| LF.16 | `use_runtime` reaches the tool: its parameter is `language`, not `runtime`, which LangGraph's tool node takes for its injected runtime (every call failed with an empty error) | DONE 2026-10-19 `2ccbf81` | [monitoring handover §0](monitoring-handover.md) |
| LF.17 | a measurement with no test results, or a criterion the locked suite's own files name, never sends QA to add tests that are "missing" (a dispute 100 ms after a reverted fix reopened the suite on six such criteria) | DONE 2026-10-19 `2ccbf81` | [monitoring handover §0](monitoring-handover.md) |
| LF.18 | the QA lead's dispute is told the product's code is not the standard and never to open the product's files to decide what a test may expect | DONE 2026-10-19 `2ccbf81` | [monitoring handover §0](monitoring-handover.md) |
| LF.19 | the specification's layout is checked against what the scaffold serves first, on a repair budget of its own (it came last in a chain sharing two repairs, and a plan building where nothing serves it was approved) | DONE 2026-10-19 `2ccbf81` | [monitoring handover §0](monitoring-handover.md) |
| LF.20 | a missed edit after the stage's own change names its own edit (same batch or earlier) or a command, and no longer claims the passage was right for the version it had | DONE 2026-10-19 `af2086f` | [monitoring handover §0](monitoring-handover.md) |
| LF.21 | a fix reverted because nothing could run puts the build or start error first in what it broke, so the next fixer sees the cause | DONE 2026-10-19 `af2086f` | [monitoring handover §0](monitoring-handover.md) |
| LF.22 | (owner's idea) whoever writes the tests - the acceptance author and the testing work order - is handed the product's API as the specification decides it: endpoints, data shapes, errors and the interface, whole, within 12,000 characters (a 71k specification reached the acceptance author as headings only) | DONE 2026-10-19 `1113dec` | [monitoring handover §0](monitoring-handover.md) |
| LF.23 | a command whose output was cut names, in the per-call digest, the `read_command_output` reference of its whole output (a stage asked for "call 7", the digest's own label, which names no output) | DONE 2026-10-19 `eacafc1` | [monitoring handover §0](monitoring-handover.md) |
| LF.24 | (owner's request: what else helps test writers, planners and other agents) the product's API as the specification decides it goes to every work order and every fixer, the acceptance reviewer, the QA dispute and the milestone review - measured on the medium run, fixers and the dispute saw the 71k specification's headings only, and the service drifted to `username` where it said `full_name` | DONE 2026-10-19 `1bc7264` | [monitoring handover §0](monitoring-handover.md) |
| LF.25 | the architect is told the layout the scaffold sets up - the project folder, the files it serves, where unit and acceptance tests live, the files the harness keeps - before it writes the file plan | DONE 2026-10-19 `1bc7264` | [monitoring handover §0](monitoring-handover.md) |
| LF.26 | a write's "files that import this one" note names only the importers whose import the compiler resolves to that file - measured live, writing `src/api/client.js` was told six pages under `frontend/src/` would fail to load (they import `frontend/src/api/client.js`), and the fixer rewrote the file it had just written, identically | DONE 2026-10-19 `6ffed0f` | [monitoring handover §0](monitoring-handover.md) |
| LF.27 | deleting or moving a database file (`*.db`, `*.sqlite`, `*.sqlite3`) is refused as a database, not as "credential material", and the refusal names the cause a leftover database points at: the product keeps it outside `DATA_DIR` - measured live, a fixer with `UNIQUE constraint failed: users.username` was refused the delete as credential material and spent its next calls looking for the file, while the product's database URL was a file in the working directory | DONE 2026-10-19 `e21a5ad` | [monitoring handover §0](monitoring-handover.md) |
| LF.28 | a reverted fix's log line also says how many tests it had made pass ("broke 1 test(s) that passed before it, and had made N pass that did not"): the snapshot after a reverted fix is not kept, so whether a whole fix should go for one broken test could not be judged - measured live, six fixes reverted, one of them a rewrite of the served page for one broken test. Observability only; whether to keep a fix that gains more than it breaks is a group-2 question with these numbers | DONE 2026-10-19 `3ffe5fb8` | [monitoring handover §0](monitoring-handover.md) |
| LF.29 | a criterion's first pass names its measurement as what it was: a snapshot's label is "after X", "before X", "suite locked" or "accepted", and the ledger read every one as "after" - measured on the live page after the deploy, "first passed after Before Defect Fix 2 16"; it reads "first passed by the start of Fixing problem 17 (test round 2)" now | DONE 2026-10-19 `c6e04398` | [monitoring handover §0](monitoring-handover.md) |
| LF.30 | a `read_command_output` call that names a file of the workspace is answered with that file's place and, when it was searching, the `grep` call that does it - without the list of saved command outputs in front - measured live: a fixer searching a source file with its read tool withdrawn got thirty log names first and the `grep` it needed last, and did not use it. A path found nowhere still lists the saved outputs | DONE 2026-10-19 `aeb97b18` | [monitoring handover §0](monitoring-handover.md) |
| LF.31 | (owner's report) the start page said thorough runs take about 1.5 h and fast ones 4+ h, so thorough read as the faster: the figure was the median wall time of whatever runs had finished - two thorough runs (a small benchmark and the low brief) against six fast ones of briefs of 8-18 criteria, some from many harness versions ago. Now a mode's figure comes from its 10 most recent completed runs and needs three of them (two say "only 2 thorough runs finished here: too few to estimate"); with the brief's criteria from its preview, each delivery card shows its own estimate for a brief that size ("about 5.2 h for 13 criteria", from the median hours per criterion), so the modes compare like with like; the run page scales it to the run's criteria (the run payload carries them) | DONE 2026-10-19 `d45581f1` | [monitoring handover §0](monitoring-handover.md) |
| LF.32 | (owner's request) a run started with "use the frontier model" ticked checks first that the frontier model is configured - a model named, a key where its provider needs one - and answering: one listing of its models, never a model call, kept a minute (`models/frontier_check.py`, `GET /api/settings/frontier/status`). The start page shows the status beside the box ("Ready: … answers", or the reason with a link to the model settings) and does not start until it holds; the start route refuses an explicit `use_frontier_model: true` with the reason before preparing anything (an omitted value keeps the run on whatever is configured, so the loop's runs are unchanged); `loop.sh start` now reports a refused start instead of printing "started", and removes the run it created | DONE 2026-10-19 `d45581f1` | [monitoring handover §0](monitoring-handover.md) |
| LF.33 | (owner's report) the activity feed's step headings stuck 12 px below the lane chips, and entries scrolled visibly through that strip: the scroller's top padding offsets a sticky heading. The scroller has none above now, and the stepper's group headings stick the same way, flush; the other two sticky headers (the page header, the Audit table's head) sit in unpadded containers. Measured live: both headings at 0 px below their scroller's top | DONE 2026-10-19 `d45581f1` | [monitoring handover §0](monitoring-handover.md) |
| LF.34 | (owner's report) the Delivery pane split itself in two by the window's width (`xl:grid-cols-2`), so in the run page's narrow ledger column each criterion wrapped to a few words a line beside a squeezed "did not prove" list. It is laid out by its own width now (a container query: one column in the ledger, two when the pane itself is wide); each criterion is one row - its id, its text across the row, its status at the right edge, so statuses scan as a column - with the test count and its first passing test in one quiet line under it; a bar and the count of each status sit above the list. A criterion's "first passed" line reads "first passing test:", since a failing criterion can have one. Measured live: axe 0; the pane 368 px at 1440 and 448 px at 1920, one column at both | DONE 2026-10-19 `4144268f` | [monitoring handover §0](monitoring-handover.md) |
| LF.35 | (deep analysis) once a stage's reading was withheld, the command tool refused every `cat`, `ls`, `find` and the like as "only showing what the project memory and your earlier reads already gave you"; measured on a 6-hour run, 49 of its 70 refusals were false - an installed `.venv`, a built `dist`, a folder holding a database, none of which the memory shows. A look is refused now only when the stage already has what it shows: a file's lines when this stage has seen that file as it is now (held whole by the memory, or read or written by the stage), a name or a folder's listing when every file under it is a text file the memory names; an ignored, binary, missing or changed target runs (`agent_toolkit._the_memory_shows`) | DONE 2026-10-19 | [monitoring handover §0](monitoring-handover.md) |
| LF.36 | (deep analysis; the owner asked why the fix loop did not improve) a stage whose conversation was compacted lost the request it was given: langchain's summariser trims what it summarises to its last 4,000 tokens and starts that on a human message, a stage's only human message is its opening request - far larger - so the slice was always empty, the summary read "Previous conversation was too long to summarize.", and it replaced the request too. Measured: 7 of the shakedown's 8 compactions empty, 6 of them in fix stages, all 6 fixes failed (one fixer lost its defect, its failing tests and the stub warning, and went on to edit the copy nothing serves); an earlier run had 7 of 8 empty. The stage agent's summariser (`agents/compaction.RequestKeepingSummarization`, still named `SummarizationMiddleware` so deepagents swaps it for its default rather than adding a second) carries the stage's whole opening turn - every message before the model's first reply (live: the files as they stood, then the defect brief; the first version kept only the first and lost the brief, caught by replaying the live fixer's conversation before it deployed) - whole into the summary message and through every later compaction, names the files the stage has written, and hands the summariser the latest work under a human lead-in, so the summary is never empty | DONE 2026-10-19 | [monitoring handover §0](monitoring-handover.md) |
| LF.37 | (owner's report: "seems like looping") a testing stage refused `ls -la tests/` on an empty folder four times running, then spent its calls repeating one reply ("I need to stop trying `run_terminal_command`"), the same `glob` seven times and one test file rewritten unchanged, until its tools were withheld and it claimed 14 files it never wrote (caught). LF.35 still refused a look at an empty folder, everything in it being - vacuously - held. An empty folder's listing now runs: it costs nothing and settles the question | DONE 2026-10-19 | [monitoring handover §0](monitoring-handover.md) |
| LF.38 | (routine audit) a batch after which the product did not start for the acceptance suite raised each acceptance test that had passed before as its own regression - "gone now - no test of that name ran ... removed or renamed" - queued ahead of the start failure the test round raised once, so a fixer went looking for a renamed test in a locked suite (the CI snapshot already recorded why no test ran: `problem`). With a start failure recorded, lost acceptance tests are not regressions one by one; unit regressions are raised as before (`engineering.regression_defects`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.39 | (deep analysis) a review's findings were handed to the architect again on every pass until the next review: after a review-driven revision, the architect's own check sent it back for one section, and the repair pass got the review's "MUST FIX" list beside "return only `specialist_advice_decisions`" - measured live, it rewrote ten sections a second time (four minutes of model time), where the same repair with nothing else asked rewrote one. The architect records which review it has applied (`architecture_review_applied`); the findings are open again only after a new review (`workflow._the_review_s_findings_are_open`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.40 | (deep analysis) the architect was told where the product's files go, not where its data lives: the gate run's specification planned a server's column types and search (`JSONB`, a computed `TSVECTOR`, `TIMESTAMPTZ`, tests "against a real PostgreSQL") for a product every test runs on the file database. The packs that fall back to a file database now say what that means - the schema, its types, queries and migrations must work on it as well as on the server - to whoever writes the code, and the same goes to the architect beside the layout (`StackPack.data_store`; the fullstack and service builders and Next) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.41 | (routine audit, gate run's first 15 minutes) the layout repair told the architect "the scaffold serves `src/App.tsx`, `pkg/main.py`" - paths relative to the project folder, with no folder said - and it planned `pkg/src/App.tsx`, the page inside the service's package; both repairs were spent and the plan went on building the page where nothing served it. The repair now names each served file from the workspace root and says which folder is the project's (`workflow._the_layout_repair`). The run was cancelled and restarted on the fix | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.42 | (routine audit, gate run's first 30 minutes) told where the data lives (LF.40), the architect wrote the file-database fallback the setup needs; the architecture reviewer, never told the setup, raised it as a major finding ("contradicts the hard constraint 'Database must be PostgreSQL'" - the brief does ask for PostgreSQL), and the revision made `DATABASE_URL` required with "no fallback database ... in any environment": a service no test can start. The review now gets the same layout and data-store facts as the architect, with the rule that what the setup requires is not a departure from the brief (`build_architecture_review_request(environment=...)`, `workflow._the_setup_for_the_review`). The run was cancelled and restarted on the fix | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.43 | (deep analysis) a fast in-place revision showed the reviser each section through `json.dumps(..., default=str)`, so every decision record arrived as `title='...' decision='...'`; the reviser handed them back so, and the revision - five minutes of model time - "could not be joined: 11 validation errors" and was thrown away for a whole-document revision. Sections are shown as the specification's own JSON (`specification_parts._sections_as_json`), in the in-place revision and in the parts writer's core | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.44 | (routine audit) a product that did not start was recorded with three lines from the first error and the last eight: when the page's build failed, those were Playwright's own "was not able to start" and a Node error object's file list, and the build's line naming the cause - the import that did not resolve - sat between them and was cut, so every fixer was told the build failed and not why. The lines in between that state a cause are kept too, up to six (`suite.the_product_did_not_start`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.45 | (routine audit) the project's dependencies were installed once, by the scaffold: fast delivery drafted `package.json` with `react-router-dom` in it - one model call, no command after - and nothing installed it, so every test round built the page against the scaffold's `node_modules`, the build failed to resolve the import, and the product "did not start" round after round while its manifest was right (LF.44 is what showed the import). Before each of the harness's own measurements (the suite run, the unit run in CI) the project is installed again when a dependency manifest changed since the last install; the scaffold records its install, and a failed install is tried again at the next measurement (`contract.install_if_the_manifests_changed`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.46 | (deep analysis; **its evidence corrected 04:15 JST 2026-10-20**) the project memory is kept byte for byte through a stage visit for the server's prefix cache; `stage_memory`'s own notes say an approval resume rebuilds the stage's agent, and a rebuilt middleware would take the memory afresh. The visit's snapshot is now kept in `stage_memory`, which an approval survives and a worker restart does not (`project_memory._the_visit_s_memory`). **Correction:** the measurement first given for it - "the memory changed 18 times in one fix stage" - counted the transcript's `project_memory` block, which includes the growing "[Project memory update]" note at the end of each request. Counted properly, the opening message was sent anew once per compaction plus once at the start (15 for 14 compactions in one stage, 10 for 9 in another): the cache misses were the compaction storm, fixed by LF.47, not rebuilds. LF.46 is kept as a guard for a rebuild; it moved no measured number | DONE 2026-10-20; **REMOVED 2026-10-20 (owner)**: it moved no measured number | [monitoring handover §0](monitoring-handover.md) |
| LF.47 | (routine audit) LF.36's summary carried the stage's whole opening turn, and with a request's fixed share - the project memory, a snapshot of the files at the stage's start, the request, the system prompt and the tools - a compacted conversation's kept tail already sat near the 80,000-token trigger: measured on the gate run, compactions every one or two calls (10 in a fix stage's 28 calls, 9 in 40, 7 in 30; 8 in the whole earlier 7-hour run), each a summary call, a rewritten conversation and lost recent context (a fixer re-sent an edit it had made). The opening turn is carried within 48,000 characters - its last message, the request, always whole; a context message before it only while it fits, the project memory holding the files as they are - and a conversation just compacted is not compacted again until it has gained 8 messages past its kept tail; a request too large for the window is still compacted at once by the summariser's overflow fallback (`compaction.MOST_CARRIED_CHARACTERS`, `NEW_MESSAGES_BEFORE_COMPACTING_AGAIN`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.48 | (routine audit) LF.45 installed a changed manifest before the suite's run and CI's unit run only; a fixer's own check after its fix - one acceptance file at a time, and the procedural unit run - went through neither, and on the resume the harness ran `npm test` with no install and no install record. Every command the harness runs to measure the product (`test`, `probe`) goes through `scaffold.sandbox_runner`, which now installs first when a manifest changed since the last install | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.49 | (routine audit) a fix that named no regression test was recorded as "the fix named no regression test" even when the measurement after it showed its own tests still failing - three fixes of "the unit tests fail" on the gate run, each with failing unit tests after it. The measurement is read first: a fix whose own tests still fail is recorded as that; the missing test name is the reason only when the measurement cannot say. Both leave the defect open, as before (`workflow._settle_the_fix`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.50 | (routine audit) once the page built, Playwright's runner stopped at "Fatal process out of memory: Failed to reserve virtual memory for CodeRange" in `node::worker::Worker::Run` on every acceptance file, five seconds in all, and the round recorded 13 criteria as not working - the product was never measured. Measured in the worker through the sandbox: four Node worker threads would not start under a 1 or 2 GB data limit and ran at 3 GB, each thread's V8 instance reserving a code range the limit counts (the Angular pack had declared 4 GB for this; no other pack had). A pack whose unit or acceptance command starts a Node toolchain is given at least 4 GB per process; the tree watcher still bounds real use (`sandbox.NODE_TOOLCHAIN_MEMORY`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.51 | (routine audit) a suite run that wrote no report was saved as "the runner wrote no report; its output is below" with no output: `AcceptanceResult.as_dict` left `output` out, and the cause of LF.50 was found only by running the command again by hand. The saved result keeps the runner's output tail | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.52 | (deep analysis) `["cd", "task-management-dashboard", ".venv/bin/python", "-m", "pip", "list"]` was refused three times on the gate run and five on the shakedown ("`cd` is not a program. Pass `working_directory`"), each a model call to say what the argv already said. A leading `cd <folder>` - with or without `&&` after it - is taken as the working directory, joined to the one given, and the command runs there with a note saying so; the sandbox resolves and confines the folder as it does any `working_directory`. A bare `cd` is refused as before (`agent_toolkit._a_cd_taken_as_the_working_directory`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.53 | (owner's decision, 2026-10-20) `python -c` and `node -e`/`--eval`/`-p`/`--print` were refused ("Put the code in a file ... named `tmp-<what it checks>`") - 10 refusals on the gate run, 35 on one earlier, each a model call, and the advice rarely followed. The command tool now does what the advice says: the snippet is saved as `tmp-inline-<hash>` (`.py`, `.cjs`) in the project folder or the working directory, the interpreter is run on that file with the arguments after the code kept, and the result names the file; a `tmp-` file is swept before the next test round and at release. The sandbox's own refusal is unchanged for anything that still reaches it (`agent_toolkit._code_on_the_command_line_as_a_file`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.54 | (owner's decision, 2026-10-20) the start page left "use the frontier model" ticked with no frontier model configured, so the box could only block the start. It is asked once on opening; with none configured the box starts unticked and a saved default cannot tick it back; one configured but not answering stays ticked and says why (`Home.tsx`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.55 | (routine audit) a drafted `package.json` pinned `@playwright/test` 1.45.0, `vite` 5.4.2 and `vitest` 2.0.0 over the scaffold's 1.64.0, ^7 and ^3.2. Uninstalled, the scaffold's versions kept working; once LF.45/LF.48 installed it, Playwright 1.45 hung under the runtime here - every acceptance run, even `--list` of one file, timed out with no output, inside the sandbox and out. The harness already put back its kept files and manifest scripts; it now also puts back the pack's version of every package its kept files import (`@playwright/test`, `vite`, `vitest`, the framework's Vite plugin), leaving the product's own packages alone, and the changed manifest is then installed (`contract._put_back_the_toolchain`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.56 | (routine audit) `["python3", "-m", "pip", "install", "fastapi", "uvicorn[standard]", ...]` was refused twice on clean gate run 1 as "it runs until it is stopped, and nothing here will stop it". The install carve-out found the package manager by `argv[0]` only, so pip driven as a module was not an install; and the module check took any server module after `-m` for the one being run. `python -m <manager>` is that manager, and the module run is the word right after `-m` (`sandbox._manager_of`, `_starts_a_server`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.57 | (owner's request, 2026-10-20: "rewind to the stage before the bug ... so we don't waste the work"; "make the testing as effective as possible and efficient") tonight three gate runs were cancelled and started again for bugs found after the specification, and a findings run was cancelled 4 hours in - each restart redid the intake, the consults, the specification and the suite, which the fix did not touch. The harness could already rewind a stopped run to the start of a stage with its files (and `.harness/`) as they were; the loop could not ask for it. `loop.sh rewind <graph stage> [run] [at-or-before]` pauses a live run, picks the stage's entry (`scripts/loop/rewind_point.py`) and rewinds; `--pause-only` pauses for a deploy between. Each rewind is recorded in the transcript (`rewound`, with the moment it went back to), and the KPIs and `run_timing` leave out the work the rewind discarded (`run_kpis.live_branch`; `rewinds` counted) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.58 | (owner: testing efficient) the loop's whole suite ran on one process, about 290 s, and every fix waited on it before its deploy (about 25 runs on 2026-10-20). With `pytest-xdist` it runs on 12 workers in 64 s with the same result; `loop.sh suite` uses it when installed (`SUITE_WORKERS`, default 12) and `pyproject.toml` lists it | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.59 | (gate run 1) the gate's language service read only the first 12 changed code files by name, so on a batch of 22 - migrations and page files first - the router at 19th was never read, and the imports nothing defined there failed the service's start three test rounds running, one missing name a round. Each Python read was also a whole-project Pyright run kept for one file: 2 s a file, 45 s a batch. Python files are now read by one Pyright run (19 files in 2.0 s on the live workspace, the same findings as file by file); the file-by-file reads (TypeScript) take the product's own code first, so the cap (now 24) falls on tests and configuration; a Python finding is no longer labelled the TypeScript service's (`language_service.python_underlined_together`, `engineering.underlined_in_the_batch`). Held for deploy until both gate runs end, as a non-spoiling fix | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.60 | (gate run 1, LF.53's own gap) the `tmp-inline-` file LF.53 saves code from the command line in was never swept: the sweep before each test round removes only a file the project memory says a stage of this run wrote, and the command tool wrote these itself - seven sat in the gate run's product. The file is now recorded as the calling stage's, so the existing sweep removes it. The command tool's description still said such code was refused and to write, run and delete a file (three calls for one); it now says what happens (`agent_toolkit._code_on_the_command_line_as_a_file`). Held for deploy until both gate runs end | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.61 | (gate run 1) the service declared `passlib[bcrypt]` and `bcrypt>=4.0.0`; the install took bcrypt 5.0.0 and every hash raised "password cannot be longer than 72 bytes" from passlib 1.7.4's own start-up check (its last release) - reproduced in the product's environment, where `bcrypt` called directly works. The fixer read it as a version mismatch. Python stacks are now told, in the seeded guidance: hash with `bcrypt` directly, or declare `bcrypt<5` beside passlib (`plugins/seed.py`). Held for deploy until both gate runs end | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.62 | (deep analysis, gate run 1) only 59% of the run's 17.3M prompt tokens came from the server's cache. Classified by what broke each prefix: the project memory - the conversation's second message - rendered again within a stage with the stage's new file in the middle of it, 48 calls and 2.4M tokens re-read (about 18 min of the run's 105 model-minutes); tool-list changes 2.5M (EF.1); compactions 1.2M (inherent). The snapshot meant to stay byte for byte through a visit lived on the middleware instance, and every gated tool call interrupts the graph and the node builds the agent afresh on resume. The visit's snapshot, held files and starting files are now kept in `stage_memory`, keyed by the stage's inner thread (`project_memory.build_project_memory_middleware`). Held for deploy until both gate runs end | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.63 | (deep analysis, gate run 1) the audit's 43% redundant reads (healthy 8-19%): 40 of the 57 repeated `read_file` results came after a compaction had taken the earlier result out of the conversation - necessary reads, each told "this returned nothing you did not already have", and counted toward the refusal rung. A compaction now makes the stage forget the lines, bytes and repeat tally its reads were given (`stage_memory.forget`, `workspace_backend.WHAT_THE_CONVERSATION_WAS_GIVEN`, `compaction.RequestKeepingSummarization`). The redundant-read KPI is not comparable across this fix. Held for deploy until both gate runs end | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.64 | (deep analysis, gate run 1) the service stopped at start-up on "unable to open database file" (its database module ignored `DATA_DIR` for a relative `data/app.db`). The defect's excerpt kept only frames inside the installed packages, and the one product file the output named was a deprecation warning's - so the fast fix rewrote that router, the start failed again, and the sprint was planned again. The excerpt now keeps the product's own frames nearest the error with the line each ran (`suite.the_product_did_not_start`); a data file that would not open gets a `DATA_DIR` hint; the fast fix no longer takes a file from a line that only warns (`rewritten_fixes.files_to_fix`). Held for deploy until both gate runs end, unless the owner decides otherwise | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.65 | (gate run 1) the re-plan after sprint 1's second exhausted attempt was given round 0's "the unit tests fail" (an import error the last round's unit tests no longer had - 23 of 23 passed), and "the product does not start" twice and without its cause (`unable to open database file`); it planned the unit tests' setup while the product went on failing to start. Each defect now records the round that raised it and the attempt keeps what it showed; the lead's brief lists what the last round still found first, each with what it showed, de-duplicated, and marks what only an earlier round raised (`Defect.found_in_round`, `workflow._what_a_plan_did`, `technical_lead._what_the_last_attempt_left`). Held for deploy with LF.59-LF.64 | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.66 | (loop) `loop.sh defects` counted the attempt a rewind discarded - the re-plan read "attempt 3" where the record held two. It now shows the live branch (`run_kpis.live_branch`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.67 | (gate run 1) the re-plan's work order wrote `tests/test_tasks.py` with `await` inside a plain `def`; the write guard's Python check was `ast.parse`, which accepts it (the compiler's later pass raises it), so the write went through and every test in the file failed to collect in the next round. The check now compiles the file without running it, so `await`, `return` or `yield` outside a function and `break` outside a loop are refused at the write with their line (`syntax_balance.structural_problem`). Held for deploy with LF.59-LF.66 | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.68 | (gate run 1) round 1's run of the suite passed 47 of 62 tests, and round 0's "the product does not start" stayed open: it names no criterion, so the round's measurement could not close it, and its fixer spent 20 minutes on it and left it open as "its own tests still fail" - the unit tests, failing for another reason. A start defect now closes when the suite's last run reached the product with no start failure recorded (`workflow._the_product_starts_now`, in `_resolved_by_a_measurement`), and a fix is settled on that, not on the unit tests (`_the_defect_s_tests_in`). Held for deploy with LF.59-LF.67 | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.69 | (gate run 1) the service's async unit tests failed to set up round after round under pytest-asyncio's strict mode ("requested an async fixture"), and the fix tried was the configuration - a file the harness keeps. First built as `asyncio_mode = auto` in the Python packs' kept `pytest.ini`; REVISED by LF.70: proven with real pytest, auto mode takes anyio's tests from anyio and runs a trio-parametrised one on asyncio - a fix for one product that breaks another. The kept file is as it was; the Python plugin instructions now say what strict mode needs (`@pytest.mark.asyncio`, `@pytest_asyncio.fixture`, or `@pytest.mark.anyio`) (`plugins/seed.py`) | DONE 2026-10-20 (revised) | [monitoring handover §0](monitoring-handover.md) |
| LF.70 | (owner, 2026-10-20: every fix language- and framework-agnostic; anything specific handled through the harness's existing tables, packs and plugin instructions, so a fix for one stack neither misses nor hinders another) review of LF.59-LF.69. Reworked: LF.53/LF.60's inline-code rewrite knew only Python and Node while the sandbox refuses code on the command line for Ruby, PHP, Elixir and Scala too - one table beside the sandbox's refusals (`sandbox.CODE_AS_A_FILE`: suffix and file template per program and flag) now drives the rewrite and the tool's description; LF.59's gate tested for `.py` and named Pyright itself - the language service now says which suffixes one project-wide run reads and what each service is called (`language_service.underlined_in`, `service_name`); LF.64's frames were Python's and Node's, with their dependency folders listed - a frame is now the product's when it names one of the product's own files outside the folders a tool fills, in any runtime's trace form (Go, JVM, Node and Ruby traces tested), absolute paths are mapped to the workspace for the fast fix, and the data-file hint quotes the run's own pack (`StackPack.data_store`); LF.69 as above. Unchanged, as already agnostic or in their language's own place: LF.61 (plugin instructions), LF.62, LF.63, LF.65, LF.66, LF.67 (Python's branch of the per-language syntax check; JavaScript's parser already refuses the same case), LF.68 | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.71 | (deep analysis, gate run 1) a page check's "the interface is not styled" was fixed by rewriting its stylesheet and `tests/test_tasks.py`: every fast rewrite is given the run's last failing command, here another fixer's unit-test run, and its files were taken as the defect's. The rewritten test broke 17 tests, and the revert took the stylesheet with it. Files now come from the defect's own evidence first, the last failing command only when that names none; a test file is taken from failure text only for a defect the unit tests raised (one the defect names is still its own) (`rewritten_fixes.files_to_fix`). Language-agnostic: file kinds and the defect's own words. Held for deploy with LF.59-LF.70 | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.72 | (owner, 2026-10-20: where a failure comes from the model's training data being older than a library, the agents reach the current answer) the stages could read a project's own documentation and registry, never what neither says - passlib 1.7.4 failed on every hash with bcrypt 5.0.0 and the fixers worked around it for rounds, while a search for the error gives the bcrypt issues naming the cause first. A private SearXNG (`searxng` in docker-compose, pinned image, no host port, JSON API on, limiter off, engines kept to the general web and developer sources - code hosts, Q&A, the package registries, MDN, Microsoft Learn, the vulnerability database: `docker/searxng/settings.yml`) and two tools for the stages that read documentation (architect, stack selector, every specialist and fix stage): `search_the_web` and `read_web_page`, a page read only from a public address (never the compose network, the host or a cloud metadata service, redirects checked), answers labelled as leads, not instructions; a shared share of 8 per stage (`app.tools.web_search`, `research.MOST_WEB_LOOKUPS`). Verified from the worker on the compose network | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.73 | (owner, 2026-10-20: the agents find and use a library's MCP server where its makers publish one) the libraries every manifest declares (npm, PyPI, Go, crates, Maven, Composer, RubyGems, NuGet - one reader, `app.analysis.manifests`, now shared with the loop's pack-freshness check) are searched in the official MCP Registry; a server is the library's own when its verified namespace (`dev.svelte`, `io.prisma`, `io.github.<account>`) matches the homepage or repository the library's own registry entry gives (`package_registry` now reports `homes` for every ecosystem) - measured: "fastapi" and "angular" return only third parties' servers, refused; Svelte's and Prisma's pass. Only a remote server, only its tools that declare `readOnlyHint`; the search runs in the background, never holding up a stage, and what it found is kept in `.harness/mcp-official.json` for the stages built after (`app.tools.mcp_registry`, `mcp_tools.tools_for`). Not done, for the owner: a package server (`npx @sveltejs/mcp`) would run third-party code inside the worker, outside the sandbox and beside the run's secrets | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.74 | (gate run 1) a locked acceptance helper built `new URL('/api/tasks', 'http://localhost')` instead of using the suite's `baseURL`; 48 failures in the suite's last run were `connect ECONNREFUSED ::1:80` / `127.0.0.1:80`, charged to the product while fixers looked for a server the suite never starts there. A request to port 80 or 443 on the local host is now a test's own bug in the packs' patterns - Node's message in the JavaScript packs', `requests`' in the Python packs' - so the round reopens the suite for QA instead (`packs/_javascript.TEST_BUGS`, `packs/_python.TEST_BUGS`); the suite's own port refusing stays the product's. Held for deploy with LF.59-LF.73 | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.75 | (findings run) a fix for "the unit tests fail" rewrote the unit test file - 24 tests passed that did not - and changed one router, which broke 13 sign-in acceptance tests; the whole fix was reverted, the test repair with it (the second all-or-nothing revert of the run, after LF.71's). When only acceptance tests broke, the fix's own test changes are now kept and its product changes put back: the acceptance suite runs the product, so a unit test file cannot be what broke it; the part is measured once more and kept only if it breaks nothing, and the defect's own tests settle it as before (`engineering._its_tests_without_its_product_change`, `ci.restore_paths`). Kind-based, no language named | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.76 | (deep analysis, findings run) after the 10:31 rewind the timing read 138 of 311 minutes as "neither model nor tool": the records left after a rewind (`live_branch`) still span the abandoned branch, the first before it and the last after, so the wall clock - and every share of it, model-busy among them - counted its 89 minutes as the run's own. The time each rewind discarded is now taken off the wall and out of the orphan gaps (`run_kpis.discarded_seconds`, in `kpis` and `scripts/loop/run_timing.py`, whose two imports are now separate so a worker deployed before this still filters the records) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.77 | (findings run) with the acceptance suite at 62 of 62, the sprint was planned again for its one open defect - the unit tests could not collect `tests/test_tasks.py` (`await` in a plain function). The re-plan was shown the defect's first 600 characters - pytest's and the import system's frames - and "the unit test command exits non-zero", twice (two rounds' output differed), and planned new test files, leaving the broken one. A failing unit run's defect now says what its output says went wrong: the last lines that name an error or a failure, not the frames (`workflow._what_the_failure_says`, in `_the_unit_tests_fail`), and one check's defect from two rounds is shown once, by its first sentence (`technical_lead._what_the_last_attempt_left`). Any runner's words: Error, Exception, FAIL, failed, panicked | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.78 | (findings run) a testing stage was told by a SyntaxError that line 146 was wrong, asked for lines 135-195 (and for the whole file nine times), and was pointed at the project memory each time - which holds a file's text without line numbers - until its read tool was withheld; it spent three attempts of forty calls and fell back to `cat -n`. A read of a held file by position, 80 lines or fewer, is now read from the file with its numbers; a whole or wide read still gets the pointer, which now says how to get numbered lines (`project_memory.MOST_WINDOW_LINES`, `NUMBERED_LINES`). Narrows the earlier decision that every window of a held file is a pointer | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.79 | (suite) a suite run built an agent with this repository as its workspace; LF.73's registry search read the repository's own manifest, asked PyPI and the MCP Registry from inside the tests, and wrote `.harness/mcp-official.json` into the source tree. The suite now keeps the web and the registry search off unless a test turns them on (`tests/conftest.no_research_reaches_the_network`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.80 | (findings run) the gate reported `jose` and `starlette` as imports no manifest declares: `jose` is what the declared `python-jose` installs, `starlette` what the declared `fastapi` requires - and a fixer that declared `jose` would have installed an unrelated, abandoned package of that name. The import-to-distribution alias table knew neither. The check now reads the product's own environment: the installed packages' `top_level.txt` says which import names each provides, their `METADATA` what each requires, so an import of a package a declared one brings is declared; nothing is run (`dependency_drift._what_is_installed`, `_what_a_clean_install_brings`). The table stays for a package not installed. On the live product: deployed code reports both, the new none | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.81 | (deep analysis, findings run) a fix stage compacted eight times in 26 minutes, re-reading the same three test files after each (27 of its 36 calls): the trigger is 80k tokens, the parts re-sent whole on every call - the project memory (114k characters), the request, the specification, the system prompt - about 50k, and the tail kept by count (15 messages) held the file reads, so each compaction left the request at 72-87k, at or above its own trigger (03:17 UTC: 86.7k straight after one; the next, at 87.6k, gained under 1k). LF.47's hysteresis counts messages and three parallel reads are four. The kept tail is now cut to 15% of the trigger as well as to its count, only before a model message so no tool result is parted from its call, at least two kept (`compaction.RequestKeepingSummarization._determine_cutoff_index`, `KEPT_TAIL_SHARE`, wired in `role_agent._compaction_middleware`). After it a compaction leaves at most about 64k here. The memory's own share (EF.5) is the next lever, measured in group 2 | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.82 | (findings run) the manifest-drift defect raised before LF.80 (`jose`, `starlette`) stayed open across the deploy and went to two fixers in turn; each "declared" `jose`, the second broke the product's start (102 tests), and both were reverted. The check made before a fixer is dispatched closed only language-service defects it could read back. A bundled drift defect is now read back the same way: the reconciliation is run again and, when none of the packages it named is still undeclared, the defect is closed without a fixer (`dependency_drift.still_undeclared`, `engineering.no_longer_underlined`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.83 | (findings run) `cd task-management-dashboard && npx vitest` sent with that folder as `working_directory` was refused twice as `task-management-dashboard/task-management-dashboard`: LF.52's `cd` rewrite joined the folder to the working directory whatever it named. When that join is not a folder and the `cd` names one from the workspace's root - or the folder it already runs in - that is where the command runs; a folder inside it is still entered (`agent_toolkit._a_cd_taken_as_the_working_directory`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.84 | (findings run) "The unit tests fail." was raised by round 0 and again by round 1 with a longer output; both stayed open, and round 2 sent two fix stages of forty calls each, one after the other, at the one failure (about 25 minutes a round). Rounds merged their own repeats (`_one_defect_per_cause`) but never checked what was still open. A defect a round raises again - the same first sentence from the same check, still open - now refreshes the open one with the newer description, output and round, and no second fixer is queued; the round still counts it, as failing and against the budget, so a failure that persists still exhausts it (`workflow._refreshed_by_the_round`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.85 | (power loss, 2026-10-20 ~15:15 JST) the host lost power; the stack was back within minutes, orphan recovery found the run and waited for its model server - 15 minutes, every 30 s - and the local model server answered only after that, so the run was left `failed` until it was resumed by hand at 15:45. A recovered run now waits two hours for its model server, still one readiness call every 30 s (`manage.MODEL_WAIT_SECONDS`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.86 | (findings run) with 62 of 62 acceptance tests and 118 of 118 unit tests passing, the final check against the operator's brief sent the finished sprint back: "a user can `filter` ... Nothing in the product names it". The product's search, priority and status filters live in a Python router; the check read browser scripts alone (`.js`, `.ts`, `.tsx`, `.jsx` and a page's inline scripts), so an action built in any server language - and in a Vue or Svelte component - read as missing. It now reads behaviour in every language the harness builds in (`file_kinds.BEHAVIOUR_SUFFIXES`), and a component or page by its `<script>` only, so a class name in markup is still not the feature (`file_kinds.SCRIPTED_MARKUP_SUFFIXES`, `integration_checks._a_required_action_nothing_implements`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.87 | (power loss) a model call's in-flight marker survived on the data volume when the host lost power mid-call; no process was left to remove it, and the next deploy waited at its gate for a call that no longer existed. A worker now removes, as it starts, every marker written before it did (`call_gate.forget_calls_from_before`, `tasks._forget_the_calls_of_a_previous_worker`), and the deploy counts only markers younger than a call can run (`loop.sh deploy`: `-mmin -40`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.88 | (findings run) a rewind to fix the brief check could not be made: listing the run's rewind points held every checkpoint of an 11-hour run whole in memory, and the API's workers were killed for memory three times (08:14 UTC). The history is now read one checkpoint at a time, each kept as the five fields a point needs (`workflow.rewind_points`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.89 | (findings run) with LF.88 deployed the rewind still failed: the listing's own reads and the rewind's search for its checkpoint each read the history through the checkpoint store, which reads it whole, and the API's workers were killed for memory again. A rewind now reads its one checkpoint by id (`workflow.rewind_to`, `graph.get_state` with `checkpoint_id`); the points themselves were listed in the worker (8 GB) to make this rewind. A points listing that never reads the history whole is the follow-up | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.90 | (findings run) the milestone review's security finding asked for `SECRET_KEY` to be moved to the environment; the work order made `auth.py` raise when it was unset, the suite (which starts the product with only `PORT` and `DATA_DIR`) found nothing running, and two fix stages were reverted for breaking more than they fixed. The environment contract already told the building stages; the security reviewer was never told. Its prompt now says a secret comes from the environment with a development default (or is generated at first start under `DATA_DIR`) and a remediation keeps the product starting when the variable is unset (`security_reviewer.SECRETS_HERE`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.91 | (gate run 1, owner's report) the run page's header, progress panel and artifacts stayed on the first specialist consult while the activity showed the later ones, until a reload. The runner announces a `stage_change` only at a gate, and the stages between two gates send agent events alone; the page refreshed on `stage_change` and a few other types only, and a refresh asked for while one was in flight was dropped. The page now refreshes when an event comes from a stage other than the last event's (and on `artifact` events), and a refresh asked for during another runs after it (`RunDashboard.tsx`, both coalesced as before). UI only: the owner counts the gate run as clean | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.92 | (gate run 1) the specification's file plan was a markdown list (``- **`path`** - purpose``) with each directory's files as bare names indented under it; `drafting.planned_files` took each entry's first word, the list marker, and read the plan as its five headings ("Root-level", "Frontend", ...). Fast delivery's work orders made from it held none of the product's files, three services listed only under their directory were given to nobody, and the lead was sent back three times (its second attempt, thinking off, came back with 11 problems). The reader now takes list items, joins a bare name to the directory entry above it (in the same entry or the next), and skips lines that name no path; the plain `path: purpose` and `path - purpose` forms read as before. On the live run's plan: 60 files, against 5 headings | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.93 | (gate run 1, after LF.92's rewind) with the file plan read as files, the plan made from it failed readiness on 32 problems: the project's own package (`task_management_dashboard/`, the project's name as a module) read as a near-spelling of `task-management-dashboard/` - a second project - and stayed outside it; the workspace's top-level `.gitignore` was taken for the project's; and the harness's `vite.config.ts` was given to a work order because what the harness keeps is named from the workspace root and the plan's paths from the project. A path whose first part exists inside the project is now the project's (`work_orders._inside_the_project`), and the specification's work orders name each file from the root before the harness's files are taken out (`planned_work`). On the live run: 0 problems, 55 product files and 7 tests | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.94 | (gate run 1) a pause stops its task with SIGTERM in the middle of a model call; the call's in-flight marker is never removed, and the worker that forgets old markers at its start (LF.87) is not restarted by a pause. The next deploy waited 13 minutes on it. The deploy now counts only markers whose process still runs (`/proc/<pid>` in the worker, the pid being in the marker's name) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.95 | (gate run 1) the CI gate's bundled defect for packages no manifest declares named the files that import them as its files; it was merged under the symptom it causes ("`analytics.spec.js` fails ... importlib"), and the fast rewrite fixed those code files (`database.py`, `main.py`, a page component, a test) and left `requirements.txt` and `package.json` as they were - the defect left open by construction. The defect now names the manifest each language is declared in (`dependency_drift.MANIFESTS`, the first that exists), and in a merge a defect that names a cause leads the symptoms it explains, so its files come first | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.96 | (gate run 1) the gate's certain findings - a dozen unknown imports in five files (`routers/auth.py`, `schemas/__init__.py`, ...) and the undeclared packages - were merged with the test round's failing-test defects into one: a failing test names no file, so it joined every finding it shared a name with, and through it every finding joined every other. One fixer rewrote four files, and each round met the next missing import (`get_settings`, then `get_db`) while Pyright had reported all of them at once. Two groups that each hold a language-service finding now join only when those findings share a file, and findings in one file are always one defect (`_one_defect_per_cause`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.97 | (gate run 1) the gate kept its first 6 language-service findings, one per message: one module's twelve unknown imports could take every place and leave the router that stops the service for a later round. With one file's findings always one defect (LF.96), the cap now counts files: every finding of the first 6 files is kept (`engineering.underlined_in_the_batch`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.98 | (gate run 1) a defect merged with others ("The same problem, as other checks reported it: ...") was rechecked by reading its whole description as one finding: the message ran to the end of what the others said, matched nothing the language service reported, and the defect was closed as "no longer underlined" - two in one round (`database.py`, `main.py`) while Pyright still reported every finding. The recheck now reads the defect's own finding only (`engineering.SAME_PROBLEM_ELSEWHERE`, shared with the merge), and a merged defect stays open while its file is still underlined | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.99 | (gate run 1, deep analysis) the model calls fast delivery makes outside an agent loop - one per drafted file, one per rewritten fix - carried no callbacks and ran in pool threads without the caller's context: 61 drafted files and every rewrite were missing from the transcript, the cost and the activity stream, the run's KPIs counted 16 build calls and "neither model nor tool busy" 40% of the time, and the call gate named their run "none". They now carry the run's callbacks (`observability.direct_calls.config_for_this_run`) and each pool call runs in a copy of the caller's context (`mapped_in_this_context`). KPIs of earlier fast runs undercount these calls | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.100 | (gate run 1, deep analysis) five routers imported `get_settings` - later seven `get_db` - from a module that did not define it; each defect named an importer, and three rounds of rewrites changed the importers and never the module, where one definition fixes them all. An unknown-import finding now says what the module defines and which files import the name from it, and when several do the module is the defect's first file (`language_service.what_the_module_defines`, a per-language table; Python first) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.101 | (gate run 1, LF.100 live) a finding that put the module first still named its importer as a second file; a router importing names two modules lacked joined both modules' findings - sixteen, across two modules and nine routers - into one defect, more than one rewrite covers. Such a finding now names the module alone as its file, its importers in its text | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.102 | (gate run 1) the settings module's defect - its own finding merged with the routers' "`get_db` is unknown import symbol" - was rewritten for its own finding, recorded as fixed without a measurement, and the product stopped on `get_db` a round later: the merge kept only the first finding's expected outcome (the routers' "define it in this module" was cut away), and nothing asked the language service again. A merged defect now carries every member's expected outcome, and a language-service defect is settled by asking the service again: one it still reports is left open (`engineering.still_underlined`, `_settle_the_fix`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.103 | (gate run 1, attempt 2's re-plan) the lead's one work order had neither test cases nor criteria and the plan went back - after the lead had already lost a five-minute reply to reasoning; and the testing work order the harness adds named `config.py`'s test `tests/config.test.tsx`, the page's pattern, in a pack with a Python service. A work order without test cases now takes its criteria, else the specification's cases that name its files, else the sprint's criteria due; and each file's test is named by the pack's pattern for its own language (`unit_test_names`) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.104 | (gate run 1, attempt 2's re-plan) the plan went back on seven problems, six a `python -c` check the readiness check called "not permitted" though the command tool has run such code from a scratch file since LF.60, and one `npm run build 2>&1 \| tail -5` whose trimming changes nothing the command does. The readiness check now passes inline code the tool runs from a file (`planned_commands._runs_its_code_from_a_file`, the `sandbox.CODE_AS_A_FILE` table), and a check's trailing `2>&1` / `\| tail -N` / `\| head -N` is dropped as `cd <project> &&` is (`work_orders._without_output_trimming`). Three tests that held the old refusal now use a command the tool does refuse | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.105 | (gate run 1, attempt 2) the product stopped on a name its module did not define (`TaskCreate` from `schemas/task.py`) through three rounds; each round raised only "the suite fails ...", whose traceback names the importer, so each fix rewrote the importer. The language service names the module, but it runs at the CI gate - once per batch - not per round. A round that finds the product not starting now also raises the language service's certain findings in what the sprint changed (`acceptance_nodes._what_the_language_service_finds`, the gate's own check; `ci.first_commit` when no sprint was accepted yet) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.106 | (gate run 1) the specification planned `playwright.config.ts`; with the file plan read as files (LF.92) a work order drafted it beside the kept `playwright.config.js`, and Playwright loaded the `.ts` one - no base URL, no JUnit report, results outside the evidence folder. Every test failed "Invalid URL" and the harness counted 0 of 0 ("the runner wrote no report"), so each round fell back to file-by-file defects that hid the product's real state (its page build fails). A file with a kept file's name and another extension in the same folder is now the harness's (`contract.owned_by_the_harness`: no work order, no write), and one already written is removed when the contract is enforced before each suite run. Confirmed on a copy of the workspace: with the shadow removed the suite runs and names the build error | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.107 | (gate run 1, attempt 4) the page's build stopped on `import EmptyState from './EmptyState'` for a module with `export const EmptyState`; the TypeScript service kept TS1192 ("has no default export") but not TS2613, the same error when a named export of that name exists ("... Did you mean to use `import { EmptyState }`"), so the language service said nothing about the one error that kept the product from starting. TS2613 is now kept with the import errors that fail at load (`language_service`, both the file's own and its importers'). Proven in the worker image (the host has no TypeScript compiler, where the test skips) | DONE 2026-10-20 | [monitoring handover §0](monitoring-handover.md) |
| LF.108 | (gate run 2) the architect wrote its specification in the model's tag form (`<parameter=product_scope>...</parameter></function></tool_call><tool_call><function=...><parameter=data_contracts>...`) and was cut at the 30,000-token cap; the server's parser put all 111,127 characters into `product_scope`, the model's tags inside it - the document write was refused for them, and every later stage would have carried them. Fields written in tag form inside another field's value are now taken back apart by their tags, and one the reply stopped inside is marked cut off and asked for, as any cut-off answer is (`tool_arguments.with_the_written_parameters_apart`) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.109 | (gate run 2, deep analysis) the specification's file plan held `task_management-dashboard/task_management_dashboard/schemas.py` beside 25 files under `task-management-dashboard/` - the model's typo of the project folder. A near-spelling of the project folder was always read as a second project and flagged "outside the project directory", sending the plan back to the lead (the costliest stage, measured at 5-8 minutes a lost reply). A near-spelling that does not exist in the workspace is now the project, misspelt (`work_orders._inside_the_project`); one that exists is still flagged as a second project | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.110 | (gate run 2) an acceptance author whose fix was already in its files wrote them again and again, each answered "the file already contains exactly this content" (and, before that, "already contained exactly this content"); neither wording was among the results the stall rule counts as nothing new, so it ran on toward its whole 40-call budget. Both now count (`settled_answer._NOTHING_NEW`), so five such results stall the stage to its answer like any other repeat | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.111 | (gate run 2) the environment contract told every stage the product starts from `PORT` and `DATA_DIR` alone, and the specification said in six sections that `SECRET_KEY` is "required at startup. Default: None (service fails if missing)"; the architecture review let it pass, the drafted service refused to start for the suite, and every fix is told to keep what the specification gives. A setting other than those the harness gives that the specification calls required at start ("refuses to start", "fails if missing", "Default: None") now sends it back to the architect, on the bounded repair path the served-files check uses, with the contract's rule - a development default, or a value generated at first start under `DATA_DIR` (`workflow._settings_it_cannot_start_without`) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.112 | (gate run 2) the undeclared-packages defect named both manifests (LF.95) and listed its packages by importing file only; the fix put `recharts`, a JavaScript package, into `requirements.txt`, and every install after failed - eight times in a row, each logged as "`pip install ...` failed" with nothing of what pip said. The defect now says which manifest each language's packages go in ("declare `recharts` in `package.json`; `passlib`, `python-dotenv` in `requirements.txt`", `dependency_drift._where_each_belongs`), and a failed install's note carries the end of the installer's own output (`contract.install_if_the_manifests_changed`) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.113 | (gate run 2) with `recharts` in `requirements.txt` every install failed, nothing that manifest declared was installed, and the product could not start - but the install's note was dropped: `suite.run` called the install and threw its answer away, so no round raised it, and the undeclared-packages check saw the missing packages as declared. The suite now keeps the install's note with its repairs, and a round that finds the product not starting raises a blocking defect naming the manifests and quoting the installer (`acceptance_nodes._the_install_that_failed`, `contract.INSTALL_FAILED`) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.114 | (gate run 2) a fix stage made 41 model calls against its budget of 40 and went on: the budget counts the model's replies in the conversation, and a compaction replaces them with one summary, so the count started again after each - every compacted stage was unbounded, which is how agent fix stages ran 25-35 minutes. A summary now carries how many calls the messages it replaced had made (`compaction.CALLS_BEFORE`, added across repeated compactions), and the budget counts them (`settled_answer._model_calls_used`) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.115 | (gate run 2, deep analysis) a failed install was raised only when the product did not start (LF.113); the product ran on what an earlier install had left, 31 of 34 tests passed, and the `requirements.txt` it would have released - `recharts` in it - failed every install, so a clean checkout could not run it. A failed install is now a defect in every round, whatever the suite measured (`acceptance_nodes.failing_due_defects`) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.116 | (gate run 2) a fix stage lost a reply to reasoning, was compacted, and lost another: the rule that keeps thinking off for the rest of a visit after its second lost reply counts the lost replies in the conversation, the compaction had summarised the first away, and the second was treated as a first - thinking came back on for the reply after (the same flaw LF.114 fixed for the call budget). The summary now carries how many replies were lost before it (`compaction.LOST_BEFORE`), and the count includes them (`settled_answer._replies_that_were_all_reasoning`) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.117 | (gate run 2) the last failing acceptance test stored a Promise as a value - `const id = (await request.get(...)).json().then((r) => r.id)` - so it posted `assignee_id: {}` and the service rightly answered 422; the failure was an ordinary assertion, the pack's test-bug patterns read only failure messages, and the fixers spent an hour bending the product to coerce it. Packs now also give patterns over a test's own source (`_javascript.TEST_SOURCE_BUGS`, by test-file suffix): a failed test whose body matches is the test's bug, and goes back to QA like one whose message matches (`suite.tests_that_broke_themselves`). On the live suite it flags exactly that test | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.118 | (gate run 2) the unit-test defect quoted the last 3,000 characters of the run, and took its cause lines from them alone; the project's command ran the page's tests and then the service's, so the tail began at the page runner's timing line and was the service's passing output - the failing page test (`app-page-load.test.tsx`: "Invalid Chai property: toBeVisible") was in no defect, through two rounds. The cause lines are now taken from the whole run and stated ahead of the tail (`workflow._the_unit_tests_fail`). Proposed, not built: the React pack sets up `@testing-library/jest-dom` for its page tests, whose usual matchers fail without it | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.119 | (gate run 2, owner report) the run page's sprint panel showed a sprint planned again as "Failed: exhausted remediation attempts" with one bug open while its next attempt had passed every acceptance criterion and unit test: an attempt is recorded only when it ends, so the panel had nothing newer than the failed one. The route now adds the attempt under way while the run is live (`workflow.the_attempt_in_progress`, `sprint_summary.sprint_views(..., in_progress)`), with its live defects and round, and the panel draws it as In progress, not as a failure. A completed sprint, a finished run and the plan's end are not re-opened | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.120 | (gate run 2, product audit) every acceptance and unit test passed while 1,883 of the product's 3,167 lines (59%) were modules nothing imported: the service ran from one `main.py` that redefined its models, schemas, auth and routes, the page from one `App.tsx`, and the planned modules beside them imported each other only. The unserved-code check knew only a second copy of a served folder. Now `app.analysis.reachability` walks the import graph from the pack's entrypoints (and the files that import one, a launcher), one row per language family (Python; scripts with launchers, lazy imports and `compilerOptions.paths` aliases), and each served folder's unreached modules join `scaffold.code_the_product_does_not_run` - told to every fixer and recorded at release - with the reached file a copy repeats. Only for packs with `wired_by_imports` (fullstack, FastAPI, Flask, Node HTTP, fullstack Node): Django, Next and other frameworks that load modules by place or name are not checked. Test names come from the pack | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.121 | (gate run 3, acceptance review) a 58,000-character suite showed 24,000 in the review request and told the reviewer to read the rest; the project memory held all ten files whole, so all five reads came back "is in the project memory" and the stall rule withheld the reviewer's tools - a model call and five tool calls for what it already had. With the memory on, a suite file left out of a request now says it is in the memory and is read only if the memory names it as not included (`acceptance.requests._where_a_file_left_out_is`) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.122 | (gate run 3, deep analysis) the run read "neither model nor tool busy" 45% of its first 49 minutes; six minutes of that were the specification's parts written by direct model calls the transcript never saw. LF.99 recorded drafting and rewrites only: the specification's parts, its revisions in place and the section choice, the research brief and the plugin-instruction calls carried no callbacks, and a pool thread lost the run's context. Each now passes `config_for_this_run` and its pool runs `mapped_in_this_context`; a source-wide test fails on any direct model call that is not recorded (probes and health checks outside a run excepted) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.123 | (gate run 3, deep analysis) every deploy into a live run restarts the worker, and the startup sweep's grace kept the run idle twice over its two looks: 120 s each, about three minutes per deploy with the wait for calls in flight. The race it guards was measured at 11 s after a hand-off; `RECENTLY_TOUCHED_SECONDS` is now 60, five times that and the floor the existing safety test sets | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.124 | (gate runs 2 and 3) the brief lists "Due dates and reminders"; both intakes put "Reminder system" under "Deferred scope", the specification deferred testing it, no criterion named reminders, and both products shipped without them. The deferred-requirement check read only user actions. `integration_checks.brief_features_the_text_defers` takes the items of each "and" list in the brief's list items and finds a line that defers one - by its own words or under a deferring heading - and the architecture review is told, beside the deferred actions, that it is a major finding | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.125 | (gate run 3) rewound to `architecture_review` so the review would see LF.124, the review ran without its request: the rewind put the workspace back as it was then, `.harness/stage-threads.json` included, holding the note of the visit a deploy had cut off; a restored note would make the rewound visit carry an old conversation on with no input. A rewind now crosses out every conversation the run wrote down (`abandoned_threads.forget_every_stage`, from `rewind_to`). A defence found while chasing the request that went missing; LF.126 was that failure's cause | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.126 | (gate run 3) twice rewound to `architecture_review`, the review ran with no request - only the project memory - read the specification for itself and passed it. The run was paused on `acceptance_author_0`'s gate, its record still named that gate after the rewind, so the resume answered it on the rewound state; the review node took the decision as a gate's answer and resumed a conversation made up for it. Now a decision with no gate waiting for it is dropped and the stage starts with its request (`_run_gated_agent`), the point a rewind goes back to answers no gate (`rewind_to` clears the pending decision, thread and approval), and the record names the stage rewound to before the resume reads it (`RunManager.rewind_run`). And a rewind to a gate whose revisions are spent cannot send its work back: go back to the gate's first visit | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.127 | (gate run 3) the architecture review is handed the specification as JSON while it is written, so a whole section was one "line": the deferred-requirement checks quoted the first 200 characters of the scope as the line that deferred `reminders`, and read `update` as deferred because the same JSON line deferred something else. Both checks now split escaped line breaks and quote the sentence that defers (`_the_lines_of`, `_the_sentence_of`) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.128 | (gate run 3) rewound to its first visit, the review's request named "reminders" as a deferred brief requirement and a major finding, and its eight findings never mentioned it. In fast delivery the specification is sent back once, so a finding the first review misses is never raised. The workflow now raises it itself, as it does a success measure the specification drops (`_a_brief_feature_the_specification_defers`): a major finding, once per run, never on the revision that would exhaust the cap | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.129 | (gate run 3) the revised specification added reminders with contract lines such as "AC-11 PUT /tasks/{id} -> 200 (updates reminder_at field)" and "AC-11 page /dashboard card task reminder bell icon": a line that follows none of the three forms was dropped at the lock with nothing said, so the release check neither checked nor named it. A trailing parenthesised note is now no part of a line's check, and the lines that still follow no form are kept at the lock and named at release as unchecked (`interface_contract.the_unreadable_lines`) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.130 | (gate run 3) at the lock, 32 of the specification's 58 contract lines followed no form - before LF.129 every one would have vanished. The common shapes were a word naming where a control sits (`page /dashboard form textbox "Title"`), several criteria leading one line (`AC-1 AC-2 AC-3 POST /auth/register -> 201`) and an element named for its role (`select`, `textarea`). These are now read (the role and its name last, the first criterion, `select` as combobox and `textarea` as textbox), and the release reads the lines set aside at the lock again: 13 of the 32 became checks. The 19 left name no accessible control and stay named as unchecked. Proposed: a contract whose lines follow no form goes back to the architect before the lock | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.131 | (gate run 3) a work order's `.env.example` was drafted, refused as a credential path, and handed to the agent loop - where the same rule refuses it again: a model call and an agent's visit for a file no stage may write. Drafting now leaves a credential-shaped path out (no call), the work order is done without it, and its record says the settings take development defaults | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.132 | (gate run 3) a drafted service entry point failed to parse on one line ("parameter without a default follows parameter with a default"), and its whole work order went to the agent loop: drafting drafted once more only with a language-service finding in hand. A write refused because the language cannot parse the file is drafted once more with the error too (`drafting.CONTENT_REFUSALS`) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.133 | (gate run 3) a builder sent one install command twelve times in a row, about every eight seconds, each answered "Requirement already satisfied": a command, so no query rung counted it, and with thinking on the same-call rung did not apply. The same call answered the same four times running now withholds that tool for the next call, thinking on or off, timings aside (`settled_answer._the_same_call_answered_the_same`) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.134 | (gate run 3, deep analysis) the file-ownership table was recorded from the lead's plan - one backend order of 18 files - and fast delivery then split it into orders of three without recording it again. Every later order was refused its own files as "specialist_backend_0's", a stage the dispatched plan does not have: one refused six times on the service's entry point, and the order owning that entry point could not have written it. The owners are now recorded from the work orders as dispatched - after a split, and on every dispatch, so a resumed run is put right (`workflow._record_the_owners`) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.135 | (gate run 3, owner's question) a round's log said only "test_round_1 did not report 5 failing acceptance criteria" - the defects it raised. In that round the product did not start, every criterion failed and the start failure stood for the rest, so it read better than round 2, where the product started and 2 of 13 passed, as the run page said. Each round now logs what the suite measured (`the_round_s_measurement`: criteria passing of all, tests passing of all), and the defects line says it counts defects | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.136 | (owner report) saving the longest single reply as 0 brought the field back as 32,000: both save paths stored 0 as empty, which cleared the override, so the ceiling was derived from the window again - while the budget reads a stored 0 as no ceiling. 0 is now stored as 0; the request to the model then names no `max_tokens` (the server's own limit applies), the timeout keeps its configured value, and thinking left on stays on with no ceiling instead of falling back to the server default, with no zero `budget_tokens` sent to a provider that refuses it. The page says what 0 means | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.137 | (gate run 3, deep analysis) the model server refused one malformed reply ("output that does not match the expected peg-native format", a 500); the transient retry re-entered the stage on a new conversation - 25 calls of reading, edits and test runs thrown away, and the call budget started again from nothing, so the stage ran 41 calls past its 40. A transient model error now leaves the visit's note marked for carrying on (`abandoned_threads.AFTER_A_TRANSIENT_ERROR`), and the retry continues the same conversation from its last saved step: the call is retried, not the stage | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.138 | (gate run 3) the next transient model error after LF.137 started its fixer over all the same: LF.137 patched only the path a visit starts on, and with every gated tool call resumed through a decision, most of a stage's model calls run on the resume path, whose retry still minted a new conversation. That path now leaves the note for carrying on too | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.139 | (gate run 3, its KPIs) a run begun before provenance existed was recorded as one version, `mixed_versions False` on the one commit its last segment named - six hours on several harness versions read as a clean arm for MF.5. Model calls before a run's first segment now count an `unknown` version, so the run is mixed and left out of comparisons | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.140 | (loop operation) `loop.sh deploy` waited an hour for a stage boundary while `loop.sh` was edited, and on finishing bash read the grown file from its old byte offset: `syntax error near unexpected token ')'` at line 389, after the deploy itself had worked. The dispatch is now one group, parsed whole, that exits inside itself | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.141 | (the first LFM run, owner's screenshot) the run page's Progress and Activity said "Not started yet" two minutes in while two stages had finished and a third was working: the steps are built from the run's events, and the activity stream published only reply text, tool calls and results, so a stage answering in structured output alone - an intake, every technology consultation on a model that calls no tools there - published nothing. Each stage visit now publishes one `stage_change` at its first model call; iterated stages (`consult_*`, `defect_fix_*`, ...) carry their family's meaning instead of their bare name | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.142 | (the first LFM run) the architect's first reply repeated `" - "` until 107,596 tokens were spent (3.5 min, cut at the length limit), and the next call was handed all 205,682 characters of it: its reply repeated one JSON block 102 times. A length-cut reply with content was carried whole - only the empty case (all reasoning) was handled. Before each call a cut reply longer than 8,000 characters is now shown as its first 4,000 and a note (naming repetition when its tail compresses past 12:1 - both loops flagged, none of 38 long replies in the run before); the stored history is untouched | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.143 | (the first LFM run) a deploy restarted the worker during the scaffold; on resume the scaffold found the manifest its own first attempt had written, took it for a seeded codebase ("already has a project manifest; it is built on as it is"), refused twice and failed the run. The node's whole-scaffold retry - written for "a worker recreated mid-install" - had never been able to succeed for the same reason. A manifest is now someone else's only when the contract does not record it as this pack's own unproven scaffold of this project | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.144 | (owner's screenshot) after LF.141 the steps list showed the stages, but the Activity tab still said "Nothing to show yet" with two events in the log: the feed kept only replies, tool calls and decisions, so a stage answering in structured output alone never appeared there. Its start (`stage_change`, with its meaning) and its outcome (`log`) are now quiet note rows in the feed | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.145 | (owner's screenshot: "this ux is bad") the Progress pane's sticky sprint heading and the steps' icons shared one layer, so icons scrolled over the heading and hid the first title; and every finished step took a title, a description and a status line, so the short pane showed two steps and not the one in flight. The heading is above the icons; a finished step is one line (title and time, its description on hover); the step in flight is scrolled into view | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.146 | (the second LFM run) the plugin instructions' auxiliary call - the stack's framework list, and the notes for a framework the store does not know - asks for a 2,048-token reply with reasoning off; a model that reasons on every reply whatever it is asked spent all 2,048 tokens thinking and wrote nothing (`finish_reason: length`, no text). Known frameworks were still matched in the stack text; an unknown framework's notes would have been lost. A reply that is all reasoning at its cap is now asked once more with four times the room | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.147 | (owner: "make it more presentable") the Progress pane: a progress bar under its count; a sprint's earlier finished steps fold into one row ("7 earlier steps · 3m 30s") that opens and folds again, with the last finished step and the step in flight shown; the step in flight shows how long it has been working, live; every stage a run makes has words for its name (`research_brief`, `drafting`, `defect_fix`, `advice_review_*`, `code_review_*`, `stack_setup_*` read as their raw names) | DONE 2026-10-21 (not deployed: ships with the next deploy, owner) | [monitoring handover §0](monitoring-handover.md) |
| LF.148 | (LFM smoke run run-abd8b897, failed 16:36 JST) the sprint planner wrote a whole plan in each of six replies, each a near miss of its schema - a sentence where a list was wanted, a list where a line was, a dependency as the number 1, fields the schema has no place for - was told which fields were wrong, looped, and failed the run. An answer written as text never went through the shape repair a tool call's arguments get. It does now (`settled_answer.validated_leniently`, both places a text answer is validated), with three more repairs in `tool_arguments._repaired`: a list of lines where a text is wanted, a number where a text is wanted, a field a closed schema forbids dropped - and only for an object most of whose top-level keys are the schema's own. All six replies are accepted | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.149 | (same run) its error said the stage "spent its entire output budget before writing anything ... no text", of replies of 78,000-129,000 characters, and named a higher output limit as the fix. A cut reply with text now has its own message: the model does not stop, a higher limit costs more, look at repetition and the schema's errors | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.150 | (owner 2026-10-21: "if replies are lost to reasoning, reduce the scope so the model answers with thinking on"; researched first - overthinking: arXiv 2505.00127, 2505.17813; least-to-most decomposition: Zhou et al. ICLR 2023; structured-output reliability falls with size; the harness's own specification parts at 4-15k tokens where the whole ran out at 33k) a stage whose last reply ran out of room - reasoning to the limit or an answer that would not stop - was asked the same thing again, thinking off (ignored by a model that always reasons), then on fresh conversations. Now, once per stage, before the restarts, its answer is asked for in parts with thinking left as it is: the schema's fields four at a time, a list of objects as a one-line outline then item by item, each part seeing the parts before it (`app.agents.answered_in_parts`, `workflow._the_answer_in_parts`). A part that cannot be read leaves the stage to its restarts as before | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.151 | (deep audit of all 273 transcripts, owner: "check whether any such findings were missed") every open defect of the same owner was bundled into one fixer's request, with no limit and no test of relatedness. Across every recorded run: one defect per fixer fixed 64% (median 18k output tokens, 11% of stages cut off at the reply limit), 2-3 fixed 53% (58k, 47%), 4+ fixed 26% (73k, 62%). Acceptance defects arrive one per root error, so bundles joined unrelated causes, and a defect an earlier fix resolved is closed by measurement whether bundled or not - bundling bought only a wider question. A fixer is now shown only defects that share an affected file with its own, two at most (`MOST_BUNDLED_DEFECTS`) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.152 | (same audit) findings that need many runs were missed because every audit read only the live run. `loop.sh patterns [since]` (`scripts/loop/patterns.py`) measures across every transcript: reply health per stage family (cut off, looping, all reasoning, p50/p90), fix outcome by bundle size, and the tool failures that recur across runs. Each deep analysis reads it | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.153 | (owner 2026-10-21, after the deep audit) a fix, build or test stage that cannot answer is recorded as blocked and the run goes on; a planning stage that ran out of every way to answer failed the run (one run's sprint planner, after six replies). The sprint planner now gives way to one sprint over every locked criterion, the intake's success measures and the specification's file plan (`scrum_master.a_plan_the_harness_writes`), recorded as the harness's in the decision log and listed among the release's gaps. Only for `StageGaveNoAnswer`, the stage-spent-every-answer error; the architect and the reviews keep no fallback (owner: a made-up specification or an unreviewed pass would mislead every later stage) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.154 | (suite) a test module importing `app.server.auth` at its top level errored at collection when its xdist worker had not loaded auth another way first: `ENV=development` was set in a session fixture, after collection. Set at conftest import | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.155 | (LFM smoke run run-a4876ad2, deep analysis) an acceptance test ran `subprocess.run(["bash", "start.sh"])` - the script starts the service and never returns - and the suite hung to the command's 300-second limit with no test reporting; locked, every test round would have hung. pytest has no per-test limit of its own (JavaScript's runners do): every pack that writes a `pytest.ini` now sets `timeout = 90` and installs `pytest-timeout`, so such a test fails alone and every other test reports | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.156 | (same run) writing the black-box acceptance suite drew "imports nothing from the project ... Import the module under test (`import { addTask } from './app.js'`)" - JavaScript advice on a Python file, and wrong for a suite meant to meet the product from outside. The check knew only relative imports, so every Python test file drew it. A test importing a module the project has by name counts as testing it; files in the locked acceptance suite are exempt; the note no longer names one language's syntax | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.157 | (same run) the acceptance writer, its suite hung by LF.155's test and no result to read, decided the product had to be built and spent fourteen calls trying: `database.py`, `models.py` four times, `main.py` by another path, `edit_artifact`, then `python3 -c` and a shell heredoc. Each was a different file or tool, so the repeat count kept per file never fired, and the acceptance-suite and test-round refusals had no count at all. A stage-wide count of writes refused outside the stage's own files now leads every such refusal from the third: how many, that every one will be refused, finish and answer. Recorded, not changed: a command the stage may run can still write a file its tools may not (the last attempt's script tried) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.158 | (same run) the acceptance writer, its terminal withheld, ran `run_validation` with `working_directory="/workspace/notes-api"` then `"/workspace"` - the sandbox's own mount, which every command's output shows - and was told each time it was "not a directory in this workspace". The read tools rewrote an invented root and the command tools did not: a command's working directory now gets the same rewrite (host path, invented top directory, the sandbox's mount) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.159 | (same run) the root of its 40-minute loop: QA wrote a test that ran `bash start.sh` (a service that never exits), the suite hung with no result, and QA spent forty calls starting the service and writing the product. Neither QA nor its reviewer was told that the suite's own setup starts a product that keeps running. Both are now (any stack: a service or a page's server; a program that runs and exits is still run by its tests) | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.160 | (same run) the suite's timeout went back to QA as "timed out ... FFF.F.F.FFF." - twelve tests finished, the thirteenth never returned - and QA read it as a missing product and tried to write models.py again. A suite that never finished now goes back with the test it stopped at named (from a runner's per-test progress marks and the files' own test order) and the cause stated: a test waiting on something that never ends, most often a running product it started itself, which the setup already starts - a test problem, nothing of the product missing | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.161 | (LFM smoke run run-9a475ffb, LF.150's first live use) the architect's answer in parts: six parts of 3-15k tokens and a twelve-line outline of its decisions came back valid where the whole had run out at 33k, then decision 1 came back as the whole specification again - each item was shown every part written so far, and echoed it. An item now sees the outline, the items before it and only the names of the other parts; a reply is read for any object that is the part, not only its first; a part that cannot be read is asked once more, plainly | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.162 | (run-9a475ffb, deep analysis) answer-in-parts for a stage that did work: the acceptance writer's whole answer ran out, and its parts, asked with only the stage's request, reported files it never wrote (`acceptance/test_ac_tests.py`), a conftest that "starts the service via start.sh", and checks of files that did not exist with invented exit codes. The parts are now given the stage's own record from its conversation - every write, edit and command with its outcome, and its last words - and told to report only what it shows | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.163 | (run-9a475ffb) the QA lead sent the suite back with fifteen findings, every one "test_acN fails with 404 because ... is not implemented" - the suite is written before the product and is meant to fail now; its prompt says so, and the model wrote them anyway. QA, handed them, tried again to write the product. Findings that only say a test fails because the product lacks something are dropped before the send-back (`suite.findings_about_the_suite`); one that also faults the test is kept; none left is an approval | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.164 | (run-9a475ffb, a fix stage) `cat /workspace/notes-api/notes_api/storage.py` and `ls /workspace/notes-api/notes_api/` - "No such file" each time, for files the read tools had just shown under that spelling: a command argument was rewritten for `/project/file` but not with a root in front (the sandbox's `/workspace`, or an invented one). Such an argument now becomes the workspace path less its first part when that exists. Recorded, not changed: a test using the shared `client` fixture errored at setup once in three of today's suites, a different test each time, passing alone | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.165 | (run-9a475ffb) the dispute rightly found the AC-18 test could never pass (it assumed an empty store the suite's shared service did not have) and reopened the suite for it; QA's repair, told "change only the tests named above", wrote the file back with that one test in it - seventeen criteria lost their tests and the suite went back for all of them. A reopen now records the tests under repair (`suite.repairing`), and a write to a suite file during a repair that drops any other test the last locked version had is refused, naming them; locking again ends the repair | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.166 | (suite) four of the day's suites had a different `client` test error at setup, each passing alone: `_prepare_multiprocess_dir`, run by a metrics test with `PROMETHEUS_MULTIPROC_DIR` set, switches `prometheus_client`'s value class for the life of the process, and only the variable was put back, so the next app built in that xdist worker failed creating its first metric. Reproduced deterministically by running the two tests in order; an autouse fixture now restores the value class after every test | DONE 2026-10-21 | [monitoring handover §0](monitoring-handover.md) |
| LF.167 | (Measure gate run 1, run-650d812f; filed, not deployed into it - MF.4) fast delivery's rewriting fix took `tasks-api/test-results/acceptance.xml` - the runner's report, named in the failure text - as the file to rewrite, two defects in a row; both stayed open. A file the project's own ignore rules exclude (a report, a build, a cache) is never a rewrite's target, asked of git so every stack's ignore file answers | BUILT 2026-10-21, held for the Fix batch | [monitoring handover §0](monitoring-handover.md) |
| LF.168 | (Measure gate run 1, deep audit: a **false acceptance** - 21/21 criteria and 67/67 locked tests inside, 0/10 hidden) the specification designed its own `start.sh` (`exec python tasks_api/app.py`), drafting overwrote the pack's working one (`.venv/bin/python -m gunicorn ...`), and nothing in the run ever ran it: the suite's setup started the service by the framework's own command, AC-17's test had become a static check (LF.159), and the contract probe had no HTTP runner. With the pack's `start.sh` put back the same product scores 10/10. Every service pack's suite now starts the service the way the brief does - the project's `start.sh` when it has one (Python packs' conftest, Node and other services' Playwright `webServer`), its whole process group stopped after - so every locked test proves the entrypoint the customer runs | BUILT 2026-10-21, held for the Fix batch | [monitoring handover §0](monitoring-handover.md) |
| LF.169 | (Measure gate run 2, deep analysis) both gate runs' specifications designed their own `start.sh` - the architect's layout facts named the served files, the test folders and the kept files, never that the setup had already written a working start script; run 1's design was drafted over it. A pack that writes `start.sh` now says so in the layout facts, with its command, and that the file plan keeps it unless the brief asks for something it does not do | BUILT 2026-10-21, held for the Fix batch | [monitoring handover §0](monitoring-handover.md) |
| LF.170 | (owner approved 2026-10-21) the command loophole: a stage's file tools refused a write outside its own files, its commands did not - the LFM acceptance writer, refused product code a dozen ways, ran `python3 -c "open('notes_api/storage.py','w').write(...)"` and the sandbox ran it. For the stages that never run beside a builder (the acceptance writer, test rounds), the files the stage may not write are held before each command (content, files the project ignores excluded) and anything the command changed or made among them is put back or removed, told in the result and counted with the stage's other refusals. Builders and fixers are not held: they may write the product, and run beside one another | BUILT 2026-10-21, held for the Fix batch | [monitoring handover §0](monitoring-handover.md) |
| LF.171 | the project memory opens the request and the request can run to 70,000 tokens after it: on gate run 2 (Measure), 24 of 142 tool-calling replies did nothing but read files the memory held - the lead's three, and every review's first move - each a model call with its reasoning, answered with a pointer. The opening request now ends with one line naming the files the memory holds whole (`project_memory.files_held_line`, at most 30 names), fixed for the visit so the prompt cache holds; test `test_the_opening_request_ends_by_naming_the_files_the_memory_holds.py` | BUILT 2026-10-22, held for Fix batch 2 | [monitoring handover §0](monitoring-handover.md) |
| LF.172 | a product that crashes at start, under a suite that starts the service per test, ran every test and failed each at setup with the same crash; the never-started check asked only when no test ran, so Measure 2 run 1's startup crash (`main.py` calling a function `database.py` did not define) became six criterion defects, six fixers rewrote their criteria's files and all six were left open. `suite.every_failure_is_the_start`: when every failing test failed with the service not starting, the round's problem is the product not starting - one blocking defect with the crash; test `test_a_service_that_crashes_at_start_in_every_test_is_one_defect.py` | BUILT 2026-10-22, held for Fix batch 2 | [monitoring handover §0](monitoring-handover.md) |
| LF.173 | a fix is reverted only for breaking what passed before it; with every test red (the service not starting) nothing can break, so on Measure 2 run 1 a fast rewrite for the start script wrote seven calls to `database.get_db_sync`, which `database.py` never defined, was kept, and the service crashed at start for every fixer after it. `engineering.after_a_fix` now also reverts a fix that made nothing pass when the language service is sure a line it wrote fails when it runs (`what_the_fix_made_certain_to_fail`: findings on lines `git diff -U0` shows the fix added, or anywhere in a file it created); test `test_a_fix_that_only_adds_certain_failures_is_reverted.py` | BUILT 2026-10-22, held for Fix batch 2 | [monitoring handover §0](monitoring-handover.md) |
| LF.174 | on Measure 2 run 1 a fixer ran one test command twice in a row and another three times, each with the same result and no file changed between, reasoning 4,000-20,000 tokens "to reproduce the failure" before each run (about 9 minutes); the repeated-call guard waits for four in a row. A test command whose pass and test counts equal the last run of the same command in the same place, with no workspace file changed since that run, now says so in its result (`sandbox.SAME_RESULT_NOTHING_CHANGED`): running it again cannot show anything new; test `test_a_test_run_that_cannot_show_anything_new_says_so.py` | BUILT 2026-10-22, held for Fix batch 2 | [monitoring handover §0](monitoring-handover.md) |
| LF.175 | whether a defect's own tests pass was judged by the exit code of each acceptance file naming its criterion, and a file holds tests of several criteria: on Measure 2 run 1 AC-9's six tests passed while the same file's later-sprint AC-8 test failed, so AC-9 was left open each time its fix was measured and the fixer was told its tests still failed. `per_file.each_file(naming=...)` now judges each file by the tests whose own names carry the criterion, from the run's report (`_its_own_tests`; the suite name is the file, so it is not read), falling back to the exit code when no test carries it; test `test_a_defect_is_judged_by_its_own_tests_not_their_file.py` | BUILT 2026-10-22, held for Fix batch 2 | [monitoring handover §0](monitoring-handover.md) |
| LF.176 | a test whose writer is not recorded (drafting writes through direct calls) could be moved out of the suite: on Measure 2 run 1 a fixer was refused deleting `tests/test___init__.py`, was told by the refusal to rename then delete it, and moved it to `test___init__.py.bak` - allowed, and the suite lost the test. In a run, a move of a test this stage did not write to a name no runner collects (no longer a test's name, or another extension) is now refused (`TEST_MOVED_OUT_OF_THE_SUITE`), and the delete refusal no longer offers the rename; outside a run and for a scratch-named file the way out stays; test `test_a_test_another_stage_wrote_cannot_be_moved_out_of_the_suite.py` | BUILT 2026-10-22, held for Fix batch 2 | [monitoring handover §0](monitoring-handover.md) |
| LF.177 | the timing report, the run KPIs and the run page's stage usage paired a reply with one open request per stage, so a stage that asks several at once (the specification written in parts) had each request overwrite the last: Measure 2 run 1's report read 20% of its wall as "neither" while the model answered, and the report dropped those replies' calls and tokens. All three now keep each stage's open requests oldest first (`run_timing.py`, `run_kpis.kpis`, `stage_usage.stage_usage`/`recent_calls`); test `test_the_timing_report_counts_a_stage_s_parallel_calls.py` | BUILT 2026-10-22 (measurement; the KPIs of runs before it under-count parallel model time) | [monitoring handover §0](monitoring-handover.md) |
| LF.178 | the server check matches a server's name anywhere in a command, and `fastapi`, `uvicorn` and `serve` are also package names: on Measure 2 run 2 a fixer's `python -m pip show fastapi starlette` was refused twice as a server that "runs until it is stopped". A package manager's lookup subcommands, by tool (`sandbox._PACKAGE_LOOKUPS`: pip show/list/freeze, npm view/ls, cargo tree, go list, ...), are never a server; test `test_a_package_lookup_is_not_a_server.py` | BUILT 2026-10-22, held for Fix batch 2 | [monitoring handover §0](monitoring-handover.md) |
| LF.179 | knowledge newer than the model: on Measure 2 run 2 the product put the account's integer id in a token's `sub` claim, PyJWT 2.10+ refuses that on decode, every signed-in request answered 401 and eight criteria failed behind it for about an hour of fix stages. The Python stack guidance in `plugins/seed.py` now says a token's `sub` must be a string (`_PYTHON_TOKENS`, beside the passlib/bcrypt note); test `test_python_stages_are_told_a_token_s_subject_is_a_string.py` | BUILT 2026-10-22, held for Fix batch 2 | [monitoring handover §0](monitoring-handover.md) |
| LF.180 | `kpi_ledger arms` matched a commit exactly while the ledger keeps the full one, so `arms 039ad84 20dcdfbe` found no run of either arm after Measure pair 2; an arm is now the runs whose one commit starts with the one named (a mixed run still never counts); test `test_an_arm_is_named_by_its_short_commit.py` | BUILT 2026-10-22 | [monitoring handover §0](monitoring-handover.md) |
| LF.181 | the undeclared-import check (K.4) counted every Python manifest as a declaration, read or not: on Measure 3 run 1 `bcrypt` was in `pyproject.toml`, the pack's install read only `requirements.txt` and `requirements-dev.txt`, the check found nothing, and the product did not start nor the unit tests import (the third run of three to lose its first round to an undeclared package). Where the project's install is recorded, only the requirement files it names count, and `pyproject.toml` only when it installs the project itself (`dependency_drift._what_the_install_reads`); test `test_a_package_only_a_manifest_the_install_never_reads_declares_is_undeclared.py` | BUILT 2026-10-22, held for Fix batch 3 | [monitoring handover §0](monitoring-handover.md) |
| LF.182 | a suite against one long-lived service shares its store across tests, and only the FastAPI pack told the suite's writer so: on Measure 3 run 1 (Flask) `test_ac7_no_item_stored` asserted a signed-in account's list was empty after signing in to an account an earlier test had filled - it could pass for no product, a fix stage was spent on it, and the suite was reopened and reviewed twice. Every pack of kind `http_api` or `fullstack` now has `requests.SHARED_STORE` added to its acceptance guide unless the guide already says it; test `test_every_service_suite_writer_is_told_the_store_is_shared.py` | BUILT 2026-10-22, held for Fix batch 3 | [monitoring handover §0](monitoring-handover.md) |
| LF.183 | a fix stage that changes nothing and blames the locked suite is sent to a dispute only when its blockers name a suite *file*; on Measure 3 run 1 the fixer reported "test_ac7_persistence_after_restart has an unfixable typo" (the repaired test signed in as the wrong account), no dispute was held, and the next round sent the same criterion to another fixer. `workflow._blames_a_locked_test` now also matches the locked tests' own names (`suite.declared_tests`, word-bounded, parameters dropped); test `test_a_fixer_that_names_a_locked_test_by_its_name_blames_the_suite.py` | BUILT 2026-10-22, held for Fix batch 3 | [monitoring handover §0](monitoring-handover.md) |
| LF.184 | the no-dependency rule read any line of `product_intake.md` or `technology_stack.md` holding "no external dependencies" as the brief's own words: on Measure 3 run 2 the stack selector's rationale said SQLite "suits this single-user workload with no external dependencies" (no database server), and every install of the product was refused - the `pip install -e .` that would have installed its `pyproject.toml` packages among them - with advice about Node's `node:test` to a Python project. A line now counts only in a section headed constraints or when it opens with the phrase; the refusal's advice follows the command's ecosystem (`_WITHOUT_AN_INSTALL`); test `test_a_stack_rationale_that_mentions_no_dependencies_is_not_the_brief.py` | BUILT 2026-10-22, held for Fix batch 3 | [monitoring handover §0](monitoring-handover.md) |
| LF.185 | the dispatch re-measure (L.3) closed a defect as fixed whenever its own tests passed alone - also when nothing had changed since the round measured them failing in the whole suite: on Measure 3 run 2, across three attempts at sprint 1, criteria were closed this way and raised again next round on the same product, fixers were sent at order- or state-dependent tests, and the sprint failed twice. The suite's saved result now carries a fingerprint of the product it measured (`app/acceptance/unstable.py`: HEAD plus the uncommitted product diff, harness and runner output left out); a criterion that passes alone on an unchanged product goes to a dispute with that reason while one may be held, and closes as before otherwise; test `test_a_criterion_that_passes_alone_on_the_same_product_is_unstable.py` | BUILT 2026-10-22, held for Fix batch 3 | [monitoring handover §0](monitoring-handover.md) |
| LF.186 | the cause LF.181 now names is still made at drafting: on five gate runs in a row a Python service's packages were drafted into `pyproject.toml` while the pack's install read only `requirements.txt`, and a fix round was spent each time. The contract block said "add dependencies the normal way". It now names the manifests the recorded install reads (`contract._where_dependencies_go`: the `-r` files, that a package listed elsewhere is never installed, a test-only tool in the development file; another ecosystem's install command named), and every drafted file's request carries the same line (`drafting._where_dependencies_go`); test `test_every_stage_is_told_where_this_project_s_dependencies_go.py` | BUILT 2026-10-22, held for Fix batch 4 | [monitoring handover §0](monitoring-handover.md) |
| LF.187 | an undeclared-package defect (K.4, LF.181) was settled by the unit tests that mention the package: on Measure 4 run 1 the fixer declared `bcrypt` and `pyjwt` in `requirements.txt` - the reconciliation then found nothing undeclared - and the defect was left open, those unit tests failing for another reason. `_the_defect_s_tests_in` now settles such a defect by `dependency_drift.still_undeclared`, the check that raised it; test `test_an_undeclared_package_defect_is_settled_by_declaring_it.py` | BUILT 2026-10-22, held for Fix batch 4 | [monitoring handover §0](monitoring-handover.md) |
| LF.188 | a stage's opening request held each project file twice: the project memory (every stage agent carries it) and the project snapshot before the request. On Measure 4 run 1 every call of a fix stage carried 14 files twice, about 24,000 characters, and the snapshot named `acceptance/test_items.py` "not included, read it" while the memory held it and refused the read - the fixer concluded the memory held only summaries. `project_snapshot.for_a_stage` gives the snapshot only when the project memory is off, and the empty-project notice always; `_run_gated_agent` uses it; test `test_a_stage_is_given_each_file_once.py` | BUILT 2026-10-22, held for Fix batch 4 | [monitoring handover §0](monitoring-handover.md) |
| LF.189 | under `RELEASE_DOCS_REQUIRED` (PN.2) a release with no README was sent back to the lead for one, a model round, while every fact a README needs is the harness's: Measure 3 run 1 passed 10/10 hidden tests with no README, so with the switch on every release would have gone back. `release_docs.complete_the_handoff` writes the pack's install, start and test commands and a route table from the locked interface contract into the README (an own README keeps its words and gains only what it lacks); what the harness cannot know is still asked for; `delivery.release` calls it before the check; tests in `test_a_release_needs_a_readme_and_a_summary_of_what_it_serves.py` | BUILT 2026-10-22, Fix batch 4 | [monitoring handover §0](monitoring-handover.md) |
| LF.190 | `DEFECT_CALL_CAP` (AY step 4): `defect_budget.calls_in` with no attempt start counted every call ever made under the stage's name, and a name recurs across a sprint's attempts; found running the whole suite with every switch on. Now None; test `test_a_defect_s_calls_are_bounded_across_attempts.py` | BUILT 2026-10-22, Fix batch 4 | [monitoring handover §0](monitoring-handover.md) |
| LF.191 | `LESSON_DISTILLER`: lessons are filed under the run's pack (`python-http-api`) and prompts looked them up only by the stack document's frameworks, so the two the owner approved never reached a prompt; a lesson's rule named one product's packages; a run's recurrence was counted on every `loop.sh kpi`. The plugin middleware adds the pack's name to the keys, the rule names no packages, recurrence is counted once per run id; tests in the two lesson test files | BUILT 2026-10-22, Fix batch 4 (group 2 review) | [monitoring handover §0](monitoring-handover.md) |
| LF.192 | `INTERFACE_CLASH_CHECK`: a definition moved to another file of the batch, or a common name (`get`) another file uses from elsewhere, was a major defect no fixer could settle. A name added anywhere in the batch, or defined in the using file, or used by a file that never names the removed file's module, is no clash; `lstrip("./")` (it ate `.github`'s dot) replaced by a prefix strip in the group 2 modules; tests in `test_two_work_orders_that_disagree_on_an_interface_are_a_defect_at_once.py` | BUILT 2026-10-22, Fix batch 4 (group 2 review) | [monitoring handover §0](monitoring-handover.md) |
| LF.193 | `PROJECT_GRAPH_*`/`CODE_GRAPH_TOOL`: `.project-graph.json` was written at the workspace top, committed, and led the code reviewer's capped diff; now `.harness/project-graph.json`; vendored and build-output folders are not walked; a name the graph does not show is said to be unseen, not undefined (it invited a second definition); tests in `test_a_request_gets_its_files_neighbours_from_the_code_graph.py` | BUILT 2026-10-22, Fix batch 4 (group 2 review) | [monitoring handover §0](monitoring-handover.md) |
| LF.194 | `ASK_SPECIFICATION`: the architect's 800-token answer was reasoning to its end on a server that reasons by default; asked without reasoning; test in `test_a_builder_may_ask_the_specification_a_bounded_number_of_questions.py` | BUILT 2026-10-22, Fix batch 4 (group 2 review) | [monitoring handover §0](monitoring-handover.md) |
| LF.195 | `VERIFY_AFTER_WRITE`: a write that did not happen (`{"error": ...}`, a refusal) still ran the defect's tests and spent one of six checks; test in `test_a_write_in_a_fix_loop_is_followed_by_the_defect_s_test.py` | BUILT 2026-10-22, Fix batch 4 (group 2 review) | [monitoring handover §0](monitoring-handover.md) |
| LF.196 | `FIX_CYCLE`: a defect with no tests of its own got three candidates and the first that changed anything was kept unchecked; now no candidates for it; test in `test_a_defect_is_fixed_by_rewriting_its_files.py` | BUILT 2026-10-22, Fix batch 4 (group 2 review) | [monitoring handover §0](monitoring-handover.md) |
| LF.197 | `STABLE_TOOLS`: the withheld set lived on the middleware instance, so a withheld write or command that paused for approval ran on the rebuilt agent; and its refusal matched neither the refused nor the nothing-new patterns, so stall and repeat escalation never fired. Kept in the stage's memory; the refusal opens `Refusing:`; test in `test_a_withheld_tool_called_anyway_is_not_run.py` | BUILT 2026-10-22, Fix batch 4 (group 2 review) | [monitoring handover §0](monitoring-handover.md) |
| LF.198 | `STABLE_TOOLS` with a research brief: the architect's research tools, no longer removed, ran up to their whole shares; `over_its_share` refuses when the reading was done for the stage; test in `test_a_withheld_tool_does_not_change_the_tool_list.py` | BUILT 2026-10-22, Fix batch 4 (group 2 review) | [monitoring handover §0](monitoring-handover.md) |
| LF.199 | `RELEASE_DOCS_REQUIRED`: a route with a trailing slash never read as documented, and a project named like a harness record (`book-reviews`) had every document left out - each sent the release back twice; test in `test_a_release_needs_a_readme_and_a_summary_of_what_it_serves.py` | BUILT 2026-10-22, Fix batch 4 (group 2 review) | [monitoring handover §0](monitoring-handover.md) |
| LF.200 | AY in parallel mode: a batch of fixes skipped the call cap, the check after a write and the attempt record; and the cap missed the harness's own rewrite, candidate and localisation calls (recorded as stage `defect_fix`). Both wired; tests in `test_defects_are_fixed_side_by_side.py`, `test_a_defect_s_calls_are_bounded_across_attempts.py` | BUILT 2026-10-22, Fix batch 4 (group 2 review) | [monitoring handover §0](monitoring-handover.md) |
| LF.201 | `RELEASE_AUDITS`: the secret scan read `.agent-home/` (a seeded workspace's module cache holds libraries' test keys) and documented example keys; the Python CI audit audited the runner's pip, not `.venv`; test in `test_a_release_scans_for_secrets_lists_licences_and_audits_in_ci.py` | BUILT 2026-10-22, Fix batch 4 (group 2 review) | [monitoring handover §0](monitoring-handover.md) |
| LF.202 | a criterion whose every locked test also proves a later sprint's criterion was planned in a sprint where it could not pass: on Measure 4 run 1 sprint 1 held AC-7 (accounts and items survive a restart) and sprint 2 the item routes; its only test, tagged AC-7 and AC-20, creates an item, restarts and lists items; `suite._judged` keeps a criterion's waiting tests when it has no other, so sprint 1 spent two fix rounds (~75 min) on it and was planned again. `scrum_master.with_each_criterion_where_its_tests_can_pass` moves each criterion to the earliest sprint in which one of its tests can pass, after `with_every_criterion_assigned`; test `test_a_criterion_is_planned_where_a_test_of_it_can_pass.py` | BUILT 2026-10-22, Fix batch 4 | [monitoring handover §0](monitoring-handover.md) |
| LF.203 | a release held back (failing criteria, a missing README, a credential) hands on with no milestone plan, so the lead plans afresh - and the planning request never read the hold's comments: two blind re-sprints. The planning request now carries "Why the release was held back" when `release_attempts` > 0. Also `RELEASE_DOCS_REQUIRED`: a README at the workspace root names the project directory for its commands, a pack with no start script names its kept `start` script; tests in `test_a_release_needs_a_readme_and_a_summary_of_what_it_serves.py` | BUILT 2026-10-22, Fix batch 4 (deep review) | [monitoring handover §0](monitoring-handover.md) |
| LF.204 | `RELEASE_AUDITS`: `.env.example`/`*.sample`/`*.template` files, placeholder tokens (`ghp_xxxx…`, one repeated character, `your-`, `changeme`) and nested toolchain folders (`app/vendor/…`) held the release; Java had no CI audit. Test in `test_a_release_scans_for_secrets_lists_licences_and_audits_in_ci.py` | BUILT 2026-10-22, Fix batch 4 (deep review) | [monitoring handover §0](monitoring-handover.md) |
| LF.205 | `ASSUMPTIONS_GATE`: intake sent back by its review recorded every assumption again, and the architect's block listed each question twice, never the owner's answer; recorded once per question, the block keeps the last answer per question | BUILT 2026-10-22, Fix batch 4 (deep review) | [monitoring handover §0](monitoring-handover.md) |
| LF.206 | `INTERFACE_CLASH_CHECK` (after LF.192): a moved name still imported from its old file was no clash (the move suppression ran first), a name in a comment or string was one, and a clash was never re-checked at settlement (closed on any named test, held open on none). The using file must import the name from the removed file's module, comments and strings are blanked, `still_clashing` re-checks at settlement like the language service; `ASK_SPECIFICATION`'s `answers.json` is written under the lock through a temporary file (six parallel askers corrupted it). Tests in `test_two_work_orders_that_disagree_on_an_interface_are_a_defect_at_once.py` | BUILT 2026-10-22, Fix batch 4 (deep review) | [monitoring handover §0](monitoring-handover.md) |
| LF.207 | undeclared packages were read by a line pattern: on Measure 4 run 1 a docstring line "import of ``tasks_api.main`` which would..." raised a package `of`, and the fast rewrite declared `of==0.0.1`. Python imports are read from the syntax tree (the pattern only for a file that does not parse); namespace packages, sibling modules and the test tree's helpers are local, not undeclared (each was a defect no manifest could settle after LF.187); test `test_an_import_is_read_from_the_syntax_tree_not_a_docstring.py` | BUILT 2026-10-22, Fix batch 4 (deep review) | [monitoring handover §0](monitoring-handover.md) |
| LF.208 | failed tries counted only reverts: a fix measured and left open counted none, so candidates, the judgement-model escalation and the last-attempt note waited for a revert that never came; and a recurring problem counted one earlier generation only (calls and tries of the rest lost). Tries count attempt records too; `recurrence_chain` follows every generation, nearest first, in tries, the call cap and the ledger's earlier attempts; test `test_a_problem_raised_again_and_again_counts_every_earlier_try.py` | BUILT 2026-10-22, Fix batch 4 (deep review) | [monitoring handover §0](monitoring-handover.md) |
| LF.209 | AY: a linear fix's approval pause reset the call cap's start (`fix_started` now carried), the batch's start was left in every checkpoint, the check after a write ran after writes that changed nothing and missed `replace_lines` | BUILT 2026-10-22, Fix batch 4 (deep review) | [monitoring handover §0](monitoring-handover.md) |
| LF.210 | LF.202 refinement: a move that would empty sprint 1 discarded every move (the measured AC-7 shape recurred when sprint 1 held one such criterion); only sprint 1's own moves are dropped. LF.185: the product's state is taken before the dispatch probe (a committed store file rewritten by the probe made every product "changed"). LF.183: a one-word test title (`describe('Accounts')`) read as blaming the suite; a leading `[AC-3]` tag was stripped away. LF.186: a mixed pip+npm install names `package.json` too | BUILT 2026-10-22, Fix batch 4 (deep review) | [monitoring handover §0](monitoring-handover.md) |
| LF.211 | LF.188 follow-ups: the memory holds build files without a code suffix (`go.mod`, `pom.xml`, `.csproj`, `Gemfile`, `config.ru`, `phpunit.xml`, `.properties`) - the snapshot had shown them - and holds back a later sprint's test files as the snapshot did. `RELEASE_DOCS_REQUIRED`: a run with no pack record finds its README in the pinned project (it was held back twice and escalated). `CHANGE_REQUEST_RUNS`: generated folders are left out only where generated (a product's `src/target/` was dropped), links out of the workspace are not copied, a failed copy is cleaned and answered 400 (it wedged every retry). `prefix_breaks` and the distiller never raise on malformed records | BUILT 2026-10-22, Fix batch 4 (deep review) | [monitoring handover §0](monitoring-handover.md) |
| LF.212 | PX.1 measurement: a request that resends nothing (`carried` 0) opens a conversation of its own - a one-shot call beside a stage's agent, a part of a specification written at once - and was scored as a break of the call before it under the same stage name. On the first all-on run 8 of 10 breaks were these (`system_changed` 4, `opening_changed` 3, `tools_changed` 1 of them), so the prefix-cache switches were judged on calls they cannot affect. Now `first_of_a_conversation`; test in `test_a_prefix_break_is_classified_by_its_first_difference.py` | BUILT 2026-10-22, takes effect at the next deploy (KPIs are computed after the run) | [monitoring handover §0](monitoring-handover.md) |
| LF.213 | a pause leaves the paused task's model calls in flight: on the first all-on run the owner paused and resumed within 4 s, the paused task's two in-flight specification-part calls ran on for 235-255 s beside the resumed run (whose first call took 119 s) and were thrown away, about 4-5 min lost; the warning called them "1 other run(s) (none)". The warning now names calls no run claims as such (`call_gate.UNCLAIMED`); test in `test_a_deploy_waits_for_the_model_calls_in_flight.py`. Filed, not built: abort a paused run's in-flight model calls (a deploy's restart already does, so pause+deploy+rewind is unaffected) | BUILT 2026-10-22 (warning) | [monitoring handover §0](monitoring-handover.md) |
| LF.214 | a module of the product's own imported by the wrong path (`from database import` in `tests/`, for `tasks_api/database.py`) was reported as an undeclared package `database` - an invitation to put it in the manifest (the LF.207 class). Seen on the first all-on run; the rewrite declared only `bcrypt`, so no harm there. A name the project's tree defines is local; the wrong import is left to the tests that run it; test in `test_an_import_is_read_from_the_syntax_tree_not_a_docstring.py` | BUILT 2026-10-22, bundled (does not change this run's outcome) | [monitoring handover §0](monitoring-handover.md) |
| LF.215 | a revision made in place (fast delivery) rewrote nearly every section: asked for every section a change touches and every one that repeats a changed name, the model named ten each time. On the first all-on run three review rounds of three blocking findings took 56 of the architect's model minutes (20 calls, 170k output tokens). The sections the review's own words name are rewritten, and at most `MOST_UNNAMED_SECTIONS` (2) more of the model's choice; a review naming none keeps the model's choice; test in `test_a_revision_rewrites_only_the_sections_the_review_touches.py`. Filed, not built: a locked test that contradicts the specification's error catalogue (signin with an empty username: test 401, specification 422) passed the acceptance review twice and cost sprint 1 a whole attempt - not caught without a model | BUILT 2026-10-22, bundled (the architect's phase of this run is over) | [monitoring handover §0](monitoring-handover.md) |
| LF.216 | the fast rewrite's request carried neither the defect's actual behaviour - where the harness writes "Reverted: it broke ..." - nor the attempt ledger (DECISION_LEDGER fed only the agent loop's request). On the first all-on run two rewrites of one unit-test defect were asked the identical 93,541-character request, wrote the same change and were reverted for the same broken unit test; the sprint attempt ran out of rounds. `rewritten_fixes.fix_request` now carries both; test in `test_a_defect_is_fixed_by_rewriting_its_files.py` | BUILT 2026-10-22, deployed into run-bf8a972f with LF.215 | [monitoring handover §0](monitoring-handover.md) |
| QM.1 | quality measures beside the hidden score (owner, 2026-10-22: improve the quality of what gets built, not only efficiency). The tasks-api hidden tests now answer 10/10 on every finished run and no longer tell one product from a better one. (a) `benchmarks/tasks-api/quality/`: 7 tests of the brief at its edges (a password never stored as given, whitespace-only title, malformed requests, a non-boolean `done`, foreign/non-numeric ids, a 5,000-character title, 20 parallel creates) - the reference passes all; scored apart as `quality_passed/quality_total` so the headline stays comparable. Live: run-bf8a972f 7/7, run-7e5c11af 7/7, run-10d79850 5/7. (b) `loop.sh score` runs the mutation test too (12 changes; `MUTATE=0` skips): run-bf8a972f's locked suite noticed 6 of 10 changes, missing whitespace-only username/title checks and `check_same_thread`. (c) the KPI ledger carries `hidden_score`, `quality_score`, `mutation_score` and flags a drop of 0.15 below the 5-run mean. Tests in `test_the_tasks_api_bench_reference_scores_full.py` | BUILT 2026-10-22 (measurement only) | [monitoring handover §0](monitoring-handover.md) |
| QM.2 | mutation-guided tests (owner, 2026-10-22: improve the quality of what is built, not only efficiency). The release probe already breaks the product on purpose and reports what the locked suite does not notice as an unactioned completion gap; run-bf8a972f's locked suite missed 4 of 10 such changes, including a whitespace-only check and a connection setting, and the product shipped with no test holding it to either. With the switch on, the same probe runs once per sprint attempt when the sprint's due criteria all pass, on that sprint's own source files, a few changes only, never for a suite that drives a browser; a change neither the unit tests nor the locked suite notices is one finding for the testing role - a unit test that fails with the change and passes without it - settled deterministically by the harness re-applying the one change and running the unit test command, as a language-service finding is re-asked; an equivalent change the fixer names and explains is closed as such; one unsettled after its tries is a completion gap, never an escalation, and never charges the sprint's attempt budget. `src/app/acceptance/mutation_guided.py`; wired into `_settle_the_fix`, `_fixed_by_rewriting` (rewrites are refused for a finding), `test_and_triage_node`, `defect_fix_gather_node`, `delivery.release`; `recurrence_of` never treats one finding as a restatement of another (`sprint.TEMPLATED_SOURCES`); tests in `test_mutation_guided_tests.py` | BUILT 2026-10-22, behind `MUTATION_GUIDED_TESTS`, off (not yet measured live) | [monitoring handover §0](monitoring-handover.md) |
| SZ.1 | old long tool results folded (owner 2026-10-23: the product works on small and large codebases, the approach chosen by measured size). Past the argument trigger (half the window), behind the kept tail, a tool result over 1,200 characters keeps its opening 300 and a line saying what was folded and to run the call again; the boundary moves 10 messages at a time so the request's opening stays cached; a fold forgets the repeat-read memory, as a compaction does. SWE-agent's folded observations and OpenHands' condenser. `src/app/agents/observation_folding.py`, `compaction.RequestKeepingSummarization._truncate_args`; test `test_old_writes_and_results_are_shortened_behind_the_kept_tail.py` | BUILT 2026-10-23, behind `OBSERVATION_FOLDING`, off | [monitoring handover §0](monitoring-handover.md) |
| SZ.2 | a file over 24,000 characters (about a quarter of the 32,768-token reply cap) is fixed by SEARCH/REPLACE blocks over its outline and the windows the failure names, applied with `edit_approved_artifact`'s matching (`_a_repaired_span`, `content_with_passage_replaced`) and written once through the write path's parse checks; any block that fails refuses all and the next pass is told why. Smaller files are rewritten whole as before. `src/app/graph/anchored_edits.py`, `rewritten_fixes`; test `test_a_file_too_long_to_rewrite_whole_is_fixed_by_anchored_edits.py` | BUILT 2026-10-23, size-gated | [monitoring handover §0](monitoring-handover.md) |
| SZ.3 | in output over its budget, runs of three or more stack frames outside the project are one line, kept: every workspace frame, every non-frame line, each trace's last frame; decided by path, for Python, Node, Go, Java, Ruby, PHP, .NET shapes. In `what_failed` before its cut and `sandbox._truncate` before head/tail. `src/app/analysis/tracebacks.py`; test `test_a_long_failure_keeps_the_project_s_frames_and_drops_the_runtime_s.py` | BUILT 2026-10-23, size-gated | [monitoring handover §0](monitoring-handover.md) |
| SZ.4 | search results cap note | SKIPPED: `search_text`/`inspect_repository` reach no model (the repository read tools were withdrawn); the agents' `grep`/`glob` are SZ.5 | - |
| SZ.5 | `ls`, `glob`, `grep` of the workspace backend return at most 200 entries and say how many more (`ls` a note entry; `glob`/`grep` marked truncated, so deepagents' own narrow-it note shows). Test `test_a_large_listing_is_cut_and_says_so.py` | BUILT 2026-10-23, size-gated | [monitoring handover §0](monitoring-handover.md) |
| SZ.6 | the code graph is built once per state of the project's files (path, mtime, size), its JSON rewritten only when changed; files of Go, Java, Kotlin, Rust, Ruby, PHP, C#, Swift carry their definitions (no import edges; `who_uses` says so), so `where_is` works in them; `reachability.FAMILIES` unchanged. Test `test_the_code_graph_is_built_once_and_knows_every_language_s_definitions.py` | BUILT 2026-10-23 | [monitoring handover §0](monitoring-handover.md) |
| SZ.7 | eight workspace walks (`suite.suite_files`, `mutation.source_files`, `per_file.each_file`, `work_orders`, `interface_checks`, `delivery`, `handover.files_of`, the throwaway sweep) prune dependency and hidden folders instead of descending into `node_modules`/`.venv` and filtering after (`walk.files_under(..., skip_hidden)`). Test `test_the_workspace_walks_do_not_enter_dependency_directories.py` | BUILT 2026-10-23 | [monitoring handover §0](monitoring-handover.md) |
| SZ.8 | a file a defect or a work order names by a path suffix is found at any depth (shallowest unique match; a tie is not guessed), where only `root/name` and `*/name` were looked at. `walk.the_file_ending`, `rewritten_fixes._the_files`, `drafting._neighbours`. Not size-gated: a small project's file two folders down is now found too. Test `test_a_file_named_deep_in_the_tree_is_found.py` | BUILT 2026-10-23 | [monitoring handover §0](monitoring-handover.md) |
| SZ.9 | a map of what each file defines that overflows its budget holds the files that matter first - named by the request, the code graph's neighbours of those, defining the request's words, most imported - and counts the rest; it was cut in path order. The memory's left-out list names 60 files and counts the rest (it named every path, outside the budget); under `CANONICAL_MEMORY` the memory's map ranks by imports only, so it stays the same between requests. A map that fits is unchanged. `project_memory.map_of`, `localisation._the_map`; test `test_a_large_project_s_map_holds_the_files_that_matter.py` | BUILT 2026-10-23, size-gated | [monitoring handover §0](monitoring-handover.md) |
| SZ.10 | under the project memory a stage's start reads the project only until a file with content (the snapshot was built from every file, then discarded). `project_snapshot.for_a_stage`; test `test_a_stage_under_the_memory_does_not_read_the_whole_project_at_its_start.py` | BUILT 2026-10-23 | [monitoring handover §0](monitoring-handover.md) |
| SZ.11 | the toolkit's `read_repository_file` read whole returns the first 400 lines and the file's length past that (agents' `read_file` already pages at 400). Test `test_a_whole_file_read_of_a_long_file_returns_its_first_window.py` | BUILT 2026-10-23, size-gated | [monitoring handover §0](monitoring-handover.md) |
| MD.1 | every model is diagnosed the first time it is seen, and the harness adapts to it (owner, 2026-10-23: the owner swaps local models often and each had tool and reasoning quirks learnt only from failed calls mid-run). At a run segment's start, and before the next call when the server's model changes mid-run, a model with no kept diagnosis is asked small questions shaped like a stage's: tools offered, required and named (thinking as served and off), only offered names, the right one of 16 stage tools, the stage's own structured answer forced and offered with the stage's work in the conversation, forced after a ~20,000-token request, two calls in one reply, a fact in the middle of a long request, the existing tool-fitness and edit-format probes, and the reasoning cost of each switch. Kept in `DATA_DIR/model-fitness/<served name>.json` beside the model's other measurements; applied: a model that cannot be forced has its structured answers offered (`_NO_FORCED_TOOL_WHILE_THINKING`), the measured reasoning switch seeds `thinking.least_reasoning_effort`; the rest is advice in `loop.sh ready` and `loop.sh diagnose [--again]`. Sampling stays the owner's. First diagnosis, Qwen3.8-Flash-Next IQ1_M (158 s): every forced and named check passed (3/3, 2/2 long); offered, the structured answer is given 0-2 of 3 (it reads files first); 3/5 fitness probes - it lists and searches through the terminal instead of `ls`/`grep`; `reasoning_effort=none` 3 tokens against 50 as served. `src/app/models/diagnostics.py`, `scripts/loop/model_diagnose.py`; test `test_a_new_model_is_diagnosed_once_and_its_settings_kept_with_it.py` | BUILT 2026-10-23 | [monitoring handover §0](monitoring-handover.md) |
| RS.1 | a reply cut off by the reply cap is salvaged from its own reasoning instead of capping reasoning (owner, 2026-10-23: a cap costs accuracy). Measured over nine runs: 19 of 1,927 replies reasoned to the cap and wrote nothing (10% of all output tokens), 74 finished between 16,000 and 32,768 tokens - a cap would have cut them. The request is sent again with the model's reply begun: its whole reasoning (last 48,000 characters), closed with a sentence that it answers now; a reply cut part way through its text is continued (at most twice, Aider's infinite output). Whether a server continues a begun reply, and in which shape (`reasoning_content` or the template's think tags), is measured per model and kept with it; salvage is used only where it worked. Qwen3.8-Flash-Next: `reasoning_field`, tool calls after it, continuation (the server repeats the begun text; stripped). `src/app/models/reply_salvage.py`, `CompatibleChatOpenAI._generate_once`; test `test_a_reply_cut_off_by_the_cap_is_salvaged_from_its_own_reasoning.py` | BUILT 2026-10-23, behind `REPLY_SALVAGE`, on (owner), used per model as measured | [monitoring handover §0](monitoring-handover.md) |
| MD.2 | a model that does not do as stages ask is given guidance measured to help, in every stage's prompt (owner, 2026-10-23, for LFM2.5: settings or a switch with instructions, not model-specific code). The deep diagnosis asks five stage-shaped questions three times each - a plan answered in its schema, the answer as a call once the work is done, a long list without looping, a role kept when the failure is another role's, stopping when its tests pass - then tries each candidate line only where the model fell short and keeps the lines that raised the pass count; the kept set is asked once more together. Kept as the model's row of `plugin_instructions` (`model:<served name>`, editable like a stack row) and appended by the plugin middleware while that model serves; a reply ceiling (40,000) is chosen when a check saw it loop and the deployment leaves replies uncapped. Runs at a new model's first segment, or `loop.sh diagnose --deep [--again]`. LFM2.5-24B-A2B (248 s on 3 slots): plan in schema 1/3 -> 3/3 and stopping when done 1/3 -> 3/3 with two kept lines; answer offered as a call 0/3 either way (forcing covers it, 3/3); no loop, no ceiling. `src/app/models/model_guidance.py`, `deep_diagnosis.py`; test `test_a_model_s_guidance_is_measured_kept_and_given_to_every_stage.py` | BUILT 2026-10-23, behind `MODEL_GUIDANCE`, on (owner) | [monitoring handover §0](monitoring-handover.md) |
| MD.3 | model steering made general (owner, 2026-10-23 ~19:50 JST: settings for models in general, not per model; weaker models steered more; a settings-page action that diagnoses and saves against the model; each guide its own switch; keep growing the checks). One catalogue of eight guides (`app.models.guidance.GUIDES`: answers in their schema, stops when its checks pass, never repeats itself, keeps to its role, each tool's own argument names, one program a command, paths as given, changes course when refused), each its own `GUIDE_<ID>` switch (off in code, on in compose) and tied to the deep-diagnosis checks that show the need; the lines are general `guide:<id>` rows of `plugin_instructions`, editable once for every model. Eleven stage-shaped checks now (six added from today's runs: a role kept while building, exact argument names, one program a command, paths as given, a refusal heeded, a rule kept after a long request). Per model only its steering profile is kept: tier from its baseline pass share (strong >= 0.9: only what helped; standard >= 0.65: what helped where it fell short; weak: every guide for where it fell short, helped or not, and an end-of-request reminder - Aider's `reminder="user"`, prompt repetition), the guides chosen, the owner's per-guide Auto/On/Off overrides (kept across re-diagnoses) and the reply ceiling. Settings > Models: "Diagnose this model and set its guidance" (a worker job, refused while a run is live) and each guide's control (`GET/POST/PUT /api/settings/model/steering...`). `src/app/models/guidance.py`, `steering_job.py`, `langchain-ui/src/components/ModelGuidancePanel.tsx`; tests `test_a_model_s_guidance_is_measured_kept_and_given_to_every_stage.py`, `test_the_settings_page_diagnoses_the_model_and_sets_its_guidance.py`, `ModelGuidancePanel.test.tsx` | BUILT 2026-10-23, not deployed (gate run live) | [monitoring handover §0](monitoring-handover.md) |
| MD.4 | next, from the research (Aider, OpenHands, Cline, llama.cpp, JSONSchemaBench, Less-is-More, Natural Language Tools, prompt repetition): (a) a compact tier - fewer tools offered to a weak model's stages (Less-is-More: up to 35-40% better tool accuracy on small models) and terser rules (Cline's xs variant); (b) a text tool-call protocol with a generated worked example for a model whose native calls the diagnosis finds unreliable (OpenHands `fn_call_converter`); (c) constrained answers - `response_format` / required tool choice per profile, since llama.cpp grammars raised small-model schema compliance from 38% to 74% (JSONSchemaBench); (d) sampling advice per stage kind (low temperature for calls) shown on the settings page, never sent; (e) the server-side warning that a quantised KV cache degrades tool calling (llama.cpp docs) in `loop.sh ready`. Each a guide or a profile field chosen by measurement | PLANNED | [monitoring handover §0](monitoring-handover.md) |
| MD.5 | the serving model's capabilities on the settings page (owner, 2026-10-23: what the harness needs to know about a model - vision, thinking, reasoning, multilingual and more - set by the owner, else found by asking the model and searching for it; and the two vision gaps: fixers never saw the page, and reading images was guessed from the name). Fourteen fields (reads images, reasons, how reasoning is turned down, native tool calls, several calls a reply, answers to a JSON schema, continues a begun reply, multilingual, languages, context window, parameters, quantisation, recommended sampling, model card), each resolved owner > the model asked (a red square whose colour it must name, a two-field JSON schema, a question in Japanese) and what MD.1/RS.1 measured > the server's `/props` > its Hugging Face model card (task tag, languages, weights, the card's sampling) > unknown, and kept against the model. `vision.reads_images` uses the measured value before any name rule (the owner's `MODEL_READS_IMAGES` still wins), and a fix request gets the page's desktop and phone screenshots when the build model reads images (`page_screenshots.with_the_page_for_a_fixer`) - only the reviewer was shown them. Settings > Models "Model capabilities": each field editable, its source shown, "Find what is missing" (a worker job, refused while a run is live); a new model's capabilities are found at its first segment. `src/app/models/capabilities.py`, `ModelCapabilitiesPanel.tsx`; test `test_a_model_s_capabilities_are_set_or_found_and_used.py`, `ModelCapabilitiesPanel.test.tsx` | BUILT 2026-10-23, not deployed (test run mid-fix-cycle) | [monitoring handover §0](monitoring-handover.md) |
| MD.7 | the steering playbook's top items (owner, 2026-10-23: build everything; reports/Steering stubborn local models.md). (a) `STRUCTURED_EXTRACTION`: llama.cpp enforces neither a named `tool_choice` (read as `auto`) nor, for LFM2.5, `required` with one tool (measured: three prose replies of three), so a stage's prose answer was only ever reminded; now it is asked once more with no tools and the answer's JSON schema as `response_format` - enforced by the server's grammar - and the object is handed to the stage as its answer-tool call; a refused schema or an object that does not validate leaves the reminder. (b) `REFUSALS_FOLDED`: in what each call is sent, every refusal but the latest is one line (self-conditioning, Sinha et al. 2025; SWE-agent keeps refused commands out of history); the guards count the conversation as stored. (c) LF.238. `src/app/agents/structured_extraction.py`, `refusal_folding.py`; test `test_a_prose_answer_is_asked_again_with_only_its_schema_allowed.py` | BUILT 2026-10-23, on in compose | [monitoring handover §0](monitoring-handover.md) |
| MD.6 | the owner's sampling sent per request (ADR-0008: sampling is the owner's - sent only when turned on, per model): capabilities `send_sampling`, `sampling_to_send` (found from the model card's recommendation, editable) and `dry_sampler` (DRY at 0.8 / 1.75 / 2 / last 1024 tokens - the measured setting that cut verbatim loops by about half, off on llama.cpp by default). Parsed into the request (top-level OpenAI fields, the server's own in `extra_body`); a value the request has wins; nothing read unless the owner turned something on. `capabilities.sampling_for`, `CompatibleChatOpenAI._get_request_payload`; test `test_the_owner_s_sampling_is_sent_only_when_turned_on.py` | BUILT 2026-10-23, off until the owner turns it on per model | [monitoring handover §0](monitoring-handover.md) |
| LF.217 | fast delivery's own sprint-planning path (`_the_specification_s_work_orders`) makes no model call, so no event ever carried `stage="technical_lead"` for the sprint it opened - the run page's sprint counter (`runs.py`, built by counting `technical_lead` visits) silently skipped it. The next sprint's `technical_lead` visit wore the missed number: live, sprint 1 showed no sprint header while it was built, and the header that first appeared, over sprint 2's planning, read "Sprint 1" (owner screenshot, run-8cced4a9). The deterministic branch now narrates itself through `AgentActivityStream`, the same mechanism a deterministic close already uses (`models.call_gate._tell_the_run`); test in `test_work_orders_are_made_from_the_specification.py` | BUILT 2026-10-22, bundled (UI only, never affects a run's outcome or score) | [monitoring handover §0](monitoring-handover.md) |
| LF.218 | `_fixed_by_rewriting` (fast delivery's AY step): a candidate attempt that failed fell through to a rewrite that asked `app.graph.localisation.localised` the same question again - same defect, same failure - spending a second model call finding the same files, in every retry that tries both paths. Localisation now runs once, ahead of the candidates call, and its result (`located`) is carried into both `fix_by_candidates` and `fix_by_rewriting` via a new `files=` parameter each accepts; computed lazily (only when the candidates path is actually entered), so a defect that never reaches it pays nothing extra. Test in `test_a_defect_is_localised_before_it_is_rewritten.py` | BUILT 2026-10-23, filed for the next Fix batch (this is a gated run, MF.4 - no mid-run deploys) | [monitoring handover §0](monitoring-handover.md) |
| LF.221 | a service that started, listened and answered the suite's readiness request with an error status was reported as "did not start": on the first QM.2 run (run-85ad15b0) gunicorn listened, the readiness request to the health route answered 404 for 30 s, and four fixes over two sprint attempts rewrote start-up code and password hashing - each reverted for breaking a passing unit test - while the routes were never registered; the 404 line sat past the six cause lines the start excerpt keeps. `suite.the_product_did_not_start` now recognises the service listening plus an HTTP error status and says, ahead of the excerpt (a defect carries its first 1,500 characters), that the route is not served and the routes must be registered with the application the start command runs. Test `test_a_service_that_listened_and_answered_an_error_is_told_its_route_is_not_served.py`. Major under MF.4: the run was cancelled and the QM.2 arm restarted on the fix | BUILT 2026-10-23, deployed | [monitoring handover §0](monitoring-handover.md) |
| LF.222 | deepagents shortens the arguments of old calls only for its own `write_file`/`edit_file`; every stage writes through `write_artifact`/`edit_artifact`, so the relief `role_agent` configures for written files (a 51 KB specification in every later request) never fired. `compaction.RequestKeepingSummarization._truncate_args` covers the harness's writing tools, behind the same trigger and kept tail, its boundary in steps of 10 messages. Found in the 2026-10-23 re-review of the DevFlow review. Test `test_old_writes_and_results_are_shortened_behind_the_kept_tail.py` | BUILT 2026-10-23, not deployed | [monitoring handover §0](monitoring-handover.md) |
| LF.223 | a reply that ends inside its fenced block (cut off by the reply cap) was taken as a reply with no fence and written whole, its opening fence line included, or a short earlier block was taken for the file; an odd count of fence lines now means no file, which every caller treats as no draft. `drafting.the_content_in`; test `test_a_reply_cut_off_inside_its_block_is_not_written.py` | BUILT 2026-10-23, not deployed | [monitoring handover §0](monitoring-handover.md) |
| LF.224 | a Qwen3-Coder model with words between its version and "coder" (`qwen3.8-flash-next-coder-iq1_m`) was read as plain qwen3 - JSON tool calls advised - though its template writes XML ones; the family pattern now allows any words between. `registry.FAMILIES` | BUILT 2026-10-23 | [monitoring handover §0](monitoring-handover.md) |
| LF.225 | another model behind the same server, at the same slots and context, was no change to the mid-run server check, so nothing measured of the old model was re-measured; `server_profile.what_changed` now compares the model too, and a change diagnoses the new one before the next call (MD.1) | BUILT 2026-10-23 | [monitoring handover §0](monitoring-handover.md) |
| LF.226 | a model's fitness file was rewritten whole by each measurement, so measuring one thing forgot another; `registry.merge_into_fitness` keeps each beside the rest | BUILT 2026-10-23 | [monitoring handover §0](monitoring-handover.md) |
| LF.227 | RS.1's first live continuation (run-ec1e5ae2, a drafted test file) continued a reply stuck repeating one unit (`"never-issued-token-000..."` to the cap) twice, writing more zeros; a cut-off text whose last 400 characters are one unit of at most 16 repeated is not continued, and a continuation that starts repeating stops. `reply_salvage.repeating`. Built, not deployed (Measure run) | BUILT 2026-10-23, not deployed | [monitoring handover §0](monitoring-handover.md) |
| LF.228 | MD.1's first diagnosis of LFM2.5-24B-A2B (run-ec1e5ae2, resumed on it) advised two things the checks did not show: "calls tools that were not offered" for a model that read the file (`read_file`, offered) before editing it, and "fails forced and offered alike" for a forced answer that passed 3/3 and fell short only after the long request (1/2). Another offered tool first now passes "only offered names" (only a name not offered fails it), and the advice names the stage-shaped check that fell short. Built, not deployed | BUILT 2026-10-23, not deployed | [monitoring handover §0](monitoring-handover.md) |
| LF.229 | a call wrapping an offered tool's call - `Skill({"skill": "SprintPlanOutput", "arguments": {...}})`, seen in run-ec1e5ae2's sprint planning on Qwen3.8-Flash-Next - was refused as "not a valid tool" and the whole plan thrown away; its next answer dropped the success-measure coverage, so planning was asked again. A call to a tool not offered, holding exactly one value naming an offered tool and one object, is taken as that tool's call (`tool_arguments._the_call_it_wraps`), before the alias and near-name repairs. Built, not deployed | BUILT 2026-10-23, not deployed | [monitoring handover §0](monitoring-handover.md) |
| LF.230 | a whole command line sent as one string had its program taken as the line's last path part (`os.path.basename`): `cd /workspace/tasks-api && cat .../routes.py | head -50` was refused as "'routes.py | head -50' is not permitted for role ...", `... 2>/dev/null && ...` as "'null && ...' is not permitted"; the helpful "no shell here" answer fired only when the line's first word was a permitted program, and `cd` is none. In gate run run-ea0a7402 one LFM2.5 fixer sent eight such lines in a minute. Now any first item holding a whole line is answered: no shell, one program per call with its arguments as items, joined commands and redirections as separate calls or a script file, `cd` as `working_directory`; a forbidden first word is still named not permitted. `sandbox._a_command_line_in_one_string`; test `test_a_command_line_in_one_string_is_told_there_is_no_shell.py`. Built, not deployed (gate run live) | BUILT 2026-10-23, not deployed | [monitoring handover §0](monitoring-handover.md) |
| LF.231 | gate run run-ea0a7402 on LFM2.5 (replies uncapped by the owner's setting): replies reasoned 80,000-144,000 tokens each - 300,000-500,000 characters, most of the 131k window - on planning and fix stages; salvage answered three, three more ended with nothing and no record of whether salvage was tried. The deep diagnosis's short questions never showed it. Now a twelfth check asks a planning-sized request with a 32,768-token room (`an answer within a stage's reply`), and a model that reasons past it gets the 40,000 reply ceiling under `MODEL_GUIDANCE` - salvage then answers a reply cut there from its own reasoning; a salvage that comes back empty, or fails, is logged at info. `deep_diagnosis._answers_within_a_reply`, `reply_salvage`. Built, not deployed (gate run live) | BUILT 2026-10-23, not deployed | [monitoring handover §0](monitoring-handover.md) |
| LF.232 | LF.231's new log gave the cause of the unsalvaged replies at once: "asked to answer from its reasoning, it reasoned again (length, 173,569 characters)". LFM2.5's probe answered in the `reasoning_field` shape on a short question; on a fix stage's long request the same shape made it reason again, to the 40,000 ceiling, for nothing. A reply lost to reasoning is now asked in the shape that answered after a long request, else each other shape once (the template's own closing tag written into the reply), the shape that answered kept as the model's `long_shape`, and each salvage's own reply held to 16,000 tokens. `reply_salvage._answered_from_its_reasoning`; test `test_a_reply_cut_off_by_the_cap_is_salvaged_from_its_own_reasoning.py` | BUILT 2026-10-23, deployed into test run run-ea0a7402 | [monitoring handover §0](monitoring-handover.md) |
| LF.233 | MD.5's first live fill read LFM2.5 as not reasoning - from 41 output tokens on a one-number question - while it reasons 100,000 tokens on a stage. Whether a model reasons is now whether its reply to a small timing question carries any reasoning at all (`capabilities.measure`). Built, deployed at the test run's next pause | BUILT 2026-10-23, not deployed | [monitoring handover §0](monitoring-handover.md) |
| LF.234 | a salvage of a large fix stage's reply was refused by the server: "Message too long: 149266 tokens exceeds the context" - the request, 48,000 characters of kept reasoning and the answer's room did not fit the 131k window. The reasoning kept is now cut to what fits beside the request's own input tokens and a 16,000-token answer, and a reply whose request leaves less than 4,000 characters of room is not salvaged (said in the log). `reply_salvage._room_for_the_reasoning`; test `test_a_reply_cut_off_by_the_cap_is_salvaged_from_its_own_reasoning.py` | BUILT 2026-10-23, deployed into test run run-ea0a7402 | [monitoring handover §0](monitoring-handover.md) |
| LF.235 | salvaged answers were handed to the stage with the begun reply the server echoes before its answer - `<think>` and tens of thousands of characters of the model's own reasoning - so the stage's answer reader called them "prose where the schema was expected" twice in run-ea0a7402. The echoed begun text, or a leading closed reasoning block, is taken off a salvaged answer. `reply_salvage._without_the_reasoning_it_was_given`; test `test_a_reply_cut_off_by_the_cap_is_salvaged_from_its_own_reasoning.py` | BUILT 2026-10-23, deployed into test run run-ea0a7402 | [monitoring handover §0](monitoring-handover.md) |
| LF.236 | a shell line split into items for a permitted program - `["python", "-m", "uvicorn", ..., "&&", ...]` - was refused about the module `-m` names (or a forbidden argument), its operator never mentioned, because the shell-operator check ran after the argument checks; it now runs first for a permitted program (a program not permitted - `cd`, a builtin - keeps its own refusal). Seen in run-ea0a7402. `sandbox.validate_command`; test `test_a_command_line_in_one_string_is_told_there_is_no_shell.py` | BUILT 2026-10-23 | [monitoring handover §0](monitoring-handover.md) |
| LF.238 | refused calls were tallied by identical `(name, arguments)`, so a model that changes its call a little each time - a different shell line, refused the same way - was never repeating itself; ten in a minute in run-ea0a7402 and the tool was never withheld. A tool that writes no file is now also tallied by the kind of its refusal (its opening with what it quotes and counts taken out, read from the JSON error), the larger count deciding; a tool that writes keeps exact counting, since a stage fixing a file that does not parse is refused the same way edit after edit. `settled_answer._the_kind_of`; test `test_a_call_refused_the_same_way_each_time_is_one_loop.py` | BUILT 2026-10-23 | [monitoring handover §0](monitoring-handover.md) |
| LF.237 | a salvage's begun reply could be answered by the model opening its reasoning again (`<think>` once more, to its ceiling). The tag the template opens reasoning with is found from the server (`/props` template, `/tokenize` ids) as the capability "How it opens its reasoning"; a salvage request then carries `logit_bias [[id, false]]` for a one-token tag and the tag in `stop`. `capabilities`, `reply_salvage`; test `test_a_reasoning_prefill_cannot_open_its_reasoning_again.py` | BUILT 2026-10-23 | [monitoring handover §0](monitoring-handover.md) |
| LF.239 | MD.1's forcing checks asked questions that invite their tool (the weather tool for the weather), so a model called it unforced and forcing looked enforced; measured with "say hello" and one tool required, LFM2.5 on llama.cpp answered in text three times of three. A capability "A required tool call is enforced by the server" is now measured that way (`capabilities.measure`); `STRUCTURED_EXTRACTION` covers a server that does not enforce it. Test `test_a_model_s_capabilities_are_set_or_found_and_used.py` | BUILT 2026-10-23 | [monitoring handover §0](monitoring-handover.md) |
| LF.240 | a capability fill while the model server was restarting kept every probe's 502 or dropped connection as "cannot" - forcing, JSON-schema answers. Only a refusal (4xx) or a wrong answer now records "no"; a server that did not answer leaves the field unknown, said in the log. `capabilities._refused`, `_failed`; test `test_a_model_s_capabilities_are_set_or_found_and_used.py` | BUILT 2026-10-23 | [monitoring handover §0](monitoring-handover.md) |
| LF.241 | a run started while the model server had no model loaded: every probe of the new model's automatic diagnosis was answered "No model loaded" (400), the diagnosis took 0 s, and it kept the refusals as the model's - "forcing a tool does not work", "reply salvage not supported", no guidance. Before anything about a model is measured (tool diagnosis, salvage, deep diagnosis, the model's own capability probes, the settings action), one small request must be answered (`diagnostics.the_model_answers`); otherwise nothing is recorded and the settings action says to load the model. Test `test_a_new_model_is_diagnosed_once_and_its_settings_kept_with_it.py` | BUILT 2026-10-23 | [monitoring handover §0](monitoring-handover.md) |
| LF.242 | `loop.sh ready` asked only whether the configured model was listed; a server listing every model on disk answered each request "No model loaded", the check said ALL READY, and a run started and failed at once. It now also sends one small request and is NOTREADY with what the server said when that is not answered. `scripts/loop/model_ready.answers`; test `test_a_model_listed_but_not_answering_is_not_ready.py` | BUILT 2026-10-23 | [monitoring handover §0](monitoring-handover.md) |
| LF.243 | the settings page stayed on "diagnosing" through a closed model server and a restart of every container: the job's status file said running, nothing ever said otherwise, and the action refused to start while it did. A running job now refreshes its status every 30 s; a "running" status not refreshed for 2 minutes (a dead worker, a deploy, a job never picked up) is shown as failed with why, and the action starts again. A model server that stops answering mid-diagnosis fails the job and keeps nothing of that part. `steering_job._Beating`, `status`, `_gone`; test `test_a_diagnosis_that_stopped_is_seen_to_have_stopped.py` | BUILT 2026-10-23, deployed | [monitoring handover §0](monitoring-handover.md) |
| LF.244 | the owner's cancel did not stop a run left "running" by a restart with no worker running it: the cancel was flagged for a worker that did not exist, and each cancel touched the run, so orphan recovery kept judging it too recent to be abandoned. A cancel now asks the workers (one second) whether any is running the run's task; none is, and the run is cancelled at once; one is, and it stops at its next check as before. `runner._a_worker_is_running`; tests `test_runner_lifecycle.py` | BUILT 2026-10-23, deployed | [monitoring handover §0](monitoring-handover.md) |
| LF.245 | the settings page showed nothing of a finished diagnosis, and the capability probe sent a picture to a server that holds no vision part (a 400, and the owner's server hung on it). The worker keeps measurements under the file name the server reports; the API process never read the server and looked under the configured name, so every row said "not yet" and what the owner set went to a file no run read. Now every process names the model one way (`model_guidance.served_as`; the page reads the server afresh, `steering_job.page_model` / `server_profile.recent`), what was kept under the configured name is folded into the served file (`registry.fold_into_served`), and `/props` `modalities.vision` is the field's answer from the server - no image is sent when it says no. Tests `test_the_settings_page_names_the_model_as_the_worker_does_and_sends_no_image_to_a_server_without_vision.py` | BUILT 2026-10-23, deploying | [monitoring handover §0](monitoring-handover.md) |
| LF.246 | `loop.sh ready` described the model by its configured name, so it said "reply salvage unmeasured" and "edit preference unmeasured" of a model the diagnosis had just measured. It now names the model as the worker does (`served_as`). Test `test_ready_describes_the_model_by_the_name_its_measurements_are_kept_under.py` | BUILT 2026-10-23, deploying | [monitoring handover §0](monitoring-handover.md) |
| LF.247 | a revision of specification sections in place was thrown away when one section came back as an empty list: the reply wrote the section the changes touched and answered `[]` for a second that held none, and the nine minutes it took were dropped for a full rewrite by the architect. A section answered empty is now left as it stands and the written ones are kept; a section the reply does not name at all still sends the revision back to the architect. `specification_parts.revised_in_place`; tests `test_a_revision_rewrites_only_the_sections_the_review_touches.py` | BUILT 2026-10-24, deploying mid-run | [monitoring handover §0](monitoring-handover.md) |
| LF.248 | an in-place revision of specification sections failed to join ("9 validation errors") when a section it rewrote held nothing yet: the request said "the same form as the section's current value", an empty list gave no form, and the reply invented record keys (`summary` for `context` and `decision`). The request now carries the JSON schema of the sections being rewritten. `specification_parts._the_form_of`; test `test_a_revision_rewrites_only_the_sections_the_review_touches.py` | BUILT 2026-10-24, deploying mid-run | [monitoring handover §0](monitoring-handover.md) |
| LF.249 | a stage's count of writes refused outside its own files was inflated by the harness's own questions: before and after every command it asks the write guards about every workspace file, and each product file counted as a refusal. The acceptance author stood at 124 after six commands with one real refusal, so that one told the model "every one will be refused: stop and return your structured response". The guards now count nothing while only asked (`repository.just_asking`, used by `_not_this_stage_s` and the rewrite-fix `may_write`); real refusals count as before. Tests in `test_a_stage_refused_outside_its_own_files_is_told_to_stop.py` | BUILT 2026-10-24, deploying mid-run | [monitoring handover §0](monitoring-handover.md) |
| LF.250 | a reply cut at the reply ceiling was lost because the salvage request was refused: the ban on the reasoning tag was sent as llama.cpp's list of pairs with `false`, and one model's server answered 400 "logit_bias: Input should be a valid dictionary" - 24,000 tokens (5 minutes) thrown away at the first reply the new ceiling cut. The ban is now an object with -100 (accepted by both kinds of server), and a server that still refuses `logit_bias` is asked again without it, the stop string kept. `reply_salvage._sent`; tests in `test_a_reasoning_prefill_cannot_open_its_reasoning_again.py` | BUILT 2026-10-24, deploying mid-run | [monitoring handover §0](monitoring-handover.md) |
| LF.251 | the cross-file parse check raised the harness's own scratch file as a product defect: a command given as `python -c CODE` is run from a saved `tmp-inline-<hash>.py`, a stage's one-liner with a typo stayed in the workspace, and the check reported "tmp-inline-... does not parse" as the first defect of a sprint, for a fixer. The check now skips scratch names like every other consumer of the rule (`integration_checks._a_source_file_that_does_not_parse`). The sweep of `tmp-` files exists (LF.60) and the finished product held none, so it works at release; the file that became a defect sat at the workspace root, which the sweep between rounds did not reach, and is now harmless to the check. Test `test_a_throwaway_script_is_not_reported_as_a_file_that_does_not_parse.py` | BUILT 2026-10-24, deploying mid-run | [monitoring handover §0](monitoring-handover.md) |
| LF.252 | the rewrite fix took the test runner's own report as the file to correct: the failure text named `reports/unit.xml`, the project's `.gitignore` did not list `reports/`, and the earlier answer (ask git whether the file is ignored) therefore let it through - two fixes in a row rewrote the report, 27,000 tokens, both defects left open, the sprint planned again. A file the setup declares as a test report, or any JUnit XML document, is now never a fix target, whatever the ignore file says (`rewritten_fixes._a_test_report`). Test `test_a_test_report_is_never_the_file_a_fix_rewrites.py` | BUILT 2026-10-24, deploying mid-run | [monitoring handover §0](monitoring-handover.md) |
| LF.253 | the acceptance writer was never told to assert no more than the brief requires: seven of the eight gaps the first Ornith run's release recorded were locked tests asserting the exact text of an error body where the brief and the interface contract required only the status code, so a product built to the brief failed them and the suite was locked failing. A rule now tells the writer to check what the brief or contract says - a status, a field, an exact message where one is given - and, where no wording is given, only that it is an error and its shape (`acceptance/requests.py`). Test `test_the_suite_writer_is_told_to_assert_only_what_the_brief_requires.py` | BUILT 2026-10-24, committed and not deployed (the clean comparison run run-cfb01bcc is frozen); deploys when it ends | `docs/work-batching.md` section 8 |
| LF.254 | a run that failed on a stopped model server waited for someone to look: the owner's server stopped at 07:28 JST, the run failed with a connection error, and every minute until the next audit was model time lost, with nobody awake to resume it. `loop.sh resume <run>` resumes a failed, paused or cancelled run in place, and `loop.sh resume-when-ready <run>` polls `loop.sh ready` and resumes it on the first ALL READY (resume is refused while the model is unreachable, so polling is safe); it starts no model and changes no setting. `scripts/loop/resume_when_ready.py`; test `test_a_failed_run_is_resumed_when_the_model_server_answers_again.py` | BUILT 2026-10-24 (scripts only; no deploy) | [monitoring handover §0](monitoring-handover.md) |
| LF.255 | no rule named the blank-value case: across runs the one quality test the products kept failing was "a title of only spaces is refused and nothing is stored" (the product answered 201), and the clean Ornith run failed it again (quality 6/7). The architect's `error_catalogue` now says a required value that is empty or only whitespace once trimmed is the same failure as a missing one and is listed with it, for every required text value, so the builders and the suite writer inherit it (`principal_architect.TechnicalSpecificationOutput.error_catalogue`). Test `test_the_error_catalogue_names_blank_values_as_missing_ones.py`. Judge by the next runs' quality score | BUILT 2026-10-24, deployed before run 3 | [monitoring handover §0](monitoring-handover.md) |
| LF.256 | a JavaScript setup was not told that a test runner has its own JUnit reporter: on a Hono service tested with Vitest the setup looked up `@vitest/junit-reporter` and `vitest-junit-reporter` (neither exists), wrote a reporter class of its own that wrote no file under that Vitest version, the harness could not prove the setup and left the project's tests to the agents, about forty minutes. The seeded JavaScript setup guidance now names each runner's own reporter (Vitest `reporters: ['default', 'junit']` with `outputFile`, Jest `jest-junit`, Node `--test-reporter=junit`, Playwright `reporter: [['junit', ...]]`) and says never to write one (`plugins/seed.py`, `_JAVASCRIPT_TESTING`). Test `test_the_javascript_setup_is_told_the_runner_has_its_own_junit_reporter.py`. Judge by the same run rewound to its setup | BUILT 2026-10-24, deploying with a rewind | [monitoring handover §0](monitoring-handover.md) |
| LF.257 | a folder in the setup's declaration was reported as a missing file: a Hono setup listed `node_modules` under `kept_files`, the check asked whether it was a file and said "these declared files do not exist: node_modules", the setup ran `npm install` to create it, and the same message came back - two attempts, then the setup was left to the agents. A declared folder now gets its own message (`kept_files` and `smoke_files` list files; name the files to keep, or leave the folder out - what `install` makes is made again), and only a path that does not exist is called missing (`custom_setup._declared`). Test `test_a_declared_folder_is_named_as_a_folder_not_as_a_missing_file.py` | BUILT 2026-10-24, deploying with a rewind | [monitoring handover §0](monitoring-handover.md) |
| LF.258 | a project's own tool installed under `node_modules/.bin` but off the PATH was told it was "not installed - run `npm install`": a Hono setup declared `["vitest", "run"]`, the proof's command could not start it, the message sent the setup to install what was installed, and with LF.256 and LF.257 the setup was left to the agents three times (about 90 minutes). The sandbox now says the tool is installed in the project and to run it as `npx <tool> ...` or an npm script (`SandboxExecutor._a_project_binary_off_the_path`), and the JavaScript setup guidance names the pitfall in the seed. Test `test_a_project_tool_off_the_path_is_told_to_use_npx.py` | BUILT 2026-10-24, deploying at a boundary; proven on the next JavaScript run | [monitoring handover §0](monitoring-handover.md) |
| LF.259 | the library of proven setups almost never hit: it was keyed by the exact wording of the stack selector's text (cut at 120 characters), so three Python entries and a Hono and Vitest one proven on 2026-10-19 sat unused, and a later Hono run spent about ninety minutes setting the same stack up from nothing. A stack is now matched by what it is - language, framework, unit runner, by a table of names (`canonical_key`), an unlisted framework by its own name, an old entry whose file name lost its runner by language and framework - and when no rule matches, the model is asked once to pick the closest entry from a short list (`_chosen_by`; the owner's suggestion 2026-10-24). A replayed setup is still proved by the harness before any agent is asked, so a wrong match costs one proof. `custom_setup.replay`; test `test_a_proven_setup_is_found_by_what_the_stack_is_not_by_how_it_was_worded.py` | BUILT 2026-10-24, deploying | [monitoring handover §0](monitoring-handover.md) |
| LF.260 | a fix for "Module ... has no exported member X" rewrote the test that imports it, not the module that should export it: a Hono run's test imported `makePersistence` from `../src/store.js`, the failure text named `src/store.js`, the file is `store.ts`, so it was not found and only the test was rewritten - with a stand-in for the missing function defined inside it. The type error went away, the suite passed, the SQLite feature was never built, and a reviewer found it later. A compiled name now resolves to its TypeScript source (`.js`/`.jsx`/`.mjs`/`.cjs` to `.ts`/`.tsx`/`.mts`/`.cts`), and a missing-export failure (the compiler's wording, and the runtime's) points the fix at the module that should export it and leaves the importing test alone (`rewritten_fixes._modules_missing_an_export`). Test `test_a_missing_export_is_fixed_in_the_module_that_should_export_it.py`. Owner approved 2026-10-24 | BUILT 2026-10-24, deploys after the live run | [monitoring handover §0](monitoring-handover.md) |
| LF.261 | a drafted work order was recorded as done when its files merely wrote: a work order to add a SQLite store listed `export function makePersistence(...)` and `export interface Persistence` among its interfaces, the files were drafted from a specification that described only the JSON store, `store.ts` came out as it was, every file wrote without error and the work order was done. A work order is now done only when its files define the names its `interfaces` say they export (`export function/class/interface/const/type Name`, `def name`, `class Name`; a name only imported or mentioned does not count), else it goes to the agent loop as a failed file does (`drafting.promised_names`, `not_defined_in`). A work order that names nothing is done as before. Test `test_a_work_order_is_done_only_when_what_it_promised_is_there.py`. Owner approved 2026-10-24 | BUILT 2026-10-24, deploys after the live run | [monitoring handover §0](monitoring-handover.md) |
| LF.262 | the deep diagnosis scored a model weak for what its engine refuses: on an LM Studio server running gpt-oss-20b a named `tool_choice` is a 400 ("Invalid tool_choice type: 'object'. Supported string values: none, auto, required"), so the checks that force the answer tool scored 0/3 (a plan in its schema, an answer within a stage's reply) and the tier read weak. Those checks now fall back to `required` with the one tool offered, which forces it the same and which that engine enforces (`deep_diagnosis._forced_call`); the tool diagnosis still tests the named form itself, so its record of what the engine refuses stays true. Test `test_a_check_forces_the_answer_tool_in_the_form_the_engine_accepts.py` | BUILT 2026-10-24, deployed before the gpt-oss baseline | [monitoring handover §0](monitoring-handover.md) |
| LF.263 | an engine that takes only string tool choices was run with `auto`, and its own parser rejected the model's output: on an LM Studio server running gpt-oss-20b a named `tool_choice` is a 400, the diagnosis concluded "forcing does not work" and switched forcing off for the server, and the client then rewrote every forced choice, `required` included, to `auto`. With `auto` the model's output failed the engine's parser ("does not match the expected peg-native format"): 0 or 1 replies in 3 answered, the consult stages failed on every attempt, and the baseline run was cancelled in its first minutes. With `required`, even with all the stage tools offered, all 3 answered. The diagnosis now checks `required` on a stage-shaped request (`a structured answer, required`) and settles on `structured_answers = "required"` when the named form is refused for its type and `required` works; `apply` and the client send a named choice as `required`, and a first refusal teaches the client the same (`models._NAMED_CHOICE_BECOMES_REQUIRED`). Test `test_an_engine_that_takes_only_string_tool_choices_is_sent_required.py` | BUILT 2026-10-24, deployed before the gpt-oss baseline restart | [monitoring handover §0](monitoring-handover.md) |
| LF.264 | a run failed because a file's bytes were not UTF-8: the measure that fingerprints the product read `git diff` with strict decoding; the decode error is a ValueError, which the call sites' `except (OSError, SubprocessError)` do not catch, so it ended the run in the middle of a fix with its sprint half done. All twelve git reads in the product (fingerprint, lines a fix added, a file's last commit, the history view, the delivery diff, release audits, repository status and ignore checks, seeding) now decode with `errors="replace"`: git output is read for its shape, never for exact text. Test `test_a_git_answer_that_is_not_text_does_not_end_the_run.py` (three behaviours, plus a guard that fails when any git call decodes strictly) | BUILT 2026-10-24, deployed mid-run, run resumed | [monitoring handover §0](monitoring-handover.md) |
| LF.265 | the model pick of a proven setup (LF.259) never ran for the Hono stack: the list of candidates was built with `' '.join(declared['unit_test'])`, which raised `TypeError` for an entry whose declaration held a list of argv lists, and the broad `except Exception` that keeps the pick from ever hurting a run hid it, so no entry was offered to the model and the stack set itself up from nothing (found by reproducing the pick on the live run's stack). A declared command is now flattened whether it is a string, an argv list or a list of them (`_command_words`). Test added to `test_a_proven_setup_is_found_by_what_the_stack_is_not_by_how_it_was_worded.py` | BUILT 2026-10-24 | [monitoring handover §0](monitoring-handover.md) |
| LF.266 | a Node command in a stack no pack covers ran under the 1 GB data limit and every test-runner worker thread died (`Fatal process out of memory: Failed to reserve virtual memory for CodeRange`, exit 133): the replayed Hono setup could not be proven, the setup agent could not get a unit test to run (it tried jest flags on vitest), and the locked acceptance suite "could not run" three times. The 4 GB Node room existed but only where a stack pack said its tests run on Node; a replayed or agent-written setup has no pack. `_process_memory(workspace, argv)` now gives a command whose program is a Node launcher (`npm`, `npx`, `node`, `pnpm`, `yarn`) the Node room whatever the project; the tree watcher still bounds real use, and container mode (a real cgroup limit) is unchanged. Test added to `test_a_node_toolchain_gets_room_for_its_threads.py` | BUILT 2026-10-24 | [monitoring handover §0](monitoring-handover.md) |
| RL.1 | a product the locked suite accepts was thrown away over the model's own unit tests. A gpt-oss-20b run on the notes-api brief scored hidden 9 of 9 and ended as failed: 17 of 18 criteria passed (the 18th a test flaw a dispute had already deferred), and the project's own unit tests, written by the same model, would not pass - every fixer gave up or was reverted for breaking a test that passed. Each release hold on them sent the last sprint round again, each round ended in an escalation, and the escalation budget (3) ran out ("not converging"). `release_with_failing_unit_tests` (switch `RELEASE_WITH_FAILING_UNIT_TESTS`, off in code, on in compose): when only the unit tests fail and the sprint was accepted at an escalation with them open, or the release has held as often as it may, the product is released with a named gap in `completion_gaps` (never when a criterion fails, the suite does not run, or the handoff is not ready). Off = the old behaviour. Tests `test_a_product_the_suite_accepts_is_released_with_its_failing_unit_tests_recorded.py`. To measure: runs that reach the release with failing unit tests - released with the gap vs the old stop | BUILT 2026-10-24, owner away: switch on, tell the owner | [monitoring handover §0](monitoring-handover.md) |
| LF.219 | scoring: the hidden-test runner was taken as ready when its interpreter existed, so an install cut off part-way (a scoring command whose output pipe closed early) left it without pytest; every hidden test then produced no report, and gated run 2 - 10/10 in truth - was scored 0/10 as a FALSE ACCEPTANCE and entered the KPI ledger. The runner is ready only when `import pytest, httpx` succeeds (reinstalled otherwise); a run whose hidden tests produced no report is UNSCORED (score None, never a false acceptance) and `report.py` leaves it out; tests in `test_benchmark_measures_trust_in_done.py` | BUILT 2026-10-23 (tooling, no run behaviour) | [monitoring handover §0](monitoring-handover.md) |
| LF.220 | `VERIFY_AFTER_WRITE` told a fixer its defect was fixed and to answer, and a model could carry on regardless: on run-3bfd71ee a fixer whose unit-test defect was fixed (53/53) was told so seven times and went on diagnosing another defect's 500s with throwaway scripts, on work another fixer is given. After the second pass notice, the last measurement still a pass, the stage is left only its answer (tools withheld, `_FIXED_ANSWER_NOW_NOTICE`); counted from the conversation; test `test_a_fixer_told_its_defect_is_fixed_is_left_only_its_answer.py` | BUILT 2026-10-23, deployed into run-3bfd71ee (time-wasting) | [monitoring handover §0](monitoring-handover.md) |

### Work batching (owner 2026-10-24; design and evidence in [work-batching.md](work-batching.md))

| Row | What | Status | Evidence |
|---|---|---|---|
| WB.8 | `loop.sh scan`: tokens a call and minutes a stage against the last five runs' medians, longest replies, redundant reads, a model's outliers; read at every audit with `loop.sh patterns` | BUILT 2026-10-24 `scripts/loop/scan.py`, `loop.sh scan`; test `test_the_scan_names_a_stage_far_out_against_the_recent_runs.py` | Ornith 17k tokens a call in the acceptance author against Qwen's 1-2k went unremarked for two audits |
| WB.9 | a reply ceiling chosen from what a model did on real runs: `loop.sh scan` suggests one when 10% or more of replies are over 16,000 tokens and hold half the output; `loop.sh ceiling <tokens>\|none [why]` sets it in the model's deep record (`reply_ceiling_from`); `deep_diagnosis.keep` keeps it across a new diagnosis. First use: Ornith 24,000 (21 of 97 replies held 73% of output). Judge by the run: hidden score, `loop.sh effects` salvaged against lost, minutes. Test `test_a_reply_ceiling_chosen_from_the_runs_is_kept_and_suggested.py` | BUILT 2026-10-24, deploy with the next fix | `work-batching.md` section 8 |
| WB.1 | Work-plan module (items, core, carry, join), a capacity check in the deep diagnosis (most items finished in one reply), shadow `work_split` records, `effects` lines; inert | PARTLY BUILT 2026-10-24: batch size by the model's measured tier (`acceptance_batches.batch_size`; strong or unmeasured = one batch) and a logged plan when the switch is off; the measured-capacity check in the diagnosis and the generic module are still to do | `work-batching.md` section 3 |
| WB.2 | Acceptance author in batches of criteria (one file a group, shared helpers first, `AC-n` coverage check) | BUILT 2026-10-24 `acceptance_batches.py`, switch `BATCH_ACCEPTANCE_AUTHOR` (code off, compose OFF after the first measurement: on Ornith part 1 took 3 calls, 63k tokens, 16 min and wrote nothing, because the cost is per turn, not per criterion - `work-batching.md` section 8); first writing only, 8 criteria a batch for a standard model, 4 for a weak one, then one `fill` batch for any criterion left untested; resumable through `suite.coverage`; tests `test_the_acceptance_suite_is_written_in_batches_when_the_model_needs_it.py`. Quality gate: next tasks-api run against run-2b891f3f (hidden, quality, mutation not lower; acceptance-author minutes and tokens a call lower) | 14 calls, 240k tokens, 17k a call on Ornith |
| WB.3 | Fixer bundle size set by the model's capacity | DROPPED 2026-10-24 after reading the code: `MOST_BUNDLED_DEFECTS = 2` already caps a fixer at three defects (added from the same measurement); the 4+ rows of `loop.sh patterns` are history, and for 2-3 defects the fix rate (53% against 56%) and the tokens a defect (58k for three against 19.5k each) match single defects. Revisit only if `loop.sh scan` flags defect_fix | `loop.sh patterns` (all runs, confounded) |
| WB.4 | Specification core and parts chosen by size, component by component for large products | FILED | architect 13.6k a call on Ornith |
| WB.5 | Work orders and sprint planning per milestone | FILED | technical_lead p90 21.9k, 11% cut |
| WB.6 | Review sharding for large codebases, clean-context reviewer | FILED | p90 16-25k |
| WB.7 | Settings page: capacity, per-stage `BATCH_<STAGE>` switches, last fallbacks | FILED | guides' panel as the model |

### One writer, independent checkers (owner question 2026-10-24; review in [single-writer-review.md](single-writer-review.md))

| Row | What | Status |
|---|---|---|
| SW.1 | `loop.sh scan` reports defects by source and who wrote the product, per run | BUILT 2026-10-24 (`scan.provenance`; test in `test_the_scan_names_a_stage_far_out_against_the_recent_runs.py`) |
| SW.2 | QA writes the suite before product code; setup stops at the smoke path (the three setup fixes stay) | FILED |
| SW.3 | A single builder stage with the run-and-fix loop, for products whose working set fits a context budget, behind `SINGLE_BUILDER` with a fallback | FILED |
| SW.4 | The measured arm: two runs each, same model, current flow against the new one (MF.4 gate) | FILED |
| SW.5 | Above the budget: module-by-module writers with a carried interface ledger, shared with WB | FILED |

### Setups captured and replayed, workers that build and learn (owner 2026-10-24)

| Row | What | Status |
|---|---|---|
| SP.1 | A proven setup is found by what the stack is, else by the model's pick, and always proved by the harness (LF.259) | BUILT |
| SP.2 | Harvest a setup from a finished run that passed (declaration inferred from the package scripts and the QA's declared command; real tests as smoke tests), prove it in a clean copy by the harness, keep it | FILED |
| SP.2a | A library entry must replay on an empty project. Measured on the first Hono run to try it: the entry's unit smoke test imported a product module (`../../src/db.js`) the entry did not keep, and its tsconfig included only `src/`, so `tsc` found no inputs, the proof failed and the setup agent (gpt-oss-20b) then failed twice on a test API it invented (`createTestClient` in `hono/testing`). Two parts: (1) `remember` keeps an entry only when its smoke files import nothing outside the kept and smoke files (a smoke test of the product's own module is the setup stage overreaching, SP.5); (2) a Hono pack (SP.3), because a stack the benchmarks use every week should not depend on a weak model inventing its test harness. Open design question for (2): Node 24 strips TypeScript types natively, so a pack could run `node --test` on `.ts` files with `tsc --noEmit` as the type check and no extra runner | FILED 2026-10-24, from run-73e5c929 |
| SP.3 | Promote a library entry replayed successfully on two runs to a code pack, tested by `verify_packs` | FILED |
| SP.3a | a Hono pack (`node-hono-api`, TypeScript, Jest with ts-jest like the Nest pack, Playwright `request` acceptance): the benchmark stack of the Hono baselines had no pack, so a small model's setup stage invented `createTestClient` from `hono/testing` and the run failed because its acceptance suite could not run. Scaffolded for real with `scripts/loop/verify_packs.py` (install, unit smoke and acceptance smoke pass in 17 s). A TypeScript stack naming Hono gets it; JavaScript + Hono, Elysia and Fastify still get none rather than another framework's pack. The guide first said there is no `hono/testing` client, which was wrong (it exports `testClient`); corrected 2026-10-24 after a run's worker invented `createClient`. Tests `test_hono_has_a_pack_that_tells_a_builder_the_real_test_api.py` and the selection cases in `test_programs_and_libraries_in_every_major_language.py` and `test_a_runtime_name_is_not_a_framework_choice.py` | BUILT 2026-10-24 | [monitoring handover §0](monitoring-handover.md) |
| SP.4 | Order of setup: pack, library replay, then an agent that verifies and adjusts; stacks composed from component recipes (runtime, framework, runner) | FILED |
| SP.5 | Fence the setup stage to its declaration, kept files and smoke files, so the workers build the product; QA writes the suite first (SW.2) | FILED |
| SP.6 | Per-role lessons: a defect's lesson is shown to the role that owns it; report defects per role per run | FILED (the lessons store and the owning role exist) |

Rules for the set: each stage its own switch, code default off; shadow records before anything acts; identical request when capacity covers the work; coverage check then fall back to the single call; resumable per batch; a quality gate (hidden, quality, mutation not lower; minutes, tokens a call or cut-offs lower) before default-on.
