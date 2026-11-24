# Product review: web-todo container 6 (run-972956f5-ed2b-457e-8982-577f4a8bcd1d)

**Result (started 14:05 JST 11-24 on :1234, finished 15:02, 57 minutes; mixed versions: bundle 1 deployed into it at 14:32): delivered, hidden 10 of 10, quality 6 of 6, handoff 1.0; locked suite 31 of 31.**

- **What happened.** One architecture review, then an escalation of its open findings. Two suite-authoring passes, 31 tests over 16 criteria, locked. One sprint with three test rounds:
  - Round 0 raised 7 defects. The rewrite path fixed AC-3. Four acceptance defects closed without a fixer once that rewrite made them pass.
  - Round 1 found the unit test importing names that `src/main.js`, a browser script, does not export.
  - Round 2: the sprint's three rounds ran out with every acceptance test passing. The escalation accepted the sprint with the unit test set aside.
- **Lost:** nothing hidden or in quality.
- **What the escalation cost:** no code, milestone or security review ran, since the sprint was accepted at the escalation (DR-16).
  - Across 146 scored runs with this gap, 82 were accepted at an escalation and 64 were fast runs accepted on the locked suite alone. 18 of the 146 lost a hidden test (12%), against 15% of all scored runs, so the skipped reviews are not costing score.
- **Recurring note: a unit test set aside while the suite passes.** 15 scored runs, none of which lost a hidden test.
  - Here the cause was a unit test written against exports the product never had. The one fix attempt ran in tests-only mode (`TESTS_ONLY_WRITES`, kept on: off, 3 of 8 runs shipped red unit tests; on, 0 of 9). Its rewrite still imported the missing names.
  - Worth a look in bundle 3: the tests-only fixer should be told which names the file under test really exports, so its rewrite tests the product's real interface.
- **Wasted time:**
  - About 5 minutes in the second suite author: seven edits sent at once, quoting text the files did not hold. All seven were refused with the nearest lines shown, then re-read. It happened in this run only, out of the last 12.
  - The rewrite path's fix requests were 84-99K characters on this small product; LF.1270 sizes only the agent-loop fixer's request. To carry into bundle 3.1 (one input budget per request).
- **Fixes seen working:** `SETTLE_SPEC_CONTRADICTIONS` settled five specification contradictions (DR-8 to DR-12). Approved lessons were shown six times. A defect whose criterion passed after another fix was closed on the measurement, not on a claim.
