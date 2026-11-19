# State of the loop
The one file every session reads first (plan MF.6): what is live, what is off, the last three runs, the next
action. At most 150 lines and 16,000 characters, rewritten, never appended. Reference: `docs/HANDOVER.md` (rules,
accounts, commands), `docs/monitoring-handover.md` (mechanics, run log), `docs/improvement-plan.md` (every fix, LF
rows), `docs/measuring.md` (everything under measurement), `docs/owner-decisions.md`. The file this replaced, with
every narrative up to 11-17 01:30 JST, is `docs/archive/STATE-before-2026-11-17.md`.
<!-- state:generated -->
**As of:** 11-19 15:45 JST (written by `loop.sh state`). Harness 51022b54 committed; 51022b54 deployed.
**Live, and stopped in the last day:** run-5c68f972 running at defect_fix_1_1; run-eaed36e7 failed at failed; run-e68d3ce9 failed at failed; run-cbf36159 failed at failed; run-8f1478a7 failed at failed; run-1aa50e5e failed at failed
**Last scored:** run-23078e72 tasks-api 10/10 (completed, handoff 0.875; scored 11-19 15:45 JST); run-7880a2c0 notes-api-go 9/9 (completed, mixed, 73 active min, handoff 1.0; scored 11-19 15:07 JST); run-d74ff9cb notes-api-csharp 9/9 (completed, mixed, 83 active min, handoff 1.0; scored 11-19 13:36 JST).
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
- tasks-api 2 run-58e79fce-d928-4d32-a9ea-78e3c8eb9482 (:8888, 23:30-02:15, mixed): **10/10, 7/7, handoff 1.0**, mutation
  0.55, 144 active minutes; its own verdict not deliverable on four contract lines answered 401 to the unsigned bare
  probe (a false red, LF.1116). Root cause of both that and the edge probe's 22 skipped checks: the sign-up body was
  written `{"username": <string>, ...}` after `— request body:` and never read, so no probe signed in (LF.1117).
- Haiku arm: H notes-api-rust hybrid-haiku 1 run-160e0f62-7720-49e1-a831-50f5453e7484 (:1234, 01:25-02:54, mixed):
  **9/9 hidden, 7/8 quality**, 88 active min, 3 reverts, $0.87 hosted - but Haiku-BUILT, not judgement-only: a design
  escalation moved every build stage to Haiku (LF.1123). The first Rust 9/9 on the new version (local-only
  Rust 1, 4, 7: 0/9). Verdict not deliverable on a real gap: a spaces-only title accepted. Sprint 1 attempts 1-4 lost
  to one defect (LF.1118).
- M web-todo container 1 run-3cc0ed29-ac73-423d-bb47-ee30e36953e7 (:8888, 02:37-05:10, mixed): **10/10, 6/6, delivered**,
  handoff 1.0, mutation 1.0, 129 active min, 0 reverts. Lost ~30 min to a form-id mismatch (LF.1121) and re-run probes
  (LF.1122) before both were fixed live.
- H notes-api-csharp hybrid-haiku 1 run-04f2aa30-834c-4895-bab4-6e42f9dd168d (:1234, 03:19-05:10, mixed): **9/9, 8/8,
  delivered**, handoff 1.0, mutation 0.8, 101 active min, $1.31 hosted - the first full C# score. Haiku-BUILT (design
  escalation, LF.1123). Survived LF.1124 (reply blocks written as files) and LF.1125 (offline delivered start).
- H notes-api-rust hybrid-haiku 2 run-82f66a50-dafd-4ea3-81ab-69140b79189f (:1234, 05:15-08:52, mixed, rewound 06:58):
  **9/9, 7/8, delivered with cuts**, handoff 0.857, mutation 1.0, 111 active min, $1.45 hosted. Judgement-only for
  attempt 1 (compile errors), then Haiku-built after the re-plan (designed rung). LF.1126 fired: `app()` kept for the
  first time. Lost the blank-title quality test: its contract was all unreadable (LF.1127), so no probe asked a write.
- H notes-api-csharp hybrid-haiku 2 (judgement only) run-e68d3ce9-f8ef-41bb-90a2-cc37fd5e9228 (:1234, 09:10-10:51,
  mixed): **3/9, 4/8, failed** (stalled after two re-plans), 98 active min, $0.43. Hosted arms so far: Haiku-built
  Rust 9/9 and C# 9/9; judgement-only C# 3/9 (Rust 9/9 only after its build moved to Haiku). The build model carries
  the hard languages; judgement on Haiku over a local build does not rescue C#.
- M tasks-api container 3 run-af4108e6-0e1b-4287-a87c-a67f2796a1c7 (:8888, 05:16-10:45, mixed): **10/10, 7/7, not
  deliverable** (a real defect: the product leaks SQLite connections and the locked suite's sequence hangs; hidden tests
  do not exercise it), handoff 1.0, 315 active min, 40 defects left open - the local model never closed the leak.
- H tasks-api hybrid-haiku 1 (judgement only) run-23078e72-af18-49d4-b0b7-2d6f6faa3f92 (:1234, 13:04-15:43, mixed):
  **10/10, 7/7, delivered**, handoff 0.875, 148 active min, $1.34. Identical calls 36% (5-run mean 3%): each part of a
  review answered in parts starts a fresh conversation and re-reads the same files - a review took ~5 min of it. Hybrid
  arms done (Rust, C#, web-todo, tasks-api); hosted total ~$4.80 of $30.
- M notes-api-go container 1 run-7880a2c0-c41a-4827-8bfd-341529f5ce0c (:8888, 13:39-15:05, mixed): **9/9, 8/8, delivered**,
  handoff 1.0, mutation 0.9, 73 active min. Its first attempt never started (a drafted go.mod needing `go mod tidy`,
  which no fixer can run without a network - LF.1134 since); the re-plan recovered.
- M notes-api-csharp container 5 run-d74ff9cb-e47a-4723-9c79-1c93bd4b0be9 (:8888, 12:06-13:33, mixed): **9/9, 7/8,
  not deliverable - and right**: the one defect left open, writes made at the same moment not each kept (the
  concurrent-write probe), is exactly the quality test lost. Handoff 1.0, 83 active min. First full local C# score
  (C# 4: 0/9, a false acceptance). LF.1125/1128/1131 fired; recovered from a NU1202 dependency (LF.1132 since).
- H web-todo hybrid-haiku 1 (judgement only) run-249303db-1fb7-4b11-9ec2-2f9ccb957f83 (:1234, 11:04-12:52, mixed):
  **9/10, 6/6, delivered - a FALSE ACCEPTANCE**, 96.5 active min, $0.18. A last fix toggled a row's class in place
  instead of re-rendering, so a task completed under the "active" filter stays listed; no locked test completes a task
  while filtered. Candidate guidance for the browser packs (seed.py): state changes re-render through the filtered view.
- M notes-api-rust container 8 run-eaed36e7-d0cb-4ac6-8b98-4aab119efab6 (:8888, 10:55-12:00, rewound 11:21, mixed):
  **0/9, 0/8, failed** - the product never compiled (12 borrow/ownership errors) though every fix aimed at Rust fired:
  LF.1126 finding, LF.1130 ruling, LF.1131 folding, rusqlite pinned to a version rustc 1.85 builds. Local Rust is 0/9
  in runs 1, 4, 7, 8, all compile failures; Haiku-built Rust 9/9 twice. The remaining limit is the local model's Rust.
- LF.1116-1118 shipped live 03:10 JST, LF.1119 (a run store opened beside the backup's dump stalled the app
  03:05-03:09) at 03:18, both into web-todo 1 (mixed).
- H notes-api-csharp hybrid-haiku 1 run-04f2aa30-834c-4895-bab4-6e42f9dd168d (:1234, 03:19, on 9d134086) - the second
  Haiku arm run: does the judgement tier lift C# as it lifted Rust?
- LF.1120 (a stage researched before it began is offered no lookup tool; the Haiku architect spent five paid turns on
  refused `read_docs`) and LF.1121 (a script looking up an id no page declares is a proven defect - web-todo 1 lost
  40/46 tests to `add-task-form` vs `add-form`) shipping into both runs (both mixed). LF.1122 (an acceptance file
  is run once per product while defects are dispatched; 53 runs in 20 min on one unchanged product) live 03:59.
- LF.1124 shipped live ~04:25: a hosted reply's block list was written as its Python form into five C# source files
  (81 syntax errors on line 1; the C# Haiku run's first attempt lost to it). Every reply reader now reads text blocks.
- LF.1126 live 06:50 (5cd321e); Rust hybrid 2 rewound to architecture_review at 06:52 so its specification is checked
  and the judgement-only arm is measured on a buildable design (mixed). Was: a specification that calls the setup's no-parameter `app()` with
  arguments goes back to the architect - the root of the Rust `app()` failures, 5 of 5 recent Rust runs.
- LF.1125 shipped live ~05:00: the delivered-product start of a toolchain that restores when it starts (C#) gets a
  network; NU1301 in every round on a C# product that started for the suite (LF.1113's run had the same root).
- LF.1123 committed, deploys at the next boundary: the C# Haiku run is also Haiku-built (design escalation) and
  finishes as such. The judgement-only hybrid arm has not been measured yet - next Haiku run measures it.
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
