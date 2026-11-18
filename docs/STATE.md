# State of the loop
The one file every session reads first (plan MF.6): what is live, what is off, the last three runs, the next
action. At most 150 lines and 16,000 characters, rewritten, never appended. Reference: `docs/HANDOVER.md` (rules,
accounts, commands), `docs/monitoring-handover.md` (mechanics, run log), `docs/improvement-plan.md` (every fix, LF
rows), `docs/measuring.md` (everything under measurement), `docs/owner-decisions.md`. The file this replaced, with
every narrative up to 11-17 01:30 JST, is `docs/archive/STATE-before-2026-11-17.md`.
<!-- state:generated -->
**As of:** 11-18 13:47 JST (written by `loop.sh state`). Harness 90e875d8 committed; 90e875d8 deployed.
**Live, and stopped in the last day:** run-1e04154a failed at failed; run-db139a37 failed at failed; run-760be6cb failed at failed; run-092a40cb failed at awaiting_approval:defect_fix_1_0; run-844673cd failed at failed; run-9f8188cb failed at failed
**Last scored:** run-1e04154a notes-api-rust 0/9 (failed, handoff 0.429; scored 11-18 13:47 JST); run-4886c02b notes-api-go 9/9 (completed, mixed, 47 active min, handoff 1.0; scored 11-18 13:45 JST); run-14e254a1 notes-api-java 9/9 (completed, mixed, 234 active min, handoff 1.0; scored 11-18 12:25 JST).
<!-- /state:generated -->

## Live now
| | |
|---|---|
| Phase | Launch review (`docs/reviews/launch-review-2026-11-16.md`, LR.1-65) built item by item; M36 measuring runs on both ports. Owner hands off 11-16 21:50 JST: all review items by the morning of 11-17. |
| Models | :8888 `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` (key); :1234 `qwen3.6-35b-a3b-mtp@iq4_nl` (no key). Both the owner's; both take runs (:1234 was held 18:45-21:52 JST on 11-17); each run pinned to its port (`PIN_MODEL=1`). Never load or change them. |
| Harness | af9aa70d deployed 11-17 11:55 JST: LF.995-1010 (owner 11-17: remaining launch items built in parallel behind switches, all ON, past runs the baseline). Host has Pyright 1.1.414. |
| Switches | 52 fixes built in (always on; only a host env var turns one off). 11 optional switches; one on - NEAR_GREEN_REPLANNED_ONCE, but off per run since 11-18 08:15 JST (`SWITCHES_OFF`): by its own rule (measuring.md M14) it should go off - Rust container 3 lost the hidden test of the criterion it left open - and the default change waits on the owner (it touches docker-compose.yml). Off: Context and cost (OBSERVATION_FOLDING, STABLE_STAGE_PREFIX, BATCH_ACCEPTANCE_AUTHOR, REASONING_KEPT_AFTER_AN_ANSWER), Efficiency (EQUIVALENT_MUTANTS_REMEMBERED, MUTANT_CHECK_IN_THE_FIX_STAGE, REVIEWS_WITHOUT_REASONING, HARNESS_FINDINGS_RECHECKED), Setup scope (SETUP_SCOPE_GUARD), Review gates (MILESTONE_EVIDENCE_GATE). Admin page: Controls. |
| Operations | Backups nightly to `data/backups` and `BACKUP_DIR` (external disk, 7 daily + 4 weekly), checked by `loop.sh backup --check`; finished runs older than `RETENTION_DAYS` (60) cleared nightly; both set in git-ignored `data/loop/ops.env`. Owner's Postgres port in git-ignored `docker-compose.override.yml`; `docker-compose.prod.yml` + `deploy/Caddyfile` for TLS. |
| Suites | `loop.sh suite` and `loop.sh suite-production` (every built-in fix on, as shipped) both green: 17,316 passed, 0 known failures. |

## Off until measured
The 10 optional switches above. Hosted-model runs (LR.44) only when the owner starts or instructs them.

## The last three runs
Generated above. Tonight's M36 runs (hidden, quality, verdict):
- notes-api-php 1 run-657c3113 (:8888): 9/9, 8/8, delivered, handoff 1.0; LF.986 found `GET /notes/not-a-number`
  answering 500 and it was fixed in the run.
- notes-api-csharp 2 run-a99ce5d1 (:1234): 9/9, 6/8 (a POST answer without `id`; writes at once lost),
  not_deliverable - rightly: its unit tests did not compile, now named by LF.979; handoff 1.0 after LF.988.
- notes-api-java 1 run-9c05c6e7 (:8888): 9/9, 7/8 (`GET /notes/abc` answers 500), delivered, handoff 1.0 after the
  scorer fix LF.985 (Rust and Java each lost a handoff point for a port they read).
- tasks-api 2 run-925391f7 (:1234): 10/10, 7/7, delivered (after the duplicate-task rewind); 13 fixes reverted for
  imports of modules the project lacked - Python writes were never checked as written (LF.980).
- notes-api-csharp 1 run-4db255e8 (:1234): stopped at its scaffold - `dotnet` refused, no toolchain pinned (LF.981);
  notes-api-csharp 2 run-a99ce5d1 started 03:14 on the fix.
- notes-api-rust 1 run-d8b0e95b (:8888, 52 min): 9/9, 8/8, not_deliverable - wrongly, for `package.json` having no
  `test` script (LF.978); its unit tests did not compile (an axum `TestClient` that does not exist) and no gap said so (LF.979).
- notes-api-go 1 run-ca45a144 (:8888): 9/9, 8/8, not_deliverable - 2 Go unit tests ship failing (right), and the same
  false `package.json` blocker (LF.978).
- textkit-lib 2 run-fdd127ff: 8/8, 7/7, delivered. fullstack-bookmarks 1 run-0933e611: 8/8, delivered.
- Earlier on 11-16: web-todo 10/10 delivered; notes-api-hono 9/9 8/8 delivered; notes-api-js 9/9 8/8 with cuts;
  web-todo-react 10/10 not_deliverable (663 lines against the brief's 500); fullstack-bookmarks-py 8/8 after LF.958;
  tasks-api 1 10/10 7/7 (6 h, LF.951/953/956); wordstats-cli 2 6/8 (the family's recurring --top loss, warned).
- Browser and change families had no quality set until LF.971; their runs from now on carry one.

## Morning report (11-18)
Container sweep: every language delivered 9/9 hidden at least once (Go, Java, Rust, C#, PHP, Ruby, tasks-api);
Java run 5 the first Java with every quality test. Rust is the open family: runs 1 and 4 failed 0/9 on `app()`
declared as a router still waiting for its state; LF.1064 now holds the declaration at every round. Fixes overnight:
LF.1036-1064 (scorer: LF.1037/1042/1043/1046/1053/1054). Owner decision pending: `NEAR_GREEN_REPLANNED_ONCE` off by
default (patch saved; off per run meanwhile). The 11-17 report is in git history.

## Next actions
1. LR.30 container-mode Java run 2, run-844673cd-1d2d-459c-aca9-7641567f9fc8 (:8888, 14:26-15:36): FAILED, hidden 0/9,
   quality 0/8, handoff 0.43 - its one sprint re-planned 3 times. Four harness fixes from it: LF.1017 (Maven warm-up),
   LF.1020 (a Java test mirrors its code's package), LF.1021 (Maven has the network while building in container mode),
   LF.1023 (the product is built without compiling its tests: a test naming a missing class stopped `start.sh`, so
   nothing reached a product whose code compiled). Run 1 (run-9f8188cb) failed at its scaffold (LF.1017).
   Java run 3, run-e53e1441-f6ed-4d89-aded-8c1cdb79e0bd (:8888, 16:12-17:50): hidden 9/9, quality 7/8, DELIVERED,
   handoff 1.0 - the first Java container run delivered. The quality loss is lost writes at once, which
   CONCURRENT_WRITE_PROBE had raised in the run (the fixers did not close it): the probe was right and cost no hidden test.
   Rust container run 1, run-760be6cb-36d5-45f2-98ea-9a67c2133de8 (:8888, 17:56-19:36): FAILED, hidden 0/9, quality 0/8,
   handoff 0.43. The specification fixed `build_router() -> Router<AppState>`, which `axum::serve` cannot serve, and
   eight fixes were reverted as "it broke the install" while nothing had built before any of them. Fixed: LF.1032 (no
   `axum::test`), LF.1033 (a defect's place on rustc's `-->` line), LF.1034 (no general-purpose subagent on any hosted
   provider), LF.1035 (a pack's design facts reach the design stages), LF.1036 (a fix is blamed for the install only
   when it worked where the fix started), LF.1037 (container-mode mutation scores were never recorded).
   Rust container run 2, run-c7a00abc-1f89-4d22-a153-2341b48c4641 (:8888, 19:54-21:32): hidden 9/9, quality 8/8,
   handoff 1.0, verdict not_deliverable (AC-18 deferred; one unit test file did not compile). From 0/9 in run 1:
   LF.1035 (the design gave a plain `Router`), LF.1036 (no fix reverted in four attempts, against 8), LF.1038-1041
   (the Rust pack's known compiler errors, each given its cause; the handler-order error closed once it was).
   LF.1042 (no check reads a toolchain's build output: its release checks and mutation probe read `target/doc`).
   Open, measured: the design gate's "says opposite things" findings are mostly false - 43 over the last 4 runs,
   7-12 in each ("no response body" on DELETE paired with every endpoint's body). Next: scope a denial to what it
   is about before calling two statements opposite.
2. LR.30 container-mode Go run 1, run-666e030f-1c7d-4830-bf58-b9594f31ac4a (:1234, 15:28-16:44): hidden 9/9, quality
   8/8, handoff 1.0, verdict not_deliverable (contract lines and design points left open). LF.1022, LF.1024-1025 from it.
   C# next on :1234: its pack failed `verify_packs` in container mode (LF.1027, the .NET image's uid) - a run started on it
   at 16:46 was cancelled at once; verify every pack in container mode before its first run.
   C# container run 1, run-092a40cb-21da-4853-b600-cfb137ce824b (:1234, 16:54): stopped when the owner took :1234
   (18:45 JST), left failed when the owner released the port at 21:52 (16 fixes later; C# reran fresh on :8888).
   C# container run 2, run-2a42b19c-205a-4bd5-812c-0028762cc920 (:8888, 21:46-23:12): hidden 9/9, quality 8/8,
   handoff 1.0, DELIVERED - the first C# container run delivered. Its attempt 1 failed on a fixer that wrote C# into
   `App.csproj` (LF.1045 now reverts a fix that leaves a manifest unreadable); the re-plan built it green. Mutation
   4/12 caught (LF.1046: the probe's copy failed on .NET's sockets). LF.1044 (one point per denial) deployed 22:11.
   PHP container run 1, run-e8e3120f-5d67-4b47-9037-e4745c898148 (:1234, 21:52-23:50): hidden 9/9, quality 8/8,
   handoff 1.0, DELIVERED; mutation 7/12. One middleware fix (JSON parsing on every request) closed 7 defects.
   Ruby container run 1, run-c7b0d7ec-4406-41fe-af2f-74259ee63996 (:8888, 23:19-00:52): hidden 9/9, quality 7/8
   (16 writes at once kept as one id: the routes' helper still made a store per request), handoff 0.875,
   not_deliverable. LF.1047 (rackup kept), LF.1048 (Sinatra lost-writes cause), LF.1050 (probe at 16, as the hidden
   test; the cause names the helper).
   Java container run 4, run-b770f08f-2b04-42c9-9172-1c330717b0d9 (:1234, 23:56-01:40): hidden 9/9, quality 7/8,
   handoff 1.0, delivered_with_cuts. Lost writes now pass (LF.1030 helped Java). Lost `GET /notes/abc` -> 500 (a
   catch-all exception handler; Java run 1 lost the same test): LF.1052 asks the 5xx probe at near-green rounds too.
   LF.1049 (MockBean cause) and LF.1051 (the JVM's temp folder off the noexec /tmp: SQLite could not load) helped.
   :8888's model is not loaded since about 00:55 (the owner's); nothing started there.
   Ruby container run 2, run-6a9c0fb9-4d07-42e0-9bf1-59aa5d5f91f6 (:1234, 02:01-03:33): hidden 9/9, quality 8/8,
   handoff 0.875, delivered (first scored 0/9: the scorer's Ruby ignored gems built in the sandbox image - LF.1053).
   Every language in the container sweep now passes 9/9 hidden (handoff 1.0 after LF.1054).
   tasks-api container 1, run-1cef3eae-17ed-4e38-a8ae-8e97812fe352 (:1234, 03:39-05:50): hidden 10/10, quality 7/7,
   handoff 1.0, verdict not_deliverable (a locked test reclassified under dispute; mutation 0.1 - a weak suite).
   Rust container run 3, run-1badaa8f-b4cc-425a-a27a-aa0146b7fbbd (:1234, 06:00-07:22): hidden 8/9, quality 6/8,
   handoff 1.0, not_deliverable; mutation 12/12. The design held (LF.1035/1039: `app() -> Router`, state applied
   inside). Lost: an update (the near-green criterion left at acceptance), a blank title kept, a long body refused.
   Built from it: LF.1055 (a fixed compiler finding no longer kept open by another error in its file), LF.1056
   (`oneshot` takes the router by value). :8888's model was not loaded 00:55-08:30; the owner made it available again.
   Rust container run 4, run-db139a37-8100-4378-acb8-8bf1f16197d4 (:8888, 08:32-11:13): FAILED 0/9, re-planned 3
   times; the product never started - `app()` declared `-> Router<AppState>` in every attempt, fixers editing
   `main.rs` where the error is reported. Built from it: LF.1057, LF.1060, LF.1061, LF.1063 (Rust known errors).
   Java container run 5, run-14e254a1-3dd0-454f-8597-3165efd5452b (:1234, 08:15-12:20): hidden 9/9, quality 8/8,
   handoff 1.0, DELIVERED - the first Java run with every quality test: lost writes and the non-numeric id 500
   both pass (LF.1030, LF.1052); LF.1049/1051/1059/1062 unblocked it. About an hour lost writing its suite
   against the unbuilt product (LF.1058 since).
   Go container run 2, run-4886c02b-bdaf-49c8-92a6-0d41364b8ed4 (:1234, 12:29-13:40): hidden 9/9, quality 8/8,
   handoff 1.0, DELIVERED. Rust container run 5, run-1e04154a-6c23-4b3d-8b7f-85c17fc18441 (:8888, 11:24-13:42): FAILED
   0/9 - the signature held (`-> Router`), but handlers took `Extension<AppState>` while `app()` used `.with_state`:
   every route answered 500 "Missing request extension", a body the Playwright failures never showed the fixers.
   LF.1066 grouped the 500s into one defect; next: that defect quotes one failing response's body.
   Live: C# container run 3 (:1234, 13:49); PHP container run 2 (:8888) - near-green switch off per run.
3. The language sweep then has one run per language; next, a second run of the families that lost quality tests.
   LF.987 (records only) waits for the next deploy. shortlinks-api is held out (Measure runs only, `MEASURE=1`).
3. LR.53 rest (a suite repair that leaves the suite near green goes back to the round: M14's open part), LR.52 rest, then a whole run in container mode (LR.30).
4. When no fix is pending for a full audit cycle: freeze and start the LR.20 batch.

## Rules that are never optional
`AGENTS.md`. In short: the model is the owner's (`loop.sh ready` must say ALL READY); fixes are stack-agnostic
(packs, `plugins/seed.py`, per-language tables); every fix has a test proven failing on the old code; both suites
green; commit and push after every change (`git push main harness-hardening-session`); no secrets printed; the
operator account only (`docs/HANDOVER.md` §3); times in JST.
