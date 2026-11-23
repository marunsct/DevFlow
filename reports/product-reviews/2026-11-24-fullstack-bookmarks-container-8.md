# Product review: fullstack-bookmarks container 8 (run-915a9bcb-29e4-484f-87c4-d7d9a4ce0a7e)

**Result (started 03:29 JST 11-24 on :1234, finished 04:35, about 66 minutes; one version, 0c55c376): delivered, hidden 8 of 8, quality 7 of 7, handoff 1.0, mutation 0.73.** KPI regressions: identical calls 11.5% (5-run mean 1.9%), prefill to decode 11:1 (mean 5:1).

- **The first fullstack-bookmarks run of the last four with every quality test and no deferred criterion** (bookmarks 6: AC-4 deferred on a test that could not pass; 7: three deferred on whole-list counts). The suite this time asserted no counts and picked no records by a piece of a title - nothing for LF.1237/LF.1246 to catch, which is the shape the guidance (LF.1235) asks for.
- **Identical calls:** the acceptance authors re-read the same spec files 8-10 times across their passes, and one fixer sent an edit already in the file six times in two minutes (`already_applied` each time, with no word that it was repeating).
- **Open:** two specification contradictions left by escalation (`created_at`, length limits); no test lost to them.
