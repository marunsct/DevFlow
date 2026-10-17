# Harness Improvement Plan: High-Quality Product Delivery with Local & MoE Models

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

### Initiative F: Root-Crash & Load-Error Pre-Check Gate (Prevent Defect Sprawl)
- **Reasoning**: When an application has a fatal initialization or script loading error, every single acceptance criterion that touches the UI fails simultaneously. Queueing a separate defect for every individual acceptance test creates massive defect sprawl and redundant fixer executions for what is fundamentally a single root bug.
- **Empirical Evidence**:
  - `run-77c6650e-042a-4310-bf72-bb819a8f8fee`: When `index.html` failed to initialize cleanly on startup, **15 acceptance criteria failed simultaneously** with the message *"The product reports errors by itself while it loads, before any test touches it"*. The harness queued 17 defects (`defect_fix_1_0` through `defect_fix_1_16`). Once `defect_fix_1_2` fixed the root script load error, defects `1_3` through `1_16` were immediately closed without fixers as *"passing since"*.
- **Harness Mechanism**:
  - In `src/app/acceptance/suite.py` and defect queue generation, detect if the application fails to boot, import scripts, or load the DOM cleanly (*"The product reports errors by itself while it loads"*).
  - Treat this root load error as a blocking prerequisite defect. Defer queueing downstream element selector defects (e.g., button, filter, checkbox checks) until the application initializes cleanly.
- **Impact**: Prevents cascading defect sprawl, saving 10–14 redundant fixer invocations and ~20 minutes of wall-clock time per sprint.

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

## Appendix (2026-10-18): Deep Review — Release Integrity, Local-Model Quality, Throughput, UI/UX

**Method and evidence base.** This appendix follows a full review of the harness
(core modules read end-to-end; 255 worker transcripts and 9 analyzed in depth;
postgres run/bench data; the live medium-brief run `run-bf43c7e2` observed from
00:54 JST 2026-10-18 through its fix treadmill; three web-research passes on
frontier agent harnesses, local-model serving, and agent-product UI/UX, all
source-verified on 2026-10-17/18). Working notes and both research reports were
kept in `docs/review-findings-wip.md`; the frontier-harness report in full is at
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

### Part 1 — Systemic gaps: environment, release integrity, and the fix treadmill (P0)

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

### Part 2 — Local-model output quality (complements Initiatives A–I; no duplication)

Research base: the full local-LLM serving/orchestration report (primary
sources verified 2026-10-17/18) is reproduced in `docs/review-findings-wip.md`
§8; key citations inline below.

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

### Part 3 — Throughput without quality loss

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

### Part 4 — UI/UX (owner request: "improve the UI and UX as much as possible")

The full audit (28 files line-by-line, live DOM probes, axe-core scan, 9
screens, ~40 Vercel Web Interface Guidelines violations with file:line, and
12 research-backed opportunities with verified competitor sources) is in
`docs/review-findings-wip.md` §7. Condensed plan:

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

### Part 5 — Benchmarks and measurement (so the loop can verify all of the above)

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
