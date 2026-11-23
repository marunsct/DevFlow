# Product review: tasks-api container 15 (run-607e8e9a-83b3-4e63-9b84-ad4326d3dbdd)

**Result (started 00:08 JST 11-24 on :1234, finished 03:15, about 3 hours 7 minutes; mixed versions to 0c55c376): delivered, hidden 10 of 10, quality 7 of 7, handoff 1.0, mutation 0.36.** KPI regression: mutation 0.36 (2-run mean 0.79).

- **The two quality tests tasks-api 14 lost now pass** (a title of only spaces refused; items created at the same moment all kept). The release probes reached those writes signed in for the first time on this family: LF.1249 read the seven contract lines from the criteria (the specification left its interface contract "Not specified"), LF.1242 signed in with the criteria's sign-up body - concurrent write 1 asked, 1 probed; wrong shape 4 of 4; bad body 4 of 4; emptied field 3 probed.
- **What happened.** Two sprints; sprint 2 was re-planned after a dispute that reclassified one locked test (`test_ac20_persistence_multiple_operations`); mutation rounds left several findings open (0.36).
- **Open:** the mutation score - the unit tests notice few deliberate changes; a sign-in API's tests check statuses more than stored state.
