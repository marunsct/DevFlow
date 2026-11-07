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
| M5 | MEASURE_ONCE (reuse an unchanged product's measurement) | `MEASURE_ONCE` (built in) | ON | suite minutes | - | - | LF.676 fixed its skipped own-start check; built in, no arm |

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
runs instead of 84. Until E.1 lands, no arm can be judged: since 11-05 no family has two clean runs on one SHA.

Superseded by HR2 (do not build as first written): SF.2b (parked on evidence), SF.3a (premature until replay
works), Q3 (deprioritised), Q4's stub leg (dropped), F6 (wrong shape -> fix.4), WB.5 (not supported by the data),
E4 (-> PR.9 generated edge sets).

HR2 progress: bundle 1 - R.1, R.4 (LF.690; 45 ledger rows recomputed, 2,145 paused minutes taken out), O.1, E.5 (LF.691), C.3, C.4a, OB.1, R.5 (LF.692, deploys at the next boundary), fix.7 (LF.693), E.3, Q.10 (LF.694) built 11-08 01:0x; left in bundle 1: Q.1, Q.4, Q.9, G.1, fix.1, P.5, P.8, SS.4, OB.1, Q.6a, Q.11, G.3, PR.10.

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
