# What is being measured (the one copy)

Owner 2026-11-07 17:1x JST: one document for every change under measurement, so no measurement is missed on or off.
**This file is the only list.** STATE, the handovers, the status board and the plan point here and do not repeat it.
Update it in the same commit as any switch change, deploy that turns a switch on or off, or verdict.

Rules (owner 2026-11-05 and 2026-11-07):
- Bug fixes and quality fixes need no measurement: always on, no switch, recorded in `docs/improvement-plan.md` Appendix M.
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
Written by `loop.sh measuring` from 244 scored runs in the ledger. On and off counts are over every run, across commits: a verdict here says where to look, not that a pair on one commit was run.

| Switch | Group | Default | Runs on | Fired | Runs off | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| `CONTRACT_LINE_COVERAGE` | Being measured | on | 58 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `CONTRACT_NON_NUMERIC_IDS` | Being measured | on | 58 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `CONTRACT_PROBE_AT_LOCK` | Being measured | on | 58 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `CONTRACT_PROBE_WITH_A_BAD_BODY` | Being measured | on | 58 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `CONTRACT_PROBE_WITH_A_RECORD` | Being measured | on | 58 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `CONTRACT_UNREAD_LINES_AT_REVIEW` | Being measured | on | 58 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `IDS_READ_WITHOUT_A_CREATE` | Being measured | on | 58 | 0 | 0 | not measured: needs 0 more on and 2 more off |
| `MUTATION_TEST_RETENTION` | Being measured | on | 58 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `NAMED_TEST_REWRITE` | Being measured | on | 58 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `NAMING_FINDING_BEFORE_DEFERRAL` | Being measured | on | 58 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `ORDER_PROBE` | Being measured | on | 58 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `SPEC_DRY_RUN` | Being measured | on | 58 | 2 | 0 | not measured: needs 0 more on and 2 more off |
| `TESTS_ONLY_WRITES` | Being measured | on | 58 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `PREMIUM_CHANGE_REQUESTS` | Bundles | on | 0 | no signal | 0 | not measured: needs 2 more on and 2 more off |
| `PREMIUM_DEEP_VERIFICATION` | Bundles | on | 0 | no signal | 0 | not measured: needs 2 more on and 2 more off |
| `PREMIUM_MODEL_TUNING` | Bundles | on | 0 | no signal | 0 | not measured: needs 2 more on and 2 more off |
| `PREMIUM_PROJECT_INTELLIGENCE` | Bundles | on | 0 | no signal | 0 | not measured: needs 2 more on and 2 more off |
| `BATCH_ACCEPTANCE_AUTHOR` | Context and cost | off | 0 | no signal | 0 | not measured: needs 2 more on and 2 more off |
| `OBSERVATION_FOLDING` | Context and cost | off | 0 | no signal | 0 | not measured: needs 2 more on and 2 more off |
| `STABLE_STAGE_PREFIX` | Context and cost | off | 0 | no signal | 0 | not measured: needs 2 more on and 2 more off |
| `EQUIVALENT_MUTANTS_REMEMBERED` | Efficiency | off | 0 | no signal | 0 | not measured: needs 2 more on and 2 more off |
| `MUTANT_CHECK_IN_THE_FIX_STAGE` | Efficiency | off | 0 | 0 | 0 | not measured: needs 2 more on and 2 more off |
| `REVIEWS_WITHOUT_REASONING` | Efficiency | off | 2 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `MILESTONE_EVIDENCE_GATE` | Review gates | off | 0 | no signal | 0 | not measured: needs 2 more on and 2 more off |
| `SETUP_SCOPE_GUARD` | Setup scope | off | 0 | no signal | 0 | not measured: needs 2 more on and 2 more off |
| `CHANGE_REQUEST_RUNS` | bundle PREMIUM_CHANGE_REQUESTS | on | 235 | no signal | 1 | not measured: needs 0 more on and 1 more off |
| `ASK_SPECIFICATION` | bundle PREMIUM_DEEP_VERIFICATION | on | 234 | no signal | 2 | measured: hidden 0.91 on / 0.70 off; minutes 87.89 / 206.75 |
| `ASSUMPTIONS_GATE` | bundle PREMIUM_DEEP_VERIFICATION | on | 234 | 131 | 2 | measured: hidden 0.91 on / 0.70 off; minutes 87.89 / 206.75 |
| `MUTATION_GUIDED_TESTS` | bundle PREMIUM_DEEP_VERIFICATION | on | 228 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `REGRESSION_CONTRACT` | bundle PREMIUM_DEEP_VERIFICATION | on | 234 | no signal | 2 | measured: hidden 0.91 on / 0.70 off; minutes 87.89 / 206.75 |
| `RELEASE_AUDITS` | bundle PREMIUM_DEEP_VERIFICATION | on | 234 | no signal | 2 | measured: hidden 0.91 on / 0.70 off; minutes 87.89 / 206.75 |
| `RELEASE_DOCS_REQUIRED` | bundle PREMIUM_DEEP_VERIFICATION | on | 234 | no signal | 2 | measured: hidden 0.91 on / 0.70 off; minutes 87.89 / 206.75 |
| `SCREENSHOT_RUBRIC` | bundle PREMIUM_DEEP_VERIFICATION | on | 234 | no signal | 2 | measured: hidden 0.91 on / 0.70 off; minutes 87.89 / 206.75 |
| `FIX_STAGE_REPLY_CAP` | bundle PREMIUM_MODEL_TUNING | on | 153 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `GUIDE_ANSWER_IN_SCHEMA` | bundle PREMIUM_MODEL_TUNING | on | 227 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `GUIDE_EXACT_ARGUMENTS` | bundle PREMIUM_MODEL_TUNING | on | 227 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `GUIDE_HEED_REFUSALS` | bundle PREMIUM_MODEL_TUNING | on | 227 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `GUIDE_KEEP_TO_ROLE` | bundle PREMIUM_MODEL_TUNING | on | 227 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `GUIDE_NO_REPETITION` | bundle PREMIUM_MODEL_TUNING | on | 227 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `GUIDE_ONE_PROGRAM_A_COMMAND` | bundle PREMIUM_MODEL_TUNING | on | 227 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `GUIDE_PATHS_AS_GIVEN` | bundle PREMIUM_MODEL_TUNING | on | 227 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `GUIDE_STOP_WHEN_DONE` | bundle PREMIUM_MODEL_TUNING | on | 227 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `MODEL_GUIDANCE` | bundle PREMIUM_MODEL_TUNING | on | 227 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `PLAN_REVIEW_REPLY_CAP` | bundle PREMIUM_MODEL_TUNING | on | 146 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `SALVAGED_REPLIES_TURN_THINKING_OFF` | bundle PREMIUM_MODEL_TUNING | on | 146 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `STEERING_AT_THE_TAIL` | bundle PREMIUM_MODEL_TUNING | on | 234 | no signal | 2 | measured: hidden 0.91 on / 0.70 off; minutes 87.89 / 206.75 |
| `STRUCTURED_EXTRACTION` | bundle PREMIUM_MODEL_TUNING | on | 227 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `BUILDER_FACTS` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 190 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `CANONICAL_MEMORY` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 234 | no signal | 2 | measured: hidden 0.91 on / 0.70 off; minutes 87.89 / 206.75 |
| `CODE_GRAPH_TOOL` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 234 | no signal | 2 | measured: hidden 0.91 on / 0.70 off; minutes 87.89 / 206.75 |
| `DECISION_LEDGER` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 234 | no signal | 2 | measured: hidden 0.91 on / 0.70 off; minutes 87.89 / 206.75 |
| `LESSON_DISTILLER` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 235 | 96 | 1 | not measured: needs 0 more on and 1 more off |
| `NAMING_STANDARD` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 210 | no signal | 0 | not measured: needs 0 more on and 2 more off |
| `PROJECT_GRAPH_BUILDERS` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 234 | no signal | 2 | measured: hidden 0.91 on / 0.70 off; minutes 87.89 / 206.75 |
| `PROJECT_GRAPH_FIXES` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 234 | no signal | 2 | measured: hidden 0.91 on / 0.70 off; minutes 87.89 / 206.75 |
| `SHARED_FACTS` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 234 | 117 | 2 | measured: hidden 0.91 on / 0.70 off; minutes 87.89 / 206.75 |
| `STATE_AT_DISPATCH` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 234 | no signal | 2 | measured: hidden 0.91 on / 0.70 off; minutes 87.89 / 206.75 |
| `WHERE_THINGS_STAND` | bundle PREMIUM_PROJECT_INTELLIGENCE | on | 234 | 119 | 2 | measured: hidden 0.91 on / 0.70 off; minutes 87.89 / 206.75 |
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
| M9 | The acceptance review answers without reasoning first (68-74% of output tokens are reasoning; its own output was all reasoning) | `REVIEWS_WITHOUT_REASONING` (group `Efficiency`) | OFF (built 11-09 10:4x, LF.765) | acceptance-review model minutes; hidden score; false acceptances; suite strength (mutation score, review findings) | on: wordstats-cli 6 (run-aaf136ca, c325856d then e0d2d61e) 7/8, false acceptance, review 0 reasoning chars, ~3 review-minutes, review missed a test's own arithmetic; off: wordstats-cli 7 (run-023f2c45, e0d2d61e, :8888) started 13:46; swapped pair on :1234: on wordstats-cli 8 (run-19fb2b9f) 8/8, no false acceptance, review 0 reasoning chars; off wordstats-cli 9 started 15:13; void before: wordstats-cli 4 (LF.768), wordstats-cli 5 (crashed, LF.770) | M9 on wordstats-cli 4 (run-4c98359a, c46bb201) VOID: the switch did not reach the model (judgement model None; LF.768) - its review reasoned 54-74k characters a reply | needs on/off pairs: 2 runs per port on one SHA (`SWITCHES_ON=REVIEWS_WITHOUT_REASONING` on one run of each pair) |
| M5 | MEASURE_ONCE (reuse an unchanged product's measurement) | `MEASURE_ONCE` (built in) | ON | suite minutes | - | - | LF.676 fixed its skipped own-start check; built in, no arm |
| M10 | A firing signal for every switch: 51 of 58 switches leave no text `switch_firing.SIGNALS` can read, so the gate cannot tell "never acted" from "acted and changed nothing" | `app.observability.switch_firing.SIGNALS` | 7 signalled | switches with a signal | - | - | to build: one signature each, on-by-default switches first |

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
