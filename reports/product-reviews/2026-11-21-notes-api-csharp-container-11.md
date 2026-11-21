# Product review: notes-api-csharp container 11 (run-9119a2a4-d18d-42f7-8cfc-7419ee073710)

**Result (finished 12:03 JST, started 11:15 on :8888, 48 minutes): delivered, hidden 9 of 9, quality 8 of 8, handoff 1.0; no KPI past 1.5x its 5-run mean.**

- **What went well.** Registry look-ups before drafting found versions (nuget 3 of 4, npm 3 of 4); compile errors in the entry file and the unit test project were fixed in single attempts; the product started the first time.
- **What cost time.** One fix round used 16 attempts (`defect_fix_2_10` to `2_15`, `3_16`) on acceptance defects AC-1 to AC-8, one left open as "the unit tests still pass with the change". The run ended with the suite locked while one test (AC-18) verified nothing: it filtered by a title prefix no note ever had, so it passes whatever the server stores. This is the same weak-test shape as the low mutation scores on service briefs.
- **Open / to measure:** a suite check for a "nothing was stored" assertion that has no prior creation (a count assertion of zero over a filter nothing could match) - the suite-review stage already reads tests, so a general review prompt line or deterministic check may catch it; one case so far, so counting only. Fix-round length (16 attempts) to be totalled across C# runs.
- **Other harnesses:** held-out mutation checks (done here via the mutation score) are the usual guard against vacuous assertions.
