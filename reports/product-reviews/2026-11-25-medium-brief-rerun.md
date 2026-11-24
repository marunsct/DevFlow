# Product review: the medium brief rerun (run-c53e7bd2-07c6-4bc5-b97c-2a3aba44709d, "Medium")

**Result (started 15:10 JST 11-24 on :1234, failed 01:17 11-25, about 10 hours; thorough delivery; many deploys into it): sprint 1 of 3 accepted (18 of 18 locked tests, the first test round green); sprint 2 failed on its time budget (257 active minutes against 126 for 8 criteria) with AC-2 to AC-7, AC-9, AC-10 still failing. Not scored - medium briefs are not counted.**

Against the first medium run (24 h 15 min, 17 of 97): the specification's rate limit was declined before the lock (LF.1269 with LF.1275), and the suite was written a sprint at a time (LF.1266). Sprint 1 was delivered whole.

What sank sprint 2, in order:
- **Reading stages re-read the same files after every summary.** Sprint 2's technical lead took about an hour; the backend builder spent 24 minutes and wrote one file. Fixed during the run: LF.1284-1289 (files held and outlined in memory, whole files chosen again at each summary, reads sized to the room). After them, sprint 2's code review read each file once and the page builder finished in 12 minutes.
- **The build was handed over unfinished.** The first test round raised 11 defects that said the features were never built: stub routes, a missing service, 404 endpoints. Four fix stages could not build features. Fixed: LF.1299 checks each work order against what it promised before the test round, and sends "not built" defects to the builder, not the fix loop.
- **The time budget ended the attempt, and the foundation rule ended the run.** Sprint 2 is depended on by sprint 3, so it could not be deferred; past its budget it is not planned again. The budget's pace came from fast runs with no review stages. Fixed: LF.1306 takes a thorough sprint's review stages off its clock.
- **Deploys into the run restarted stages in flight** (about a dozen tonight). Medium 3 runs on one frozen set of fixes where possible.

Medium 3 (run-bc3cbd00, started 01:53 JST 11-25) has all of these from its first stage, plus HK phase 1-2 and KS.5.
