
## Appendix 4 (2026-10-19, fourth review session): local models on complex products

Evidence base: `docs/review-findings-wip.md` §15 (findings I1–I12),
`data/kpi/run-8b0c94df….json`, the 33 scored runs in `data/bench/`, and the
web research in §15.1/15.3. Every initiative below states what KPI (W.4) it
moves and by how much, so the W.2 baseline runs can confirm or refute it.
Format per the owner's request: Goal → Evidence → Files → Steps → Tests
(failing-first, named) → Acceptance → Effort → Depends on. Initiatives
continue the lettering from AW: **AX … BI**. Nothing here re-proposes a
DROPPED item.

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
| spend less wall time outside the model | I8 | non-model time −50% | BE |
| give an all-local run two tiers | I9 | escalation buys a different behaviour, not a replay | BD |
| know the model you serve; edit the way it can | tool failures 7.3%, P.1 | tool failures ≤3% | BH |
| verify the hard cases with a rubric, never narration | I2 | second-failure fixes > 0 | BI |
| measure composition per call | I11 | makes the above falsifiable | BF |
| UI/UX | I12 | (Part 19) | BG |

### Part 18 — Initiatives

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
  4. **Per-defect ledger**: total calls across attempts ≤ 60 (configurable);
     when exhausted, record the localisation's hypothesis as the defect's
     diagnosis and leave it open — no fourth conversation.
  5. **Read tool withheld from a fast fix stage whose files are in its
     request** (they are: `fix_request` carries the files and the memory);
     offer `grep` only.
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
  (`digest_of` focus) — target ≤15k tokens of spec per request. (4) Gate: the
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

#### BA. Prefix-cache discipline on a 1-slot server — P1

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
  withholding becomes a refusal + turn end. (3) Serialise interleaving when
  slots == 1. (4) Slot save/restore when available (advisory to the owner:
  `--slots --slot-save-path /path`; 2–3 slots of ~40k if VRAM allows, for
  the drafting pool). (5) Advise `--cache-reuse 256` for the compaction case.
- **Tests.** `tests/test_a_withheld_tool_does_not_change_the_tool_list.py`
  (fails on old code), `tests/test_fix_batches_run_in_sequence_on_one_slot.py`.
- **Acceptance.** `cached_token_share` 0.73 → ≥ 0.85 on brief_medium;
  effective input tokens −40%.
- **Effort.** M.  **Depends on.** BF.

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

#### BD. Two tiers from one local server (and a model recommendation to the owner) — P1

- **Goal.** An all-local run escalates to a *different behaviour*: the same
  weights with a larger reasoning budget (AX) and lower temperature, or a
  second model process when the owner runs one.
- **Evidence.** I9; HANDOVER §2 notes qwen cloud quota exhausted, so the
  local tier is the real one.
- **Files.** `src/app/models/roles.py` (judgement profile = default endpoint +
  `JUDGEMENT_THINKING_BUDGET`, `JUDGEMENT_SEED`), settings UI (profile
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

#### BE. One sandbox container per run — P2

- **Goal.** Command start-up cost paid once per run, same isolation.
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
- **Effort.** M.  **Depends on.** —.

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

#### BH. Model registry: parser, template, sampling, thinking and edit format per model family, measured by `fitness` — P1

- **Goal.** The harness knows, per served model, which tool-call protocol the
  server parses (hermes / qwen3_coder XML / mistral / glm / harmony), which
  thinking switch and budget it honours, its recommended sampling per mode,
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

#### BG. UI/UX — see Part 19.

### Part 19 — UI/UX (fourth pass): from a status page to a control room

Evidence: §15.2 (I12.1–I12.12). Effort S ≤ 1 day, M 2–4 days, L ≥ 1 week.
"Backend" names the 15.5 enabler or the new route an item needs. Items refine
or pull forward the open UI-S/UI-0/UI-P rows; none duplicates a DONE row.

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

#### BG.2 Needs-you inbox + notifications — P1, M, no backend (completes UI-0, UI-S1)
- Dropdown with one actionable row per waiting run ("run-8b0c… · Release
  review · approves itself at 09:40", one-tap Approve); count only live runs
  (`useNeedsYou.ts:40`); favicon badge (canvas); opt-in browser
  `Notification` on `waiting_*`, `failed`, `completed` from any page.
- **Tests.** count excludes terminal/dismissed runs; notification requested
  only after opt-in. **Acceptance.** a self-approving gate is never silent.

#### BG.3 Gates as a composer with the artifact inline — P1, M (UI-S4 composer, pulled forward)
- Render the reviewed document in place (`fetchArtifactContent`, `Markdown`/
  `ArtifactViewer`), revision diff when `revision > 1` (artifact versions
  endpoint, 15.5), comment box, approve / request changes / skip as the
  composer; steering folded into the same composer with the upcoming stage
  named and the note echoed in the feed when `applied_stage` is set.
- **Files.** `ReviewPanel.tsx`, `ApprovalGate.tsx`, `SteeringBox.tsx`.
- **Acceptance.** no gate asks for download→edit→re-upload.

#### BG.4 Rail / work area / ledger layout with real tabs — P1, L (= UI-S4 layout)
- Left rail: run identity, progress strip (BG.1), stage stepper with
  per-stage time (+ tokens once `/usage` exists), newest-commit chip from
  `/changes` ("3 files · +120/−8"); centre: tabs (Activity / Changes / Log /
  Artifacts / Audit) with `role=tablist` + arrow keys; right: the criteria
  ledger (Delivery) and decisions; gates render as a banner above the work
  area. Collapse steering to a one-line "Steer…" until BG.3 lands.
- **Acceptance.** everything actionable visible at 1366×768 without scroll;
  axe ≤ 5 per theme kept.

#### BG.5 Model-server surface — P1, S UI + S backend (refines UI-S5)
- New read-only `GET /api/health/server` returning the cached `/props` probe
  (model, quant, slots, context as started, last probe time, which run holds
  the slot) — no model call. Header dot + tooltip; Settings → Models first
  (tabs: Models / Appearance / Runs / Lessons / Account) with a "Test call"
  button; intake and run page say "waits for run X to free the model" when
  slots = 1 and another run is `running`.
- **Files.** `src/app/models/server_profile.py`, `src/app/server/api.py`,
  `Settings.tsx`, `Layout.tsx`, `Home.tsx`.

#### BG.6 Fix-loop and sprint data from structured endpoints — P1, S UI + S backend (new row)
- Render `RemediationInfo` ("Fix attempt 2 of 3 · 23 defects, 9 open · tests
  4/30 → 9/30") while `current_stage` matches `defect_fix*`/`test_round*`;
  label the sprint-row icons; replace `parseSummary` with
  `GET /runs/{id}/sprints` (the engine renders the summary — emit the JSON
  it is rendered from).

#### BG.7 Audit tab — P2, M UI (refines UI-S6; pull the per-run half forward)
- Stage × (wall, model-busy, calls, in/out/cached tokens, lost replies,
  redundant reads, tool failures) from `/usage` + `/kpi` (15.5), worst cell
  per column highlighted; "Download transcript" beside "Handover pack"
  (`GET /runs/{id}/transcript`); "Open in transcript" per feed row. This is
  the UI for AX/AY/BA/BF's acceptance numbers.

#### BG.8 Feed: live classification and lanes — P2, S, no backend (new)
- Classify tool results with the `LAYERS` markers (shared constant): muted
  "held back: already read", "reply cut off" chips; lane chips "backend ·
  frontend · testing" filtering by the event's `stage` prefix; render
  `review_decision` events in order ("chose FastAPI because …").

#### BG.9 Changes per file + criterion link — P2, M (= UI-S4 Changes, extended)
- File tree per commit, collapsible hunks, syntax colouring; link from a
  criterion's first passing test to the commit (commit↔criterion mapping
  from the suite result timestamps, S backend).

#### BG.10 Plan-first intake with pre-flight — P2, L (= UI-S3)
- Brief as text and/or files; pre-flight card from `/health/ready` +
  `/settings` ("Build model … 1 slot, 126 k context — ready"); review step
  showing the criteria ledger as "not yet" rows and the slice plan (AZ)
  before Start; one `POST /runs/start`.

#### BG.11 Copy and stage names from the graph — P2, S (= UI-S4 open)
- `STAGE_COPY` generated from the graph's node list so no H1 renders a raw
  stage id; product vocabulary (brief, build, run, gate) across screens.

#### BG.12 Visual residue — P2, S (refines UI-T5)
- Remove `.glass-card`/`backdrop-filter`/`.gradient-btn`/hero; type scale
  12 px floor; contrast theme borders only interactive/container elements;
  every number labelled with its source.

#### BG.13 Accessibility and polling — P2, S
- Real tabs; `group-focus-within` on hover-only affordances;
  `aria-expanded` on disclosure rows; `aria-live` off on the log with a
  separate live region for `agent_message` headlines and status; label the
  rewind control; `/events?since` on reconnect only and no `/logs` paging
  after replay; one `/runs/{id}/summary` aggregate replacing four panel
  polls; `loading="lazy"` on screenshot thumbnails.

#### BG.14 Timeline scrubber / replay — P3, M, no backend (new)
- Stage ticks, gate markers, steering notes, rewind points above the feed;
  clicking scrolls the feed and filters Changes to that moment.

#### BG.15 Context pressure and throughput — P3, S UI (refines UI-S6)
- "Last call used 94 k of 126 k context" (red > 90%), output tok/s sparkline
  over the last hour, "model busy 71% of the last 10 min" in the rail — needs
  per-call fields in `/usage`.

#### BG.16 Command palette, shortcuts, cross-run compare — P3, M (= UI-S1, UI-S6)

**Housekeeping.** Regenerate `docs/ui/*-runs.png`; `vite.config.ts:11` →
:8000; delete `wizardData.ts`, `DynamicWorkflowUI.tsx`, `App.css`;
`Home.tsx:84` reviewer hard-code.

### Part 20 — Implementation sequence

| wave | items | gate |
|---|---|---|
| 0 (1 week) | BF, AX, BC | brief_medium KPI: lost replies ≤5, identical calls ≤5% |
| 1 (1–2 weeks) | AY, BB, BD, BH | fix ratio ≥0.5, lead lost replies 0, tool failures ≤3% |
| 2 (2–3 weeks) | AZ, BA, BG.1–BG.6 | brief_medium completes ≤8 h, cache ≥0.85 |
| 3 | BE, BI, BG.7–BG.16 | non-model share ≤15% |

### Appendix 4 rows (Implementation Progress Ledger continuation)

| Item | Priority | Status | Notes |
|---|---|---|---|
| AX reasoning budget per role | P0 | NOT STARTED | needs server build ≥ b9982 for per-request; else advisory |
| AY bounded fix cycle | P0 | NOT STARTED | |
| AZ skeleton + slices | P0 | NOT STARTED | after AY |
| BA prefix-cache discipline | P1 | NOT STARTED | after BF |
| BB lead plans in parts | P1 | NOT STARTED | |
| BC stalls end one call earlier | P1 | NOT STARTED | |
| BD two local tiers + model advice | P1 | NOT STARTED | owner's A/B |
| BE one container per run | P2 | NOT STARTED | |
| BF prompt composition record | P1 | NOT STARTED | first |
| BH model registry + measured edit preference | P1 | NOT STARTED | extends `fitness` |
| BI rubric-graded candidates | P2 | NOT STARTED | after AY |
| BG.1 progress/tokens in summary | P1 | NOT STARTED | S, no backend |
| BG.2 needs-you inbox + notifications | P1 | NOT STARTED | completes UI-0/S1 |
| BG.3 gates as composer, artifact inline | P1 | NOT STARTED | UI-S4 pulled forward |
| BG.4 rail/work-area/ledger + real tabs | P1 | NOT STARTED | = UI-S4 layout |
| BG.5 model-server surface | P1 | NOT STARTED | new `GET /api/health/server` |
| BG.6 fix-loop + sprints structured | P1 | NOT STARTED | new `/runs/{id}/sprints` |
| BG.7 Audit tab | P2 | NOT STARTED | needs `/usage`, `/kpi` |
| BG.8–BG.13 feed, changes, intake, copy, visual, a11y | P2 | NOT STARTED | |
| BG.14–BG.16 replay, pressure, palette/compare | P3 | NOT STARTED | |
