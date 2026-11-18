# State of the loop
The one file every session reads first (plan MF.6): what is live, what is off, the last three runs, the next
action. At most 150 lines and 16,000 characters, rewritten, never appended. Reference: `docs/HANDOVER.md` (rules,
accounts, commands), `docs/monitoring-handover.md` (mechanics, run log), `docs/improvement-plan.md` (every fix, LF
rows), `docs/measuring.md` (everything under measurement), `docs/owner-decisions.md`. The file this replaced, with
every narrative up to 11-17 01:30 JST, is `docs/archive/STATE-before-2026-11-17.md`.
<!-- state:generated -->
**As of:** 11-18 16:45 JST (written by `loop.sh state`). Harness ce51a55c committed; 0e092255 deployed (not the same).
**Live, and stopped in the last day:** run-8f1478a7 running at acceptance_dispute; run-1e04154a failed at failed; run-db139a37 failed at failed; run-760be6cb failed at failed; run-092a40cb failed at awaiting_approval:defect_fix_1_0
**Last scored:** run-e8053d6e notes-api-csharp 9/9 (completed, handoff 1.0; scored 11-18 16:45 JST); run-260f3fc5 tasks-api 10/10 (completed, 210 active min, handoff 1.0; scored 11-18 16:15 JST); run-1e04154a notes-api-rust 0/9 (failed, mixed, 137 active min, handoff 0.429; scored 11-18 13:47 JST).
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
Generated above. Today's container-mode runs (hidden, quality, verdict):
- notes-api-csharp 3 run-e8053d6e-82b7-4c00-a991-282b15beb4d2 (:1234, 13:49-16:44, mixed 90e875d8..0e092255): 9/9,
  8/8, delivered at an escalation, handoff 1.0, mutation 0.67. A false red for most of its 3 h: four sprint attempts,
  34 defects left open, 4 reverts (3 for a start the fixers broke), 5 min lost to false memory refusals (LF.1070) -
  the deep review's A1-A3 and B3/B4 in one run.
- notes-api-php 2 run-8f1478a7-72fe-4881-9efa-a932afdc7176 (:8888, live): round 2 closed nothing in 110 min; five
  reverts for a start broken by invented Slim methods; sprint re-planned at 16:38.
- notes-api-go 2 run-4886c02b (:1234): 9/9, 8/8, delivered. notes-api-rust 5 run-1e04154a: 0/9 (router-state trap;
  LF.1064, LF.1067, LF.1071 since).
- Live: notes-api-rust 6 run-1aa50e5e-a142-418f-913b-dbfe5aab83cf (:1234, 16:49, frozen 0e092255) - the first run
  with LF.1071 (no model-written axum note).

## Morning report (11-18)
Container sweep: every language delivered 9/9 hidden at least once (Go, Java, Rust, C#, PHP, Ruby, tasks-api);
Java run 5 the first Java with every quality test. Rust is the open family: runs 1 and 4 failed 0/9 on `app()`
declared as a router still waiting for its state; LF.1064 now holds the declaration at every round. Fixes overnight:
LF.1036-1064 (scorer: LF.1037/1042/1043/1046/1053/1054). Owner decision pending: `NEAR_GREEN_REPLANNED_ONCE` off by
default (patch saved; off per run meanwhile). The 11-17 report is in git history.

## Next actions
1. **Wave 1 is merged, green and pushed (LF.1073-1096, ba23885a), not deployed.** Both suites 18,365 passed;
   `verify_packs` compiled all seven golden examples. Deploy with `BOUNDARY_WAIT=0 loop.sh deploy` once both live runs
   have ended (frozen-version rule), then start two runs per family on the new version: notes-api-rust, notes-api-php,
   notes-api-csharp first (the families today's runs failed or dragged on), then tasks-api and web-todo (probes,
   verdict). Watch: `unmeasured` records, edge/page probe false reds, best-checkpoint restores, single-culprit batch
   reverts, the dependency gate's verdicts, start probe in its container.
2. Wave 2 building in worktrees: 1.1 typed defects + 1.4 fix journal / end by cause + 1.5 integrator gate; 1.6
   drafting waves; D2 rewind by snapshot id + D5 `degraded()`.
3. Wave 3: C2 typed contract, C4 harness-driven fixer, F2 change lane, D3 transition table, 2.1 medium benchmark, 2.6
   hidden evaluator, E1b broker live trial (`BROKER_ENFORCE=0` first), 2.8 role ablation runs. Hosted test waits on
   the owner's yes, provider and budget. `INSTALL_SCRIPTS_SKIPPED` built, off, unregistered.
4. Live on 0e092255: PHP container run 2 (:8888, second sprint attempt), Rust container run 6 (:1234, 16:49) - score
   both; Rust 6 is the baseline for LF.1096 (its specification planned unit tests on axum's TestClient).

## Rules that are never optional
`AGENTS.md`. In short: the model is the owner's (`loop.sh ready` must say ALL READY); fixes are stack-agnostic
(packs, `plugins/seed.py`, per-language tables); every fix has a test proven failing on the old code; both suites
green; commit and push after every change (`git push main harness-hardening-session`); no secrets printed; the
operator account only (`docs/HANDOVER.md` §3); times in JST.
