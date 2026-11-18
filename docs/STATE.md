# State of the loop
The one file every session reads first (plan MF.6): what is live, what is off, the last three runs, the next
action. At most 150 lines and 16,000 characters, rewritten, never appended. Reference: `docs/HANDOVER.md` (rules,
accounts, commands), `docs/monitoring-handover.md` (mechanics, run log), `docs/improvement-plan.md` (every fix, LF
rows), `docs/measuring.md` (everything under measurement), `docs/owner-decisions.md`. The file this replaced, with
every narrative up to 11-17 01:30 JST, is `docs/archive/STATE-before-2026-11-17.md`.
<!-- state:generated -->
**As of:** 11-18 16:15 JST (written by `loop.sh state`). Harness 0e092255 committed; 0e092255 deployed.
**Live, and stopped in the last day:** run-e8053d6e running at defect_fix_2_6; run-8f1478a7 running at defect_fix_2_12; run-1e04154a failed at failed; run-db139a37 failed at failed; run-760be6cb failed at failed; run-092a40cb failed at awaiting_approval:defect_fix_1_0
**Last scored:** run-260f3fc5 tasks-api 10/10 (completed, 210 active min, handoff 1.0; scored 11-18 16:15 JST); run-1e04154a notes-api-rust 0/9 (failed, mixed, 137 active min, handoff 0.429; scored 11-18 13:47 JST); run-4886c02b notes-api-go 9/9 (completed, mixed, 47 active min, handoff 1.0; scored 11-18 13:45 JST).
<!-- /state:generated -->

## Live now
| | |
|---|---|
| Phase | **Deep-review plan (owner 11-18 16:25 JST: implement all; doc 9nhWdxAtiiatDkDiLR5Wwx).** Frozen-version measuring: bundles ship at run boundaries, mid-run deploys only for an outcome-changing bug. Language sweep and RC count paused until items 1.7 and 1.8 are built. Wave 1 (6 bundles in worktrees) building since 16:30. |
| Models | :8888 `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` (key); :1234 `qwen3.6-35b-a3b-mtp@iq4_nl` (no key). Both the owner's; both take runs (:1234 was held 18:45-21:52 JST on 11-17); each run pinned to its port (`PIN_MODEL=1`). Never load or change them. |
| Harness | 0e092255 deployed 11-18 16:10 JST (LF.1071); LF.1072 is scorer-only. Host has Pyright 1.1.414. |
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
1. Deep-review wave 1, six bundles in worktrees (each item: a fail-on-old test, an LF row on merge):
   B1 fix-loop measurement (A1 unmeasured outcome, A2 compiler-gated rewrites, A3 checkpoints and culprit-only batch
   revert, A5 no re-asks, A7 closure by measurement); B2 verification (B2 probes at release, B1 contract edge probe,
   B5 browser probes, B4 verdict calibration, B6 unit-test filter); B3 agents (C5 tool lists, C3 request size, C7
   prompt contradictions + lean profile, C8 intake questions); B4 stacks (E3 language table, E4 golden examples);
   B5 product (best attempt, Git source, tidy handover, supported matrix, run doctor, health page); B6 sandbox (E1a no
   product code in the worker, E2 dependency gate, E1b broker design). Merge, both suites, verify_packs, deploy at the
   live runs' end.
2. Wave 2 (after wave 1 merges): 1.1 typed defects, 1.4 fix journal / end attempt by cause / targeted re-plan, 1.5
   integrator gate, 1.6 ordered drafting waves, D5 `degraded()` helper, D4 switch clean-up, D2 one attempt record.
3. Wave 3: C2 typed contract, C4 harness-driven fixer, F2 change lane, D3 transition table, 2.1 medium benchmark, 2.6
   hidden evaluator, E1/E2 broker and registry proxy live, 2.8 role ablation runs. Hosted test (decision 4) waits on
   the owner's yes, provider and budget.
4. Live: C# container run 3 (:1234) and PHP container run 2 (:8888) run to their end on 0e092255; score both, then
   start nothing new on a port until wave 1 is deployed (frozen version, two runs per family).

## Rules that are never optional
`AGENTS.md`. In short: the model is the owner's (`loop.sh ready` must say ALL READY); fixes are stack-agnostic
(packs, `plugins/seed.py`, per-language tables); every fix has a test proven failing on the old code; both suites
green; commit and push after every change (`git push main harness-hardening-session`); no secrets printed; the
operator account only (`docs/HANDOVER.md` §3); times in JST.
