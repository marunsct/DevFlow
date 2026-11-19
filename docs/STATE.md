# State of the loop
The one file every session reads first (plan MF.6): what is live, what is off, the last three runs, the next
action. At most 150 lines and 16,000 characters, rewritten, never appended. Reference: `docs/HANDOVER.md` (rules,
accounts, commands), `docs/monitoring-handover.md` (mechanics, run log), `docs/improvement-plan.md` (every fix, LF
rows), `docs/measuring.md` (everything under measurement), `docs/owner-decisions.md`. The file this replaced, with
every narrative up to 11-17 01:30 JST, is `docs/archive/STATE-before-2026-11-17.md`.
<!-- state:generated -->
**As of:** 11-20 00:23 JST (written by `loop.sh state`). Harness edfd65e9 committed; bdcedefb deployed (not the same).
**Live, and stopped in the last day:** run-eaed36e7 failed at failed; run-e68d3ce9 failed at failed
**Last scored:** run-6d577fad notes-api-go 9/9 (completed, handoff 1.0; scored 11-20 00:23 JST); run-840dfaf1 notes-api-csharp 9/9 (completed, 53 active min, handoff 1.0; scored 11-20 00:15 JST); run-ab877193 tasks-api 10/10 (completed, mixed, 96 active min, handoff 1.0; scored 11-19 22:45 JST).
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
Earlier runs: git history of this file and the status board.
- :8888 held by the owner 20 Nov ~00:25-00:30 JST, released; both ports take runs. Live: M web-todo container 3
  run-0080bed4-34fa-4e72-9ff5-32d56e180ad6 (:8888, 00:30), M notes-api-java container 2 run-e382df47-4105-44d6-b678-9e62b4009154 (:1234, 00:28).
- M notes-api-go container 2 run-6d577fad-b2a9-4525-93ee-3cb3f2f34e98 (:1234, 22:17-00:17): **9/9, 8/8, delivered**, handoff 1.0,
  120 active min. LF.1134 measured: no "go.mod needs tidy" all run (Go 1 lost an attempt to it). Redundant reads 36%, the
  highest this week - the restart re-read pattern (backlog), now in four runs.
- M notes-api-csharp container 6 run-840dfaf1-ce11-48d2-9bef-e12a80b24fd2 (:8888, 22:51-23:47): **9/9, 8/8, delivered**, handoff
  1.0, mutation 0.86, 53 active min - the best local C# run; the concurrent-writes quality test C# 5 lost now passes
  (LF.1133). The audit cron had expired at 23:46 (7-day limit) and was recreated 00:16; this run was scored 00:17.
- M tasks-api container 4 run-ab877193-00ec-4a46-bba3-272497adde08 (:8888, 19:14-22:44, paused 20:21-20:53 for an unloaded
  model, mixed): **10/10, 7/7, delivered with cuts**, handoff 1.0, 96 active min - against container 3's 315 on the same
  brief. LF.1133 measured working: WAL, a busy timeout and a request-scoped connection closed in `finally` from the first draft.
- M notes-api-ruby container 1 run-7a5a4556-5654-462f-a761-e9830dced91a (:1234, 17:29-22:13, mixed): **9/9, 8/8, delivered**,
  handoff 1.0, mutation 0.75, but 267 active min - an invented `sqlite3 ~> 1.0.2` failed every install, and QA spent a
  22-minute repair round and six refused Gemfile edits chasing it (LF.1138, LF.1139 since). Every local family is now
  9/9 or better except Rust.
- M web-todo container 2 run-686e8d70-7600-49d7-afbf-2376ad5699da (:8888, 17:54-19:03, mixed): **10/10, 6/6, delivered**,
  handoff 1.0, mutation 0.75, 64 active min, no KPI regression. The hybrid's browser-filter false acceptance did not recur.
- M notes-api-java container 1 run-5c68f972-a08a-4531-9d2f-fdd9d0d226ca (:8888, 15:12-17:33, mixed): **9/9, 6/8, not
  deliverable - and right**: a non-numeric id answered 500, which the harness's server-error probe raised and the local
  model never fixed (malformed JSON too). Handoff 1.0, 120 active min. First full hidden score for local Java.
- M notes-api-php container 5 run-34ea7163-aa42-4b39-b3c8-1fa619f969ca (:1234, 15:52-17:24, mixed): **9/9, 8/8, delivered**,
  handoff 1.0, mutation 0.89, 89 active min, 0 reverts, 0 defects left open. One install failure was shown to its fixer
  as Composer's usage text (LF.1136 since).
## Next actions
1. Score the live runs when they finish (web-todo container 3, Java container 2); start the next family on each port
   through the gated start.
2. Internet lookups (owner 11-20, `docs/improvement-plan.md` Appendix 10, WL.0-WL.7): WL.1 (search asks the
   developer sources; the general engines refuse the private instance) built and suite-green, deploys at the next
   run boundary; then WL.2-WL.4 (Stack Exchange and GitHub issue search, the user setting, lookups when stuck) behind
   `WEB_LOOKUP_WHEN_STUCK`. Owner action: a free Stack Apps key and a no-scope GitHub token; a Brave key optional.
3. Backlog: the restart re-read pattern (4 runs); version look-up before a manifest line; browser-pack re-render
   through the filtered view; Rust routing (local Rust 0/9 in four runs, Haiku-built 9/9 twice) for the owner.

## Rules that are never optional
`AGENTS.md`. In short: the model is the owner's (`loop.sh ready` must say ALL READY); fixes are stack-agnostic
(packs, `plugins/seed.py`, per-language tables); every fix has a test proven failing on the old code; both suites
green; commit and push after every change (`git push main harness-hardening-session`); no secrets printed; the
operator account only (`docs/HANDOVER.md` §3); times in JST.
