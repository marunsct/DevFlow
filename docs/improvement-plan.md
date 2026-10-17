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

## 3. Technology-Agnostic Harness Improvement Initiatives

### Initiative A: Procedural Design System & Token Seeding (`stacks/packs` & `seed.py`)
- **Concept**: Never force a small model to invent a design system from an empty CSS file.
- **Harness Mechanism**:
  - In `src/app/stacks/packs/_javascript.py` and `src/app/plugins/seed.py`, embed high-quality baseline CSS custom properties in the project scaffold:
    ```css
    :root {
      --font-sans: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
      --color-bg: #f8fafc;
      --color-surface: #ffffff;
      --color-text: #0f172a;
      --color-text-muted: #64748b;
      --color-primary: #2563eb;
      --color-primary-hover: #1d4ed8;
      --color-border: #e2e8f0;
      --radius: 0.5rem;
      --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
      --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
    }
    ```
  - Provide modern CSS reset defaults and accessible focus indicators (`:focus-visible`).
- **Impact**: Specialists immediately write beautiful, accessible layouts adhering to modern design standards without wasting context tokens.

### Initiative B: Procedural Visual & Layout Audits (`page_view.py`)
- **Concept**: Ground the UI specialist with concrete layout measurements instead of raw HTML strings.
- **Harness Mechanism**:
  - Automatically invoke `look_at_page` following UI specialist file modifications.
  - Compute layout boundaries via Playwright:
    - Check if `document.documentElement.scrollWidth > window.innerWidth` (flags mobile horizontal overflow).
    - Detect whether clickable targets are smaller than 44x44px.
    - Check for missing `aria-label` or `<label>` associations.
  - Return these computed diagnostics directly into the model's next turn prompt as a feedback notice.

### Initiative C: Contract-Strict Interface Extraction in Specification
- **Concept**: Ensure the architect and technical lead explicitly define UI element selectors, labels, and roles during specification before code generation begins.
- **Harness Mechanism**:
  - In `src/app/agents/principal_architect.py`, ensure `TechnicalSpecificationOutput` requires an explicit `ui_contract` listing every interactive element:
    - Target element tag (e.g. `button`, `input[type="checkbox"]`, `select`).
    - Exact accessible label (`aria-label`, `<label>`, or inner text).
    - Expected ID or data attribute.
- **Impact**: Eliminates test mismatches (like the 5/10 hidden score) by ensuring implementation specialists and acceptance authors share the exact same DOM contract.

### Initiative D: Pre-Execution Linter and Assertion Normalizer Gate
- **Concept**: Catch syntax and assertion errors before launching heavy container runners.
- **Harness Mechanism**:
  - In `src/app/tools/sandbox.py`, run a fast AST/linter check on modified test files.
  - Automatically detect and correct deprecated or mismatched assertion calls (e.g., mapping `assert.notMatch` $\to$ `assert.doesNotMatch` in `node:test`).
  - Provide instant error feedback when invalid syntax is detected without spending test round timeouts.

### Initiative E: Narrow, Single-File Work Orders
- **Concept**: Limit the cognitive load on smaller models by restricting work order tasks to single files.
- **Harness Mechanism**:
  - In `src/app/graph/planned_work.py` and `technical_lead.py`, enforce that a single work order modifies at most one core product file (`app.js`, `index.html`, or `styles.css`) and its paired test.
  - Keep prompt sizes under 4,000 tokens during specialist execution.

### Initiative F: Root-Crash & Load-Error Pre-Check Gate (Prevent Defect Sprawl)
- **Concept**: Catch root initialization crashes before evaluating downstream element assertions.
- **Harness Mechanism**:
  - In `src/app/acceptance/suite.py` and defect queue generation, detect if the application fails to boot, import scripts, or load the DOM cleanly (*"The product reports errors by itself while it loads"*).
  - Treat this root load error as a blocking prerequisite defect. Defer queueing downstream element selector defects (e.g., button, filter, checkbox checks) until the application initializes cleanly.
- **Impact**: Prevents cascading defect sprawl (e.g., 15 simultaneous defects generated for 1 root load error in `run-77c6650e`), saving 10–15 redundant fixer invocations and ~20 minutes of wall-clock time.

### Initiative G: Lenient Whitespace and Unicode Normalization in `edit_artifact`
- **Concept**: Prevent failed tool calls caused by trivial whitespace or character formatting differences.
- **Harness Mechanism**:
  - In `src/app/tools/artifacts.py` (`edit_artifact`), when an exact literal string match fails, attempt a **normalized fallback match**:
    - Trim trailing whitespace per line.
    - Normalize Unicode dashes (`─`, `—`, `-`) and curly quotes.
    - Check if a unique normalized block match exists.
  - If a single unambiguous match is found, apply the replacement cleanly.
- **Impact**: Eliminates recurring tool retries observed in `specialist_testing` and acceptance authoring where models format comment dividers or indentation slightly differently than disk.

### Initiative H: Pre-Flight State Verification Before Defect Fixer Dispatch
- **Concept**: Never invoke a defect fixer if the defect's target condition is already satisfied on disk.
- **Harness Mechanism**:
  - In `src/app/graph/engineering.py`, before launching a defect fixer node, execute a lightweight pre-flight check (file existence, AST check, or targeted test rerun).
  - If the requested change is already present (e.g., `defect_fix_2_17` in `run-77c6650e` where a file rename was already completed by a preceding stage), immediately close the defect and advance without launching the model node.
- **Impact**: Saves 10–12 model calls and 3–5 minutes per sprint by bypassing already-resolved defect tickets.

### Initiative I: Reasoning Token Budget Governor for Synthesis & Planning Roles
- **Concept**: Prevent reasoning models from consuming their entire reply budget before generating tool calls.
- **Harness Mechanism**:
  - In `src/app/agents/context_budget.py` and model request parameterization, set a bounded `max_thinking_tokens` (e.g., 2,048 tokens) for stages that require tool invocation (`principal_architect`, `technical_lead`).
- **Impact**: Guarantees the model retains sufficient output budget to emit tool calls in its initial turn, avoiding the zero-call reasoning exhaustion observed in `run-77c6650e` and `run-bf43c7e2`.

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

