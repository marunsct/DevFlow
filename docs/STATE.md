# State of the loop
The one file every session reads first (plan MF.6): what is live, what is running, the last runs, the next action.
At most 150 lines and 16,000 characters, rewritten, never appended. Updated in every commit that changes any of those;
the block below is written by `loop.sh state`. The map of all documents is `docs/README.md`; open work is
`docs/improvement-plan.md`; how the product works is `docs/PRODUCT.md`; how to run and test it is `docs/HANDOVER.md`;
decisions in force are `docs/owner-decisions.md`; old information is found through `docs/ARCHIVE.md`.
<!-- state:generated -->
**As of:** 11-23 23:23 JST (written by `loop.sh state`). Harness c89334ea committed; 7df6e52b deployed (not the same).
**Live, and stopped in the last day:** run-8f0be29e running at test_round_2; run-418ca472 failed at awaiting_approval:defect_fix_1_11
**Last scored:** run-6c8ef0d7 fullstack-bookmarks 8/8 (completed, handoff 1.0; scored 11-23 23:23 JST); run-1a210682 notes-api-go 9/9 (completed, mixed, 41 active min, handoff 1.0; scored 11-23 20:09 JST); run-8c35f01e tasks-api 10/10 (completed, mixed, 60 active min, handoff 1.0; scored 11-23 19:04 JST).
<!-- /state:generated -->

## Live now
| | |
|---|---|
| Phase | **Learning runs, fixes deployed at once** (deep-review plan, owner 11-18: implement all; frozen-version measuring for Measure batches). The release-candidate count starts only when a full audit cycle finds nothing to fix. |
| Models | :8888 `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` (key); :1234 `qwen3.6-35b-a3b-mtp@iq4_nl` (no key). Both the owner's; both take runs; each run is pinned to its port. |
| Harness | Deployed 11-21 08:48 JST: 8cf5ae39 (LF.1140-1204; LF.1201-1204 off). Deploying after both suites: LF.1205 the Slim pack names a container passed to the app factory first. |
| Switches | 53 fixes built in (always on). 29 optional switches (9 groups, `docs/measuring.md`); `WEB_LOOKUP_WHEN_STUCK` is off and set per run. Measure arms use `SWITCHES_OFF` per run. |
| Operations | Nightly backups (`loop.sh backup --check`); finished runs older than 60 days cleared. Audit cron `01339d0d` every ~10 minutes (7-day expiry: recreate by 11-27). |
| Suites | `loop.sh suite` and `loop.sh suite-production` both green at 18,701 passed. |

## Off until measured
`WEB_LOOKUP_WHEN_STUCK` (internet lookups for a stuck fixer: needs 2 runs on, 2 off). BATCH_ACCEPTANCE_AUTHOR. Hosted-model
runs only when the owner starts them. Everything under measurement: `docs/improvement-plan.md` section 2.

## The last three runs (11-20, hidden / quality; local model)
Earlier runs: `reports/status-board/`, git history of this file.
- **Live (11-23 15:48 JST):** run-244ac383 `L notes-api-csharp container 15` on :8888 (started 23:28 on 7df6e52b). run-8f0be29e on :1234 (not mine). LF.1227-LF.1234 deployed 13:47 JST (c3423c45); LF.1235 deployed 14:57 JST (f71fef7e, md5 verified): a test picks out its own records by a marker each carries whole, and the dispute names one whose pick misses a record (bookmarks 6's AC-4 test kept titles holding "Work <id>" from "Work <id>" and "Work Two <id>", expected two, and the dispute ruled it right). LF.1236 deployed 15:07 JST (f8d3815c): drafted files recorded as the drafting pass's, so LF.1232 sees them (it had not fired on bookmarks 6). LF.1237 deployed 15:55 JST (fd0dd6fb): a test whose pick of its own records misses one it made cannot pass, before the lock and in a dispute (JavaScript packs).
  LF.1238 deployed 16:29 JST (d7fcfa7): `LONG_REASONING_BEFORE_A_READ` on (measured): the reply after one that reasoned 8,000+ tokens only to read goes without thinking. LF.1239 deployed 16:39 JST: the axum pack's known causes for a missing rusqlite `JournalMode`, a struct only imported and a `?` that cannot convert one library's error into another's (16:54, 3af9ad32; pack verified). LF.1240 deployed 17:10 JST (7384e2a7): the cause of a mutable call through a shared reference. LF.1241 deployed 18:03 JST (2c7f6e84): a TypeError on null the product's answer gave is the product's failure, not the test's; advice names every test reading an answer before its status (the owner's run spent four suite passes on it). LF.1242 deployed 19:26 JST (ef388011): the release probes take their bodies from the criteria too, so they sign in (tasks-api 14 lost two quality tests its probes never reached).
  LF.1243 deployed 20:07 JST (680e035): a 429 behind half the failing tests is one defect naming the rate limit (the owner's medium-brief run sat at 17 of 97 for eight hours behind a sign-up limit of ten an hour). LF.1244 deployed 21:01 JST (68086131): a fix round takes the defects its latest test round raised before those carried over (the owner's run fixed old defects while the router's double prefix 404ed every task route). LF.1245 deployed 22:30 JST (7df6e52b): a full-stack pack carries its service language's known errors (none reached a full-stack fixer before), and a doubly created index is a known cause (the owner's run reverted every fix for three rounds on it).
- Scored 2026-11-23: **fullstack-bookmarks 7 (8/8, 6/7; not deliverable: AC-8, AC-15, AC-17 deferred on page tests counting a shared list, LF.1246; 186 min)**, **notes-api-go 12 (9/9, 8/8; delivered, 48 min, mutation 0.89; LF.1242's probes reached every write)**, **tasks-api 14 (10/10, 5/7; delivered with cuts: AC-21; 63 min; blank title and concurrent creates lost - the release probes never signed in, LF.1242)**, **textkit-lib 8 (8/8, 7/7; delivered from the first draft in 10 min, mutation 1.0)**, **notes-api-rust 1 (9/9, 8/8; delivered, 97 min, mixed, mutation 0.50; one own unit test shipped failing - the fifth run with that note)**, **fullstack-bookmarks 6 (8/8, 7/7; delivered with cuts: AC-4 deferred on a locked test that could not pass, AC-14; 114 min, mixed, mutation 0.50)**.
- Scored 2026-11-22: **notes-api-csharp 14 (9/9, 8/8; delivered, mutation 0.42, redundant reads 55%), wordstats-cli 6 (8/8, 6/6; delivered, mutation 0.80, tool failures 14.5%)**, **notes-api-java 10 (9/9, 8/8; delivered, 123 min, mutation 0.63; file-store data-folder start cause cleared by the fixers with LF.1206)**, **web-todo-react 4 (10/10, 6/6; delivered, 63 min, mutation 0.33; one own unit test shipped failing)**, **fullstack-bookmarks 5 (8/8, 6/7; delivered, 147 min; LF.1223 fixed the typed-markup quality test)**, **notes-api-go 11 (9/9, 6/8; delivered with cuts: AC-16 an aggregate criterion deferred; 73 min, mutation 0.80)**, **notes-api-php 11 (9/9, 8/8; delivered, 70 min, mutation 0.50; PSR-17 factory start failure, LF.1224)**, **fullstack-bookmarks 4 (8/8, 5/7; delivered with cuts: AC-14, AC-3 deferred; 210 min; page double-escaped titles, LF.1223)**, **tasks-api 13 (10/10,
  7/7; delivered with cuts: AC-1 deferred on a shared-store test; 143 min; LF.1208 and LF.1216 closed two defects)**, **notes-api-ruby 5 (9/9, 8/8; delivered,
  60 min, mutation 1.0)**, **notes-api-csharp 13 (9/9, 8/8; delivered with cuts: AC-10/AC-11 deferred on suite tests that cannot pass; 85 min,
  mutation 0.90)**, **textkit-lib 7 (8/8, 7/7; delivered, 16 min,
  mutation 1.0; no unread-lines finding: LF.1221 verified)**, **textkit-lib 6 (8/8, 7/7; delivered, 20 min, mutation 1.0)**,
  **notes-api-java 9 (9/9, 8/8; delivered, 76 min, mutation 1.0), textkit-lib 5 (8/8, 7/7; delivered, 24 min, mutation 1.0)**,
  **wordstats-cli 5 (8/8, 6/6; delivered, 47 min, mutation 0.67)**, **notes-api-go 10 (9/9, 8/8; delivered,
  60 min; flat layout again), notes-api-php 10 (9/9, 8/8; delivered, 91 min,
  mutation 0.70; Slim not-found loop again)**. Scored 11-21: **notes-api-go 9 (9/9, 8/8; delivered, 37 min; LF.1217 + LF.1218 live: flat package layout)**, **tasks-api 12 (10/10, 7/7; delivered, 104 min, mutation 0.83)**, **notes-api-go 8 (9/9,
  7/8; not deliverable: DR-7 left open; 33 min; LF.1217 chose the Go pack)**, **tasks-api 11 (10/10,
  7/7; not deliverable: AC-18/AC-21 deferred on a suite test counting shared rows; 214 min; LF.1213, LF.1214, LF.1216)**, **notes-api-go 6 (0/9, 0/8; failed,
  58 min: service split into packages the brief did not ask for; LF.1215)**,
  **notes-api-csharp 12 (9/9, 8/8; delivered, 59 min, mutation 1.0; one unit test shipped failing)**, **notes-api-ruby 4 (9/9,
  8/8; delivered, 52 min, mutation 0.46)**, **textkit-lib 4 (8/8,
  7/7; delivered, 21 min; mutation 0.67)**, **web-todo-react 3 (10/10, 6/6; delivered, 62 min; mutation 0.33)**, **wordstats-cli 4 (8/8, 6/6; delivered, 55 min,
  mutation 1.0; eight parallel fixers 45 min)**, **fullstack-bookmarks 3 (8/8, 6/7; delivered,
  147 min; a unit run that never finished read as no output for 100 min, LF.1210)**,
  **notes-api-php 9 (9/9, 8/8; delivered, 103 min; namespace/autoload start failure, LF.1209)**,
  **notes-api-go 5 (9/9, 8/8; delivered, 77 min; redundant reads 30%)**, **tasks-api 10 (10/10, 6/7; delivered,
  98 min; LF.1208 closed a 45-minute concurrent-write defect in one attempt)**, **notes-api-java 8 (9/9, 8/8; delivered,
  117 min; LF.1206+LF.1207 turned Java 7's failure into a delivery)**, **notes-api-csharp 11 (9/9, 8/8; delivered, 48 min; one vacuous AC-18 test)**, **notes-api-php 8 (9/9, 8/8; delivered, 94 min,
  mutation 0.25; LF.1205)**, **notes-api-java 7 (2/9, 2/8; failed: start error hidden by Playwright ignoring stdout, then 500s; LF.1206)**, web-todo 3 and 4 (10/10, 6/6), Ruby 2 and 3 (9/9, 8/8; 64 and 56 min against 267 before), Java 3 (9/9, 8/8),
  PHP 6 and 7 (9/9, 8/8; 42 and 78 min), C# 7 and 8 (9/9, 8/8), Java 4 (9/9, 8/8; 244 min, a start defect for three rounds), tasks-api 6 (10/10, 7/7; 110 min;
not deliverable: one edge-probe 500 left), **textkit-lib 3 (8/8, 7/7; delivered, 14 min), notes-api-java 6 (9/9, 8/8; delivered, 94 min), wordstats-cli 3 (8/8, 6/6; delivered, 23 min, mutation score 1.0), notes-api-csharp 10 (9/9, 8/8; delivered, 92 min, 4 fixes reverted), notes-api-java 5 (9/9, 8/8; delivered, 178 min, identical calls 36%), fullstack-bookmarks-py 1 (8/8, 7/7; delivered, 90 min; fix-order arm 3), web-todo 5 (10/10, 6/6; not deliverable on a 347px sideways overflow at 360px; 82 min; fix-order arm 2), notes-api 2 (9/9, 8/8; delivered, 119 min, mutation score 0), ,
  fullstack-bookmarks 2 (8/8, 6/7; delivered, 107 min; fix-order arm 1), **web-todo-react 1 (9/10, 6/6; not deliverable, false acceptance: four criteria deferred, 364 min on :1234)**, web-todo-react 2 (10/10, 5/6; delivered, 73 min), ,
  tasks-api 9 (10/10, 7/7, delivered, 136 min; QA trim shows no saving), notes-api-go 4 (9/9, 8/8, delivered, 51 min; `go.mod` lowered to 1.21, LF.1199), tasks-api 8 (10/10, 7/7, delivered, 83.5 min; prompt-size switches' second arm), ,
  notes-api 1 (9/9, 8/8, delivered, 70 min), fullstack-bookmarks 1 (8/8, 7/7; not deliverable on a false contract blocker being fixed; 289 min, 2.5 h on an unpassable test LF.1196 now catches), ,
  tasks-api 7 (10/10, 7/7, delivered; the suite-repair bugs found and fixed in it), C# 9 (9/9, quality 6/8; not deliverable: probe-found 500s merged under a unit-test defect; fixed in LF.1186)**, Go 3 (9/9, 8/8), tasks-api 5 (10/10, 7/7; 175 min).
  **Java 2 failed 0/9** (never started: an invented "SQLite via H2" mode; LF.1145-1147 fixed the evidence and the ceiling).
- Every local family scored full hidden marks today except Rust (0/9 in four local runs; Haiku-built 9/9 twice).
- Each run's product review: `reports/product-reviews/`.

## Next actions
1. Score the live runs when they finish (full run id), update this file, write the end-of-run review to `reports/product-reviews/`,
   start the next family on each port through the gated start (`ready` must print ALL READY).
2. Internet lookups: WL.3-WL.7 built (`WEB_LOOKUP_WHEN_STUCK`, `WEB_TOOLS_AFTER_TWO_FAILED_FIXES` off, measured per run)
   (`docs/improvement-plan.md` 3.1). Owner action: enter a free Stack Apps key and a no-scope GitHub token on /admin (Lookup keys); a paid key optional.
   Web tools ON for every run (owner 2026-11-23: `WEB_LOOKUP_WHEN_STUCK`, `WEB_TOOLS_OFFERED`, `WEB_TOOLS_AFTER_TWO_FAILED_FIXES`, new-run form default "always"); measured from here, medium and high briefs not counted.
3. Workspace view: WS.1-WS.5 and WS.7 built (LF.1164-1181); next WS.6 take over (last, a service, measured): `docs/improvement-plan.md` 3.2.
   Preview trials: the second real-Docker trial passed (`reports/audits/2026-11-20-preview-real-docker-trial.md`); next a supervised
   trial through the run page with `PRODUCT_PREVIEW` on.
4. Backlog (plan 3.3): stack-decision check
   for a database named as one engine "via" another; the restart re-read pattern; Rust routing (owner).
5. Per-role audit done (`reports/audits/2026-11-20-per-role-audit.md`); sure fixes deployed (LF.1176-1179), doubtful ones built behind
   switches (LF.1182) for a measuring pair. Open: the read guard returned an unchanged file in full after a notice (Java 4; check against history trimming).

## Rules that are never optional
`AGENTS.md`. In short: the model is the owner's (`loop.sh ready` must say ALL READY); fixes are stack-agnostic
(packs, `plugins/seed.py`, per-language tables); every fix has a test proven failing on the old code; both suites
green; commit and push after every change (`git push main harness-hardening-session`); no secrets printed; the
operator account only (`docs/HANDOVER.md`, "Accounts, access and the operator login"); times in JST; reports in
`reports/`; this file and `docs/PRODUCT.md` updated in the same commit as the change; nothing left uncommitted.
