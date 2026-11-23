# Product review: fullstack-bookmarks container 7 (run-6c8ef0d7-a143-4435-ab62-80e5a145eec4)

**Result (started 20:14 JST 11-23 on :8888, finished 23:20, about 186 minutes; mixed versions to 7df6e52b): not deliverable, hidden 8 of 8, quality 6 of 7, handoff 1.0, mutation 0.58.** KPI regressions: identical calls 4.2% (mean 1.5%), 5 replies lost to the output cap (mean 0), 2 fixes reverted (mean 0.4).

- **Why not deliverable:** three criteria shipped deferred (AC-8, AC-15, AC-17), each on a locked page test that asserts an exact count of every list item (`toHaveCount(0)` after deleting its own bookmark or after a refused save) on a page that shows every test's bookmarks from one shared service. The dispute found the shape after two attempts (it also reclassified two AC-10 filter tests that counted with `toHaveCount(3)`), and the suite could not be repaired again. The hidden tests prove the product itself is right.
- **Recurring (sum-recurring-notes): a locked test counting a store other tests also write** - tasks-api 11, notes-api-csharp 13, tasks-api 13, and this run (5 tests in one suite). The guidance (`SHARED_STORE`, the dispute's `ONE_SHARED_SERVICE`) names it; a model writer and reviewer still lock it. LF.1246, a deterministic pre-lock check, is being built.
- **Lost quality test:** a body that is not JSON is refused and nothing stored - the wrong-shape probe asked one write and probed one; the hidden test sends a different shape.
- **What worked:** LF.1232/1236 fired in the testing stages (the code held, the finished plans named); the dispute's rulings were right.
- **Other harnesses:** test-data isolation per test (a fresh tenant or a namespace per test) is the usual answer; where one service is shared, suites count only what they made.
