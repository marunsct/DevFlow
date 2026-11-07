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
| M5 | MEASURE_ONCE (reuse an unchanged product's measurement) | `MEASURE_ONCE` (built in) | ON | suite minutes | - | - | LF.676 fixed its skipped own-start check; built in, no arm |

## Harness review items behind a switch (to build, then measure)

From `docs/harness-review.md` Phase 2-3. Each gets its own switch, default off, and a row in the table above when built.

| Item | What it changes | Status |
|---|---|---|
| D1+D2 | deterministic cross-section consistency check; harness writes setup-owned sections | to build |
| D3 | one design review plus deterministic gates | to build |
| P1+P7 | plan repair by delta; readiness rules in the schema | to build |
| P2, P3, P6 | failure-made re-plans; edit format by model tier; two draft candidates | to build |
| G3 | milestone send-back only with a failing test, check or probe behind it | to build |
| G4, G5 | deterministic security scanner; one batched advice review | to build |
| Q2-Q6, Q8 | isolation by fixture; Python dry run; stub validation; browser mutants; executable dispute verdicts; relational assertions | to build |
| F1, F5, F6 | candidate selection; SBFL localisation; fresh second attempts | to build |
| C2, C3, C4, C6 | constrained answers; masked tools; stable opening; repo map | to build |
| SF.2b, SF.2c, SF.3 | harness-run generator (stacks that have one; Python has none, so M6 covers the falcon case); setup budget and rollback; patch on replay and promotion | to build |

## Review items that need no measurement (bug fixes, always on)

Built: R1 (LF.660), F2 telemetry (LF.663), F3 (LF.664), C1, F4 measured form (LF.669), D8 (LF.674), R6 (LF.675), C7 (LF.677), Q1 recording and report (LF.678; `loop.sh suite-checks`), P4 in its measured form (LF.679: a finished work order owns no file), F8 (LF.680), E1 (LF.681: `impact.py` leaves out runs a change was deployed into), SF.0b (LF.684-685), SF.0c (`loop.sh stack-misses`: every stored custom-setup run that fits a pack now is listed - all old misses fixed; the 9 still unfitted are Falcon, no pack), SF.1.
R3 not needed now, measured: no real orphan since LF.595; the KPI that suggested one counted long model calls (fixed, LF.682).
R2 not needed, measured over the last 30 runs: 178 deploy cancellations, every one a call refused before it was sent ("this stage's call is not made"); no call in flight was lost at a resume - the pause already drains at the call boundary.
Not built on evidence: G1 (measured), G6 (measured), P5 (on merit). Covered: G2 (LF.648).
To build, in order: none left - the switched items next (table above).
