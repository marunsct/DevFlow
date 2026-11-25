# What is being measured (the one copy)


**2026-11-16 (LR.65, launch review): the "Being measured" batch is concluded.** Its 13 checks (NAMED_TEST_REWRITE,
TESTS_ONLY_WRITES, MUTATION_TEST_RETENTION, CONTRACT_LINE_COVERAGE, CONTRACT_PROBE_AT_LOCK, CONTRACT_UNREAD_LINES_AT_REVIEW,
CONTRACT_NON_NUMERIC_IDS, CONTRACT_PROBE_WITH_A_RECORD, CONTRACT_PROBE_WITH_A_BAD_BODY, NAMING_FINDING_BEFORE_DEFERRAL,
SPEC_DRY_RUN, ORDER_PROBE, IDS_READ_WITHOUT_A_CREATE) ran on in every run since release candidate 7 and through the
measurement runs of 11-16; they check what a suite proves, so by the switch policy they are built in and keep no switch.
The groups still switchable are cost and efficiency (Context and cost, Efficiency) and the two measured gates (Setup
scope M6, Review gates M7).

Owner 2026-11-07 17:1x JST: one document for every change under measurement, so no measurement is missed on or off.
**This file is the only list.** STATE, the handovers, the status board and the plan point here and do not repeat it.
Update it in the same commit as any switch change, deploy that turns a switch on or off, or verdict.

Rules (owner 2026-11-05 and 2026-11-07):
- Bug fixes and quality fixes need no measurement: always on, no switch, recorded as a row in `docs/archive/plans/fix-log.md`.
- A change whose value is in doubt is built behind a switch and measured here: two runs per family with it on and
  two with it off, each on one harness SHA (`loop.sh kpi`, then `kpi_ledger.py arms <sha-a> <sha-b> <family>`).
  A mixed-version run counts for neither arm.
- Verdict: kept (moves to `BUILT_IN`, switch removed) when no hidden or quality score falls and its target KPI
  moves; parked (off, kept in code) when nothing moves; removed when it hurts.
- Every audit reads this table and says which arm the live runs are in.
- How to run an arm (LF.708, 11-08): on one deployed SHA, start the off arm with `SWITCHES_OFF="NAME" loop.sh bench <family>`
  (or `SWITCHES_ON` for a switch that ships off) and the other arm without; compare with
  `python3 scripts/loop/kpi_ledger.py switch-arms data/kpi/ledger.csv <sha> NAME <family>`. No deploy between the arms.

## Every switch (generated)

<!-- switches:generated -->
Written by `loop.sh measuring` from 505 scored runs in the ledger. On and off counts are over every run, across commits: a verdict here says where to look, not that a pair on one commit was run.

| Switch | Group | Default | Runs on | Fired | Runs off | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| `PREMIUM_CHANGE_REQUESTS` | Bundles | on | 0 | no signal | 0 | not measured: needs 2 more on and 2 more off |
| `PREMIUM_DEEP_VERIFICATION` | Bundles | on | 0 | no signal | 0 | not measured: needs 2 more on and 2 more off |
| `PREMIUM_MODEL_TUNING` | Bundles | on | 0 | no signal | 0 | not measured: needs 2 more on and 2 more off |
| `PREMIUM_PROJECT_INTELLIGENCE` | Bundles | on | 0 | no signal | 0 | not measured: needs 2 more on and 2 more off |
| `BATCH_ACCEPTANCE_AUTHOR` | Context and cost | off | 1 | no signal | 112 | not measured: needs 1 more on and 0 more off |
| `LEAD_REPLAN_REQUEST_SMALLER` | Context and cost | off | 3 | 3 | 50 | measured: hidden 1.00 on / 0.96 off; minutes 118.60 / 89.45 |
| `LEAN_PROMPTS_FOR_STRONG_MODELS` | Context and cost | on | 91 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `LEAN_TOOL_LISTS` | Context and cost | on | 91 | 91 | 0 | not measured: needs 0 more on and 2 more off |
| `OBSERVATION_FOLDING` | Context and cost | on | 112 | no signal | 1 | not measured: needs 0 more on and 1 more off |
| `QA_PROMPT_TRIMMED` | Context and cost | off | 3 | 2 | 50 | measured: hidden 1.00 on / 0.96 off; minutes 118.60 / 89.45 |
| `READS_SIZED_TO_THE_ROOM` | Context and cost | off | 0 | 0 | 0 | not measured: needs 2 more on and 2 more off |
| `REASONING_KEPT_AFTER_AN_ANSWER` | Context and cost | on | 112 | no signal | 1 | not measured: needs 0 more on and 1 more off |
| `REQUEST_BUDGET_FOR_EVERY_STAGE` | Context and cost | off | 0 | 0 | 0 | not measured: needs 2 more on and 2 more off |
| `REVIEWER_SHAPED_PLUGIN_CONTENT` | Context and cost | off | 3 | 3 | 50 | measured: hidden 1.00 on / 0.96 off; minutes 118.60 / 89.45 |
| `SLICED_MEMORY` | Context and cost | on | 91 | 85 | 0 | not measured: needs 0 more on and 2 more off |
| `STABLE_STAGE_PREFIX` | Context and cost | on | 112 | no signal | 1 | not measured: needs 0 more on and 1 more off |
| `CONCURRENT_WRITE_PROBE` | Contract probes | on | 112 | 10 | 1 | not measured: needs 0 more on and 1 more off |
| `EDGE_PROBE` | Contract probes | on | 91 | 22 | 0 | not measured: needs 0 more on and 2 more off |
| `PAGE_PROBE` | Contract probes | on | 91 | 2 | 0 | not measured: needs 0 more on and 2 more off |
| `WRONG_SHAPE_BODY_PROBE` | Contract probes | on | 112 | 21 | 1 | not measured: needs 0 more on and 1 more off |
| `DRAFTING_IN_WAVES` | Drafting order | on | 91 | 72 | 0 | not measured: needs 0 more on and 2 more off |
| `EQUIVALENT_MUTANTS_REMEMBERED` | Efficiency | on | 112 | no signal | 1 | not measured: needs 0 more on and 1 more off |
| `FIX_ORDER_CRITERIA_FIRST` | Efficiency | off | 2 | 2 | 45 | measured: hidden 1.00 on / 0.96 off; minutes 81.35 / 86.66 |
| `FIX_STAGES_THAT_CLOSE_NOTHING` | Efficiency | on | 112 | 16 | 1 | not measured: needs 0 more on and 1 more off |
| `HARNESS_FINDINGS_RECHECKED` | Efficiency | on | 112 | no signal | 1 | not measured: needs 0 more on and 1 more off |
| `LONG_REASONING_BEFORE_A_READ` | Efficiency | on | 0 | 0 | 0 | not measured: needs 2 more on and 2 more off |
| `MUTANT_CHECK_IN_THE_FIX_STAGE` | Efficiency | on | 112 | 28 | 1 | not measured: needs 0 more on and 1 more off |
| `MUTATION_GAPS_BUNDLED` | Efficiency | off | 1 | 0 | 53 | not measured: needs 1 more on and 0 more off |
| `NEAR_GREEN_REPAIR_TO_ROUND` | Efficiency | on | 112 | 0 | 1 | not measured: needs 0 more on and 1 more off |
| `NEAR_GREEN_REPLANNED_ONCE` | Efficiency | on | 48 | 2 | 72 | measured: hidden 0.91 on / 0.88 off; minutes 101.86 / 104.42 |
| `ONE_DESIGN_REVIEW` | Efficiency | on | 112 | 0 | 1 | not measured: needs 0 more on and 1 more off |
| `REPLY_ROOM_SIZED_PER_ROLE` | Efficiency | off | 1 | 1 | 35 | not measured: needs 1 more on and 0 more off |
| `REVIEWS_WITHOUT_REASONING` | Efficiency | on | 117 | no signal | 146 | measured: hidden 0.89 on / 0.98 off; minutes 98.01 / 87.95 |
| `SPRINT_TIME_BUDGET` | Efficiency | on | 112 | 0 | 1 | not measured: needs 0 more on and 1 more off |
| `STABLE_MEMORY_ORDER` | Efficiency | on | 112 | 108 | 1 | not measured: needs 0 more on and 1 more off |
| `SUMMARISE_LATER_WITH_HEADROOM` | Efficiency | off | 3 | 1 | 37 | measured: hidden 0.74 on / 0.97 off; minutes 88.47 / 75.21 |
| `PULL_REQUEST_DELIVERY` | Existing projects | off | 0 | 0 | 0 | not measured: needs 2 more on and 2 more off |
| `INTERFACE_STATES_AS_CRITERIA` | Interface design | off | 0 | 0 | 0 | not measured: needs 2 more on and 2 more off |
| `API_CARDS_FOR_NEWER_RELEASES` | Internet lookups | off | 0 | 0 | 0 | not measured: needs 2 more on and 2 more off |
| `FRAMEWORK_GUIDANCE_FOR_ADVISERS` | Internet lookups | off | 0 | 0 | 0 | not measured: needs 2 more on and 2 more off |
| `WEB_TOOLS_BY_MEASURED_TIER` | Internet lookups | off | 0 | 0 | 0 | not measured: needs 2 more on and 2 more off |
| `WEB_LOOKUP_WHEN_STUCK` | Internet lookups | on | 54 | no signal | 1 | not measured: needs 0 more on and 1 more off |
| `WEB_TOOLS_AFTER_TWO_FAILED_FIXES` | Internet lookups | on | 53 | 11 | 1 | not measured: needs 0 more on and 1 more off |
| `WEB_TOOLS_OFFERED` | Internet lookups | on | 52 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `PRODUCT_PREVIEW` | Product preview | off | 53 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `DIAGNOSE_A_RECURRING_CAUSE` | Recurring causes | on | 91 | 2 | 0 | not measured: needs 0 more on and 2 more off |
| `DESIGN_REVISION_CROSS_CHECKED` | Review gates | on | 112 | 103 | 1 | not measured: needs 0 more on and 1 more off |
| `INTAKE_ASKS_FIRST` | Review gates | on | 91 | 91 | 0 | not measured: needs 0 more on and 2 more off |
| `SPECIALIST_DOMAIN_REVIEW` | Review gates | off | 0 | 0 | 0 | not measured: needs 2 more on and 2 more off |
| `MILESTONE_EVIDENCE_GATE` | Review gates | on | 112 | no signal | 1 | not measured: needs 0 more on and 1 more off |
| `SETUP_SCOPE_GUARD` | Setup scope | on | 112 | no signal | 1 | not measured: needs 0 more on and 1 more off |
| `CONTESTED_TESTS_CONFIRMED` | Suite disputes | off | 2 | 0 | 53 | measured: hidden 1.00 on / 0.96 off; minutes 123.35 / 89.90 |
| `UNIT_TEST_QUARANTINE` | Unit test signal | on | 91 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `CHANGE_REQUEST_RUNS` | bundle PREMIUM_CHANGE_REQUESTS | on | 496 | no signal | 1 | not measured: needs 0 more on and 1 more off |
| `ASK_SPECIFICATION` | bundle PREMIUM_DEEP_VERIFICATION | on | 495 | no signal | 2 | measured: hidden 0.92 on / 0.70 off; minutes 90.41 / 206.75 |
| `ASSUMPTIONS_GATE` | bundle PREMIUM_DEEP_VERIFICATION | on | 495 | 390 | 2 | measured: hidden 0.92 on / 0.70 off; minutes 90.41 / 206.75 |
| `MUTATION_GUIDED_TESTS` | bundle PREMIUM_DEEP_VERIFICATION | on | 489 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `RELEASE_AUDITS` | bundle PREMIUM_DEEP_VERIFICATION | on | 495 | no signal | 2 | measured: hidden 0.92 on / 0.70 off; minutes 90.41 / 206.75 |
| `RELEASE_DOCS_REQUIRED` | bundle PREMIUM_DEEP_VERIFICATION | on | 495 | no signal | 2 | measured: hidden 0.92 on / 0.70 off; minutes 90.41 / 206.75 |
| `SCREENSHOT_RUBRIC` | bundle PREMIUM_DEEP_VERIFICATION | on | 495 | no signal | 2 | measured: hidden 0.92 on / 0.70 off; minutes 90.41 / 206.75 |
| `FIX_STAGE_REPLY_CAP` | bundle PREMIUM_MODEL_TUNING | on | 414 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `GUIDE_ANSWER_IN_SCHEMA` | bundle PREMIUM_MODEL_TUNING | on | 488 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `GUIDE_EXACT_ARGUMENTS` | bundle PREMIUM_MODEL_TUNING | on | 488 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `GUIDE_HEED_REFUSALS` | bundle PREMIUM_MODEL_TUNING | on | 488 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `GUIDE_KEEP_TO_ROLE` | bundle PREMIUM_MODEL_TUNING | on | 488 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `GUIDE_NO_REPETITION` | bundle PREMIUM_MODEL_TUNING | on | 488 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `GUIDE_ONE_PROGRAM_A_COMMAND` | bundle PREMIUM_MODEL_TUNING | on | 488 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `GUIDE_PATHS_AS_GIVEN` | bundle PREMIUM_MODEL_TUNING | on | 488 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `GUIDE_STOP_WHEN_DONE` | bundle PREMIUM_MODEL_TUNING | on | 488 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `MODEL_GUIDANCE` | bundle PREMIUM_MODEL_TUNING | on | 488 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `PLAN_REVIEW_REPLY_CAP` | bundle PREMIUM_MODEL_TUNING | on | 407 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `SALVAGED_PLANNING_THINKING_OFF` | bundle PREMIUM_MODEL_TUNING | on | 231 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `SALVAGED_REPLIES_TURN_THINKING_OFF` | bundle PREMIUM_MODEL_TUNING | on | 407 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `STEERING_AT_THE_TAIL` | bundle PREMIUM_MODEL_TUNING | on | 495 | no signal | 2 | measured: hidden 0.92 on / 0.70 off; minutes 90.41 / 206.75 |
| `STRUCTURED_EXTRACTION` | bundle PREMIUM_MODEL_TUNING | on | 488 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `THINKING_OFF_REPLY_CAP` | bundle PREMIUM_MODEL_TUNING | on | 231 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `BUILDER_FACTS` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 451 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `CANONICAL_MEMORY` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 495 | no signal | 2 | measured: hidden 0.92 on / 0.70 off; minutes 90.41 / 206.75 |
| `CODE_GRAPH_TOOL` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 495 | no signal | 2 | measured: hidden 0.92 on / 0.70 off; minutes 90.41 / 206.75 |
| `DECISION_LEDGER` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 495 | no signal | 2 | measured: hidden 0.92 on / 0.70 off; minutes 90.41 / 206.75 |
| `LESSON_DISTILLER` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 496 | 277 | 1 | not measured: needs 0 more on and 1 more off |
| `NAMING_STANDARD` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 471 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `PROJECT_GRAPH_BUILDERS` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 495 | no signal | 2 | measured: hidden 0.92 on / 0.70 off; minutes 90.41 / 206.75 |
| `PROJECT_GRAPH_FIXES` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 495 | no signal | 2 | measured: hidden 0.92 on / 0.70 off; minutes 90.41 / 206.75 |
| `SHARED_FACTS` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 495 | 377 | 2 | measured: hidden 0.92 on / 0.70 off; minutes 90.41 / 206.75 |
| `STATE_AT_DISPATCH` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 495 | no signal | 2 | measured: hidden 0.92 on / 0.70 off; minutes 90.41 / 206.75 |
| `WHERE_THINGS_STAND` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 495 | 362 | 2 | measured: hidden 0.92 on / 0.70 off; minutes 90.41 / 206.75 |
<!-- /switches:generated -->

## Measurement schedule

Arms run on the two ports in turn; each row's off arm is a run with only that row's switch (or group) off.

| # | Change | Switch / group | State now | Target KPI | On arm runs | Off arm runs | Verdict |
|---|---|---|---|---|---|---|---|
| M1 | 13 verification checks (the "Being measured" batch, LF.582) | group `Being measured` | ON since 11-05 11:55 (RC7) | false acceptances, suite reopens | ~25 (all runs since) | 0 | needs an off arm: 2 runs per family with the group off |
| M2 | Premium bundles (model tuning, project intelligence, deep verification) | `PREMIUM_*` | ON since 10-22 (all-on baseline) | hidden score, model calls, tool failures | 79 | 5-6, early, other harness | `effects gate` calls 10 park candidates on 5-6 off runs: too thin - an off arm per bundle on today's SHA before any parking |
| M3 | Context and cost | group `Context and cost` | see `loop.sh switches` | input tokens, cache share | - | - | not started |
| M4 | Efficiency (mutation findings) | group `Efficiency` | see `loop.sh switches` | model calls on mutation defects | - | - | not started |
| M6 | Setup scope: a layered setup stage writes only its framework files, declaration, smoke tests, manifests and test configuration | `SETUP_SCOPE_GUARD` (group `Setup scope`) | OFF (built 11-07 21:0x, LF.686) | setup lines written; hidden score on custom stacks; setup minutes | 0 | falcon 4-9 (all off) | needs on runs: 2 notes-api-falcon runs with it on, on one SHA |
| M7 | Milestone send-back only with evidence: a blocking finding a failing test, criterion or underline shows (harness review G3) | `MILESTONE_EVIDENCE_GATE` (group `Review gates`) | OFF (built 11-07 21:1x, LF.687) | milestone send-backs, minutes per run; hidden score | 0 | every run so far (all off) | needs on runs: 2 per family on one SHA |
| M9 | The acceptance review answers without reasoning first (68-74% of output tokens are reasoning; its own output was all reasoning) | `REVIEWS_WITHOUT_REASONING` (group `Efficiency`) | OFF (built 11-09 10:4x, LF.765) | acceptance-review model minutes; hidden score; false acceptances; suite strength (mutation score, review findings) | on: wordstats-cli 6 (run-aaf136ca, c325856d then e0d2d61e) 7/8, false acceptance, review 0 reasoning chars, ~3 review-minutes, review missed a test's own arithmetic; off: wordstats-cli 7 (run-023f2c45, e0d2d61e, :8888) 8/8, no false acceptance, 358 active min (6 h on miscounted locked tests; DISPUTE_QUOTES_THE_CRITERION on for it alone from 17:06); pair 3 (identical sampling on both ports): on wordstats-cli 10 (run-b572702f) 8/8, no false acceptance, 39 active min, review 0 reasoning chars but one 20k-token reply reasoning in its text; off wordstats-cli 11 (run-5447eb12) 6/8, FALSE ACCEPTANCE (printed case, with reasoning - LF.780), 93 active min; tally 1 false acceptance in 3 on arms, 1 in 3 off arms; pair 4 (LF.780 on): on wordstats-cli 12 (run-9bbbfb2f, :1234) 8/8, no false acceptance, 35 active min (spec said output is lower case: LF.780 fired); off wordstats-cli 13 (run-051cda30) 8/8, no false acceptance, 62 active min vs on 35. TALLY after 4 pairs: on 1 false acceptance in 4 (8/8, 8/8, 8/8, 7/8), off 1 in 4 (8/8, 8/8, 6/8, 8/8); on arms faster in 3 of 4 pairs; swapped pair on :1234: on wordstats-cli 8 (run-19fb2b9f) 8/8, no false acceptance, review 0 reasoning chars; off wordstats-cli 9 (run-bbbf1e3d) 8/8, no false acceptance, 61 active min vs on 36; void before: wordstats-cli 4 (LF.768), wordstats-cli 5 (crashed, LF.770) | M9 on wordstats-cli 4 (run-4c98359a, c46bb201) VOID: the switch did not reach the model (judgement model None; LF.768) - its review reasoned 54-74k characters a reply | needs on/off pairs: 2 runs per port on one SHA (`SWITCHES_ON=REVIEWS_WITHOUT_REASONING` on one run of each pair) |
| M5 | MEASURE_ONCE (reuse an unchanged product's measurement) | `MEASURE_ONCE` (built in) | ON | suite minutes | - | - | LF.676 fixed its skipped own-start check; built in, no arm |
| M10 | A firing signal for every switch: 51 of 58 switches leave no text `switch_firing.SIGNALS` can read, so the gate cannot tell "never acted" from "acted and changed nothing" | `app.observability.switch_firing.SIGNALS` | 7 signalled | switches with a signal | - | - | to build: one signature each, on-by-default switches first |
| M11 | Sampling by mode (LF.774): each call sent its mode's sampling (thinking precise / general, no thinking) | owner setting "Send sampling by mode" (Settings -> Models), off by default | ON for qwen3.6-35b-a3b-mtp (both ports) since 11-09 17:37 JST (owner: same sampling on both ports) | hidden score; malformed tool arguments; replies lost to length; minutes | - | - | needs on/off pairs once the owner turns it on for a model |
| M12 | Reads of files the project memory already holds: flagged above the 5-run mean in 3 runs in a row (L web-todo-react 4 0.33, L notes-api-js 3 0.24 vs 0.09; L tasks-api 13 had 35 pointers, 21 already-read and 17 same-bytes answers in 546 tool results, 14 pointers in one lead re-plan). The stall rule ends each streak at 5 results, but each new visit or plan attempt reads again. Candidate (doubtful, so switched): a stage visit's first pointer ends reading for that visit (`POINTERS_BEFORE_THE_ANSWER` 2 -> 1), against the risk of an answer written before a needed read | to build: switch `ONE_POINTER_ENDS_READING` (group `Efficiency`), off | - | redundant_read_rate, lead-plan minutes; hidden score must not fall | - | - | to build after the RC count, then 2 on / 2 off per family on one SHA |
| M13 | Carried reasoning reset at each answer (LR.52, launch review): an answer ended the stretch the reasoning belongs to, so earlier tool-calling replies lost it at once and the prompt changed from there - calls labelled "stable" carried 90M uncached tokens over 40 runs, against 21.5M for `opening_changed`. Kept, no sent message changes; it costs the reasoning's tokens, read from the cache | built: switch `REASONING_KEPT_AFTER_AN_ANSWER` (group `Context and cost`), off | - | uncached input tokens per call, prompt cache share; hidden score must not fall | - | - | 2 on / 2 off per family on one SHA |
| M14 | Near-green sprints planned again once (LR.53): over 175 past re-plans in 109 runs, after a near-green locked suite (1-2 failing or 90% passing) the first re-plan beat the best in 41 of 57, later ones in 4 of 27 at about 34 active minutes each (931 in all); 21 of 22 such runs scored every hidden test. Not supported by the data: skipping the first re-plan (72% beat). Open: a suite repair that leaves the suite near green going back to the round (19 of 45 gains came from the repair alone, then about 25 more minutes of re-plan) | switch `NEAR_GREEN_REPLANNED_ONCE` (group `Efficiency`), ON from 11-17 (`EXPERIMENTS_ON`, LF.977) | - | firing (`near-green suite is not planned again`); hidden score of runs it fired in; active minutes per sprint | - | - | live M36 runs; off at once if a run it fired in loses a hidden test the re-plan would have found |
| M15a | BATCH_ACCEPTANCE_AUTHOR OFF again 11-17 12:50 (M15's rule, a drastic change): in M37 notes-api-csharp 4 the first batch's writer listed the other batches' criteria as blockers, 12 of 18 were deferred, the run built 6 and the escalation stopped it. Fixed (LF.1013: a batch writer's blockers count only for its own batch); back on after one run of a family shows the whole suite written | `BATCH_ACCEPTANCE_AUTHOR` | OFF | criteria deferred at the lock; tests per criterion | - | - | one run with it on after LF.1013 |
| M15 | The 10 built-but-off switches (Context and cost, Efficiency, Setup scope, Review gates) on together from 11-17 (owner: past runs are the baseline, no new off-runs first). Past data: REVIEWS_WITHOUT_REASONING hidden 0.93 on / 0.96 off, minutes 46 / 134 (11 runs); the rest none | `EXPERIMENTS_ON` (owner 11-17) | ON from the deploy after 11-17 10:00 JST | hidden and quality score per run against the family's runs before; active minutes against the 5-run mean (KPI check) | - | - | off at once, by switch or by group, if a run loses a hidden test or takes 1.5x; the next run of that family verifies |
| M16 | The switches built 11-17 in parallel (owner: on at deploy, past runs the baseline): DESIGN_REVISION_CROSS_CHECKED, STABLE_MEMORY_ORDER, NEAR_GREEN_REPAIR_TO_ROUND, FIX_STAGES_THAT_CLOSE_NOTHING, ONE_DESIGN_REVIEW, SPRINT_TIME_BUDGET, CONCURRENT_WRITE_PROBE, WRONG_SHAPE_BODY_PROBE; each has a firing signal | `EXPERIMENTS_ON` | ON from 11-17 | design escalations per run; fix rounds; active minutes; hidden and quality score; firing per switch | - | - | as M15: off at once on a lost hidden test or 1.5x minutes in a run it fired in |
| M17 | Every stage's memory held to its request's input budget (LF.1274 part 3, review item 3.1): a non-fixer stage whose request and memory are past the target (room for 10 working calls before the first summary, about 75K characters deployed) gets the memory within what the target leaves, long workflow documents as digests of at most 12K. Measured: a medium run's builders, lead, planner, reviews and suite author opened on 157-198K characters, 53-69K of them the specification's digest; small runs open at 95-175K too, and score full hidden marks today, so it is switched (the fixers' budget, both paths, is always on) | `REQUEST_BUDGET_FOR_EVERY_STAGE` (group `Context and cost`) | OFF (built 11-24, LF.1274); off, each stage's `request_budget` record still says what would be cut (`applied` false; `loop.sh effects`) | hidden score and fix rate on a medium run with it on against the failed medium run (17/97); no hidden-score loss on two small runs with it on; summaries a stage and reads of held files per stage | 0 | 0 | measuring: ON for the medium rerun run-c53e7bd2 from 19:16 JST 11-24; it does not change how often a stage is summarised - the summary trigger never counts the memory (`reports/audits/2026-11-24-review-stages-reread-loop.md` 1.7) - so its measure is quality and tokens, not summaries; two small runs still to run |
| M18 | A whole read past the room the request has left is answered with the file's outline (LF.1289, step 3 of `reports/audits/2026-11-24-reading-stages-past-their-room.md`): a `read_file` naming no range, of a file longer than 80 lines, whose numbered text is larger than the room left (the last reply's reported input tokens against the input ceiling, less what the tool results since returned) gets each definition with its lines and "read the lines you need by range"; a range read is never changed. Measured on the earlier medium run: 492 of 2,100 calls (23%) were past the room, and the lead read a file 2.4-12.2 times a visit | `READS_SIZED_TO_THE_ROOM` (group `Context and cost`) | OFF (built 11-24, LF.1289); its answers say "more than this request has room left for" (the firing signal) | on one medium run, after steps 1-2 are deployed: lead whole reads a file at most 1.2, summaries a visit at most 1, calls to a plan under 12, held stages' calls past the input ceiling none; quality must not fall: plans sent back (`work_order_problems`), work orders naming a file or name that does not exist, the sprint's suite result, the hidden score; small families: no answer fires (the guard) | 0 | 0 | stop rule: off for good if the lead's plans are sent back more often with it on, or a stage makes more than three range reads of one file in a row (then reviews/plans in parts for that stage); measuring: ON for the medium rerun run-c53e7bd2 from 23:36 JST 11-24 (sprint 2 testing builder: 121 reads of 27 files, 7 summaries, 1 write in 25 min before it); ON for Medium 3 run-bc3cbd00 from 05:14 JST 11-25 (its sprint 1 suite author: 110 reads of 21 files, 7 summaries, no write in 25 min) |
| M-HK.10 | Product research for the product manager (LF.1305, plan HK.10, doubtful): with the run owner's consent, at most three web searches built from the brief's product type alone, summarised once into at most six cited suggestions the brief does not require; a suggestion the intake puts outside deferred scope is moved there | `PRODUCT_RESEARCH` (group `Internet lookups`) and the run's own consent (`PRODUCT_RESEARCH_CONSENTED`, new-run form) | OFF (built 11-25, LF.1305); firing signal "Comparable products: suggestions the brief does not require" | it cannot be scored by hidden tests (they score the brief): the owner's review of each run's suggestions (`.harness/research/product-research.json`, the `product_research` decision) - useful, sourced, about products of this kind; no added scope: no suggestion in success measures, core workflows, MVP candidates or acceptance criteria, criteria count and sprint count equal to a run of the same brief without it; no private word in a query (the `outbound` records); minutes added at intake under 3 | 0 | 0 | to measure: two consented runs of the medium brief with the switch on, reviewed by the owner at the end-of-run product review against a run without; kept only on the owner's word that the suggestions helped and no scope was added; removed on any query carrying a private word or any suggestion reaching a criterion |
| M19 | HK.7 API cards (LF.1302, `reports/research/2026-11-24-agents-that-work-like-a-team.md` HK.7): a dependency whose installed release line began after the build model's training data ends (`knowledge_cutoff` on the model's capabilities) gets a short card - its installed exports, changelog and migration notes on the names the work uses, its documentation for that release (Context7 pinned to the version) - in the builders' and fixers' requests for the files that use it; at most 3 libraries and 6% of the opening target. Evidence: RustEvo2 +13.5 points after the cutoff, GitChameleon +10 | `API_CARDS_FOR_NEWER_RELEASES` (group `Internet lookups`) | OFF (built 11-25, LF.1302); needs the model's cutoff (settings page, or its card on the next capability fill) - with none it never fires; `.harness/api-cards.json` lists what was flagged | defects whose cause is an API the installed release does not have (missing export, renamed call, removed option) per run; install-to-first-green-build minutes; hidden score held; firing signal "Libraries whose installed release line is newer than this model's training data"; request characters added per builder and fixer | 0 | 0 | measure on the stale-knowledge trap family (plan (e) item 3, owner decision) or a no-pack family whose framework's current major is newer than the model, 2 on / 2 off on one SHA; off for good if a hidden test is lost or 1.5x the family's minutes; parked if trap-family API defects do not fall |
| M20 | HK.9 framework guidance (LF.1303, same report HK.9): the stack's framework's own security and testing guidance for the release the project uses, read once per framework release (Context7 pinned, else its own docs when on the newest line), checked to be about its topic, at most 2,500 characters and labelled 'the brief decides' - to the security and testing specialists before the specification and to the security reviewer | `FRAMEWORK_GUIDANCE_FOR_ADVISERS` (group `Internet lookups`) | OFF (built 11-25, LF.1303) | hidden quality tests (security and testing ones); security review findings later confirmed by a failing test or probe, against findings dismissed; adopted advice that adds a rule the brief does not state (must not rise: the deep review's A.1 rate limit); hidden score held; firing signal "its own guidance, for the release this project uses" | 0 | 0 | 2 on / 2 off on one SHA on two API families with a framework Context7 holds (tasks-api, notes-api-hono); off for good if any hidden test is lost or brief-external rules adopted rise |
| M-HK.11 | HK.11 tools by measured tier (LF.1307, `reports/research/2026-11-24-agents-that-work-like-a-team.md` HK.11): the model diagnosis asks whether, given a file to write against a release newer than its training and a lookup, the model calls it and uses the answer (capability `researches`, `models/research_check.py`); a model that does is offered one `research(question)` tool - the HK.3 lookup, condensed and version-checked, a note and never pages - in place of the web search and page reader (always on); a model that never does is offered no web tool schemas | `WEB_TOOLS_BY_MEASURED_TIER` (group `Internet lookups`) for the removal only | OFF (built 11-25, LF.1307); acts only on a model with a kept verdict (settings page diagnose, or the next run's start) and the run's Internet lookups choice Always | passing model: `research` calls per stage visit (ledger `lookup` records, trigger "research tool") and notes whose named change appears in the next write or closes the next fix; failing model: request characters per stage (tool schemas, about 3,300 fewer) and hidden score held | 0 | 0 | 2 on / 2 off on one SHA on the local model (measured failing) across two families; off for good if a hidden test is lost; a passing model is judged on a hosted run when the owner starts one |
| M-PQ.8 | PQ.8 interface states (LF.1331, `reports/audits/2026-11-25-product-quality-ui-db-api.md` PQ.8): for a product with a page, the specification's `interface_design` names an `Empty:`, a `Busy:` and a `Failed:` line, each with an ARIA role and the words shown, outside any list; a draft missing one goes back once. Presentation only | `INTERFACE_STATES_AS_CRITERIA` (group `Interface design`) | OFF (built 11-25, LF.1331); acts only on a product with a page | page probe finds the three states; hidden web tests (an empty-state element must not be counted as a list item); specification repairs; architect minutes | - | - | 2 on / 2 off on web-todo, web-todo-react and fullstack-bookmarks on one SHA |
| M-SK.2 | Craft checklists by file domain (LF.1336, plan SK.2 with PQ.6 and PQ.9, `reports/audits/2026-11-25-product-quality-ui-db-api.md`): a builder's request and each file drafted whole carry a few lines per domain its files are in (interface: empty, busy and failure states outside the list, the pack's design tokens and never raw values, labels, contrast in both schemes, phone width; data: constraints the data implies within the brief, indexes on looked-up/filtered/sorted fields, created and changed times stored and never returned unasked, migrations when asked; service: one error shape, the status code per failure, never a 500 for one, authorisation on owned records, no input accepted and ignored); the UI/UX adviser and the architect are told the pack's token names; the database and backend advisers are asked for the same bars | `DOMAIN_CRAFT_CHECKLISTS` (group `Builder craft`) | OFF (built 11-25, LF.1336); firing signal "Craft checklist for your files" | the PQ.10 quality score (interface, data, service parts) and the PQ.2 schema conformance count; hidden score held (a 3-field service must not gain returned fields); minutes to green | 0 | 0 | to measure once PQ.10 scores runs: 2 on / 2 off on one SHA for web-todo-react, notes-api and fullstack-bookmarks, plus the medium brief; kept when the quality score rises and no hidden test is lost; removed on a hidden loss traced to a checklist line |
| M-SP.3 | Specialists review their own domain (LF.1322, plan SP.3, owner's question 2026-11-25 "why are my ux, db and other specialists not catching anything"; `reports/audits/2026-11-25-product-quality-ui-db-api.md`, `reports/audits/2026-11-25-per-agent-audit.md`): in the advice-review call each consulted specialist also reports at most 5 defects in its own domain in the sprint's changed files (file, line, observable failure); blocking/major gate as Sprint Record findings with source `specialist` shown to the milestone reviewer | `SPECIALIST_DOMAIN_REVIEW` (group `Review gates`) | OFF in code and compose (owner decides when on) | (1) gating `specialist` findings per sprint (Sprint Record `findings`, source `specialist`, `gating` true); (2) how many are confirmed later - the milestone review raises it, or a later fix or defect names the same file and the failure stops (defect log `files`, a test that fails then passes); (3) minutes added: `advice_review_*` stage minutes per sprint on against off; hidden score must not fall | 0 | 0 | needs 2 runs per family on and 2 off on one SHA; kept when confirmed findings per sprint rise with no hidden-score loss and under 5 minutes added per sprint |

## Second review (HR2, 11-08): switched items to build, in the merged order of docs/harness-review.md §10 bundle 8

Each gets its own switch (default off), a row in the table above when built, and two runs per family on and off on
one SHA. Order: `FIRST_TRY_CANDIDATES` (fix.2), `PLANNING_THINK_BOUND` (P.2), `DESIGN_REVIEW_IN_ONE_CALL` (D.3), M7's
on arm (G.7), D1 lint + `DESIGN_SINGLE_REVIEW` (D.7+D.6), `SUITE_PASSES_TWICE` (Q.3), `ADVICE_ONE_CALL` (G.6), G.2
security as spec conformance, `SPEC_SLICES_BY_STAGE` (D.5), `CONTRACT_LIST_PROBE` (Q.8), `STOP_WHEN_OWN_TESTS_PASS`
(fix.8), `REVIEW_THE_SUITE_DELTA` (Q.7), `SURRENDER_AFTER_A_FAILED_WRITE` (fix.5), `MUTATION_SURVIVORS_TO_QA` (Q.6b),
`PRODUCT_LINT` (PR.6), `SETUP_PROOF_FEEDBACK` (SS.7), G.5 scanner note, M6 arm, M8 arm, D.8, `EDIT_FORMAT_BY_SIZE`
(P.9), Q5 browser mutants; from §12: `MEMORY_BY_NEED` (C.2, near the top with fix.2 and P.2), `CAPS_FROM_THE_DIAGNOSIS`
(C.4b), C.5 schema-first, C.1 estimated cache, E.2 stage forks (tooling). Bug and quality items (bundles 1-7) need no row: they are always on.

Measurement plan (HR2 §12, adopted): first HR2.E.1 (per-run switch overrides) and HR2.R.1 (pauses out of the time
KPI), then one frozen SHA; each switch as a pair on both ports (on A / off B, then swapped: 4 runs = 2+2) on the
shortest families that exercise it; stage forks (HR2.E.2) for the token/efficiency switches before any full run; M1
as one group with one off arm on web-todo and tasks-api; M2 bundle by bundle, largest token share first. Budget ~20
runs instead of 84. E.1 landed 11-08 (LF.708): arms now run on one SHA with per-run switch settings.

Superseded by HR2 (do not build as first written): SF.2b (parked on evidence), SF.3a (premature until replay
works), Q3 (deprioritised), Q4's stub leg (dropped), F6 (wrong shape -> fix.4), WB.5 (not supported by the data),
E4 (-> PR.9 generated edge sets).

HR2 progress: bundle 1 - R.1, R.4 (LF.690; 45 ledger rows recomputed, 2,145 paused minutes taken out), O.1, E.5 (LF.691), C.3, C.4a, OB.1, R.5 (LF.692, deploys at the next boundary), fix.7 (LF.693), E.3, Q.10 (LF.694), Q.1 (LF.696), Q.6a (LF.697; mutation median 0.667 -> 0.583 honest) fix.1 (LF.698) built 11-08 01:3x, Q.4 (LF.699, 11-08 09:5x), Q.9 (LF.700, 10:0x), G.1 (LF.701), P.5 (LF.702), P.8 (LF.703), SS.4 (LF.704; M6's KPI now in `effects`), Q.11 (LF.705, `loop.sh blind-spots`), G.3 (LF.706, `loop.sh gap-precision`), PR.10 (LF.707, `handoff_score`). Bundle 1 done 11-08 11:0x. Bundle 1b: E.1 (LF.708), R.3 (LF.709), R.2 (LF.710), O.3 (LF.711), E.4 (LF.712; no family held out now - a new held-out brief is owed), O.2 (LF.713) built: bundle 1b done 11-08 11:5x. Bundle 2 (what ships): PR.1 (LF.714), PR.2 (LF.715), PR.11 (LF.716), PR.4 (LF.717), G.8 (LF.718), PR.3 (LF.719), PR.12 (LF.720), RT.1 (LF.721), G.4 (LF.722) built; PR.13 moved to the switched list (`UNIT_TESTS_REPAIR_PASS`, off): red unit tests preceded a lost hidden test in 9 of 57 runs (16%, under the 21% base) - a handoff cost, not a score one - and a tests-only model pass is the shape TESTS_ONLY_WRITES had when it was removed for cost; build it when a model is up to measure it (KPI: `handoff_score`'s unit line, model calls). Bundle 2 done 11-08 13:1x; bundle 3: D.4 (LF.723), D.1 (LF.724; KPI advice-repair rounds a run, 224/120 -> ~0); D.2 (LF.725; KPI architect calls -2 to -3 a run): bundle 3 done; bundle 4: P.1 (LF.726; KPI readiness resends a run 1.1 -> ~0.1); P.6 (LF.727); P.3 split: (a) is mostly the built-in first-reread answer; (b) masking `read_file` for planning stages goes behind `PLANNING_READ_MASK` (off) - it can take away a read the lead needs, so it is measured on `redundant_read_rate` and planning minutes first; P.7 (falcon-only evidence) and P.4 next; bundle 5: fix.3 (LF.728), fix.4 (LF.729; KPI second-attempt fix rate); fix.6 (LF.730; KPI fix rate by source): bundle 5 done; bundle 7: SS.5 (LF.731), SS.1 (LF.732; KPI replay successes, setup minutes on a second run of a stack); full pack check 11-08 14:5x in its own container: 38/38 packs proven; library 0/6 - all six entries predate LF.732 (falcon's lacks requirements.txt, as SS.1 found) and were set aside, so the library refills in the new form; SS.6 (LF.733), SS.2 (LF.734; KPI setup input tokens ~45k -> ~25k a call, M6's lines beyond scope); SS.3 deferred on merit: its gain is measured only on Python services, and the one custom family (falcon) already has its layer - layer data for ten more packs would change setups no benchmark runs; build it with the first custom family in another language; bundle 6: G.9 (LF.735), PR.8 (LF.736; KPI quality title_of_only_spaces 12/49 -> 0); Q.2 not built on evidence: of 318 shipped 'locked with this still open' items only 1-2 say nothing is wrong (the review counted 49/295 with a pattern that matched real findings using 'correctly'/'acceptable'); a prose filter would drop real findings; its structured-field half is a prompt change for a model-up cycle; Q.5 and PR.7 need a model to verify - next with the first runs; FILED 11-08 (wordstats-cli 1): a command-line product's contract command lines are never checked at release - the sandbox refuses `python -m <its own package>`, and most lines hold placeholders (`<file>`, `N`) or a shell pipe the harness cannot run as written; a fix needs (1) `-m` of a package inside the project allowed, (2) the project's own interpreter, (3) only concrete lines run, the rest named unchecked with that reason - else false failures; PR.5 reshaped (only node-hono-native keeps an entry file; drafted entries replace a template line - needs a design, not a template edit); next G.4, PR.3, PR.12, PR.13, RT.1.

## Harness review items behind a switch (first review's list; see HR2 above for the current order)

From `docs/harness-review.md` Phase 2-3. Each gets its own switch, default off, and a row in the table above when built.

| Item | What it changes | Status |
|---|---|---|
| D1+D2 | deterministic cross-section consistency check; harness writes setup-owned sections | to build next (every falcon run and both tasks-api runs on 11-07 escalated at the second design review) |
| D3 | one design review plus deterministic gates | to build |
| P1+P7 | plan repair by delta; readiness rules in the schema | to build |
| P2, P3, P6 | failure-made re-plans; edit format by model tier; two draft candidates | to build |
| G3 | milestone send-back only with a failing test, check or probe behind it | built behind a switch: M7 |
| G4, G5 | deterministic security scanner; one batched advice review | to build |
| Q2-Q6, Q8 | isolation by fixture; Python dry run; stub validation; browser mutants; executable dispute verdicts; relational assertions | to build; Q5 (browser mutants) waits for M2's verdict on `MUTATION_GUIDED_TESTS`, which it would extend (11-07 22:3x) |
| F1, F5, F6 | candidate selection; SBFL localisation; fresh second attempts | to build |
| C2, C3, C4, C6 | constrained answers; masked tools; stable opening; repo map | to build |
| SF.2b, SF.2c, SF.3 | harness-run generator (stacks that have one; Python has none, so M6 covers the falcon case); setup budget and rollback; patch on replay and promotion | to build |

Candidates found by audits (efficiency: a switch and a measured no-loss result before any is kept):
- M8 (low): a one-file rewrite is shown 60-70k characters of project memory (`rewritten_fixes.MEMORY_CHARACTERS`; 115 requests over 20 runs, median 64,610) - try the failure's files and their imports only (~20k), judged on the rewrites' fix rate; ~2 min of prefill a run.

## Review items that need no measurement (bug fixes, always on)

Built: R1 (LF.660), F2 telemetry (LF.663), F3 (LF.664), C1, F4 measured form (LF.669), D8 (LF.674), R6 (LF.675), C7 (LF.677), Q1 recording and report (LF.678; `loop.sh suite-checks`), P4 in its measured form (LF.679: a finished work order owns no file), F8 (LF.680), E1 (LF.681: `impact.py` leaves out runs a change was deployed into), SF.0b (LF.684-685), SF.0c (`loop.sh stack-misses`: every stored custom-setup run that fits a pack now is listed - all old misses fixed; the 9 still unfitted are Falcon, no pack), SF.1.
R3 not needed now, measured: no real orphan since LF.595; the KPI that suggested one counted long model calls (fixed, LF.682).
R2 not needed, measured over the last 30 runs: 178 deploy cancellations, every one a call refused before it was sent ("this stage's call is not made"); no call in flight was lost at a resume - the pause already drains at the call boundary.
Not built on evidence: G1 (measured), G6 (measured), P5 (on merit). Covered: G2 (LF.648).
To build, in order: none left - the switched items next (table above).

## Measure batch 2026-11-10/11 (frozen 87d7c9b8, owner's go 11:33 JST)

Two runs per family, scored by hidden tests only; no deploys into the batch.

| Family | Runs | Hidden | Wall minutes | Notes |
|---|---|---|---|---|
| textkit-lib | run-80d8b13a, run-7f175172 | 8/8, 8/8 | 28, 27 | |
| tasks-api | run-629f0be3, run-f1f2a8ec | 10/10, 10/10 | 87, 235 | 235: suite rework, 3 sprint attempts |
| web-todo | run-c0622089, run-42527557 | 10/10, 10/10 | 88, 111 | 111: prose spiral (LF.805), wrong filter tests (LF.806) |
| wordstats-cli | run-447c561f, run-510c3a03 | **6/8 (false acceptance)**, 8/8 | 32, 49 | spec overrode the brief's "instead" (LF.807) |
| notes-api-hono | run-a418c471, run-76a4a334 | 9/9, 9/9 | 250 (72 active), 60 | 4a: :8888 outage; unpassable `list[0]` test (LF.808) |
| fullstack-bookmarks-py | run-cbb75448, run-7c8e03f5 | 8/8, 8/8 | 107, 526 | 526: 24 fix stages, 59 salvaged replies (LF.805, LF.811) |

**Result: 10 of 11 full (one false acceptance).** Fix batch LF.801-813 deployed 2026-11-11 05:19 JST (33a45a6).
