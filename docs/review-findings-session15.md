
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

Model-busy time ≈ 0.7319 × 1,448.9 = 1,060 min. Output 5.22M tokens at the
~100 tok/s measured on 77c6650e and 3642baf8 ≈ 870 min → **decode is ≈82% of
model time**; the 43.9M uncached input tokens fit in the remaining ≈190 min
(≈3.8k tok/s prefill, plausible for a 3B-active MoE). So on this server the
levers are, in order: (1) tokens *not* generated (lost replies, reasoning
spirals, monolithic JSON plans), (2) calls not made (fix loop, re-reads),
(3) prefill not repeated (cache discipline). Prompt diets (X.4) matter less
than the earlier sessions assumed; they still matter for context rot.

#### I5 (QUALITY, high): one sprint, thirty locked tests, one monolithic specification is the wrong shape for a complex brief ✓

Fast delivery plans one sprint for ≤20 criteria (`scrum_master.
max_sprints_for_criteria_count`); brief_medium produced 30 locked acceptance
tests and 16+ work orders drafted in one wave from a ~200k-character
specification (`review-findings-wip.md` §G, "spec often ~200k"). After the
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

`MODEL_CALLS_PER_STAGE = 40` is re-armed on every restart
(`_restart_on_a_fresh_conversation`, structured-retry restarts, escalation to
the judgement model), so one defect saw 198 calls. AK made budgets survive a
*worker* restart; nothing bounds the sum across attempts of one defect. A
per-defect call ledger (sum over attempts, e.g. 60) with the remainder going
to a whole-file rewrite is cheaper than a fourth 40-call conversation.

#### I11 (TOOLING, medium): the harness cannot observe its own prompt composition per call

Transcripts record characters sent and `input_tokens`, but not *which block*
each request's bytes came from (system prompt, tool schemas, project memory,
spec excerpt, conversation). The sessions keep estimating composition from
constants (X.4 ceilings, `MEMORY_SHARE`). A per-request composition record
(block name → chars) in `observability/transcript.py` would turn I3/I4/I7
into measured numbers and make the prefix-cache hypothesis testable
(expected: cache misses correlate with tool-list changes and memory
re-renders).

#### I12 (UI/UX): findings I12.1–I12.12 in §15.2

### 15.1 What the 2026 frontier harnesses do about the same problems

From the web research of this session (full report with ~95 primary sources:
`docs/research-frontier-harnesses-2026.md`). Only techniques that bear on a
finding above are listed; each names the harness or paper it comes from.

| finding | technique in the field | source | what it means here |
|---|---|---|---|
| I1 lost replies | Thinking per role and per turn, **bounded** (`--reasoning-budget`, per-request `reasoning_budget_tokens`); gpt-oss low/medium/high = 37/53/61 SWE-bench Verified, so effort is a real dial; Aider's Qwen3 run with default thinking scored *lowest* (49.8%) with 58 malformed outputs and ~3× the cost; Kimi K2.5 ran Terminal-Bench non-thinking | llama.cpp server README; HF cards; aider.chat/2025/05/08/qwen3 | AX: budget by role; thinking off for routine edit loops, on and bounded for architect/reviews/repair |
| I2 fix loop | Repair gains come in the first 2–3 attempts, then decay 60–80% ("Debugging Decay Index"; "How Many Tries"; "Is Three the Magic Number"); fresh-context restarts at computed points beat continued debugging (Llama 3.1 8B 72.6→82.8%); parallel rollouts + verifier selection lift a 32B model Pass@1 34→51% hybrid Best@26 (R2E-Gym), Qwen3-Coder-30B-A3B Best@16 39.6→54.2 with repo-grounded rubrics (Agentic Rubrics); Agentless-style localise→repair→validate | arXiv papers cited in the report §9, §4 | AY: ≤3 in-context repairs, then restart with failure output; k=2–4 short candidates selected by the defect's tests; localisation before repair |
| I2 / I5 foundation | Anthropic's long-running-agent harness: initializer writes `init.sh`, a progress file and a **JSON feature list** (`passes:false`), every later session does env check + smoke test, implements **one feature**, verifies end-to-end (browser), commits; only the verifier flips `passes`; Terminal-Bench failure taxonomy: "command not found"/PATH is the largest failure class (24%), premature termination and step repetition are named classes | anthropic.com/engineering/effective-harnesses-for-long-running-agents; arXiv 2601.11868 | AZ: walking skeleton + slices; the locked suite is the JSON ledger; skeleton proof = the session-start ritual |
| I3 re-reads, I7 cache | Prefix caching needs: tools constant and ordered, static system prompt, dynamic state at the *end*, append-only transcript, canonical JSON; Claude Code splits its system prompt into a static cacheable prefix and a dynamic tail; llama.cpp `--cache-reuse 256`, `id_slot` pinning, `--slot-save-path` save/restore (ms), LRU eviction forces full reprocessing | platform.claude.com prompt-caching; arXiv 2609.00006; llama.cpp README + discussion #13606 | BA |
| I3 tools | Minimal flat tool set (3–6), MCP off for local models, `parallel_tool_calls=false`, one action per turn for ≤35B models; mini-SWE-agent (bash only) is the top SWE-bench Pro public scaffold; Factory Droid's +15 pts over Claude Code at fixed model came from minimal tools, simplified schemas, model-specific scaffolding, a plan tool, short timeouts | github.com/SWE-agent/mini-swe-agent; factory.com/news/terminal-bench; kilo.ai docs | AY step 5, BH |
| I4 decode cost | Native MTP where the model ships it (Qwen3.6-35B-A3B has MTP heads), n-gram speculation on whole-file-edit turns (output copies input), flash attention on, KV q8_0 safe for Qwen (KL 0.039) but not Gemma | vLLM/llama.cpp docs; localbench KL study 2026-04 | advisory to the owner (BD) — the harness only measures |
| I5 context | NoLiMa/RULER/Context Rot: effective context of open models is a fraction of the advertised window (Qwen3-30B-A3B RULER effective 64K; focused ~300-token inputs beat 113K inputs on every model); compaction helps small models (ACON −26–54% tokens, up to +46% task gain) | adobe-research/NoLiMa; NVIDIA RULER; Chroma 2025-07 | AZ: ≤24–32K live context per turn by design, not by compaction |
| I6 plan JSON | Codex and Claude Code keep user/work-order text verbatim and summarise only trajectories; schema-constrained artifacts with a short `rationale` field first do not lose reasoning (.txt rebuttal) | gist osolmaz; blog.dottxt.ai | BB: one order per call, schema-constrained |
| I9 tiers | Cognition "smart friend": a cheap primary forks to a stronger model for hard moments; mini-SWE roulette: alternating two models beat either alone (66.6%) | cognition.com/blog/multi-agents-working; swebench.com roulette | BD |
| edit format | Aider: `whole` 100% well-formed vs `diff` 92–95% on Qwen3-235B; lenient matching with fallbacks ≈9× fewer edit errors; architect/editor split lifts every model (+3–5 pts) | aider.chat edit-formats, unified-diffs, architect | BH: measure well-formed rate per model, choose whole-file below ~300 lines |
| model registry | vLLM/llama.cpp need the family's tool-call parser/template (hermes, qwen3_coder XML, mistral, glm47, openai-harmony) and sampling per mode; "protocol adherence isn't guaranteed" | docs.vllm.ai tool_calling; qwen.readthedocs.io | BH |
| verification | Deterministic gates beat self-assessment (Stop hooks, `/goal`, Hermes verify-on-stop); Playwright accessibility snapshots instead of screenshots; mutation testing: top agents detect <40% of realistic mutants | code.claude.com docs; playwright-mcp; SWE-Mutation 2026 | already in the harness (locked suite, AF mutation probe); keep |

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
`RunCostSummary.total_tokens/prompt_tokens/completion_tokens`
(`types/index.ts:41-44`) are in the payload and rendered nowhere (grep: zero
`.tsx` uses); a local run reads "$0.00" instead of "not priced"; the
`/runs/outcomes` forecast (`api/index.ts:118`), `RunStage.duration_seconds`
and `SprintSummaryPanel.plannedTotal` (:77) are never combined into
"sprint x of y · stage · elapsed vs typical". `waiting_for_budget` exists
(`types/index.ts:65`) but no budget bar.

#### I12.2 (OWNER, high): gates are not legible
`ReviewPanel.tsx:33-56` shows `artifact_id` + `revision` + Download and
asks for download→edit→re-upload (:116-118); `ApprovalGate.tsx:69-74` is a
`max-h-32 <pre>`. The owner approves a specification they cannot read in
place although `fetchArtifactContent` (`api/index.ts:322`) and the
`Markdown`/`ArtifactViewer` components exist.

#### I12.3 (OWNER, high): nothing tells an absent owner
Title badge only on the run page (`RunDashboard.tsx:70-76`); no favicon
badge, no `Notification`; gates self-approve at `gate_deadline` with nobody
told (UI-0 open items). For a 6–20 h run this is the largest wasted-hours
risk in the UI.

#### I12.4 (OWNER, medium): decisions and steering are buried
Decisions sit third-from-bottom in `DeliveryPanel` titled `DR-1`, toggled
without `aria-expanded` (:202-213); the server already emits a
`review_decision` event (`runs.py:1637`) that the feed does not render.
Steering notes have no history and "for the next stage only" names no
stage (`SteeringBox.tsx:43-56`).

#### I12.5 (OWNER, medium): intake has no pre-flight or review step
`Home.tsx:70-124` never reads `/settings` or `/api/health/ready`; `createRun`
can succeed and `startRun` fail, leaving an orphan; `reviewer: "Product
Manager"` is hard-coded (:84). (= UI-S3, open.)

#### I12.6 (DEVELOPER, high): per-stage time/tokens/KPIs exist only on the CLI
`scripts/loop/kpi.py:189-225` and `run_timing.py` compute per-stage calls,
tokens, lost replies, redundant reads, model-busy share — from the worker
transcript via `docker compose exec`; no route serves them (`runs.py:486-944`
has `evidence`, `changes`, `steering`, `decisions`, `outcomes`; no `usage`,
`kpi`, `transcript`). `RemediationInfo` (`types/index.ts:32-38`) is sent and
unused; sprint data is regex-parsed from markdown with 10 artifact probes
every 30 s (`SprintSummaryPanel.tsx:55-150`).

#### I12.7 (DEVELOPER, medium): held-back reads and lost replies look like successes in the feed
`AgentActivity.tsx:140-143` marks only failed tools; a read refused as
redundant (`kpi.py:34-43` `LAYERS` markers) renders as success. Changes view
is one `<pre>` per commit without per-file navigation (`ChangesPanel.tsx:46-81`)
although `files[]` is sent (`api/index.ts:380-385`). No replay/scrubber
(rewind is a `<select>`, `RunDashboard.tsx:565-585`).

#### I12.8 (OPERATOR, high): no model-server surface
`/api/health/models` is admin-only and triggers billable calls
(`api.py:257-263`); `loop.sh ready`'s `/props` probe (`model_ready.py:50-69`:
slots, context, model, quant) reaches no screen; two runs can be started on a
one-slot server with no "waits for run X" notice; nothing shows tok/s,
model-busy share, or the last call's input vs the server context (the
condition behind lost replies, I1).

#### I12.9 (DESIGN, medium): hierarchy inverted, plan not first-class
Equal-weight cards; a gate (a request) looks like a sprint summary (a
report). The plan (criteria + sprint goals, `WizardDashboard.tsx:117-135`) is
shown after the fact; mission-control UIs (Claude Code web, Codex cloud,
Devin, Cursor background agents) show task list left, feed centre with a
live checklist, diff right, plan approval before expensive work, a small
actionable inbox, cost/time per step, replay. Parallel specialists
interleave in one scroll (`AgentActivity.tsx:156-168`) though events carry
`stage`.

#### I12.10 (DESIGN, low): visual residue and copy
`.glass-card` with `backdrop-filter` and `.gradient-btn` (`index.css:255-275`)
on the header (`Layout.tsx:31`), New Run (`RunList.tsx:134`), Start
(`Home.tsx:293`) and cards; centred hero (`Home.tsx:167-175`); type sizes
`text-[10px]`…`[13px]` below the plan's 12 px floor; the contrast theme
borders every element including `<dt>` labels (`contrast-run.png`); copy
("Workflow Runs", "Write Approval Required", "Artifact:") not in the
product vocabulary.

#### I12.11 (A11Y/PERF, medium): not yet in the ledger
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
proxies :8001 while compose exposes :8000; dead `wizardData.ts`,
`DynamicWorkflowUI.tsx`, `App.css`.

### 15.3 Sources

Primary sources are listed in `docs/research-frontier-harnesses-2026.md`
(research report of this session). The llama.cpp facts used in I1/I7 were
verified directly: server release b9982 ("honour per-request
reasoning_budget_tokens / reasoning_budget_message", PR #23116);
`--reasoning-budget` from #13771; PR #25961 (soft/intro budget messages,
open); discussion #13606 (slot save/restore, `-sps`, `cache_prompt`, LRU).
Host evidence: `data/kpi/run-8b0c94df-eff4-47f2-82c8-0ad06b7c5285.json`,
`data/kpi/ledger.csv`, `data/bench/*.json` (33 runs), `docs/HANDOVER.md` §2,
`docs/monitoring-handover.md` §0.2/§0.9.
