# HR2.03 Acceptance suite and QA (second review, 2026-11-07/08)

Read-only. Evidence from the 13 runs of 2026-11-07, the 536 stored transcripts, 106 surviving workspaces (86 with
an acceptance lock decision), `data/bench` (263 scored runs, 205 mutation files) and the code. Times in minutes of
stage work with gaps over 10 minutes (deploy pauses) taken out.

## 1. What exists

- **Author** `src/app/graph/acceptance_nodes.py:504` (`acceptance_author`), request in
  `src/app/acceptance/requests.py:174` (`build_author_request`: brief 12k chars, suite text 24k, criteria, contract,
  testability, about 20 prose rules incl. `TESTS_ASSUME_ONLY_WHAT_THEY_MADE` at :47 and the view/action rule
  `actions_within_a_view.py:24`). Batched writes `:460`.
- **Review** `acceptance_nodes.py:634-886`: two auto-corrections (`rename_files_the_runner_skips`,
  `correct_reads_of_the_fixture_s_baseurl`), `suite.gaps`, `suite.run`, roll back a repair that made it worse
  (`:647`), `tests_that_cannot_pass` (`suite.py:4988`: 11 measured + 25 text checks, wrapped by
  `findings_that_reopen` `:5071` after a lock), five lenient checks (`locators_nobody_sees`, `locators_that_pick_one`,
  `controls_never_found_by_name`, `records_never_found_as_the_brief_shows_them`, `views_never_acted_within`),
  contract checks (`tests_that_want_json_from_a_204`, `tests_whose_success_status_the_contract_does_not_give`),
  `contract_coverage`, then the LLM QA lead (`src/app/agents/acceptance_reviewer.py:60`, prompt :63-120), then
  `suite.lock` `:333`, `record_at_lock`, `probe_at_the_lock` (`interface_contract.py:1255`). Limits:
  `MAX_ACCEPTANCE_ROUNDS = 3` (`:36`), fast delivery sends the QA lead's findings back once (`:789`),
  `cannot_pass_to_lock` / `too_weak_to_lock` one more round at the limit (`:59`, `:69`).
- **Q1 recording** (LF.678, today): `src/app/acceptance/check_findings.py:36` `noted(root, round, check, findings)`
  writes `.harness/check-findings.jsonl`; `scripts/loop/suite_check_settling.py` (`loop.sh suite-checks`) reports
  per check "settled" (not raised again in a later round). Wrapped today: 12 call sites in `acceptance_nodes.py`
  (`tests_that_cannot_pass` is **one bucket** for its 36 checks). The QA lead's findings are **not** recorded.
- **Reopen / repair** `reopen_the_suite_for` `:1885`, `may_repair` `:1678` (`MAX_SUITE_REPAIRS = 2` per test,
  `MAX_SUITE_REPAIRS_IN_ALL = 4` `:1645-1655`), `tests_left_unrepaired` `suite.py:367`, targeted repair
  (`TARGETED_SUITE_REPAIR`, built in) locks again on the harness's checks when only the named tests changed `:725`.
- **Dispute** `src/app/graph/workflow.py:11964` (`acceptance_dispute_node`): agent `src/app/agents/suite_dispute.py`
  (`SuiteDisputeWithRulings` :82, `STRUCTURED_DISPUTE_VERDICT` now built in; quote guard `_the_standard_holds` :286,
  `tests_it_names` :345), then the executable leg `tests_that_fail_alone` (`acceptance_nodes.py:1728`),
  `tests_whose_service_stayed_up` (:1775), the reclassification cap `within_the_cap` (:1717), then
  `reopen_the_suite_for(..., reclassifying=True)`. `product_at_fault.py` (`QA_SAYS_THE_PRODUCT_IS_AT_FAULT`, built
  in) lets a dispute-opened repair answer "the product is at fault" with word-for-word quotes.
- **Contract probes** `interface_contract.py`: `server_errors` :868 (bare request per contract line, 5xx is a
  defect), `bad_body_errors` :904 (`CONTRACT_PROBE_WITH_A_BAD_BODY`), `emptied_field_errors` :962, pytest probe
  module :586-730 for Python packs, Playwright for JS; `probe_at_the_lock` :1255 (`CONTRACT_PROBE_AT_LOCK`, group
  "Being measured", on). Hooks `with_a_record_made_first` :124.
- **Mutation** `mutation.py` (release, `CHANGES_AT_RELEASE = 3`, 18 operators :38-57, `BROWSER_KINDS` left out
  :35; a change that turns every test red counts as caught, :19/:82-83); `mutation_guided.py` (premium
  `MUTATION_GUIDED_TESTS`, 6 changes a sprint, 3 findings, 2 tries, settled by running the unit tests);
  `mutation_equivalents.py`, `mutation_retention.py` (`MUTATION_TEST_RETENTION`, being measured).
- **Criteria** `criteria.py` (brief headings -> numbered criteria), `sprint_scope.py` (which locked tests are a later
  sprint's). **Unstable** `unstable.py`: a product fingerprint; a defect whose tests pass alone on an unchanged product
  goes to the dispute with `unstable.reason` (LF.185).
- Changed today in this area: LF.670 (empty unit report measured again), LF.671 (a probe's finding is settled by the
  probe), LF.676 (own-start check also under `MEASURE_ONCE`), LF.678 (Q1 recording), LF.680 (stable defect ids).

## 2. Measured

**Today's 13 runs** (work minutes, gaps out; `w/per_run.json`):

| Stage | Minutes | Per run | Model calls | Output tokens | Notes |
|---|---|---|---|---|---|
| acceptance_author | 160 | 12.3 | 489 | 780k | input median 49k tokens; 156 `read_file`, 102 `edit_artifact`, 80 terminal, 46 `run_validation` |
| acceptance_review (QA lead) | 81 | 6.2 | 44 | 491k | **12.2k output tokens a call (median), reasoning 40k chars median, 82k max; 6 of 42 calls hit the cap and were salvaged**; 46 `read_file` |
| acceptance_dispute | 11 | 0.9 | 10 | 52k | one call reasoned 97k chars / 20k tokens |
| all acceptance | **253 of 1,172** (21.6%) | 19.5 | | | the architect+review 179, lead 114, fixing ~250 |

The wall-clock figures in the transcripts are inflated by deploy pauses: e5c39a49's dispute "105 min" is 5.6 min of
work and an 83-min gap; 44a25a80 author_1 "90 min" is 4,368 s of gap; 4fa87240 author rounds "52+58 min" hold two gaps
of 42 and 44 min. Audits that read stage durations see pauses as stage cost.

**Lock rounds** (86 workspaces with a lock decision): 1 round 33, 2: 17, 3: 32, 4: 3, 5: 1 - **42% reach the
limit**; today 4 of 13 (a9f73836, eee50710, 66e5a37c, 4fa87240) locked after 3 rounds with problems open.
**53 of 86 (62%) locked with problems "still open"**: 295 items, of which **118 are QA-lead criterion findings, 85
"other" (nearly all QA-lead prose), 37 harness checks (13%)**. Of the 295, **49 (17%) are non-findings** the QA lead
returned as findings ("no finding there", "acceptable as stated", "the criterion does not state details content, so
it is fine. No finding.") and `findings_about_the_suite` (`suite.py:267`) drops only "the product lacks it". 23 are
shared-store counts (AC-9 asserts `[]` after other tests created notes), 55 "weak/missing assertion". Open problems
become `acceptance_open_problems` and so release concerns - part of G1's 0.23 precision.

**Harness checks (Q1)**: 13 findings in 5 runs since LF.678 (recording started today): `tests_that_cannot_pass` 5
findings, 3 settled; `views_never_acted_within` 4, 2 settled; `locators_nobody_sees` 3; `controls_never_found_by_name`
1. Too few to judge any check, and the 36 checks inside `tests_that_cannot_pass` cannot be told apart. Today's 11
Python runs recorded one harness finding in all; their rounds were the QA lead's.

**Disputes**: 146 of 536 runs had a dispute (337 calls). Hidden score with a dispute 0.864 (129 runs) vs 0.897 (131)
without; **20 of the 30 false acceptances had a dispute**. Verdicts: 22 lock decisions say a test "cannot pass for any
product", 3 "an error in the test's own code"; 58 runs shipped a "reclassified under dispute" gap; 45 re-locks (v2+).
The executable leg's outcomes (`tests_that_fail_alone` passed-alone, service stopped, past the cap) are logger
warnings only - **not in the transcript, decisions or KPIs**, so "how often a dispute's repair was overruled" cannot
be measured from stored data. `QA_SAYS_THE_PRODUCT_IS_AT_FAULT` (built in): the rule was shown in 17 runs, the model
made **0 claims**, 0 "QA found no fault" decisions in 86 workspaces - built, on, never fires. `unstable.reason`
reached a dispute in 5 runs.

**False acceptances** (30 of 263): web-todo 8, fullstack-bookmarks-py 5, notes-api-hono 4, wordstats-cli 3, falcon 2,
tasks-api 2, notes-api 2, others 4. Causes: 9 are whole-run zeros (the product did not start as delivered: falcon
`No module named 'falcon'` x2 = LF.662/676; tasks-api x2, textkit, web-todo-react) - a start/packaging class, not a
suite class; 21 are partial scores where the locked suite was green and one or two hidden tests failed.

**Blind-spot list** (hidden tests failing in partial-score runs; the suite's misses):

| Family (runs) | Hidden test | Fails | Last seen | Harness answer |
|---|---|---|---|---|
| web-todo (47) | a task completed while filtered to active leaves the active list | 12 (8 on 10-18, 4 scored 11-04, visible 10/10) | before LF.569 (11-04) | `views_never_acted_within` + LF.616; one web-todo since: 10/10 |
| web-todo | refuses a task without a title / edits a title and keeps it | 7 / 7 | 10-18 batch | - |
| notes-api-hono (93) | test_deletes_a_note | 5 partial | 10-27 | (204/JSON checks) |
| fullstack-bookmarks-py (19) | filters the list by tag | 3-4 | 11-05 | LF.616 (typed filter counts as a view) |
| fullstack-bookmarks-py | newest first / saves and links / deletes from page | 2 / 2 / 2 | 11-04 | order: `tests_that_assert_an_unstated_order` only refuses order |
| notes-api (19) | refuses an update that empties the title | 2 | 11-0x | emptied-field probe: 7 defects raised, 4 closed without a fixer, 3 left open |
| wordstats-cli (6) | json_top_words / most frequent / ties alphabetical | 3 / 2 / 1 | - | no CLI pack hooks |
| tasks-api (54) | none partial | 0 | - | every tasks-api miss is a whole-run zero |

**Contract probes at release**: of 1,421 completion gaps stored, bad-body 2, emptied-field 1, server-error 0; defect
events: emptied-field raised 7, bad-body raised 1. The probes fire rarely and nothing records what they probed (lines
checkable / probed / skipped), so their coverage is unknown.

**Mutation at release** (204 files, 2,247 mutants): median score 0.667, 92.6% of suites below 1; **218 completion
gaps "the locked suite did not notice"** - the largest acceptance-area gap kind, acted on by nobody at release.
Survivors by kind: `&&`->`||` 80% survive (78/98), `||`->`&&` 68%, `True`->`False` 57%, `False`->`True` 57%,
`true/false` 52-53%, `or`->`and` 50%, `and`->`or` 50%; comparison flips 5-26% (`<`->`>=` 5%, `==`->`!=` 19%,
`===`->`!==` 26%). **334 mutants (15%) turned every test red (the product broke outright) and count as caught**
(`mutation.py:19`), inflating the score. `MUTATION_GUIDED_TESTS` (premium): 149 findings raised, 80 fixed, 48 left
open, 69 closed; its fixer-judged "equivalent" path is text (`_SAYS_EQUIVALENT`).

**Recurring notes totalled**: (a) "locked with these still open" 53 runs, cause: the QA lead's limit-round findings
and non-findings are kept as problems; (b) shared-store counts 23 open items + the dispute's run-alone leg, cause:
isolation is a prose rule (`TESTS_ASSUME_ONLY_WHAT_THEY_MADE`) checked by text; (c) QA lead replies at the output
cap 14%, cause: one holistic verdict over a 42k-token request with reasoning on.

## 3. The first review's items in this area

- **Q1** BUILT (LF.678) but partial: one bucket for 36 checks; the QA lead's findings - 80%+ of what sends a suite
  back - are not recorded. Reshape (HR2.Q.1).
- **Q2** (isolation by pack fixture) OPEN, right: 23 shared-count open items, the dispute's run-alone leg, and four
  shared-count checks (LF.651/654 patched twice) show the cost. Add an executable leg (HR2.Q.3) so the fixture's
  effect is measured, not assumed.
- **Q3** (Python dry run) OPEN, **deprioritise**: today's 11 Python runs recorded one harness finding; pytest's own
  collection errors are already a measured check (`the_suite_failed_in_its_own_words`). No Python false finding in
  the stored lock decisions. Build only when `suite-checks` shows a Python text check below 0.8.
- **Q4** (stub + seeded-fault validation before the lock) OPEN, **drop the stub leg**: a contract-conforming stub is
  another model artifact that can be wrong, and before a product exists the harness already knows every test must
  fail (`already_passing`, `vacuous_green`). The seeded-fault leg exists as `MUTATION_GUIDED_TESTS` at sprint end and
  mutation at release; what is missing is scoring it right and acting on survivors (HR2.Q.6, Q5).
- **Q5** (browser mutants) OPEN, keep as a switch, after HR2.Q.6: 21% false acceptance on browser/full-stack and the
  survivor kinds (boolean logic, which is what a filter predicate or a view check is) say where to aim.
- **Q6** (executable dispute verdicts) OPEN, reshape: the executable legs exist (run alone, service up, dry run,
  contract status); what remains textual is the quote guard. Replace quoting with choosing (HR2.Q.5).
- **Q8** (relational assertions) OPEN, narrow it to a harness-made probe on contract list routes (HR2.Q.8); the
  research's 44% false-alarm rate for model-written properties argues against asking QA for them in prose.

## 4. Research (web, 2026-11-07; details in the digest)

- **Meta TestGen-LLM** (FSE 2024, arXiv 2402.09171): keep a test only if it builds, passes, passes 5 times, adds
  coverage; 57% of candidates passed reliably. **ACH** (FSE 2025, arXiv 2501.12862): mutants made per concern; a test
  kept only if it passes on the original and kills the mutant; equivalent mutants: strip comments, drop identical,
  LLM judge yes/no/unsure with "unsure" treated as equivalent (0.95/0.96 after pre-processing); 49% of kept tests
  added no coverage but killed a fault.
- **Qodo Cover** (Nov 2024, docs): keep on run+pass+coverage gain, 5-run flakiness check; **Mathews & Nagappan**
  (arXiv 2412.14137, Dec 2024): 60-68% of CoverAgent/CoverUp suites validated the bug - "pass on current code" turns
  every bug into a locked regression; all bug-revealing tests were discarded by the filter.
- **SWE-bench Verified** (Aug 2024): FAIL_TO_PASS and PASS_TO_PASS both required. **SWT-bench** (NeurIPS 2024, v3
  Feb 2025): keeping only patches whose generated tests are all F2P/P2P doubles precision to 47.8%. **OmniCode**
  (arXiv 2602.02262, May 2026): a test is correct only if it passes the gold patch and fails every known-bad patch;
  requiring failure on bad patches cuts scores 2-5x, i.e. gold-only validation accepts vacuous tests. **UTBoost**
  (ACL 2025): 345 SWE-bench patches wrongly labelled passing for lack of tests.
- **Oracles**: Konstantinou et al. (arXiv 2410.21136, v2 Oct 2026): LLM oracles capture actual behaviour, not
  expected; Bodicoat et al. (AIware 2025): count an oracle correct only if it fails the buggy and passes the fixed
  version; TOGLL (2024): 47% false-positive assertions for neural oracles. **Agentic PBT** (NeurIPS 2025 w/s, arXiv
  2510.09907): 56% of property reports valid, a ranking rubric lifts the top to 86%. "LLM test generators with newer
  LLMs" (arXiv 2601.09695, Jan 2026): ~20% uncompilable, ~43% fail an assertion before repair.
- **Playwright docs**: one fresh context per test, start clean rather than clean up, `testInfo.testId` for unique
  backend ids, serial mode "not recommended", separate accounts per worker when tests mutate server state, web-first
  assertions. **pytest**: function-scoped fixtures and `tmp_path` per test.
- **Dispute/"which is wrong"**: no 2025-2026 system reaches a measured verdict by LLM judgement alone (judges below
  AUROC 0.65, arXiv 2606.09863); every measured one executes against a reference (gold patch, mutant,
  counter-implementation). UTDebug (arXiv 2502.01619) trusts a test only after its oracle is validated.
- Fit here: the locked suite is validated one-sidedly (everything fails on the scaffold) and the only two-sided
  evidence - mutants - arrives at release and is not acted on. Isolation and repeat-pass are executable preconditions
  the leading pipelines apply before keeping a test; the QA lead and the dispute are judgement, which the evidence
  says should rank and explain, not decide.

## 5. New items

**HR2.Q.1 - record every sender of a suite send-back, per check** (bug; S).
Evidence: §2 - 240 of 295 open items are the QA lead's, 13 harness findings recorded in one bucket.
Change: `check_findings.noted` called inside `tests_that_cannot_pass` per check function (name = the function), the
QA lead's findings recorded as check `qa_lead` with the criterion id as the key, and `findings_that_reopen`'s notes
recorded as `noted_not_acted`. `suite_check_settling.py` then reports the QA lead's settle rate beside the checks.
Test: a finding from `locators_that_do_not_exist` is recorded under that name, a QA-lead finding under `qa_lead`
(fails on the old code: one bucket, no `qa_lead` row). KPI: per-check precision (Q1's), lock rounds.

**HR2.Q.2 - a non-finding is not a problem** (bug; S).
Evidence: 49 of 295 open items say there is no finding; they cost send-backs (fast delivery: one) and are shipped as
open problems. Change: `findings_about_the_suite` also drops a line that names no criterion id and no test, and a
line whose verdict clause says there is no finding (a short closed list: "no finding", "acceptable", "is fine",
"correctly" with no test-side fault named); the structured `findings` field asks for `criterion`, `test`, `what is
wrong` as fields (C2-style) instead of a free line, so the filter reads fields, not prose. Test: the stored
non-finding lines above are dropped, the AC-9 shared-store line is kept (fails on the old code). Banned-word test
for the prompt change. KPI: runs locked with open problems (62% now), G1 verdict precision.

**HR2.Q.3 - the suite proves its isolation by running twice** (quality; switch `SUITE_PASSES_TWICE`; M).
Evidence: 23 shared-store open items, run-alone disputes, four shared-count text checks patched twice (LF.651/654);
TestGen-LLM/Qodo keep a test only after repeated passes. Change: at the first measurement where the suite is green on
a product (any round), run it once more against the same running product without a restart; a test green then red
is named as "depends on an empty store or on order" with its name - an executable finding that reopens the suite for
that test only (the targeted repair path). API suites cost seconds; a browser suite runs once more (2-6 min), so the
switch. Replaces the shared-count text checks once measured on parity. Test: a stub runner that passes a test on the
first run and fails it on the second yields the finding (fails on the old code). KPI: false acceptances on
full-stack, shared-count findings, dispute count.

**HR2.Q.4 - dispute outcomes recorded** (bug; S).
Evidence: run-alone, service-stopped, past-the-cap and "quotes what the standard does not say" are warnings only;
`QA_SAYS_THE_PRODUCT_IS_AT_FAULT` never fired in 17 runs. Change: the dispute node writes one decision
(`point="acceptance_dispute"`) with: tests shown, tests the ruling called wrong, passed alone, service stopped, past
the cap, refused for the quote, reopened; `loop.sh disputes` totals them per family and joins the hidden score.
Retire `product_at_fault.py` (0 claims; the rule's quote format is the cause) unless Q.4's data shows a need. Test:
a dispute whose named test passes alone records `passed_alone` (fails on the old code). KPI: dispute precision
(reopened tests whose repair was then overruled or re-disputed).

**HR2.Q.5 - the ruling chooses the standard by id, never by quote** (quality; no switch; S).
Evidence: the quote guard (`_the_standard_holds`) needed LF.628/633/640/641 and still refuses true rulings; research:
no measured verdict rests on wording. Change: `DisputeRuling.the_standard_says` becomes `standard_id` chosen from the
list the request shows (criterion ids, contract line numbers, numbered brief lines); the harness attaches the text
itself; a ruling naming no listed id reopens nothing. The executable legs stay in front. Test: a ruling with a
paraphrased quote and a right id reopens; one with a verbatim quote of the instructions and no id does not (fails on
the old code). KPI: wrong dispute outcomes (Q.4's record), repairs per run.

**HR2.Q.6 - mutation scored and acted on** (bug for the score; switch for acting; S+M).
Evidence: 15% of mutants broke the product outright and count as caught; 218 release gaps nobody acts on; boolean
operators survive 50-80%, comparisons 5-26%. Change (bug): `everything_failed` counts as inconclusive in `score`
(`mutation.py:88-94`), `mutation_score` in the ledger regenerated; the release's 3 changes drawn from the operators
with the highest survivor rate in the stored data (a table in `mutation.py`, not per stack). Change (switch
`MUTATION_SURVIVORS_TO_QA`): at release a survivor is one bounded finding to the testing role (the
`mutation_guided` path, already built) instead of a gap - at most 3, one try each. Test: a file whose mutants all
turn every test red scores None, not 1.0 (fails on the old code). KPI: mutation score (E5), survivors shipped.

**HR2.Q.7 - the QA lead reviews a delta after the first round** (efficiency; switch `REVIEW_THE_SUITE_DELTA`; M).
Evidence: 12.2k output tokens a call, 14% at the cap, 6.2 min a run, 3 rounds re-reading a 42k-token request.
Change: round 2+ shows the diff since the last review and the last findings each marked settled/open by the harness
(Q.1's record), with the whole suite available by tool; the verdict schema asks per finding only `settled: true|false`
plus new findings. Test: the round-2 request carries the diff and the prior findings and not the whole suite text
(fails on the old code). KPI: review minutes, output tokens, lock rounds; hidden score unchanged.

**HR2.Q.8 - contract-derived relational probe for filtered lists** (quality; switch `CONTRACT_LIST_PROBE`; M).
Evidence: blind spots are filter/order cases (filtered action x12, filter by tag x4, newest first x2, only your own
items); PBT written by models is 44% false alarms, but a probe the harness writes from the contract is not a guess.
Change: for a contract line `GET <route>?<field>=<value> -> 200` (or an order the specification names), the probe
makes 3 records through the contract's write line (`with_a_record_made_first`), reads the list, and asserts every
returned record has `field == value`, that each made record with it is present, and (order) the sequence is sorted
by the named key; a miss is a defect like the other probes. Pages: no (Q5 covers). Test: a stub answering an
unfiltered list fails the probe (fails on the old code). KPI: hidden failures on filter/order tests, false
acceptances on APIs/full-stack.

**HR2.Q.9 - probe coverage recorded** (bug; S).
Evidence: bad-body 2, emptied-field 1, server-error 0 among 1,421 gaps; emptied-field defects 4 of 7 closed without a
fixer; nothing says which lines were probed. Change: `.harness/contract-probe.json` with lines checkable / probed /
skipped (reason: no body, page line, sign-in failed, write refused) per probe kind; `loop.sh effects` reads it. Test:
a contract with one page line and one write records one skipped with its reason (fails on the old code).

**HR2.Q.10 - audits read work minutes, not wall minutes** (bug in tooling; S).
Evidence: three of today's five longest "stages" were deploy gaps (83, 73, 44 min). Change: `run_timing.py` and
`audit_live.py` subtract gaps over 10 min between records and print both. Test: a transcript with a 20-min gap in
one stage reports its work minutes (fails on the old code).

**HR2.Q.11 - a standing blind-spot report** (tooling, host side; S).
Change: `scripts/loop/blind_spots.py` (`loop.sh blind-spots`): per family and hidden test, failures in partial-score
runs since the last LF row that named the test, so a recurrence after a fix shows at the next audit (owner:
sum recurring notes). No run code changes.

Not proposed: a Python dry run (Q3) and a pre-lock stub (Q4's first leg) - see §3.

## 6. Priority order

1. **HR2.Q.1 + Q.2 + Q.4 + Q.9 + Q.10** (bugs, S each, one bundle): nothing in this area can be judged without them;
   Q.2 alone removes about 17% of open problems and one send-back in the runs that carry a non-finding (~5-8 min
   each, a third of runs).
2. **HR2.Q.6 (score part)**: one line, corrects a KPI the gate will rest on (E5).
3. **HR2.Q.3** (run twice, switch): the measured replacement for the shared-count text checks and most of Q2's
   motivation; expected to cut full-stack false acceptances (5 of 19 runs) and the shared-store rounds; 0.1-6 min a
   run.
4. **HR2.Q.5** (choose by id): removes the quote guard's patch stream; S.
5. **HR2.Q.8** then **Q5** (browser mutants) then **HR2.Q.6 (acting part)**: the blind-spot list says filter/order
   and view/action are where the score is lost; expected +1 hidden test on the runs that now score 0.875-0.9 in
   those families.
6. **HR2.Q.7** (review delta, switch): ~4 min and ~300k output tokens a run when a suite goes three rounds.
7. Q2 fixture, Q3, Q4-stub: after the above measure; Q3 and the stub likely stay unbuilt.
