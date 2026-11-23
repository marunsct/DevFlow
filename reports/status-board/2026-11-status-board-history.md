Archived copy of the cloud status board, exported 2026-11-20. The live status is docs/STATE.md.

# Harness status board

Nov 1, 2026 · @Arun

## The launch cycle

The product is launch-ready on quality when every family below passes three runs in a row on one frozen version; two families pass today and three were failing when last run. My estimate for reaching it is 11-05 to 11-08, and the sweep below will firm that up.

I had spent about 70% of all scored runs on the two families that already pass. They now score full marks every time, so more of those runs teach almost nothing, and the failing families have not run since 10-26.

| Family | Benchmark | Last results (hidden) | Last run | Stage |
| --- | --- | --- | --- | --- |
| Full stack, Node | fullstack-bookmarks | 8/8 on 11-01 (before that 3/8, false acceptance) | 10-26 | swept, passing once |
| Command line | wordstats-cli | 8/8 on recheck, 11-02 (before that 6/8, 5/8, 5/8, 7/8) | 11-02 | swept, failing, for triage |
| Web page | web-todo | 10/10 on recheck, 11-02 (before that 9/10, 10/10, 2/10, 9/10, 10/10, 8/10) | 11-02 | swept, failing, for triage |
| Full stack, Python | fullstack-bookmarks-py | 8/8 on 11-02, no stack pack (before that 0/8) | 10-19 | sweep |
| Web page, React | web-todo-react | 10/10 on recheck, 11-02 (was 1/10: the product did not build) | - | sweep |
| Change to existing code | tasks-api-change | 15/15 on recheck, 11-02 (was 0/15: the seed stayed at the root) | - | release candidate |
| Library | textkit-lib | 8/8, marked non-deliverable | 11-02 | triage the label |
| API, Python | notes-api | 9/9, marked non-deliverable | 11-02 | triage the label |
| API, JavaScript | notes-api-js | 9/9, marked non-deliverable | 11-02 | triage the label |
| API, TypeScript | notes-api-hono | full marks, last 8 runs | 11-01 | sentinel only |
| API with sign-in | tasks-api | full marks, last 8 runs | 11-01 | sentinel only |

**The cycle.**

1. **Sweep:** one run of each family on one frozen version, worst first, two at a time. About 1 to 2 days.
2. **Triage:** rank what the sweep found. Fix only what loses a hidden test, gives a false acceptance, or wastes over 30 minutes. Everything else is filed.
3. **Fix batch:** one batch per cause, each fix with a test that fails on the old code. One deploy, only between runs.
4. **Recheck:** rerun only the families that batch touched, plus one sentinel to catch regressions. Back to step 2 until each is green.
5. **Release candidate:** freeze the version and run each family three times. Any failure goes back to step 2.

**What changes.**

- **Switch groups** are no longer measured by repeat runs. They stay as they are during the sweep. At the release candidate, any switch that never changed an outcome is turned off, so the launch carries less unproven machinery.
- **Stored failures are replayed first:** a fix for a test-suite check is tested against the stored suites by reading them, which costs no model time.
- **Queue items** are built only if the triage ranks them above the bar; the rest wait until after launch.

**The launch gate.**

| Measure | Bar |
| --- | --- |
| Hidden tests | full marks, every family, three runs in a row |
| False acceptances | none |
| Time | every run under 4 hours |
| Larger brief | one run of a bigger brief reviewed by hand, since no hidden tests exist for it |

This gate is my proposal, and it covers build quality only. Billing, sign-up, hosting, storage (the three S3 tests fail for want of credentials) and customer model choice are not assessed here; see Waiting on you.

## How to read this board

Every feature sits in exactly one state below. I update this board at each deploy and each finished run, and the date at the top is the last time.

| State | Means | Where |
| --- | --- | --- |
| Live | Built, tested, switched on, no measurement pending | Live and switched on |
| Measuring | Switched on as a trial; compared against earlier runs | Switch groups being measured |
| Built, off | Built and tested, switched off until a measurement says on | Built but switched off |
| Queued | Not built | Not built yet |
| Waiting on you | Needs your decision | Waiting on you |

"Tested" means a unit test that I saw fail on the old code. Where that proof is weak or missing, the table says so. "Seen live" means it acted in a real run. The full detail of each change is in the improvement plan (rows LF.447 to LF.509) and the state file in the repository.

## Right now

**Update 2026-11-08 14:10 JST.** No run since 01:45: a GPU driver fault (amdgpu ring timeout from gnome-shell) stopped both model apps and Docker Desktop. Docker is back; Unsloth (:8888) and LM Studio (:1234) are not, so tasks-api 6 (run-ed4e910f) and wordstats-cli 1 (run-885a8285) wait to be resumed. Meanwhile 38 fixes from the second review (HR2) were built, tested on the old code, deployed, and wait for their first run.

| Bundle | What it does | Fixes | Tested | First run will show |
| --- | --- | --- | --- | --- |
| 1 Telemetry | each dispute, probe, filter, draft, setup proof, capped reply and pointer read is recorded; blind spots, gap precision, handoff score | LF.690-707 | yes, all fail on old code | the new rows in effects, scan, suite-checks |
| 1b Measurement | per-run switch settings (both arms on one SHA); build before pause; pause at the stage boundary; nightly beside one run; held-out families; STATE block written from the records | LF.708-713 | yes | the first switch pair; paused minutes a deploy |
| 2 What ships | a README on every shipped product with settings, start, tests and routes; no shipped test data or untouched template; HOST honoured by every pack; dev-server note; escalation named; dead DB connections replaced | LF.714-722 | yes; packs scaffold-checked; DB restart checked live | handoff score; no data/ or stub in products |
| 3 Design | one revision limit; part writers see advice ids; harness repairs name their sections | LF.723-725 | yes | architect calls and advice rounds a run |
| 4 Planning | repairs before the readiness check; data files never unassigned | LF.726-727 | yes | readiness resends a run (1.1 to \~0.1) |

Moved behind a switch to measure first: PR.13 (a unit-test repair pass), P.3b (no reads for planning stages). Reshaped: PR.5 (logging needs a design; the packs keep no entry file).

**2026-11-10 06:40 JST.** Scored L fullstack-bookmarks-py 11 (run-e16844fb) 8/8 and L web-todo 8 (run-efaecb0f) 7/10, a false acceptance: the filters were named "All (0)" etc. instead of the brief's names, and "Add task" was disabled until a title was typed. Deployed c8956ed: LF.783-792. Built, tested and live: installs refused from harness hosts, the true network line, no default storage key, a cap on refused writes outside a stage's own files, no worker secrets in product code, a commit guard, the Redis password, setup-env never re-keys stored credentials, and a page check for controls shown under a longer name. Next to measure: LF.792 on L web-todo 9 (run-ea2fb039).

**2026-11-10 07:53 JST.** L web-todo 9 (run-ea2fb039) scored 10/10, handoff 0.857: the controls kept the brief's names and the suite asked for them exactly, so web-todo 8's loss did not recur. Built, tested and live since 07:00: LF.794 (a defect's call cap counts across re-plans), LF.795 (accessibility defects name their files), LF.796 (the brief's quoted names win over the specification's in every suite and fix request), LF.797 (a setting written with a full stop reaches the README). Per-role audit published.

**2026-11-10 08:24 JST.** L notes-api-hono 3 (run-75d539d5) scored 9/9, handoff 1.0. Live since 08:12: LF.798 (a ruling on a quote cut from a longer statement is rejected) and LF.799 (a suite the QA lead never read is read once at the round limit). Running: L fullstack-bookmarks 4 (:8888) and L wordstats-cli 14 (:1234), the family behind two recent false acceptances.

**2026-11-10 11:30 JST.** L wordstats-cli 14 (run-443662be) and L fullstack-bookmarks 4 (run-e6e4b2e1) both scored 8/8 with handoff 1.0, no false acceptance - wordstats-cli is the family behind two of the four recent false acceptances. LF.800 (intake and advice never override what the brief states) live since 08:31. The owner's run ("low brief") is on :1234, so the loop runs only on :8888 until it ends: L textkit-lib 3 (run-80d8b13a) started 11:32.

**2026-11-10 12:07 JST, Measure batch on frozen 87d7c9b (owner's go at 11:33).** Pair 1 textkit-lib: run-80d8b13a 8/8 (28 min) and run-7f175172 8/8 (27 min), 2 and 3 fix stages against 5-14 in earlier textkit runs. Pair 2 tasks-api started on both ports. Filed for the next Fix batch, not deployed: F1 (fixers sent to locked tests no product passes) and F2 (a library's README never says how to use it).

**2026-11-10 16:33 JST, Measure pair 2 tasks-api:** run-629f0be3 10/10 (87 min) and run-f1f2a8ec 10/10 (235 min), both handoff 1.0, no false acceptance. The long run spent its time re-authoring its suite (60 model-min) and re-planning around one comprehensive test, not fixing (34 min). Pair 3 web-todo started on both ports. Built for the Fix batch, not deployed: LF.801-803.

**2026-11-10 18:28 JST, Measure pair 3 web-todo:** run-c0622089 10/10 (88 min) and run-42527557 10/10 (111 min), handoff 1.0 both. The longer run lost about 22 minutes to a fixer reasoning in plain text (built as LF.805, held) and about 50 minutes on two filter tests the dispute later ruled wrong (audit fix #6, next to build). Batch so far: 6 of 6 full. Pair 4 wordstats-cli running on both ports.

**2026-11-11 01:25 JST, Measure batch nearly done (frozen 87d7c9b):** 10 of 11 runs full - textkit-lib, tasks-api, web-todo, notes-api-hono and fullstack-bookmarks-py (12a 8/8) all full; wordstats-cli 1 of 2 (a false acceptance, fixed as LF.807). The last run, fullstack-bookmarks-py 12b, is live. Built and held for the Fix batch: LF.801-811 (deferral survives the lock, repeated calls run once, library README usage, computed counts, prose-reasoning salvage, dispute keys per attempt, architect told the brief wins and "instead" means nothing else, shared-list positions, three README settings fixes, withheld-tool refusals name what is left).

**2026-11-11 05:21 JST, Measure batch done: 10 of 11 runs full** on the frozen 87d7c9b (the one false acceptance, wordstats-cli 15a, fixed as LF.807). The last run, fullstack-bookmarks-py 12b, took 8.8 hours (24 fix stages, 59 salvaged replies) and scored 8/8. **Fix batch LF.801-813 deployed at 05:19 (33a45a6).** Learning runs started on both ports: L wordstats-cli 16 (checks LF.807) and L notes-api-hono 5 (checks LF.808).

**2026-11-11 06:36 JST, first learning runs on the fix batch:** L wordstats-cli 16 (run-cf31be1c) 8/8 - LF.807 held, the brief's "instead" survived to the product - and L notes-api-hono 5 (run-899060c6) 9/9, handoff 1.0, 71 minutes against 72 active minutes and three attempts for the same family in the batch. LF.814 (README usage under any criterion id) deployed 06:32. Running: L fullstack-bookmarks-py 13 and L web-todo 11.

**2026-11-11 07:51 JST.** L fullstack-bookmarks-py 13 (run-9d2bf366) **8/8, handoff 1.0**, locked suite 16/0. Deployed since 07:00: **LF.815** (the dispute judge is told the suite shares one service), **LF.816** (Python shared-list position check, plus count-check fixes, after two independent review rounds that reproduced 14 false positives or misses in the drafts), **LF.817** (escalation settles an open finding that the specification departs from the brief; the brief stands), **LF.818** (a contract line naming a record by number is probed as its route; 12 false release gaps in the scored runs). Live: L web-todo 11 (:1234), L tasks-api 10 run-63db1e89 (:8888, started 07:51). Open: audit #7 (planning with thinking off, behind a switch), F1b.

**2026-11-11 10:20 JST.** L tasks-api 10 (run-63db1e89) **10/10, quality 7/7, handoff 1.0**, locked suite 23/0. Deployed 07:50-09:55: **LF.818** (release probe of a numbered record), **LF.819-821** (salvaged-reply count survives compaction and restarts; planning stages behind `SALVAGED_PLANNING_THINKING_OFF`), **LF.822** (salvage keeps the stage's reply budget; a salvage that only reasons again is no answer), **LF.823** (mutation findings of one file shown together; one already settled closed without a fixer), **LF.824** (F1b: page suites wait for a save before typing again), **LF.825** (`THINKING_OFF_REPLY_CAP`, measured: on :1234 a 47,000-token reply became about 4,200), **LF.826** (defects naming different things keep different ids, so one's calls are not charged to another). Docker VM now 16 GiB (owner). Paused 10:12 for the owner to load a higher-bit model on :1234: L web-todo 11 run-45cef9f4.

**2026-11-11 13:20 JST.** L fullstack-bookmarks 5 (run-b7b8ae49) **8/8, handoff 1.0**, but accepted at an escalation after 3 re-plans, with 2 locked tests unpassable (a text locator matching two elements; an empty-store assumption), each caught by the dispute. Deployed since 10:20: **LF.827** (ratchet: product words may not spread in the source), **LF.828** (a fix naming no files sees its role's earlier fixes; stops two checks undoing each other), **LF.829** (the prose-reasoning cap follows the stage family; measured on both ports: capped replies about 4,000 tokens instead of 12,000-47,000). Live: L web-todo 11 (:1234, sprint 1 attempt 2), L textkit-lib 4 run-db55fd26 (:8888, started 13:20). Today's learning runs: 5 of 5 at full hidden scores.

**2026-11-11 14:02 JST.** L textkit-lib 4 (run-db55fd26) **8/8, handoff 1.0**; L web-todo 11 (run-45cef9f4) **10/10, handoff 1.0** after three sprint-1 attempts on the 4-bit build. Today's learning runs: **7 of 7 at full hidden scores**. Deployed 13:45-13:57: **LF.830, LF.831** (the harness's own deferral check was wrong in all three runs it fired today - a signature's parameters read as features, and extensions like "password reset" read as deferring the feature - and it overturned two approved specifications into escalations), **LF.832** (the one-call rewrite is told the earlier fixes to keep; a page check had been undoing a test's fix ten times over). Live: L notes-api 7 run-6ee6e730 (:8888), L web-todo-react 1 run-7a727629 (:1234), both 14:02.

**2026-11-11 15:07 JST.** L notes-api 7 (run-6ee6e730) **9/9, handoff 1.0** (accepted at an escalation; 2 unit tests shipped failing; 2 unused source files). Today's learning runs: **8 of 8 at full hidden scores**. Deployed 14:29-14:52: **LF.833** (design stages told the files the setup writes and the dependencies it declares), **LF.834** (`HARNESS_FINDINGS_RECHECKED`, off: a revision made only for the workflow's own findings rechecked by them), **LF.835** (`TESTS_ONLY_WRITES` taken off for cost on its second costly case). Live: L web-todo-react 1 run-7a727629 (:1234), L notes-api-js 1 run-6d1c3399 (:8888, 15:07).

**2026-11-11 15:33 JST.** L web-todo-react 1 (run-7a727629) **10/10, handoff 1.0**: one fix round, 8 of 10 defects closed without a fixer, on the 4-bit build. Today's learning runs: **9 of 9 at full hidden scores**. Live: L notes-api-js 1 run-6d1c3399 (:8888; design escalation from real contradictions in the specification), L notes-api-falcon 11 run-6ff5ddd0 (:1234, 15:33).

**2026-11-11 16:27 JST.** L notes-api-js 1 (run-6d1c3399) **9/9, handoff 1.0**, locked suite 17/0. Today's learning runs: **10 of 10 at full hidden scores**. Deployed 16:13: **LF.836** (the sections one review finding names are revised in one call; a contradiction between two sections revised apart had survived into the second review). Live: L notes-api-falcon 11 run-6ff5ddd0 (:1234), L wordstats-cli 17 run-2b67f0be (:8888, 16:27).

**2026-11-11 17:16 JST.** L wordstats-cli 17 (run-2b67f0be) **8/8, handoff 1.0**. Today's learning runs: **11 of 11 at full hidden scores**. Deployed 16:58-17:08: **LF.837** (intake stages' replies capped at 16,000 tokens; one wrote a tool call's closing tags over and over for 12 minutes), **LF.838** (a review naming an ADR names the decisions section, so the revision rewrites it; LF.836's first run settled all but that one finding). Live: L notes-api-falcon 11 (:1234), L tasks-api 11 run-c6b5bce1 (:8888, 17:16).

**2026-11-11 17:26 JST.** L notes-api-falcon 11 (run-6ff5ddd0) **9/9, handoff 1.0**, locked suite 17/0; 5 fixes reverted over a layout split between the proven setup's package and the specification's flat modules (3 of the last 80 runs: watched). Today's learning runs: **12 of 12 at full hidden scores**. Live: L tasks-api 11 run-c6b5bce1 (:8888, 17:16), L web-todo 12 run-b3e4f96b (:1234, 17:26).

**2026-11-11 19:00 JST.** L web-todo 12 (run-b3e4f96b) **10/10, handoff 1.0**, locked suite 23/0: sprint 1 in two fix rounds (about 45 minutes) on the same 4-bit build where web-todo 11 needed three attempts over most of the day - the clearest before-and-after of today's fixes. Today's learning runs: **13 of 13 at full hidden scores**. Live: L tasks-api 11 run-c6b5bce1 (:8888), L fullstack-bookmarks 6 run-a94d704a (:1234, 19:00).

**2026-11-11 19:40 JST.** L tasks-api 11 (run-c6b5bce1) **10/10, quality 7/7, handoff 1.0**, locked suite 38/0; 10 of its own unit tests ship failing. Today's learning runs: **14 of 14 at full hidden scores**. Deployed 19:25: **LF.839** (a repeated reply of several calls is noticed; a stage sent the same two searches seven times unnoticed). Watched: unit tests shipping red in 2 runs since `TESTS_ONLY_WRITES` went off (LF.835). Live: L fullstack-bookmarks 6 run-a94d704a (:1234), L notes-api-hono 6 run-f8d4e2af (:8888, 19:40).

**2026-11-11 20:25 JST.** L fullstack-bookmarks 6 (run-a94d704a) **8/8, handoff 1.0**; 10 unit tests ship failing. Today's learning runs: **15 of 15 at full hidden scores**. **LF.840: `TESTS_ONLY_WRITES` back on** - with it off (14:52-20:25), 3 of 8 runs shipped failing unit tests (2, 10, 10); with it on, 0 of 9. Its cost is bounded to one first fix attempt. Live: L notes-api-hono 6 run-f8d4e2af (:8888), L web-todo-react 2 run-d239b5da (:1234, 20:17).

**2026-11-11 20:47 JST.** L notes-api-hono 6 (run-f8d4e2af) **9/9, handoff 1.0**, locked suite 10/0. Today's learning runs: **16 of 16 at full hidden scores**. Design: hono 6 and web-todo-react 2 both passed on their second review with no escalation, after 7 of the morning's 9 runs escalated (LF.830-838). Live: L web-todo-react 2 run-d239b5da (:1234), L fullstack-bookmarks-py 14 run-2f129659 (:8888, 20:47).

**2026-11-11 22:23 JST.** L fullstack-bookmarks-py 14 (run-2f129659) **8/8, handoff 1.0**, no unit test shipped red (`TESTS_ONLY_WRITES` fired once and fixed a unit test in the test file); L web-todo-react 2 (run-d239b5da) **10/10, handoff 1.0** with one locked test (title editing) still red. Today's learning runs: **18 of 18 at full hidden scores**. 21:12 host GPU fault (not the harness) took the session down; both runs resumed in place at 21:17. **LF.841**: the ready check given an address now checks that server (a bare address had been ignored). Live: L textkit-lib 5 run-0c7ac86e (:8888, 22:15), L wordstats-cli 18 run-e5f4f9c4 (:1234, 22:23).

**2026-11-11 23:36 JST.** L textkit-lib 5 (run-0c7ac86e) **7/8 - false acceptance**: `title_case` split on spaces only and no locked test used a tab. **LF.842** (a kind of input is tested with more than one member, for the suite writer and its reviewer) deployed 23:07; L textkit-lib 6 (run-98fafcd0) on the same brief: **8/8, handoff 1.0**, its suite now testing tabs. Today's learning runs: **19 of 20 at full hidden scores**. :1234 now serves `qwen3.6-35b-a3b-mtp@iq4_nl` (owner, 22:48). Live: L wordstats-cli 18 run-e5f4f9c4 (:1234), L notes-api-js 2 run-274d1ea0 (:8888, 23:36).

**2026-11-11 23:52 JST.** L wordstats-cli 18 (run-e5f4f9c4, first run on :1234's IQ4\_NL build) **7/8 - false acceptance**, the same hidden test the morning Measure batch lost: the specification gave `--top N --json` only the top words (as the brief says) and `--json --top N` the counts as well, by option order alone. **LF.843** (23:51): command lines that differ only in option order and give different results are a major finding at design review. Today's learning runs: **19 of 21 at full hidden scores**. Live: L notes-api-js 2 run-274d1ea0 (:8888), L wordstats-cli 19 run-787a3f4c (:1234, 23:52, re-checks LF.843).

**12 Nov 00:47 JST.** L notes-api-js 2 (run-274d1ea0, :8888) **9/9**, handoff 1.0, locked suite 11/11, released 00:37 after three mutation findings (one judged equivalent). LF.844 deployed 00:25 (the setup's starter files are not said to exist before the build); LF.845 deployed 00:32 (a mode whose output replaces another's is tested for the other's absence; writer and reviewer) - L wordstats-cli 19 rewound to its suite writer to carry it. L notes-api 8 (:8888) from 00:47.

**12 Nov 01:36 JST.** L notes-api 8 (run-96a84970, :8888) **9/9**, handoff 1.0, locked 14/14, green at its first test round; LF.844 verified (no failed starter-file reads). **LF.846 deployed 01:10** (the harness finds a brief's alternative literal outputs held only in part; flags 7 of 19 stored wordstats suites incl. all 3 that lost a hidden test) - fired on L wordstats-cli 19 at 01:14 and its test now asserts the counts are absent. L tasks-api 12 (:8888) from 01:36.

**12 Nov 02:27 JST.** L wordstats-cli 19 (run-787a3f4c, :1234 IQ4\_NL) **8/8** - `test_json_top_words` passed for the first time in four wordstats runs: **LF.846 verified** (the harness found the weak test, the dispute upheld it, a rewrite fixed the product). **LF.847 deployed 02:09** (a milestone finding naming only the locked suite is recorded minor; it kept wordstats-cli 19 from a sprint over a locked test). L wordstats-cli 20 (:1234) from 02:27 to confirm unrewound; L tasks-api 12 (:8888) in its release reviews.

**12 Nov 03:11 JST.** L tasks-api 12 (run-3a8d00f4, :8888) **10/10**, handoff 1.0, locked 44/44, two sprints, no KPI regression. LF.848 deployed 02:52 (a plan short of carried-forward decisions is told the items, numbered). L fullstack-bookmarks 7 (:8888) from 03:11; L wordstats-cli 20 (:1234) writing its suite.

**12 Nov 04:40 JST.** L fullstack-bookmarks 7 (run-75511fa9, :8888) **8/8**, accepted at an escalation; the harness's suite checks and one right dispute took its locked suite to 20/20. **LF.849 deployed 04:12 and verified 04:20** (a past-the-cap deferral records its tests, a Python suite written as classes included, so the next lock keeps it) - wordstats-cli 20's AC-7/AC-11 stayed deferred. L web-todo 13 (:8888) from 04:40.

**12 Nov 04:58 JST.** L wordstats-cli 20 (run-d2c01d2d, :1234 IQ4\_NL) **8/8** - LF.846 fired on its own (suite sent back once, `test_json_top_words` passed); LF.849 held its deferrals. LF.850 deployed 04:55 (an intake assumption written "-> Assumption:" is recorded as its answer). Learning runs tonight: 7 of 7 scored at full hidden scores. L notes-api-hono 7 (:1234) from 04:58; L web-todo 13 (:8888) in design.

**12 Nov 06:07 JST.** L notes-api-hono 7 (run-665859fa, :1234 IQ4\_NL) **9/9**, locked 10/10. LF.851 deployed 05:36 (a page test using a locator as a list is caught as cannot-pass) - web-todo 13's broken AC-9 test was repaired at 05:36. Learning runs tonight: 8 of 8 scored at full hidden scores. L textkit-lib 7 (:1234) from 06:07; L web-todo 13 (:8888) in its second fix round.

**12 Nov 06:47 JST.** **LF.852 deployed 06:30 and verified**: a criterion speaking of whitespace whose tests use only spaces sends the suite back - L textkit-lib 7 (run-477755ed, :1234) gained a tab-and-newline `title_case` test and scored **8/8**. (Its first product, completed 06:27, was lost unscored to a rewind - an operator slip, noted.) Learning runs tonight: 9 of 9 scored at full hidden scores. L textkit-lib 8 (:1234) from 06:46; L web-todo 13 (:8888) still in fix rounds.

**12 Nov 07:36 JST - FROZEN on d92dfb9 as RC15.** L textkit-lib 8 (run-0d3a4fd3) **8/8** (its writer tested tabs unprompted). Learning runs this night: **10 of 10 at full hidden scores** (notes-api-js 2, notes-api 8, wordstats-cli 19 and 20, tasks-api 12, fullstack-bookmarks 7, notes-api-hono 7, textkit-lib 7 and 8, and textkit-lib 6). Fixes deployed tonight: LF.844-852 (four of them deterministic suite checks that replaced prompt rules the models ignored). RC15 tasks-api 1 (:1234) from 07:36; L web-todo 13 (:8888) still in fix rounds.

**12 Nov 08:02 JST.** L web-todo 13 (run-97f30e2b, :8888, mixed) **10/10** after \~78 min of fix rounds; escalated with two locked tests still failing, one a test fault (a delete test picked the first record by position under a newest-first order) - filed for the Fix batch, not deployed under the RC15 freeze. Learning runs: **11 of 11 at full hidden scores**. RC15 runs: tasks-api 1 (:1234) in design, notes-api 1 (:8888) from 08:02.

**12 Nov 08:47 JST.** LF.853 deployed 08:19 (a test-broke-itself finding quotes the runner's reason, e.g. `fixture 'auth_token' not found`) - it can cost score, so the RC15 freeze broke and **the count restarts as RC16 on 66bc01d9**. RC15 notes-api 1 (run-76cc1045, :8888, mixed) **9/9**, locked 19/19. RC15 tasks-api 1 (:1234, mixed) in fix rounds; RC16 fullstack-bookmarks-py 1 (:8888) from 08:47.

**12 Nov 10:23 JST.** RC15 tasks-api 1 (run-92c99813, :1234, mixed) **10/10**, quality 7/7, locked 33/33, accepted at an escalation after 1 h 53 - three suite rounds lost to a false "not changed" finding (LF.854, committed, held for the Fix batch). Fix batch queued: one broken shared helper/fixture counts as one repair (2 runs tonight), LF.854, the page-test position check. Overnight: 13 of 13 scored runs at full hidden scores. RC16 fullstack-bookmarks-py 1 (:8888) in fix rounds at 15/20; RC16 wordstats-cli 1 (:1234) from 10:23.

**12 Nov 10:58 JST.** RC16 fullstack-bookmarks-py 1 (run-dbf5babe, :8888) **8/8**, locked 20/20 - RC16 1/1 full, but 2 h: three re-plans on a false "records not drawn as list items" finding (the page set `role` from its script) - LF.855 committed, held for the Fix batch with LF.854. RC16 wordstats-cli 1 (:1234) building (LF.846 fired on its first suite draft); RC16 notes-api-hono 1 (:8888) from 10:58.

**12 Nov 11:07 JST.** RC16 wordstats-cli 1 (run-855d2fe0, :1234) **8/8** in 36 min - LF.846 fired on its first draft. **RC16 2/2 full.** Overnight: 15 of 15 scored runs at full hidden scores. RC16 notes-api-hono 1 (:8888) in design; RC16 textkit-lib 1 (:1234) from 11:06.

**12 Nov 11:37 JST.** RC16 textkit-lib 1 (run-73d45df7, :1234) **8/8** in 28 min, no failed tool calls - LF.852 fired on its first draft. **RC16 3/3 full.** Overnight: 16 of 16 scored runs at full hidden scores. RC16 notes-api-hono 1 (:8888) in fix rounds; RC16 notes-api-js 1 (:1234) from 11:36.

**12 Nov 12:07 JST.** RC16 notes-api-hono 1 (run-4ac89f9d, :8888) **9/9**, locked 15/15, 62 min. **RC16 4/4 full** (fullstack-bookmarks-py, wordstats-cli, textkit-lib, notes-api-hono). Overnight: 17 of 17 scored runs at full hidden scores. RC16 notes-api-js 1 (:1234) writing its suite; RC16 web-todo 1 (:8888) from 12:07.

**12 Nov 12:57 JST.** RC16 notes-api-js 1 (run-bc3eecd1, :1234) **9/9**, locked 11/11, no KPI regression. **RC16 5/5 full** (fullstack-bookmarks-py, wordstats-cli, textkit-lib, notes-api-hono, notes-api-js). Overnight: 18 of 18 scored runs at full hidden scores. RC16 web-todo 1 (:8888) in fix rounds at 15/18; RC16 tasks-api 1 (:1234) from 12:57.

**12 Nov 14:38 JST.** RC16 tasks-api 1 (run-f78ba2fa, :1234) **10/10**, quality 7/7, locked 57/57 (escalated; prefill:decode 22.3). **RC16 6/6 full.** Fix batch now LF.854-856 committed + cause clusters to build (subsystem review `docs/reviews/test-fault-attribution-2026-11-12.md`). RC16 web-todo 1 (:8888) at 17/18 after a dispute (1 test past the cap - the stale-filter case LF.856 fixes); RC16 notes-api-falcon 1 (:1234) from 14:38.

**12 Nov 14:51 JST.** RC16 web-todo 1 (run-64bd1cd1, :8888) **10/10** but 2 h 38 - three stale-filter edit tests (LF.856's case) chased \~50 min; redundant reads 53%. **RC16 7/7 full.** RC16 notes-api-falcon 1 (:1234, no pack) in design; RC16 fullstack-bookmarks 1 (:8888) from 14:51. Plan: finish the RC16 sweep (web-todo-react, notes-api), then ship the Fix batch (LF.854-856 + cause clusters).

**12 Nov 16:09 JST.** RC16 fullstack-bookmarks 1 (run-5bdf94b7, :8888) **8/8**, locked 20/20, no failed tool calls, no KPI regression. **RC16 8/8 full.** Fix batch ready to ship after the sweep: LF.854-857 (LF.857 = one broken suite helper is one cause under the reclassification cap). RC16 notes-api-falcon 1 (:1234) at 23/25 with 2 test faults deferred; RC16 web-todo-react 1 (:8888) from 16:09; notes-api last.

**12 Nov 17:17 JST.** RC16 notes-api-falcon 1 (run-3c6f48ca, :1234, no stack pack) **9/9** after 2.5 h - its two deferred tests were test faults. **RC16 9/9 full.** RC16 web-todo-react 1 (:8888) in fix rounds (a dispute rewrote 2 tests, 1 past the cap); RC16 notes-api 1 (:1234) from 17:16 - the last RC16 family. Then the Fix batch LF.854-857 ships.

**12 Nov 18:18 JST - RC16 closed 10/10 full, Fix batch shipped.** RC16 web-todo-react 1 (run-6a6a14b7) **10/10**. RC16 covered ten families, all at full hidden scores. **Fix batch LF.854-857 deployed 18:10 (f28449e)**: a passing repaired test counts as repaired; a record role set from a script counts as drawn; a test that follows a record by the text it edits is cannot-pass; one broken suite helper is one cause under the reclassification cap. **RC17 counts from f28449e**: RC17 web-todo 1 (:8888) from 18:18; RC16 notes-api 1 (:1234) is mixed.

**12 Nov 18:27 JST.** notes-api 1 (run-36555b59, :1234, mixed after the batch) **9/9**, locked 10/10, no failed tool calls. Since last night: **22 of 22 scored runs at full hidden scores**. RC17 web-todo 1 (:8888) in design (escalated); RC17 notes-api 1 (:1234) from 18:27.

**12 Nov 23:38 JST.** RC17 web-todo 1 (run-f1336d72) **10/10**, locked 27/27; RC17 notes-api 1 (run-47c29453) **9/9**, locked 14/14 - **RC17 2/2 full** on the Fix batch build. Gap 18:47-23:32: the audit cron lapsed and both ports sat idle \~4 h; recreated. Since last night: **24 of 24 scored runs at full hidden scores**. RC17 fullstack-bookmarks-py 1 (:8888) and RC17 tasks-api 1 (:1234) from 23:38.

**13 Nov 02:28 JST.** tasks-api 1 (run-6ff14cae, :1234, mixed) **10/10**, quality 7/7. **LF.858 and LF.859 deployed 01:12 / 01:28**: a failing criterion's defect carries what the page reported while loading; a page whose own script did not run is raised alone as one cause - verified on fullstack-bookmarks-py 1 (17 blind defects -> 1; the page fixed; 2 -> 10/19 in ten minutes). Since last night: **25 of 25 scored runs at full hidden scores**. RC18 counts from cbda81d: RC18 wordstats-cli 1 (:1234) from 02:28; fullstack-bookmarks-py 1 (:8888, mixed) in fix rounds at 10/19.

**13 Nov 04:18 JST - a false acceptance, fixed.** RC18 wordstats-cli 1 (run-5ea7a3ba) **0/8**: its locked suite passed 19/19, then the release's own clean-up removed the untouched `__main__.py` as a template "nothing loads" (Python loads it for `python -m`), and the product shipped dead - caught by the re-measure only as a gap. **LF.861 deployed 04:16** (with LF.860): `__main__.py` is loaded by Python itself; a release removal that breaks the suite is put back and measured again. fullstack-bookmarks-py 1 (run-d87d7155) **8/8**. Since last night: 26 of 27 scored runs full. **RC19 counts from 4635938**: wordstats-cli 1 (:1234) and fullstack-bookmarks-py 1 (:8888) from 04:18.

**13 Nov 05:17 JST.** RC19 wordstats-cli 1 (run-60ea8418, :1234) **8/8**, 54 min, no KPI regression - **LF.861 verified** (`__main__.py` kept; the release re-measure passed) and LF.846 fired on its first suite draft. **RC19 1/1.** RC19 fullstack-bookmarks-py 1 (:8888) building; RC19 textkit-lib 1 (:1234) from 05:16.

**13 Nov 05:46 JST.** RC19 textkit-lib 1 (run-ffadb8fc, :1234) **8/8**, locked 31/31 in 28 min - LF.852 fired on its first suite draft. **RC19 2/2.** RC19 fullstack-bookmarks-py 1 (:8888) in fix rounds; RC19 notes-api-js 1 (:1234) from 05:45.

**13 Nov 06:40 JST.** RC19 fullstack-bookmarks-py 1 (run-2af25177, :8888) **8/8** after 2 h 7, accepted at an escalation with AC-2/AC-4 deferred - both met. **RC19 3/3 full** (wordstats-cli, textkit-lib, fullstack-bookmarks-py). RC19 notes-api-js 1 (:1234) at 9/12; RC19 web-todo 1 (:8888) from 06:40.

**13 Nov 07:16 JST.** RC19 notes-api-js 1 (run-d39df8f6, :1234) **9/9**, 83 min (tool failures 12%). **RC19 4/4 full** (wordstats-cli, textkit-lib, fullstack-bookmarks-py, notes-api-js). RC19 web-todo 1 (:8888) suite locked 28, building; RC19 tasks-api 1 (:1234) from 07:16.

**13 Nov 08:39 JST.** RC19 web-todo 1 (run-b13b7ac7, :8888) **10/10**, locked 28/28, no KPI regression - though a dispute's rewritten test used an anchored record filter and the fixer made the buttons label-only to satisfy it (LF.862, built, ships next). **RC19 5/5 full** (wordstats-cli, textkit-lib, fullstack-bookmarks-py, notes-api-js, web-todo). RC19 tasks-api 1 (:1234) at 11/26; RC19 notes-api-hono 1 (:8888) from 08:39.

**13 Nov 09:19 JST.** RC19 tasks-api 1 (run-fb10a44d, :1234) **10/10**, quality 7/7, locked 26/26. **RC19 6/6 full** (wordstats-cli, textkit-lib, fullstack-bookmarks-py, notes-api-js, web-todo, tasks-api). RC19 notes-api-hono 1 (:8888) building; RC19 notes-api 1 (:1234) from 09:19.

**13 Nov 09:37 JST.** RC19 notes-api-hono 1 (run-003d543f, :8888) **9/9**, locked 30/30 in 48 min. **RC19 7/7 full.** RC19 notes-api 1 (:1234) in design; RC19 fullstack-bookmarks 1 (:8888) from 09:36. LF.862 ships at the next both-ports boundary.

**13 Nov 10:49 JST - RC19 closed 8/8 full.** RC19 notes-api 1 (run-d4d901f4, :1234) **9/9**, locked 33/33, no KPI regression. RC19 on 4635938: wordstats-cli, textkit-lib, fullstack-bookmarks-py, notes-api-js, web-todo, tasks-api, notes-api-hono, notes-api - all full. **LF.862 deployed 10:47 (180627f)**: a page test matching a record by its whole text is the test's own fault. **RC20 counts from 180627f**: RC20 web-todo-react 1 (:1234) from 10:48; RC19 fullstack-bookmarks 1 (:8888) now mixed.

**13 Nov 11:06 JST - LF.863 deployed (9ba0841).** A fix split into "its tests only" now keeps the dependency manifest and lock file its tests declared (falls back to tests alone if that breaks a test). RC19 fullstack-bookmarks 1 (run-0238dd0d, mixed) **8/8**, locked 25/25 - its no-body 500 defect took 3 sprint attempts because the split dropped the test library the fix had declared. RC20 web-todo-react 1 now mixed; **RC21 counts from 9ba0841**: RC21 wordstats-cli 1 (:8888) from 11:06.

**13 Nov 11:13 JST - LF.864 deployed (78d0b44).** The filtered-view finding names the item actions the brief offers instead of "changes an item" (summed: open 3+ rounds in 6 of 23 runs, all add/remove briefs; no hidden test lost). Both live runs (web-todo-react, wordstats-cli) now mixed; **RC22 counts from 78d0b44**.

**13 Nov 11:41 JST - LF.865 deployed (3cc9b6b), scaffold-checked.** The React and Vue packs build with `tsconfig.build.json` (only `src`): a type error in a unit test no longer fails the production build and goes to a page fixer (2 of 6 earlier React/Vue runs fixed builds in tests only). browser-react and browser-vue scaffold ok. **RC23 counts from 3cc9b6b**.

**13 Nov 11:51 JST - LF.866 deployed (b182eee), 9 packs scaffold-checked.** Every simulated-page vitest config (React, Svelte, Vue, Next, full-stack page) sets `globals: true`, so Testing Library cleans up each render: the live web-todo-react run had 11 of 22 unit tests fail with "found multiple elements" on a right product (21/22 with globals on a copy); 3 of 7 earlier React runs added `cleanup` by hand. **RC24 counts from b182eee**.

**13 Nov 12:17 JST - RC21 wordstats-cli 1 (run-d9e4574c, mixed) 8/8, handoff 0.833; LF.867 deployed 12:15 (f4d7895).** The README said nowhere how to run the tool because the specification's interface contract came back empty (5 of 206 specifications); that section is now asked for again. **RC25 counts from f4d7895**: RC25 textkit-lib 1 (:8888) from 12:17; RC20 web-todo-react 1 (:1234) mixed, in its specialist reviews at 13/13.

**13 Nov 12:22 JST - RC20 web-todo-react 1 (run-ba1d9ae3, mixed) 10/10, handoff 1.0**, locked 13/13 (1 h 29; sprint 1 in three attempts: piled-up unit-test renders - LF.866's case - and a contrast fault reverted twice). RC25 web-todo-react 1 (:1234) from 12:22, the first React run on LF.865 and LF.866.

**13 Nov 12:37 JST - LF.868 deployed (c72d068).** The mutation probe (release and bench) no longer changes a markup tag's or type argument's `<`/`>` in JS/TS: on RC20 web-todo-react 1, 7 of 12 changes broke the build and were inconclusive (mutation 0 against a mean of 0.672); 105 of 129 sites on its `App.tsx` were brackets, now 0 of 24. Both RC25 runs now mixed; **RC26 counts from c72d068**.

**13 Nov 12:52 JST - LF.869 deployed (262668d).** The specification-contradiction call now records in its rulings file how many rulings it gave and why each was dropped. RC25 textkit-lib 1's call kept none (40 of 129 calls keep none), its locked suite then carried the architect's self-contradicting `truncate` example, and the reasons had been lost with the worker log. Watching for the reasons before deciding a real fix. **RC27 counts from 262668d**.

**13 Nov 13:03 JST - RC25 textkit-lib 1 (run-cd7df61a, mixed) 7/8 - FALSE ACCEPTANCE; LF.870 deployed 13:02 (e34f712).** Locked 47/47: a dispute rightly called four `truncate` tests wrong (the architect's self-contradicting example) and wrongly the right `title_case` tab test; the rewrite copied the product's output and the hidden word-after-a-tab test failed. LF.870: a whitespace test that leaves a word after a tab unchanged sends the suite back (1 of 14 stored textkit suites flagged, that one). **RC28 counts from e34f712**: RC28 textkit-lib 1 (:8888) from 13:03 to re-check it.

**13 Nov 13:21 JST - LF.871 and LF.872 deployed (630ac1c), React pack scaffold-checked.** LF.871: a suite repair's changes to tests it was not sent for are put back before the review (an audit of the runs that lost a hidden test after a dispute found 3 of 4 lost through repairs loosening tests no ruling named). LF.872: the React pack ships jest-dom and its vitest setup (16 of 26 unit tests failed without it in RC25 web-todo-react 1; 5 of 7 React runs added it by hand). LF.865 and LF.866 confirmed live: the React build is green and no renders pile up. **RC29 counts from 630ac1c**.

**13 Nov 13:31 JST - LF.873 deployed (4d66676).** The design stages are told the Python package the setup will write, by the setup's own rule (the brief's module, else the directory's name): RC28 textkit-lib 1 was told `text_toolkit_library/` while the setup wrote `textkit/`, its design escalated, and two rulings sided with the path never made - found through LF.869's new rulings record on its first use. **RC30 counts from 4d66676**.

**13 Nov 13:54 JST - LF.874 deployed (7832e3a).** A test asserting a value equals a text and has a length that text does not have cannot pass: RC28 textkit-lib 1 asserted `truncate("Hello, World!", 10) == "Hello, W..."` (11 characters) and length 10; its dispute upheld it and two fixes of a right product were reverted. 2 of 203 stored suites flagged, both real. **RC31 counts from 7832e3a**.

**13 Nov 13:58 JST - RC25 web-todo-react 1 (run-29a32727, mixed) 10/10, handoff 1.0**, locked 21/21. **LF.865, LF.866 and LF.868 verified**: the React build is green, no unit-test renders pile up, and the mutation score is 0.875 with 2 of 10 changes inconclusive (was 0 with 7 of 12). RC31 fullstack-bookmarks 1 (:1234) from 13:55.

**13 Nov 14:06 JST - RC28 textkit-lib 1 (run-e50a5dd9, mixed) 8/8, handoff 1.0**, locked 35/35. **LF.874 verified**: its two self-contradicting `truncate` tests were reopened and fixed, and the brief that gave the morning's false acceptance is clean. RC31 notes-api-js 1 (:8888) from 14:06.

**13 Nov 14:22 JST - LF.875 deployed (ed345af).** A rejected specification ruling now keeps its two quotes beside the reason: RC31 notes-api-js 1's escalation gave two rulings, both rejected as "not in the specification word for word", and the quotes are what tells whether the match is too strict. **RC32 counts from ed345af**.

**13 Nov 14:45 JST - FROZEN on ed345af as RC32.** Three audit checks since 14:22 found nothing to fix. Since 10:45: LF.862-875 deployed (14 fixes); 7 runs scored, 6 full, 1 false acceptance (RC25 textkit-lib 1, fixed by LF.870 and verified 8/8 on the same brief). From now on only a fix that costs score is deployed. The two live runs started before ed345af and count as learning; RC32 counts from the next starts.

**13 Nov 15:17 JST - RC31 notes-api-js 1 (run-b7fd8303, learning) 9/9, handoff 1.0**, locked 21/21 (59 min, no KPI past 1.5x). **RC32 wordstats-cli 1 (:8888) from 15:17 - the first run counted on the frozen ed345af.**

**13 Nov 16:06 JST - RC32 wordstats-cli 1 (run-bcdc6779) 8/8, handoff 1.0 - RC32 1/1** on the frozen ed345af (40 min; a dispute rightly corrected a test's character count; the README says how to run it - LF.867's family). RC32 textkit-lib 1 (:8888) from 16:06. Held for the next batch: LF.876 (a relative fetch before opening the page).

**13 Nov 16:36 JST - RC32 textkit-lib 1 (run-f4f91943) 8/8, handoff 1.0 - RC32 2/2.** LF.874 and LF.852 caught two weak tests at its first review, before the lock. RC32 notes-api 1 (:8888) from 16:36.

**13 Nov 17:37 JST - RC32 notes-api 1 (run-9de81b4a) 8/9 - FALSE ACCEPTANCE; freeze broken; LF.876-878 deployed (762b9c7).** The product accepted `PUT` with an empty title; the emptied-field probe never ran because the spec's contracts held only error bodies and the request bodies stood in its test cases. LF.878 reads a body written after its write from any section. Shipped with it: LF.876 (a relative fetch before opening the page cannot pass) and LF.877 (a fixer that changed nothing and names the acceptance tests calls a dispute). RC32 ended 2 of 3 full. **Learning again; RC33 counts from 762b9c7.**

**13 Nov 18:28 JST - RC31 fullstack-bookmarks 1 (run-2b7e877e, learning) 8/8, handoff 1.0**, locked 22/22 after 4 h 27 (about 2 h of fixers on tests that fetched before opening the page - LF.876 fired at 17:54 on its last one). L notes-api 9 (:1234) from 18:28 to verify LF.878.

**13 Nov 19:09 JST - RC32 tasks-api 1 (run-87ab5937, learning) 10/10, quality 7/7, handoff 0.875; LF.879 and LF.880 deployed (4115293).** LF.879: the emptied-field probe reads bodies written as prose (`{"username": ..., "password": ...}`, an unclosed `{"title": "<string>" ...`) and fields refused together ("an empty username or password"); tasks-api's probe had asked nothing. LF.880: a database the tests wrote never ships (`acceptance/.test-data/tasks.db` shipped because the plan named the runtime `tasks.db`). **RC33 counts from 4115293.**

**13 Nov 19:56 JST - LF.878/879 verified on L notes-api 9.** The emptied-field probe asked 4 of 4 writes (it asked none on the notes-api run that was a false acceptance) and caught `POST /notes` accepting a title of only spaces, which a fixer then closed.

**13 Nov 20:11 JST - LF.881 deployed (2b44a27).** An accessibility finding names the remedy for each rule it reports - for the list rule, the empty-state message goes beside the list, never inside it (3 runs broke it; one re-planned a 25/25 sprint). **RC33 counts from 2b44a27.**

**13 Nov 20:17 JST - L notes-api 9 (run-abff4e03) 9/9, handoff 1.0 - LF.878/879 verified end to end** on the brief that was 8/9 at 17:16: the emptied-field probe asked every write and caught a blank title before release. L fullstack-bookmarks-py 15 (:1234) from 20:17.

**13 Nov 20:30 JST - L web-todo 14 (run-f54fd703) 10/10, handoff 1.0**, locked 25/25 (two sprints; an empty-state message inside the list re-planned sprint 1 - the case LF.881 now names the remedy for). L notes-api-hono 8 (:8888) from 20:30.

**13 Nov 20:55 JST - LF.882 deployed (adb95b4).** A specification ruling that stands on one of the setup's own facts is kept, as a ruling for the brief is: LF.875's saved quotes showed a right ruling rejected because its standing quote was a setup fact (`start.sh` runs `node src/main.ts`), one cause of contradiction calls that keep nothing. **RC33 counts from adb95b4.**

**13 Nov 22:08 JST - L notes-api-hono 8 (run-32b38d82) 9/9, handoff 1.0**, locked 12/12 (1 h 27). L web-todo-react 3 (:8888) from 22:08 - the first React run with jest-dom in its setup (LF.872) and the accessibility remedies (LF.881).

**17 Nov 19:58 JST - catch-up (the board missed 14-16 Nov; docs/STATE.md and docs/improvement-plan.md have the full record).** Launch review LR.1-65 built; LR.30 container-mode language sweep under way on :8888. :1234 is held by the owner since 18:45 (only :8888 takes runs). Scored today: notes-api-go container 1 **9/9**, quality 8/8; notes-api-java container 3 **9/9**, quality 7/8, delivered; notes-api-rust container 1 **0/9** (failed: the specification fixed an entry Rust's server cannot run, and eight fixes were reverted for an install that was already failing). Deployed today: **LF.1029-LF.1036** - defects quoting one compiler error merged (LF.1029, LF.1033), writes under one lock in every service guide (LF.1030), LM Studio parallel slots share its window (LF.1031), Rust test imports (LF.1032), no general-purpose subagent on any hosted provider (LF.1034), a pack's design facts reach the design stages (LF.1035), a fix blamed for the install only when it worked where the fix started (LF.1036). **LF.1037** (scoring only): container-mode mutation scores are recorded again. Tests reorganised after Khorikov's book (`.claude/skills/unit-testing/SKILL.md`): about 46 tests that pinned wording or stubs removed, hundreds reworked through public paths; suites green, 17,854 passed. Live: notes-api-rust container 2, run-c7a00abc (:8888, 19:54).

**17 Nov 21:40 JST** - notes-api-rust container 2 (run-c7a00abc) **9/9**, quality 8/8, handoff 1.0 (run 1: 0/9). Deployed into it: **LF.1038-1041** (the Rust pack's known compiler errors with their cause: handler extractor order, a router still waiting for its state, `axum::test`). Built: **LF.1042** (no check reads a toolchain's build output such as `target/doc`). Measuring next: the design gate's contradiction matcher (43 mostly false findings over 4 runs). :1234 still held by the owner.

**17 Nov 23:20 JST** - notes-api-csharp container 2 (run-2a42b19c) **9/9**, quality 8/8, handoff 1.0, **delivered** - the first C# container run to deliver. :1234 released by the owner at 21:52. Deployed: **LF.1043** (mutation probe changes Rust and C# code), **LF.1044** (one point per denial at the design gate: 43 mostly false points over 4 runs came from 7 denials), **LF.1045** (a fix that leaves a manifest unreadable - C# written into `App.csproj` - is reverted). Built: **LF.1046** (the mutation probe's copy skips sockets). Live: PHP container 1 on :1234 (21/21 acceptance), Ruby container 1 on :8888.

**17 Nov 23:57 JST** - notes-api-php container 1 (run-e8e3120f, :1234) **9/9**, quality 8/8, handoff 1.0, **delivered**; mutation 7/12. Every language in the container sweep has now delivered once: Go, Java, Rust, C#, PHP (Ruby live). LF.1044 fired on the Ruby run's design gate: no denial repeated. Live: Ruby container 1 (:8888), Java container 4 (:1234).

**18 Nov 01:06 JST** - notes-api-ruby container 1 (run-c7b0d7ec) **9/9**, quality 7/8 (lost writes at 16 at once), handoff 0.875, not deliverable. All six languages in the container sweep now pass 9/9 hidden. Deployed: **LF.1047** (Ruby keeps `rackup`), **LF.1048** (Sinatra lost-writes cause), **LF.1049** (Spring `MockBean` import cause; fired on Java run 4 and the test compiled). Built: **LF.1050** (the concurrent-write probe sends 16 at once, as the hidden test). Live: Java container 4 (:1234).

**18 Nov 02:02 JST** - notes-api-java container 4 (run-b770f08f, :1234) **9/9**, quality 7/8 (lost writes now pass; `GET /notes/abc` answered 500), delivered with cuts. Deployed: **LF.1050** (concurrent-write probe at 16), **LF.1051** (the JVM's temp folder off the noexec /tmp - SQLite could not load in container mode), **LF.1052** (the 5xx probe asked at near-green rounds). :8888's model not loaded since about 00:55; nothing started there. Live: Ruby container 2 (:1234), measuring LF.1048 and LF.1050 on lost writes.

**18 Nov 03:41 JST** - notes-api-ruby container 2 (run-6a9c0fb9, :1234) **9/9**, quality **8/8**, handoff 0.875, **delivered**. First scored 0/9: the scorer's Ruby ignored gems compiled in the sandbox image; **LF.1053** reinstalls them when `bundle check` fails, and the rescore is 9/9. Every language in the container sweep now passes 9/9 hidden. Live: tasks-api container 1 (:1234). :8888's model not loaded since about 00:55.

**18 Nov 06:01 JST** - tasks-api container 1 (run-1cef3eae, :1234) **10/10**, quality **7/7**, handoff 1.0; its own verdict not deliverable (a locked test reclassified under dispute; mutation 0.1 - the locked suite is weak). Scorer fixed: **LF.1054** (handoff checks skip `vendor` and `target`; three Ruby runs had lost a point to a gem's comment). Live: Rust container 3 (:1234) to confirm this evening's Rust fixes. :8888's model not loaded since about 00:55.

**18 Nov 07:28 JST** - notes-api-rust container 3 (run-1badaa8f, :1234) **8/9**, quality 6/8, handoff 1.0, mutation 12/12; not deliverable (accepted near green with an update failing). The design fixes held on a fresh run. Deployed: **LF.1055** (a fixed compiler finding is no longer kept open by a different error in its file - seen in two Rust runs), **LF.1056** (Rust: `oneshot` takes the router by value). :8888's model not loaded since about 00:55.

**18 Nov 12:30 JST** - notes-api-java container 5 (run-14e254a1, :1234) **9/9**, quality **8/8**, handoff 1.0, **delivered** - the first Java run with every quality test (lost writes and the non-numeric id 500 now pass). notes-api-rust container 4 (run-db139a37, :8888) **0/9**, failed: `app()` declared `-> Router<AppState>` in every attempt while fixers edited `main.rs`. Deployed this morning: LF.1057-1063 (Rust and Spring known errors, the QA engineer told failing tests are expected before the build, a one-line test repair kept out of the full agent loop). Near-green switch: off per run; its default waits on the owner. Live: Rust container 5 (:8888), Go container 2 (:1234).

**18 Nov 16:50 JST** - notes-api-csharp container 3 (run-e8053d6e, :1234) **9/9**, quality **8/8**, handoff 1.0, mutation 0.67, **delivered** at an escalation after four sprint attempts and 2 h 55 min: a false red for most of the run (34 defects left open, 4 reverts, 5 min lost to false memory refusals). Deployed today: **LF.1064-1071** (Rust signature held, route-wide 500s quote the response, crates version fix, module exports only where readable, C# project SDK held, page cache is not memory in use, no model-written framework notes for a pack's framework); **LF.1072** scorer fix (tasks quality sets take any refusal of a bad id). **Deep review 2026-11-18 approved by the owner (implement all):** frozen-version measuring, language sweep and RC count paused, wave 1 (6 bundles) building. Live: PHP container 2 (:8888, re-planning), Rust container 6 (:1234, 16:49, frozen 0e092255, first run with LF.1071).

**18 Nov 20:10 JST** - notes-api-php container 2 (run-8f1478a7) **0/9**, quality 0/8, failed on its sprint time budget: invented Slim methods and a misplaced namespace kept the product from starting (7 reverts). notes-api-rust container 6 (run-1aa50e5e) **0/9**, failed: no model-written axum note reached it (LF.1071 held), but its specification planned tests on a `TestClient` axum does not have and its draft declared a `State` that clashed with axum's. Both are the baseline before the deep-review waves. **Deployed 20:09: 532dba3 - waves 1 and 2 (LF.1073-1105):** unmeasured outcome, compiler-gated rewrites, fixer checkpoints and culprit-only batch reverts, typed defects with a fix journal, start-first fixing, drafting in waves, probes at release, the contract edge probe, browser page checks, a data-calibrated verdict, unit-test quarantine, lean tool lists and sliced memory, intake questions, one language table, golden examples on seven packs, PHPStan for Slim, the dependency gate, no product code in the worker, rewind by checkpoint id, `degraded()` records, best-attempt download, a tidy handover, the run doctor and the health page. Live on it: Rust container 7 (:1234) and PHP container 3 (:8888).

**18 Nov 21:05 JST** - **notes-api-php container 3 (run-c5d6a8a5, :8888) 9/9, quality 8/8, handoff 1.0, delivered, mutation 0.64, in 44.8 active minutes with 0 reverts** - the first run on 532dba3, against PHP container 2's 0/9 in 313.6 minutes with 14 reverts. Drafting waves, the golden example, PHPStan and the dependency gate all fired, and the product started at the first test round. Deployed into Rust container 7: **LF.1106** (an offline build that cannot resolve a host failed because the product's install failed, not the environment - LF.1085 had read it as unmeasured). Live: Rust container 7 (:1234), PHP container 4 (:8888, 21:05).

**18 Nov 22:37 JST** - notes-api-rust container 7 (run-cbf36159, :1234) **0/9**, quality 0/8, failed after three sprint attempts in 134 active minutes. The design held (no `TestClient`, LF.1096) and each manifest failure was fixed in the run - **LF.1106** (an offline build that cannot resolve a host is the product's), **LF.1108** (a crate feature that does not exist is answered with the real ones), **LF.1109** (a lock file is the package manager's: a hand-written one is refused, a refused one is written again) - and then the product's own Rust code did not compile. Rust is the first family for the Haiku arm (owner approved $30 on `claude-haiku-5-5`; waiting for the key in Settings). Also: **LF.1107** prices the current Claude models; `MAX_RUN_COST_USD` defaults to $8. Live: PHP container 4 (:8888, second attempt, the product starts).

**18 Nov 23:32 JST** - **notes-api-php container 4 (run-f00ea384, :8888) 9/9, quality 8/8, handoff 1.0**, 125 active minutes, 0 reverts: PHP is 2 of 2 full on the new version (0/9 on the old). Its own verdict said not deliverable on a contract line `GET /notes/{id} -> 400` answered 404 for a non-numeric id - a false red, now **LF.1110** (a malformed request refused with another 4xx is a note; a missing record's 404 still binds). Live: C# container 4 (:1234), tasks-api container 2 (:8888, 23:30).

**19 Nov 01:40 JST** - notes-api-csharp container 4 (run-1b5b8d8e, :1234) **0/9, quality 0/8, delivered - a false acceptance**: its suite was 18/18 inside the harness after five attempts, but a re-planned work order had pointed `nuget.config` at the sandbox's own `.agent-home` package cache, so nothing restores elsewhere. Fixed as **LF.1113** (a product file naming the harness's own folder is refused, and blocks its release). Also: **LF.1111** (a package added in a nested manifest is installed), **LF.1112** (a deleted saved model stays deleted - the owner's Settings report). **Haiku arm started:** H notes-api-rust hybrid-haiku 1 (run-160e0f62, 01:25) - the architect's calls reach `claude-haiku-5-5`, building stays on the local model; $8 ceiling per run.

**19 Nov 02:45 JST** - tasks-api container 2 (run-58e79fce, :8888) **10/10, quality 7/7, handoff 1.0, mutation 0.545, 143.7 active min, 2 reverts** - but the harness called it not\_deliverable: the release contract probe made unsigned calls to lines about a signed-in caller and read the 401s as a broken contract. Fixed as **LF.1116** (behind a sign-in, a bare line answered 401/403 unsigned is listed as unchecked, not failed); committed e3c47a9c, deploys at the next run boundary. Open: the edge probe skipped all 22 of its checks with "sign-in answered first" - being traced. Next: web-todo container 1 started 02:37 on :8888; the Haiku hybrid Rust run (run-160e0f62, :1234) is in its second sprint attempt at $0.63 hosted spend.

**19 Nov 03:20 JST** - Haiku arm, notes-api-rust hybrid 1 (run-160e0f62, :1234 build model, claude-haiku-5-5 for judgement) **9/9 hidden, 7/8 quality, 88 active min, $0.87 hosted** - the first Rust 9/9 on the new version (local-only Rust runs 1, 4, 7 were 0/9). Verdict not deliverable on a real gap (a spaces-only title accepted). Fixes since: **LF.1117** (the release probes now sign in when the specification writes its sign-up body with `<string>` placeholders - the root cause behind LF.1116), **LF.1118** (a changed-declaration defect also names the callers that pass it arguments - four Rust fix attempts were lost to it), **LF.1119** (opening a run store beside the nightly backup no longer stalls the app; it hung 03:05-03:09). LF.1116-1118 shipped 03:10, LF.1119 shipping now.

**19 Nov 04:12 JST - correction to the Haiku Rust result.** The Rust 9/9 was largely **Haiku-built**, not judgement-only: the architecture review escalated, and the rung that moves a retried sprint to the judgement model read that design escalation, so every specialist, drafting and fix stage ran on Haiku (146 calls). The C# Haiku run (run-04f2aa30, live) is built the same way and will finish as such. Fixed as **LF.1123** (a design escalation no longer moves the build); the true judgement-only hybrid arm is still to be measured. Also live since 03:59: **LF.1120** (no lookup tools for a stage researched before it began), **LF.1121** (a script looking up an id no page declares is a proven defect - web-todo lost 40/46 tests to it), **LF.1122** (an acceptance file runs once per product while defects are dispatched - 53 runs in 20 minutes on one unchanged product). Hosted spend $1.37 of $30.

**19 Nov 05:35 JST** - two full scores. **web-todo container 1** (run-3cc0ed29, :8888) **10/10, 6/6, delivered**, handoff 1.0, mutation 1.0, 129 active min. **C# Haiku 1** (run-04f2aa30, :1234) **9/9, 8/8, delivered**, handoff 1.0, mutation 0.8, 101 active min, $1.31 hosted - the first full C# score (Haiku-built). Fixed during them and live since 04:59 (031e9c05): **LF.1124** (a hosted reply's thinking-and-text blocks were written into five source files as their Python form), **LF.1125** (the delivered-product start of a toolchain that restores when it starts gets a network and the restored cache - NU1301 in every round before; the root cause of C# run 4's false acceptance too). Now live: Rust hybrid 2, the first true judgement-only Haiku run (LF.1123), and tasks-api 3 (verifies the probes sign in, LF.1117). Hosted $2.18 of $30.

**19 Nov 09:05 JST** - **Rust hybrid 2** (run-82f66a50, :1234) **9/9, 7/8, delivered with cuts**, handoff 0.857, mutation 1.0, 111 active min, $1.45 hosted. First attempt judgement-only (local build stalled on compile errors), then Haiku-built after the re-plan. **LF.1126** fired after a rewind to the first design review: the specification was corrected and `pub fn app()` was kept in the code for the first time on Rust. The lost quality test (a blank title accepted, as in Rust Haiku 1) traced to **LF.1127**: every contract line was written `AC-n route METHOD /path -> status`, none was read, and no probe tried a blank title - the reader now accepts that and a reason after the status (40 earlier corpus lines now read, none worse). Hosted $3.10 of $30.

**19 Nov 10:56 JST** - **tasks-api container 3** (run-af4108e6, :8888) **10/10, 7/7, not deliverable**, handoff 1.0, 315 active min - the verdict is right about a real defect the hidden tests do not reach: the product opens a SQLite connection per request and never closes it, so the locked suite's sequence hangs (AC-12). The fixers were shown "database is locked" from the service log; the local model never closed the connection. Fixed since 10:00 and live: **LF.1128** (a unit run that crashed after its totals is described by the crash, not "Failed: 0"), **LF.1129** (a fresh conversation of a stage is not refused a file it never read). Started: **Rust container 8** on :8888, the first local-only Rust run on LF.1118/1126/1127. C# Haiku hybrid 2 continues on :1234.

**19 Nov 11:05 JST** - **C# Haiku hybrid 2 (judgement only)** (run-e68d3ce9, :1234) **3/9, 4/8, failed** after two re-plans stalled, 98 active min, $0.43 hosted. Its product refused valid bodies with 400 and its API tests crashed the test host (`PORT` unset) - the defect now says so (**LF.1128** fired; before, it read "Failed: 0"). **The hosted test so far:** Haiku-built Rust 9/9 and C# 9/9; judgement-only C# 3/9, and judgement-only Rust reached 9/9 only after its build moved to Haiku. The build model carries the hard languages. Next: the web-todo hybrid arm on :1234; Rust local container 8 on :8888. Hosted $3.30 of $30.

**19 Nov 12:08 JST** - **Rust container 8** (run-eaed36e7, :8888, local only) **0/9, failed** - the product never compiled (12 borrow/ownership errors). Every Rust fix fired: the specification's `app()` contradiction raised (LF.1126) and ruled for the setup (**LF.1130**, live 11:21), the entry-file contract folded into the start defect instead of waiting behind it (**LF.1131**, live 11:44), and the dependency pinned to one the toolchain builds. Local Rust is 0/9 in four runs, all compile failures; Haiku-built Rust 9/9 twice - the remaining limit is the local model's Rust. Started: **C# container 5** (local) on :8888 to measure LF.1125/1128/1131 on a local build. web-todo Haiku hybrid continues on :1234.

**19 Nov 13:05 JST** - **web-todo Haiku hybrid 1** (run-249303db, :1234) **9/10, 6/6, delivered - a false acceptance**, 96.5 active min, $0.18 hosted. A late fix made the Done control toggle a row's class in place instead of re-rendering, so a task completed while the "active" filter is on stays listed; the locked suite (27/27) never completes a task under a filter. Fixed since 12:00 and live: **LF.1132** (a package lookup offers the newest release the image's toolchain builds - Rust and C# each lost an attempt to a too-new dependency today). Started: **tasks-api Haiku hybrid 1** on :1234 (the last planned hybrid arm). C# container 5 (local) continues on :8888. Hosted $3.50 of $30.

**19 Nov 13:40 JST** - **C# container 5** (run-d74ff9cb, :8888, local only) **9/9, 7/8, not deliverable - and right**, handoff 1.0, 83 active min - the **first full local C# score** (C# 4 was 0/9, a false acceptance). The one defect it left open, concurrent writes not each kept (the harness's concurrent-write probe), is exactly the one quality test lost. The overnight C# fixes fired: the delivered start with a network and the restored cache (**LF.1125**), the crash named instead of "Failed: 0" (**LF.1128**), the setup's contract folded into the start defect (**LF.1131**); a too-new dependency (NU1202) was recovered by its fixer, and **LF.1132** now prevents it. tasks-api Haiku hybrid 1 continues on :1234.

**19 Nov 15:13 JST** - **Go container 1** (run-7880a2c0, :8888, local only) **9/9, 8/8, delivered**, handoff 1.0, mutation 0.9, 73 active min. Its first attempt never started: the drafted `go.mod` needed `go mod tidy`, which only the install's network can run - fixed for new runs as **LF.1134** (every Go pack tidies in its install; verify\_packs 3/3 ok). Also live since 13:56: **LF.1133**, SQLite connection guidance for every stack on SQLite (two runs today lost hours to a connection leak and lost concurrent writes). Started: **Java container 1** on :8888. tasks-api Haiku hybrid 1 is in sprint 2 on :1234.

**19 Nov 15:55 JST** - **tasks-api Haiku hybrid 1** (run-23078e72, :1234) **10/10, 7/7, delivered**, handoff 0.875, 148 active min, $1.34. The four planned hybrid arms are done: judgement-only on Haiku delivers full scores on tasks-api and (with one false acceptance) web-todo, but not on C# (3/9) or Rust without moving the build up - **the build model is what carries the hard languages**. Hosted total about $4.80 of $30. A waste found: reviews answered in parts re-read the same files in every part (36% identical calls this run) - a design item, not a quick fix. Started: **PHP container 5** (local) on :1234; Java container 1 continues on :8888. Also live: **LF.1135** (a test's name read as a file is pointed at its file).

**19 Nov 17:30 JST** - **PHP container 5** (run-34ea7163, :1234, local only) **9/9, 8/8, delivered**, handoff 1.0, mutation 0.89, 89 active min, 0 reverts, 0 defects left open. One install failure reached its fixer as Composer's usage text with the error cut off - fixed as **LF.1136** (an install failure leads with the installer's own error lines). Local scores today: tasks-api 10/10, web-todo 10/10, C# 9/9, Go 9/9, PHP 9/9; Rust 0/9 (the local model). Started: **Ruby container 1** on :1234; Java container 1 continues on :8888 (sprint 1 attempt 3, Spring routing).

**19 Nov 19:14 JST** - **Java container 1** (run-5c68f972) **9/9, 6/8, not deliverable - and right** (a non-numeric id answered 500; the harness's probe raised it, the local model did not fix it) - the first full hidden score for local Java. **web-todo container 2** (run-686e8d70) **10/10, 6/6, delivered** in 64 active min, no KPI regression. Fixed and live since 17:00: **LF.1137** (an install refused on a lock file out of step with its manifest installs again without it), **LF.1138** (a version the registry lacks is named with the registry's release for Bundler, Composer and NuGet too - fired on Ruby 1's invented `sqlite3 ~> 1.0.2`). Started: **tasks-api container 4** on :8888 to measure the SQLite guidance (LF.1133); Ruby container 1 continues on :1234.

**19 Nov 22:17 JST** - **Ruby container 1** (run-7a5a4556, :1234) **9/9, 8/8, delivered**, handoff 1.0 - every local family has now scored full on hidden tests today except Rust (tasks-api, web-todo, C#, Go, PHP, Java, Ruby). Ruby took 267 active min: an invented `sqlite3 ~> 1.0.2` failed every install and QA chased it - fixed as **LF.1138** (the registry's release is named) and **LF.1139** (QA is told the product does not install and the manifest is not its). Measured working: **LF.1133** - tasks-api container 4's database code has WAL, a busy timeout and a request-scoped connection closed in `finally`, where container 3 leaked. An evening restart left the :8888 model unloaded; the run on it was paused until the owner loaded it, both resumed. Started: **Go container 2** on :1234 to measure LF.1134.

**19 Nov 22:52 JST** - **tasks-api container 4** (run-ab877193, :8888) **10/10, 7/7, delivered with cuts**, handoff 1.0, **96 active min against container 3's 315 on the same brief** - the SQLite guidance (**LF.1133**) measured working: correct connection handling from the first draft, no leak, no five-hour fix loop. Started: **C# container 6** on :8888 (measures LF.1132's version lookup and LF.1133 on C#'s concurrent writes); Go container 2 continues on :1234.

**20 Nov 00:18 JST** - **C# container 6** (run-840dfaf1, :8888) **9/9, 8/8, delivered**, handoff 1.0, mutation 0.86, **53 active min** - the best local C# run; the concurrent-writes quality test C# container 5 lost now passes, so the SQLite guidance (**LF.1133**) holds on C# too. The routine audit job had expired at 23:46 (its 7-day limit); recreated at 00:16, and the missed scoring done. No new run on :8888: its model is downloaded but not loaded (the gated start refused, NOT READY) - waiting for the owner to load it. Go container 2 continues on :1234.

**20 Nov 00:28 JST** - **Go container 2** (run-6d577fad, :1234) **9/9, 8/8, delivered**, handoff 1.0, 120 active min. **LF.1134** measured: no "go.mod needs tidy" failure all run (Go container 1 lost an attempt to it). :8888 is held by the owner from 00:25 - runs on :1234 only. Started: **Java container 2** on :1234.

**20 Nov 01:36 JST** - **web-todo container 3** (run-0080bed4, :8888) **10/10, 6/6, delivered**, handoff 1.0, no false acceptance. A colour-contrast defect took four rounds: the remedy told the fixer to keep the page's own colour names, and the failing colour was one - **LF.1144** now names the nearest shade that reads. Built from the audits since 00:40 and **shipped live at 01:33** (Java container 2 marked mixed): **LF.1140** (web search asks the developer sources - the general engines refuse the private instance, so every search had come back empty), **LF.1141/LF.1143** (action-verb reading: a state and its opposite, the comma before "and", toggle), **LF.1145** (a failed start shows the error it stated, not only its stack frames - Java's product exited at start for two rounds with only frames shown). **LF.1142**: a fully green suite no longer exits 1. Plan: internet lookups when agents are stuck, Appendix 10 (WL). Started: **Ruby container 2** on :8888; Java container 2 continues on :1234.

**20 Nov 02:15 JST** - **Java container 2** (run-e382df47, :1234) **0/9, 0/8, failed**, 84.6 active min, mixed. The product never started: the stack was chosen as "SQLite via H2's SQLite mode" - H2 has no such mode - and SQLite's busy timeout went into H2's connection URL. Three fixes from this run, all shipped live: **LF.1145** (the failed start shows the error it stated, not only stack frames), **LF.1146** (the Spring pack names this H2 refusal and the ways out), **LF.1147** (a defect that gains a known cause after its per-defect call ceiling gets one more attempt - the attempt that carried the cause was skipped and the run stopped). Open: a stack decision naming one engine "via" another's mode should go back before the specification. Started: **Java container 3** on :1234 at 02:04; Ruby container 2 continues on :8888.

**20 Nov 02:57 JST** - **Ruby container 2** (run-1a8bcfcf, :8888) **9/9, 8/8, delivered**, handoff 1.0, mutation 0.86, **63.7 active min against Ruby container 1's 267**, 0 defects left open - installed first time, one edge-case defect fixed in two rounds. Shipped live since 02:12: **LF.1148** (a `vendor/` folder a tool fills, known by the manifest beside it, is out of every stage's listing and the project memory - Ruby's listings had named \~780 gem files) and **LF.1149** (a service that stops because its fresh `DATA_DIR` does not exist yet is told to create it at start - Java container 3's case). Started: **PHP container 6** on :8888; Java container 3 continues on :1234.

**20 Nov 03:27 JST** - **Java container 3** (run-9c875db7, :1234) **9/9, 8/8, delivered**, handoff 1.0, 62.7 active min - every quality test, against Java container 2's 0/9 the same night. Its product also failed to start at first (the database folder under `DATA_DIR` was never made), but **LF.1145** showed the real cause from the first round instead of stack frames, and it was fixed within the attempt. Started: **C# container 7** on :1234 at 03:23; PHP container 6 continues on :8888.

**20 Nov 03:47 JST** - **PHP container 6** (run-bf4765fa, :8888) **9/9, 8/8, delivered**, handoff 1.0, **41.6 active min - the fastest PHP run**, 0 defects left open. Found in it and shipped live at 03:44: **LF.1150** - in container mode the harness's own start probe had its readiness path `/health` rewritten to `../health` (a rewrite meant only for a model's workspace paths), so every probe of a product that did start got no answer and its real error went unshown; **LF.1151** - the Slim pack names Slim 4's middleware shape (a Slim 3 `callable $handler` failed every request). Started: **tasks-api container 5** on :8888 at 03:46; C# container 7 continues on :1234.

**20 Nov 05:06 JST** - **C# container 7** (run-f37cd853, :1234) **9/9, 8/8, delivered**, handoff 1.0, mutation 1.0, 86.6 active min. It lost its first attempt and half of its second to a chain of compile errors, each rewrite fixing one and writing the next - and the cause was the harness's: **the compiler check had never run on the C# pack's own layout** (project files under `src/App` and `tests/UnitTests`, nothing at the top), so no rewrite was ever told what the compiler still reported. **LF.1152** (live 04:14) builds the project file that references the others; attempt 3 went 0 -> 10 -> 18 of 18 criteria. Started: **Go container 3** on :1234 at 05:05; tasks-api container 5 continues on :8888 (sprint 2, 16 of 21 criteria).

**20 Nov 06:35 JST** - **Go container 3** (run-2be2b208, :1234) **9/9, 8/8, delivered**, handoff 1.0, 78.5 active min. Its first two attempts were lost to one import line (`notes_api/store` under `module notes-api`) and a correctly reverted half-fix; attempt 3 passed 18 of 18 from its first round. Shipped live from it: **LF.1154** (`read_docs` reads a Go module's documentation from pkg.go.dev - the architect had been told twice that nothing existed for `modernc.org/sqlite`) and **LF.1155** (every Go pack explains "is not in std"). tasks-api container 5 is at 20 of 21: two locked tests send the sign-in JSON object as the bearer token (verified) and are past their repair cap - filed as a design item. Started: **web-todo container 4** on :1234 at 06:34.

**20 Nov 07:02 JST** - **tasks-api container 5** (run-ea01f85c, :8888) **10/10, 7/7, delivered with cuts**, handoff 1.0, 175 active min (container 4: 96). Every hidden and quality test passed; the time went on two sprints and about an hour at 20 of 21, held there by two locked tests that send the sign-in JSON object as the bearer token - verified wrong, called wrong by the dispute, past their repair cap. Filed as a design item: accept with contested tests only after a mechanical confirmation of the dispute's claim. Started: **Ruby container 3** on :8888 at 07:01; web-todo container 4 continues on :1234.

**20 Nov 08:06 JST** - **Ruby container 3** (run-62a7d976, :8888) **9/9, 8/8, delivered**, handoff 1.0, mutation 1.0, **56 active min, 0 defects left open** - 18 of 18 after one fix round; Ruby is 2 of 2 full tonight, each in about an hour (container 1: 267 min). Shipped from it at 07:43: **LF.1156** - the service packs' suite guide shows how to send a malformed JSON body (its acceptance author had spent 12 minutes searching installed Playwright source, its documentation lookup having returned only the README). Started: **PHP container 7** on :8888 at 08:05; web-todo container 4 continues on :1234 (11 of 16, fixing).

**20 Nov 08:53 JST** - **web-todo container 4** (run-09fc4306, :1234) **10/10, 6/6, delivered**, handoff 1.0, mutation 0.83, 124.5 active min. **LF.1144 measured working**: the colour-contrast defect closed in one 2-call rewrite with the computed shade (container 3: four rounds); the action-verb notes LF.1141/1143 removed did not recur. Started: **Java container 4** on :1234 at 08:52; PHP container 7 continues on :8888 (re-planning after a shared 500 on every route).

**20 Nov 09:36 JST** - **PHP container 7** (run-aa3693b6, :8888) **9/9, 8/8, delivered**, handoff 1.0, 77.6 active min. Its first attempt was lost to one shared 500 on every route; the second passed 18 of 18 from its first round. PHP is 2 of 2 full tonight. Filed (low priority, behind a switch): send the mutation gaps found in one file to one fixer - three ran in turn here (38 calls, 15 min); across tonight 4 of 11 runs fixed gaps, most in under 2 min. Started: **C# container 8** on :8888 at 09:35; Java container 4 continues on :1234.

**11-09 20:16 JST:** deployed 53c06750. Built and deployed since 15:00:

- LF.772: counts computed, not typed;
- LF.773: placeholder commands unchecked;
- LF.774 and LF.775: sampling by mode, on for both ports;
- LF.776: a dispute holds the test's own criterion (switch, off; it worked live once);
- LF.777: a reply's edits to one file that parse only together become one;
- LF.778: tests called wrong past the cap are carried to release.

Register rows: M9 (2 pairs: 1 false acceptance on, 0 off; stays off), M10 (firing signals), M11 (sampling by mode, on). Live: M9 on wordstats-cli 10 (:8888), L tasks-api 9 (:1234).

**11-09 11:36 JST:** :1234 is on hold (owner). tasks-api 8 scored 10/10 (handoff 1.0). M9 on wordstats-cli 4 scored 6/8, a false acceptance: the brief leaves the printed case of a word ambiguous. It is void as an M9 arm (LF.768: the switch did not reach the model; fixed and deployed as ffbbb46f). Also built: LF.767 (a generated register row per switch in `docs/measuring.md`, with "no signal" where firing cannot be read: 51 of 58) and LF.769 (contract placeholders match any value). A fresh M9 on arm starts on :8888 once LF.769 is deployed.

**11-09 10:58 JST:** textkit-lib 2 scored 8/8, handoff 1.0: the fourth full-handoff release in a row. Deployed as c46bb201: LF.764 (installing the project itself is no dependency), LF.766 (a project's own venv is named, not "install it"), and LF.765, the `REVIEWS_WITHOUT_REASONING` switch (Efficiency, off; M9). The M9 measurement started with "M9 on wordstats-cli 4" on :8888 (switch on). The off arm and the swapped pair follow on one commit.

**11-09 09:47 JST:** wordstats-cli 3 and fullstack-bookmarks-py 10 scored 8/8 with handoff 1.0. LF.763 (`python -m` may run the workspace's own module, so a command-line product's contract lines are checked) is deployed as 9e3aadd5. L textkit-lib 2 (:8888) and L tasks-api 8 (:1234) started at 09:46 to measure LF.756 and LF.763, and LF.757, LF.758 and LF.760.

**11-09 09:07 JST:** LF.751 to LF.760 are deployed: at 08:31 after a Docker Desktop restart (with the owner's standing permission), built with an anonymous Docker config (LF.761, which needs no deploy). LF.762, a docstring no longer counts as using a removed name, deployed at 08:51 (7ef53269). notes-api 6 scored 9/9 with handoff 1.0; tasks-api 7 failed with a 10/10 product. L wordstats-cli 3 started on :8888 to exercise LF.756.

**11-09 07:58 JST:** notes-api-hono 4 scored 9/9 (handoff 0.875). L notes-api 6 started on :8888. Built and tested, not deployed (Docker Desktop): LF.757 (no route added only for the tests), LF.758 (Python packs run the suite with `--confcutdir=acceptance`, so a product `conftest.py` cannot skip a locked test), LF.759 (prose settings reach the README; the scorer counts only named variables). tasks-api 7 is in a suite loop caused by a product `conftest.py` that skips a locked test, the case LF.758 fixes.

**11-09 07:08 JST:** textkit-lib 1 scored 8/8 (handoff 0.833) in 22 minutes. L notes-api-hono 4 started on :8888. Built and tested, not deployed (Docker Desktop's compose call hangs): LF.755 (page lines written near the contract's form are checked) and LF.756 (command lines that say what they print are checked, and feed the README's usage examples), with LF.751 to LF.754 before them.

**11-09 06:30 JST:** web-todo 7 scored 10/10 (handoff 0.857), on 760ae09a. LF.751 (thinking-aloud comments removed at release), LF.752 (no deploy left hanging on a container at Created, and no docker call keeps a lock), LF.753 (no rebuild of a commit already built; `SHIP_COMMIT`) and LF.754 (STATE reads the running worker's commit) are built and tested, not deployed: two deploys hung in Docker Desktop's compose call. Queued next: lenient page lines in the interface contract (87 of 274 runs carry unreadable ones).

**11-09 05:05 JST:** fullstack-bookmarks-py 9 scored 8/8 (handoff 1.0) and wordstats-cli 2 scored 8/8 (handoff 0.833). LF.750 is deployed (760ae09a): a clean-up is blamed only for tests it broke. LF.739 (the README for command-line products) is tested and has worked in a live run. Now running: tasks-api 7 on :1234 and web-todo 7 on :8888.

**Update 2026-11-09 03:53 JST.** **L notes-api-falcon 10 (run-bec09178) completed 03:33: hidden 9/9, handoff 1.0**, locked 27/0 - the first custom-stack run on today's setup changes (setup on its layer, 0 lines beyond its files, proven at the 2nd attempt). Fixed from it and the runs before: LF.745 (a layered setup is kept for reuse), LF.746-748 (refusals that say what to do), LF.747 (run-only testing orders left to the test round), LF.749 (a deferred criterion whose tests pass at release is a note: 29 runs carried the false line). **Six of six runs today at full hidden marks.** Live: L fullstack-bookmarks-py 9 (:1234, round 2 fixes, \~4 h); L wordstats-cli 2 (run-3f858a3b, :8888) started 03:49. Watch: capped fixer replies (2 of 30 runs, \~16 min a run that has one) - too rare to change the cap.

**Update 2026-11-09 00:57 JST.** **L notes-api 5 (run-4b3287dd) completed 00:52: hidden 9/9, handoff 1.0** (the first full handoff), locked 13/0, mutation 0.333, defects left open 7. Five of the six runs today escalated after their second design review (only web-todo 6 did not): D.3 and D.7 are the first switches to measure. LF.744: the audit names the whole design phase. Live: L fullstack-bookmarks-py 9 (:1234, building); L notes-api-falcon 10 (:8888) started 00:57 - the first live test of the setup changes LF.732-734.

**Update 2026-11-09 00:03 JST.** **L notes-api-hono 3 (run-9a18d077) completed 23:49: hidden 9/9**, locked 11/0, design escalated after the second review (DR-6; an earlier note here said it did not - corrected 00:26). web-todo 6's mutation 0 traced to a page running inline code beside an unloaded 410-line `src/main.js`: LF.742 deployed (named to builders, fixers and the release). LF.743: the handoff score follows a start into the program that reads PORT. Today's four finished runs: 8/8, 10/10, 10/10, 9/9. Live: L fullstack-bookmarks-py 9 (:1234), L notes-api 5 (run-4b3287dd, :8888, started 23:59).

**Update 2026-11-08 23:43 JST.** **L web-todo 6 (run-daab28e9) completed 23:28: hidden 10/10**, locked 18/0, handoff 0.857; mutation 0 against a 0.567 mean (to look at). It shipped 7 false "does not keep its interface contract" warnings for page controls that appear only once a task exists - a note recurring in 13 runs (12 of them 1.0): fixed as LF.741 and deployed. Today's runs so far: wordstats-cli 8/8, tasks-api 10/10, web-todo 10/10. Live: L notes-api-hono 3 (:8888, fixing); L fullstack-bookmarks-py 9 (run-1e6f6436, :1234) started 23:42.

**Update 2026-11-08 22:58 JST.** **L tasks-api 6 (run-ed4e910f) completed 22:42: hidden 10/10, quality 7/7**, locked 33/0, handoff 0.75 (a database shipped beside the code; a thinking-aloud comment in a test). LF.740 deployed 22:55 (databases the run wrote do not ship). The 21:50 and 22:55 deploys paused at a stage boundary with no call cut. Live: L web-todo 6 (run-daab28e9, :1234) fixing after its first test round; L notes-api-hono 3 (run-9a18d077, :8888) started 22:55.

**Update 2026-11-08 21:56 JST: the first runs on today's fixes.** Models back 21:04 (:1234) and 21:06 (:8888); both runs resumed. **L wordstats-cli 1 (run-885a8285) completed 21:41: hidden 8/8**, locked 15/0, 62 active min, handoff 0.714, mutation 0.455 (one survivor in analyzer.py). Seen firing live: draft records (4 of 4 at the first pass), dispute outcome (2 called wrong, reopened), probe coverage, rewrite replies, the harness plan dispatched with no resend (tasks-api 6), and on the 21:50 deploy the build before the pause (26 s) and the pause at the stage boundary (no call cut). Fixed from what they showed: LF.737 run time leaves out every stop (app only), LF.738 overall tokens/s (3.3 to \~90-100; app only), LF.739 a CLI README says how it is used. **L tasks-api 6** running (:8888); **L web-todo 6 (run-daab28e9)** started 21:55 on :1234.

**Update 2026-11-06 20:55 JST.** Learning runs continue. Live version ef6ec00 (LF.637). Every fix below is deployed.

**Finished today (hidden tests):**

| Run | Score | What it showed |
| --- | --- | --- |
| L web-todo 1 (:8888) | 10/10 | Over-specified AC-13 test; four fixes reverted chasing it |
| L tasks-api 2 (:8888) | 10/10, escalated | A test ruled wrong was never repaired (LF.628, LF.630) |
| L notes-api 2 (:8888) | 9/9 in 54 min | The fastest clean run, fully on the current harness |
| L fullstack-bookmarks-py 2 (:1234) | 8/8, cancelled | Right product held about 20 h by false suite findings and test faults (LF.606-627) |
| L web-todo 2 (:1234) | 9/10, false acceptance | Phone overflow dropped when a kept measurement was rebuilt (LF.636) |
| L fullstack-bookmarks-py 3 (:8888) | 7/8, false acceptance | "Delete" found by substring while the product named each "Delete \<title>" (LF.637) |
| L fullstack-bookmarks-py 4 (:8888) | 7/8, false acceptance | Title shown as text, URL linked; the suite found the link by locator('a') (LF.642). Also fixed in it: unawaited header reads (LF.638-639), dispute quote guard (LF.640-641) |
| L web-todo 3 (:1234) | 10/10 | Right product held by two tests counting 3 after making 2; the quote guard refused right rulings until LF.640-641. First scored against the wrong benchmark (LF.643) |
| L notes-api-hono 1 (:1234) | 9/9 | Design escalated over behaviour planned in the kept main.ts (LF.645); final brief check falsely called update undelivered, PUT route not read as update (LF.648) |
| L tasks-api 3 (:1234) | 10/10 | Architect's core lost as an empty answer call (LF.650, 37 cases in 10 runs); mutation 0.167 from unit tests that never held the code |
| L fullstack-bookmarks-py 6 (:8888) | 8/8 | First full score in the family tonight: plain-page pack (LF.644), links by title (LF.642), shared-list counts sent back at the lock (LF.651, after a rewind) |
| L notes-api 3 (:1234) | 9/9 | Clean run: tool failures 1.7%; restart persistence fixed in one round; one mutation gap closed with a proven test |
| L web-todo 4 (:1234) | 10/10 | Locked suite clean on every new check at the lock; design approved without escalation. Frozen on 37b777c6 after it: RC13 counts from here |
| RC13 notes-api-hono 1 (:1234) | 9/9 | First run on the frozen 37b777c6: 51 min, one fix stage, locked suite 10/10; mutation 0.417 |
| L fullstack-bookmarks-py 7 (:8888) | 8/8, cancelled | Right product held 3 h by a racy two-saves test (LF.656: wait for the first record before typing the second). Clean count restarts as RC14 on f0c83ed9 |
| RC14 fullstack-bookmarks-py 1 (:8888) | 8/8 | \~60 min on f0c83ed9; suite clean on every check at the lock; LF.656's wait present |
| RC14 tasks-api 1 (:1234) | 10/10 | \~3 h 50 min: 7 reverts, 15 defects open, identical calls 10% - the fix-loop waste in the harness review |
| SF baseline notes-api-falcon 2 (:1234) | 0/9, false acceptance | Setup left to the agents; start.sh worked only inside the sandbox (LF.662) |
| SF baseline notes-api-falcon 3 (:8888) | 9/9 | Setup left to the agents; LF.657-662 carried it |
| SF.2 notes-api-falcon 4 (:1234) | 9/9 | First run on the runner layer: setup proven first attempt in \~3 min; \~66 min run |
| SF.2 notes-api-falcon 5 (:8888, mixed) | 9/9 | \~2 h 40. The specification's WSGI app under an ASGI server broke the start: 15 fixes in a row reverted until LF.667 (full failure output) - then five kept within 10 min. Found LF.665-669 (guide, proven entry, failure ends, broken-start streak). |
| L tasks-api 4 (:1234, mixed) | 10/10 | Escalated, not released (last two attempts did not beat the best); locked 39/39; the AC-18 dispute repaired a wrong test; false 'ships no unit tests' gap from a builder's --collect-only report fixed as LF.670. |
| L notes-api-falcon 6 (:8888, mixed) | 0/9 - false acceptance | Locked 33/33. The setup stage wrote the whole product; MEASURE\_ONCE reused the pre-lock measurement, which skipped the own-start check, and start.sh ran a bare python3 without Falcon. Fixed as LF.676 (also LF.672/673 found here). |
| L notes-api-falcon 7 (:1234, mixed) | 9/9 | \~1 h 47. Setup proven first attempt and in scope; builders kept its falcon.asgi.App (LF.666); the async-responder cause fixed in one round (no revert streak, cf. falcon 5's 15). 5 defects left open. |
| L notes-api-falcon 8 (:8888, mixed) | 9/9 | 53 min, the fastest falcon run; locked 28/28. Released on its locked suite alone (no code review in fast delivery). |
| L notes-api-falcon 9 (:1234, mixed) | 9/9 | \~1 h 51. First falcon design approved without escalation; a milestone send-back on a code-reading KeyError finding (\~20 min, G3's case); one 42.9k-token salvaged planning reply led to LF.683. |
| L tasks-api 5 (:8888, mixed) | 10/10 (quality 6/7) | \~1 h 55; released, not escalated (cf. tasks-api 4); a dispute repaired one test, one re-plan; locked 18/18. |
| L notes-api 4 (:1234, mixed) | 9/9 | \~1 h 24; locked 23/23; settled green with one unit test asking for an OSError the product never raises; a dispute and one re-plan. |
| L web-todo 5 (:8888, mixed) | 10/10 | \~3 h 30 incl. \~25 min of deploy pauses (two Docker Desktop create hangs); 14 defects left open, 3 reverted (an accessibility fix vs the empty-title tests), one re-plan. Second harness review (HR2) merged 11-08 00:33: docs/harness-review.md Part 2. |
| L notes-api-hono 2 (:8888, mixed) | 9/9 | \~35 min; locked 10/10. A false ES-module finding on a passing Playwright spec sent two fixers to package.json; both broke the start and were reverted (LF.669's streak note recorded); fixed as LF.695. |
| L fullstack-bookmarks-py 8 (:1234, mixed) | 8/8 | \~3 h 27; locked 16/16; a dispute reclassified the newest-first test; one re-plan; full score on the family with the highest false-acceptance rate. |

**Fixes since 11-05 22:00, by kind:**

- **The suite's own checks were wrong, and sent right suites back:**
  - LF.606: the product's 500 page was blamed on the tests.
  - LF.611: a value sent to the product was treated as never given.
  - LF.616: a filter you type into was not counted as a view acted within.
- **The suite missed test faults:**
  - LF.609: "cannot pass" findings were locked in at the review limit.
  - LF.625, LF.626, LF.627: page assertions without `await`.
  - LF.634: regex escapes written into a text locator.
  - LF.637: brief-named controls found by part of their name.
- **Disputes and repairs:**
  - LF.622: the dispute judge now gets the brief-over-spec rule.
  - LF.628, LF.633: correct rulings are no longer refused for the form of their quote.
  - LF.630: a repair must change each test it was sent for.
- **Evidence for fixers:**
  - LF.607: a fixer sees its own criterion's failing tests.
  - LF.632: a fixer sees what the page reported when it loaded.
  - LF.629: a test-file finding goes to the testing role.
- **Probes and packs:**
  - LF.600, LF.603, LF.604, LF.605: Python services get the contract probes, signed in.
  - LF.631: full-stack packs ship and keep `start.sh`.
- **Memory and prompts:**
  - LF.610, LF.612: less duplicated material in the technical lead's memory.
  - LF.613-615, LF.617, LF.621, LF.624: prompt conflicts and stale facts removed.
  - LF.618, LF.619, LF.623: steering reaches every model call, is safe for concurrent notes, and has an audience.
- **Operations:**
  - LF.595: a hung orphan sweep no longer stops recovery.
  - LF.596: LM Studio is asked for `/props` once, then read through its own model list.
  - `loop.sh ship-live`: one checked deploy step.
  - `loop.sh impact`: changes measured by family, with one run after a change treated as a watch.

**Live:** L fullstack-bookmarks-py 4 (:8888) and L web-todo 3 (:1234), both fully on LF.637.

**Update 2026-11-05 21:50 JST.** Phase: learning runs (named `L <family> n`). Verified fixes are deployed into live runs at once; the release candidate is frozen and counted only after a full audit cycle finds nothing to fix. Live version 3308f8c.

**Finished today (hidden tests):**

| Run | Score | Note |
| --- | --- | --- |
| L notes-api 1 (:8888) | 9/9 | one root error broke 17 criteria; one fix closed it |
| fullstack-bookmarks-py 1 (:1234) | 6/8, false acceptance | the page left Save disabled after a save, so a second bookmark could never be saved; fixed by LF.599 |
| Earlier today | full | notes-api-hono, notes-api x3, web-todo x2, tasks-api x3 |

**Deployed this evening:**

- LF.591: a fixer's memory leads with the code (verified: 81k characters, was 162k).
- LF.592: a whole-page lookup of a per-record control is caught from the test's text.
- LF.593: `loop.sh impact` compares each change's later runs with the same family's earlier ones; 52 of 200 ledger rows had been filed under the other port's family.
- LF.594 and LF.598: agent memory leaves out scratch files, packaging output and harness bookkeeping.
- LF.595: an orphan-sweep pass that hangs no longer stops recovery; Redis calls have timeouts.
- LF.596: a server without `/props` (LM Studio) is asked once, then read through its own model list.
- LF.597: suite writers are told the starting skeleton is not theirs to finish (refused product writes: 0 in the next run, was 4 to 48).
- LF.599: a suite adds two records in a row from one page.
- LF.600: Python service stacks get the interface-contract probes, which until now ran only through Playwright.
- LF.601: a specification part cites no criterion id it cannot see.
- LF.602: a harness scratch file is not a stage's to delete (67 tries over 30 runs).

**Impact since LF.580 (corrected families):** fix rate x1.67 and wall time x0.75, with no hidden test lost until fullstack 1. On watch: defects left open x1.3, and output tokens x1.44 after LF.583/584.

**Live:** L tasks-api 1 (:8888) and L fullstack-bookmarks-py 2 (:1234).

*The older narrative below is kept as history.*

Work resumed at 2026-11-02 11:19 JST after the owner's model trial; the two held runs are running again, no fix is being built, and everything built is deployed (2026-11-03 10:48 with LF.553-555 at the owner's request (keys per endpoint, Anthropic path, run name on Home), then 11:59 with LF.556 (a pytest suite counting a list other tests write to was not caught, and cost a run over 30 minutes), the clean count restarting for the eighth time; notes-api 2a then scored 9/9 at 12:30 (mixed, so not counted), web-todo 1b 10/10 (mixed); the fullstack-bookmarks-py recheck failed at its suite at 14:11 (a Playwright report form, LF.557 deployed 14:19); rerun 2b and web-todo 1c started 14:19; LF.558 deployed into both at 15:08 (the testing role could not run pip, so the rerun's setup could not be proven), the clean count restarting again; LF.559 at 15:28; fullstack-bookmarks-py 2b then scored 3/8, a false acceptance: a finding raised in the suite review was dropped when the suite locked at its round cap (LF.560 deployed 16:24); owner hands off from 16:30; LF.561 (the start verdict reaches the snapshot, the fixes, the best attempt and the release; first deep-review item) and LF.562 (an empty suite is told where its commands run) deployed 17:42 into fullstack-bookmarks-py 2c and web-todo 1c; LF.563 at 18:43; fullstack-bookmarks-py 2c then scored 8/8, so every family has scored full today, and release candidate 1 was frozen at bf23015 at 18:55, first run notes-api-hono, 9/9 at 19:44 (the first counted result; mutation 0.833), then notes-api 1 9/9 at 20:40; LF.564 deployed 20:44 (a run pinned to a local server is served locally even when the settings name a hosted provider), so release candidate 2 restarts on 5eb1e083 from 20:46 with tasks-api 1, and web-todo 1 on :1234 from 22:57; tasks-api 1 scored 10/10 at 23:23 (first RC2 count), then fullstack-bookmarks-py 1 from 23:32; LF.565 to LF.567 deployed 00:13 on 11-04 (a forked worker reads its own settings, after the owner's run made one paid Anthropic call; pins take their server's saved limits), so release candidate 3 counts from f33ea83; web-todo 1 (mixed) scored 10/10 at 01:10 and RC3 web-todo 1 scored 10/10 at 02:53 (the first counted RC3 result); fullstack-bookmarks-py 1 (mixed) scored 8/8; RC3 notes-api-hono 1 scored 9/9 and web-todo 2 10/10 at 04:04 (RC3 3 of 3 full so far: web-todo 2/3, notes-api-hono 1/3); notes-api 1 and web-todo 3 started at 04:07; notes-api 1 scored 9/9 at 04:48 (RC3 4 of 4 full), then tasks-api 1 from 04:55; web-todo 3 scored 9/10 at 05:52, a false acceptance (no test completed an item while the Active filter showed it; the prompt-rule experiment for this did not help) - first RC3 failure, Fix batch priority 1; notes-api-hono 2 started on :1234 at 05:57; tasks-api 1 scored 10/10 at 06:02 (RC3 5 clean, 1 failed); fullstack-bookmarks-py 1 started at 06:06; notes-api-hono 2 scored 9/9 at 07:00 on :1234 (RC3 6 clean, 1 failed); notes-api 2 started at 07:05; fullstack-bookmarks-py 1 scored 8/8 at 09:55 (RC3 7 clean, 1 failed); tasks-api 2 started at 09:59; the owner asked that :1234 take no new runs after notes-api 2; LF.568-574 deployed into both by 11:02 on 11-04 (LF.573: a mutation put back within the same second left a compiled copy of the change running, the cause of notes-api 2's fall from 17/17 to 3/17; LF.574: every suite measurement kept and loop.sh deep-audit); the host restarted at 11:08; RC3 notes-api 2 (mixed) scored 9/9 at 11:56 on :1234; tasks-api 2 waits on :8888, whose model server aborts with a GPU (ROCm) error on its large request since the restart; LF.575 (loop.sh finds its containers by service after the restart left them renamed); :8888 down from 12:35 (its model server aborts at start); LF.576 (a lock note the release measurement refutes is not shipped, backlog B16) deployed with LF.575 at 13:10 as 9ba08ba; the owner fixed :8888 by 13:50; RC3 tasks-api 2 (mixed) scored 10/10 at 13:49; LF.577 (the pressure card's overall speed counted pauses and restarts, because a request that ended in an error stayed open; 7.8 tokens/s shown, 33.4 real) deployed 14:00 as ee48b84, from which release candidate 4 counts on :8888; RC4 notes-api-hono 1 started 14:01 and scored 9/9 at 15:01 (the first RC4 count; mutation 0.667); RC4 web-todo 1 started 15:09 (:8888) and RC4 notes-api 1 at 16:22 (:1234, the owner opened it again); web-todo 1's fixers spent about an hour on a filtering test that gave a locator hasText: '^B$' as a string, which matches those characters and never an item, so LF.578 (a pattern written as text goes back to the suite) was deployed into both at 16:46 as 0751b4f, both runs now mixed, and the clean count restarts on 0751b4f as release candidate 5; LF.578 then fired in web-todo 1 at 17:02 and the suite writer corrected all six locators; RC4 notes-api 1 (mixed) scored 8/9 at 17:24, a false acceptance: the suite tested the empty-title refusal on create only and the product accepts an update with an empty title - Fix batch priority 1 is a probe that empties each field the specification refuses empty on every write route; RC4 web-todo 1 (mixed) scored 10/10 at 17:55; RC5 tasks-api 1 (:1234) from 17:28 scored 10/10 at 18:15 in 48 min (the first RC5 count), fullstack-bookmarks-py 1 (:8888) from 18:00, notes-api-hono 1 (:1234) from 18:17; LF.579 (at a green round, each field the criteria refuse empty is sent empty to every write of the contract, and a write that accepts it is a defect) deployed into both at 18:47 as a0473c4, so the clean count restarts on a0473c4 as release candidate 6; RC5 notes-api-hono 1 (mixed) scored 9/9 at 19:20; RC6 notes-api 1 (:1234) started 19:28, the first run fully on a0473c4; RC5 fullstack-bookmarks-py 1 (mixed) scored 8/8 at about 20:00; the owner asked at 20:05 for no new runs on :8888, so new runs go on :1234 only; the Home, Settings, Admin and Runs screens were redesigned at the owner's request and deployed app-only at 19:48 and 20:05, which by the owner's rule does not reset the count; RC6 notes-api 1 scored 9/9 at 20:40, the first RC6 count (the family of the afternoon's false acceptance, now refusing the empty title on update as well); RC6 notes-api-hono 1 (:1234) from 20:46, paused overnight and resumed 09:45 on 11-05 after a host restart, scored 9/9 at 09:52 (RC6 2 of 2 full); the owner opened both ports again at 09:44, and RC6 tasks-api 1 (:8888) started 09:45 and web-todo 1 (:1234) 09:57; LF.580 (unit tests drafted after the code they test and shown it - the per-role audit found 25 of 31 unit-test fixes left open because tests were drafted before the code) deployed into both at 10:50 as 52cfcc5, so the clean count restarts as release candidate 7; owner rule 11-05: bug fixes and quality changes always on, only non-quality improvements behind switches, in meaningful groups; LF.581 (a 500 the service never logged is named to the fixer) deployed 10:57; RC6 web-todo 1 scored 10/10 at 11:08 and tasks-api 1 10/10 at 11:41 (both mixed); LF.582 deployed 11:55 as 543519f: 12 quality switches built in, the 13 unmeasured verification checks on as one measured batch, five grouped as Context and cost and Efficiency, the bundles kept as tiers - the clean count restarts as release candidate 8, first run fullstack-bookmarks-py 1 (:8888) from 11:56; the per-role audit then gave LF.583 (a test too weak to lock goes back once) and LF.584 (drafts capped; a looping draft redrafted), deployed 13:26; RC8 fullstack-bookmarks-py 1 failed at 14:05 on its own suite setup while its product scored 8/8, because no pack fitted a FastAPI service with a plain page; LF.585 (that pack) and LF.586 (chosen when the selector leaves the page field empty) deployed 14:20 and 14:33, and verified live: no stack setup, the suite locked in about 22 minutes instead of about 80; RC9 tasks-api 1 scored 10/10 at 15:41 (mixed); release candidate 11 counts from f412ca9, fullstack-bookmarks-py 1 (:1234) from 14:34 and tasks-api 1 (:8888) from 15:47; web-todo 1c (mixed) scored 9/10, a false acceptance from a criterion deferred after a suite repair that got worse; notes-api-hono 1c scored 9/9 on the version before; LF.552: a derived pack kept the page checks silent and cost a hidden test; LF.548 fixed every run since the 01:33 model settings change failing at its first stage; earlier: LF.537-546; the clean release candidate count starts on this version; LF.531: lessons rest on recorded facts, 8 false ones removed; LF.532: a missing suite report says where it was looked for; LF.533: a suite may list several test runners; LF.534: browser suites with no pack get the page checks; LF.535: a label lookup that also matches a longer name goes back to QA; LF.517 and LF.518 are now on for the rechecks JST).

| Item | State |
| --- | --- |
| run-fd0630c7, notes-api-hono sentinel on :8888, finished 9/9 | started 09:10, launch sweep |
| run-304c1913, fullstack-bookmarks-py recheck on :1234, finished 8/8 at 15:44 after rewind | started 09:38, launch sweep |
| Build agents (one running: launch fix batch 1) | none running |
| Machine | no restart since 2026-10-31 09:47 JST; restart recorder running |
| Branch | harness-hardening-session, pushed |

## Live and switched on

These are fixes and features with no switch, all in the deployed image. Of the first 21 rows, 2 have no flip test, 2 have only partial proof, and 1 cannot be proved by design; each says so.

| Rows | What it does | Proof it fails on the old code | Seen live |
| --- | --- | --- | --- |
| LF.447-457, 470-473 | Fixes from earlier runs: stack guidance, known-error tables, the QA repair rule, the deep readiness check, the ship step counting errors | recorded at the time; I did not recheck them today | across the earlier runs |
| LF.474-476 | A model pin per run, its toggle button and a run name | tested | every run since 10-31 00:47 JST |
| LF.477 | Tests no longer send real requests to the live model | tested | suite no longer crashes workers on that |
| LF.478 | A fix reads the files its defect's own words name | failing test | not singled out |
| LF.480 | The stored-suite dry run can signal no other process (it ended your login session twice) | none, on purpose: running it on the old code would repeat the outage | the two outages are the evidence |
| LF.490 | A response name follows its last assignment, so a helper's answer is not called a fixture response | yes | found on run-0349d8e9; not seen since |
| LF.491 | A service that stops by itself says why, and a dispute does not blame the test for it | yes | run-416d1bbb, report text in the suite output |
| LF.492 | A content-type check is judged on the answer it reads, not on any delete in the test | yes | not seen since |
| LF.493 | That stopped-service report reaches the fixer | yes | run-416d1bbb |
| LF.495 | A folder name in a path no longer merges two defects (the cause of one false acceptance) | yes | not hit since |
| LF.496 | A test reading a kept file's text is found, following variables | yes; read-only replay of 31 stored suites gave 2 findings, both right | probably run-0349d8e9, not confirmed |
| LF.498 | The stored-suite dry-run test runs only when asked for | none (the fix is a skip) | n/a |
| LF.501 | The ruling step uses the deployment's own model when none is named | yes | ran on every run since |
| LF.502 | The design stages are told what the setup decides (runner, start command, kept files) | yes | open design findings since then are about the product, not the harness's files; design time is not shorter |
| LF.503 | `loop.sh effects` names a switch that was on and never acted | partial: 2 of its tests failed only on a missing name | not yet |
| LF.504 | The ruling call is told the setup and to quote the specification | yes | not singled out |
| LF.505 | Two tests no longer scan the whole working tree (the full suite went from 5 minutes to 100 seconds) | none (the fix is the test) | every suite since |
| LF.506 | A test asserting an exact count on a shared list is found | yes, one behaviour test; read-only replay: 3 findings, 1 real fault, 2 passing by order | not yet |
| LF.507 | A dispute's ruling needs a quote the standard really holds | partial: 2 of 3 tests failed only on a missing argument | not yet |
| LF.508 | A quote with its section's name before it still counts as a quote | yes | not singled out |
| LF.509 | A bodiless write refused with either refusal is unchecked at release, not failed | yes | not yet |
| LF.510 | A delete asserted to answer with an error is not the 204 in the content-type check (third false finding from that check) | yes | found on run-aa67722c; deployed 18:17, not yet seen working |
| LF.511 | A run pinned to a server is judged by its own model's sight, not the global server's (a launch blocker for browser families on :8888) | yes | found on run-92f8ee23; deployed 20:33, checking on that run |
| LF.512-516 | Launch batch 1: a helper that opens the page counts; the production build is run; a product that will not start says why; ready probes the run's server; a pattern finding reopens a locked suite only on a failing test | yes | deployed 11-02 03:56, not yet seen working |
| LF.519 | A setup may declare its unit tests beside the code, as a pack does | yes; 2 of the tests were not run on the old code | deployed 11-02 03:56, not yet seen working |
| LF.517, LF.518 | Built, deployed and off: BRIEF\_OVER\_SPEC\_ADDITIONS, TESTS\_OF\_ACTIONS\_WITHIN\_A\_VIEW | wiring only; effect on a model unmeasured | arm them on the rechecks of wordstats-cli and web-todo |
| LF.520 | A product seeded at the workspace root moves into the pinned folder; a seed with code skips the setup stage. It comes back nested, and with no manifest there is no unit gate | yes; git-clone seeds not tested | deployed 11-02 05:07, being checked on run-b8eb5351 |
| LF.521 | The verdict separates evidence of failure from notes. Over 137 stored runs: 7 of 18 low-scoring runs still read deliverable (3 newly) and 70 of 119 full-mark runs read not deliverable. Better, still weak | yes, 22 of 23 fail on the old code; no real run yet | deployed 11-02 05:22, first real test on the two live rechecks |
| LF.522 | A suite whose every test fails with one message from its own helper goes back to QA, not to fixers | yes, 9 of 26 fail on the old code | deployed 11-02 08:11; run-b8eb5351 rewound to its test round to see it fire |
| LF.523-529 | Launch batch 3: failing unit tests ship only if an escalation accepted them; test tools on no-dependency briefs; sharper suite finding; leftover files removed; dashboards split gaps from notes; safe rewind; bad key no longer crashes ready | yes; install path untried in the image; dashboards not seen in a browser | deployed 11-02 09:37, not yet seen working |
| LF.530 | With no pack, the harness appends the commands it knows to the README; a handoff hold says so instead of "failing criteria"; a curl-only block no longer counts as how to run | yes, 9 of 11 fail on the old code | deployed 11-02 09:48, being checked on run-304c1913 |

## Built but switched off

Eighteen switches are built, tested and off in the deployed image. None of the sixteen newer ones has acted in a real run; the two older ones, `BATCH_ACCEPTANCE_AUTHOR` and `OBSERVATION_FOLDING`, I have not rechecked.

| Switch | Rows | What it does | Why it is off | To turn it on |
| --- | --- | --- | --- | --- |
| `CONTRACT_LINE_COVERAGE` | LF.484 | Names contract routes no test calls to QA on a first writing | lenient text search, never run live | a run measuring lines with no test at lock |
| `CONTRACT_PROBE_AT_LOCK` | LF.485 | Probes the product once the suite locks, and raises any 5xx | never run live | same |
| `CONTRACT_UNREAD_LINES_AT_REVIEW` | LF.486 | Raises unreadable contract lines at the architect's review | never run live | same |
| `CONTRACT_NON_NUMERIC_IDS` | LF.487 | Reads `AC-health GET /health` style lines | never run live | same |
| `CONTRACT_PROBE_WITH_A_RECORD` | LF.488 | At release, makes a record through the contract's POST and probes `{id}` routes | the compiled Playwright check has never been executed | a live run with it on; release reports show 4 to 21 unchecked lines per run |
| `CONTRACT_PROBE_WITH_A_BAD_BODY` | LF.500 | Sends unparsable JSON to write routes and raises any 5xx | compiled probe never executed; cannot reach routes behind sign-in | a live run with it on |
| `NAMING_FINDING_BEFORE_DEFERRAL` | LF.489 | Sends a criterion that ships deferred only for want of a test name back to QA once | the route back through the full graph was not run | a live run with it on |
| `SPEC_DRY_RUN` | LF.479 | Runs each browser-test file with stand-ins and turns errors from the test's own code into findings | runs model-written code on the host | a sandbox, then your yes |
| `ORDER_PROBE` | LF.481 | At the first green round, runs each test file alone, last first, and records failures | records only | a run showing order dependence |
| `IDS_READ_WITHOUT_A_CREATE` | LF.482 | Flags a test reading a literal id nothing created | 0 findings on the stored suites | a stored case that needs it |
| `STABLE_STAGE_PREFIX` | LF.458-469 | Keeps the start of each request identical for cache reuse | the servers report no cache data, so it cannot be judged | a server that reports cache use |
| `NAMED_TEST_REWRITE` | LF.458-469 | Rewrites only the named tests in a QA repair | group not yet measured | its group measured |
| `TESTS_ONLY_WRITES`, `MUTANT_CHECK_IN_THE_FIX_STAGE`, `MUTATION_TEST_RETENTION`, `EQUIVALENT_MUTANTS_REMEMBERED` | LF.458-469 | Tests-only writes beside a green suite, and mutation findings handled in the fix stage | group not yet measured | the tests-and-mutation group measured |
| `OBSERVATION_FOLDING`, `BATCH_ACCEPTANCE_AUTHOR` | older | not rechecked | not rechecked | not rechecked |

## Switch groups being measured

Four groups are on as trials. None has yet shown an effect on the hidden score, because every run on both benchmarks scores full marks; time, reverted fixes and known gaps have to carry the comparison, and my own deploys have clouded those.

| Group | Switches | On since | Baseline | Seen so far | Decision rule |
| --- | --- | --- | --- | --- | --- |
| Fix loop | `AGENT_LOOP_FIX_LIMITS`, `SURRENDER_TO_REWRITE`, `KEPT_FIX_CANDIDATES`, `CO_DEFECT_FAILURES_IN_REWRITES`, `REPEATED_REWRITE_PROMPT_STOP` | 10-31 00:47 JST | run-c82c85d9 (5.3 h) and run-21519414 (93 min), both off, both full marks | 20 finished runs on: hidden score full except one 8/9, caused by a different bug (LF.495); times from 40 min to 4 h | ablate one switch at a time only if the group does not help |
| Targeted repair and structured dispute | `TARGETED_SUITE_REPAIR`, `STRUCTURED_DISPUTE_VERDICT` | 10-29 | 54 earlier re-locks and 2 wrong prose verdicts | run-5acea1e1: a one-test repair re-locked in about 3 minutes without a full review | watch mutation score for a weaker suite |
| Contradiction | `SETTLE_SPEC_CONTRADICTIONS`, `UNIT_TESTS_YIELD_TO_THE_LOCKED_SUITE` | 11-01 09:49 JST (rulings ran from 10:57) | runs before 09:49 | 5 rulings accepted over 8 runs; the same PUT contradiction settled the same way on two runs, none changed an outcome; the yield rule has not fired | park the group if the next runs show no outcome changed |
| QA hand-back | `QA_SAYS_THE_PRODUCT_IS_AT_FAULT` | 11-01 14:00 JST | runs before 14:00 | has not fired; no run since needed it | park if it never fires or fires wrongly |

## Results so far

Twenty-two finished runs since 10-31, all with full hidden marks except one (8/9, from the defect-merge bug LF.495). Mutation counts the deliberate product changes the locked suite noticed, out of 12 unless shown as a fraction (some runs tried 8 or 9); in brackets, with the unit tests too.

| Run | Benchmark | Hidden | Time | Mutation | Note |
| --- | --- | --- | --- | --- | --- |
| run-c82c85d9 | tasks-api | 10/10 | 5.3 h | 0.75 | fix loop off |
| run-21519414 | notes-api-hono | 9/9 | 93 min | 3 (3) | fix loop off |
| run-ec3e81ab | tasks-api | 10/10 | not recorded | 6/6 | one defect only |
| run-dfcaf697 | notes-api-hono | 8/9 | not recorded | not recorded | false acceptance, cause LF.495 |
| run-416d1bbb | notes-api-hono | 9/9 | 3.5 h | 7 (10) | 2 h lost to a wrong dispute |
| run-0349d8e9 | notes-api-hono | 9/9 | 4 h | 8 (10) | a spec contradiction became a standoff |
| run-27b8cc24 | tasks-api | 10/10 | 70 min | 7/8 (8/8) | quality 6/7 |
| run-7829e37c | notes-api-hono | 9/9 | 41 min | 10 (11) | first with the false-finding fixes |
| run-4027a954 | tasks-api | 10/10 | 84 min | 3 (10) | weak locked suite |
| run-767b4f54 | notes-api-hono | 9/9 | 40 min | 10 (12) |  |
| run-617f1671 | notes-api-hono | 9/9 | 64 min | 9 (10) | rulings inert (LF.501) |
| run-7904116f | tasks-api | 10/10 | 70 min | 7/9 (8/9) |  |
| run-bce0db0a | notes-api-hono | 9/9 | 2 h 55 | 8 (8) | tests no fix could satisfy |
| run-3095f3a7 | tasks-api | 10/10 | 70 min | 7 (10) |  |
| run-2363aa37 | tasks-api | 10/10 | 2 h 8 | 8 (9) | first with LF.502 |
| run-4958939d | notes-api-hono | 9/9 | 41 min | 8 (11) | 4 known gaps |
| run-5acea1e1 | notes-api-hono | 9/9 | 76 min | 7 (10) | first real rulings |
| run-4529981d | tasks-api | 10/10 | 1 h 44 | 10 (12) | quality 7/7 |
| run-ff5e0c66 | notes-api-hono | 9/9 | 50 min | 11 (11) | 3 known gaps, no failed calls |
| run-aa67722c | notes-api-hono | 9/9 | 1 h | 6 (9) | a false finding cost about 10 min (LF.510) |
| run-be332286 | notes-api-hono | 9/9 | 45 min | 10 (12) | first with LF.510; no failed calls |
| run-fa8e80d7 | tasks-api | 10/10 | 2 h 55 | 6 (8) | quality 7/7; time in planning and review; AC-17 shipped deferred |
| run-17983a18 | wordstats-cli | 6/8 | 95 min | 4/5 (4/5) | false acceptance: the specification added a casing rule the suite then locked |
| run-92f8ee23 | fullstack-bookmarks | 8/8 | 2 h | 11 (12) | found LF.511; up from 3/8 on 10-26 |
| run-7a4a8d63 | fullstack-bookmarks-py | 8/8 | 2 h 50 | 8 (8) | no stack pack, so no packaged way to run it; AC-14 deferred |
| run-bfc8c162 | web-todo | 9/10 | 4 h | 8 (10) | false acceptance: a task completed while filtered stays listed; found LF.512 |
| run-101a87aa | web-todo-react | 1/10 | 2 h | not recorded | false acceptance: production build fails; nothing runs it |
| run-452d9723 | tasks-api-change | 0/15 | 2 h 35 | 10 (12) | marked non-deliverable, as all 9 sweep runs were; product rebuilt beside the seed; found LF.519, LF.520 |
| run-55de5eb7 | textkit-lib | 8/8 | 49 min | 6 (8) | full marks, yet marked non-deliverable: 2 locked tests reclassified under dispute, design finding left to an escalation |
| run-67b0fb57 | notes-api | 9/9 | 56 min | 7 (12) | full marks, yet marked non-deliverable; gaps include findings already settled by decisions |
| run-91b34de5 | notes-api-js | 9/9 | 55 min | 7 (12) | full marks, yet marked non-deliverable; last run of the sweep |
| run-d1d5eed8 | web-todo-react recheck | 10/10 | 48 min | 11 (12) | up from 1/10; the build check fired and the fix held; correctly read as deliverable |
| run-a5a5854f | wordstats-cli recheck | 8/8 | 43 min | 4 (4) | first full marks for this family; not credited to LF.517: the specification still has the first-occurrence rule. Read as deliverable |
| run-b6e4870e | web-todo recheck | 10/10 | 51 min | 8 (12) | up from 9/10 in 4 h; read as deliverable. This family has varied before, so not credited to LF.518 |
| run-b8eb5351 | tasks-api-change recheck | 15/15 | 4 h 25, over 1 h of it paused | 10 (12) | up from 0/15; LF.520 and LF.522 worked in a real run; non-deliverable only for a one-line README |
| run-fd0630c7 | notes-api-hono sentinel | 9/9 | 87 min active, 2 h 51 with the pause | 8 (12) | read as deliverable; the attempt to add transactions broke tests and was rolled back, so that finding ships as a note; one mutant closed as equivalent was later caught by a real test |
| run-304c1913 | fullstack-bookmarks-py recheck | 3/8 | 92 min active, 2 h 56 with pause and rewinds | 6 (12) | own suite 27/27; bookmarks are not real list items, and the suite only looked for a CSS class. Read non-deliverable, but for a setup gap, not this fault |
| run-304c1913 (rewound) | fullstack-bookmarks-py recheck | 8/8 | 142 min active, 4 h 34 with pause and rewinds | 4 (12) | up from 3/8 the same day; LF.533-535 got it there. Read non-deliverable for a test id taken as a file, fixed by LF.536; weakest mutation score so far |
| run-eba03186 | wordstats-cli, RC 1 of 3 | 8/8 | 30 min | 2 (2) | read non-deliverable: one of its own unit tests ships failing; no review read the code, since the sprint was accepted on its locked suite |
| run-6e190dfa | web-todo, RC 1 of 3 | full marks | 71 min | 7 (12) | read as deliverable; one fix reverted for breaking 13 tests; half of its reads were repeats |
| run-0d817a9a | fullstack-bookmarks-py, RC 1 | 0/8, unscored | about 2 h | not measured | own suite 33/33; start.sh could not start, so no hidden test ran. Read non-deliverable, but for an unrelated setup gap. LF.537 fixes the blind spot and restarts the release candidate count |
| run-4e57c399 | web-todo-react, mixed version | 10/10 | about 3 h 25 | not measured | read non-deliverable: its own suite ended 14 of 16, AC-1 and AC-8 deferred after about 2 h of fixes on a hidden description. Not counted |
| run-9bc85e07 | fullstack-bookmarks, mixed version | 8/8 | about 4 h 35 | not read | own suite 22/23, one test failing on delete. Not counted; slow because a re-plan dropped the page work order (LF.539) |
| run-da433831 | textkit-lib, mixed version | 0/8 | 1 h | not read | own suite 22/23 but import textkit finds nothing a customer can use: the package moved to the project top and a fix deleted the real one. Read non-deliverable for another reason; a fix also added a default limit to suit a wrong test |
| run-f0bf8a48 | textkit-lib, clean on 3638bc8 | 8/8 | 67 min | 2 (4) | read as deliverable; up from 0/8 the same evening. Two wrong tests went to QA after the dispute ruling got through (LF.543). Evidence, not counted: LF.545-546 were deployed after it |
| run-eb5cffb8 | fullstack-bookmarks-py, mixed (LF.545 deployed into it) | 0/8, hidden could not start it | 85 min | 8 (12) | own suite 38/38; LF.545 got start.sh fixed in one attempt, but it starts only from a folder named bookmarks, so the scorer's copy could not import it. Read non-deliverable for a setup gap, not this |
| run-a69ff175 | notes-api-hono, clean 1 of 3 on be1fc06 | 9/9 | 72 min | 11 (12) | first counted run of the candidate; own suite 13/13; read non-deliverable for a release probe of PUT /notes/:id, under investigation as a probe fault |
| run-8ac0e9c0 | tasks-api, mixed (LF.549-551 deployed into it) | 10/10 | 130 min active, 2 h 25 wall | 6 (12) | read non-deliverable: 3 unit tests ship failing on 422 versus 401 for a missing Authorization header, the contradiction a rejected design ruling left open (LF.550 now fixes the rejection); 3 fixes reverted, 8 defects left open. Evidence, not counted |
| run-7570da3a | fullstack-bookmarks-py 1c, mixed (rewound to setup after LF.549-551) | 7/8 | 130 min active, 4 h 17 wall | 2 (2) | own suite 22/22 on a product the setup stage built, no build sprint; the hidden filter-by-tag test timed out; read non-deliverable for a missing npm test script and no unit tests. Evidence, not counted |

## Not built yet

About 10 more items from the reviews and about 13 from the older backlog. Building them at one agent at a time runs to roughly 11-06; measuring the switch groups runs to roughly 11-10 to 11-14. These are estimates from this session's pace.

| Item | From | Note |
| --- | --- | --- |
| Find a repair that drops assertions it was not asked to | run-bce0db0a review | a repair removed type checks on list items and the re-lock let it pass |
| Repair or remove the unit tests that ship failing, and say which | several reviews | happened on several runs |
| Report a run's time by cause (tests, product, specification) | three reviews | also on the run page |
| A sprint whose tests already pass skips the reviews | run-3095f3a7 review | about 4 minutes |
| Check the file plan against the manifest | run-7829e37c review | the missing `tsx` |
| Release wording: "escalated to a person" on an unattended run; known gaps ranked by what a customer cares about | two reviews |  |
| A readiness probe that tolerates a busy server | audits | `ready` fails while :1234 is busy |
| Generate a two-user isolation test from the contract | run-27b8cc24 review | about a day |
| Stop the no-change edits the harness refuses (about 9% of calls) | run-4529981d review |  |
| Look into: the `PUT` contract report on run-767b4f54, the 18% of output lost to the length cap on run-2363aa37, the removed-name import defect | reviews | open questions, not yet investigated |
| Backlog B6, B10, B12, B16, B18 (report-name half), B21, B23 (ask-again step), B25 | STATE.md | route-handler type check, per-stage reasoning effort, plan role check, skeleton tests, defer a criterion after the second re-plan, drop stale review notes at release, a round budget for the mutation probe, scratch files committed in batches |
| Plan items 3 (remainder), 19 (measurement), 23 (ongoing), 24 (last) | deep-review plan |  |

## Waiting on you

Five decisions are yours, and nothing here is scheduled until you answer.

| Decision | What it unlocks | Since |
| --- | --- | --- |
| A sandbox for `SPEC_DRY_RUN`, then yes or no on turning it on | replaces text-pattern checks that have caused several false findings | 11-01 |
| Put a specification contradiction to the customer as one question with a suggested answer and a timeout | removes the contradiction standoffs without a model call | 11-01 |
| Hold a release back, or trigger one round of test writing, when the locked suite catches few deliberate product changes | the 3-of-12 case on run-4027a954 | 11-01 |
| Offer a held-back share of the customer's own acceptance tests, run only at release | a check customers cannot game | 11-01 |
| The Harness² ideas (contrastive fix candidates and others), item B22 | proposed to you on 10-28 | 10-28 |

Two more from the launch cycle: whether the gate above is the right bar, and which model customers will run on. All of this testing is on local Qwen, and a launch on a cloud model needs at least one full pass on it, which could use the cloud API you mentioned.

## Known problems and corrections

These are things I got wrong or have not resolved.

- **Your restarts.** The two session endings on 10-31 (11:11 and 14:51 JST) were my build agent's dry run sending a kill to every process you own (LF.480, fixed before merge). The 10-31 09:46 hard reset is unexplained; the load limits stay and a recorder watches for the next one.
- **Two pushes with a failing test** on 11-01 (about 08:35 and 11:21 JST). Nothing was deployed from either, both were fixed, and I now run the suite and the push as separate steps.
- **Reports I corrected:** I said no contradiction ruling had been accepted when one had (the run-2363aa37 review now says so); I wrote "measured on two runs" where I had measured one.
- **A repair can weaken a test beyond what was asked,** and nothing in the harness compares assertions before and after. It happened on run-bce0db0a.
- **`loop.sh ready` fails while :1234 is busy,** and has failed repeatedly today for that reason. It only matters when starting a run.
- **Weak proof** is listed in the Live table (LF.503, LF.507) and on the two rows with no flip test (LF.498, LF.505).
- **Plan rows needing an edit** in the improvement plan: LF.501 sits out of order, and the LF.508 row still says no ruling had been accepted.

## 2026-11-23 15:50 JST

- **Scored:** fullstack-bookmarks 6 (run-eebf5e67): hidden 8/8, quality 7/7, delivered with cuts (AC-4 deferred on a locked test that could not pass; AC-14), 114 min, mutation 0.50.
- **Deployed today:** LF.1227-LF.1234 (13:47, c3423c45: aggregate criteria, stuck lookups on the product's own error, Go/Maven registry names, build output skipped, missing-import refusal, builders and code reviews on written code hold that code, web tools on for every run); LF.1235 (14:57, own-record pick rule); LF.1236 (15:07, drafted files recorded).
- **Fired and helped:** LF.1230 (stopped a flood of build-output problems; verified by test only so far); LF.1231 (no case since deploy); LF.1232/1233 (did not fire on bookmarks 6: drafted files had no author, fixed by LF.1236); LF.1235 (deployed, did not move the dispute's ruling); web tools (no stuck fixer yet since deploy).
- **Building:** LF.1237, a deterministic own-record pick check handed to the dispute.
- **Live:** run-e625936e notes-api-rust 1 on :8888 (15:47); run-8f0be29e on :1234 (owner's).

## 2026-11-23 17:37 JST

- **Scored:** notes-api-rust 1 (run-e625936e): hidden 9/9, quality 8/8, delivered, 97 min, mutation 0.50.
- **Deployed since 15:50:** LF.1237 (15:55, own-record pick check), LF.1238 (16:29, `LONG_REASONING_BEFORE_A_READ` on, measured), LF.1239 (16:39/16:54, axum known causes), LF.1240 (17:10, borrow cause).
- **Fired and helped:** LF.1238 fired 4 times on run-8f0be29e: the acceptance author went from 13-28k reasoning tokens a read to under 4k and finished in 7 minutes; LF.1239's struct-import cause shown to two stages, that defect closed; web lookups fired 3 times on Rust, closed nothing on their own.
- **Live:** run-b6dce69e textkit-lib 8 on :8888 (17:35); run-8f0be29e on :1234 (owner's).
