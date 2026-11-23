# Product review: notes-api-ruby container 6 (run-a07ec311-263b-428e-8c6f-96bd88115ec0)

**Result (started 06:54 JST 11-24 on :1234, finished 08:06, about 72 minutes; mixed versions to 8ff4031c): delivered, hidden 9 of 9, quality 6 of 8, handoff 1.0, mutation 0.55.** KPI regressions: quality 0.75 (5-run mean 1.0), mutation 0.55 (mean 0.81).

- **Lost quality tests:** a note deleted twice should answer 404 the second time; a long body should be kept whole. No release probe asks either; LF.1254 (a delete-twice probe and a long-value round-trip probe) is being built.
- **Wasted time:** about 25 minutes (07:26-07:47 JST) of suite repair: the drafting pass rewrote the acceptance runner's `package.json` with a second Playwright, and the runner collected no test. LF.1253 (a non-JavaScript service keeps that manifest as the harness wrote it) was deployed mid-run, put the file back, and the next install removed the stray Playwright; the suite then ran and locked.
- **Open:** three specification contradictions settled by rulings.
