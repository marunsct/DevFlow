# State of the loop
The one file every session reads first (plan MF.6): what is live, what is off, the last three runs, the next
action. At most 150 lines and 16,000 characters, rewritten, never appended. Reference: `docs/HANDOVER.md` (rules,
accounts, commands), `docs/monitoring-handover.md` (mechanics, run log), `docs/improvement-plan.md` (every fix, LF
rows), `docs/measuring.md` (everything under measurement), `docs/owner-decisions.md`. The file this replaced, with
every narrative up to 11-17 01:30 JST, is `docs/archive/STATE-before-2026-11-17.md`.
<!-- state:generated -->
**As of:** 11-17 19:46 JST (written by `loop.sh state`). Harness 2703e4a9 committed; e4140adc deployed (not the same).
**Live, and stopped in the last day:** run-760be6cb failed at failed; run-092a40cb failed at awaiting_approval:defect_fix_1_0; run-844673cd failed at failed; run-9f8188cb failed at failed; run-2db7b0a2 failed at failed; run-4db255e8 failed at failed
**Last scored:** run-760be6cb notes-api-rust 0/9 (failed, handoff 0.429; scored 11-17 19:46 JST); run-e53e1441 notes-api-java 9/9 (completed, mixed, 89 active min, handoff 1.0; scored 11-17 17:56 JST); run-666e030f notes-api-go 9/9 (completed, mixed, 69 active min, handoff 1.0; scored 11-17 16:45 JST).
<!-- /state:generated -->

## Live now
| | |
|---|---|
| Phase | Launch review (`docs/reviews/launch-review-2026-11-16.md`, LR.1-65) built item by item; M36 measuring runs on both ports. Owner hands off 11-16 21:50 JST: all review items by the morning of 11-17. |
| Models | :8888 `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` (key); :1234 `qwen3.6-35b-a3b-mtp@iq4_nl` (no key). Both the owner's; :1234 HELD by the owner since 11-17 18:45 JST (only :8888 takes runs); each run pinned to its port (`PIN_MODEL=1`). Never load or change them. |
| Harness | af9aa70d deployed 11-17 11:55 JST: LF.995-1010 (owner 11-17: remaining launch items built in parallel behind switches, all ON, past runs the baseline). Host has Pyright 1.1.414. |
| Switches | 52 fixes built in (always on; only a host env var turns one off). 11 optional switches; one on - NEAR_GREEN_REPLANNED_ONCE (Efficiency, LF.977, measuring.md M14: off at once if a run it fires in loses a hidden test). Off: Context and cost (OBSERVATION_FOLDING, STABLE_STAGE_PREFIX, BATCH_ACCEPTANCE_AUTHOR, REASONING_KEPT_AFTER_AN_ANSWER), Efficiency (EQUIVALENT_MUTANTS_REMEMBERED, MUTANT_CHECK_IN_THE_FIX_STAGE, REVIEWS_WITHOUT_REASONING, HARNESS_FINDINGS_RECHECKED), Setup scope (SETUP_SCOPE_GUARD), Review gates (MILESTONE_EVIDENCE_GATE). Admin page: Controls. |
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

## Morning report (11-17)
Of the 52 launch-review items, 42 are done, 5 in part, 5 not done.
- Done tonight: LR.51 (LF.969-970: a commit, revert or restore that did not happen is reported; a restore is all or
  nothing), LR.25 (LF.971: quality sets for every family; the old references failed 1-3 of them and were fixed),
  LR.24 (LF.973: the 44 production-default failures were all tests of the off path; none was an on-path defect),
  LR.15 rest (LF.968), LR.54 part (LF.967), LR.41 (shortlinks-api, held out), LR.64 (this file).
- Found live and fixed: LF.974 - under a load spike the orphan sweep took a partial broker answer for "the task is
  gone" and resumed a running run (two tasks on one run for 17 min; the second held the last worker slot, so the
  run started on :8888 never began). LF.972 - a deploy's boundary pause lost with a killed app worker is asked again.
  The load spike (load average about 2,700 at 00:45-01:00 JST) has no known cause; watch for a repeat.
- Found on the language sweep (Go, Rust, Java, C#, PHP, Ruby, one run each) and fixed, each deployed:
  LF.978 a false `npm test` blocker on non-Node stacks; LF.979 unit tests that do not compile now named, not taken
  for passing; LF.980 Python writes checked by Pyright as they land (13 reverts in one run); LF.981 a pack's
  scaffold opens its toolchain (a C# run refused `dotnet`); LF.983 a doubled compiler path; LF.984 suite writers
  told kept files are tested by what they do (seen working in the next run); LF.986 routes probed with an id that
  is not a number (a 500 only a quality test found); LF.989 a product that listens but fails every request is
  told so, not "did not start"; LF.990 the LF.986 defect asks for a refusal, not the line's success (it
  fired on PHP: `GET /notes/not-a-number` answered 500). LF.991 the backend role refuses what it cannot use with a 4xx (3 of 6 sweep runs
  had a 500 there); LF.992 a spec making its own `require` with `createRequire` is not flagged as CommonJS; LF.993 the bad-body
  probe sends unparsable bytes - it had sent a valid JSON string, so the "unparsable JSON answered 500" defects in
  Ruby and C# were the probe's (both products answer 422 when asked by hand); each re-planned a sprint on it. Records: LF.976 real re-plan counts, LF.982, LF.987. Scorer: LF.985, LF.988.
- Sweep scores: every language 9/9 hidden; quality 7/8-8/8 but C# 6/8. Recurring product defects the harness does not
  yet catch: writes made at once lost (several families) - next: pack storage guidance and a concurrent-write probe.
- In part: LR.20 (the report is built; the frozen batch is about 5 days of runs, not started), LR.30 (per-pack
  images LF.1005, container environment LF.1007, 7 images built; first whole container-mode run (Python notes-api,
  run-19ff2786) scored 9/9 hidden, 8/8 quality, delivered (LF.1015 scorer fix); Java next, then the other toolchains), LR.52, and LR.53 (cause grouping; a green suite settles; a near-green
  sprint is planned again once - LF.977, measured on 175 past re-plans; open: a repair back to the round), LR.54 (four contradictions removed).
- LR.42 done. LR.50 done (LF.1016 phase 1, LF.1018 phase 2: every node lifted into `app.graph.nodes`, one
  `GraphContext`; workflow.py is the wiring). LR.46 rest waits on the rule-coverage counter's data; LR.44
  (hosted-model matrix) waits for the owner.

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
   Live: Rust container run 2, run-c7a00abc-1f89-4d22-a153-2341b48c4641 (:8888, 19:54), on e02b0bbf.
2. LR.30 container-mode Go run 1, run-666e030f-1c7d-4830-bf58-b9594f31ac4a (:1234, 15:28-16:44): hidden 9/9, quality
   8/8, handoff 1.0, verdict not_deliverable (contract lines and design points left open). LF.1022, LF.1024-1025 from it.
   C# next on :1234: its pack failed `verify_packs` in container mode (LF.1027, the .NET image's uid) - a run started on it
   at 16:46 was cancelled at once; verify every pack in container mode before its first run.
   C# container run 1, run-092a40cb-21da-4853-b600-cfb137ce824b (:1234, 16:54): stopped when the owner took :1234
   (18:45 JST). :1234 is HELD for the owner's other task: only :8888 takes runs until it is released.
3. The language sweep then has one run per language; next, a second run of the families that lost quality tests.
   LF.987 (records only) waits for the next deploy. shortlinks-api is held out (Measure runs only, `MEASURE=1`).
3. LR.53 rest (a suite repair that leaves the suite near green goes back to the round: M14's open part), LR.52 rest, then a whole run in container mode (LR.30).
4. When no fix is pending for a full audit cycle: freeze and start the LR.20 batch.

## Rules that are never optional
`AGENTS.md`. In short: the model is the owner's (`loop.sh ready` must say ALL READY); fixes are stack-agnostic
(packs, `plugins/seed.py`, per-language tables); every fix has a test proven failing on the old code; both suites
green; commit and push after every change (`git push main harness-hardening-session`); no secrets printed; the
operator account only (`docs/HANDOVER.md` §3); times in JST.
