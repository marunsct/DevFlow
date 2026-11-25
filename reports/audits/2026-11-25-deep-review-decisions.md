# Deep review 2026-11-25: decisions made on wrong or partial data

Aspect: every place the harness decides something by itself (resolve a design finding, lock a suite, close / keep /
revert a fix, end an attempt, plan a sprint again, stop on time), checked against the real decision logs, ledgers,
transcripts and workspaces. Read-only; nothing in `src/`, `tests/`, config or docs was changed. All times JST.

**Data read.** Live runs run-32362f3b (Medium 4, thorough) and run-2f653f55 (fullstack-bookmarks, fast): full
transcripts, `.harness/` ledgers, `docs/decision_log.md`, git history of both workspaces (state at 23:35 JST).
Decision-type records (`defect`, `time_budget`, `resumed`, `foundation_smoke`, `fix_order`, `model_error`) of the 45
most recent transcripts: 3,102 defect events in 43 runs. Full transcripts of 16 runs for the fixer write check.
Not re-reported: LF.1318-1407 and FX.1-FX.11, except where a decision they made or left is judged below.

**How the two runs ended (read after they finished).** Medium 4 stopped at 23:43 JST (DR-31, "stop the run ... not
deliverable"): sprint 1 passed 9 of its 21 tests after 9 h 53 min, the time budget read 389 active minutes against
218, four defects raised by the last test round got no fixer, and `ARRAY` was still in `models.py`. Findings 1, 2, 4,
5, 7 and 9 are that run's chain, in order. fullstack-bookmarks was delivered at 00:41 JST on 11-26 with 32 of 32
tests after 6 h 54 min, against about 66 minutes for the family; findings 3 and 8 account for about 3 h of it.

## Summary table

| # | Decision | What it used | How often | Cost |
|---|---|---|---|---|
| 1 | Design finding "resolved" | the reviewer's word on a claim the specification makes about a library | 3 of the 6 round-5/6 gating findings of Medium 4 rest on a false or unbuildable claim | Medium 4 failed: sprint 1 took 9 h 53 min for 8 -> 9 of 21 tests, the blocker still in the code |
| 2 | "Plan the sprint again" | one line ("passes 8 of 21"); no failure output, none of the 5 open defects | every re-plan; 1 live case read in full | the lead guessed a cause the harness's own measurement contradicts; the tester's real finding never shown again |
| 3 | Suite locked (fast delivery) "with these still open" | the round count, not what the open finding says | 2 locks in the live fast run, both with a "fails on a correct product" finding open | about 2 h of suite repair, found only after 88 min of fix rounds |
| 4 | Defect "fixed" / "its own tests still fail" | unit tests that mention the defect's file, for a defect no test was raised from | false "fixed": 5 in Medium 2; false "still fail": 1 live | fixes closed that the next round raised again 6 h later; a made fix counted as failed |
| 5 | "The fix changed nothing" | `git status` of the whole workspace, which sees the harness's own files | 7 fix attempts in the two medium runs with transcripts | a fix never written is recorded "its tests still fail" and shown so to the next fixer |
| 6 | "A fix round left the product unchanged": end the attempt | a fingerprint the harness's own revert restored | 11 of 11 firings, 8 runs | 9 sprints planned again, 2 escalations, for a fix that was written and reverted |
| 7 | Criterion "currently PASSED" | tests the suite gate itself said pass with nothing built | 3 of 6 sprint-1 criteria of Medium 4 | "still failing: AC-1, AC-8, AC-13" leaves out migrations that never run |
| 8 | Product changes of a batch put back, tests kept | any one regressed acceptance test; the net gain not weighed | 2 times, 1 run (of 59 workspaces) | 54 min: the same rewrite made three times (12 -> 19 tests twice discarded); no ledger event |
| 9 | Sprint time budget after a re-plan | a clock that started at the first plan | 1 (Medium 4) | the re-planned attempt began past twice its old budget and was ended by it after two fix rounds; the run stopped |
| 10 | "Changed by stage X" in an edit refusal | a stale last-writer record | 1 seen | the fixer is told a build stage is working alongside it |

---

## 1. A gating design finding is resolved on the reviewer's word about a claim nobody checked

**Evidence (run-32362f3b, `technical_specification`, 12:57 JST; `docs/decision_log.md` DR-21, DR-22, DR-23).**

- DR-22, finding G16 (major, "ARRAY column type is not addressed for SQLite compatibility"): *resolved in review
  round 6*, "the re-review says it is resolved", quoting specification line 22: "In SQLite (used for development and
  testing), SQLAlchemy maps ARRAY columns to JSON type ... The ORM layer handles this transparently". That sentence is
  false. The product's `models.py` (lines 145, 148) and `alembic/versions/001_initial.py` (lines 77-78) use `ARRAY`,
  and the tester's round found at 20:15 JST "SQLAlchemy ARRAY type blocks SQLite table creation in test fixtures" (the
  `'SQLiteTypeCompiler' object has no attribute 'visit_ARRAY'` error of the brief). `ARRAY` was still in both files when the
  run was stopped.
- DR-21, finding G15: resolved on "database.py calls alembic.command.upgrade(engine, 'head')" (specification lines
  107, 153). That call does not exist in that form (the command takes a configuration, not an engine). The built
  `database.py`/`alembic/env.py` end in a `_do_run` that only starts a transaction; three fixers (22:13, 22:14, 23:00
  JST) tried to repair it and were refused by the edit checks.
- DR-23, finding G17: resolved on "each acceptance test runs in its own Playwright worker process with a separate
  SQLite file ... via the workerId property". The finding itself says the harness starts the product once; the
  answer cannot be built under the harness's own test setup, which the product may not change. The tester later
  reported the consequence (one server, one in-memory rate limiter, 429s between tests).

The reviewer's quotes are in the document (checked: every round-5/6 quote is found in the final specification), so
"is the quote there" would not have caught it. What was wrong is the kind of evidence: a sentence about how a
third-party library or the harness's own setup behaves was taken as settling a finding that asked exactly whether
that behaviour holds.

**Root cause.** `src/app/graph/design_gate.py:182-184`: an earlier gating finding is resolved when the re-review's
answer says so; the answer's text is recorded as the reason and nothing classifies what it rests on. The same holds
for line 195 ("the re-review no longer finds it").

**General.** Every thorough run. In this run 17 gating findings were resolved this way; 3 of the last 6 rest on such a
claim. Medium 2 and 3 failed on the same family of facts (tables never created, routes not mounted).

**Cost.** Sprint 1 of Medium 4 started 13:50 JST; the run was stopped at 23:43 JST with 9 of 21 tests passing, 8 of
which passed before anything was built. The three claims are three stacked blockers (migrations not run, ARRAY on SQLite, one shared
store between tests).

**Fix (always on, stack-agnostic).** When a finding is resolved, the gate records what the resolution rests on. A
resolution whose text asserts behaviour of something outside the specification (a library, a tool, the test setup)
is recorded as *resolved on an assumption* and becomes a proof obligation: the first work order of the first sprint
that touches it must show it with a command the harness runs (here: create the tables on the test database), and the
foundation smoke asks it before any fixer is sent. An assumption that contradicts a fact the harness holds (the
product is started once per suite run - already in the reviewer's prompt) is refused at the gate. Stack facts that
are known false (a column type one engine has and the other does not) belong in the pack's known-errors list.

**Test from real output.** Feed `_after_a_review` the real round-6 review answer for G16 (captured in the
transcript, `architecture_review`, 12:56-12:57 JST) and the real specification; assert the entry is recorded as
resolved on an assumption with the quoted sentence, not plainly resolved.

## 2. A sprint is planned again with no evidence of why it failed, and its open defects are dropped

**Evidence (run-32362f3b, `technical_lead`, request of 20:15:38 JST, 163,325 characters).** The whole reason given
to the lead is one paragraph: "Plan sprint 1 ... again: later sprints build on it, so its failing criteria (AC-1,
AC-8, AC-13) cannot be deferred. Evidence: the plan has sprint 2, 3 depend on sprint 1, which passes 8 of its 21
acceptance tests. Find the one cause behind these failures first - the step they all stop at". The request holds
no failing test's output, no first failing step, and none of the five defects the test round had raised one second
earlier (searched: "blocks SQLite", "Defect (open)", "visit_", "time budget" - none present; "ARRAY" only inside the
specification's own text). The escalation's decision record (DR-30) lists those defects; the model that must act on
the decision does not get them.

What the lead then did: read files for 19 minutes and decided, seven times over in near-identical replies, that
"`command.upgrade()` is called synchronously ... the entire FastAPI app cannot start". The harness had measured the
opposite: the product starts, `/api/health` answers, 8 tests pass. The new plan's work order was built on that guess
("Fix the root cause of all auth endpoint failures: database.py line 91..."), the next code review and two fixers
inherited the phrase, and the tester's defect `be476bcb37` (ARRAY) does not appear in any record after 20:15:37 JST:
the new attempt's first test round (21:37 JST) raised three defects, none of them it.

**Root cause.** The re-plan's requested change is the foundation rule's one line (`src/app/graph/foundation.py:107-112`),
and a re-plan starts a new remediation cycle: the old cycle's defects, with what their tests printed, stay in the
Sprint Record only. FX.3 ("defects keep printed errors") keeps the error inside a defect; it does not carry the
defects across a re-plan.

**General.** Every "plan the sprint again": 80 defects were left open with "exhausted remediation attempts; the
sprint is planned again" and 182 with the time-budget form across the 43 runs. Only this one request was read in
full, so the count of re-plans that guessed wrong is not known.

**Cost.** From 20:15 JST to the stop at 23:43 JST (3 h 28 min) the re-planned attempt worked on the guessed cause;
one test gained, and the run failed.

**Fix (always on).** The re-plan request carries, measured by the harness: the open defects of the attempt that
ended, each with its printed error; the first failing step of the failing tests grouped by cause (the grouping the
fix round already makes); and what the harness knows to be true that bounds the diagnosis ("the product starts and
answers its health check"). Open defects from sources other than the suite (tester, code review) are carried into
the new cycle as open, not re-discovered.

**Test from real output.** Build the re-plan request from this run's state at 20:15 JST (the five `raised` defect
records and the acceptance result are in the transcript and `.harness/acceptance-result.json` of that commit);
assert each open defect's title and the suite's first failing answer are in the request.

## 3. Fast delivery locks a suite with a "fails on a correct product" finding open

**Evidence (run-2f653f55, `acceptance_tests`).** DR-12, 19:34 JST: "lock it ... locked after 3 round(s) with these
still open: AC-11 (tag filter test) ... causes the later AC-12 invalid JSON test to fail its assertion that the
entire list is empty - even though the product correctly rejected" the request. Fix rounds ran 19:40-21:08 JST
against that suite. At 21:09 JST the harness's own check reached the same conclusion (DR-15: "`[AC-12] POST
/api/bookmarks returns 400 for invalid JSON body` cannot pass for any product that does what its criterion says")
and reopened the suite; the repair took until 23:12 JST (three author rounds of 16 to 40 minutes, two deploy
restarts inside them). DR-16 then locked it again "after 4 round(s) with these still open: ... intermittent failures
on a correct product" (UI tests that do not wait for a save).

**Root cause.** `src/app/graph/suite_gate.py:1-21`: the gate applies to thorough delivery only; "Fast delivery ...
lock as before", that is on the round count. The QA lead's finding carried its meaning in words the lock did not
read.

**General.** Every fast run whose review still has a finding at the round limit. This family normally delivers in
about 66 minutes; this run took 6 h 54 min.

**Cost.** About 2 h (21:09-23:12 JST), plus fixers sent at a test no product passes for 88 minutes.

**Fix.** Quality, so always on, both delivery modes: a finding at the lock that says a test fails on a correct
product (the QA lead's severity blocking, or the harness's cannot-pass checks) gets one targeted repair of that
test alone before the lock - the repair DR-15 ordered 95 minutes later. No waiting for a person in fast delivery;
only the order changes. A finding of "intermittent on a correct product" marks the named tests as unstable in the
ledger so that a later regression of one of them alone does not revert a fix (see finding 8).

**Test from real output.** The real review of round 3 (transcript `acceptance_review_2`... the 19:3x JST reply) as
input to the lock decision; assert the AC-12 test is sent for repair, not locked.

## 4. A defect no test was raised from is settled by unit tests that mention its file

**Evidence, false "still fails" (run-32362f3b, `defect_fix_2_4`, 23:11:08 JST).** Defect `d07fb5380d`, raised by the
tester: "JWT HMAC key is 31 bytes". The fixer made the change (23:02:21 JST, `auth.py` line 39, the default now 32
bytes). Verdict: "left open: its own tests still fail, measured after the fix". The tests that "still fail" are the
nine `tests.test_auth` cases failing on `sqlalchemy ... _determine_joins` - the mapper defect another fixer was
working on (`.harness/unit-result.json`, `.harness/ci.json` "after defect_fix_2_batch"). The key-length change has
no test at all. The attempt was counted as a failed fix. In the same measurement the mapper defect itself
(`608a40fa68`, file `models.py`) came out "unverified", because no test's name contains "models".

**Evidence, false "fixed" (run-8f0be29e, Medium 2, sprint 2, 11-23).** Five tester-raised defects with no criterion
tag were recorded `fixed` between 13:02 and 14:20 JST ("Login endpoint returns incorrect response structure", "Task
CRUD endpoints return non-201/non-404", "Priority validation not enforced", "Task assignment to non-existent user
returns wrong status code", "Backend unit test files missing"), each "(no passing command recorded)". The next test
round (20:18 JST) raised the same faults under new ids ("Task creation endpoint returns 404", "Priority validation
tests fail - all ... return 404", "Task assignment ... returns 404"), and at 00:06 JST "Backend unit test suite was
completely missing". Across the 43 runs: 109 `fixed` events, 78 with no passing command recorded; 26 of them
tester-raised with no criterion tag and no failing unit run behind them (some of those are harness probes that are
asked again, which is a real measurement).

**Root cause.** `src/app/graph/workflow.py:3797-3799` (`_the_defect_s_tests_in`): for any defect with no criterion
tag it falls back to `_the_unit_tests_about` (3716-3731: unit tests whose key contains a stem of the defect's
files). The sibling that runs the tests live, `_the_defect_s_tests_pass`, already refuses this at 3677-3682 with the
comment "Passing unit tests answer only for a defect that was raised from failing ones" - fixed in one of the two
functions only. LF.1260 ("no closing on a claim") added the `unverified` branch, but that branch is reached only
when this function says None.

**Fix (always on).** In `_the_defect_s_tests_in`, the unit-test fallback only for a defect that begins with the
unit-tests-fail heading or whose evidence names unit tests; otherwise None, so the defect is `unverified` and the
next round decides. A failing unit test whose failure message is the same before and after the fix is not evidence
against the fix.

**Test from real output.** The real `ci.json` snapshot "after defect_fix_2_batch" of run-32362f3b with the real JWT
defect: assert the result is None (unverified), not False.

## 5. "Changed nothing" is read from `git status` of the whole workspace

**Evidence (run-32362f3b, `defect_fix_1_2`, 22:00-22:15 JST).** The fixer made two edit calls; both were refused
("it would add errors the language service is sure of ... Nothing was written", 22:13:41 and 22:14:11 JST). It ran
one `python3 -c` command, which the harness saved as `tmp-inline-99274923.py` inside the product directory. Verdict:
"left open: its own tests still fail, measured after the fix"; journal entry `files: []` with `did` = the model's
sentence "Changed both to call alembic.command.upgrade(...)". The next fixer's request (22:29 JST) shows it under
the heading "Earlier attempts at this defect, as the harness measured them": "defect_fix_1_2: changed no file; ...
Changed both to call alembic.command.upgrade(...) -> left open: its tests still fail", followed by "Do not make a
change one of them made and was measured making". A change that was never made is listed with a measured verdict
against it. That fixer spent a 12,119-token reasoning pass working out that nothing had been written, then read
`database.py` seven more times and wrote nothing.

Count over the 16 full transcripts, thorough runs only (the fast rewrite path writes without tool calls): 7 fix
attempts with no successful write were settled "its own tests still fail" (6 in run-8f0be29e, 1 here); 4 of them had
run a terminal command. The branch that says "nothing was changed: no file of the product differs" fired twice in
all 43 runs.

**Root cause.** `src/app/ci.py:619-633` (`unchanged_since`): `git status --porcelain` with no path limits, so the
harness's inline-command file, a test database, test reports and the workflow's own `docs/` count as the fixer's
change. The product fingerprint (`src/app/acceptance/unstable.py:79`) already leaves the harness's files out; this
check does not use it. `.harness/acceptance-history.jsonl` shows the same blind spot: two measurements 11 seconds
apart (22:14:59 and 22:15:10 JST) carry different product fingerprints although no product file was written.

**Fix (always on).** `changed_nothing` from the product fingerprint before and after the fix (or the fixer's own
successful write results, which the tool layer already has). The earlier-attempts line for an attempt with no write
says only "wrote nothing: both edits were refused (reason)" - never the model's account of a change, and never a
test verdict. Inline-command files go outside the product directory or are ignored by the fingerprint.

**Test from real output.** Replay the real tool results of `defect_fix_1_2` (two refusals, one inline command) into
the settlement; assert "nothing was changed", no failed-fix count, and that the next request's earlier-attempts line
has no "Changed both".

## 6. "The fix round left the product unchanged" fires only after the harness's own revert

**Evidence.** The rule ends an attempt when two consecutive test rounds measure the same product and no defect was
closed. All 11 firings in the 43 runs came in a round where a fixer did write a fix and the harness reverted it:
run-1d79334d (11-25 09:10 JST, the fix left unused imports in one Go file), run-2c83118a, run-c4fd577a,
run-59135d0b (three times), run-eded4941 (twice), run-4702bef3, run-8c35f01e (twice). Nine ended "the sprint is
planned again", two "escalated to a person". None was the case the rule was written for (fixers that spend their
calls and write nothing).

**Root cause.** `src/app/graph/unchanged_fix_round.py:47-58`: the comparison is the fingerprint and the closed
count. A revert restores the fingerprint. The rule's premise - "the next fix round starts from exactly where the
last one did" - does not hold: the next round would start with the revert's evidence (what the fix broke), which is
new and usually one line from a working fix.

**Cost.** 9 re-plans and 2 escalations in 8 runs; in the Go run the same defect was then fixed four rounds later.
The switch (`FIX_STAGES_THAT_CLOSE_NOTHING`) is recorded as firing and "kept on no measured loss", but what it
measured was reverts.

**Fix.** Behind the same switch: the round counts as unchanged only when no fix of the round was reverted or
repaired forward (the ledger has both events) and no fixer made a successful write. Re-measure the switch after.

**Test from real output.** The real defect-event sequence of the Go run's round 2 (shown, reverted, raised again):
assert `ends_the_attempt` is False.

## 7. Criteria are "currently PASSED" on tests the gate said pass with nothing built

**Evidence (run-32362f3b).** At the lock (13:50 JST, DR-29) the harness recorded: "8 of 21 test(s) pass although
nothing of the product is built yet", naming both AC-12 tests, both AC-15 tests and all four AC-14 tests. From then
on every decision reads those criteria as met: the re-plan request (20:15 JST) lists "AC-12 ... currently PASSED",
"AC-14 ... currently PASSED", "AC-15: Database migrations required - currently PASSED"; the time-budget and
escalation records say "still failing: AC-1, AC-8, AC-13"; `best-attempt.json` counts 9 of 21. AC-15's tests
("service starts with migrations applied") pass while the migration function runs no migration - the very fault
three fixers are trying to reach through AC-1. Progress over 9 h 53 min, read without the eight, is 0 -> 1 of 13.

**Root cause.** The finding lives only in the lock's rationale. `src/app/graph/suite_gate.py:66-72` rates "a test
that passes before anything is built" minor (reasonable for one test of several), and nothing marks a criterion
*all* of whose tests are such.

**Fix (always on).** A criterion whose every test passed before the product existed is recorded "not proven by
its tests" at the lock: gating severity major in thorough delivery (the suite gate then holds it), and in every
later status line shown as "passes, but passed before anything was built" instead of PASSED; pass counts used for
progress, best attempt and the foundation rule leave such tests out.

**Test from real output.** The real 13:34 JST `suspected false finding` record and the acceptance result of the
lock commit; assert AC-14 and AC-15 are not listed as met.

## 8. A batch's product changes are put back silently when any acceptance test regresses

**Evidence (run-2f653f55, workspace git log and `.harness/acceptance-history.jsonl`).**

| JST | Commit | Passing |
|---|---|---|
| 19:40 | Best attempt so far | 12 of 32 |
| 20:02:39 | "defect_fix_1_batch as written, before it is split" (`src/app.js` rewritten, styles, tests) | 19 |
| 20:03:26 | "Fix, its tests only" (`app.js` and styles put back) | 12 |
| 20:37:11 | "as written, before it is split" (`app.js` rewritten again) | 19 |
| 20:37:57 | "Fix, its tests only" | 12 |
| 20:56:20 | third rewrite of `app.js`, kept | 19 |
| 21:08:57 | next batch | 27 |

Twice a change that took the suite from 12 to 19 was discarded because at least one test that had passed did not.
Which test is recorded nowhere: there is no `reverted` event, the worker log of that hour is gone with the deploy
restarts, and the four fixers were settled "its own tests still fail, measured after the fix" / "unverified" - true
of the product the harness had just restored, and silent about why. The suite's own review had said its UI tests
fail intermittently on a correct product (finding 3).

**Root cause.** `src/app/graph/engineering.py:816-850` (`_its_tests_without_its_product_change`) and its call in
`after_a_fix` (about lines 1104-1109): when only acceptance tests broke, the tests are kept, the product is put
back, and the function returns "nothing broken", so no revert is recorded and the fixer is not told. The net gain
is not weighed (a contested test has such a rule; an ordinary one does not).

**General.** Rare: 2 commits of this kind in 59 workspaces, both here. Cost here: 54 minutes (20:02-20:56 JST).

**Fix (always on).** Record the split as what it is (a `reverted` event naming the tests that regressed) and give
that to the next fixer. Before putting a product change back, re-run the regressed tests once alone: an unstable
test does not discard a fix. A batch that gains more tests than it loses on a product that starts is repaired
forward with the lost tests named (the LF.1270 path) rather than put back.

**Test from real output.** The two snapshots around 20:02 JST can be rebuilt from commits `85d16f1` and `e230c35` of
this workspace; assert a `reverted` record with test names, and that the next request for the same defect names
them.

## 9. The sprint clock does not know the escalation planned the sprint again

**Judgement of LF.1396-1398:** right as built (first fix round goes, adopted items counted, failed-call streaks off
the clock). Recomputed from the transcript with the module's own rules at 23:35 JST: 432 active minutes since the
first plan, 31 in reviews, about 21 ending on failed calls: about 380 against 218.

**What is still wrong.** At 20:15 JST the fix round was stopped at 219 of 102 minutes; the escalation then chose
"plan sprint 1 again" (DR-30, "0 of 3 re-plans used") because of the foundation rule, and the new attempt began with
the same clock already past twice its limit (`src/app/graph/sprint_time_budget.py:238-246`, the clock starts after
the previous *sprint*, never after a re-plan of the same one). It ran two fix rounds only because LF.1397 was
deployed into the run and doubled the limit. At its next test round (23:43 JST) the attempt ended on the same clock -
"389 active minutes against 218" - and the run was stopped, with four defects that round had just raised (a second
ambiguous foreign key, the shared rate limiter, the error format, a stub route) never sent to a fixer. Two rules
decided the same question with opposite answers: the escalation spent 3 h 28 min on a re-plan the budget had already
ruled out, and the budget then ended it one round after the tester had found the next causes.

Also on the clock: the gaps between a stop and its resume when shorter than 30 minutes (9 minutes in this run), and
the first request after each restart is rebuilt from the checkpoint untrimmed (measured: 112,444 -> 253,508
characters for `test_round_0` at 21:28 JST; 101,545 -> 185,518 for `defect_fix_2_5` at 22:45 JST), so the call after
a restart is the slowest of the stage.

**Fix.** When the escalation plans a sprint again for its foundation, it grants a stated allowance (the budget of
the criteria still failing) and records it; the clock compares against first-plan budget plus allowances. Gaps that
end on a `resumed` record are off the clock. The request-trimming state is saved with the checkpoint.

**Test from real output.** The head lines (time, stage, kind) of this run's transcript from 13:50 JST on: assert the
budget read at the re-planned attempt's first test round is under its limit, and that the 9 stop-resume minutes are
not counted.

## 10. Minor: an edit refusal names the wrong stage

run-32362f3b, `defect_fix_2_3`, 23:01:49 JST: "the file changed after you last read it - 'specialist_ui_ux_2', a
stage working alongside you, changed it since". The stage that changed `models.py` was `defect_fix_2_4`, in the same
batch; `specialist_ui_ux_2` ended at 19:11 JST. The workspace listing in the 20:15 JST re-plan request likewise says
`database.py`, `models.py` and `routes/auth.py` were "written by specialist_ui_ux_2". The last-writer record is not
updated by fixers (or by parallel stages). Fix: record the writer at every successful write, whatever the stage.

---

## Checked and fine

- **Transcript head parsing for the time budget** (`_HEAD`, the `kind` right after `stage`): matches every record
  kind of the live transcript; `model_error` and review stage names are read correctly (the LF.1399 class of bug is
  not present here).
- **Reverts** (34 in 43 runs): each cites what broke; the odd wording "broke 8 test(s) that passed before it: the
  product did not start before this fix either" was a real unit-test break. No revert on a stale baseline found.
- **"Closed by the round's measurement"** (27) and **"closed without a fixer"** (59): one of 86 came back later (a
  concurrency probe, unstable by nature).
- **"Moved forward"** (4 events): each names a test and a later line or a pass; the live one matches the pass count
  8 -> 9.
- **Deploy restarts**: stages resume from their checkpoint (message counts continue); a fixer that had finished
  before the restart is not run again; the test round entered again returns its first answer.
- **Foundation smoke "not asked"** (41 of 82 records): the rule asks only when a foundation defect is suspected;
  not a wrong decision by itself, though finding 1's proof obligations would give it something to ask.
- **Design-gate quotes**: every round-5/6 resolution quote exists in the final specification; earlier rounds' quotes
  are partly gone because the text was revised after.
- **Call caps** ("left open after N model calls"): 104 events, 103 of them in two runs of 11-22/23; none since.

## Seen at the end, not examined further

- run-2f653f55, 00:18 JST 11-26: with every acceptance test passing, the sprint was "planned again" for one open
  styling fault that the defect itself describes as "none of them holding the sprint"; the re-plan fixed it in one
  rewrite 3 minutes later. A re-plan for a defect that does not hold the sprint is a decision worth its own check.

## Not determined

- Which acceptance tests regressed in finding 8 (not recorded anywhere that survived the restarts).
- How many other re-plans guessed a wrong cause (finding 2): one request was read in full.
- Whether the ten proxy time-outs of 17:49-18:15 JST were helped by the 156,000-184,000-character requests rebuilt
  after the two restarts; the proxy was being set up at that hour, which is the likelier cause.
