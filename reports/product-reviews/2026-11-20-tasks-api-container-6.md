# End-of-run product review: tasks-api container 6 (2026-11-20)

Run run-0f60c7a7-3f48-4f63-bcbb-66f4ce5d4377, tasks-api in Python/Flask/SQLite, unsloth/Qwen3.6-35B-A3B-MTP-GGUF on :8888, 12:19-14:25 JST, switches on: `CONTESTED_TESTS_CONFIRMED`, `WEB_LOOKUP_WHEN_STUCK`.

**Score:** hidden 10 of 10, quality 7 of 7, handoff 1.0, no false acceptance. 110 active minutes (tasks-api 5: 175), 203 model calls, mutation score 0.455. **Verdict: not deliverable**, correctly: at release the edge probe still finds `DELETE /items/{id}` at a 20-digit id answering 500.

## What cost time
- About 70 minutes and four attempts at sprint 1 went to that one edge-probe defect, with all 47 acceptance tests green throughout. The fixer saw only Flask's HTML error page; the product's cause was `OverflowError: Python int too large to convert to SQLite INTEGER`. LF.1185 (deployed 14:28) puts what the server printed into such a defect and gives the Python pack that cause.
- Mutation gaps were worked one fixer at a time (about 30 minutes); they sat in different files, so per-file bundling would not have merged them.

## Switches
- `CONTESTED_TESTS_CONFIRMED`: no case - the one dispute (13:07) was settled before the reclassification cap.
- `WEB_LOOKUP_WHEN_STUCK`: no lookup for the stuck defect, because its text held no concrete error to search for (only the HTML page). LF.1185 gives it one. Registry-version lookups (T4, built in) ran three times before dependency files were drafted.

## How others do it
Test runners and API checkers (Schemathesis, Dredd) report the server's log beside a 5xx; the harness now does the same.

## Added value
Full hidden and quality marks in 110 minutes on the largest local brief; the remaining 500 is reported honestly instead of shipped as delivered.
