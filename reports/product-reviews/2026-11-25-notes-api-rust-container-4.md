# Product review: notes-api-rust container 4 (run-c4fd577a-bce6-4cbe-a2c8-986d23157d1e)

**Result (started 23:17 JST 11-24 on :8888, finished 00:15 11-25, 58 minutes): delivered, hidden 9 of 9, quality 7 of 8, handoff 1.0, mutation 0.75 (1.0 with the unit tests); locked suite 18 of 18.** The second local Rust pass in a row, after four 0/9 runs (LF.1277-1281 in from its scaffold).

- **What happened.** Crates resolved at once (LF.1277); no sqlx macros.
  - The first sprint attempt used its three fix rounds on one-line compiler faults (`Path` imported twice, `list_notes` defined twice, a `?` that cannot convert into `rusqlite::Error`). The last of these has a known-error hint (LF.1239) that the fixer did not act on.
  - The sprint was re-planned once and accepted.
- **Lost: `test_a_long_body_is_kept_whole` (KeyError 'id').** The specification added limits the brief never set - title at most 500 characters, body at most 10,000 - and the product refused the hidden test's 26,000-character body with 400.
  - **Sum:** the test has failed in 17 of 95 scored runs (10 of those never started).
  - **Why the probe missed it:** the round-trip probe (LF.1254) sends 20,000 characters, but a refused long value was SKIPPED, not reported ("1 skipped by the probe").
  - **LF.1298 building:** a refused long value is a finding unless the brief sets a maximum; builders are told not to add a length limit the brief does not set.
  - Same family as LF.1269 (a rate limit the spec adds) and LF.1273 (an empty value the brief leaves free).
- **Cost:** tool failures 17% (5-run mean 8%) and identical calls 6% (mean 3.5%), most in the fix rounds on the compiler faults.
