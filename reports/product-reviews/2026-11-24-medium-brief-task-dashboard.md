# Run review: the owner's medium brief, task management dashboard (run-8f0be29e-4c22-425f-9219-46b166b93d70)

**Result: failed at 00:06 JST 11-24 after about 24 hours (started 23:51 JST 11-22 on :1234).** The sprint "Full task CRUD with assignment, priorities, due dates, categories, and tags" was planned once and could not be accepted: 891 active minutes against a 126-minute budget; AC-2, AC-3, AC-4, AC-5, AC-6, AC-9, AC-10 still failing. The acceptance suite never passed more than 17 of its 97 tests (first reached 08:33 JST 11-23). Not a benchmark: no hidden tests, so no score. Not counted in the measuring (owner 11-23).

## Why it did not move
1. **The product's own rate limit** (sign-up 10 an hour, sign-in 5 a minute) answered 429 to 66 of 92 failing tests: the suite signs up an account per test from one address. One defect for it was never raised because other statuses failed beside it (fixed by LF.1243).
2. **The task router was mounted with a double prefix**, so every task route answered 404 (13 tests) - found by test round 1 at 20:18 JST, never worked: the round fixed defects carried over from earlier rounds first (LF.1244 orders the latest round's defects first; it landed mid-round and could not reorder that round).
3. **Every database fix was reverted:** the service stopped starting on `index ix_tasks_assigned_to already exists` (an index declared twice), and the full-stack pack carried no Python known errors at all (LF.1245).
4. **Time lost to the harness:** about 4 hours of suite repair passes on a login TypeError read as the test's own error (LF.1241); 50 minutes of a testing stage re-reading files after summaries and writing no tests (LF.1232/1233/1236); replies reasoning 13-35k tokens before single reads (LF.1238/1247).

## Fixes this run produced
LF.1231, LF.1232, LF.1233, LF.1236, LF.1238, LF.1241, LF.1243, LF.1244, LF.1245, LF.1247 - each with a test failing on the old code, each deployed on 11-23/24.

## What a rerun would show
The same brief on the current harness is the honest measure: the rate limit is named as one defect, the round's root cause goes first, the index cause reaches the fixer, and the suite's login loop does not happen. Whether to rerun it is the owner's call.


## Correction (2026-11-24)
The deep review (`reports/audits/2026-11-24-why-medium-briefs-fail.md`) supersedes the numbers above: the final 80 failures were 37 direct 429, 18 thrown by the suite's sign-in helper, 13 404, 8 "Login failed 401" and 4 other (the "66 of 92" was a mid-run reading); LF.1243 never fired on this run and LF.1244's mid-round deploy made the round skip the defects it was to put first; with the limiter off and three small code fixes the product passes 82 of 97.
