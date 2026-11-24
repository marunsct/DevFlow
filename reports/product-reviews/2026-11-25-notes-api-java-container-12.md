# Product review: notes-api-java container 12 (run-cc265cee-3a52-4d9c-b3b6-876d2a9bca6a)

**Result (started 01:12 JST 11-25 on :8888, finished 02:18, 66 minutes; mixed versions - two deploys landed in it): hidden 9 of 9, quality 8 of 8, handoff 1.0, but verdict not deliverable - the locked suite ended 15 of 16 and four of its own unit tests shipped failing; mutation 0.64 (3-run mean 0.88).**

- **The product works; the harness's own evidence did not settle.**
  - The four failing unit tests all assert a 400 for an empty, null or whitespace title on create and update. The hidden and quality tests that check the same thing passed.
  - So the unit tests most likely expected a different error shape or status path from the one the product gives - the recurring "unit tests ship failing" note (Rust and Java this week).
- **The testing builder tried to edit product code 8 times** (refused each time). LF.1310 (deployed 02:44) now records that as the testing stage's blocker for the owning builder.
- **Cost:** tool failures 10% (5-run mean 5%), redundant reads 26% (mean 16%).
