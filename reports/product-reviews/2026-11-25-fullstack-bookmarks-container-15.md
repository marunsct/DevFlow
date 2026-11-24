# Product review: fullstack-bookmarks container 15 (run-b6c5c636-7264-4cee-840a-1c8c4b07855e)

**Result (started 04:30 JST 11-25 on :8888, finished 07:53, about 3 h 24 min; mixed versions - LF.1314-LF.1315 deployed into it): delivered, hidden 8 of 8, quality 7 of 7, handoff 1.0; locked suite 14 of 14.**

- **What happened.** One sprint; its first attempt ran out of fix rounds and was re-planned once.
  - The first round fixed the page's list items (`<div>` to `<li>`, so the suite finds them as list items).
  - The second attempt spent its fix rounds on the project's own unit tests in `tests/store.test.js`: the tests shared one store file, so each test's records leaked into the next ("expected 1, actual 6"; a list of six records where none were expected).
  - The tests-only fixer edited the file five times, about six minutes a cycle, without giving each test a store of its own.
- **Found and fixed from it - LF.1316 (deployed 07:56):**
  - Unit-test writers and the tests-only fixer are told that a test that stores data starts from an empty store of its own.
  - The fixer is shown the leaked records and the tests that made them.
  - The defect listing now keeps the actual values ("6 !== 1"); before, it cut them, so no fixer could see the shared store.
  - This is the second root of the recurring "own unit tests ship failing" note (20% of recent runs); LF.1312 was the first.
- **Time:** long for a small product, mostly the slow tests-only loop and the re-plan.
