# State of the loop
The one file every session reads first (plan MF.6): what is live, what is off, the last three runs, the next
action. At most 150 lines and 16,000 characters, rewritten, never appended. Reference: `docs/HANDOVER.md` (rules,
accounts, commands), `docs/monitoring-handover.md` (mechanics, run log), `docs/improvement-plan.md` (every fix, LF
rows), `docs/measuring.md` (everything under measurement), `docs/owner-decisions.md`. The file this replaced, with
every narrative up to 11-17 01:30 JST, is `docs/archive/STATE-before-2026-11-17.md`.
<!-- state:generated -->
**As of:** 11-17 02:26 JST (written by `loop.sh state`). Harness cf069ea7 committed; 44dbe725 deployed (not the same).
**Live, and stopped in the last day:** run-925391f7 running at advice_review_security_reliability; run-53970d86 failed at ?; run-bdf40247 failed at awaiting_approval:defect_fix_2_15; run-9831f11c failed at awaiting_approval:defect_fix_1_5
**Last scored:** run-d8b0e95b notes-api-rust 9/9 (completed, handoff 0.857; scored 11-17 02:26 JST); run-ca45a144 notes-api-go 9/9 (completed, mixed, 56 active min, handoff 1.0; scored 11-17 00:37 JST); run-fdd127ff textkit-lib 8/8 (completed, 23 active min, handoff 1.0; scored 11-16 23:25 JST).
<!-- /state:generated -->

## Live now
| | |
|---|---|
| Phase | Launch review (`docs/reviews/launch-review-2026-11-16.md`, LR.1-65) built item by item; M36 measuring runs on both ports. Owner hands off 11-16 21:50 JST: all review items by the morning of 11-17. |
| Models | :8888 `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` (key); :1234 `qwen3.6-35b-a3b-mtp@iq4_nl` (no key). Both the owner's; both take runs; each run pinned to its port (`PIN_MODEL=1`). Never load or change them. |
| Harness | 0216902e (LF.978-979) deploying 11-17 ~02:40 JST; 005ce413 (LF.976-977) live from 01:52; 4d062ad0 (LF.970-974) before. |
| Switches | 52 fixes built in (always on; only a host env var turns one off). 11 optional switches; one on - NEAR_GREEN_REPLANNED_ONCE (Efficiency, LF.977, measuring.md M14: off at once if a run it fires in loses a hidden test). Off: Context and cost (OBSERVATION_FOLDING, STABLE_STAGE_PREFIX, BATCH_ACCEPTANCE_AUTHOR, REASONING_KEPT_AFTER_AN_ANSWER), Efficiency (EQUIVALENT_MUTANTS_REMEMBERED, MUTANT_CHECK_IN_THE_FIX_STAGE, REVIEWS_WITHOUT_REASONING, HARNESS_FINDINGS_RECHECKED), Setup scope (SETUP_SCOPE_GUARD), Review gates (MILESTONE_EVIDENCE_GATE). Admin page: Controls. |
| Operations | Backups nightly to `data/backups` and `BACKUP_DIR` (external disk, 7 daily + 4 weekly), checked by `loop.sh backup --check`; finished runs older than `RETENTION_DAYS` (60) cleared nightly; both set in git-ignored `data/loop/ops.env`. Owner's Postgres port in git-ignored `docker-compose.override.yml`; `docker-compose.prod.yml` + `deploy/Caddyfile` for TLS. |
| Suites | `loop.sh suite` and `loop.sh suite-production` (every built-in fix on, as shipped) both green: 17,316 passed, 0 known failures. |

## Off until measured
The 10 optional switches above. Hosted-model runs (LR.44) only when the owner starts or instructs them.

## The last three runs
Generated above. Tonight's M36 runs (hidden, quality, verdict):
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
- In part: LR.20 (the report is built; the frozen batch is about 5 days of runs, not started), LR.30 (isolation
  built; container mode fits Node and Python stacks only - each pack needs its own image, see the review doc), LR.52, and LR.53 (cause grouping; a green suite settles; a near-green
  sprint is planned again once - LF.977, measured on 175 past re-plans; open: a repair back to the round), LR.54 (four contradictions removed).
- Not done, and why: LR.42 (scale the process to the brief), LR.46 (narrow rules behind the pack interface),
  LR.50 (lift nodes out of `build_workflow_graph`) - each a week-sized redesign that needs measured runs before and
  after, not a night; LR.44 (hosted-model matrix) waits for the owner.

## Next actions
1. Live: tasks-api 2 run-925391f7 (:1234, rewound to its 00:11 JST defect fix after the duplicate, sprint 1 green 43/43).
   Score it with its full id when it finishes. The status board (Claude Doc) was not updated: the docs connector was
   not connected this session.
2. Then shortlinks-api 1 on :1234 (held out); the language sweep on :8888: notes-api-java (next, after the LF.978-979 deploy), -csharp, -php, -ruby.
3. LR.53 rest (a suite repair that leaves the suite near green goes back to the round: M14's open part), LR.52 rest, then a whole run in container mode (LR.30).
4. When no fix is pending for a full audit cycle: freeze and start the LR.20 batch.

## Rules that are never optional
`AGENTS.md`. In short: the model is the owner's (`loop.sh ready` must say ALL READY); fixes are stack-agnostic
(packs, `plugins/seed.py`, per-language tables); every fix has a test proven failing on the old code; both suites
green; commit and push after every change (`git push main harness-hardening-session`); no secrets printed; the
operator account only (`docs/HANDOVER.md` §3); times in JST.
