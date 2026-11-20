# Suite repair flow: design review (2026-11-20)

Why: four point fixes in one subsystem today (LF.1177, LF.1183, LF.1188, LF.1189), so the owner's rule asks for a whole-design review. The code was read at `68bd6263`. The live data comes from run-2df00e65 (tasks-api), read-only from `langchain-worker-1` at 07:29 UTC (16:29 JST). Times below are UTC, and JST is UTC+9.

Deployed state: the worker has LF.1188 (`began=` is in `/app/src/app/graph/rewritten_tests.py`). It does not have LF.1189 yet: `/app/src/app/acceptance/suite.py` has no `REPAIR_BEST_DIR`. The worked example therefore shows the bug LF.1189 fixes, not the fix itself.

## 1. The flow, end to end

**How the suite is reopened.** There are three entry points, and all of them call `reopen_the_suite_for` (`src/app/graph/acceptance_nodes.py:2644`):

- A test round. `acceptance_for_round` (`acceptance_nodes.py:2545`) runs the suite. Its "cannot pass" list comes from `suite.findings_that_reopen` (`src/app/acceptance/suite.py:6095`) applied to `tests_that_cannot_pass`, plus a few other checks. The round's caller is `src/app/graph/nodes/triage.py:84-88`.
- A dispute (`src/app/graph/nodes/reviews.py:420`). The tests that remain after running alone (`tests_that_fail_alone`), the service-stopped filter and the reclassification cap are sent. Past the cap, `contested_tests.confirmed_past_the_cap` can add tests (`src/app/graph/contested_tests.py`).
- The naming send-back (`naming_back_to_qa`, `acceptance_nodes.py:2805`). It records `NAMING_REPAIR`.

A budget limits reopens: `may_repair` (`acceptance_nodes.py:2279`) allows `MAX_SUITE_REPAIRS = 2`, or up to 4 when the tests are new to repair.

**Recording the repair.** `reopen_the_suite_for` calls `suite.repairing` (`suite.py:472`). That call writes three things into `acceptance.json`:

- `repairing`: the names of the tests sent.
- `repair_bodies`: each test's code as it was first seen.
- `before_repair`: taken once, from `last_result` (`suite.py:492`), as passed + failed.

**The one-call rewrite.** `_rewritten_in_one_call_each` (`acceptance_nodes.py:2619`) calls `rewritten_tests.repair` (`src/app/graph/rewritten_tests.py:234`), which runs behind `NAMED_TEST_REWRITE`. It reads the test bodies (`:321`), unlocks the suite, writes the rewrite, and records the rewritten titles, including siblings, with `began=` (`:333`). When it succeeds, the flow goes straight to `acceptance_review` with round 1. Otherwise QA's author loop gets the work at round 0, with `REPAIR_RULE`.

**QA's request.** `build_author_request` (`src/app/acceptance/requests.py`) sends the findings under "What the last review of this suite found". It adds `THE_PRODUCT_DOES_NOT_START_YET` (`:273`) when the product is not starting. It decides "partly built" from `last_result().passed` (`:334`).

**The review** (`acceptance_review`, `acceptance_nodes.py:982`) runs in this order:

1. `_the_repair_measured` (`:959`): put back the tests the repair was not sent for (`suite.py:755`), run the suite, check `a_repair_that_made_it_worse` (`suite.py:496`).
2. If worse, `put_back_the_best_of_the_repair` (`suite.py:584`; the lock when no best is saved) and run again (`:996-1009`).
3. `keep_the_best_of_the_repair` (`suite.py:545`, `:1012`).
4. The checks, including `tests_left_unrepaired` (`suite.py:429`, `:1048`) and `check_findings.withheld` (`:1098`).
5. The limits: 3 rounds (`MAX_ACCEPTANCE_ROUNDS`), +2 when the suite does not run or proves nothing, +2 more while cannot-pass findings shrink, and the once-at-the-limit send-backs (`:1107-1155`).
6. The targeted lock (`TARGETED_SUITE_REPAIR`, `:1160`) or the QA lead's review, then `suite.lock` (`suite.py:364`, `:1253`), which clears the repair state, the best version and the last-review findings.

When the rounds run out on a suite that cannot run or proves nothing, `_kept_as_locked_before` (`acceptance_nodes.py:2592`) puts back the lock snapshot and locks it.

## 2. Worked example: run-2df00e65

There were three reopens after the first lock. The worker log only covers the time after 06:50:59, when the container restarted. Reopens 1 and 2 are rebuilt from `.harness/acceptance-history.jsonl`, `check-findings.jsonl`, `acceptance-locks/`, `decisions.json` and the workspace git log, so their start times are approximate.

| # | Opened | What reopened it | What happened | Locked | Open |
|---|---|---|---|---|---|
| 0 | first writing | - | Rounds 1-5, 05:48-06:06. At round 2 (05:50:59) LF.1177 withheld the true finding "`test_ac4_items.py` line 106 signs in as `notinstore`" (see 3a). The QA lead listed 9 sign-in-without-sign-up tests. | v1 06:06:17 (15:06 JST), with those open (DR-14) | - |
| 1 | about 06:12:50 | suite check, the `notinstore` finding (DR-16); product not starting (0 of 62) | One-call rewrite: `_signup` added to 3 tests (v2.diff). The reviews at 06:13:27, 06:16:46, 06:20:18 and 06:25:12 all said "has not changed `test_ac3_create_item_success_returns_201`, `..._title_is_string`", which v2.diff shows were changed. This is the LF.1188 bug. | v2 06:25:12, with that false problem open (DR-17) | about 12 min |
| 2 | about 06:33-06:35 | `test_ac15` 'owneruser' collides (DR-18) | Review r1 at 06:36:20, measured 24/62, said `test_ac17_start_sh...` "has not changed it". v3.diff shows it was changed (the same bug, for a sibling). | v3 06:45:13, QA lead approved (DR-19) | about 10-12 min |
| 3 | 06:55:28 (15:55 JST) | dispute: 3 AC-12 tests (DR-20), before = 52/62 | 06:56:03: one call rewrote 6 tests. 06:56:26: measured **57/62**, sent back for 1 finding ('multiuser' collides). QA's author loop ran until 07:06:15, then put back 3 tests it was not sent for: 61 tests, 58 passing. Undoing that put-back gave 61/59. That was still "worse" (61 < 62), so at 07:07:10 "put back 5 file(s) as locked" (no best was kept, because LF.1189 is not deployed). 07:07:35: measured 52/62. The send-back said "worse" **and** "has not changed" the 3 tests (finding `54cb424f2383`), although it was the harness that reverted them. QA redid the work until 07:16:23. The targeted lock took 58/62. | v4 07:16:23. v4.diff holds exactly the 6 rewritten tests plus a renamed user. DR-21 says "the QA lead approved", but the log says "locked again on the harness's checks". | 20 min 57 s |

In total the suite was open for about 43-46 minutes after the first lock, in a run that had been going for about 2 hours. One fault class, a sign-in with no sign-up, was known at the first lock in 9 tests. It was repaired over three reopens, 3 tests at a time and then 6.

## 3. Pieces of state that can disagree

The pattern behind LF.1188 and LF.1189 is the same: a check reads one record while a different writer has changed the thing that record describes.

| State | Writer, when | Readers | Disagreement |
|---|---|---|---|
| `repair_bodies` (`acceptance.json`) | `repairing`, first sight per name | `tests_left_unrepaired`, `keep_the_best...changed` | **a.** After a put-back to the lock, the current code equals the start, so the check says "has not changed" when the harness did the reverting. **Confirmed live**, 07:07:35. |
| `before_repair` | `repairing`, once, from `last_result`, as passed + failed (skipped left out) | `a_repair_that_made_it_worse`, `keep_the_best` | **b.** It is compared with `_counted` (`suite.py:525`), which counts skipped tests as run. A repair that turns failing tests into skips is therefore "no worse" and can become the best. Found by reading the code. **c.** If the product did not start (as in reopen 1, 0/62), every 62-test version is "no worse", so nothing measures the repair. |
| `repair_best` plus `acceptance-repair-best/` | `keep_the_best` after each review | `a_repair_that_made_it_worse` (message only), `put_back_the_best` | **d.** The best is used for a put-back only after the suite is "worse than before". The limit lock, the targeted lock and `_kept_as_locked_before` (which puts back the snapshot) never consult it. |
| `acceptance-snapshot/` (the lock) | `lock` | the put-backs, `tests_a_repair_would_drop`, `only_the_repaired_tests_changed`, `put_back_tests_the_repair_was_not_sent_for` | These checks measure the change against the lock, while the put-back may restore the best. This is consistent today, but it is a third baseline beside "before" and "best". |
| `acceptance-result.json` (`last_result`) | every `suite.run`, including the runs of half-repaired versions inside one review | `before_repair`, `requests.py:334` "built", `the_product_did_not_start_when_last_measured`, `_failed_on_its_own_code` (`suite.py:704`), the failure messages for the rewrite | **e.** `_failed_on_its_own_code` judges the current text against the previous version's failure. **f.** A repaired version with 0 passing makes QA's next request say "Nothing of the product's features is built yet... expected". Both found by reading the code; neither verified live. |
| `check-findings-last-review.json` | `withheld` at each review; deleted at the lock | `withheld` | **g.** `_key` (`check_findings.py:126`) is the check, plus the wording with values stripped, plus the `test_\w+` names. For a Python finding that names a file and a line, that name is the file stem. So every "signs in as nobody" finding in `test_ac4_items.py` has the same key (fingerprint `9bc51e5e2d74` with name `test_ac4_items`), which I verified on the live rows. The new line-106 finding was held back as "unchanged" at round 2, and stayed held through round 5, the lock and reopen 1. **h.** "Repaired" means the digest changed, which also happens when the harness renames or corrects files. |
| `ONCE_AT_THE_LIMIT` flags plus `suite-before-the-send-back.json` | `acceptance_review` at the limit | the send-backs, `_put_back_before_the_send_back` | **i.** These are cleared by `_the_send_backs_spent` (`:951`), which only the normal lock path calls. `_kept_as_locked_before` locks without calling it, so the next reopen loses its once-at-the-limit send-backs and can later restore an old suite. Found by reading the code. |
| graph state `suite_repaired_tests` vs `acceptance.json` `repairing` | `reopen_the_suite_for` vs `repairing` plus the rewrite's siblings | `may_repair` vs the suite's checks | **j.** Siblings are under repair for the checks, but they count as "fresh" for the budget. |
| `problems` from `suite.gaps` | `_the_repair_measured`, before any put-back | the send-back | **k.** After a put-back of the best or the lock, the gaps of the worse version are still sent. |
| decision rationale | the lock path | the Sprint Record, release | **l.** The record says "the QA lead approved" on a targeted lock that the QA lead never read. **Confirmed live** in DR-21. |

## 4. A simpler model: one repair record

Keep one file, `.harness/suite-repair.json`, written only by a new `app/acceptance/suite_repair.py`, and have every check read it:

- `opened`: the time, the findings, `lock_version` and the trigger (round, dispute or naming).
- `sent`: for each test, its file, title and code at the start. Siblings are added with their own start code.
- `versions`: a list. Version 0 is the lock as measured at the reopen. Each later version records who wrote it (rewrite, QA, or harness put-back), the suite digest, its files under `.harness/suite-repair/vN/`, and the number of tests run (skipped not counted), passed and failed. It also records whether the product started, plus the failing names.
- `best`: the index of the best version that ran the most tests and, among those, passed the most. A version measured while the product was not starting cannot be best, except version 0.

The rules all read from that record:

- After each measurement, a version worse than `best` is replaced by `best`. Version 0 is the lock, so "best or lock" stops being a special case.
- "Not repaired" means no version written by the writers ever changed the test. A put-back is a harness version, never a writers' version.
- `withheld` compares findings across writers' versions only, and identifies them by the test titles at the lines they name.
- The final lock locks `best`. This covers the limit, the targeted lock and running out of rounds.
- The once-at-the-limit flags and the send-back copy live inside the record, so they die with it at every lock.

Together this removes `repairing`, `repair_bodies`, `before_repair`, `repair_best` and `suite-before-the-send-back.json` as separate stores.

## 5. Remaining limits

1. "Worse" is measured against the suite before the repair: a 54/62 version after a best of 57/62 stays, and at the limit it is locked (d).
2. Running out of rounds locks the old version even when a better one was measured (d), and leaves the limit flags set (i).
3. A version running one test fewer is worse however many it passes. That is right, but without a kept best it cost the live run 61/59 -> 52/62.
4. Each version is measured once, so one flaky pass can make a version the best.
5. A reopen sends only the finding that triggered it. The faults recorded at the lock for the same tests are not sent. In the live run, 9 tests with one fault took three reopens. When the product is not starting, siblings are switched off (`rewritten_tests.py:286`), which is exactly when reopen 1 happened.
6. A send-back after a successful one-call rewrite goes to QA's whole author loop. In the live run, renaming one user took about 10 minutes.
7. LF.1189 is merged but not deployed in `langchain-worker-1`.

## 6. Ranked changes

1. **One best-version rule for every exit.** Compare "worse" against the larger of before and best. `_kept_as_locked_before` and the limit lock put back the best when the current version is worse than it.
   - Removes: limits 1 and 2, and disagreement d.
   - Risk: low, since only the choice of a measured version changes.
   - Test: before 52/62, best saved at 57/62, current 54/62. `acceptance_review` must put back the best; today it does not. Also, `_kept_as_locked_before` with a best saved must restore the best; today it restores the snapshot.
   - Sure fix.
2. **"Not changed" is true only for the writers.** `tests_left_unrepaired` must not report a test the harness put back. When a put-back happened in this review, the send-back says the harness restored the version and names the tests to redo.
   - Removes: disagreement a (live, 07:07:35).
   - Risk: low.
   - Test: start a repair, change a sent test, make the suite measure worse with no best saved, and review. Today the result includes "has not changed"; the test asserts it does not. If the wording changes, add the banned-word test.
   - Sure fix.
3. **The `withheld` key uses the titles at the named lines** (`suite._the_tests_at`, `suite.py:6063`), or keeps the line and quoted values, not the file stem.
   - Removes: disagreement g (live, rounds 2-5).
   - Risk: low. Fewer findings are held back.
   - Test: findings for lines 50 and 106 of the same Python file, two different users, with a repair between them. Today the second is held back.
   - Sure fix.
4. **Clear the limit flags and the send-back copy inside `suite.lock`.**
   - Removes: disagreement i.
   - Risk: low.
   - Test: set `cannot_pass_repaired_once` and the copy file, then run `_kept_as_locked_before`. Today both survive.
   - Sure fix.
5. **One counting function, with skipped tests not counted as run**, used by both `before_repair` and `_counted`.
   - Removes: disagreement b.
   - Risk: low.
   - Test: before 52 passed and 10 failed; after 52 passed and 10 skipped. Today this is "no worse"; it must be worse.
   - Sure fix.
6. **Re-read the gaps after any put-back, and say "locked on the harness's checks" on a targeted lock.**
   - Removes: disagreements k and l.
   - Risk: none.
   - Test: a put-back after a version that dropped a test's tag must send no gap for it; today it does. A targeted lock's rationale must not claim the QA lead approved.
   - Sure fix.
7. **The repair record of §4**, as a refactor that carries the tests from items 1-6.
   - Removes: five stores and three baselines.
   - Risk: medium, because it touches every reader.
   - Test: the existing repair tests plus 1-6, and one new test that a version measured while the product was not starting cannot become the best.
   - Sure in its behaviour, so no switch. Measure repair minutes per run before and after.
8. **A reopen carries the lock's open problems that name the same tests or files and the same check.** With the product not starting, siblings are found by the same static finding, not by the failure message.
   - Removes: limit 5. In the live run that was about 30 minutes over two reopens.
   - Risk: a larger repair, and more tests changed per reopen.
   - Test: a lock with 9 open findings of one check across 3 files, reopened for one of them, must send all 9; today it sends 1.
   - Measure behind a switch.
9. **A send-back of test-level findings after a successful rewrite goes to the rewrite again**, falling back to QA's loop.
   - Removes: limit 6.
   - Risk: the rewrite could loop on a finding it cannot fix, so cap it at once per review.
   - Test: after a rewrite, a 'multiuser' collision finding must route to the review stage; today it routes to the author.
   - Measure, extending `NAMED_TEST_REWRITE`.
10. **QA's request decides "built" from the product, not from the last suite run, while a repair is open** (disagreement f).
    - Risk: low.
    - Test: repair open, product started, last result 0 passed. Today the request contains `NOT_BUILT_SO_IT_FAILS`.
    - Sure fix. Not seen live.

## 7. Not verified

- The start times of reopens 1 and 2 are inferred, because the worker log before 06:50:59 is gone.
- I did not verify live whether withholding the line-106 finding caused the v1 lock to keep it open. The QA lead did list it at round 4.
- Disagreements b, e, f, h, i, j and k come from reading the code, not from live data.
- The deploy time of LF.1188 is between 06:36 and 06:55, judging by the 06:36:20 "has not changed" row and the 06:50:59 restart.
