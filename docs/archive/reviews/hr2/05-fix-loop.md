# 05 Fix loop (HR2) - ci_gate, test_and_triage, defect_remediation, defect_fix_worker, the fixer's request

Reviewer 05, read-only, 2026-11-07/08. Data: 536 transcripts in the worker (123 runs since 11-01, 45 since 11-05,
14 on 11-07), `data/bench` (262 scored), `data/kpi/ledger.csv`. Script:
`/tmp/claude-1000/-home-arun-Desktop-langchain/d4298d72-a977-42bb-8a37-f5c3120002bc/scratchpad/review2/fixloop_measure.py`
(outputs `m_1101.json`, `m_1105.json`, `m_1107.json` beside it). Fix stages were reconstructed from the transcript by
chronological segmentation: every record since the previous fix-stage end event (`fixed`/`reverted`/`left open`/
`closed without a fixer`) belongs to the next one; stage names recur across sprints, so a name alone cannot key them.

## 1. What exists

- **CI gate** `src/app/graph/engineering.py:478` (`ci_gate`): deterministic - regressions against the last snapshot
  (`regression_defects` :126), what the language service still underlines (`underlined_in_the_batch` :289), what the
  manifests do not declare (:411), what the compiler says (:445). No model call.
- **Test round** `workflow.py:10720` (`test_and_triage_node`): the harness runs the locked suite once a round
  (`acceptance_for_round` :10755), repairs or sets aside tests that cannot pass (:10758-10773), and in fast delivery
  the round is the harness's own (`harness_round` :10816): failing criteria, the unit run (`_the_unit_tests_fail`
  :2964), the stub check, page check (:10965), pack contract (:10970), later-sprint filter (:10973), the suite's
  backstop (:10990), then the three merges `_one_defect_per_cause` :5940, `_one_defect_per_root_error` :6152,
  `_one_defect_per_failing_tests` :6123, known causes (:11045), `_closed_by_this_round_s_measurement` :7035, the stable
  id refresh `_refreshed_by_the_round` :2906 (LF.680 `defect_ledger.defect_id`). Exhaustion -> `_replan_or_escalate`
  :11188 (settle-when-green :11227, stall rule :11234, best attempt :11242).
- **Dispatch** `defect_remediation_node` :11674 (linear cursor) / `_the_next_fix_batch` :11706 (parallel, measured
  once per batch, reverted whole, then alone). Per defect `_fix_one` :11484: closed-without-a-fixer re-measure
  (`_closed_if_an_earlier_fix_resolved_it` :6867), per-defect call cap (`defect_budget`, 60), model choice by failed
  tries (`_the_build_model` :9017), base commit (`before_a_fix` engineering.py:692), modes (`defect_fix_modes.begin`),
  kept-candidate replay (`kept_fix_candidates.replayed`), **the rewrite path** `_fixed_by_rewriting` :11388 ->
  `rewritten_fixes.fix_by_candidates` :536 (only when `failed_tries >= 1`) then `fix_by_rewriting` :415 (up to
  `MOST_PASSES` 3 passes over `files_to_fix` :114 + `localisation.localised`, one whole-file or anchored-edit call per
  file, "If this file needs no change, reply with it unchanged" :369); when it writes nothing -> **the agent loop**
  (`create_specialist_agent` + `_run_gated_agent` :11549-11573, `verify_after_write.watching`, 16-call cap, ends for
  good under `AGENT_LOOP_FIX_LIMITS`); an answer with no changed file -> `surrender_to_rewrite.after_a_surrender`
  :11586 (LF.663 records wrote/declined). Then `engineering.after_a_fix` :840: snapshot, broken tests, install and
  start breaks, kept-if-tests-only (:875), `unit_tests_disagree` (:897), `net_gain` (:914), contested test (:920),
  revert + `start_breaks.record` (:931-935, LF.669), commit and `start_breaks.clear` (:949-954). Settlement
  `_settle_the_fix` :3398 by the defect's own tests (`_the_defect_s_tests_pass` :3221); disputes :11617-11636, :11655.
- **The fixer's request** `specialists.py:1130` (`build_defect_fix_request`): defect prose, affected files, observed
  output (`_observed_output` :1115 - the criteria's own tests first since LF.607/664: `workflow.py:11319-11321`),
  page look, where the product stands, the regression clause; then `workflow.py:11333-11376` appends what to leave
  alone, the mode briefing, the specification part, bundled co-defects, the last-attempt section, earlier attempts
  (PH.2), stub/unserved/database sections, shared facts (CM.1), where things stand (PH.1), code-graph neighbours
  (CG.2), the page screenshot; `start_breaks.the_section` (LF.669) rides on the shared facts block
  (`shared_facts.py:245-252`, `with_the_facts` at workflow.py:11361), so it reaches every stage that reads the facts
  while the streak lasts, not only the fixer. `defect_ledger.shown` :11382 records a fingerprint and the section list.
- Today's changes in this area: LF.663 (surrender telemetry), LF.664 (unit-test defects see their own failing
  tests), LF.667/667b/668 (a long failure keeps its raised error, once), LF.669 (start-break streak told to the next
  fixer), LF.670 (empty unit report re-measured), LF.671 (a probe's finding settled by the probe), LF.680 (stable
  defect ids; a rewrite records `shown`).

## 2. Measured

**Where fix time goes (123 runs since 11-01; 729 fix stages with a fixer, 280 closed without one).**

| Path (attempt shape) | n | fixed | left open | reverted | min median (fixed / open / reverted) | input tokens median |
|---|---|---|---|---|---|---|
| rewrite only (whole file or anchored) | 339 | 72 (21%) | 193 | 74 | 0.7 / 0.8 / 0.9 | 25k |
| agent loop only | 213 | 100 (47%) | 94 | 19 | 3.8 / 3.6 / 4.7 | 0.6M / 1.0M / 0.7M |
| rewrite declined, then the loop | 177 | 62 (35%) | 86 | 29 | 6.8 / **13.1** / 10.4 | 0.58M / **1.06M** / 1.02M |
| closed without a fixer | 280 | - | - | - | - | - |

Fix stages are 23.5% of wall time since 11-01 (27% since 11-05, 21% on 11-07; the first review's 21-36% holds).
Of 3,817 fix-stage minutes, **2,391 (63%) are "rewrite declined, then the loop"**, and 1,497 (39%) are that path's
left-open stages alone. The round itself (last fix end to the next round's first defect event) costs median 0, p90
3.4 min, 866 min over 277 rounds - the measurement is not the waste; the fixer is.

**Why the rewrite declines.** Of the whole-file rewrite replies sent before an agent loop ran in the same stage,
**206 were the file sent back unchanged**, 30 changed and 6 had no fenced block (exact comparison with the file as
sent). Over every whole-file rewrite reply since 11-01, 327 of ~770 (42%) are "unchanged". The request is median
89,870 characters, of which the project memory is 71% (`MEMORY_CHARACTERS` 60k). When the loop then fixed the defect
(87 cases), it wrote the very file the rewrite had been pointed at in 57 (66%) and another file in 30 (34%): examples
`notes-api/test/app.test.ts -> src/app.ts`, `tasks-api/run_pytest.py -> server.py`, `word-statistics-tool/input.txt
-> wordstats/cli.py`. 63 of 259 files the declined rewrite was asked to correct (24%) were test or acceptance files.
So two faults: the one-shot rewrite is pointed at a test or scratch file a quarter of the time (`files_to_fix` reads
the failure's file names; the localiser `localisation.localised` is skipped when 1-2 files were found, :MOST_FILES_UNASKED),
and two thirds of the time it has the right file and still answers "no change" - the loop, which can run the test and
read the trace, then fixes it in 7 min and 600k tokens.

**Candidates (F1).** Since 11-01, 9 stages of ~730 sent the same rewrite prompt more than once (the only trace a
candidate round leaves): 1 fixed, 7 left open, 1 reverted. The gate is `failed_tries >= 1 and candidate_model and
not after_a_surrender` (workflow.py:11443) plus `check() is None -> return None` (rewritten_fixes.py:573: no
candidates for any defect without criteria or a unit-run opening). The first attempt - where 551 of 969 attempts
happen and 29% fix - never samples.

**Surrender (F2).** Of 180 agent-loop stages left open since 11-01, **138 wrote files and still left the defect
open; 42 wrote nothing**. The surrender path only sees the 42. Since LF.663 (11-07 14:09 JST) 8 loop stages were
left open: 7 had written (no surrender, by design), 1 surrendered and the rewrite "declined: the rewrite found no
file it may write, or wrote none"; the other two records are mutation findings (declined by rule). The costly case
is not the silent loop; it is the loop that writes a change that does not pass and whose change is then **committed**
(`after_a_fix` :949 commits whatever broke nothing) - the next round raises the defect on the altered product.

**What the fixer is shown (F3, LF.607/664).** First agent-loop requests by source, 11-01 to 11-07: acceptance-suite
defects 124 "last failing command" vs 64 "its failing tests" vs 7 none; test-round defects 76 vs 9 vs 5; mutation
findings 78 last command, 2 "what settles this finding". Since 11-05 the mix is 126 own tests / 109 last command / 67
none; on 11-07, 30 / 21 / 11. The last command reaches acceptance-suite fixers when `what_the_criteria_s_tests_printed`
finds no failed test under the tag (suite.py:4644 - a run that did not start, or a tag the test names do not carry)
and every test-round defect worded by the model (LF.664 keys on "The unit tests fail." only, suite.py `_A_UNIT_TEST_DEFECT`).
`shown` sections (LF.680) are recorded on 68 of today's fixers; the rewrite's `shown` now appears.

**Reverts by cause (F4, LF.669).** Since 11-01 before LF.669: acceptance test broke 50, unit test broke 30, start
break 22 (15 of them on 11-07 before 15:38 JST, falcon 4-6), language service 16. After LF.669 (8 runs, 34 fix
stages): acceptance 3, unit 1, **start breaks 0**. But the streak section (`start_breaks.HEADING`) appears in **0**
fixer requests and no workspace holds `.harness/start_breaks.json`: with no start break after the deploy there was
nothing to tell. The fall coincides with LF.667/668/672/673 (the setup's proof and the kept error), not with LF.669,
which has not fired yet. `loop.sh effects` should list it so the first firing is seen.

**Following one defect (F8).** 808 defects since 11-01 (stable id, LF.680's key recomputed for older runs): 637
raised in one round, 106 in two, 65 in three. The 171 raised in 2+ rounds ended: left open 71 (42%), fixed 37 (22%),
closed by a round's measurement 30, closed without a fixer 26, cut off 7. Their attempt sequences: `left open > left
open` 32, `left open > fixed` 18, `left open x3` 13, `left open > closed without a fixer` 12, `reverted > left open`
9. **Outcome by attempt number**: 1st 29% fixed (162/551), 2nd 22% (48/222), 3rd 11% (11/104), 4th+ 14% (13/92).
By path pair: `loop > loop` fixes 65% on the second try (20/31); `rewrite > rewrite` 16% (7/45); `rewrite > (rewrite
declined, loop)` 33% (12/36). On 11-07 (14 runs): 84 defects, 28 raised 2+ rounds, ending closed without a fixer 11,
closed by measurement 7, left open 5, fixed 4.

**Closed without a fixer.** 280 of 1,009 stage ends (28%): 224 "AC-n failing when reported, passing since" (another
fix's side effect), 30 "its own tests passed in a re-measure taken at dispatch", 15 language-service lines gone, 5
start proven, 2 page check. Real: only 16 (6%) were raised again later under the same id. The first review's "57%
of acceptance defects closed without a fixer" is right and it is the merge working (symptoms of one cause), not waste:
each costs ~0.3 min.

**Left open at release vs hidden tests.** 107 runs joined with `data/bench`: 65 shipped with >= 1 defect left open -
56 full score, 9 partial (14%); 42 shipped with none - 33 full, 9 partial (21%). Left-open defects do not predict a
hidden failure. By source on full-score runs: test round (unit tests) 82, acceptance suite 44; on the 9 partial runs
with open defects: acceptance suite 17, test round 15. The acceptance-suite ones on partial runs are the deferred
criteria G6 measured; the unit-test ones are `release_with_failing_unit_tests` doing what it says.

**Agent-loop calls.** Fixed stages: median 11-12 calls (p90 16-17); left open: median 16 = the cap. `VERIFY_AFTER_WRITE`
does fire: 230 of 475 fix-stage writes since 11-05 carry the "ran this defect's own tests" line.

**Ledger (last 60 rows).** Fix stages median 7.5 a run, fixed 2, left open 3, reverted 0 (sum 63), closed without a
fixer 1; active minutes median 95.

## 3. The first review's items in this area

| Item | State | Evidence and verdict |
|---|---|---|
| F1 candidates: find why they never win; select by net passes and smallest diff; diverse | **open; reshape** | They barely run (9 of 730 stages) because the gate waits for a failed try and the first try is a lone rewrite that answers "unchanged" 42% of the time. The fix is to sample on the first try (HR2.fix.2), not only to select better. Selection by full measurement is already what `after_a_fix` does to the kept one. |
| F2 surrender: record wrote/declined; close the declining branch | **built (LF.663); the branch is the wrong target** | 3 records, all declined by rule. 138 of 180 left-open loops wrote something: the surrender never sees them. Reshape to HR2.fix.5. |
| F3 the defect's own failing tests first | **built for unit-run defects (LF.664); half-done** | Acceptance-suite fixers still get the last command 2:1 overall (124:64), test-round defects worded by the model 76:9, mutation findings 78:2. HR2.fix.6. |
| F4 cause order; measured form LF.669 | **built, not yet fired** | 0 streak sections shown; start breaks 0 after the deploy for other reasons. The cause-order part (start -> install -> compile -> unit -> acceptance -> page) stays a switch; the merge already orders by root error. Low priority on this evidence. |
| F5 light SBFL feeding the localiser (large codebases) | **open; a cheaper first step exists** | 24% of declined rewrites were aimed at a test/scratch file and the loop fixed 34% of its cases in another file; the localiser is skipped for 1-2 found files. HR2.fix.3 (bug) first; SBFL stays Phase 3. |
| F6 attempt 2+ as a fresh context with a reflection | **wrong shape** | Every attempt is already a fresh conversation (a new stage). What decays is the *path*: `rewrite > rewrite` 16% vs `loop > loop` 65%. Reshape to HR2.fix.4: alternate the path and carry the diagnosis, no reflection call. |
| F8 stable defect id | **built (LF.680)** | Used above; recommend the ledger also carry the path (HR2.fix.7). |
| M8 rewrite memory 60-70k chars | **candidate; worth the arm** | Memory is 71% of a 90k-character request whose fix rate is 21% and "unchanged" rate 42%. Judge the arm on the unchanged rate and fix rate, not on prefill minutes alone. |
| G6 (deferral gate, not built) | confirmed | Left-open acceptance defects on partial runs are the deferred criteria; a last try (LAST_TRY_ON_DEFERRED) is the lever, as measured. |
| AY steps 1-6 (plan) | 1, 3, 4 built and firing (localiser 2 calls/run, verify-after-write 230/475, cap); 2 and 6 not | Step 2 "candidates from the same model, drop the judgement-model gate" and step 6's attempt order are what HR2.fix.2/4 ask for; the plan already holds them - cite AY, do not add a second row. |

## 4. Research (2025-2026) and what fits

- **Agentless** (Xia et al., arXiv 2407.01489; README 50.8% SWE-bench Verified): localise hierarchically (file ->
  function -> edit), sample many short search/replace patches, run selected regression tests, re-rank. Our rewrite is
  Agentless without the sampling: one whole-file reply, kept if it changed anything. Fits: sample 3 on the first try,
  "unchanged" is a discarded sample.
- **CodeMonkeys** (Ehrlich et al., Jan 2025, arXiv 2501.14723): serial scaling (more iterations) and parallel
  scaling (more independent state machines); 57.4% Verified; selection by model-written tests and voting. The
  harness has locked tests, a stronger selector than theirs. Fits: parallel is cheap here (a rewrite is 25k tokens vs
  a 0.6-1M-token loop); run them on the same server only up to `max_parallel()`.
- **Nemotron-Cascade** (arXiv 2512.13607) ranks k patches by regression tests passed, ties by vote then shortest
  patch - the first review's "net passes, smallest diff". Fits the kept-candidate selection once candidates exist.
- **Debugging Decay Index** (Adnan and Kuhn, Sci. Reports 2025, arXiv 2506.18403): 60-80% of debugging
  effectiveness lost within 2-3 attempts; a fresh restart with only the problem recovers it. Our curve is 29 -> 22 ->
  11% by attempt. The restart is already a fresh stage; the lesson that applies is "do not re-run the failed
  strategy": alternate path, carry the measured outcome.
- **EET - Experience-driven Early Termination** (arXiv 2601.05777, Jan 2026): stop generating once a patch scores
  above a confidence threshold. Here the threshold is executable: the defect's own tests pass after a write
  (verify-after-write already prints it). Fits: end the loop at that line (HR2.fix.8).
- **AutoCodeRover** (arXiv 2404.05427) adds SBFL method hints only when a test suite exists and reports better
  context selection; a 2025 C-repair paper (arXiv 2509.01947) puts Ochiai scores in the prompt. Per-test coverage
  needs a coverage tool per stack (pack hook) - Phase 3, after the file-kind fix.
- **SWE-agent / OpenHands** (profiling study arXiv 2506.17208): iterative refinement with a learned critic choosing
  among trajectories; "more fail-to-pass tests correlate with lower patch success". Fits: our locked suite as the
  critic; no learned critic.

## 5. New items

**HR2.fix.1 - record the rewrite's reply class and the path on every fix outcome (bug, observability).** Evidence:
the "unchanged" rate (42%) and path shares had to be rebuilt from message text; `loop.sh defects` cannot show them.
Change: `fix_by_rewriting` notes `rewrite reply: unchanged|changed|no block|edit not applied` per file in the ledger;
`fixed`/`left open`/`reverted` events carry `path` (rewrite / candidates / loop / loop>rewrite), calls and minutes;
`loop.sh defects` and `effects` report outcomes by path and list LF.669's section among the mechanisms. Test: a
rewrite whose reply equals the file leaves an `unchanged` record (fails on old code: no record). KPI: none (telemetry).
Size S. Risk none.

**HR2.fix.2 - sample on the first try (doubtful, switch `FIRST_TRY_CANDIDATES`, group Fixing).** Evidence: 177
stages (63% of fix minutes) are a lone rewrite that declined and a loop; 206 of its declines are "unchanged";
candidates run 9 times in 730 stages. Change: in fast delivery the first attempt asks `CANDIDATES` whole-file rewrites
at once with different seeds (plan AY step 2 - `the_candidate_model` without the judgement-model gate), an
"unchanged" reply is a discarded sample, the first whose own tests pass is applied and measured by `after_a_fix` as
now; the loop follows only when none passes. For a defect with no own test (`check() is None`) keep one rewrite. Test:
a first attempt with the switch on sends three requests and keeps the one whose tests pass, with an unchanged reply
discarded (fails on old code: one request). KPI: fix-stage minutes a run, share of "rewrite declined then loop",
hidden score unchanged. Size M. Risk: server concurrency (bounded by `max_parallel()`), 3x rewrite tokens (75k vs
the 1M of the loop it replaces).

**HR2.fix.3 - a criterion's rewrite is never aimed at a test, scratch or data file (bug).** Evidence: 63 of 259
files the declined rewrite asked to correct were test/acceptance files; `run_pytest.py`, `input.txt`; the localiser
is skipped when the failure names 1-2 files (`localisation.py` `MOST_FILES_UNASKED`). Change: for a defect that names
AC-/CR- criteria, `files_to_fix` drops files `is_test`/`is_scratch`/non-source (data) unless the defect's own words
name them (LF.367 keeps the unit-run exception), and the localiser is asked when what remains is empty - whatever
the count before the filter. Test: a failure whose text names only `tests/x.test.ts` asks the localiser and rewrites
the product file it names (fails on old code: rewrites the test). KPI: unchanged-reply rate, rewrite fix rate. Size
S. Risk: a defect truly in a test helper goes to the loop, as it does now when the rewrite declines.

**HR2.fix.4 - a second attempt does not repeat a declined path (bug).** Evidence: `rewrite > rewrite` 45 pairs, 16%
fixed; `rewrite > (declined, loop)` 33%; `loop > loop` 65%; repeated-prompt stop acts only after 3 byte-identical
prompts, which a refreshed failure text defeats. Change: when the previous attempt's rewrite replied "unchanged" for
every file it was shown (from HR2.fix.1's record), the next attempt skips the rewrite and goes to candidates/loop with
one line in the request: "a whole-file rewrite of `f` judged it needed no change; the cause is elsewhere or needs the
trace". Test: attempt 2 after an all-unchanged rewrite sends no rewrite request (fails on old code). KPI: second-attempt
fix rate, minutes per defect. Size S. Risk: none measured; the loop was next anyway.

**HR2.fix.5 - a loop that wrote and did not pass hands its diff to one rewrite before the defect is left open
(doubtful, switch `SURRENDER_AFTER_A_FAILED_WRITE`, group Fixing).** Evidence: 138 of 180 left-open loops wrote
files; the surrender path covers only the 42 that wrote nothing; their half-change is committed (`after_a_fix` :949)
and the next round's fixer starts from it without being told. Change: when the loop's answer changed files and
`_the_defect_s_tests_pass` is False, ask one rewrite of the changed files with the loop's diff and the fresh failure
("what the last fixer changed and what still fails"), measure as now; off, nothing changes. Also always-on and small:
the `left open` event and the next request's earlier-attempts section name the files the loop changed and kept.
Test: a left-open loop with changed files triggers one rewrite request carrying the diff (fails on old code). KPI:
defects fixed on attempt 1, minutes. Size M. Risk: one more 25k call on 138 of 969 attempts.

**HR2.fix.6 - every fixer sees the output that defines its defect (bug; completes F3).** Evidence: acceptance-suite
fixers 124 last command : 64 own tests; test-round 76 : 9; mutation 78 : 2. Change: (a) when the suite's last run
has no failed test under the tag, show the suite's `problem` (did not start / collection error) under "What its
failing tests printed" instead of falling through; (b) a test-round defect with `caught_by` a unit command shows that
command's failures (reuse `what_the_unit_tests_printed` keyed by `caught_by`, not the opening words); (c) a mutation
finding shows "what settles this finding" and never the last command. Tests: one per case (fail on old code: title
"What the last failing command actually printed"); banned-word test for the new title text. KPI: fix rate by source.
Size S. Risk none.

**HR2.fix.7 - `defects` by defect id across rounds in `loop.sh defects` (bug, observability).** Evidence: today's
report lists events per round; the attempt curve (29/22/11%) and endings of multi-round defects are not reported.
Change: group by `defect_id`, print rounds raised, attempt outcomes in order, ending, path per attempt (needs
HR2.fix.1). Test: a transcript with one id in two rounds prints one story. Size S.

**HR2.fix.8 - end the loop when the defect's own tests pass after a write (doubtful, switch `STOP_WHEN_OWN_TESTS_PASS`,
group Fixing).** Evidence: fixed loops end at median 11-12 calls, left-open at the 16 cap; verify-after-write already
prints "they pass now" on 230 of 475 writes, and the model goes on reading and running. Change: after that line the
harness ends the stage with the answer built from the changed files (as the rewrite path answers), skipping the
model's own wrap-up; measured by `after_a_fix` as now. Test: a loop whose write passes its tests makes no further
model call (fails on old code). KPI: calls per fixed stage, minutes. Size S. Risk: a regression test the fixer was
asked to add is not written - keep the stop only when `regression_test_required` is false or `caught_by` is set.

**HR2.fix.9 - the rewrite's memory arm (M8, as registered; sharpen the KPI).** Judge the 20k arm on three numbers:
unchanged-reply rate (42% now), rewrite fix rate (21%), "declined then loop" share (177/729); prefill minutes last.
No new row; this is the measurement plan for M8.

Not proposed: SBFL (F5) before HR2.fix.3 is measured; a reflection call (F6) - the fresh stage already exists; any
change to the closed-without-a-fixer path (94% real, 0.3 min each); a release gate on left-open defects (no
predictive value, G6 stands).

## 6. Priority order and expected effect

1. **HR2.fix.1 + HR2.fix.7** (S, telemetry) - first, so 2-5 are judged on data `loop.sh` prints; ~1 hour of work.
2. **HR2.fix.3** (S, bug) - removes a quarter of the mis-aimed first rewrites; expected: unchanged rate 42% -> ~30%,
   a few of the 177 "declined then loop" stages a day turn into 0.7-min rewrites (each avoided loop is ~7-13 min).
3. **HR2.fix.6** (S, bug) - completes F3; expected effect on the 40% of fixers still shown another defect's command:
   the measured fix rate by source will say; no time cost.
4. **HR2.fix.4** (S, bug) - 45 second attempts a week take the 33-65% path instead of the 16% one: ~1 min and 25k
   tokens saved per pair, and ~8 more defects fixed per 100 multi-round defects.
5. **HR2.fix.2** (M, switch) - the largest lever: targets the 63% of fix minutes in "declined then loop"; if a third
   of those stages are settled by a candidate, ~8 min a run on a 95-min median run (~8%), and attempt-1 fix rate from
   29% toward the loop's 47%. Two runs per family on and off (M-row in `docs/measuring.md`).
6. **HR2.fix.8** (S, switch) - ~4 calls per fixed loop (median 12 -> ~8): ~1-2 min a run.
7. **HR2.fix.5** (M, switch) - after 2 and 4 are measured; it only matters if left-open loops with writes remain the
   top cost.
8. M8 arm (HR2.fix.9) alongside 5, same family runs; then F5 SBFL only for the large-codebase briefs E3 adds.

Everything above is stack-agnostic (file kinds come from `app.analysis.file_kinds`; test commands from packs), keeps
work orders, templates, the Sprint Record and the parallel/linear toggle untouched, and holds for small and large
codebases (the candidates and the file filter act per defect; the localiser's map is already importance-ranked).
