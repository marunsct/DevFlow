# State of the loop
The one file every session reads first (plan MF.6): what is live, what is running, the last runs, the next action.
At most 150 lines and 16,000 characters, rewritten, never appended. Updated in every commit that changes any of those;
the block below is written by `loop.sh state`. The map of all documents is `docs/README.md`; open work is
`docs/improvement-plan.md`; how the product works is `docs/PRODUCT.md`; how to run and test it is `docs/HANDOVER.md`;
decisions in force are `docs/owner-decisions.md`; old information is found through `docs/ARCHIVE.md`.
<!-- state:generated -->
**As of:** 11-21 04:43 JST (written by `loop.sh state`). Harness 0b5335ba committed; d29ff5a8 deployed (not the same).
**Live, and stopped in the last day:** run-426163d2 running at acceptance_review_3
**Last scored:** run-42484a4f web-todo 10/10 (completed, handoff 1.0; scored 11-21 04:43 JST); run-a6b50450 notes-api 9/9 (completed, 119 active min, handoff 1.0; scored 11-21 04:03 JST); run-8808daaa fullstack-bookmarks 8/8 (completed, 108 active min, handoff 1.0; scored 11-21 03:13 JST).
<!-- /state:generated -->

## Live now
| | |
|---|---|
| Phase | **Learning runs, fixes deployed at once** (deep-review plan, owner 11-18: implement all; frozen-version measuring for Measure batches). The release-candidate count starts only when a full audit cycle finds nothing to fix. |
| Models | :8888 `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` (key); :1234 `qwen3.6-35b-a3b-mtp@iq4_nl` (no key). Both the owner's; both take runs; each run is pinned to its port. |
| Harness | Deployed 11-20 23:19 JST: d29ff5a8 (LF.1140-1201; LF.1201 off). Deploying after both suites: LF.1202 a repeat read is told so only while the model can still see the text. |
| Switches | 53 fixes built in (always on). 29 optional switches (9 groups, `docs/measuring.md`); `WEB_LOOKUP_WHEN_STUCK` is off and set per run. Measure arms use `SWITCHES_OFF` per run. |
| Operations | Nightly backups (`loop.sh backup --check`); finished runs older than 60 days cleared. Audit cron `01339d0d` every ~10 minutes (7-day expiry: recreate by 11-27). |
| Suites | `loop.sh suite` and `loop.sh suite-production` both green at 18,701 passed. |

## Off until measured
`WEB_LOOKUP_WHEN_STUCK` (internet lookups for a stuck fixer: needs 2 runs on, 2 off). BATCH_ACCEPTANCE_AUTHOR. Hosted-model
runs only when the owner starts them. Everything under measurement: `docs/improvement-plan.md` section 2.

## The last three runs (11-20, hidden / quality; local model)
Earlier runs: `reports/status-board/`, git history of this file.
- **Live:** notes-api-java container 5 (:1234, from 04:05); fullstack-bookmarks-py container 1 (:8888, from 04:49, `FIX_ORDER_CRITERIA_FIRST` on).
- Scored today: web-todo 3 and 4 (10/10, 6/6), Ruby 2 and 3 (9/9, 8/8; 64 and 56 min against 267 before), Java 3 (9/9, 8/8),
  PHP 6 and 7 (9/9, 8/8; 42 and 78 min), C# 7 and 8 (9/9, 8/8), Java 4 (9/9, 8/8; 244 min, a start defect for three rounds), tasks-api 6 (10/10, 7/7; 110 min;
not deliverable: one edge-probe 500 left), **web-todo 5 (10/10, 6/6; not deliverable on a 347px sideways overflow at 360px; 82 min; fix-order arm 2), notes-api 2 (9/9, 8/8; delivered, 119 min, mutation score 0), ,
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
   Turn `WEB_LOOKUP_WHEN_STUCK` on for a measuring pair on C#, Java and Rust.
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
