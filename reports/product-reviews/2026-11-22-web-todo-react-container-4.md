# Product review: web-todo-react container 4 (run-dcad5c17-b668-4246-bed8-b4dece516875)

**Result (finished 11:59 JST, started 10:56 on :8888, about 63 minutes): delivered, hidden 10 of 10, quality 6 of 6, handoff 1.0, mutation 0.33, one of the product's own unit tests shipping failing.** KPI regressions: mutation score 0.33 (5-run mean 0.50) and redundant reads 0.44 (mean 0.26).

- **What happened.** Four suite-authoring rounds and reviews (about 25 minutes), then a first test round with 11 acceptance defects and a batch of 11 fixers (about 40 minutes); one of them (`defect_fix_1_9`) was reverted for breaking 10 passing acceptance tests (the Done-checkbox tests and others) and the suite was re-authored; the second round passed every acceptance test; the milestone passed and the release delivered with the project's own `App.test.tsx` test for editing a title through an inline input still failing, shipped as a gap.
- **Against web-todo-react 3** (62 minutes, mutation 0.33): the same time and the same mutation score; the editing of a title (AC-3, AC-10) is again where the product's own unit test and the page disagree.
- **Open:** the shipped-failing unit test (the persistent unit-test failure pattern: C# 12, bookmarks 4, Java 10, this one); DR-6 settled (the specification said two things about valid JSON in the stored list); mutation low on the UI brief (0.33 twice).
- **Cost.** The 11-fixer first batch plus one revert; redundant reads 44%, the highest of the week.
- **Other harnesses:** a unit test the product's author wrote that fails against the finished page is normally removed or fixed by the author before release; ours ships it and records it.
