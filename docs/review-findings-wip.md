# WIP — Deep harness review findings (2026-10-18, review session)

**Status file.** This is the working evidence log for the deep review requested by
the owner on 2026-10-18 (JST). The final deliverable is an improvement plan
appended to `docs/improvement-plan.md` (backend + local-model quality + UI/UX).
No code is being changed. This file exists so findings survive session loss;
it is the evidence archive referenced by the appended plan (keep while the plan is live).

## 0. Task constraints (from owner)

- Deep review of the harness; improve performance WITHOUT compromising quality.
- Harness is mainly for LOCAL AI models → make local models produce high-quality output.
- Review only; create improvement plan; APPEND to existing plan in docs/
  (`docs/improvement-plan.md`, dated 2026-10-17, Initiatives A–I + roadmap).
- Docker run logs available and in use (run is LIVE: `run-bf43c7e2`, medium brief, fast mode).
- Deep web research on frontier agent harnesses; latest info, not memory.
- Reasoning + evidence for every suggestion.
- Language- and framework-agnostic product.
- NEW (2nd message): also plan UI/UX improvements (current UI "good but not great").

## 1. Subagents in flight (collect before finishing)

| id | task | status |
|---|---|---|
| f85b6e1b-4a23-4301-b09d-f8513dd1c924 | Docker log/transcript forensics | **DONE — report in §5** |
| 8408a576-4a67-4ec4-8ec8-256713608e1c | Frontier harness research (web) | running |
| d2176eb1-b9d7-47e6-9c83-13af84703aaf | Local/small-model quality research (web) | **DONE — full report in §8** |
| d0e933d9-1873-4ed7-a913-3ea7bb3dc3da | UI/UX audit + research | **DONE — report in §7** |

## 2. Repo/context map (already reviewed)

- ~95k LOC Python under `src/app`. Biggest: `graph/workflow.py` (10.5k),
  `tools/repository.py` (7.4k), `analysis/integration_checks.py` (7k),
  `tools/sandbox.py` (4.7k), `agents/settled_answer.py` (2k).
- UI: `langchain-ui/` React 19 + Vite + Tailwind 4, ~7.3k LOC / 28 files.
  Biggest: Settings.tsx (912), RunDashboard.tsx (720), wizardData.ts (694),
  WizardDashboard.tsx (624), AgentActivity.tsx (507), Home.tsx (466).
- Docs read: HANDOVER.md (§0,2,2.3,2.4,5,6,7), monitoring-handover.md
  (§0.9,0.10,5,6,8,9,10), harness-improvement-plan.md (full), improvement-plan.md (full).
- Code read (full or key parts): agents/role_agent.py, agents/thinking.py,
  models/__init__.py, models/roles.py, agents/context_budget.py,
  agents/workspace_digest.py (injection = append-at-end, cache-friendly),
  server/runner.py `_run_loop`/`_handle_state`, graph/workflow.py
  `_run_gated_agent` + `queued_parallel_pauses` + node list, delivery.py,
  models/call_gate.py, tools/sandbox.py (header+network policy),
  graph/drafting.py, graph/planned_work.py, models/fitness.py,
  models/tool_arguments.py (header), agents/text_tool_calls.py (header),
  agents/settled_answer.py (header), tools/package_registry.py (header),
  stacks/packs/_fullstack.py (grep), stacks/contract.py (grep).

### What the harness ALREADY does well (plan must not duplicate)

Two-tier models (build/judgement) + escalation after 2 attempts; fast/thorough
delivery; per-file one-call drafting from spec; harness-made work orders;
project memory + workspace digest + project snapshot; read ladder; repeated-query
detection; settled-answer loop break; text-tool-call recovery; tool-name mapping;
truncated tool-call recovery w/ held fields + continuation prompts; reasoning
carry-over (append-only, prompt-cache friendly); paced timeouts + reply-cap
halving retries; thinking probe (`least_reasoning_effort`); fitness probe;
call gate for mid-run deploys; orphan recovery/abandoned threads; rewind
snapshots; CI gate w/ revert; locked acceptance suite w/ dispute engine;
IDE-grade language checks; proven-setup replay; research share limits;
sandbox = argv-only, no shell, per-category network (install only), fail-closed.

## 3. My findings so far (with evidence) — LIVE run-bf43c7e2 (medium brief, fast, local Qwen3.6-35B-A3B on :8888)

### F1 (CRITICAL): Fullstack entrypoint never wired to drafted code
- Pack `fullstack-react-fastapi` scaffolds stub `task_management_dashboard/main.py`
  (only `/api/health` + static dist serving) and `serve-acceptance.mjs` launches
  exactly that stub via uvicorn.
- Spec file plan put the real app in `backend/` (main.py with create_app(),
  routers auth/tasks/users/analytics, SQLAlchemy, alembic). Drafting wrote those files.
- Nothing imports/mounts `backend` into the stub → acceptance server serves only
  health + Swagger UI. Result: 31/35 acceptance tests fail; the 4 passing are
  stub artifacts (health, Swagger UI, 2 accidental 404→page fallbacks... 3 passed).
- Evidence: ci.json latest (before defect_fix_2_1): 31 failed / 4 passed;
  workspace inspection: stub main.py vs backend/ tree; serve-acceptance.mjs
  `start_argv` from `_fullstack.py` line 413.
- Consequence: fixers edit backend/ → zero effect on suite; any change that
  breaks the stub's 2 passing tests → whole-stage revert (see F5) → treadmill.
  Two stages already reverted: worker log 16:55 & 17:07 UTC
  "Reverted defect_fix_1_1/1_2: it broke 4 test(s) that passed before it".
- Fix direction: post-drafting "entrypoint wiring gate" — boot the pack's
  acceptance server, probe the spec's declared routes (route table is IN the
  spec), one ROOT defect "entrypoint does not serve the planned API" instead of
  N criterion defects. Language-agnostic: contract declares health/route probe.

### F2 (CRITICAL): No service provisioning; spec free to require PostgreSQL
- brief_medium asks for PostgreSQL; spec mandates real Postgres ("not SQLite...
  TEXT[] arrays, GIN indexes, @> containment"), asyncpg + alembic + DATABASE_URL
  required (no default) + startup migration.
- Sandbox has NO database service; `pg_isready` not even an allowed executable;
  pack contract (`stacks/contract.py`) has NO `services` concept; acceptance
  webServer passes only PORT + DATA_DIR.
- Result: app can never satisfy its own spec in the test env → every AC fails →
  unfixable defect loop. Same shape as run-fd3a244d (6h Celery limit, 13/13
  "untested") and run-c7a1f6cf (9h52m fail in defect fixing).
- Fix direction: (a) environment capability profile injected into architect
  prompt as hard constraint; (b) pack contract `services:` (image, env,
  healthcheck) started by sandbox runner per test round (docker socket already
  used); (c) spec-level substitution rule (embedded equivalent behind interface,
  recorded as decision) when service can't be provided.

### F2-REFINED (CRITICAL, root cause located): capability knowledge asymmetry
- `stack_selector.describe_execution_environment()` (stack_selector.py:133)
  ALREADY tells the selector: "NOTHING IS RUNNING... no database server...
  A brief may still *require* PostgreSQL, and you should still choose it - but
  the design has to be verifiable without a live one: data access behind an
  adapter the tests can substitute, migrations written and reviewed rather
  than applied...".
- grep proves it is used ONLY in stack_selector.py (lines 206/251). The
  principal architect (who writes the spec), the acceptance author, and the
  specialists never see it. The live run's architect therefore specified
  asyncpg + required DATABASE_URL + startup alembic migrations — exactly what
  the selector was warned against — and acceptance tests hit real endpoints.
- Fix direction (three layers, all agnostic):
  1. Give the same derived environment description to architect, acceptance
     author, and specialist prompts (one shared builder; derived from the
     allowlist + pack contract so it cannot drift).
  2. Deterministic spec gate: flag "requires a live external service at
     startup or test time" (startup migration, required env with no default,
     driver connect at import) → back to architect with the reason, like the
     other spec send-backs.
  3. Optional (bigger): pack-contract `services:` provisioning via docker
     sidecars for runs that SHOULD exercise a real service (brief_medium asks
     for PostgreSQL; hidden-test parity). Decide after 1+2 measured.

### F3 (HIGH): Dependency-manifest drift after drafting
- Drafted code imports sqlalchemy/pydantic-settings/jose/passlib/asyncpg/alembic/
  bleach; `requirements.txt` still only fastapi+uvicorn. Nobody reconciles
  imports↔manifest before test rounds.
- Evidence: transcript tool results — fixer tmp-check "No module named
  'pydantic_settings'/'sqlalchemy'/'jose'"; 30+ fixer calls spent on pip
  installs; `.venv/bin/pip install ...` by defect_fix_1_1 SUCCEEDED (installed
  19 packages) but was invisible to defect_fix_1_2 which reinstalled.
- Fix direction: deterministic "manifest reconciliation" gate after
  drafting/compile-repair: scan imports per language (pack knows the manifest +
  install command), append missing, re-run install (network category exists).

### F4 (HIGH): Sandbox python env ambiguity (venv vs user-site)
- Bare `pip`/`python3` in sandbox = system python; installs go to
  `.agent-home/.local` ("Defaulting to user installation because normal
  site-packages is not writeable") — invisible to `.venv/bin/python` the
  acceptance server uses. Fixer verified with `pip list` and believed deps were in.
- Fix direction: sandbox prepends project venv bin (`.venv/bin`,
  `node_modules/.bin`) to PATH when a pack declares one; or refuse bare
  pip/python when a venv exists, with a notice naming the venv interpreter.

### F5 (HIGH): All-or-nothing stage revert by CI gate
- "it broke 4 test(s) that passed before it" → ENTIRE fix stage reverted,
  discarding the (correct) dependency work and any good edits; next fixer starts
  from identical state; loop. Two consecutive reverts observed live.
- Fix direction: per-defect/per-file revert granularity, or auto targeted
  repair round on only the broken tests before reverting everything; keep
  manifest/dependency changes out of revert scope.

### F6 (HIGH): Defect sprawl from single root cause (confirms plan Initiative F)
- test_round_0 raised 13 defects (12 ACs "does not work yet" + 1 lint) at
  16:39:41 — one root cause (server stub doesn't implement API). Bundling
  exists (`_bundle_defects_by_specialist`) but bundles 10-12 defects into one
  fixer with a 40-call budget → fixer cannot fix 12 criteria in one visit;
  reverts make it worse.
- Fix direction: root-cause grouping BEFORE queueing (boot/route probe F1,
  dependency probe F3): if the server cannot serve the spec's routes, that is
  ONE blocking defect; criterion defects deferred until it passes (exactly
  Initiative F generalized from "load errors" to "missing service wiring").

### F7 (MEDIUM): Reasoning exhaustion still live
- 17:18:43 UTC defect_fix_2_1: "Stage specialist_backend lost a reply to
  reasoning (1 in a row); asking again at once with thinking off" + "spent a
  whole reply's output budget on reasoning; thinking switched off for next
  reply". 8 `finish_reason=length` in 151 responses so far; max output 20,000.
- Existing mitigations fire AFTER a wasted 20k-token pass. Confirms Initiative I
  (bounded thinking budget up-front) — add evidence.

### F8 (MEDIUM): Very large prompts on judgement stages
- acceptance_review_1 median prompt 203k chars (~65k tokens), acceptance_dispute
  188k, scrum_master 124k, principal_architect 100k. On a local server prefill
  is slow and context rot is real (research pending). Window is ~130k tokens
  (settings) — these are near half the window in ONE message set.
- Fix direction: budget the review corpus (locked suite is ~35 tests; send
  per-file or summarized), spec section windows, cache-friendly ordering.

### F9 (MEDIUM): Streaming disabled by langchain incompatibility
- models/__init__.py `_request_timeout` docstring: streaming would fix the
  timeout-vs-length tension but `streaming=True` breaks through
  langchain.agents ("Expected a dict or openai.BaseModel, got Stream") — "Revisit
  only with a reproduction through langchain.agents". Worth retesting with
  current langchain-openai >= 1.0 (may be fixed upstream now).
- Streaming also unlocks live token streaming to the UI (UX win).

### F10 (MEDIUM): Parallel mode gets ~1.0-1.3x overlap; server is 1 slot
- Monitoring §0.9: "LM Studio's 8 slots go unused"; gated pauses drain one per
  superstep; HANDOVER §7: fixing = redesign of runner auto-approve loop.
- Also queueing: parallel specialists against a 1-slot llama.cpp server just
  serialize with extra prompt-cache thrash (each switch = new slot prefix).
- Fix direction: match HARNESS_MAX_PARALLEL to server slots (capability probe);
  server-side: recommend llama.cpp `--parallel N --cont-batching` or vLLM
  continuous batching in readiness docs; or harness-side "phase-aligned"
  scheduling so same-stage agents batch their calls.

### F11 (LOW/MED): integration_checks.py is JavaScript-shaped
- Function inventory shows node/browser/CSS/DOM checks dominate
  (`_node_suites_nothing_runs`, `_dangling_class_selectors`, browser events...).
  harness-improvement-plan B1 admits "Multi-file symbol references for Go, Rust,
  polyglot still heuristics". For language-agnostic claim: Python/Go/Rust
  products get weaker static integration analysis than JS.

### F12 (OBSERVATION): test_round "did not report 13 failing criteria;
recording them as defects" + "left out 2 problems it was handed as proven" —
harness-run test round works but the model round re-derives; fine. Also
"3 defects describe one problem; merged into one" — merging exists for
identical problems (frontend/package.json two test runners) but NOT for
common-root-cause criterion failures (F6).

### F13 (MEDIUM): Seed instructions can contradict the environment
- `plugins/seed.py` has a `postgres` key injected when the stack doc names
  PostgreSQL: guidance encourages pooled Postgres usage — while the sandbox
  provides no Postgres and `pg_isready` is refused. Python seed says "Do not
  install globally. Always use a virtual environment" — yet sandbox gives bare
  `pip` that installs to user-site (F4). This is monitoring §6.2's
  "instructing and then punishing" class, still live.
- Fix direction: seed rows must be filtered by environment capability (same
  capability profile as F2); sandbox PATH fix makes the python seed true.

### F14 (CONTEXT): Verified mechanisms relevant to plan (no gap, cite as strengths)
- `analysis/compiler_check.py`: Go/Rust/Java/C#/Swift/PHP compile checks +
  TS/Pyright language service; degrades silently when toolchain missing.
  → Python import drift IS visible to Pyright as notes, but nothing forces
  manifest reconciliation (F3) — the check reports, the gate doesn't act on
  undeclared-dependency class before test rounds.
- `graph/engineering.py after_a_fix`: regression → `ci.revert_to(root, base)`
  = git reset of WHOLE stage (F5 confirmed in code, line ~523).
- `graph/workflow.py _the_fix_request` (line ~8502): fixer already receives
  raw failure output (`_what_the_last_failure_printed`) + co-defect bundle +
  spec excerpts; `_settle_the_fix` verifies against execution ledger. Good —
  plan builds on it (root-cause grouping, not more context).
- `MODEL_CALLS_PER_STAGE = 40` (settled_answer.py:688);
  `MAX_REMEDIATION_ATTEMPTS = 3`; `INNER_AGENT_RECURSION_LIMIT = 40 × supersteps`.
- Sandbox auto-reclassifies dependency fetches to `install` category
  (network) and test commands to `test` (longer timeout) — sandbox.py:4438-4441.
- `models/window_probe.py`: real-context probe via deliberate oversized
  request (excellent; plan should extend this "probe, don't trust" pattern to
  tool-call parsing, thinking switches (exists), services, entrypoints (F1)).
- Defect merging exists for IDENTICAL problems ("3 defects describe one
  problem; merged") but not for common root cause (F6).

### F15 (HIGH): Opening requests on planning/judgement stages are 60-80k tokens
- Measured from live transcript (run-bf43c7e2, chars of full message list):
  scrum_master 241k (~80k tok), acceptance_review_2 191k (~64k),
  acceptance_author_1 183k, principal_architect 118k, architecture_review 116k,
  stack_selector 65k. Window ~130k → first call consumes 50-62% of window.
- Mechanism: spec excerpt budget = ContextBudget.specification_budget_chars
  (~69k chars for 130k window, 25% of ceiling), FRONT-LOADED `text[:budget]`
  (text_budget.excerpt) — arbitrary cut mid-document, no section awareness.
  (Legacy DEFAULT_SPECIFICATION_BUDGET=150k constant is dead/misleading;
  its docstring "roughly 15k tokens" is wrong at the measured 3 chars/token.)
- Cost on local server: cold prefill of 50-80k tokens per stage start
  (minutes on llama.cpp), context rot on a 35B MoE (research citation pending),
  and near-zero cross-stage prefix-cache reuse (each stage frames the spec in
  its own request text → different bytes → different prefix).
- Fix direction: (1) section-aware spec distribution — project_memory.digest_of
  already does "outline + sections by id/word" for >60k docs; reuse for spec
  excerpts per role (scrum master: criteria+file plan+dependencies; acceptance
  author: interface+error shapes+data model; reviewers: outline+named
  sections). (2) Byte-stable shared "spec block" placed identically right
  after system prompt in every stage that needs it, to maximize single-slot
  prefix-cache hits across stages. (3) Fix the stale 150k constant/docstring.

### F16 (STATUS): Visual review loop already exists (Initiative B ~80% built)
- `stacks/packs/_javascript.page_check` keeps page-desktop.png + page-phone.png
  every suite run; `agents/page_screenshots.py` sends both to milestone
  reviewer when `models/vision.reads_images` (name-family heuristic or
  MODEL_READS_IMAGES setting); `look_at_page` returns a11y tree + page errors +
  failed requests + (page-load.json) layout.accessibility + phoneOverflow.
- Remaining gap: axe-core-style contrast/a11y violation counts as numbers in
  the loop (currently 'accessibility' list exists in page-load.json — check
  depth), and visual findings do not GATE (reviewer-only). Local build model
  likely non-vision → judgement model must be vision-capable for this to fire.

### F17 (GAP): Benchmark corpus lacks fullstack-Python & service-backed briefs
- benchmarks/: web-todo, notes-api(-js/-hono), wordstats-cli, textkit-lib,
  fullstack-bookmarks, web-todo-react. Gate ladder covers JS/Python single-tier
  products. brief_medium (FastAPI+React+PostgreSQL) has NO hidden tests →
  audited by hand. The exact failure class of the live run (F1/F2) is
  invisible to the benchmark gate.
- Fix direction: add a `fullstack-py` benchmark (pack-supported, hidden tests
  through HTTP only) and a service-backed benchmark variant once F2 lands;
  both hold the fullstack packs to the same standard as the others.

### F18 (CONTEXT): Strong existing tooling to build measurements on
- scripts/loop/: run_timing.py, redundant_reads.py, model_fitness.py,
  lessons.py, defects.py, failures.py, audit_live.py, product_audit.py,
  stage_trace.py, check_precision.py, verify_packs.py, pack_freshness.py.
- evaluation/evaluate.py: LangSmith-based intake/architecture evaluators.
- Plan's measurement items should reuse these (e.g., add
  `entrypoint_wiring`, `manifest_drift`, `revert_treadmill` counters to
  audit_run/transcript_metrics).

## 4. Research interim (subagent d2176eb1, local-LLM) — SUPERSEDED by §8 (full report)

- vLLM: `--enable-auto-tool-choice --tool-call-parser <model-matched>` (qwen3_xml
  for Qwen3-Coder, hermes Qwen3, deepseek_v3, openai for gpt-oss, glm45/47);
  `--reasoning-parser`; native `thinking_token_budget` + `--reasoning-config`.
  (https://docs.vllm.ai/en/latest/features/tool_calling/,
  https://docs.vllm.ai/en/latest/features/reasoning_outputs/)
- Qwen3 thinking ON by default; per-request off via extra_body
  `chat_template_kwargs {"enable_thinking": false}` (harness already does this);
  Qwen3-Coder non-thinking, sampling temp 0.7/top_p 0.8/top_k 20/rep_pen 1.05,
  65k max output recommended. (https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct)
- gpt-oss requires harmony format; effort via system-prompt line.
  (https://github.com/openai/harmony)
- llama.cpp: `--jinja` needed for OpenAI tool calls; parallel tool calls exist
  but disabled by default; JSON-schema constrained decoding limits (no
  anyOf+properties mix, nested $refs broken, additionalProperties default false,
  unsupported keywords silently skipped; schema NOT injected into prompt —
  describe JSON in prompt too). (https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md,
  https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)
- Prompt-cache discipline: llama-server per-slot prefix cache (--cache-prompt
  default on; timings.cache_n); vLLM V1 prefix caching + chunked prefill default.
  Keep prompts byte-stable append-only (harness already does reasoning carry-over).
- Aider Architect/Editor split: 85.0% vs 79.7% solo baseline
  (https://aider.chat/2024-09-26/architect.html); code-in-JSON degrades code
  quality (https://aider.chat/2024-08-14/code-in-json.html) — relevant: harness
  drafting takes file content from fenced blocks in plain replies (GOOD), but
  write_artifact carries content as JSON tool arg (unavoidable; keep short).
- Quantization/context: q2_K drops Qwen2.5-Coder-32B 72.2%→61.7%; 2k ctx →
  51.9% w/ silent truncation (https://aider.chat/2024-11-21/quantization.html)
  — verify the 8888 server's real ctx & max-output; harness window setting must
  match reality (already a known rule).
- Full report pending (benchmarks, context rot, routing).

## 5. Forensics report (subagent f85b6e1b — COMPLETE, corrected numbers)

Scope: docker logs Oct 17 02:25→17:12 UTC; 255 worker transcripts; postgres
runs/model_profiles; data/bench scores. Config: build = unsloth/Qwen3.6-35B-A3B-MTP-GGUF
@ host:8888 (126k window, 20k max output, thinking=medium); judgement = qwen3.8-flash cloud.

### A. Failure modes (counts)
- **A1 CRITICAL — FALSE ACCEPTANCES**: 7/33 scored bench runs `false_acceptance:true`.
  run-94d2c449 (thorough, frontier judgement): locked-suite repairs spent →
  "Locked tests of AC-1/2/3/5 cannot pass... their failures are not product
  defects" ×5 → RELEASED → hidden score 1/10. run-3642baf8: unproven setup
  ("unit smoke test did not pass through node --test tests/**/*.test.js — exit 0,
  0 passed") + playwright failed same way 3× (18 events) → released → 1/10.
  run-866e972e: 5/10, ended with same defect raised→left open twice.
  Contrast run-77c6650e: 10/10 clean — huge run-to-run variance on same config.
  §5.2 monitoring: "Every run that shipped something broken shipped it with a green suite."
- **A2 HIGH — replace_lines 40–68% error** across 5 runs (58/85=68% run-46c9bd90;
  50/79=63% 992b132c; 42% 7bcdda40; 40% 866e972e). edit_artifact 0–20%.
  Error kinds: stale line numbers; parser-refusal trap ("TypeScript cannot parse
  this file on line 116" — cannot edit the broken file because it is broken);
  kept-file refusals.
- **A3 MED — hallucinated tool names still burn calls**: `edit_file` ×53 in one
  run (10.5% of its calls!) each answered "not a valid tool"; `global_99` ×16
  (grep args); `run_read_11=File` ×11; tools named `docs/architecture_review.md`;
  one-string argv `'npm", "run", "build"],category:'`. Mapping layer exists but
  misses these.
- **A4 HIGH — reasoning exhaustion**: "spent a whole reply's output budget on
  reasoning" ×20 + "lost a reply to reasoning" ×20 in today's 14.5h window;
  finish_reason=length: 72d4c9ee 23, 3642baf8 10, 46c9bd90 9, bf43c7e2 8,
  94d2c449 7. CORRECTED totals: ~560k tokens discarded today ≈1.6 GPU-h
  (~3h incl. thinking-off re-asks); 72d4c9ee alone ~460k (~1.3h). Per event:
  full 20k-token generation thrown away (200k/10 events verified in 3642baf8).
- **A5 HIGH — repeat/stall loops persist**: identical `changed_since_sprint
  {"sprint":1}` ×38 (72d4c9ee), ×20+×10+×7 (866e972e), ×14+×13 (7bcdda40);
  identical read_file ×27 (77c6650e acceptance_author_1); live bf43c7e2:
  pip install httpx ×5 in 20s, tmp-check-deps ×6, pip list ×6, budget warnings
  ×23, 7 tools withheld one by one. Weak models call withheld tools anyway
  (mitigation: remove all looking-tools after 2 more).
- **A6 MED — stale defect queues**: ×16 today "Defect already fixed... closed
  without a fixer"; test_round structured report systematically OMITS failing
  ACs (up to 15) → procedural backfill from stale measurement → fixers named
  then stood down (77c6650e: defect_fix_1_8…1_16).
- **A7 HIGH — locked-suite churn + reverted fixes**: bf43c7e2 locked 16:26 →
  2 stage reverts (broke 4 passing) → dispute → suite REOPENED 17:08 (~42min
  churn). 94d2c449: reopen ×2 → repairs spent → false accept. gemma once broke
  62 passing tests in one fix.
- **A8 MED — phantom write claims ×11 today** ("reported changing <files>,
  which nothing in it wrote"); two stages doubled down ("recorded without them").
- **A9 MED/HIGH — structured-output degradation**: lenient JSON reads ×6;
  spec revisions blank whole sections ×10 (error_catalogue, implementation_order,
  test_cases, configuration, library_usage, decisions — harness restores from
  previous); answers as plain text ×2+2+4 events; cut-offs at 60–106k chars on
  spec-scale outputs (992b132c cost ~1h49m); lead omitted selected_sprint_goal
  ×8 in 12min (46c9bd90); LFM list-as-string refusals killed run e3a83a33 (3/3 attempts).

### B. Token/time waste
- **B1 duplicate identical calls = 17–47% of ALL tool calls** (bf43c7e2 38%,
  94d2c449 47%, 77c6650e 43%, 3642baf8 34%, 866e972e 26%). ≈3–17M wasted input
  tokens/run (19–35% of prefill).
- **B2 prefill dominates**: in/out 31:1 (88.2M/2.80M, 46c9bd90, avg 69k/call);
  cache hit 45–73% → 2.4–15M tokens re-prefilled per run. Memory context grew
  44k→95k avg/request after project_memory deployed.
- **B3 (corrected)**: ~560k discarded reasoning tokens today ≈1.6 GPU-h pure
  generation (~3h with re-asks).
- **B4 model wait = 85–93% of wall**: p50 latency by input: <10k→55s,
  30–60k→68s, 60–120k→75s. 866e972e: 4.4h pure model wait in 7.6h run.
- **B5 redundant re-reads**: 395 pointer-answers in 8 runs (each a wasted
  10–75s round trip); reads ~70% of tool calls; 55% of reads ask for files
  untouched since last read.
- **B6 budget exhaustion after waste**: "close to its model-call budget" ×47 today.
- **B7 plan ping-pong**: milestone plan not ready ×5 + dispatched-with-problems
  ×1 today; recurring "No testing work order"; lead sent back 3× same plan
  (46c9bd90, ~40min); sprint re-planned 4×.
- **B8 package-lookup 404s ×29 today**: capitalized `Playwright` ×9, README
  casing retries ×12, pypi `PostgreSQL` ×2.

### C. Local-model specifics
1. Thinking exhaustion (A4) — Qwen3 MoE GGUF thinking=medium + 20k cap.
2. Malformed tool calls — 6+ repair layers accreted (unwrapped, list-it-held,
   offered-tool-meant, arg-fit mapping, lowercase retry, transcription repairs).
3. Structured-output fragility (A9).
4. Phantom completions (A8).
5. Loops (A5); 1-bit model worst (27× loop; ~5min/call when server shared).
6. Test-framework mixes: node --test glob not expanded by Node 20 (exit 0,
   0 passed — cost 3642baf8's setup proof), CSS role selectors, jsdom churn.
7. Unparseable drafted code: models.py "positional argument follows keyword
   argument" → redraft loop works but each pass = full file regeneration.
8. **Model-quality cliff**: local fast web-todo scored 0.1/0.1/0.5 in 3 of 4
   attempts; notes-api with frontier judgement 1.0. Local model drafts fine —
   FIXES and REVIEWS are the weak link (both bf43c7e2 reverts = specialist_backend fixes).

### D. Infra/throughput
1. Single shared model server = bottleneck (40s→~5min/call when shared);
   LM Studio raised "Context size exceeded" at ~54k despite 131k setting.
2. Prefill-bound latency (B4); >120k prompts occur (110 calls in 46c9bd90).
3. Connection failures: OpenAIConnectionError retry; OpenAITimeoutError ×2;
   LM Studio 404 "model downloaded but not loaded" ×6 (run pointed at server
   not serving its model); wedged call held 1800s once.
4. Celery 6h limit killed healthy progressing run fd3a244d (limits now 12h).
5. **Approval-gate stalls**: runs parked 12–13h in awaiting_approval
   (approval_timeout_minutes NULL); paused runs risk orphan-recovery
   resurrection competing for 2 worker slots.
6. Checkpoint msgpack serialization bug fixed (_StorableSerializer), 0 recurrences.
7. Disk: postgres 4GB; transcripts to 181MB/run; SSE client-disconnect warnings ×25.

### E. Quality compromises observed
1. Fast mode skips model code review entirely ("left to the tests and checks").
2. Milestone revision caps convert gating findings → "risks" and go on
   (46c9bd90 shipped with review-3 findings auto-accepted; ×2 today "gating
   finding naming no criterion while every test passes; recorded as minor").
3. Plans dispatched with known problems after 3 attempts.
4. Failing locked tests reclassified as test bugs after repair budget spent → shipped (A1).
5. Unproven setups "left to the agents" (3642baf8 ×2, 72d4c9ee).
6. All gates auto-approved in fast runs (by design, unattended).
7. Runs complete with defects left open (866e972e: 2 left open, hidden 0.5).
8. Documented/parked: stage notes shipped in product; release evidence
   uncommitted; phantom Sprint Record attempt; failed workspace not marked
   non-deliverable.

### Subagent's highest-leverage observations
1. Block/quarantine release when locked tests fail or setup unproven — never
   reclassify-to-ship (A1: ≥2 false acceptances at 1/10).
2. replace_lines: remove or force re-read before line edits (A2 numbers).
3. Duplicate-call waste (17–47%) + 20k reasoning cut-offs = two biggest speed
   levers; both concentrate in defect_fix + acceptance_author.
4. Re-measure suite at fixer-dispatch time to kill stale-queue class (A6).

Raw artifacts: /tmp/worker_warns.txt, /tmp/big_runs_analysis.txt; scripts
/tmp/analyze_run.py, /tmp/analyze3.py, /tmp/toolerr.py, /tmp/cache_check.py.

## 6. Next steps (review queue)

- [ ] Read: acceptance/suite.py locking+gaps, acceptance/requests.py,
      graph/engineering.py (defect fix dispatch), agents/specialists.py prompts,
      plugins/seed.py, observability/transcript_metrics.py + metrics.py,
      evaluation/*, server/api.py (UI surface), analysis/project_memory.py.
- [ ] Check sandbox category classification for `pip install` (who sets category=install).
- [ ] Check what compile-and-repair after drafting validates (does it import-check py files? run app?).
- [ ] Collect 4 subagent reports when they land; merge into findings.
- [ ] UI/UX: await d0e933d9 report; spot-check RunDashboard/Wizard myself if budget allows.
- [ ] Write final plan section and APPEND to docs/improvement-plan.md
      (structure: Part 1 systemic environment/wiring gaps; Part 2 local-model
      quality; Part 3 throughput; Part 4 UI/UX; each item: reasoning, evidence,
      mechanism, impact, effort; keep technology-agnostic rule; no run ids in
      code — run ids OK in docs as evidence).

## 6. Notes on process constraints

- AGENTS.md: fixes must be technology/framework/product-agnostic; stack-specific
  → seed.py or pack. Plan must respect that (F1-F4 fixes are contract/pack-level =
  agnostic mechanism, pack-specific data).
- Do not touch docs/logs.md. Do not edit src/. Read-only on live run.
- Times: containers/transcripts UTC; owner reports JST (UTC+9).

## 7. UI/UX audit report (subagent d0e933d9 — COMPLETE)

READ-ONLY audit: all 28 files under langchain-ui/src read line-by-line; production
serving verified (Dockerfile:6-16, src/app/server/api.py:300-327, docker-compose
${APP_PORT:-8000}:8000); live UI exercised at http://localhost:8000 (operator
account, screenshots only). Artifacts: 9 screenshots /tmp/pw-audit/shots/ +
axe scan axe-run-dashboard.json. Live run dashboard: 0 aria-live regions,
0 role=status/alert/log, 218 buttons without aria-label; axe: 197 color-contrast
violations, 1 heading-order, 3 scrollable-region-focusable.

### A. Current state
- React 19 + TS + Vite 8 + Tailwind 4 (@theme tokens index.css:4-23), axios REST
  (api/index.ts:14-38), react-router 7, react-markdown, lucide, ~7.7k LOC/28 files.
  tsc -b gates Docker build (Dockerfile:14-16); FastAPI serves /assets + SPA
  catch-all (api.py:300-327).
- Realtime: WebSocket w/ single-use ticket over REST (api/index.ts:229-232,
  server/progress.py:105-132), last_event_id resume; JWT never in URL. Backend
  caps 5,000 events/run, clips 2,000 chars (agent_stream.py:31-42); REST rate
  limit 300/min (rate_limit.py:29).
- Pages: /login, / intake form (Home.tsx), /runs (RunList + OutcomesPanel),
  /runs/:runId (RunDashboard: action bar Start/Pause/Resume/Rewind/Clone/
  Handover/Cancel; summary card w/ spend + unpriced caveat :598-617; full-width
  Review/Approval when waiting :658-663; SprintSummaryPanel :666; DeliveryPanel
  (criteria from harness evidence, decision log, screenshots); two-mode
  workspace classic (ExecutionFlow + tabs + AgentActivity :678-716) vs wizard
  (WizardDashboard)); /settings (912 lines: model profiles, context window +
  Detect, derived budgets, thinking, parallel toggle, write-only credentials).
- KEEP (already good): plain-English copy layer lib/activity.ts (:129-149,
  242-300); WS resilience (ticket auth, backoff ≤30s, resume from last_sequence,
  coalescing + 700ms debounce after documented 429 incident RunDashboard:114-122,
  177-194, 259-266); log dedupe by event_id (:87-112); feed ergonomics
  (pin-to-bottom, "N new updates", sticky stage headers, "Thinking…" heartbeat
  AgentActivity:325-360, 444-455, 477-484, 492-502); reduced-motion token reveal
  (useStreamedText:37-40); server-as-truth wizard model; empty states everywhere;
  security details (blob download via authed client, write-only credentials).

### B. Findings (C/H/M/L)
B1 Accessibility:
- C No live regions anywhere (0 grep hits; feed/logs/status/gates invisible to SR).
- C Contrast fails at scale: 197 axe violations; --color-text-muted #64748b on
  #020617/#1e293b ≈3.4:1 used for 10-12px labels (RunDashboard:577-600,
  AgentActivity:272, ExecutionFlow:123); text-primary #6366f1 small text fails.
- H ArtifactViewer modal not a dialog: no role/aria-modal/focus trap/Esc/restore/
  scroll lock/overscroll-contain (:54-124); close btn unlabeled (:77-82).
- H Unassociated labels: Login:70-98; ApprovalGate:78-88; ReviewPanel:68-93;
  Settings:419-441, 639-647, 744-799, CredentialField:175-195 (some ARE wired
  :480-488 — inconsistency).
- H Keyboard-inaccessible dropzone (div onClick, hidden input Home:184-204;
  ReviewPanel:87-102).
- H Invisible focus on custom checkbox (sr-only Home:134-161); ZERO focus-visible
  classes app-wide; 21× focus:outline-none with only 5 replacements.
- H Hover-only controls: RunList row actions sm:opacity-0 group-hover (:166-200)
  no group-focus-within, no aria-labels; AgentActivity chevron (:280-284).
  (ArtifactList:83 has focus-within — fix exists in-repo.)
- M Missing aria-expanded (SprintSummaryPanel:196-237, DeliveryPanel:108-122,
  159-170, WizardDashboard:446-474); no aria-current/pressed (Layout:39-50,
  WizardDashboard:181-214); radiogroup no arrow keys (Home:329-352).
- M Scrollable regions not focusable (axe×3: Markdown:96-117, AgentActivity:287-291,
  LogViewer:62-92). No skip link (Layout:67-83); heading order; title-only tooltips.
- L Infinite gradient loop + animate-pulse/spin ignore prefers-reduced-motion
  (index.css:100-127); default credentials printed on login (Login:118-120).

B2 Data-fetching & realtime:
- H Transient poll failure blanks whole dashboard (if (error || !run) → error card
  only, RunDashboard:406-417) — needs stale-while-error.
- H Sequential waterfall per refresh: getRun→getWizard→review→approval→getLogs
  (:117-175); 5 RTTs where 2 suffice.
- H No background-tab throttling: WS hot + RunList 5s poll (RunList:30-34) +
  SprintSummaryPanel 30s (:145); 0 visibilitychange hits; multiplies load vs
  300/min budget (documented 429 incident :183-186).
- M Unbounded log growth: logsById Map re-sorts/reallocs all per merge (:92-112);
  setLogs re-renders whole tree per WS msg; 0 React.memo; buildItems reprocesses
  everything (AgentActivity:308).
- M Navigation races (no AbortController/mounted guard; isSubscribed only guards WS).
- M Session: 401 → full reload to /login (api/index.ts:27-38); Settings claims
  "refresh enabled" (:890) but none exists; "Verifying session…" bare text (App:77-79).
- M SprintSummaryPanel 404-probes docs/sprint_{1..10}_summary.md forever (:127-146)
  + client-side regex markdown parsing (:54-116) vs own server-as-truth rule.
- L 30s axios timeout on handover-zip blob; silently swallowed errors
  (DeliveryPanel:95-96, Settings:73-84, OutcomesPanel:16); downloadError replaces
  loaded content (ArtifactViewer:101-106).

B3 IA & flows:
- H No mid-run steering/intervention; only Pause/Cancel/Rewind (:483-544).
  Harness HAS dynamic instruction injection (owner feature) — backend hook likely exists.
- H Gates arrive silently & context-free: no notification/title badge/favicon
  (0 hits); ReviewPanel shows raw artifact_id + Download only (:33-56) — cannot
  READ artifact in app; workflow = download→edit→re-upload (:116-118);
  ApprovalGate ≤32-line pre (:69-74); auto-approval countdown never shown
  (approval_timeout_minutes exists Home:398-414, types:312-313).
- H Intake = one dense form (Home:163-461): upload+supervision+delivery+models+
  approvals+6 gates; no steps/progress/per-step validation/draft persistence;
  no pre-start summary of a 7-20h decision (live OutcomesPanel: fast ≈7.6h
  typical); hardcoded reviewer "Product Manager" (:84).
- M URL doesn't reflect state (centreTab :63, wizard selection :98, DeliveryPanel
  open :91, viewMode localStorage :70-85) — no deep links.
- M Wizard stops following live run (setSelectedId(prev => prev ?? current) :105-109).
- M Native confirm()/alert() ×17 for destructive+async (RunList:37-69,
  RunDashboard:288-389); delete has no undo.
- M No parallel-agent view: 6 specialists interleaved in one scroll grouped by
  stage only (AgentActivity:156-168); events carry stage identity — lanes
  feasible without backend changes.
- M No run filtering/search/pagination (RunList:80-83 fetches all; 5s re-sort).
- L Dead code: lib/wizardData.ts (694 lines unreferenced), DynamicWorkflowUI.tsx,
  App.css; title "langchain-ui" vs "DevFlow.ai" branding.
- L No keyboard shortcuts/command palette; no cross-run comparison view.

B4 Visual system:
- M Dark-only, no color-scheme declaration/meta theme-color → native selects/
  scrollbars/autofill render light-on-dark; selects set no option colors.
- M No shared primitives: buttons re-implemented per file (actionButton string
  :451-452, gradient-btn index.css:114, ad-hoc gate buttons); radius/padding drift;
  ErrorBoundary raw inline styles (App:22-29).
- M Off-palette hexes: #080c16 LogViewer:65, #172033 AgentActivity:450, #1e2330
  ArtifactViewer:56, #0a0f1a ApprovalGate:71 + DeliveryPanel:60.
- M Emoji mixed with lucide (Settings:616, 628, 717, 739); transition-all ×30.
- L 10-11.5px load-bearing metadata; render-blocking Google Fonts @import
  (index.css:2) no preconnect — offline deployments hang.

B5 Performance:
- H No virtualization: LogViewer maps every log (:67-91); AgentActivity every
  item (:441-475) — up to 5,000 events → thousands of DOM rows (218 unlabeled
  buttons on a FINISHED small run); every WS msg re-renders all.
  content-visibility:auto or windowing.
- M Single eager bundle: 0 React.lazy/Suspense; markdown+axios+lucide loaded on login.
- M Whole-array rework per event (mergeLogs sort+realloc :110; buildItems/
  groupByStage per change :308-309); token-reveal 60fps setProgress (useStreamedText:98-104).
- L backdrop-filter blur on sticky header + every glass card (index.css:129-141,
  Layout:27); heavy blur orbs login (:42-43).
- L Elapsed clock doesn't tick (:438-446) — liveness cue misinforms.

B6 Error/edge states:
- H Whole-page replacement on fetch error (:406-417); unstyled ErrorBoundary,
  reload-only, dumps error.toString() (App:19-35).
- M Silent stream death: WS reconnects but NO visible "connection lost/
  reconnecting" indicator.
- M Error copy without next steps (alert("Failed to submit review: …") :288;
  error card only "Back to Runs" :412-414; Clone hint only for Interrupted :646-651).
- M No toast system; Settings feedback = one span for success AND error styled
  text-primary, inconsistent 3s/4s timers (:852, 266, 296, 331).
- L No offline detection; no unsaved-changes guard on Settings; i18n inline;
  currency hardcoded $…toFixed(2) (:611).

B7 Vercel WIG scan: ~40 terse file:line violations captured in subagent report
(title/theme-color/color-scheme; font @import; reduced-motion; ErrorBoundary;
aria-current; login labels/autocomplete/role=alert/printed credentials; dropzone;
checkbox focus; radiogroup; hover-only actions; confirm/alert; virtualization;
modal semantics; disclosures; scrollable focusable; Settings labels/status/
aria-pressed/unsaved guard; "..."→"…"; Intl.NumberFormat; dead code; vite proxy
:8001 vs :8000).

### C. Research-backed opportunities (all URLs verified by subagent)
- C1 Mid-run steering/side chat (L): Devin Side Chats + takeover
  (docs.devin.ai/work-with-devin/devin-session-tools); Claude Code web "actively
  steer" (claude.com/resources/articles/claude-code-on-the-web). Harness dynamic
  instruction injection = exact backend hook. Composer at waiting/escalation
  points, injected at next stage boundary.
- C2 Timeline scrubbing/checkpoint time-travel (M): Devin time navigation;
  LangGraph time-travel docs (docs.langchain.com/oss/python/langchain/frontend/
  time-travel). Rewind exists as bare <select>+confirm (:509-529) → visual
  timeline w/ checkpoint ticks, scrub feed/artifacts, then rewind.
- C3 Parallel-agent lanes (M): Cursor multi-agent (cursor.com/help/ai-features/
  multi-agent, background-agents); Lovable subagents (docs.lovable.dev/features/
  subagents). Events carry stage → per-agent columns + filter + "N agents working".
- C4 In-gate artifact reading + diffs + versions (M): OpenHands Changes tab
  (docs.openhands.dev/openhands/usage/key-features); Lovable history
  (docs.lovable.dev/features/projects/history); Windsurf cascade diffs. Artifacts
  track revision (types:15-21) — render in gate, diff revisions, version list.
- C5 Proof-of-work delivery (S-M): Devin video recordings
  (docs.devin.ai/work-with-devin/testing-and-recordings); Cursor attaches videos/
  screenshots/logs. DeliveryPanel already shows criteria+screenshots (:182-192)
  but 128px uncickable thumbs (:79) → lightbox, per-sprint evidence, test excerpts.
- C6 Notifications & mobile monitoring (S): Claude Code iOS; Cursor Slack/GitHub/
  Linear; Devin Slack (docs.devin.ai/integrations/slack). Gate self-approves
  after timeout and UI never tells anyone (0 Notification/title/favicon code).
  Minimum: tab-title "(⏸ needs review)" + favicon badge + browser Notification
  on waiting/failed/completed; optional Slack/Telegram webhook.
- C7 Cost/budget cockpit (S-M): Devin ACU caps+usage dashboard
  (docs.devin.ai/admin/billing/usage); LangSmith rollups. Cost model already
  honest (fully_priced, unpriced_requests, waiting_for_budget types:40-69) —
  add spend-vs-ceiling bar, per-stage breakdown, parked-at-budget recovery flow.
- C8 Intake expectation-setting (S-M): Lovable Design Guidance
  (docs.lovable.dev/features/design-guidance); NN/g response times
  (nngroup.com/articles/response-times-3-important-limits). Forecast line
  ("typically 7.6h over 5 runs" Home:353-359) is a gem → step wizard + final
  review screen + ETA/milestone progress + expected-vs-elapsed per stage.
- C9 Trust/transparency (S-M): Microsoft Guidelines for Human-AI Interaction G1/
  G2/G11/G15 (microsoft.com/en-us/research/publication/guidelines-for-human-ai-
  interaction); Google PAIR Guidebook (pair.withgoogle.com/guidebook); Devin
  Session Insights; NN/g big-ball-of-mud-ai + 3-agent-context-roles. Decision log
  + plain-English already implement G11 → extend: why-at-gates, retry/escalation
  counts as trust signals (data exists), post-run Insights panel (OutcomesPanel = seed).
- C10 Keyboard-first (M): Devin CLI shortcuts (docs.devin.ai/cli/reference/
  keyboard-shortcuts); ⌘K palette (jump to run/phase/artifact, toggle view,
  pause/resume w/ typed confirm); gate shortcuts A/R.
- C11 Streaming-build polish (S): bolt.new/v0/Lovable live preview. True token
  streaming rejected for event volume (useStreamedText:3-18 — sound); extend
  illusion: per-stage typing indicator in wizard rail, document.title w/ stage,
  reveal artifacts on write_artifact events (type already distinguished
  activity.ts:245-247).
- C12 UX writing for waiting/failure (S): PAIR Errors; NN/g progress. activity.ts
  nails steady state; failure paths don't → toasts w/ retry, "Last activity 12s
  ago", "Reconnecting…" chip, error cards w/ Retry/Clone/next steps.

### D. Roadmap (subagent proposal; keep for final plan)
Phase 1 quick wins (days): 1) live-region pass; 2) contrast tokens (197 axe
violations gone); 3) labels/aria-label/expanded/current + keyboard dropzone +
focus-visible app-wide; 4) toast+dialog primitive replacing alert/confirm, undo
for delete; 5) stale-while-error + Reconnecting chip + ticking clock; 6) tab
hygiene (visibilitychange pause, title/favicon badge, Notifications on gates);
7) render artifact inline in gates + auto-approve countdown; 8) shell fixes
(color-scheme, title DevFlow.ai, theme-color, preconnect, content-visibility:auto,
delete dead files, vite proxy port).
Phase 2 structural (1-3 wks): 9) design-system primitives (Button/Card/Badge/
Tabs/Modal w/ focus trap/Disclosure/Toast) + token cleanup; 10) virtualized
transcript + memoized children + capped buffer + parallel fetchState +
AbortController; 11) URL state /runs/:id?view=wizard&section=sprint-2&tab=log +
wizard follows live unless overridden; 12) artifact versioning & diff viewer +
screenshot lightbox; 13) cost/budget cockpit; 14) intake redesign (3-step wizard,
draft persistence, per-step validation, start summary + ETA); 15) command palette
+ gate shortcuts.
Phase 3 differentiators (1-2 mo): 16) steering composer via dynamic instruction
injection (+ side-chat Q&A never blocking); 17) checkpoint timeline scrubbing;
18) parallel-agent lanes; 19) post-run Insights + cross-run comparison;
20) mobile monitoring PWA (installable, notifications, one-tap gate actions);
21) i18n extraction + light theme via tokens.
Sequencing: P1 removes harm at ~zero risk; P2 pays structural debt P3 would
amplify; P3 targets the 3 things frontier competitors have that this lacks
(steering, scrubbable time-travel, parallel-agent legibility) while doubling
down on real advantages (harness-measured evidence, honest cost accounting,
plain-English narration).

## 8. Full local-LLM research report (subagent d2176eb1 — COMPLETE, supersedes §4)

Sources verified by direct fetch 2026-10-17/18 (web_search was unavailable; built
from primary docs/papers/leaderboards).

### 8.1 Constrained/guided decoding for tool calling and JSON
- vLLM: structured outputs via xgrammar or guidance/llguidance
  (--structured-outputs-config.backend, default auto); guided_* fields removed in
  v0.12.0 → structured_outputs object: json/regex/grammar/choice/structural_tag
  (schema enforced inside tags of free text). "Guaranteed validly-parsable — not
  high-quality"; ALSO specify schema in the prompt; first use of a named tool
  costs seconds of FSM compile (cached after). --tool-strict-level
  strict|allowed|open: strict constrains tool NAMES + ARGUMENTS via structural
  tags. https://docs.vllm.ai/en/latest/features/structured_outputs/ ,
  https://docs.vllm.ai/en/latest/features/tool_calling/
- Thinking vs grammar: Qwen3 Coder on vLLM DISABLES structured outputs while
  reasoning by default; need --structured-outputs-config.enable_in_reasoning=True
  (v0.11.2+). xgrammar uses the reasoning parser's end_token_id and SKIPS
  enforcement during reasoning. Reasoning-parsers doc = authoritative
  compatibility matrix: parsers per family (qwen3, glm45/glm47,
  minimax_m2_append_think, deepseek_r1, deepseek_v3, openai for gpt-oss);
  DeepSeek R1 tool calling ✗; native thinking_token_budget sampling param +
  --reasoning-config (reasoning_start/end) = built-in mitigation for "reasoning
  eats max_tokens"; server-wide --default-chat-template-kwargs
  '{"enable_thinking": false}'. https://docs.vllm.ai/en/latest/features/reasoning_outputs/
- llama.cpp/llama-server: GBNF grammars (root rule, token matching can permit
  <think>); response_format json_schema → GBNF automatically. Documented limits:
  additionalProperties defaults FALSE, unsupported features SILENTLY SKIPPED,
  properties + anyOf/oneOf unsupported, nested $refs broken, min/max int-only,
  patterns only as ^...$, schema NOT injected into prompt (model can't see it —
  describe structure in prompt too). grammar_eval_n/grammar_max_tokens,
  LLAMA_MAX_PARALLEL_GRAMMARS. https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md
  Stronger: build with -DLLAMA_LLGUIDANCE=ON (follows JSON Schema closely,
  additionalProperties default true, ERRORS instead of silently ignoring,
  ~50µs mean mask compute). https://github.com/ggml-org/llama.cpp/blob/master/docs/llguidance.md
- llama-server tool calls require --jinja; native handlers: Llama 3.1/3.2/3.3,
  Hermes 2/3, Qwen 2.5(-Coder), GPT-OSS (Harmony), Command-R7B, Firefunction-v2;
  DeepSeek R1 "WIP/reluctant"; generic fallback "may consume more tokens".
  Parallel tool calls DISABLED by default (send parallel_tool_calls: true).
  Extreme KV quantization (-ctk q4_0) "can significantly degrade tool call
  performance". https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md
  Per-request: reasoning_format, reasoning_effort (none disables),
  reasoning_budget, chat_template_kwargs {"enable_thinking": false}.
  https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- Best practice for :8888: native tool parser + structural enforcement
  (vLLM --tool-strict-level allowed|strict; llama-server --jinja + json_schema),
  restate schema in prompt, keep code/file bodies in PLAIN-TEXT fields not
  nested JSON strings (aider: 10–15% quality loss from JSON-wrapping code even
  when schema-valid https://aider.chat/2024-08-14/code-in-json.html),
  validate+retry client-side anyway
  (https://docs.langchain.com/oss/python/langchain/structured-output).

### 8.2 Per-model tool-call format quirks
- Qwen3: enable_thinking = hard switch in chat template via chat_template_kwargs
  (differs Transformers/vLLM/SGLang). Qwen vLLM page: --reasoning-parser qwen3
  (v0.9.0+; v0.8.5 bug), custom non-thinking template, --enable-auto-tool-choice
  --tool-call-parser hermes. https://qwen.readthedocs.io/en/latest/deployment/vllm.html
  Function-calling guide recommends HERMES-STYLE template; stop-word (ReAct)
  templates unreliable for reasoning models (stop word inside thoughts);
  "corner cases where tool calls may be malformed… be prepared".
  https://qwen.readthedocs.io/en/latest/framework/function_call.html
  vLLM parser for Qwen3-Coder now qwen3_xml (renamed from qwen3_coder), parallel
  supported; hermes/hermes3 for Qwen2.5/Qwen3.
- Qwen3-Coder-30B-A3B-Instruct: 30.5B/3.3B-active, 128 experts/8; NON-THINKING
  only; 262,144 native ctx (1M YaRN); temp 0.7/top_p 0.8/top_k 20/rep 1.05;
  recommended max output 65,536; "if OOM reduce context to 32,768".
  https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct
- Qwen3-30B-A3B-Instruct-2507: non-thinking, 256K native; Aider-Polyglot 35.6,
  BFCL-v3 65.1 (vs GPT-4o 66.5!), TAU2-Retail 57.0 (τ² telecom 12.3 vs 29.8 —
  drops harder multi-turn); presence_penalty 0–2 for "endless repetition";
  16,384 output; RULER decay avg 86.8: ~97@32K → 82.5@256K → 72.8@1M. Don't
  enable YaRN if average ctx ≤32K ("may hurt short text").
- gpt-oss-20b: harmony format ONLY ("will not work correctly otherwise").
  Harmony: role hierarchy + channels analysis/commentary(final tool calls)/final;
  "Reasoning: high" literal line in system prompt. 21B/3.6B-active, 131,072 ctx
  YaRN, MXFP4; AIME'24 >20K CoT tokens/question avg; STRIP prior-turn reasoning
  in multi-turn. vLLM: --reasoning-parser gpt_oss --tool-call-parser openai; no
  parallel tool calls. https://huggingface.co/openai/gpt-oss-20b ,
  https://arxiv.org/html/2508.10925v1 , https://github.com/openai/harmony
- DeepSeek-R1 + distills: vLLM matrix tool calling ✗; llama.cpp "reluctant".
  Distill guidance: temp 0.5–0.7 (0.6) "prevent endless repetition and
  incoherent output"; AVOID system prompts (all instructions in user prompt);
  32,768 max gen; sometimes skip thinking → prefill "<think>\n". R1-Distill-
  Qwen-14B LiveCodeBench 53.1. Practical: run R1-distills as BASH-STYLE TEXT
  agents, not function-callers.
  https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-14B/raw/main/README.md
- Llama 3.x: vLLM llama3_json parser; "may generate parameters in a malformed
  format"; no parallel; pythonic parser "smaller Llama models frequently fail".
- GLM-4.6: 200K, tool use during inference (interleaved), temp 1.0/top_p .95/
  top_k 40; parsers glm45/glm47. MiniMax-M2 (230B/10B-active): MUST pass
  assistant history back WITH <think> blocks intact (removing "negatively
  affects"); SWE-bench Verified 69.4 (R2E-Gym/OpenHands, 128K, 100 steps),
  Terminal-Bench 46.3, LiveCodeBench 83.0. Cross-model SWE-bench Verified:
  GLM-4.6 68.0, Kimi-K2 69.2, DeepSeek-V3.2-Exp 67.8, Sonnet 4 72.7, Sonnet 4.5
  77.2, GPT-5 74.9.
- Harness-breaker summary: (1) reasoning consumes max_tokens → empty content
  (fix: thinking_token_budget / --reasoning-budget / disable; watch
  finish_reason=length); (2) malformed/hallucinated args despite "parseable"
  guarantees; (3) parallel tool calls unsupported (many parsers; llama.cpp
  default-off); (4) format mismatches (harmony-only; strip-vs-keep reasoning:
  gpt-oss STRIP, MiniMax KEEP); (5) thinking+structured-output conflict
  (enable_in_reasoning).

### 8.3 Prompting/orchestration techniques for small models
- Scaffolding compensates for size: SWE-agent ACI → 12.5% SWE-bench pass@1
  (arXiv:2405.15793); Agentless 3-stage pipeline beat agent frameworks at
  ~$0.70/task (arXiv:2407.01489); mini-swe-agent ~100 lines, BASH-ONLY tool,
  strictly linear append-only history, >74% SWE-bench Verified w/ frontier,
  "runnable with literally any model" (github.com/SWE-agent/mini-swe-agent);
  AlphaCodium flow engineering 19%→44% pass@5 (arXiv:2401.08500).
- Generator–verifier / planner–executor: aider Architect/Editor 85.0% vs 79.7%
  baseline; EVERY pairing improved over solo (o1-mini 61.1→71.4 w/ DeepSeek
  editor; gpt-4o-mini 55.6→60.2); aider recommends --editor-model/architect
  "with models that have trouble following edit format instructions".
  Cognition: Claude Code used Haiku as edit-apply engine; Devin/SWE-1.5 built on
  RL'd small models for narrow well-specified subtasks
  (cognition.com/blog/dont-build-multi-agents).
- code-in-JSON degrades quality (Sonnet −13% even with zero syntax errors under
  schema enforcement — the constraint itself distracts). "Errors are tools" =
  12-Factor factor 7 (+ own your context window 3, tools are structured outputs
  4, own control flow 5, small focused agents 1, stateless reducer 6, compact
  errors 10). Anthropic Building Effective Agents: simplest composable pattern
  (chaining, ROUTING, orchestrator-workers, EVALUATOR-OPTIMIZER); ACI/tool design
  matters more than overall prompt (absolute paths fixed small-model tool-call
  failures). Self-consistency +17.9% GSM8K (arXiv:2203.11171); Reflexion 91%
  HumanEval (arXiv:2303.11366).
- τ-bench: tool-calling beats ReAct for gpt-4o (airline pass^1 0.420 TC vs
  0.325 ReAct); steep consistency decay pass^1→pass^4 0.460→0.225. BFCL V3
  state-based multi-turn taxonomy = canonical description of small-model tool-loop
  failure: missing implicit actions, poor environment-state tracking, loops
  terminated at max steps, over-cautious clarification
  (gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html). AgentBench: large
  commercial vs ≤70B OSS gap in long-term reasoning/decision-making/instruction-
  following (arXiv:2308.03688).
- Orchestration philosophy: one coherent context thread, compress rather than
  parallel-divergent (Cognition); Manus lessons: STABLE PROMPT PREFIXES for
  KV-cache, append-only context, MASK-DON'T-REMOVE tools, file system as
  externalized memory, RECITATION (rewrite plan each step into recent
  attention), keep wrong turns visible, avoid inference-time few-shot
  (manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus).
  Cline local-model guide: compact prompts, focused tasks, fresh task when
  context too large. plandex: plan-then-execute, diff sandbox, tree-sitter repo
  maps, multi-layer edit validation. Terminal-Bench (ICLR 2026)/Harbor: harness
  choice changes scores for the same model → route on YOUR benchmark.

### 8.4 Serving performance for agentic workloads
- Prefix caching: vLLM APC hashes KV blocks (parent-hash + tokens + cache_salt);
  multi-round conversation = primary beneficiary; accelerates PREFILL only
  (docs.vllm.ai/en/latest/features/automatic_prefix_caching/). llama-server
  --cache-prompt DEFAULT ON (timings.cache_n reports reuse), --cache-reuse N
  (KV shifting), --slot-prompt-similarity, --cache-ram 8GiB default, slot cache
  save/restore, --context-shift disabled by default. Any prefix change
  (timestamp, dynamic tool list, reordered history) invalidates — Manus: KV-cache
  hit rate "the most important metric" for production agents (input:output
  ~100:1; cached tokens ~10× cheaper). OpenHands local guide: vLLM
  --enable-prefix-caching + Arctic suffix speculation ~2× speedups.
- Batching/MoE/speculation: vLLM V1 chunked prefill default; tune
  --max-num-batched-tokens (>8192 throughput), --max-num-seqs;
  --enable-expert-parallel for MoE multi-GPU; --cpu-offload-gb/--swap-space.
  Speculative decoding LOSSLESS: n-gram, suffix, EAGLE3, MTP, draft models;
  gains largest at low-medium QPS. llama.cpp: -np parallel slots, continuous
  batching, --kv-unified-per-slot, -fa, -ctk/-ctv (q4_0 KV degrades tool calls),
  experimental --tools agent loop.
- Context rot: Chroma (18 models incl. Qwen3-32B): degradation NON-UNIFORM with
  input length even on trivial tasks; needle position + similar distractors
  matter; NIAH overstates (research.trychroma.com/context-rot, arXiv:2507.13436).
  Lost-in-the-Middle: U-shaped — critical instructions at BEGINNING or END
  (arXiv:2307.03172). OpenHands: Ollama 4096 default "far too small"; ≥22K,
  32,768 w/ max_input_tokens=30000 headroom. aider: Qwen2.5-Coder-32B 72.2%
  BF16 → 51.9% @2K window (silent truncation; edit compliance 46.2%); q4_K_M/
  q2_K cost 5–10 points (aider.chat/2024-11-21/quantization.html).
  WORKING RECOMMENDATION: cap effective per-turn context ~32–64K even on
  128–256K models; ≥4–8K output headroom; no YaRN unless truly >32K; ≥Q4_K_M/Q5
  weights, f16/q8_0 KV.

### 8.5 Small-model failure modes in multi-agent harnesses
- Loops/repetition: BFCL V3 (max-step loops, state tracking). presence_penalty
  0–2 (Qwen3), temp 0.5–0.7 (R1-distills), --reasoning-budget, harness stuck
  detection + step caps.
- Hallucinated tools/args: parseable ≠ correct; --tool-strict-level
  strict|allowed; generic llama.cpp handler misfires; validate args in harness,
  return error as tool result (12-factor).
- Whitespace-exact edit failures: aider edit-errors guide (malformed blocks,
  weak-model warnings, truncation; /undo, --editor-model, architect mode);
  plandex multi-layer validation + diff sandbox; SWE-agent ACI (line-numbered
  views, constrained edit commands). Mitigation stack: prefer whole-file or
  line-anchored edits for weak editors, apply-and-verify, architect/editor split.
- Multi-turn attention drift: "LLMs Get Lost in Multi-Turn Conversation"
  (arXiv:2505.06120): avg 39% performance drop multi-turn; early assumptions,
  premature final answers, "when they take a wrong turn, they get lost and do
  not recover". Mitigations: consolidate/re-anchor (re-state full task in fresh
  turns), condense history (OpenHands Context Condenser), fresh tasks per unit
  (Cline), Manus recitation + file-system memory.
- Thinking-budget exhaustion: gpt-oss >20K CoT; R1 skipping thinking.
  thinking_token_budget/--reasoning-budget; thinking off on execution turns;
  raise max_tokens (Qwen3-Coder 65,536); detect finish_reason=length → retry
  think-off/larger budget.
- History-format poisoning: strip prior reasoning for gpt-oss; KEEP <think> for
  MiniMax-M2; inconsistent handling silently collapses quality.
- Model-level regression: OpenHands "when it behaves like a chatbot only… the
  problem may be the model itself" — verify tool calling works before blaming
  harness; use community-confirmed models.

### 8.6 Model routing (strong planner/reviewer + fast local executor)
- FrugalGPT (arXiv:2305.05176): cascades match best single model with up to 98%
  cost reduction or +4% accuracy at equal cost.
- RouteLLM (arXiv:2406.18665, LMSYS): preference-trained routers >2× cost cut
  without quality loss; transfer when models change.
- aider architect/editor (above): reasoning model plans, cheaper model edits —
  85.0% vs 79.7%; split also REPAIRS format compliance for weak editors.
- Cognition: route DECISIONS to strong models, MECHANICAL STEPS to fast ones.
- Anthropic: routing is first-class workflow pattern.
- Production: OpenHands SDK MultimodalRouter (rule-based) + route_task_to_model
  (LLM classifier, mid-conversation switch, history preserved)
  (docs.openhands.dev/sdk/guides/llm-routing, /llm-task-routing); mini-swe-agent
  model-agnostic via litellm. Benchmark caveat: same model + different harness =
  different score (Harbor/Terminal-Bench).

### 8.7 Top-12 recommendations ([S]=server, [H]=harness)
1. [S] Match server tool/reasoning parsers to the model + turn on enforcement
   (vLLM --enable-auto-tool-choice --tool-call-parser {qwen3_xml|hermes|glm45|
   minimax_m2_append_think|openai} --reasoning-parser {...} --tool-strict-level
   allowed (+enable_in_reasoning=True if thinking on); llama.cpp --jinja,
   reasoning_format auto, json_schema). Removes largest failure class for zero
   prompt changes.
2. [H] Per-model thinking policy with budget guardrails: thinking off on
   execution/tool-heavy nodes; thinking_token_budget/--reasoning-budget; size
   max_tokens per vendor guidance; auto-retry on finish_reason=length with
   thinking disabled.
3. [H] Validate-and-retry with EXACT error feedback, capped 1–2, then escalate
   to stronger model (cascade). LangGraph conditional edges.
4. [H] Architect/Editor split: strongest model writes spec/plan/review; local
   MoE emits file edits; simple edit formats for executor. aider 85.0 vs 79.7;
   Cognition edit-apply precedent. Maps 1:1 onto PM/architect/lead vs specialist
   roles — specialist edits = the only thing the local model must get right.
5. [H] Keep code OUT of JSON strings; restate schemas in prompts (GBNF not shown
   to model; prompt-schema alignment improves quality).
6. [S+H] Cache-first context design: byte-stable system prompt + static tool
   definitions FIRST, append-only history, no timestamps/dynamic ordering in the
   cached prefix; verify via vLLM metrics or timings.cache_n; cache_salt for
   isolation. Payoff 2–10× cheaper/faster TTFT → funds retries/verification.
7. [H] Hard context budget ~32–64K effective + condense/recite: summarize older
   turns (OpenHands Condenser), rewrite current plan into recent context each
   step (Manus recitation), externalize to files, must-follow constraints at the
   END (lost-in-the-middle; context rot incl. Qwen3; 39% multi-turn decay +
   re-anchoring). Verify server real ctx (≥22–32K).
8. [S] Serving quality gates: ≥Q4_K_M/Q5 weights (BF16 72.2→q2_K 61.7), flash
   attention on, KV f16/q8_0 only, no YaRN under ~32K, vendor sampling presets
   (Qwen .7/.8/20/1.05; GLM/MiniMax 1.0/.95/40), aider-polyglot-style smoke
   benchmark after ANY server change.
9. [H] One task per turn, deterministic control flow in graph edges not model
   discretion; single coherent context per work item; compressed summaries
   between roles, not parallel divergent contexts; compact focused role prompts.
10. [S] Throughput for parallel agents: vLLM chunked prefill (default),
    --max-num-batched-tokens ≥8192, --enable-expert-parallel (MoE), n-gram/
    suffix/EAGLE/MTP speculation (lossless, biggest win at low QPS); llama.cpp
    -np slots sized to KV memory, --cache-ram, cross-slot prompt-cache reuse.
    OpenHands: ~2× from suffix speculation on Qwen3-Coder. Faster loops = more
    verification budget per task.
11. [H] Bash-first fallback executor for tool-call-unreliable models (R1
    distills): mini-swe-agent-style one-bash-tool loop, YAML/plain-text
    commands, linear append-only history, R1 sampling rules (temp 0.6, no system
    prompt, "<think>\n" prefill). Unlocks a whole model class.
12. [H] Router/cascade layer across the role graph: cheap-local-first with
    verifier-gated escalation (FrugalGPT/RouteLLM); OpenHands-style classifier
    per task type; planning/review on strongest accessible model, execution on
    local MoE. Measure per-node pass rates on YOUR benchmark.

Per-model cheat sheet: Qwen3-Coder-30B-A3B → vLLM qwen3_xml parser, no
thinking, .7/.8/20/1.05, max_tokens 65536, ctx ≤32–64K working set.
Qwen3-30B-A3B-2507 → same + presence_penalty ≤2 if looping. gpt-oss-20b →
harmony only; gpt_oss/openai parsers; strip prior reasoning; "Reasoning: low/
medium" per node. DeepSeek-R1-distill → bash-text loop, temp 0.6, no system
prompt, 32K cap. GLM-4.6 → glm45, 1.0/.95/40, keep think blocks. MiniMax-M2 →
minimax_m2_append_think, 1.0/.95/40, never strip <think>.

Mapping to our evidence: rec 1+5 ↔ A9/A3 (structured-output degradation,
hallucinated names); rec 2 ↔ A4/B3 (reasoning exhaustion — llama-server
--reasoning-budget and vLLM thinking_token_budget are the SERVER-side versions
of Initiative I); rec 4 ↔ C8 (local model drafts fine, fixes/reviews weak —
route fixes/reviews to judgement model); rec 6+7 ↔ B2/B4/F15 (prefill-bound,
60–120k prompts, 45–73% cache hits; effective-context cap 32–64K vs current
~100% of 126k window as input ceiling); rec 10 ↔ F10 (parallel vs 1-slot
server; owner's model is MTP GGUF = speculation-ready); Manus mask-don't-remove
↔ our tool-withholding changes the tool list mid-stage (cache invalidation +
confusion — consider instruction-level withholding); rec 12 ↔ existing two-tier
roles (extend: escalation for reverted fixes).

## 9. Release-integrity mechanics (my own verification, post-forensics)

Read: graph/delivery.py release() (168-250), graph/escalation.py (all 323),
acceptance/suite.py (grep), acceptance/requests.py (header+smoke).

- release(): re-runs the locked suite; `not result.ran` → treated as failing
  ("the suite did not run"); also runs the project's own unit tests
  (`_unit_tests_failing`) — a past run released with `npm test` failing.
  Failing → last sprint goes again, MAX_RELEASE_ATTEMPTS=2 → then
  _escalate_to_a_human → escalation node.
- escalation() auto mode: no criteria → FAIL ("nothing can be shipped with
  confidence"). deferred+failing > half the criteria → FAIL. Otherwise
  _defer_and_continue: suite.defer() the failing criteria ("could not be made
  to pass after fixes and re-planning") and go on → release. MAX_ESCALATIONS=3
  then stop.
- So by design a run CAN release with up to (just under) half its criteria
  deferred — "ships what works". The false acceptances came through:
  (a) dispute path: repairs spent → QA lead reclassifies failing locked tests
  as test bugs → suite repaired/rewritten → green (94d2c449 → hidden 1/10);
  (b) vacuous green: runner executed 0 tests, exit 0 (3642baf8 — caught by the
  SETUP PROOF but "left to the agents"); suite.tests_the_runner_never_ran()
  exists (suite.py:766) for written-but-unran tests.
- Smoke tests are pack-scaffold proofs (setup), NOT per-criterion release
  probes. Nothing at release independently probes the delivered product
  surface derived from the locked CRITERION TEXT — the suite (mutable via
  repairs) is the only truth at release.
- Plan recommendation anchors: (1) vacuous-green hard gate at release
  (executed-test count ≥ locked count, per-criterion coverage); (2) dispute
  reclassification cap + judgement-model second opinion + executable evidence
  per reclassified test; (3) release-time per-criterion independent probe
  (from locked criterion examples) against the REAL delivered entrypoint —
  catches both the stub-entrypoint wiring gap (F1) and suite-weakening
  repairs; (4) honest completion states: `completed_with_gaps` when anything
  deferred/reclassified/demoted (DB + UI + bench-visible), so loop audits can
  track false-accept risk without hidden tests.

## 10. Progress checkpoint (02:50 JST 2026-10-18)

- Draft appendix written: docs/review-appendix-draft.md (Initiatives J–U,
  4 parts + sequencing table; correction of the Phase-1 record re 94d2c449
  false acceptance included). Merge frontier research when 8408a576 lands,
  then append final to docs/improvement-plan.md and delete the draft + this file.
- Verified: src/app NEVER reads cache metrics (grep cache_n/cache_read/
  cached_tokens = 0 hits) — but forensics measured 45–73% cache hits from
  transcript usage records, so the data is ALREADY in transcripts; KPI work
  is scripts/loop-side surfacing only ( Initiative S/O refinement).
- Live run-bf43c7e2 at 02:50 JST: still defect_fix_2_2 treadmill; new
  evidence for L.5 hard stop — "has been refused 3 redundant reads;
  withholding the read tool for the rest of it" firing ×4 in 4 minutes:
  withholding generates refusal turns instead of ending the stage. Reasoning
  exhaustion also recurring in same stage (17:45). Run ~3h old, no sprint
  progress since suite lock; owner's ~2.5h cancel rule (≈03:24 JST) is an
  operational decision for the owner/loop operator — noted, not acted on
  (review-only mandate).

## 11. Frontier harness research (subagent 8408a576 — COMPLETE)

Full report persisted on disk: .langchain/research/frontier-harness-report.md
(+ raw notes .langchain/research/notes.md). Method: direct fetches of official
docs/blogs/repos/arXiv (web_search unavailable); community-sourced claims
labeled. Products: Claude Code+SDK, Codex CLI/Cloud, Gemini CLI, Jules,
OpenHands SDK, SWE-agent/mini-swe-agent, Aider, Cline, Roo, Devin, Amp,
Cursor, Factory, Copilot agent, Deep Agents/Open SWE, MetaGPT/ChatDev/
Magentic-One, vLLM/llama.cpp, SWE-bench/Terminal-Bench/METR.

Key points by theme (URLs in the saved report):
- T1 Context: Claude Code startup budget (~4.2k sys prompt, memory index 25KB,
  tool NAMES only, skill one-liners); compaction ~95% w/ structured summary +
  DISK RE-INJECTION (CLAUDE.md, plan, 5 recent files as paths, skill bodies);
  Anthropic compact-2026-01-12 API (trigger ≥150k default, min 50k); Codex
  per-model 180k/244k, summary "for another LLM that resumes the task",
  effective 95%; Gemini 70% compress; OpenHands condenser replaces first half
  of events; tool-output management separate (clear old outputs FIRST, >10k
  chars → file+preview; ClearToolUsesEdit keep-3); subagents = context
  isolation (Codex cites context-rot); dissent: Amp compaction-free (Handoff/
  Fork), Cline /newtask + /deep-planning fresh task, Cognition single thread +
  fine-tuned compressor. ADOPTION: compact EARLIER (~50–60% of usable window
  for small models), summary written for the resuming LLM, re-inject from
  disk, cheap summarizer model, offload big outputs to files.
- T2 Loop: plan-first (Claude plan mode, Jules plan approval, Cline Plan/Act,
  Open SWE); LIVING TODO re-injected every ~6 msgs (Cline Focus Chain);
  orchestration: single-threaded lead + READ-ONLY subagents, parallel writers
  only w/ worktrees (Cognition+Codex+Claude converge); role pipelines w/
  FILE ARTIFACTS as interface (MetaGPT SOP) beat chatty roles (ChatDev);
  Magentic-One task/progress LEDGERS AS FILES + re-plan on error;
  verification in-loop: runnable checks, Claude /goal separate evaluator
  every turn, Stop hooks block turn-end until check passes; Devin "easy to
  verify"; Copilot CI iteration; RubricMiddleware. Escalation: Gemini loop
  detection, Jules auto-retry→fail+notify, Claude "corrected twice → /clear".
- T3 Tools: mini-swe-agent BASH-ONLY, no tool-calling API, linear history,
  >74% SWE-bench Verified w/ frontier, "any model"; SWE-agent ACI guardrails:
  LINT-GATED EDITS (invalid rejected at tool level), 100-line windowed reads,
  terse search (only files w/ ≥1 match), EXPLICIT empty-output message;
  Aider edit-format compliance: whole-file ~100% at 32B vs ~73% diff;
  read-before-edit + unique old_string (Claude Edit); repo maps (tree-sitter,
  ~1k tokens, dynamic) over blind reads; Codex sandbox matrix + auto_review
  classifier agent (fail-closed, open policy.md); Claude Auto mode separate
  classifier model. ADOPTION: bash-first FALLBACK execution mode for
  tool-call-unreliable models; whole-file default for weak editors; ACI
  micro-guardrails; small classifier call for dangerous actions (20-40B can
  classify itself cheaply).
- T4 Robustness: grammar-enforce CONTROL-PLANE decisions (plan JSON, todo,
  verdicts, finish) but NOT free-form coding turns; vLLM "guaranteed
  parsable — not high-quality" + describe schema in prompt;
  enable_in_reasoning caveat for Qwen3-Coder; --tool-strict-level
  function|parameter; ToolErrorMiddleware pattern (exception → sanitized
  error ToolMessage); OpenHands LLM_NUM_RETRIES=4 + LLM_DROP_PARAMS;
  prefix-stable prompts + vLLM --enable-prefix-caching / llama.cpp slot
  cache; ROUTING: Cursor Router (complexity predictor, 75% uplift bar,
  cache-miss cost; above-Fable satisfaction at −68% cost), Codex per-subagent
  model+effort, Amp Dial + role-pinned models + small system models for
  compaction, Gemini pro→flash fallback, OpenHands Index guidance
  (strongest for long/high-stakes, cheaper routine, stronger planning/
  debugging/review); Cursor Composer = harness-RL-trained own model;
  mini-roulette (random model switching per instance) BEAT either model alone.
- T5 Quality: auto-lint/auto-test after EVERY edit w/ error feedback (Aider);
  TDD-lite (/test-add failing tests first); adversarial reviewer subagent in
  FRESH context w/ NARROW correctness-gap rubric (reviewers over-report —
  restrict!); Writer/Reviewer split; /goal evaluator; Open SWE learns repo
  review preferences from historical feedback; METR: RELIABILITY not raw
  reasoning drives long-task completion (arXiv:2503.14499) — spend harness
  complexity on gates, not fancier prompts.
- T6 Local realities: OpenHands 2026 first local recommendation =
  Qwen3.6-35B-A3B CLASS (owner's model!): ≥24GB VRAM quantized, ctx ≥22k
  REQUIRED (4096 = broken), 32,768 + flash attention recommended, vLLM
  --enable-prefix-caching, speculation ≤2× (ArcticInference); documented
  failure "chatbot-only, refuses tools". Qwen3-Coder-30B-A3B: 60.4% SWE-bench
  Verified @ ~19GB Q4 (best-in-24GB); Qwen3.6-35B-A3B: Terminal-Bench 24.6%
  = 24GB champion; bash-only board: Qwen2.5-Coder-32B collapses to 9.0%
  (scaffolding matters!); DeepSWE-Preview-32.8B 58.8% (harness-trained small
  models closing gap). llama.cpp: -ctk q4_0 KV substantially degrades tool
  calling; native handler list; gpt-oss harmony-required.

Top-15 adoptable (ranked, full URLs in saved report): 1 grammar-enforced tool
calls/control-plane; 2 bash-first minimal toolset + text-parsed fallback;
3 ACI guardrails; 4 whole-file/validated search-replace + error-feedback
retry; 5 early structured compaction + disk re-injection; 6 tool-output
offload/clearing; 7 post-edit deterministic gates (lint→type→test, finish
blocked until green); 8 re-injected living todo list; 9 read-only subagents +
single writer per workstream; 10 role-pinned routing (cache-miss-aware);
11 plan-file-first workflow; 12 repo-map structural context (~1k dynamic);
13 evaluator/rubric loop for "done"; 14 AGENTS.md convention + prefix-stable
prompts + prefix caching; 15 container sandbox + allowlisted escalation,
fail-closed review.

Harness-status mapping (mine): already have ≈ 7,9(partly: parallel writers
exist but with work-order file separation),11(work orders/sprint record),
13(locked suite+dispute),14(AGENTS.md n/a internally; digest append-at-end),
15(argv-only sandbox stricter than bash). GAPS feeding the plan: #2 bash-first
fallback mode (M), #3 ACI micro-guardrails incl. explicit empty-output notice
(P), #4 whole-file default for weak editors w/ compliance data (P — the 100%
vs 73% number is the citation for replace_lines demotion), #5 earlier
compaction + disk re-injection (O — harness compaction trigger is 0.8×window;
research says 50–60% of USABLE for small models), #6 tool-output offload (O),
#8 todo cadence re-injection (R — verify task-list middleware cadence),
#10 role-pinned routing w/ effort tiers (Q), #12 repo map (already Tier 2 in
docs/harness-improvement-plan.md — reinforce), narrow correctness-gap reviewer
rubric (Q/E2 milestone-review findings).
Bottom line quote: frontier consensus is MORE valuable on 20–40B local MoE —
"every mechanism substitutes harness engineering for model capability".

## 12. Final status (2026-10-18, ~03:05 JST)

COMPLETE. All four subagent reports merged; final appendix (Initiatives J–U,
Parts 1–5 + sequencing table + Phase-1 record correction) appended to
docs/improvement-plan.md on 2026-10-18. Working draft docs/review-appendix-
draft.md deleted after merge. This file remains as the evidence archive the
appendix cites (§5 forensics, §7 UI/UX audit, §8 local-LLM research, §11
frontier-research digest; full frontier report also at
.langchain/research/frontier-harness-report.md).

Live run at time of writing: run-bf43c7e2 still in defect_fix_2_2 treadmill
(reasoning-exhaustion events 17:45 UTC, refusal-loop "withholding the read
tool" ×4 in 4 min, ~3h elapsed, no sprint progress since suite lock 01:26
JST). Operational decision (cancel per the ~2.5h rule vs let the escalation
ladder finish) belongs to the owner/loop operator — this review was
read-only and touched nothing.

Post-script (same day): owner asked whether the plan covers all gaps named in
the opinion review. Coverage-check addendum appended to docs/improvement-plan.md:
mapping table (8 gaps → initiatives) + three fills that were previously only
indirect: Initiative V (layer-economics audit / delete-or-keep ledger +
workflow.py seam refactor track), J.5 (records must cite the independent
verdict, never suite-green alone), L.6 (final attempt changes strategy shape,
not just model).

---

## 13. Second review session — progress log (started 2026-10-18 11:30 JST)

Owner mandate (same as session 1, now a *further* pass): review only, no code
changes; append to `docs/improvement-plan.md`; evidence + reasoning per item;
language/framework-agnostic; local-model quality; throughput without quality
loss; UI/UX "as much as possible"; use fresh web research; log progress often.
Economy rule from the owner: cheap models (Sonnet/Haiku) for mapping and
summarisation, Fable for the review and the plan itself.

### 13.0 Checkpoint 1 (11:35 JST) — orientation
- Repo cloned fresh from `harness-hardening-session` @ `3fcd36d` (the branch
  name is lowercase on the remote; the Project instruction's capitalised
  spelling does not resolve).
- Read `docs/improvement-plan.md` end to end (Initiatives A–I, appendix J–V,
  two addenda, Implementation Progress Ledger). The ledger says the P0 wave
  is DONE (J.1/J.4/J.5/K.1/L.3/L.5/L.6/Q.4/J.2/J.6/K.3/K.4/K.5/L.1/L.4/L.7/
  N.2/P.1); NOT STARTED: J.3, K.6, M, N.1, Q.2, Q.3, O.1–O.4, R, T, U.1/U.3/
  U.4, V, K.2, every UI phase. The second review therefore must (a) look for
  evidence of what the DONE items changed in later runs, (b) find *new*
  gaps rather than restate J–V, (c) deepen the local-model and UI/UX work.
- No transcripts or `data/` in the clone (git-ignored) and this session has no
  bridge to the owner's Docker volumes → run forensics in this pass come from
  the docs' run records (`monitoring-handover` §0.2, ledger notes naming
  run-8b0c94df) unless the owner attaches transcripts.
- `docs/logs.md` is an external reviewer's report (owner's file, never
  edited): its six items are run-readiness gate, mutation-tested suite
  strength, capability tiers for stack support, honest cost cap, retention
  contract, reviewer-completeness visibility. Cross-checked below against
  the plan; the ones not already covered become candidates.
- Web research task launched 11:23 JST (frontier harnesses, local-model
  serving, agent UI/UX; 2025–2026 primary sources). Report integrates in
  §13.x when it lands.

### 13.1 Checkpoint 2 (11:50 JST) — spot checks while mappers run
- Four Sonnet mappers in flight (agents/models layer; graph/acceptance/tools;
  UI+API; run history/packs/loop KPIs). Their inventories land in the session
  scratchpad and are folded into this file as §13.2–13.5.
- Spot checks (grep, no model): pre-ledger Initiatives A–I are only partly
  traceable in code — G (lenient `edit_artifact` matching) and C
  (`ui_contract` in the specification) have **no** code trace; F (root
  load-error gate) and I/N (thinking budget plumbing) do. A-I were never put
  in the ledger; candidate: add them so their status is honest.
- Cross-run learning exists only as a human-driven proposer
  (`scripts/loop/lessons.py` → a person writes a seed rule). No structured,
  injection-safe lesson store (old plan Tier 1 #2 still open). Frontier
  parallel: Claude Code auto-memory, OpenHands microagents, Cursor memories.
- The control plane still relies on free-text JSON parsed from message
  content (`settled_answer._repair_json`: a 59× one-character truncation
  loop was measured). Constrained decoding for control-plane schemas
  (Initiative M) remains NOT STARTED — the single highest-leverage
  local-model item; this pass will make it concrete and evidence-ranked.
- `docs/logs.md` external review: items 1 (run-readiness gate before model
  calls), 2 (mutation-tested suite strength), 3 (capability tiers), 4 (cost
  cap honesty), 5 (retention/deletion contract), 6 (reviewer completeness)
  → 2, 3, 4, 6 are NOT covered by the current plan; 1 partly (loop.sh ready
  covers the model, not command execution); 5 partly (U.4 retention, but
  not deletion of transcripts/object-store copies).

### 13.2 Checkpoint 3 (12:10 JST) — agents/models map + UI map landed; Fable-verified findings

Mapper inventories: `map-agents.md` (agents/, models/, context budget, repair
layers, kill switches) and `map-ui.md` (React UI + API surface). Findings
below are the ones verified by reading the code directly (G-numbered to keep
them apart from session 1's F-series).

#### G1 (HIGH, local-model): prompts order a tool the role is not given — and contradict themselves
- `agents/product_manager.py:352-360` says "Do not write a document … only
  through that response" and then "**Write the complete intake in ONE single
  write_artifact call.**"; the role is built with `can_write=False`
  (`product_manager.py:391`), so `write_artifact` is not in its tool list
  (`role_agent.py:665`). Same pair in `agents/tools_models.py:322-333` /
  `:363`. The specialist prompt also says "ONE single write_artifact call, no
  follow-up edits" (`specialists.py:1317`) while `_WRITING_RULES` teaches
  `edit_artifact`, and ui_ux is told "do not run tests" (`specialists.py:84`)
  and "prove your work by running it" (`:1287`).
- Why it matters: this is the exact mechanism behind A3 (hallucinated tool
  names, `edit_file` ×53) — the prompt *names* a tool the schema lacks, and a
  small model follows the prompt. Session 1 catalogued the symptom in M; the
  prompt-side cause was not found. Deterministic fix class: a test that every
  tool name a prompt mentions is in that role's offered set (same shape as the
  banned-words tests).

#### G2 (HIGH, throughput): project memory sits at the head of the conversation and is rewritten from disk every call
- `agents/project_memory.py:312-321` splices the memory text into the
  *opening* human message; the middleware re-reads it each call; budget up to
  30% of the window (`MEMORY_SHARE`). Any write changes the first message →
  the server-side prefix cache misses for the entire history on the next
  call. This is the single largest prefix-cache leak the harness controls and
  it is *in front of* the task text (lost-in-the-middle for the brief itself).
  Session 1 measured 45–73% cache hits and average requests growing
  44k→95k after memory deployment (B2) but attributed it to size only.
- The environment contract and workspace digest are appended *after* the
  growing history (`environment_contract.py:253`, `workspace_digest.py:526`),
  so the stable block is re-prefilled every turn while the volatile block
  (memory) sits in the cached region. Both are the inverse of O.3's rule.
  Candidate: memory + contract as a byte-stable second system block
  *before* history; digest ("already known", volatile) last — and measure
  `cached_tokens` per call (nothing reads it: `map-agents.md` §2).

#### G3 (MEDIUM, local-model): no sampling or cache parameters are ever sent
- Stages send no `temperature`/`top_p`/`seed`/`cache_prompt`/`json_schema`
  (`models/__init__.py`); the only `temperature=0` is the framework-extraction
  call (`plugins/middleware.py:166`). Behaviour therefore depends entirely on
  how the owner launched the server. Model cards (Qwen3: 0.7/0.8/20, presence
  penalty for loops; GLM 1.0/0.95/40) and M's profile contract are the place
  for these; today `server/model_profiles.py` is only a saved-settings store
  (235 lines, no per-family behaviour) and `models/fitness.py` has no caller
  under `src/`.

#### G4 (MEDIUM): tool list changes mid-conversation
- Settled-answer withholding and the research-share cap remove tools
  mid-stage; the prefix changes (cache miss) and the schema the model
  learned from no longer matches (weak models keep calling the removed
  tool). Manus "mask, don't remove"; Initiative O noted it — now with code
  pointers (`map-agents.md` §6 item 4).

#### G5 (MEDIUM): maintenance prose inside system prompts
- `technical_lead.py:674-777` and the environment contract carry "Measured
  across the stored runs…" statistics and ALL-CAPS/CRITICAL emphasis. Prompt
  sizes 1.7k–14k chars per role. For 20–40B models the research consistently
  favours short, imperative, example-led rules; the rationale belongs in the
  module docstring (where this codebase already keeps it beautifully), not
  in the tokens the model pays for every call.

#### G6 (LOW–MED): parallel-mode hazard — process-wide globals
- `settled_answer.py:573,584` `_LAST_FAILING_FIELDS` / `_LAST_FAILURE_KIND`
  are module globals read across stages; in parallel mode two specialists
  can read each other's failure state. Needs a per-thread/per-stage carrier.

#### G7 (UI/plan correction): no steering endpoint exists
- Session 1's Phase 3 "steering composer via the existing
  dynamic-instruction-injection hook" rests on a misreading:
  `plugins/middleware.py` injects *framework* guidance per stack; there is
  no user→run instruction path and the WebSocket is read-only (`map-ui.md`
  §3). Steering needs a new backend enabler (queue + middleware that
  appends the operator note as a trailing message at the next stage
  boundary), and that is the right place for it architecturally.

#### G8 (UI/plan correction): artifact versioning has no real data
- `server/runs.py:1704-1713` hard-codes `revision=1` and the in-flight stage
  on every artifact. The planned diff/version viewer needs the workspace git
  history (every stage commits) exposed per path first.

#### G9 (UI): intake has no free-text brief, and a failed start orphans a run
- Intake accepts documents only; `createRun` then `startRun` — a failure in
  the second leaves a `created` run with no owner action. Access token
  expires at 60 min with no refresh → a full reload mid-run.

#### G10 (UI, measured by mapper): still-open harms from Part 4 Phase 1
- None of Phase 1 landed (no `aria-live`/`role=status`, 17 native
  `alert()/confirm()`, modal without dialog role, 31 hex literals + 115 raw
  slate/white classes, RunList polls 5 s even when hidden, no WS→poll
  fallback, whole-log copy+sort per WS frame, `waiting_for_budget` missing
  from `statusConfig`, "Documents N produced" counts code files). Landed
  since: completion_gaps/non_deliverable banners, partial-pricing honesty,
  rewind UI, outcomes+forecast, approval-timeout input.

#### G11 (API/UI mismatches, mapper)
- `document_names` (list) vs UI `document_name`; `approval_timeout_minutes`
  stored but absent from `RunStatusResponse`; token counts, `reviews[]`,
  `remediation` typed but never rendered; `delivery_mode`,
  `use_frontier_model`, `auto_approve` absent from the UI type; dashboard does
  not refetch on `budget_pause`/`approval_denied`/`review_decision`; after a
  `closed` frame the stream is never re-attached; brownfield
  (`StartRunRequest.source`, `POST /runs/{id}/codebase`) unreachable from UI.

### 13.3 Checkpoint 4 (12:25 JST) — run history / packs / loop map landed (`map-runs-packs.md`)

#### G12 (EVIDENCE CORRECTION, HIGH): the local-model "quality cliff" (C8 → Initiative Q) is confounded
- The brief_low runs scored 1/10, 1/10, 5/10 (94d2c449, 3642baf8, 866e972e)
  against `benchmarks/web-todo/hidden`, whose tests require the `## Interface`
  labels present only in `benchmarks/web-todo/brief.md`, not in
  `tests/brief_low.md`. The one run given the real bench brief (77c6650e,
  local model, fast) scored 10/10. So `false_acceptance` (`completed and
  score<1.0`) on those three mixes a *brief/suite mismatch* with harness
  faults, and improvement-plan lines 429/741 ("fast/local web-todo scored
  0.1/0.1/0.5 while frontier-judged scored 1.0") over-read it. 94d2c449
  remains a true false acceptance (reclassify-to-ship). Consequence: Q's
  routing items stay justified by the *revert* evidence (both live reverts
  were local-model fixes) but not by the hidden-score gap; the bench harness
  needs a rule that a run is only scored against a hidden suite whose brief
  it was given (or the score is tagged `brief_mismatch`).

#### G13 (EVIDENCE GAP, HIGH): no scored run exists after the P0 wave
- run-8b0c94df is the only run documented after the 2026-10-18 fixes; its
  brief, mode, model, duration and outcome are recorded nowhere (mentioned
  only at IP:1340/1344/1350, RF:1218). K.3-extension and L.1 refinement were
  written *because of* it, so it did not benefit from them. The medium brief
  has 0 completions in 9 attempts; `tests/brief_high.md` has never run; the
  stage-2 bench gate (notes-api, wordstats-cli, textkit-lib) has no recorded
  result. Session-2 plan items must therefore be framed as hypotheses with
  the measurement that confirms them, and the first action of the loop is a
  scored post-P0 run on the real bench briefs.

#### G14 (A/B BLOCKER, MEDIUM): the toggles do not reach the container
- `docker-compose.yml` `x-app-env` does not pass `LINE_EDITS`,
  `ENVIRONMENT_CONTRACT`, `WORKSPACE_DIGEST`, `PROJECT_MEMORY`,
  `HARNESS_TASK_LIST`, `JUDGEMENT_*`, `ESCALATE_AFTER_ATTEMPTS`,
  `MODEL_MAX_OUTPUT_TOKENS`. Every "A/B-verified" clause in the plan is
  unexecutable without editing compose. Related config drift:
  `SANDBOX_MEMORY_LIMIT` 4g (code) / 1g (compose) / 2g (.env.example);
  `MODEL_CONTEXT_WINDOW` default 100000 vs server started at 126,464;
  `HARNESS_MAX_PARALLEL=6` default against a 1-slot server.

#### G15 (LEDGER ACCURACY): U.2 claims not borne out
- "duplicate-call rate already in audit_live.py" — audit_live counts
  replayed call_ids; the identical-call measure lives only in
  `scripts/audit_run.py`, which `loop.sh` never calls. Not counted anywhere:
  reasoning-exhaustion discarded tokens (and the owner's llama server reports
  no reasoning tokens, so the share is unmeasurable from usage), stale-fixer
  dispatches, reverts/run, reclassifications, vacuous-green detections,
  prefill:decode ratio. No cross-run KPI ledger exists; all script output is
  text. `evaluation/evaluate.py` is a LangSmith heuristic evaluator for
  intake/architecture, unrelated to bench scores.

#### G16 (LANGUAGE-AGNOSTIC CLAIM): where the packs stop
- 35 packs / 5 kinds. Only the two fullstack-*-fastapi packs declare
  `entrypoints` (K.3's stub check covers nobody else, incl. fullstack-next/
  django, python-http/flask). Ten service packs have empty `check_families`
  (go×2, java-spring, aspnet, rust-axum, ruby×2, php×2, node-nest).
  Dependency-drift covers JS/TS + Python only; the compiler check is a
  silent no-op when a toolchain is absent; no pack for Kotlin/Swift/Dart/
  Elixir/Scala/C++; every service pack's acceptance needs Node+Playwright;
  bench corpus is JS+Python only; no `services` field in the contract.
  → The external review's "capability tiers" (logs.md §3) is the honest
  framing until K.6 lands: *pack-supported / custom / unverified*, surfaced
  at intake.

#### G17 (DOCS DRIFT): HANDOVER §2 frozen at 10-12 (model row, suite count,
"27 packs" vs 35); improvement-plan §4 still says bf43c7e2 is running (it
failed 06:49 JST in `defect_fix_2_19`, `ValueError` from the venv symlink
outside the workspace root — itself a K.5 regression candidate); line 15
calls gpt-oss-20b "frontier".

#### G18 (THROUGHPUT, parked items that matter most)
- Parallel mode ≈1.0–1.3× on 1 slot (auto-approve loop redesign parked);
  reads ≈70% of calls; task list built, off, never measured; thinking budget
  is the biggest single time lever and is an owner decision — the plan
  should give the owner a measured recommendation, not a setting change.

#### G10 amendment (12:40 JST): concurrent UI Phase 1 commit
- `3435fb0` (another session, 11:32 JST) landed contrast tokens, live
  regions on feed + log, skip link, aria-current, focus-visible, reduced
  motion, keyboard dropzone, named Settings controls, page title/colour
  scheme, and `scripts/ui/axe_measure.mjs` (455 axe violations → 5 on four
  pages). Still open from G10 after that commit: toast/dialog primitives (17
  native alert/confirm), modal dialog role/focus trap, title/favicon badges,
  browser Notifications, inline artifact rendering, auto-approve countdown,
  stale-while-error dashboard, WS→poll fallback, hidden-tab polling pause,
  log virtualization/buffer cap, `waiting_for_budget` status styling,
  dead-code deletion. The plan's Part 4 Phase 1 row should be split
  accordingly in the ledger.

### 13.4 Checkpoint 5 (12:55 JST) — graph/acceptance/tools map landed (`map-graph.md`); Fable-verified

#### G19 (HIGH, release integrity + treadmill): a fix is "fixed" on the fixer's say-so
- `graph/workflow.py:8895-8960` `_settle_the_fix`: with no blockers and a
  named test, the defect is marked fixed; `verified_by` (what the execution
  ledger confirms ran and passed) is only an info log ("does not gate the
  transition"). The post-fix check `after_a_fix` (engineering.py:555)
  reverts a fix that *broke other tests*; nothing checks that the defect's
  own tests now pass — that waits for the next test round, which then counts
  it as another failed attempt. Yet `_the_defect_s_tests_pass`
  (workflow.py:2615, per-file acceptance probe, no model) already exists and
  L.3 runs it at *dispatch*. Running it at *settlement* is the symmetric
  missing half: a defect only closes on a green probe; a red probe marks the
  attempt failed immediately (saving a whole round, and making the fixer's
  self-report irrelevant). The rewrite fixers hard-code the regression-test
  string (`rewritten_fixes.py:207,306`) and `fix_by_candidates` keeps a
  candidate when the check could not run (`:296`, `passed is not False`) —
  same class: unknown treated as passed.

#### G20 (MEDIUM): two different "tests that cannot pass" lists
- `acceptance_nodes.py:376-401` (review, 18 checks) vs `:1141-1153` (per
  round, 11): the round list lacks `locators_nobody_sees`,
  `locators_that_pick_one`, `tests_that_assert_an_unstated_order`,
  `locators_that_contradict_their_assertions`, `controls_never_found_by_name`,
  `tests_with_module_system_mismatch`, `tests_with_unawaited_async_helpers`.
  Repaired/reopened tests re-enter through the shorter list, so a test only
  the long list catches can be locked and later charged to the product. One
  list, one function.

#### G21 (MEDIUM, prompt/code disagreement): milestone `blocked` verdict
- `agents/milestone_reviewer.py:99-105` tells the model `blocked` ends the
  run; `workflow.py:9756-9768` re-plans instead, with no visible cap on that
  branch. Same class as G1 (instruct, then do otherwise) — and a weak model
  that believes `blocked` is terminal will avoid saying it.

#### G22 (MEDIUM, local-model): tool description untrue in container mode
- `agent_toolkit.py:585` says everything except install runs with the
  network off; in-container mode applies no network restriction
  (`sandbox.py:4364-4437`) and builds its environment differently (venv
  PATH, `ACCEPTANCE_PORT`). The tool text is part of the prompt the model
  reasons from; it must be rendered from the active mode.

#### G23 (THROUGHPUT): parallelism is mostly nominal
- Per-workspace command lock serialises every command (`sandbox.py:3732`);
  `HARNESS_MAX_PARALLEL=6`; `fix_by_candidates` fires 3× the file count of
  concurrent model calls (`rewritten_fixes.py:278`) — against a 1-slot
  server this is queueing plus KV-cache thrash (session-1 F10 measured
  1.0–1.3×). The honest default is `max_parallel = server slots` (S already
  reads `/props`).

#### G24 (THROUGHPUT, model calls that deterministic data can gate)
- Thorough mode runs a judgement-model testing agent every round although
  the fast "harness round" gathers the same measurements; architecture and
  milestone reviews run even when the harness found no breakage and the
  suite is green; `security_review` runs when nothing risky changed (the
  conditional skip exists per the old plan — verify it is reached);
  `what_the_files_already_prove` (49 whole-workspace checks) is recomputed
  several times per round with no caching.

#### G25 (CORRECTNESS, status model): `completed_with_gaps` is a list on `completed`
- Stored as `completed` + `completion_gaps` + `NON-DELIVERABLE.json`
  (delivery.py:259-293, runner.py:1448-1490). Never reaching the gaps list:
  fast-mode review findings recorded as risks, escalation `known_issues`,
  defects accepted as risk. Release does not re-run compiler, dependency-
  drift or integration checks. (J.4 implementation note acknowledged the
  enum constraint; the three missing sources are new.)

#### G26 (MAINTAINABILITY, refactor evidence for V)
- `build_workflow_graph` is one 3,672-line closure (46 nodes, string-routed
  through `_route_from_stage` on 35 of them); `_review_the_milestone` 463
  lines with its revise-or-escalate branch repeated 5×; `_run_gated_agent`
  440 lines with the failure block duplicated (W:3073-3111 / 3191-3230);
  `_closed_if_an_earlier_fix_resolved_it` repeats its close block 4×; two
  defect clusterers (W:4178, W:4296) share scaffolding; `MAX_*` caps read at
  import time (worker restart to change). `build_repository_read_tools` is
  imported in role_agent.py but absent from the tool list (verify: dead).
  Revert is `git reset --hard` + `git clean -fd` on the whole workspace
  (ci.py:230-239) — consistent with L.2's DROPPED verdict (one fix per
  stage) but worth stating as the invariant that keeps L.2 dropped.

#### G27 (not a bug, mapper over-flag): last-attempt shape change
- Fires at `failed_fix_tries >= escalate_after()` (=2) → attempt 3, which
  with three charged attempts *is* the last rung. No action.

### 13.5 Checkpoint 6 (13:10 JST) — corrections + outline of the session-2 plan addendum

Corrections to earlier checkpoints:
- 13.1 said Initiative G (lenient edit matching) had no code trace: wrong
  file grepped. `tools/repository.py` carries an extensive repair chain
  (line numbers, backslashes, JSON escaping, indentation, blank lines,
  pipe-stripping) and the 2026-09-19 sweep behind it (247 of 371 costly
  failures = "Could not find that text"; 294 of 330 failed edits were on a
  file the stage had already read; replay resolved 7/75). G is in code; the
  ACI problem is deeper than matching — reproducing bytes from context is
  the requirement weak models cannot meet, which is why `replace_lines` was
  built and then demoted (P.1). Edit ACI remains the open core.
- Compaction uses deepagents' `SummarizationMiddleware` with the *run's own
  model* as summariser (`role_agent.py:385-411`), trigger 0.8×ceiling, args
  truncated first (`truncate_args_settings`). The summary prompt is the
  library default (unverified offline). Summarising 55k tokens on a 35B MoE
  is itself a long decode on the prefill-bound server.

Addendum outline (appended to `docs/improvement-plan.md` as "Appendix 2,
session 2"; initiative letters continue after V):
- Part 6 Measurement first: W (scored post-P0 run on real bench briefs;
  brief-mismatch tag; toggles through compose; per-run KPI JSON + cross-run
  ledger; ledger rows for A–I).
- Part 7 Local-model core: X prompt-contract integrity (G1/G5/G21/G22);
  M made concrete (control-plane `response_format`/grammar via the
  OpenAI-compatible server, sampling presets, probe-time capability
  detection — G3); Y edit-ACI replay bench from the transcript failure
  corpus → per-profile edit format; Z compaction that keeps state (strip
  tool results first, structured summary template, re-injection).
- Part 8 Throughput: AA prefix-cache layout (memory/contract as byte-stable
  prefix, digest last, cached_tokens KPI — G2); AB parallelism = server
  slots, fan-out caps (G23); AC deterministic gating of review/testing
  model calls + check caching (G24).
- Part 9 Release integrity residuals: AD measure-at-settlement (G19, the
  mirror of L.3); AE one cannot-pass list (G20), gaps completeness +
  release re-checks (G25); AF suite-strength mutation probe (logs.md #2);
  AG capability tiers at intake (G16, logs #3); AH honest cost cap,
  retention/deletion contract, reviewer completeness (logs #4–#6).
- Part 10 Cross-run learning: AI structured, provenance-tagged lesson store
  (old plan Tier-1 #2; `lessons.py` as the proposer).
- Part 11 UI/UX session 2: corrections (G7 steering enabler, G8 real
  revisions, G9 intake, G11 mismatches), Phase-1 split after `3435fb0`,
  then the design plan proper.
- Part 12 Refactor track evidence (G26) for V.
- Sequencing table + new ledger rows. Frontier/research citations slot in
  per item when the research report lands.

### 13.6 Research report digest (landed 17:45 JST) — frontier harnesses, local serving, agent UX
Full report from the web-research task (primary sources 2025-06→2026-10).
Kept here because the research tool's output is not otherwise persisted.
R-numbers are cited from `docs/improvement-plan.md` Appendix 2.

**Headline**: "one writer, many advisors." Local-model failures are
*interface* failures (tool-call format, edit format, context truncation,
quantization) more than reasoning failures.

- R1 Anthropic "Effective harnesses for long-running agents" (2025-11-26):
  initializer writes `init.sh`, progress file, initial commit, JSON feature
  list with every feature `passes:false`; each session reads progress, runs
  a basic e2e first, implements ONE feature, commits, logs. Adopt as
  backbone.
- R2 Anthropic "Harness design for long-running apps" (≈2026-03-24):
  planner (told NOT to over-specify implementation — errors cascade) /
  generator / evaluator negotiating "sprint contracts"; evaluator drives
  the app via Playwright; context *resets* needed (Sonnet 4.5 "context
  anxiety"); ~6 h/$200 per 16-feature app; evaluator "unnecessary
  overhead" when the task is within the generator's ability → for weaker
  local models the evaluator gives *more* lift.
- R3 Cognition "Multi-agents: what's actually working" (2026-04-22): works
  "when writes stay single-threaded"; clean-context Devin Review catches
  ~2 bugs/PR, 58% severe, even on Devin's own PRs; weak-primary +
  strong-advisor failed ("quality ceiling set by the primary"); Manager
  Devins: over-prescription and assumed shared state are the failure
  modes. "Don't build multi-agents" (2025-06-12): edit-apply lesson — a
  small model rewriting a whole file from a markdown explanation beat a
  large model emitting a diff (R15).
- R4 MAST (arXiv 2503.13657): 14 failure modes; spec/design 41.8%,
  inter-agent misalignment 36.9%, verification 21.3%; ChatDev 33.3% on
  ProgramDev, +9.4% from better prompts/topology; verifiers do low-level
  checks (compiles?) and miss the requirement.
- R5 "Flat score, amplified failures" (arXiv 2607.27275): INT4 looked free
  on τ²-bench scores but out-of-list tool-call names rose 19.5%→38.3%;
  community: Qwen3.6 Q4 breaks tool JSON/diffs, Q5_K_M/Q6 fix most,
  collapse past ~30k ctx (anecdotal). Single-turn HumanEval unaffected by
  Q4. → Q6/Q8/FP8 for the tool-calling implementer; Q4 OK for summarisers.
- R6 Ollama: since commit 0334ffa6 (2026-02-02) default `num_ctx` is
  VRAM-based (4,096 <24 GiB; 32,768 24–48; 262,144 above); docs recommend
  ≥64k for agents; `/v1` ignores `num_ctx` → set `OLLAMA_CONTEXT_LENGTH`.
  "#1 silent failure for local agents."
- R7 Cline v3.35 (2025-10-31): native tool calling only for frontier
  families; tool defs as API params cut tokens ~15%/request; local models
  get XML-in-prompt; issues #10843 (Qwen emits JSON into XML parser →
  loop), #13008 (syntax change broke Ollama+Qwen3.6-35B-A3B), #7424
  (Compact Prompt for local), PR #12835 (explicit xml tool mode). Lesson:
  tolerant multi-format parser; version-stable tool syntax.
- R8 aider: edit formats whole/diff/diff-fenced/udiff/patch/editor-*;
  unknown models default to `whole` ("easiest format"); leaderboard
  reports well-formed-edit % separately; llama3-70b 73.5% well-formed on
  diff (secondary); v0.19 udiff took GPT-4 Turbo 20%→61% on the laziness
  bench; `--architect`/`--editor-model`/`--weak-model`.
- R9 JetBrains "The Complexity Trap" (arXiv 2508.21433, 2025-08-29): LLM
  summarisation +15% trajectory length vs raw, +13% vs observation
  masking; masking halves cost at equal solve rate.
- R10 mini-SWE-agent (~100 lines, bash-only, >74% SWE-bench Verified) as
  control harness; same-harness open-model run 2026-02-17: MiniMax M2.5
  75.8%, GLM-5 72.8%, Kimi K2.5 70.8%, DeepSeek V3.2 70.0% vs Opus 4.5
  76.8%; vendor claims Qwen3.6-27B 77.2%, Qwen3.6-35B-A3B 73.4%, Devstral
  Small 2 68.0% (harness-dependent; OpenAI stopped reporting SWE-bench
  Verified 2026-02).
- R11 OpenHands condenser: up to 2× per-turn cost cut, event-sourced and
  replayable; default max_size=80 keep_first=4; SDK paper arXiv 2511.03690.
- R12/R13 Claude Code: plan mode = write tools not exposed; permission
  mode ladder; ExitPlanMode gate; hooks are enforcement, CLAUDE.md is
  advice; checkpoints miss bash side-effects → use git per step; subagents
  for read-only work.
- R14 vLLM `--enable-auto-tool-choice --tool-call-parser <family>`
  (qwen3_coder/qwen3_xml/llama3_json…); Qwen3.5/3.6 recipe: MTP-1 spec
  decoding for low-concurrency latency (disable prefix caching in that
  mode); llama.cpp `--jinja`, native handlers per family else Generic
  (more tokens), lazy GBNF grammars after tool trigger (PR #9639),
  `--chat-template-file` overrides; JSON Schema→GBNF automatic. Security:
  vLLM GHSA-79j6-g2m3-jgfw (`qwen3_coder` parser `eval()` RCE) — pin.
- R16 Ralph loop (Huntley 2025-07-14): fresh context per iteration, state
  in files/git, mandatory `--max-iterations` + completion promise.
- R17 Anthropic "Effective context engineering" (2025-09-29): attention
  budget, context rot, just-in-time retrieval, compaction + notes +
  subagents; Manus: KV-cache hit rate the key production metric, mask
  don't remove tools; Lost-in-the-middle (TACL 2024), Chroma context rot.
- R18 Cursor 2.0 (2025-10-29) 8 parallel agents; Plan mode 1.7/2.1 with
  clarifying-question UI → adapt only at planning on a single GPU.
- R19 Memory as plain markdown files navigated with file tools; `LESSONS.md`
  reviewer-appends/planner-reads.
- R20 UX: Jules plan approval + browser notifications + Planning Critic
  (−9.5% failures, vendor); Devin Interactive Planning (2025-04-03), Devin
  Review hunk grouping with confidence/severity (2026-01-21); Copilot draft
  PR as work surface, mission-control steering (2025-10-28); Codex
  evidence citations of terminal logs/tests; Lovable/Bolt/v0 live preview +
  versioned rollback mapped to commits.
- R21 Huang et al. arXiv 2512.14012 (2025-12-16): professional devs
  "control the agents through planning and supervision"; "The Work Behind
  Delegation" arXiv 2609.24234: supervisory demand to understand unwritten
  work; Chen et al. arXiv 2507.08149.
- Top-20 ranked recommendations from the report (verbatim order): 1 fix
  context sizing and verify at startup; 2 single writer; 3 feature list
  as source of truth; 4 one feature per fresh context with caps; 5
  clean-context evaluator that executes; 6 per-model tool-call adapter;
  7 grammar/JSON-schema constrained decoding for structured artifacts;
  8 per-model edit format by calibration; 9 architect/editor split; 10
  avoid INT4 for the tool-calling implementer; 11 remove tools instead of
  forbidding; 12 hooks over prompts; 13 stable short system prompt +
  prefix caching; 14 condensation with template + resets at 60–70%; 15
  loop detection → reset → escalate → human; 16 plan critic; 17 git
  per step + no-network container; 18 append-only event log → OTel; 19 UI
  essentials; 20 model selection on your own harness.
- Not verified by the report (do not copy specifics): Goose, Amp,
  Windsurf, Augment, Factory, Replit, Gemini CLI internals,
  CrewAI/LangGraph patterns, AgentCoder, Roo/Kilo internals, BFCL/Tau
  tables, OTel GenAI conventions, Langfuse.

Mapping to Appendix 2: #1→M.1/W.3; #2 already (work orders); #3→Part 11
plan-first (criteria as feature list) + existing locked suite; #4→Z.3;
#5→AD/AF (+ existing acceptance); #6/#7→M.1–M.2; #8/#9→Y; #10→M.6;
#11/#12→X; #13→AA/X.4; #14→Z; #15→existing L.5 + Z.3; #16→existing
L.7/validator (plan critic = judgement-model plan review, Q-amend);
#17→existing; #18→W.4; #19→Part 11; #20→W.

### 13.7 Final status (18:05 JST)
- `docs/improvement-plan.md` Appendix 2 appended: Initiatives W, X, M
  (concrete), Y, Z, AA, AB, AC, AD, AE, AF, AG, AH, AI; UI/UX Part 11 with
  corrections + design plan; Part 12 refactor evidence; sequencing table;
  R-citations; ledger rows (all NOT STARTED, per the review-only mandate).
- This file §13 holds the per-finding evidence (G1–G27) and the research
  digest. No code was changed. No run was started.
- Follow-ups for the next session: W.2 baseline runs (owner), then P0 rows
  in order W → X.1/X.2 → AD → AE, each with its failing-first test.

### 13.8 Implementation paused (18:30 JST)
Owner approved starting the Appendix 2 P0 items, then paused when this
cloud sandbox could not install the project's dependencies (egress proxy
denies `files.pythonhosted.org`; `langchain_core` unavailable, so no target
module imports and `loop.sh suite` cannot run — AGENTS.md's failing-first
test rule cannot be honoured here). No code was changed. Resume from a
session linked to the owner's machine (or one with PyPI access) in this
order, one commit each: X.1/X.2 → AD → AE → W.3 → W.1 → W.4 → W.5. Each
item's exact code pointers are in §13.2–13.4 (G1, G19, G20, G21, G22, G25,
G14, G12, G15) and the mechanism text is in `docs/improvement-plan.md`
Appendix 2 Parts 6, 7 (X) and 9 (AD, AE).

---

## 14. Third review session — progress log (started 2026-10-18 22:10 JST)

Owner mandate: deep review again, improvement points, a *detailed*
implementation plan; revamp the UI to be more user-friendly with multiple
theme options; no code changes; check the live Docker app.

### 14.0 Checkpoint 1 (22:20 JST) — orientation
- Branch moved from `7e4bc9a` to `57e8342` since the pause: another session
  (`langchain-63`, the main driver per HANDOVER §2.0000) implemented most of
  Appendix 2 and the owner's 12 decisions of 20:55 JST — 119 files, +5.5k
  lines. Appendix 2 ledger now: DONE W.1/W.3/W.4/W.5, A–I rows, X.1–X.4,
  M.1 (narrowed), O.1/O.2/O.3-AA, AB, AC, AD, AE, AF (redesigned to
  release time), AG, AH.1–4, AI, K.2, J.3+C, U.1, V; DROPPED on measurement:
  M.2, M.3, Z/O.4, Y (no crossover found), AA.2, AC.3; UI commit `ef982a2`
  (Changes view from git history, criteria→tests, URL state, steering via
  `.harness/steering.json` + instruction middleware).
- So this pass is (1) a review of today's implementations as code (no suite
  can run here), (2) new gaps, (3) the UI revamp + multi-theme plan.
- Live Docker app NOT reachable: the desktop link exposes no shell/file
  tools in this session and the Chrome extension reports "not connected".
  Screens are reviewed from the code; the plan marks where a live
  screenshot pass should confirm.

### 14.1 Checkpoint 2 (22:50 JST) — UI/theme map landed (`map-ui-v2.md`); findings H1–H8
(H-numbers: third session; G-numbers: second.)

#### H1 (THEME FEASIBILITY, decisive): multi-theme is a token-redefinition job, not a rewrite
- 17 colour tokens in `@theme` (`index.css:4-23`), dark values only;
  `color-scheme: dark` hard-set (`index.css:27`, `index.html:8`); no
  `data-theme`, no `prefers-color-scheme`, no theme context. Tailwind 4 does
  not inline `@theme` values → redefining the same variables under
  `[data-theme="…"]` re-themes the ~829 class sites that already use
  semantic tokens with no component edits. Outliers to touch: ~210–230 sites
  in 22 files — `text-white` as heading/body 89 of 106 uses (Settings 25),
  ~72 white/black alpha overlays, 21 raw slate classes, 11 `bg-[#hex]` + 1
  inline `#f4f4f4` (ErrorBoundary), 16 red/indigo/violet; `index.css` holds
  44 hex/rgba literals (glows, glass, status, skip link, focus ring).
  Unlayered overrides `.text-primary{#a5b4fc}` / `.text-danger{#f87171}`
  (64 and 35 uses) are pastel-on-dark values that will fail on light.
- One token each for success/warning/danger serves text *and* fill: on
  white, success ≈2.3:1 and warning ≈2.1:1 → light themes need separate
  `-text` / `-bg` / `-border` variants per status.
- Fonts: Inter via Google Fonts `@import` (`index.css:2`) — render-blocking
  and fails offline, on a product whose whole point is running locally.

#### H2 (PRIMITIVES): one real primitive module
- `components/Feedback.tsx:28` (`FeedbackProvider`/`useFeedback`: toasts +
  confirm dialog with focus trap/Escape/scroll lock/focus restore) is the
  only shared primitive. No Button/Card/Badge/Tabs/Input/Select/Dialog/
  Skeleton/EmptyState; 8 separate status-colour maps; spinner hand-rolled
  7×; `Checkbox` local to `Home.tsx:134`; `CredentialField`/`InfoRow`
  defined *inside* the Settings render (`Settings.tsx:175,197`) → remount
  per render, inputs likely lose focus per keystroke.

#### H3 (NEW FEATURES, `ef982a2`): working, but thin
- ChangesPanel: `?view=changes&change=<sha>`; `GET /runs/{id}/changes`
  (≤200 commits) and `/changes/{sha}` (≤200k chars); token-based diff
  colours. No loading state (empty reads "Nothing has been changed yet"),
  no per-file view although files per commit are sent, no highlighting, raw
  commit subjects as titles.
- Criteria→tests: closed `<details>` per criterion (`DeliveryPanel.tsx:
  134-160`); panel returns null when empty (no loading/empty state).
- SteeringBox: `GET/POST /runs/{id}/steering` → `.harness/steering.json`;
  newest 5 notes ≤2000 chars appended to the *system prompt* end
  (`plugins/middleware.py:531-537`). No `steering` event → the feed never
  acknowledges a note; older notes drop silently; box shown while paused;
  product-specific placeholder. (Verified: `.harness/` is harness-owned,
  excluded from memory/scaffold/delivery.)
- URL state: only `view` and `change`; wizard/classic still localStorage.
- Gate countdown is text only; deadline derived from `updated_at +
  approval_timeout_minutes` (approximation of the real sweep).

#### H4 (API ↔ UI): fields exist server-side, UI ignores them
- `RunStatusResponse` now carries `gate_deadline`, `approval_timeout_minutes`,
  `completion_gaps`, `non_deliverable`, `delivery_mode`, `use_frontier_model`,
  `auto_approve`, `cost`; the UI type lacks the last three → a run page
  never says fast/thorough, local-only or unattended. `cost` shows dollars
  only. Not exposed at all: per-stage tokens/cost, cache share, KPI JSON,
  lessons list/approve (CLI only), `support_tier` (markdown only),
  structured `completion_gaps` detail, mutation results, interface-contract
  check results, defects ledger, work orders, Sprint Record (regex-parsed
  from markdown). Unused: `/health/ready`, `/events?since` (the missing poll
  fallback), `/codebase` + `source` (brownfield unreachable).

#### H5 (PHASE-1 REMAINDER, verified): favicon badge, browser Notifications,
WS→poll fallback, log virtualization/buffer cap (log re-sorted per
message), `waiting_for_budget` styling (missing from `RunDashboard.tsx:468`
and `RunList.tsx:86`; `describeStatus` says "Up next"), "Documents N
produced" (server counts ≤500 workspace files), dead code (`wizardData.ts`
694 lines, `DynamicWorkflowUI.tsx`, `App.css`), token refresh, orphan run on
failed start, `document_names`, refetch triggers, stream re-attach after
`closed`, inline artifact in review, self-hosted fonts, code-splitting, UI
tests. Partly: title badge (run page only), ArtifactViewer Escape/restore
without trap, tabs lack `role="tab"`.

#### H6 (NARRATION DRIFT): 21 graph stages have no `STAGE_COPY` (title-case
fallback); `activity.ts:139` renders `specialist_gather`/`specialist_worker`
as "Building the gather part".

#### H7 (IA): routes `/login`, `/` (intake), `/runs`, `/runs/:id`, `/settings`;
no 404, no global "needs you" indicator, no help, no post-login redirect;
model settings only in `/settings` and Home never checks a model is
configured; no skeletons; OutcomesPanel/DeliveryPanel/SprintSummaryPanel/
first-run Settings render nothing when empty; on the run page gate,
steering, sprint summary and delivery stack full-width above the 3-column
workspace → workspace below the fold at 768 px.

#### H8 (API data unused by the UI that would change behaviour): `/events?since`
exists → WS→poll fallback is a UI-only change; `approval_timeout_minutes`
in payload → the stall/countdown surfaces need no backend.

### 14.2 Checkpoint 3 (23:05 JST) — evidence/KPI map landed (`map-evidence-v2.md`); findings H9–H15 (verified where marked ✓)

#### H9 (GOVERNING GAP, unchanged from G13): ~25 fixes today, zero verified on a run
- run-8b0c94df's outcome is still recorded nowhere (last note: "cancel if
  ≥20 of 30 acceptance tests still fail"); no run has started on the
  post-fix code; HANDOVER §2.2 "Verify on the next run" not updated for
  today's commits. Owner decision 9 (W.2 order: fast notes-api-hono → fast
  fullstack-bookmarks-py → thorough) is the gate for everything below.

#### H10 ✓ (KPI CORRECTNESS): the new KPI script under-counts and mis-ratios
- `scripts/loop/kpi.py:123,134` look for guard markers only in the first
  600 chars of a tool result; the harness *appends* its notes after file
  content, so `redundant_read_rate` misses them and can disagree with
  `identical_call_rate` on the same call. `prefill_decode_ratio` (`:149`)
  divides total input by output — cached input inflates it; the useful
  number is (input − cached)/output. `reasoning_chars` recorded but unused;
  `invalid_tool_calls` recorded but not counted; no per-stage/per-role KPI;
  no phantom-claim rate (Q.4), prompt-size, compaction counter (so O.4's
  "revisit if KPI shows compaction" can never fire), stale dispatches,
  reclassifications, vacuous-green, edit well-formedness. 527/2190 is
  24.06%, not 23.9%.

#### H11 ✓ (LOOP SCRIPT BUGS): `loop.sh kpi` (`loop.sh:222`) redirects to
`data/kpi/<run>.json` *before* the worker command succeeds → a failing
worker leaves an error JSON in place of the run's KPIs (ledger step
skipped). `loop.sh lessons` (`loop.sh:294`) passes only `${2:-3}` → `list`
works, `propose|approve|reject` fail through `loop.sh` (HANDOVER already
notes it). The per-run proposal list for the owner is not automated.

#### H12 (THE 431 READS): the lead the ledger left open
- Read ladder today: memory pointer → note at 3rd read → withhold at 3
  repeats → name the exit at 6 → refuse at 12; read tool removed at 3
  refusals/held-backs or 8 pointers. Two plausible causes, neither
  confirmed: the first repeat gets no notice (`REPEATS_BEFORE_SAYING_SO`=2,
  notes appended *after* content), and memory pointers cover whole files
  ≤60k chars only. With R's recitation now in place, the next audit should
  measure repeated reads per stage *before vs after* R on the W.2 baseline.

#### H13 (LEDGER DRIFT): stale NOT STARTED rows duplicate DONE rows (M L1348;
O.1–O.4 L1358–1361; Z/AA/AB L2022–2024; UI rows L2036–2040); AJ row
"IDENTIFIED" though item 1 landed in `2f68304` (NullPool/`dispose()`
seeding and timeout stdout diagnostics not built — direct pytest runs can
still hang); M.4–M.6 row says out-of-list tool-name KPI NOT STARTED but
`unknown_tool_name_rate` exists; HANDOVER §2 table still 2026-10-12.

#### H14 (DECISION/IMPLEMENTATION MISMATCHES): AF budget decided "per lock",
implemented at release (correctly — the suite locks before the build — but
the decision text should say so); J.3 "gap for 2 runs then blocker" and E
"measure over 2 runs" have no run behind them; `gate_deadline` derived from
`updated_at` may not match the real timeout sweep.

#### H15 (MEASUREMENTS TO CARRY INTO THE PLAN): 37 lost replies ≈40% of the
medium run's output tokens; 5,556 edits / 21.7% refused (guards working);
72% `cache_read` on the medium run; 495 pointer answers / 93 withholdings /
85 held-back reads; ~45 "Context size exceeded" at 20–48k input under a 100k
setting in parallel waves (fixed by O.2); compaction never fired in the
last 10 runs (largest request 73–101k vs 80k trigger); 4/30 acceptance
tests passing when the medium run was last observed.

### 14.3 Checkpoint 4 (23:40 JST) — backend implementation review landed (`review-backend-diff.md`); findings H16–H33
Scope: commits `7e4bc9a..HEAD` in `src/app` and `scripts/`, read not run.
✓ = verified by hand in this session.

**High**
- H16 ✓ **AH.1 `MAX_RUN_TOKENS` / `MAX_RUN_COST_USD` are per worker process.**
  `cost_tracker._RUN_COSTS` is an in-memory dict (`cost_tracker.py:195-215`);
  `runner._budget_exceeded` (`:307`) reads it. Every mid-run deploy
  (`loop.sh deploy` restarts the worker) or orphan recovery resets the
  total to 0, so the bound is per *segment* — which defeats the 12-hour /
  73M-token case it was built for. `cost_from_transcript` exists
  (`cost_tracker.py:350`) but only feeds the display (`runs.py:1864`).
- H17 ✓ **AF mutation probe is not crash-safe.** `mutation.py:175` calls
  `apply()` *outside* the `try`; the `finally` (`:181`) restores only in the
  same process. A worker death mid-probe (deploy, OOM, cancel) leaves the
  mutated source on disk and orphan recovery re-runs release on the broken
  tree. Also: restore writes LF (CRLF files change), and sites can land in
  docstrings/comments → false "unnoticed" gaps. Fix shape: mutate a *copy*
  of the workspace or journal the original under `.harness/` and restore on
  recovery.
- H18 (verify on a run) **AA frozen memory vs `seen_content`.**
  `project_memory.py:383-386` calls `remember(held_path, held_content)` on
  every call with the *visit-start* content, overwriting the digest the edit
  tool set after the stage's own edit (`repository.py:3619`) → a later
  failed `edit_artifact` may be misreported as "a command you ran rewrote
  it". The new "read for the current text" note also contradicts `9d637fe`
  (read tool withheld after 8 pointers) and `8ed63b2` (cat/ls/find refused)
  — a fixer told to re-read with no way to.

**Medium**
- H19 K.2: the environment contract promises a fresh `DATA_DIR` per
  acceptance run; only `_javascript.py:307` provides it (≈20 packs do not);
  AF re-runs non-browser suites on shared data; `seed.py`'s postgres row
  still says "working with PostgreSQL" → two dialects, server path never run.
- H20 X.3: the network-sentence replacement matches a 16-space-indented
  docstring string; Python 3.13 dedents docstrings → no-op there (2 of 3
  tests fail on 3.13; Docker is 3.12; `pyproject` allows ≥3.12).
- H21 R digest: lists any non-failed read as "already in this conversation"
  ignoring offset/limit windows and truncation; misses writes made by
  commands; returncode regex misses string codes.
- H22 `changes.py`/`runs.py`: sync `subprocess.run` inside async handlers
  blocks the API event loop; `TimeoutExpired` uncaught; `git log/show
  --patch` runs on an agent-writable workspace without `--no-textconv`;
  nothing refuses agent writes to `.git/` (only `.harness/` is protected).
- H23 Interface contract (C/J.3): Playwright/npx/.mjs hard-coded in a
  generic module; CLI/library packs skip silently (no "unchecked" note);
  `command` lines advertised to the architect but never executed;
  `globalSetup` dropped; bare POST / parameterised routes give false gaps;
  contract frozen at lock.
- H24 M.1: `max(min(window, slot), MIN_VIABLE_WINDOW=32000)` raises the
  window back above a smaller slot with no warning; `/props` fails *open*
  (vLLM/Ollama/LM Studio 404 → no bound, no log).
- H25 E: split work-order parts keep the whole order's steps/interfaces/
  verification/out_of_scope and run in parallel → verification fails on
  files siblings have not written yet.
- H26 AE.1: widening the round's cannot-pass list widens the suite-reopen
  triggers (`workflow.py:8643-8708`); heuristic false positives can hide
  real failures; the `ea714bc` locked-in-problem filter is untested.
- H27 AD: unit fallback is "no unit test failed anywhere" (unrelated failure
  keeps defects open); `skipped` counts as not passed; tags with no
  acceptance results fall to the unit suite; `defects_left_open` will jump
  and trip W.4's regression flag; tests use `::` keys where the real
  separator is ` > `.
- H28 W.4 ledger: `mean > 0` guard means 0→n regressions never flag;
  benchmarks mixed in the 5-run window; wall time includes orphan gaps; CSV
  write non-atomic. W.1: byte-exact `cmp` fails toward *excluding* runs from
  false-acceptance stats.
- H29 AI lessons: gate is owner CLI approval only; `lessons.json` sits on a
  volume container-mode commands can write, no integrity check; `role`
  unused; rule text only length/banned-word checked, no "cannot override
  rules" framing. Injection point: system prompt after FRAMEWORK
  CAPABILITIES, cap 5, id order (byte-stable; one cache miss per approval).
- H30 `7eb9a91`: Python/JS heuristics (conftest, test-name regexes) in
  generic `stacks/scaffold.py`; mirror detection could flag monorepos.
- H31 AH.3: `_DOWNGRADE` ContextVar resets per graph build → the gap
  vanishes if the judgement server is back after a restart; detects
  construction failure only.
- H32 Repo-rule drift: stack-specific code in generic modules
  (`interface_contract.py`, `mutation.py`, `scaffold.py`); new prompt text
  without banned-word tests (X.3 sentence, AA update note, AE.2 gap
  strings — none contains a banned word today); two tests that would pass
  on old code (`ea714bc` filter, X.4 ceilings).
- H33 Steering placement (answer to the interaction question): end of the
  system prompt after stack instructions and lessons; byte-stable until a
  note is added or the 5-note window rolls (one full-prefix miss per live
  stage per note); up to 5×2000 chars ride every role's calls.

**Low**: `find -delete` and `head/tail` of logs blocked by `8ed63b2`;
confirm the per-stage withheld flag resets on stage revisit.

### 14.4 Final status (00:05 JST 2026-10-19)
- `docs/improvement-plan.md` Appendix 3 appended (`738f494`): Part 13
  fixes to today's implementations (AK budgets persisted, AL crash-safe
  mutation, AM seen-digest ownership, AN measurement correctness, AO bundle
  of ten lifecycle fixes, AP hygiene); Part 14 remaining gaps (AQ repeated
  reads, AR lost replies, AS steering v2, AT lessons v2, AU contract for
  every surface, AV AJ completion, AW K.6); Part 15 UI/UX revamp with the
  multi-theme design system (design brief reviewed against the generic
  default; three theme families + accents + density; token layers and the
  no-flash boot; codemod scope; primitive kit; six screens; backend
  enablers; quality floor); Part 16 sequence; ledger rows.
- Each item carries Goal/Evidence/Files/Steps/Tests/Acceptance/Effort.
- No code changed. No run started. The live app was not reachable; a
  screenshot pass per theme is the first UI task once a session is linked.
