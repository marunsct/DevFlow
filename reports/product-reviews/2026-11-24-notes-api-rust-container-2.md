# Product review: notes-api-rust container 2 (run-df1ac51d-b7ea-4639-a970-d8ace9a02d48)

**Result (started 15:24 JST 11-24 on :8888, failed 17:22, about 2 hours; mixed versions - five deploys landed in it): not delivered, hidden 0 of 9, quality 0 of 8, handoff 0.375. The product never built.**

- **What happened.** The plan was one sprint for the foundation. A pause for a deploy (LF.1274) came as drafting began, so all nine drafts were refused and left to the builders (LF.1276 since). The builders wrote every file. The product never built, and the sprint was re-planned three times; past a foundation it is not deferred (LF.1264), so the run stopped.
- **Why it never built - a chain of blockers, one surfacing as each was fixed:**
  1. **The toolchain.** The sandbox's rustc 1.85 met crates whose newest releases need rustc 1.86-1.88 (`icu_collections 2.4` through `url` by sqlx). The fixer pinned crates by hand. **LF.1277:** every Rust pack has cargo choose releases the toolchain builds (`.cargo/config.toml`, `incompatible-rust-versions = "fallback"`; verified in the sandbox image). This is a likely root cause of Rust's 0/9 in four earlier local runs.
  2. **sqlx's `query!` macros**, which need a live database at build time. **LF.1278:** a known-error answer and a design fact. The fixer then removed every macro.
  3. **`SqlitePoolOptions`** named from `sqlx::`.
  4. **A `JournalMode`** sqlite has not.
  5. **Signal streams not declared `mut`.**
  - Items 3-5 are one line each. **LF.1279** answers all three; they cost a round each and the attempts ran out.
- **Lost:** everything; the service never started.
- **Next:** `L notes-api-rust container 3`, started 17:24 JST, gets LF.1276-1279 from its scaffold.
- **Worth building:** a build that fails on several one-line compiler faults should hand them all to one fixer at once. Here they came one a round because each build stopped at the first crate that failed. Bundle 3 candidate: "the compiler's every error in one fix".
