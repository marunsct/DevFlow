# Review findings (unified evidence log, 2026-10-18 → 2026-10-21)

> Consolidated 2026-10-19 from `review-findings-wip.md` (sessions 1–3) and the
> session-4 review. This is the evidence log behind
> `docs/improvement-plan.md`. Each finding carries a *Plan:* line linking the
> plan items that answer it. Research moved to `docs/research-findings.md`
> (the section stubs below say where). `docs/logs.md`, cited in places
> below, was removed on 2026-10-19; its review points are listed in
> `docs/improvement-plan.md` Part 22.4.

## Finding index → plan

| Finding | Title | Plan items |
|---|---|---|
| F1 | (CRITICAL): Fullstack entrypoint never wired to drafted code | [K](improvement-plan.md#plan-k), [U](improvement-plan.md#plan-u), [L.6](improvement-plan.md#plan-l-6), [Sweep table](improvement-plan.md#plan-sweep) |
| F2 | (CRITICAL): No service provisioning; spec free to require PostgreSQL | [U](improvement-plan.md#plan-u) |
| F2 | REFINED (CRITICAL, root cause located): capability knowledge asymmetry | [U](improvement-plan.md#plan-u) |
| F3 | (HIGH): Dependency-manifest drift after drafting | [K](improvement-plan.md#plan-k) |
| F4 | (HIGH): Sandbox python env ambiguity (venv vs user-site) | [K](improvement-plan.md#plan-k) |
| F5 | (HIGH): All-or-nothing stage revert by CI gate | [L](improvement-plan.md#plan-l) |
| F6 | (HIGH): Defect sprawl from single root cause (confirms plan Initiative F) | [Sweep table](improvement-plan.md#plan-sweep) |
| F7 | (MEDIUM): Reasoning exhaustion still live | [Sweep table](improvement-plan.md#plan-sweep) |
| F8 | (MEDIUM): Very large prompts on judgement stages | [O](improvement-plan.md#plan-o), [Sweep table](improvement-plan.md#plan-sweep) |
| F9 | (MEDIUM): Streaming disabled by langchain incompatibility | [T](improvement-plan.md#plan-t) |
| F10 | (MEDIUM): Parallel mode gets ~1.0-1.3x overlap; server is 1 slot | [S](improvement-plan.md#plan-s), [Sweep table](improvement-plan.md#plan-sweep), [AB](improvement-plan.md#plan-ab) |
| F11 | (LOW/MED): integration_checks.py is JavaScript-shaped | [K.6](improvement-plan.md#plan-k-6), [Sweep table](improvement-plan.md#plan-sweep) |
| F12 | (OBSERVATION): test_round "did not report 13 failing criteria; | [Sweep table](improvement-plan.md#plan-sweep) |
| F13 | (MEDIUM): Seed instructions can contradict the environment | [Sweep table](improvement-plan.md#plan-sweep) |
| F14 | (CONTEXT): Verified mechanisms relevant to plan (no gap, cite as strengths) | not cited by a plan item (context, status or observation) |
| F15 | (HIGH): Opening requests on planning/judgement stages are 60-80k tokens | [O](improvement-plan.md#plan-o), [Sweep table](improvement-plan.md#plan-sweep) |
| F16 | (STATUS): Visual review loop already exists (Initiative B ~80% built) | [Sweep table](improvement-plan.md#plan-sweep) |
| F17 | (GAP): Benchmark corpus lacks fullstack-Python & service-backed briefs | [U](improvement-plan.md#plan-u), [Sweep table](improvement-plan.md#plan-sweep) |
| F18 | (CONTEXT): Strong existing tooling to build measurements on | [O](improvement-plan.md#plan-o), [U](improvement-plan.md#plan-u), [L.6](improvement-plan.md#plan-l-6), [Sweep table](improvement-plan.md#plan-sweep) |
| F19 | (CRITICAL, 2026-10-21): The loop fixes the harness faster than anything measures it — 137 LF rows in 3 days, every quality lever off, no clean gate run since 10-11, no run on one harness version, the gate brief without hidden tests, no provenance per run | [MF](improvement-plan.md#plan-mf), [RC](improvement-plan.md#plan-rc) |
| F20 | (HIGH, 2026-10-21): Readers misreading real model output are fixed one sample at a time (12+ LF rows) | [RC](improvement-plan.md#plan-rc) |
| F21 | (HIGH, 2026-10-21): The PM's open questions and assumptions are never put to the owner before the run | [IN](improvement-plan.md#plan-in) |
| F22 | (MEDIUM, 2026-10-21): Brownfield has no regression contract, no change-request run and no benchmark | [BW](improvement-plan.md#plan-bw) |
| F23 | (MEDIUM, 2026-10-21): 15–25 manual interventions a day; no backups; browser-only notifications | [OP](improvement-plan.md#plan-op) |
| F24 | (LOW, 2026-10-21): Product CI has no audit, secret or licence step; README unchecked; harness has no lint/type gate; root clutter | [PN](improvement-plan.md#plan-pn), [CH](improvement-plan.md#plan-ch), [SF](improvement-plan.md#plan-sf) |
| G1 | (HIGH, local-model): prompts order a tool the role is not given — and contradict themselve | [Appendix 2](improvement-plan.md#plan-appendix-2), [X](improvement-plan.md#plan-x) |
| G2 | (HIGH, throughput): project memory sits at the head of the conversation and is rewritten f | [Appendix 2](improvement-plan.md#plan-appendix-2), [AA](improvement-plan.md#plan-aa), [Part 17](improvement-plan.md#plan-part-17), [BJ](improvement-plan.md#plan-bj) |
| G3 | (MEDIUM, local-model): no sampling or cache parameters are ever sent | [M (concrete)](improvement-plan.md#plan-m-concrete), [AA](improvement-plan.md#plan-aa) |
| G4 | (MEDIUM): tool list changes mid-conversation | [AA](improvement-plan.md#plan-aa) |
| G5 | (MEDIUM): maintenance prose inside system prompts | [X](improvement-plan.md#plan-x) |
| G6 | (LOW–MED): parallel-mode hazard — process-wide globals | [Part 12](improvement-plan.md#plan-part-12) |
| G7 | (UI/plan correction): no steering endpoint exists | [Ledger](improvement-plan.md#plan-ledger), [Part 11](improvement-plan.md#plan-part-11) |
| G8 | (UI/plan correction): artifact versioning has no real data | [Ledger](improvement-plan.md#plan-ledger) |
| G9 | (UI): intake has no free-text brief, and a failed start orphans a run | [UI 15.4](improvement-plan.md#plan-ui-15-4), [Ledger.A3](improvement-plan.md#plan-ledger-a3) |
| G10 | (UI, measured by mapper): still-open harms from Part 4 Phase 1 | [Part 11](improvement-plan.md#plan-part-11) |
| G11 | (API/UI mismatches, mapper) | [Part 11](improvement-plan.md#plan-part-11) |
| G12 | (EVIDENCE CORRECTION, HIGH): the local-model "quality cliff" (C8 → Initiative Q) is confou | [Appendix 2](improvement-plan.md#plan-appendix-2), [W](improvement-plan.md#plan-w) |
| G13 | (EVIDENCE GAP, HIGH): no scored run exists after the P0 wave | [Appendix 2](improvement-plan.md#plan-appendix-2), [W](improvement-plan.md#plan-w) |
| G14 | (A/B BLOCKER, MEDIUM): the toggles do not reach the container | [W](improvement-plan.md#plan-w) |
| G15 | (LEDGER ACCURACY): U.2 claims not borne out | [W](improvement-plan.md#plan-w) |
| G16 | (LANGUAGE-AGNOSTIC CLAIM): where the packs stop | [AG](improvement-plan.md#plan-ag) |
| G17 | (DOCS DRIFT): HANDOVER §2 frozen at 10-12 (model row, suite count, | [AP](improvement-plan.md#plan-ap) |
| G18 | (THROUGHPUT, parked items that matter most) | [Part 8](improvement-plan.md#plan-part-8) |
| G19 | (HIGH, release integrity + treadmill): a fix is "fixed" on the fixer's say-so | [Appendix 2](improvement-plan.md#plan-appendix-2), [AD](improvement-plan.md#plan-ad) |
| G20 | (MEDIUM): two different "tests that cannot pass" lists | [AE](improvement-plan.md#plan-ae), [Ledger.A2](improvement-plan.md#plan-ledger-a2) |
| G21 | (MEDIUM, prompt/code disagreement): milestone `blocked` verdict | [Appendix 2](improvement-plan.md#plan-appendix-2), [X](improvement-plan.md#plan-x) |
| G22 | (MEDIUM, local-model): tool description untrue in container mode | [Appendix 2](improvement-plan.md#plan-appendix-2), [X](improvement-plan.md#plan-x) |
| G23 | (THROUGHPUT): parallelism is mostly nominal | [Appendix 2](improvement-plan.md#plan-appendix-2), [AB](improvement-plan.md#plan-ab) |
| G24 | (THROUGHPUT, model calls that deterministic data can gate) | [AC](improvement-plan.md#plan-ac) |
| G25 | (CORRECTNESS, status model): `completed_with_gaps` is a list on `completed` | [AE](improvement-plan.md#plan-ae) |
| G26 | (MAINTAINABILITY, refactor evidence for V) | [Part 12](improvement-plan.md#plan-part-12) |
| G27 | (not a bug, mapper over-flag): last-attempt shape change | [Appendix 2](improvement-plan.md#plan-appendix-2) |
| H1 | (THEME FEASIBILITY, decisive): multi-theme is a token-redefinition job, not a rewrite | [I](improvement-plan.md#plan-i), [Appendix 3](improvement-plan.md#plan-appendix-3), [Part 15](improvement-plan.md#plan-part-15), [UI 15.2](improvement-plan.md#plan-ui-15-2), [BG.11](improvement-plan.md#plan-bg-11) |
| H2 | (PRIMITIVES): one real primitive module | [I](improvement-plan.md#plan-i), [UI 15.3](improvement-plan.md#plan-ui-15-3) |
| H3 | (NEW FEATURES, `ef982a2`): working, but thin | [AS](improvement-plan.md#plan-as), [UI 15.5](improvement-plan.md#plan-ui-15-5) |
| H4 | (API ↔ UI): fields exist server-side, UI ignores them | [UI 15.5](improvement-plan.md#plan-ui-15-5) |
| H5 | (PHASE-1 REMAINDER, verified): favicon badge, browser Notifications, | [UI 15.7](improvement-plan.md#plan-ui-15-7) |
| H6 | (NARRATION DRIFT): 21 graph stages have no `STAGE_COPY` (title-case | [UI 15.1](improvement-plan.md#plan-ui-15-1), [UI 15.4](improvement-plan.md#plan-ui-15-4), [UI 15.5](improvement-plan.md#plan-ui-15-5) |
| H7 | (IA): routes `/login`, `/` (intake), `/runs`, `/runs/:id`, `/settings`; | [Part 15](improvement-plan.md#plan-part-15), [UI 15.4](improvement-plan.md#plan-ui-15-4), [Ledger.A3](improvement-plan.md#plan-ledger-a3) |
| H8 | (API data unused by the UI that would change behaviour): `/events?since` | [UI 15.4](improvement-plan.md#plan-ui-15-4) |
| H9 | (GOVERNING GAP, unchanged from G13): ~25 fixes today, zero verified on a run | [Appendix 3](improvement-plan.md#plan-appendix-3), [AP](improvement-plan.md#plan-ap), [Ledger.A3](improvement-plan.md#plan-ledger-a3) |
| H10 | (KPI CORRECTNESS): the new KPI script under-counts and mis-ratios | [AN](improvement-plan.md#plan-an) |
| H11 | (LOOP SCRIPT BUGS): `loop.sh kpi` (`loop.sh:222`) redirects to | [AN](improvement-plan.md#plan-an) |
| H12 | (THE 431 READS): the lead the ledger left open | [AQ](improvement-plan.md#plan-aq) |
| H13 | (LEDGER DRIFT): stale NOT STARTED rows duplicate DONE rows (M L1348; | [AV](improvement-plan.md#plan-av) |
| H14 | (DECISION/IMPLEMENTATION MISMATCHES): AF budget decided "per lock", | [AP](improvement-plan.md#plan-ap) |
| H15 | (MEASUREMENTS TO CARRY INTO THE PLAN): 37 lost replies ≈40% of the | [AQ](improvement-plan.md#plan-aq), [AR](improvement-plan.md#plan-ar) |
| I1 | (EFFICIENCY, critical): 35% of all output tokens were spent on replies that were thrown aw | [AX](improvement-plan.md#plan-ax), [BB](improvement-plan.md#plan-bb) |
| I2 | (QUALITY, critical): the defect-fix loop does not converge on a complex product | [AY](improvement-plan.md#plan-ay), [BC](improvement-plan.md#plan-bc), [BI](improvement-plan.md#plan-bi) |
| I3 | (EFFICIENCY, high): reading is still half of the loop's work | [AY](improvement-plan.md#plan-ay), [BC](improvement-plan.md#plan-bc), [BA](improvement-plan.md#plan-ba), [BJ](improvement-plan.md#plan-bj) |
| I4 | (EFFICIENCY, high): decode, not prefill, is the clock | [AX](improvement-plan.md#plan-ax), [BB](improvement-plan.md#plan-bb), [BD](improvement-plan.md#plan-bd) |
| I5 | (QUALITY, high): one sprint, thirty locked tests, one monolithic specification is the wron | [AZ](improvement-plan.md#plan-az), [BJ](improvement-plan.md#plan-bj) |
| I6 | (EFFICIENCY, medium): the lead's plan is one 20k-token reply | [BB](improvement-plan.md#plan-bb) |
| I7 | (EFFICIENCY, medium): parallel mode on a 1-slot server shares one KV cache | [BA](improvement-plan.md#plan-ba) |
| I8 | (EFFICIENCY, medium): one throwaway container per command | [BE](improvement-plan.md#plan-be) |
| I9 | (QUALITY, medium): local-only runs never get the "judgement" tier | [BD](improvement-plan.md#plan-bd) |
| I10 | (EFFICIENCY, low): the 40-call budget is per attempt, not per defect | [AY](improvement-plan.md#plan-ay), [BC](improvement-plan.md#plan-bc) |
| I11 | (TOOLING, medium): the harness cannot observe its own prompt composition per call | [BF](improvement-plan.md#plan-bf) |
| I12 | (UI/UX): findings I12.1–I12.12 in §15.2 | [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg) |
| I12.1 | (OWNER, high): no progress, no ETA, no tokens | [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg) |
| I12.2 | (OWNER, high): gates are not legible | [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg) |
| I12.3 | (OWNER, high): nothing tells an absent owner | [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg) |
| I12.4 | (OWNER, medium): decisions and steering are buried | [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg) |
| I12.5 | (OWNER, medium): intake has no pre-flight or review step | [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg) |
| I12.6 | (DEVELOPER, high): per-stage time/tokens/KPIs exist only on the CLI | [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg) |
| I12.7 | (DEVELOPER, medium): held-back reads and lost replies look like successes in the feed | [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg) |
| I12.8 | (OPERATOR, high): no model-server surface | [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg) |
| I12.9 | (DESIGN, medium): hierarchy inverted, plan not first-class | [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg) |
| I12.10 | (DESIGN, low): visual residue and copy | [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg) |
| I12.11 | (A11Y/PERF, medium): not yet in the ledger | [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg) |
| I12.12 | (HOUSEKEEPING): regenerate `docs/ui/*-runs.png`; `vite.config.ts:11` | [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg) |


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
  (§0.9,0.10,5,6,8,9,10), improvement-plan.md (full), improvement-plan.md (full).
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

*Plan:* [K](improvement-plan.md#plan-k), [U](improvement-plan.md#plan-u), [L.6](improvement-plan.md#plan-l-6), [Sweep table](improvement-plan.md#plan-sweep)
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

*Plan:* [U](improvement-plan.md#plan-u)
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

*Plan:* [U](improvement-plan.md#plan-u)
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

*Plan:* [K](improvement-plan.md#plan-k)
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

*Plan:* [K](improvement-plan.md#plan-k)
- Bare `pip`/`python3` in sandbox = system python; installs go to
  `.agent-home/.local` ("Defaulting to user installation because normal
  site-packages is not writeable") — invisible to `.venv/bin/python` the
  acceptance server uses. Fixer verified with `pip list` and believed deps were in.
- Fix direction: sandbox prepends project venv bin (`.venv/bin`,
  `node_modules/.bin`) to PATH when a pack declares one; or refuse bare
  pip/python when a venv exists, with a notice naming the venv interpreter.

### F5 (HIGH): All-or-nothing stage revert by CI gate

*Plan:* [L](improvement-plan.md#plan-l)
- "it broke 4 test(s) that passed before it" → ENTIRE fix stage reverted,
  discarding the (correct) dependency work and any good edits; next fixer starts
  from identical state; loop. Two consecutive reverts observed live.
- Fix direction: per-defect/per-file revert granularity, or auto targeted
  repair round on only the broken tests before reverting everything; keep
  manifest/dependency changes out of revert scope.

### F6 (HIGH): Defect sprawl from single root cause (confirms plan Initiative F)

*Plan:* [Sweep table](improvement-plan.md#plan-sweep)
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

*Plan:* [Sweep table](improvement-plan.md#plan-sweep)
- 17:18:43 UTC defect_fix_2_1: "Stage specialist_backend lost a reply to
  reasoning (1 in a row); asking again at once with thinking off" + "spent a
  whole reply's output budget on reasoning; thinking switched off for next
  reply". 8 `finish_reason=length` in 151 responses so far; max output 20,000.
- Existing mitigations fire AFTER a wasted 20k-token pass. Confirms Initiative I
  (bounded thinking budget up-front) — add evidence.

### F8 (MEDIUM): Very large prompts on judgement stages

*Plan:* [O](improvement-plan.md#plan-o), [Sweep table](improvement-plan.md#plan-sweep)
- acceptance_review_1 median prompt 203k chars (~65k tokens), acceptance_dispute
  188k, scrum_master 124k, principal_architect 100k. On a local server prefill
  is slow and context rot is real (research pending). Window is ~130k tokens
  (settings) — these are near half the window in ONE message set.
- Fix direction: budget the review corpus (locked suite is ~35 tests; send
  per-file or summarized), spec section windows, cache-friendly ordering.

### F9 (MEDIUM): Streaming disabled by langchain incompatibility

*Plan:* [T](improvement-plan.md#plan-t)
- models/__init__.py `_request_timeout` docstring: streaming would fix the
  timeout-vs-length tension but `streaming=True` breaks through
  langchain.agents ("Expected a dict or openai.BaseModel, got Stream") — "Revisit
  only with a reproduction through langchain.agents". Worth retesting with
  current langchain-openai >= 1.0 (may be fixed upstream now).
- Streaming also unlocks live token streaming to the UI (UX win).

### F10 (MEDIUM): Parallel mode gets ~1.0-1.3x overlap; server is 1 slot

*Plan:* [S](improvement-plan.md#plan-s), [Sweep table](improvement-plan.md#plan-sweep), [AB](improvement-plan.md#plan-ab)
- Monitoring §0.9: "LM Studio's 8 slots go unused"; gated pauses drain one per
  superstep; HANDOVER §7: fixing = redesign of runner auto-approve loop.
- Also queueing: parallel specialists against a 1-slot llama.cpp server just
  serialize with extra prompt-cache thrash (each switch = new slot prefix).
- Fix direction: match HARNESS_MAX_PARALLEL to server slots (capability probe);
  server-side: recommend llama.cpp `--parallel N --cont-batching` or vLLM
  continuous batching in readiness docs; or harness-side "phase-aligned"
  scheduling so same-stage agents batch their calls.

### F11 (LOW/MED): integration_checks.py is JavaScript-shaped

*Plan:* [K.6](improvement-plan.md#plan-k-6), [Sweep table](improvement-plan.md#plan-sweep)
- Function inventory shows node/browser/CSS/DOM checks dominate
  (`_node_suites_nothing_runs`, `_dangling_class_selectors`, browser events...).
  harness-improvement-plan B1 admits "Multi-file symbol references for Go, Rust,
  polyglot still heuristics". For language-agnostic claim: Python/Go/Rust
  products get weaker static integration analysis than JS.

### F12 (OBSERVATION): test_round "did not report 13 failing criteria;

*Plan:* [Sweep table](improvement-plan.md#plan-sweep)
recording them as defects" + "left out 2 problems it was handed as proven" —
harness-run test round works but the model round re-derives; fine. Also
"3 defects describe one problem; merged into one" — merging exists for
identical problems (frontend/package.json two test runners) but NOT for
common-root-cause criterion failures (F6).

### F13 (MEDIUM): Seed instructions can contradict the environment

*Plan:* [Sweep table](improvement-plan.md#plan-sweep)
- `plugins/seed.py` has a `postgres` key injected when the stack doc names
  PostgreSQL: guidance encourages pooled Postgres usage — while the sandbox
  provides no Postgres and `pg_isready` is refused. Python seed says "Do not
  install globally. Always use a virtual environment" — yet sandbox gives bare
  `pip` that installs to user-site (F4). This is monitoring §6.2's
  "instructing and then punishing" class, still live.
- Fix direction: seed rows must be filtered by environment capability (same
  capability profile as F2); sandbox PATH fix makes the python seed true.

### F14 (CONTEXT): Verified mechanisms relevant to plan (no gap, cite as strengths)

*Plan:* not cited by a plan item (context, status or observation)
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

*Plan:* [O](improvement-plan.md#plan-o), [Sweep table](improvement-plan.md#plan-sweep)
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

*Plan:* [Sweep table](improvement-plan.md#plan-sweep)
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

*Plan:* [U](improvement-plan.md#plan-u), [Sweep table](improvement-plan.md#plan-sweep)
- benchmarks/: web-todo, notes-api(-js/-hono), wordstats-cli, textkit-lib,
  fullstack-bookmarks, web-todo-react. Gate ladder covers JS/Python single-tier
  products. brief_medium (FastAPI+React+PostgreSQL) has NO hidden tests →
  audited by hand. The exact failure class of the live run (F1/F2) is
  invisible to the benchmark gate.
- Fix direction: add a `fullstack-py` benchmark (pack-supported, hidden tests
  through HTTP only) and a service-backed benchmark variant once F2 lands;
  both hold the fullstack packs to the same standard as the others.

### F18 (CONTEXT): Strong existing tooling to build measurements on

*Plan:* [O](improvement-plan.md#plan-o), [U](improvement-plan.md#plan-u), [L.6](improvement-plan.md#plan-l-6), [Sweep table](improvement-plan.md#plan-sweep)
- scripts/loop/: run_timing.py, redundant_reads.py, model_fitness.py,
  lessons.py, defects.py, failures.py, audit_live.py, product_audit.py,
  stage_trace.py, check_precision.py, verify_packs.py, pack_freshness.py.
- evaluation/evaluate.py: LangSmith-based intake/architecture evaluators.
- Plan's measurement items should reuse these (e.g., add
  `entrypoint_wiring`, `manifest_drift`, `revert_treadmill` counters to
  audit_run/transcript_metrics).

## 4. Research interim — removed

Superseded by §8, now `docs/research-findings.md` Part R4.

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

Moved to `docs/research-findings.md` Part R5 on 2026-10-19 (with its links to the plan).

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

Moved to `docs/research-findings.md` Part R4 on 2026-10-19 (with its links to the plan).

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

Moved to `docs/research-findings.md` Part R3 on 2026-10-19 (with its links to the plan).

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

*Plan:* [Appendix 2](improvement-plan.md#plan-appendix-2), [X](improvement-plan.md#plan-x)
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

*Plan:* [Appendix 2](improvement-plan.md#plan-appendix-2), [AA](improvement-plan.md#plan-aa), [Part 17](improvement-plan.md#plan-part-17), [BJ](improvement-plan.md#plan-bj)
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

*Plan:* [M (concrete)](improvement-plan.md#plan-m-concrete), [AA](improvement-plan.md#plan-aa)
- Stages send no `temperature`/`top_p`/`seed`/`cache_prompt`/`json_schema`
  (`models/__init__.py`); the only `temperature=0` is the framework-extraction
  call (`plugins/middleware.py:166`). Behaviour therefore depends entirely on
  how the owner launched the server. Model cards (Qwen3: 0.7/0.8/20, presence
  penalty for loops; GLM 1.0/0.95/40) and M's profile contract are the place
  for these; today `server/model_profiles.py` is only a saved-settings store
  (235 lines, no per-family behaviour) and `models/fitness.py` has no caller
  under `src/`.

#### G4 (MEDIUM): tool list changes mid-conversation

*Plan:* [AA](improvement-plan.md#plan-aa)
- Settled-answer withholding and the research-share cap remove tools
  mid-stage; the prefix changes (cache miss) and the schema the model
  learned from no longer matches (weak models keep calling the removed
  tool). Manus "mask, don't remove"; Initiative O noted it — now with code
  pointers (`map-agents.md` §6 item 4).

#### G5 (MEDIUM): maintenance prose inside system prompts

*Plan:* [X](improvement-plan.md#plan-x)
- `technical_lead.py:674-777` and the environment contract carry "Measured
  across the stored runs…" statistics and ALL-CAPS/CRITICAL emphasis. Prompt
  sizes 1.7k–14k chars per role. For 20–40B models the research consistently
  favours short, imperative, example-led rules; the rationale belongs in the
  module docstring (where this codebase already keeps it beautifully), not
  in the tokens the model pays for every call.

#### G6 (LOW–MED): parallel-mode hazard — process-wide globals

*Plan:* [Part 12](improvement-plan.md#plan-part-12)
- `settled_answer.py:573,584` `_LAST_FAILING_FIELDS` / `_LAST_FAILURE_KIND`
  are module globals read across stages; in parallel mode two specialists
  can read each other's failure state. Needs a per-thread/per-stage carrier.

#### G7 (UI/plan correction): no steering endpoint exists

*Plan:* [Ledger](improvement-plan.md#plan-ledger), [Part 11](improvement-plan.md#plan-part-11)
- Session 1's Phase 3 "steering composer via the existing
  dynamic-instruction-injection hook" rests on a misreading:
  `plugins/middleware.py` injects *framework* guidance per stack; there is
  no user→run instruction path and the WebSocket is read-only (`map-ui.md`
  §3). Steering needs a new backend enabler (queue + middleware that
  appends the operator note as a trailing message at the next stage
  boundary), and that is the right place for it architecturally.

#### G8 (UI/plan correction): artifact versioning has no real data

*Plan:* [Ledger](improvement-plan.md#plan-ledger)
- `server/runs.py:1704-1713` hard-codes `revision=1` and the in-flight stage
  on every artifact. The planned diff/version viewer needs the workspace git
  history (every stage commits) exposed per path first.

#### G9 (UI): intake has no free-text brief, and a failed start orphans a run

*Plan:* [UI 15.4](improvement-plan.md#plan-ui-15-4), [Ledger.A3](improvement-plan.md#plan-ledger-a3)
- Intake accepts documents only; `createRun` then `startRun` — a failure in
  the second leaves a `created` run with no owner action. Access token
  expires at 60 min with no refresh → a full reload mid-run.

#### G10 (UI, measured by mapper): still-open harms from Part 4 Phase 1

*Plan:* [Part 11](improvement-plan.md#plan-part-11)
- None of Phase 1 landed (no `aria-live`/`role=status`, 17 native
  `alert()/confirm()`, modal without dialog role, 31 hex literals + 115 raw
  slate/white classes, RunList polls 5 s even when hidden, no WS→poll
  fallback, whole-log copy+sort per WS frame, `waiting_for_budget` missing
  from `statusConfig`, "Documents N produced" counts code files). Landed
  since: completion_gaps/non_deliverable banners, partial-pricing honesty,
  rewind UI, outcomes+forecast, approval-timeout input.

#### G11 (API/UI mismatches, mapper)

*Plan:* [Part 11](improvement-plan.md#plan-part-11)
- `document_names` (list) vs UI `document_name`; `approval_timeout_minutes`
  stored but absent from `RunStatusResponse`; token counts, `reviews[]`,
  `remediation` typed but never rendered; `delivery_mode`,
  `use_frontier_model`, `auto_approve` absent from the UI type; dashboard does
  not refetch on `budget_pause`/`approval_denied`/`review_decision`; after a
  `closed` frame the stream is never re-attached; brownfield
  (`StartRunRequest.source`, `POST /runs/{id}/codebase`) unreachable from UI.

### 13.3 Checkpoint 4 (12:25 JST) — run history / packs / loop map landed (`map-runs-packs.md`)

#### G12 (EVIDENCE CORRECTION, HIGH): the local-model "quality cliff" (C8 → Initiative Q) is confounded

*Plan:* [Appendix 2](improvement-plan.md#plan-appendix-2), [W](improvement-plan.md#plan-w)
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

*Plan:* [Appendix 2](improvement-plan.md#plan-appendix-2), [W](improvement-plan.md#plan-w)
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

*Plan:* [W](improvement-plan.md#plan-w)
- `docker-compose.yml` `x-app-env` does not pass `LINE_EDITS`,
  `ENVIRONMENT_CONTRACT`, `WORKSPACE_DIGEST`, `PROJECT_MEMORY`,
  `HARNESS_TASK_LIST`, `JUDGEMENT_*`, `ESCALATE_AFTER_ATTEMPTS`,
  `MODEL_MAX_OUTPUT_TOKENS`. Every "A/B-verified" clause in the plan is
  unexecutable without editing compose. Related config drift:
  `SANDBOX_MEMORY_LIMIT` 4g (code) / 1g (compose) / 2g (.env.example);
  `MODEL_CONTEXT_WINDOW` default 100000 vs server started at 126,464;
  `HARNESS_MAX_PARALLEL=6` default against a 1-slot server.

#### G15 (LEDGER ACCURACY): U.2 claims not borne out

*Plan:* [W](improvement-plan.md#plan-w)
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

*Plan:* [AG](improvement-plan.md#plan-ag)
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

*Plan:* [AP](improvement-plan.md#plan-ap)
"27 packs" vs 35); improvement-plan §4 still says bf43c7e2 is running (it
failed 06:49 JST in `defect_fix_2_19`, `ValueError` from the venv symlink
outside the workspace root — itself a K.5 regression candidate); line 15
calls gpt-oss-20b "frontier".

#### G18 (THROUGHPUT, parked items that matter most)

*Plan:* [Part 8](improvement-plan.md#plan-part-8)
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

*Plan:* [Appendix 2](improvement-plan.md#plan-appendix-2), [AD](improvement-plan.md#plan-ad)
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

*Plan:* [AE](improvement-plan.md#plan-ae), [Ledger.A2](improvement-plan.md#plan-ledger-a2)
- `acceptance_nodes.py:376-401` (review, 18 checks) vs `:1141-1153` (per
  round, 11): the round list lacks `locators_nobody_sees`,
  `locators_that_pick_one`, `tests_that_assert_an_unstated_order`,
  `locators_that_contradict_their_assertions`, `controls_never_found_by_name`,
  `tests_with_module_system_mismatch`, `tests_with_unawaited_async_helpers`.
  Repaired/reopened tests re-enter through the shorter list, so a test only
  the long list catches can be locked and later charged to the product. One
  list, one function.

#### G21 (MEDIUM, prompt/code disagreement): milestone `blocked` verdict

*Plan:* [Appendix 2](improvement-plan.md#plan-appendix-2), [X](improvement-plan.md#plan-x)
- `agents/milestone_reviewer.py:99-105` tells the model `blocked` ends the
  run; `workflow.py:9756-9768` re-plans instead, with no visible cap on that
  branch. Same class as G1 (instruct, then do otherwise) — and a weak model
  that believes `blocked` is terminal will avoid saying it.

#### G22 (MEDIUM, local-model): tool description untrue in container mode

*Plan:* [Appendix 2](improvement-plan.md#plan-appendix-2), [X](improvement-plan.md#plan-x)
- `agent_toolkit.py:585` says everything except install runs with the
  network off; in-container mode applies no network restriction
  (`sandbox.py:4364-4437`) and builds its environment differently (venv
  PATH, `ACCEPTANCE_PORT`). The tool text is part of the prompt the model
  reasons from; it must be rendered from the active mode.

#### G23 (THROUGHPUT): parallelism is mostly nominal

*Plan:* [Appendix 2](improvement-plan.md#plan-appendix-2), [AB](improvement-plan.md#plan-ab)
- Per-workspace command lock serialises every command (`sandbox.py:3732`);
  `HARNESS_MAX_PARALLEL=6`; `fix_by_candidates` fires 3× the file count of
  concurrent model calls (`rewritten_fixes.py:278`) — against a 1-slot
  server this is queueing plus KV-cache thrash (session-1 F10 measured
  1.0–1.3×). The honest default is `max_parallel = server slots` (S already
  reads `/props`).

#### G24 (THROUGHPUT, model calls that deterministic data can gate)

*Plan:* [AC](improvement-plan.md#plan-ac)
- Thorough mode runs a judgement-model testing agent every round although
  the fast "harness round" gathers the same measurements; architecture and
  milestone reviews run even when the harness found no breakage and the
  suite is green; `security_review` runs when nothing risky changed (the
  conditional skip exists per the old plan — verify it is reached);
  `what_the_files_already_prove` (49 whole-workspace checks) is recomputed
  several times per round with no caching.

#### G25 (CORRECTNESS, status model): `completed_with_gaps` is a list on `completed`

*Plan:* [AE](improvement-plan.md#plan-ae)
- Stored as `completed` + `completion_gaps` + `NON-DELIVERABLE.json`
  (delivery.py:259-293, runner.py:1448-1490). Never reaching the gaps list:
  fast-mode review findings recorded as risks, escalation `known_issues`,
  defects accepted as risk. Release does not re-run compiler, dependency-
  drift or integration checks. (J.4 implementation note acknowledged the
  enum constraint; the three missing sources are new.)

#### G26 (MAINTAINABILITY, refactor evidence for V)

*Plan:* [Part 12](improvement-plan.md#plan-part-12)
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

*Plan:* [Appendix 2](improvement-plan.md#plan-appendix-2)
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

Moved to `docs/research-findings.md` Part R2 on 2026-10-19 (with its links to the plan).

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

*Plan:* [I](improvement-plan.md#plan-i), [Appendix 3](improvement-plan.md#plan-appendix-3), [Part 15](improvement-plan.md#plan-part-15), [UI 15.2](improvement-plan.md#plan-ui-15-2), [BG.11](improvement-plan.md#plan-bg-11)
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

*Plan:* [I](improvement-plan.md#plan-i), [UI 15.3](improvement-plan.md#plan-ui-15-3)
- `components/Feedback.tsx:28` (`FeedbackProvider`/`useFeedback`: toasts +
  confirm dialog with focus trap/Escape/scroll lock/focus restore) is the
  only shared primitive. No Button/Card/Badge/Tabs/Input/Select/Dialog/
  Skeleton/EmptyState; 8 separate status-colour maps; spinner hand-rolled
  7×; `Checkbox` local to `Home.tsx:134`; `CredentialField`/`InfoRow`
  defined *inside* the Settings render (`Settings.tsx:175,197`) → remount
  per render, inputs likely lose focus per keystroke.

#### H3 (NEW FEATURES, `ef982a2`): working, but thin

*Plan:* [AS](improvement-plan.md#plan-as), [UI 15.5](improvement-plan.md#plan-ui-15-5)
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

*Plan:* [UI 15.5](improvement-plan.md#plan-ui-15-5)
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

*Plan:* [UI 15.7](improvement-plan.md#plan-ui-15-7)
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

*Plan:* [UI 15.1](improvement-plan.md#plan-ui-15-1), [UI 15.4](improvement-plan.md#plan-ui-15-4), [UI 15.5](improvement-plan.md#plan-ui-15-5)
fallback); `activity.ts:139` renders `specialist_gather`/`specialist_worker`
as "Building the gather part".

#### H7 (IA): routes `/login`, `/` (intake), `/runs`, `/runs/:id`, `/settings`;

*Plan:* [Part 15](improvement-plan.md#plan-part-15), [UI 15.4](improvement-plan.md#plan-ui-15-4), [Ledger.A3](improvement-plan.md#plan-ledger-a3)
no 404, no global "needs you" indicator, no help, no post-login redirect;
model settings only in `/settings` and Home never checks a model is
configured; no skeletons; OutcomesPanel/DeliveryPanel/SprintSummaryPanel/
first-run Settings render nothing when empty; on the run page gate,
steering, sprint summary and delivery stack full-width above the 3-column
workspace → workspace below the fold at 768 px.

#### H8 (API data unused by the UI that would change behaviour): `/events?since`

*Plan:* [UI 15.4](improvement-plan.md#plan-ui-15-4)
exists → WS→poll fallback is a UI-only change; `approval_timeout_minutes`
in payload → the stall/countdown surfaces need no backend.

### 14.2 Checkpoint 3 (23:05 JST) — evidence/KPI map landed (`map-evidence-v2.md`); findings H9–H15 (verified where marked ✓)

#### H9 (GOVERNING GAP, unchanged from G13): ~25 fixes today, zero verified on a run

*Plan:* [Appendix 3](improvement-plan.md#plan-appendix-3), [AP](improvement-plan.md#plan-ap), [Ledger.A3](improvement-plan.md#plan-ledger-a3)
- run-8b0c94df's outcome is still recorded nowhere (last note: "cancel if
  ≥20 of 30 acceptance tests still fail"); no run has started on the
  post-fix code; HANDOVER §2.2 "Verify on the next run" not updated for
  today's commits. Owner decision 9 (W.2 order: fast notes-api-hono → fast
  fullstack-bookmarks-py → thorough) is the gate for everything below.

#### H10 ✓ (KPI CORRECTNESS): the new KPI script under-counts and mis-ratios

*Plan:* [AN](improvement-plan.md#plan-an)
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

*Plan:* [AN](improvement-plan.md#plan-an)
`data/kpi/<run>.json` *before* the worker command succeeds → a failing
worker leaves an error JSON in place of the run's KPIs (ledger step
skipped). `loop.sh lessons` (`loop.sh:294`) passes only `${2:-3}` → `list`
works, `propose|approve|reject` fail through `loop.sh` (HANDOVER already
notes it). The per-run proposal list for the owner is not automated.

#### H12 (THE 431 READS): the lead the ledger left open

*Plan:* [AQ](improvement-plan.md#plan-aq)
- Read ladder today: memory pointer → note at 3rd read → withhold at 3
  repeats → name the exit at 6 → refuse at 12; read tool removed at 3
  refusals/held-backs or 8 pointers. Two plausible causes, neither
  confirmed: the first repeat gets no notice (`REPEATS_BEFORE_SAYING_SO`=2,
  notes appended *after* content), and memory pointers cover whole files
  ≤60k chars only. With R's recitation now in place, the next audit should
  measure repeated reads per stage *before vs after* R on the W.2 baseline.

#### H13 (LEDGER DRIFT): stale NOT STARTED rows duplicate DONE rows (M L1348;

*Plan:* [AV](improvement-plan.md#plan-av)
O.1–O.4 L1358–1361; Z/AA/AB L2022–2024; UI rows L2036–2040); AJ row
"IDENTIFIED" though item 1 landed in `2f68304` (NullPool/`dispose()`
seeding and timeout stdout diagnostics not built — direct pytest runs can
still hang); M.4–M.6 row says out-of-list tool-name KPI NOT STARTED but
`unknown_tool_name_rate` exists; HANDOVER §2 table still 2026-10-12.

#### H14 (DECISION/IMPLEMENTATION MISMATCHES): AF budget decided "per lock",

*Plan:* [AP](improvement-plan.md#plan-ap)
implemented at release (correctly — the suite locks before the build — but
the decision text should say so); J.3 "gap for 2 runs then blocker" and E
"measure over 2 runs" have no run behind them; `gate_deadline` derived from
`updated_at` may not match the real timeout sweep.

#### H15 (MEASUREMENTS TO CARRY INTO THE PLAN): 37 lost replies ≈40% of the

*Plan:* [AQ](improvement-plan.md#plan-aq), [AR](improvement-plan.md#plan-ar)
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

---

## 15. Fourth review session — progress log (started 2026-10-19 07:15 JST)

Scope: a fresh read of `harness-hardening-session` at `9275b8f` (2026-10-19 06:50 JST),
the host's `data/kpi/` and `data/bench/` records, and web research on how the
2026 generation of coding harnesses (Claude Code / Agent SDK, Codex, OpenHands,
Aider, SWE-agent, Cline) and local inference servers (llama.cpp, vLLM) handle
the same problems. The question the owner asked: *how do local models handle
complex products efficiently?* Nothing below re-proposes an item the ledger
marks DROPPED (M.2, M.3, O.4/Z, Y, AA.2, AC.3, U.4, M-bash) without new
evidence. Findings are numbered I1…; the plan built from them is Appendix 4 of
`docs/improvement-plan.md` (initiatives AX…).

### 15.0 Checkpoint 1 (08:10 JST) — the shape of the problem

The harness **works for small products and does not converge on complex
ones**. The same model (`unsloth/Qwen3.6-35B-A3B-MTP-GGUF`, 1-slot llama.cpp
server, 126k context, fast delivery, no frontier model) delivered:

| run | brief | wall | model calls | output tokens | result |
|---|---|---|---|---|---|
| 77c6650e | web-todo (low) | 82 min | 172 | 0.40M | 10/10 hidden, 15/15 locked |
| 8b0c94df | brief_medium (full-stack: JWT auth, teams, tasks, analytics) | **24.1 h** (1,448.9 min) | **2,593** | **5.22M** | sprint 1 attempt 4: 9 of 30 acceptance tests; 62 defects raised, **8 fixed**, 67 open, 6 fixes reverted |

Source: `data/kpi/run-8b0c94df-eff4-47f2-82c8-0ad06b7c5285.json` (W.4 KPI,
written 2026-10-18 22:12 JST) and `data/bench/run-77c6650e….json`. The medium
run's budget went where the table below says. Every finding in this session
is a reading of that file against the code that produced it.

#### I1 (EFFICIENCY, critical): 35% of all output tokens were spent on replies that were thrown away ✓

*Plan:* [AX](improvement-plan.md#plan-ax), [BB](improvement-plan.md#plan-bb)

`replies_lost_to_length = 92`, `lost_reply_output_share = 0.3522`,
`output_tokens = 5,224,684` → **≈1.84M tokens, ≈20k tokens per lost reply**.
At the measured ~100 tok/s decode that is ≈300 model-minutes, ≈21% of the whole
run's wall clock, producing nothing. `reasoning_share_estimated = 0.32`
(1.70M tokens), so the lost replies are overwhelmingly reasoning that ran into
the 20k output ceiling the server was started with. Per stage: `technical_lead`
lost 12 replies (112 calls, 364k output), every `defect_fix_*` lost 2–6.

Mechanism (code): `agents/thinking.py` can only send `reasoning_effort`
(ignored by Qwen templates) or switch thinking on/off via
`chat_template_kwargs`; there is no token *budget*. `models/__init__.py`
`after_a_failed_call` re-asks a cut-off reply at half the cap — a reasoning
model that spiralled at 20k spirals again at 10k. `settled_answer` turns
thinking off only after two lost replies (`LOST_REPLIES_BEFORE_THINKING_STAYS_OFF
= 2`), i.e. after ~40k wasted tokens per stage visit.

What changed since the last session: llama.cpp **honours a per-request
`reasoning_budget_tokens` (and `reasoning_budget_message`) since build b9982**
(server changelog, PR #23116), on top of the `--reasoning-budget N` launch flag
that has existed since #13771. N.1 ("per-request thinking budget if the server
honours one") is therefore implementable today; it needs only a `/props`
version check. See AX.

#### I2 (QUALITY, critical): the defect-fix loop does not converge on a complex product ✓

*Plan:* [AY](improvement-plan.md#plan-ay), [BC](improvement-plan.md#plan-bc), [BI](improvement-plan.md#plan-bi)

25 `defect_fix_*` stages consumed 2,255 of the run's 2,593 model calls (87%)
and 144M of its 160M input tokens. Each stage name aggregates up to
`MAX_REMEDIATION_ATTEMPTS` restarts × `MODEL_CALLS_PER_STAGE = 40` calls, so a
single defect legitimately costs 100–200 calls at ≈62k input tokens each
before it is "left open". Outcome: 8 of 62 defects fixed. Monitoring §0.2
(06:55 JST) records the behaviour: "one made 123 model calls and 1 edit in 47
minutes, saying 'I have all the information I need' before each further
read; another 118 tool calls and none."

Root causes visible in the code and the record:

1. **The fix target is not localised before the model is asked.** The fast
   path (`graph/rewritten_fixes.py`) names files from `affected_files` and
   regexes over the failure text (`files_to_fix`), then rewrites up to 4 whole
   files with 60k chars of project memory each. When no file can be named, or
   the rewrite does not make the defect's tests pass, the agent loop takes
   over with the full tool set and a 40-call budget — the expensive path is the
   fallback for exactly the defects the cheap path could not place.
2. **Fixes are measured only at the end of the stage.** `_fix_one` runs
   `engineering.after_a_fix` once, after the stage; inside the loop the model
   runs tests itself (`run_terminal_command`) with no harness-enforced
   "run the defect's own test after every write".
3. **Candidate fixes (Agentless-style `fix_by_candidates`) exist but are gated
   on a judgement model** (`_fixed_by_rewriting`: `judgement_model is not
   model`), so a local-only run never gets best-of-N selection — the one
   technique that is cheapest on a local server (N short rewrites ≪ one 40-call
   loop).
4. **The product's foundation was broken** (login failing → 24 of 30 tests
   fail behind it; two app layouts side by side — monitoring §0.2 "Still
   open"). Root-cause clustering (L.1) reduces the count, but a file-level fix
   cannot repair a layout/plan incoherence; that is a planning defect
   (see I5).

#### I3 (EFFICIENCY, high): reading is still half of the loop's work ✓

*Plan:* [AY](improvement-plan.md#plan-ay), [BC](improvement-plan.md#plan-bc), [BA](improvement-plan.md#plan-ba), [BJ](improvement-plan.md#plan-bj)

`redundant_read_rate = 0.47`, `identical_call_rate = 0.12`, `tool_calls =
4,411`, `layer_memory_pointer = 774`, `layer_read_held_back = 170`,
`layer_tool_withheld = 158`. The project memory already hands every stage
the project at its start (`agents/project_memory.py`), and reads of held
files are answered with a pointer — but **each pointer answer still costs a
model call** (≈62k-token prefill + a reply). The guards stop the loop after
3/8/12 repeats; by then 3–12 calls are gone. Two consequences:

- A local model that keeps re-reading is not "finding something out"; it is
  stalling on a decision. The cheaper response to a repeated read is to end
  the turn and ask for the answer (what `settled_answer` does at 12), or
  better, to never offer a `read_file` tool in a stage whose project is
  already in its memory (fast fix stages: the files are in the request).
- **Every tool-list change invalidates the whole prompt cache on llama.cpp.**
  Tools are rendered into the system prompt by the chat template, so
  withholding a tool (158 times this run) or restoring it changes the first
  bytes of the prompt; the next call re-prefills the entire 60k context.
  The measured `cached_token_share` of 0.726 is consistent with this: 27% of
  160M = 43.9M uncached tokens.

#### I4 (EFFICIENCY, high): decode, not prefill, is the clock ✓

*Plan:* [AX](improvement-plan.md#plan-ax), [BB](improvement-plan.md#plan-bb), [BD](improvement-plan.md#plan-bd)

Model-busy time ≈ 0.7319 × 1,448.9 = 1,060 min. Output 5.22M tokens at the
~100 tok/s measured on 77c6650e and 3642baf8 ≈ 870 min → **decode is ≈82% of
model time**; the 43.9M uncached input tokens fit in the remaining ≈190 min
(≈3.8k tok/s prefill, plausible for a 3B-active MoE). So on this server the
levers are, in order: (1) tokens *not* generated (lost replies, reasoning
spirals, monolithic JSON plans), (2) calls not made (fix loop, re-reads),
(3) prefill not repeated (cache discipline). Prompt diets (X.4) matter less
than the earlier sessions assumed; they still matter for context rot.

#### I5 (QUALITY, high): one sprint, thirty locked tests, one monolithic specification is the wrong shape for a complex brief ✓

*Plan:* [AZ](improvement-plan.md#plan-az), [BJ](improvement-plan.md#plan-bj)

Fast delivery plans one sprint for ≤20 criteria (`scrum_master.
max_sprints_for_criteria_count`); brief_medium produced 30 locked acceptance
tests and 16+ work orders drafted in one wave from a ~200k-character
specification (`review-findings.md` §G, "spec often ~200k"). After the
wave, 26 of 30 tests failed at once, the test round raised 10–14 defects per
round (L.1 later grouped them to 8), and the fix loop started on a product
whose server/login did not work. The thorough mode's sprints are vertical
slices, but each sprint still carries the full ceremony (lead plan, dispatch,
CI, review, security, advice, milestone) and the whole spec.

Contrast with the pattern every 2026 long-running harness uses: a **walking
skeleton** first (server starts, one page renders, one route round-trips,
the test runner runs — proven before anything else), then **one feature slice
at a time**, each with its own small contract, drafts, compile, unit tests
and the *subset* of acceptance tests it owns; the next slice starts only when
the previous one is green. Context per slice stays small (a slice's spec is
≤15k tokens instead of 65k), defects are few and local, and a fix loop has a
narrow target. Anthropic's long-running-agent guidance (feature list as a
JSON/markdown checklist, one feature per session, mark done only when
verified) and OpenHands/Codex task decomposition are the same idea.

#### I6 (EFFICIENCY, medium): the lead's plan is one 20k-token reply ✓

*Plan:* [BB](improvement-plan.md#plan-bb)

`technical_lead`: 112 calls, 364k output tokens, 12 lost replies — the
largest lost-reply count of any stage. `MilestonePlanOutput` is one structured
answer carrying every work order (title, files, interfaces, steps, edge
cases, test cases, verification, out-of-scope). A 10-order plan is 8–15k
tokens of JSON *after* reasoning; with thinking on it runs into the ceiling.
The specification already moved to "parts" (`specification_parts`); the plan
has not ("two-step lead planning" parked, monitoring §0.5.1). Plan in two
steps — an outline (order titles + files + owner) in one short call, then one
work order per call, several at once — removes the ceiling collisions and
makes each order independently retryable.

#### I7 (EFFICIENCY, medium): parallel mode on a 1-slot server shares one KV cache ✓

*Plan:* [BA](improvement-plan.md#plan-ba)

`HARNESS_MAX_PARALLEL` is already `min(setting, slots)` (AB), so fan-out is 1
on this server. But `defect_fix` batches (`_fixes_run_side_by_side`), parallel
reviews and the drafting pool (`ThreadPoolExecutor`) still interleave
*different conversations* through the single slot; llama.cpp keeps one KV
cache per slot and evicts LRU, so alternating two 60k-token conversations
re-prefills both every time (tutorial #13606: "with more distinct prompts
than slots, eviction forces full reprocessing"). Two remedies, neither
touching the owner's model: run conversation-switching work strictly in
sequence while `slots == 1`, and/or use llama-server's slot save/restore
(`--slots --slot-save-path`, `POST /slots/0?action=save|restore`, ~ms per
op) around each switch. If VRAM allows, 2–3 slots of ~40k each is the better
trade for fast-mode drafting, where many short independent prompts dominate.

#### I8 (EFFICIENCY, medium): one throwaway container per command ✓

*Plan:* [BE](improvement-plan.md#plan-be)

`SANDBOX_EXECUTION_MODE=container` (compose default) starts `docker run --rm
…` for every command (`tools/sandbox.py` ≈L4766). With 4,411 tool calls and
the test runners started hundreds of times, container start-up, cold
node/python caches and Playwright browser launches add minutes to hours of
the 27% non-model time (≈390 min this run; pytest lingering alone cost 300 s
per fix stage before the 21:45 JST fix). A persistent per-run sandbox
container (`docker exec` into one container that lives for the run, same
`--read-only`/caps/limits, workspace mounted once) keeps the isolation and
removes the per-command start. The in-container mode exists but changes the
trust boundary; a per-run container does not.

#### I9 (QUALITY, medium): local-only runs never get the "judgement" tier ✓

*Plan:* [BD](improvement-plan.md#plan-bd)

With `FRONTIER=false`, `judgement_model is model`: every escalation path
(`_the_build_model` after `ESCALATE_AFTER_ATTEMPTS`, `fix_by_candidates`,
the architect and reviews) runs on the same model with the same settings.
Escalation then only buys a fresh conversation. A local deployment can still
have two tiers on one server: the same weights with thinking on vs off
(and a different reasoning budget), or a second GGUF loaded in a second
process. The roles module already supports a separate `JUDGEMENT_*`
endpoint; what is missing is guidance and a profile for the all-local case
(see BD), and the candidate-fix path should not require a *different*
model — three candidates from the same model with different sampling seeds
is the Agentless result.

#### I10 (EFFICIENCY, low): the 40-call budget is per attempt, not per defect ✓

*Plan:* [AY](improvement-plan.md#plan-ay), [BC](improvement-plan.md#plan-bc)

`MODEL_CALLS_PER_STAGE = 40` is re-armed on every restart
(`_restart_on_a_fresh_conversation`, structured-retry restarts, escalation to
the judgement model), so one defect saw 198 calls. AK made budgets survive a
*worker* restart; nothing bounds the sum across attempts of one defect. A
per-defect call ledger (sum over attempts, e.g. 60) with the remainder going
to a whole-file rewrite is cheaper than a fourth 40-call conversation.

#### I11 (TOOLING, medium): the harness cannot observe its own prompt composition per call

*Plan:* [BF](improvement-plan.md#plan-bf)

Transcripts record characters sent and `input_tokens`, but not *which block*
each request's bytes came from (system prompt, tool schemas, project memory,
spec excerpt, conversation). The sessions keep estimating composition from
constants (X.4 ceilings, `MEMORY_SHARE`). A per-request composition record
(block name → chars) in `observability/transcript.py` would turn I3/I4/I7
into measured numbers and make the prefix-cache hypothesis testable
(expected: cache misses correlate with tool-list changes and memory
re-renders).

#### I12 (UI/UX): findings I12.1–I12.12 in §15.2

*Plan:* [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg)

### 15.1 What the 2026 frontier harnesses do about the same problems

Moved to `docs/research-findings.md` Part R1 (tables R1.a and R1.b) on 2026-10-19.

### 15.2 UI/UX audit (fourth pass)

Scope: `langchain-ui/src` (50 files, ~9.5k LOC), the 12 screenshots in
`docs/ui/`, the FastAPI routes in `src/app/server/*.py`, and ledger rows
UI-0/T1-T6/P/S1-S6. Everything DONE in the ledger is not re-proposed.

**What the UI is today.** Routes (`App.tsx:94-108`): `/login`, `/` (intake),
`/runs`, `/runs/:runId`, `/settings`. Shell (`Layout.tsx:31-78`): sticky
glass header, "N need you" pill (`useNeedsYou.ts:29-56`, polls the full
`/runs` list every 30 s), theme toggle, skip link, `aria-current`. Intake
(`Home.tsx`): dropzone + workspace label left; supervision / delivery (with
the measured forecast line :361-367) / models / approvals / six review-gate
checkboxes right; `createRun` then `startRun` as two calls (:81, :117).
Runs (`RunList.tsx`): a real table, URL-held search and status filter,
needs-you rows first, 5 s poll while visible; `OutcomesPanel` after it
(`docs/ui/graphite-runs.png` predates that reorder). Run page
(`RunDashboard.tsx`): a vertical stack of equal-weight cards — action bar
(:517-602) → summary (:607-735) → gate/review panel (:739-750) →
`SteeringBox` (:753) → `SprintSummaryPanel` (:759) → `DeliveryPanel` (:763)
→ the workspace grid (stepper / tabbed centre / `AgentActivity`,
:771-817). WebSocket with ticket auth, resume from `last_sequence`,
backoff, 700 ms coalesced refetch (:231-317); view and selection in the URL
(:82-98). Settings (`Settings.tsx`, 920 lines, one page).

**Keep (it works):** the narration layer (`lib/activity.ts:244-302`,
`AgentActivity.tsx:84-153`), feed ergonomics (pin-to-bottom, "N new
updates", sticky stage headers, "Thinking…" heartbeat), honest cost copy
(`RunDashboard.tsx:677-698`), the gate-deadline sentence (:824-843), one
status map (`lib/status.ts`), the theme system with CI-checked contrast, the
measured forecast on intake, criteria→tests (`DeliveryPanel.tsx:143-163`),
steering's "Read by the run in <stage>" (`SteeringBox.tsx:49-52`).

**What a first-time user sees** (`docs/ui/graphite-run.png`): the H1 is
"Defect Fix 2 10" (title-cased stage id, `activity.ts:148` fallback) over
"Working through this step." After 19 h 2 m: Spend $0.00, Documents 125,
Sprint 1 Failed / re-run ×2 / 4/30 / 23 bugs as unlabeled icons, Delivery 0
of 13 untested. Nothing above the fold says how far along the run is, how
much longer, how many tokens it burned, or whether it is stuck; the steering
composer takes 140 px of prime space; the workspace (stepper/log/feed) is
below the fold at 900 px. `graphite-home.png`: "14 need you" counts every
historical waiting run (`useNeedsYou.ts:40`), so the one signal that
matters is devalued.

#### I12.1 (OWNER, high): no progress, no ETA, no tokens

*Plan:* [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg)
`RunCostSummary.total_tokens/prompt_tokens/completion_tokens`
(`types/index.ts:41-44`) are in the payload and rendered nowhere (grep: zero
`.tsx` uses); a local run reads "$0.00" instead of "not priced"; the
`/runs/outcomes` forecast (`api/index.ts:118`), `RunStage.duration_seconds`
and `SprintSummaryPanel.plannedTotal` (:77) are never combined into
"sprint x of y · stage · elapsed vs typical". `waiting_for_budget` exists
(`types/index.ts:65`) but no budget bar.

#### I12.2 (OWNER, high): gates are not legible

*Plan:* [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg)
`ReviewPanel.tsx:33-56` shows `artifact_id` + `revision` + Download and
asks for download→edit→re-upload (:116-118); `ApprovalGate.tsx:69-74` is a
`max-h-32 <pre>`. The owner approves a specification they cannot read in
place although `fetchArtifactContent` (`api/index.ts:322`) and the
`Markdown`/`ArtifactViewer` components exist.

#### I12.3 (OWNER, high): nothing tells an absent owner

*Plan:* [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg)
Title badge only on the run page (`RunDashboard.tsx:70-76`); no favicon
badge, no `Notification`; gates self-approve at `gate_deadline` with nobody
told (UI-0 open items). For a 6–20 h run this is the largest wasted-hours
risk in the UI.

#### I12.4 (OWNER, medium): decisions and steering are buried

*Plan:* [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg)
Decisions sit third-from-bottom in `DeliveryPanel` titled `DR-1`, toggled
without `aria-expanded` (:202-213); the server already emits a
`review_decision` event (`runs.py:1637`) that the feed does not render.
Steering notes have no history and "for the next stage only" names no
stage (`SteeringBox.tsx:43-56`).

#### I12.5 (OWNER, medium): intake has no pre-flight or review step

*Plan:* [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg)
`Home.tsx:70-124` never reads `/settings` or `/api/health/ready`; `createRun`
can succeed and `startRun` fail, leaving an orphan; `reviewer: "Product
Manager"` is hard-coded (:84). (= UI-S3, open.)

#### I12.6 (DEVELOPER, high): per-stage time/tokens/KPIs exist only on the CLI

*Plan:* [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg)
`scripts/loop/kpi.py:189-225` and `run_timing.py` compute per-stage calls,
tokens, lost replies, redundant reads, model-busy share — from the worker
transcript via `docker compose exec`; no route serves them (`runs.py:486-944`
has `evidence`, `changes`, `steering`, `decisions`, `outcomes`; no `usage`,
`kpi`, `transcript`). `RemediationInfo` (`types/index.ts:32-38`) is sent and
unused; sprint data is regex-parsed from markdown with 10 artifact probes
every 30 s (`SprintSummaryPanel.tsx:55-150`).

#### I12.7 (DEVELOPER, medium): held-back reads and lost replies look like successes in the feed

*Plan:* [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg)
`AgentActivity.tsx:140-143` marks only failed tools; a read refused as
redundant (`kpi.py:34-43` `LAYERS` markers) renders as success. Changes view
is one `<pre>` per commit without per-file navigation (`ChangesPanel.tsx:46-81`)
although `files[]` is sent (`api/index.ts:380-385`). No replay/scrubber
(rewind is a `<select>`, `RunDashboard.tsx:565-585`).

#### I12.8 (OPERATOR, high): no model-server surface

*Plan:* [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg)
`/api/health/models` is admin-only and triggers billable calls
(`api.py:257-263`); `loop.sh ready`'s `/props` probe (`model_ready.py:50-69`:
slots, context, model, quant) reaches no screen; two runs can be started on a
one-slot server with no "waits for run X" notice; nothing shows tok/s,
model-busy share, or the last call's input vs the server context (the
condition behind lost replies, I1).

#### I12.9 (DESIGN, medium): hierarchy inverted, plan not first-class

*Plan:* [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg)
Equal-weight cards; a gate (a request) looks like a sprint summary (a
report). The plan (criteria + sprint goals, `WizardDashboard.tsx:117-135`) is
shown after the fact; mission-control UIs (Claude Code web, Codex cloud,
Devin, Cursor background agents) show task list left, feed centre with a
live checklist, diff right, plan approval before expensive work, a small
actionable inbox, cost/time per step, replay. Parallel specialists
interleave in one scroll (`AgentActivity.tsx:156-168`) though events carry
`stage`.

#### I12.10 (DESIGN, low): visual residue and copy

*Plan:* [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg)
`.glass-card` with `backdrop-filter` and `.gradient-btn` (`index.css:255-275`)
on the header (`Layout.tsx:31`), New Run (`RunList.tsx:134`), Start
(`Home.tsx:293`) and cards; centred hero (`Home.tsx:167-175`); type sizes
`text-[10px]`…`[13px]` below the plan's 12 px floor; the contrast theme
borders every element including `<dt>` labels (`contrast-run.png`); copy
("Workflow Runs", "Write Approval Required", "Artifact:") not in the
product vocabulary.

#### I12.11 (A11Y/PERF, medium): not yet in the ledger

*Plan:* [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg)
Tabs are buttons (`RunDashboard.tsx:783-795`: no `role=tab`, arrow keys,
`aria-selected`); `ActionRow` chevron `opacity-0 group-hover` with no
`group-focus-within` (`AgentActivity.tsx:282`); `aria-live="polite"` on a
5,000-row `role="log"` (`AgentActivity.tsx:423-424`, `LogViewer.tsx:65-66`);
unlabeled rewind `<select>`; WebSocket replay from `last_event_id=0` plus
`/logs` paging on every coalesced refresh deliver history twice and re-sort
the whole map (`RunDashboard.tsx:145,191-195`); four panel polls per 30 s on
top; screenshot blobs without `loading="lazy"` (`DeliveryPanel.tsx:59-88`);
`backdrop-filter` on the sticky header over a scrolling feed.

#### I12.12 (HOUSEKEEPING): regenerate `docs/ui/*-runs.png`; `vite.config.ts:11`

*Plan:* [Part 19](improvement-plan.md#plan-part-19), [BG](improvement-plan.md#plan-bg)
proxies :8001 while compose exposes :8000; dead `wizardData.ts`,
`DynamicWorkflowUI.tsx`, `App.css`.

### 15.3 Sources

Primary sources are listed in `docs/research-findings.md`
(research report of this session). The llama.cpp facts used in I1/I7 were
verified directly: server release b9982 ("honour per-request
reasoning_budget_tokens / reasoning_budget_message", PR #23116);
`--reasoning-budget` from #13771; PR #25961 (soft/intro budget messages,
open); discussion #13606 (slot save/restore, `-sps`, `cache_prompt`, LRU).
Host evidence: `data/kpi/run-8b0c94df-eff4-47f2-82c8-0ad06b7c5285.json`,
`data/kpi/ledger.csv`, `data/bench/*.json` (33 runs), `docs/HANDOVER.md` §2,
`docs/monitoring-handover.md` §0.2/§0.9.

## 16. Fifth review session — the structural review (2026-10-21, 13:50–14:05 JST)

Owner's question: other than the plans made, what else can be done? Method: the run history
(`monitoring-handover.md`, `HANDOVER.md` §0–§3), the plan's own index (Appendix M) and the code,
read for what the plan never mentions. Plan: Appendix 7.

### 16.1 The shape of the loop (F19)

| Fact | Evidence |
|---|---|
| About 45 runs since 10-10: ~13 completed, 9 failed, ~16 cancelled | MH §0, H §2.3 |
| 137 LF rows in three days: 37 (10-19), 70 (10-20), 30 by 13:45 (10-21); every failure class still produced rows on 10-21 | Appendix M.2 |
| Failure classes (rough counts): environment/install 25, agent not told a fact 22, wrong file or module 18, lost reply/compaction/budget 15, suite-vs-product 13, reader misread 12, orphan/deploy/rewind 12, telemetry wrong 12, UI 8, review over-reach 5 | LF.1–137 |
| Every quality lever built and off: AQ, BB, AY, BI, BJ, M.4, `SHARED_FACTS`, `DECISION_LEDGER` | H L394–396 |
| No clean gate run since 5aadbddd (10-11); stages 2–3 never attempted; brief_high never run; the two-clean-run compare never happened | H L332, L430 |
| Each medium run carried 8–17 deploys and 2–11 rewinds | MH L150, L198, L214–228 |
| brief_medium has no hidden tests; "62/62 suite, 1 of 10 contract lines kept"; "34/34, 59% of code unreached, compose stack not starting" | H L346, MH L214 |
| Fix stages: 229/309, 91/142, 92/113, 110/172 model-minutes | MH L144–233 |
| Output lost at the cap: 35% (8b0c94df), 47% (shakedown), 22% (d48f049e) | RF I1, MH L148, L214 |
| "Neither model nor tool busy": 43–45% of early run time; 138 of 311 min after a rewind | MH L149–150, L218, LF.76 |
| Runs record no harness SHA, no served model id (the transcript stores the client class name), no sampling | `run_kpis.py`, `kpi_ledger.py`, `transcript.py:562` |
| Owner: "13 h for 1.5 sprints not competitive" (10-14); "seems like looping" (10-19); "why didn't the fix loop improve after group 1" (10-19) | MH L287, L146, L144 |

Hidden scores that do exist: web-todo 10/10 routine; notes-api-hono 9/9 four times;
fullstack-bookmarks-py 0/8 once. Whether quality improves across harness versions is unmeasured.

### 16.2 Readers (F20)
LF.43, 92, 104, 108, 109, 127, 129, 130: each a reader misreading one real output, fixed against
that sample; 75 test files hold hand-copied snippets. No harvest, no replay.

### 16.3 Intake (F21)
`product_manager.py:66–68` produces `open_questions` and `evidence_vs_assumptions`;
`workflow.py:4000` excludes `open_questions` from checks; the intake gate shows the document.
`intake-api/` is a CRUD store. `POST /api/runs/preview` numbers criteria only.

### 16.4 Brownfield (F22)
`seeding.py` and `/codebase` seed; `scaffold.py:407` and `custom_setup.py:71` skip setup when a
manifest exists; `change_request` handles a gate's request inside the same run only; all 10
benchmarks greenfield.

### 16.5 Operations (F23)
Manual: `POST /resume` after a host restart; crons re-created after a session restart
(H L412–416); rewinds by checkpoint id (H L405); deploy markers (LF.87/94); two sessions
deploying at once leave `Created` containers (MH L589); the session's usage limit left the loop
idle 7 h (H L940). Notifications browser-only (`lib/notify.ts`). No Postgres/`runs.db` backup.
Gate wait not a KPI.

### 16.6 Product checks, harness health, safety (F24)
Harness CI: pip-audit, bandit, secret scan, image scan (`ci.yml:87–114`); product CI from
`release.py`: none of them; `document_manifest.py:27` allows a README, checks nothing. Harness:
no ruff/mypy/pyright, no Dependabot, CI without `-n` (`ci.yml:39`), 34 skip/xfail, root clutter
(`Test Product Intake/`, `test_file`, `test_symlink -> nonexistent_dir`, `.github/*.docx`).
Sandbox: install category's network unrestricted (`sandbox.py`); fetched text labelled "data,
not instructions" without quarantine (`web_search.py:16`, `docs.py:18`, `mcp_tools.py:27`).

### 16.7 Covered elsewhere, confirmed
Context budgets, fix loop, lessons, communication, progress, code graph, object storage, UI —
Appendix M. Constrained decoding (M.2) is on Part 22's do-not-implement list and is left there.
