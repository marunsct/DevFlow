# Product review: notes-api-rust container 3 (run-59135d0b-52da-4387-9218-ef7c42c4cc4a)

**Result (started 17:24 JST 11-24 on :8888, finished 18:38, 74 minutes; mixed versions - LF.1279-1281 deployed into it): delivered, hidden 9 of 9, quality 8 of 8, handoff 1.0, mutation 0.67 (0.92 with the unit tests); locked suite 17 of 17.** The first local Rust run to pass a hidden test; four earlier local runs scored 0/9.

- **What made the difference.** The scaffold carried `.cargo/config.toml` (LF.1277), so cargo chose crates rustc 1.85 builds. The specification chose rusqlite; the sqlx design fact (LF.1278) was there besides.
- **The fix rounds were not clean.** Three sprint attempts:
  - Attempt 1: `axum::extract::JsonRejection` (really in `extract::rejection`; LF.1280 and the general LF.1281 since); the fix that followed broke the build and was reverted.
  - Attempt 2: a borrow fault in a transaction.
  - Attempt 3: twice a fix that had 18 tests passing broke the build in its caller `src/main.rs`. LF.1271's forward repair fired both times, but it could rewrite only `src/lib.rs`, the file the fix changed, so it changed nothing and both fixes were reverted. **LF.1282** (built, held for the next deploy) lets the repair rewrite the file the error names.
  - The run was escalated with the best product, the best attempt kept, and that product passed everything hidden.
- **Ships with:** one of its own unit tests failing (the unit tests did not compile). The note "unit tests ship failing" recurs on Rust (now 6 runs).
- **Cost:** 3 fixes reverted (5-run mean 0.8); mutation 0.67 (3-run mean 0.83).
- **Next:** another Rust run after LF.1282 deploys, to see whether the fix rounds converge rather than end on the best attempt.
