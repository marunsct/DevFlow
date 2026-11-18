# State of the loop
The one file every session reads first (plan MF.6): what is live, what is off, the last three runs, the next
action. At most 150 lines and 16,000 characters, rewritten, never appended. Reference: `docs/HANDOVER.md` (rules,
accounts, commands), `docs/monitoring-handover.md` (mechanics, run log), `docs/improvement-plan.md` (every fix, LF
rows), `docs/measuring.md` (everything under measurement), `docs/owner-decisions.md`. The file this replaced, with
every narrative up to 11-17 01:30 JST, is `docs/archive/STATE-before-2026-11-17.md`.
<!-- state:generated -->
**As of:** 11-19 01:25 JST (written by `loop.sh state`). Harness 40c3307e committed; 14207a14 deployed (not the same).
**Live, and stopped in the last day:** run-58e79fce running at defect_fix_2_0; run-160e0f62 running at tools_models; run-cbf36159 failed at failed; run-8f1478a7 failed at failed; run-1aa50e5e failed at failed; run-1e04154a failed at failed
**Last scored:** run-1b5b8d8e notes-api-csharp 0/9 (completed, FALSE ACCEPTANCE, handoff 1.0; scored 11-19 01:25 JST); run-f00ea384 notes-api-php 9/9 (completed, mixed, 125 active min, handoff 1.0; scored 11-18 23:25 JST); run-cbf36159 notes-api-rust 0/9 (failed, mixed, 134 active min, handoff 0.429; scored 11-18 22:36 JST).
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
Generated above. Today (hidden, quality, verdict):
- notes-api-php 2 run-8f1478a7-72fe-4881-9efa-a932afdc7176 (:8888, 13:5x-19:06, mixed): 0/9, 0/8, failed on the sprint
  time budget (296 of 246 active minutes): never started for long - invented Slim methods and a misplaced namespace,
  7 "no longer starts" reverts. Fixes since: LF.1098 (PHPStan), LF.1095 (golden example), LF.1104 (start first).
- notes-api-rust 6 run-1aa50e5e-a142-418f-913b-dbfe5aab83cf (:1234, 16:49-18:29, frozen 0e092255): 0/9, 0/8, failed:
  a local `struct State` against axum's extractor, then the handler trait bound; no axum note reached a request
  (LF.1071) but the specification planned tests on `TestClient` (LF.1096 since).
- notes-api-csharp 3 run-e8053d6e: 9/9, 8/8, delivered at an escalation after four sprint attempts (a false red).
- **notes-api-php 3 run-c5d6a8a5-6f88-4247-adcf-52c0a8aaad0c (:8888, 20:09-21:00, frozen 532dba3): 9/9, 8/8,
  delivered, handoff 1.0, mutation 0.64, 44.8 active minutes, 0 reverts, 0 left open** - against PHP 2's 0/9 in 313.6
  minutes with 14 reverts. Drafting waves, the golden example, PHPStan and the dependency gate all fired; the product
  started at the first round. Next: PHP 4 run-f00ea384-9ae9-4010-b75e-ee00ff1e35ad (:8888, 21:05) to confirm.
- notes-api-rust 7 run-cbf36159-b68e-4405-9440-db9797ce1aad (:1234, 20:09-22:35, mixed 532dba3..d03b4d3): 0/9, 0/8,
  failed after three sprint attempts, 134 active minutes, 1 revert. Each layer of manifest failure was fixed in the
  run (LF.1106 offline DNS, LF.1108 crate features, LF.1109 hand-written lock file), and then compile errors in its own
  Rust code remained - the local model's limit on Rust. Rust is the first family for the Haiku arm.
- notes-api-php 4 run-f00ea384-9ae9-4010-b75e-ee00ff1e35ad (:8888, 21:05-23:24, mixed): **9/9, 8/8, handoff 1.0**,
  mutation 0.3, 125 active minutes, 0 reverts - PHP 2 of 2 full on the new version (old: 0/9). Its own verdict said
  not deliverable on a 400-vs-404 contract line for a malformed id (a false red, LF.1110 since).
- notes-api-csharp 4 run-1b5b8d8e-a5a7-45c1-8987-a26b84b04716 (:1234, 22:37-01:24, mixed): **0/9, 0/8, delivered - a
  false acceptance.** Suite 18/18 in the harness after five attempts (LF.1111 installed the nested package), but a
  re-planned work order had pointed `nuget.config` at the sandbox's own `.agent-home` cache: nothing restores outside
  the harness. LF.1113 refuses that write and blocks such a release.
- Haiku arm: H notes-api-rust hybrid-haiku 1 run-160e0f62-7720-49e1-a831-50f5453e7484 (:1234 build, Haiku judgement,
  01:25) - the architect's calls reach api.anthropic.com.
- **Deployed 20:09 JST: 532dba3 (waves 1 and 2, LF.1073-1105).** Live on it: M notes-api-rust container 7
  run-cbf36159-b68e-4405-9440-db9797ce1aad (:1234) and M notes-api-php container 3
  run-c5d6a8a5-6f88-4247-adcf-52c0a8aaad0c (:8888), both 20:09.

## Morning report (11-18)
Container sweep: every language delivered 9/9 hidden at least once (Go, Java, Rust, C#, PHP, Ruby, tasks-api);
Java run 5 the first Java with every quality test. Rust is the open family: runs 1 and 4 failed 0/9 on `app()`
declared as a router still waiting for its state; LF.1064 now holds the declaration at every round. Fixes overnight:
LF.1036-1064 (scorer: LF.1037/1042/1043/1046/1053/1054). Owner decision pending: `NEAR_GREEN_REPLANNED_ONCE` off by
default (patch saved; off per run meanwhile). The 11-17 report is in git history.

## Next actions
1. **Measure waves 1 and 2 on 532dba3 (frozen; no deploys into these runs):** two runs per family - Rust and PHP now,
   then C#, tasks-api, web-todo. Per run read: hidden/quality, `unmeasured` records, `degraded` records (run doctor),
   start-first folding, fix journal and diagnosis calls, best-checkpoint restores, single-culprit batch reverts,
   drafting waves and their minutes, edge/page probe false reds, dependency-gate verdicts, the verdict against the
   hidden score. A switch whose run loses a hidden test or takes 1.5x the family's active minutes goes off (M15).
2. Wave 3: C2 typed contract, C4 harness-driven fixer, F2 change lane, D3 transition table, 2.1 medium benchmark, 2.6
   hidden evaluator, E1b broker log-only trial, 2.8 role ablation runs. Hosted test waits on the owner's yes,
   provider and budget. `INSTALL_SCRIPTS_SKIPPED` built, off, unregistered.

## Rules that are never optional
`AGENTS.md`. In short: the model is the owner's (`loop.sh ready` must say ALL READY); fixes are stack-agnostic
(packs, `plugins/seed.py`, per-language tables); every fix has a test proven failing on the old code; both suites
green; commit and push after every change (`git push main harness-hardening-session`); no secrets printed; the
operator account only (`docs/HANDOVER.md` §3); times in JST.
