# State of the loop
The one file every session reads first (plan MF.6): what is live, what is running, the last runs, the next action.
At most 150 lines and 16,000 characters, rewritten, never appended. Updated in every commit that changes any of those;
the block below is written by `loop.sh state`. The map of all documents is `docs/README.md`; open work is
`docs/improvement-plan.md`; how the product works is `docs/PRODUCT.md`; how to run and test it is `docs/HANDOVER.md`;
decisions in force are `docs/owner-decisions.md`; old information is found through `docs/ARCHIVE.md`.
<!-- state:generated -->
**As of:** 11-20 10:58 JST (written by `loop.sh state`). Harness 8c2f5de1 committed; 55975edc deployed (not the same).
**Live, and stopped in the last day:** run-b668a924 running at defect_fix_2_2; run-d2d6fd42 running at defect_fix_2_2; run-e382df47 failed at failed; run-eaed36e7 failed at failed
**Last scored:** run-aa3693b6 notes-api-php 9/9 (completed, 78 active min, handoff 1.0; scored 11-20 09:33 JST); run-09fc4306 web-todo 10/10 (completed, mixed, 124 active min, handoff 1.0; scored 11-20 08:43 JST); run-62a7d976 notes-api-ruby 9/9 (completed, mixed, 56 active min, handoff 1.0; scored 11-20 08:03 JST).
<!-- /state:generated -->

## Live now
| | |
|---|---|
| Phase | **Learning runs, fixes deployed at once** (deep-review plan, owner 11-18: implement all; frozen-version measuring for Measure batches). The release-candidate count starts only when a full audit cycle finds nothing to fix. |
| Models | :8888 `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` (key); :1234 `qwen3.6-35b-a3b-mtp@iq4_nl` (no key). Both the owner's; both take runs; each run is pinned to its port. |
| Harness | Deploying 11-20 11:27 JST: LF.1160 (the Spring pack holds the jar name), LF.1161 (WL.7: `ready` asks each lookup source live), LF.1162 (a mutant's test run cut off at 3x the normal run), the docs consolidation and the `WEB_LOOKUP_WHEN_STUCK` registration. Merged, suites running, deploy next: LF.1163 mutation gaps to one fixer (`MUTATION_GAPS_BUNDLED`, off), LF.1164 WS.3 steering (read by / edit / withdraw / three levels), LF.1165 WS.1 Workspace tab. Building in a worktree: WL.3. |
| Switches | 53 fixes built in (always on). 29 optional switches (9 groups, `docs/measuring.md`); `WEB_LOOKUP_WHEN_STUCK` is off and set per run. Measure arms use `SWITCHES_OFF` per run. |
| Operations | Nightly backups (`loop.sh backup --check`); finished runs older than 60 days cleared. Audit cron `01339d0d` every ~10 minutes (7-day expiry: recreate by 11-27). |
| Suites | `loop.sh suite` and `loop.sh suite-production` both green at 18,701 passed. |

## Off until measured
`WEB_LOOKUP_WHEN_STUCK` (internet lookups for a stuck fixer: needs 2 runs on, 2 off). BATCH_ACCEPTANCE_AUTHOR. Hosted-model
runs only when the owner starts them. Everything under measurement: `docs/improvement-plan.md` section 2.

## The last three runs (11-20, hidden / quality; local model)
Earlier runs: `reports/status-board/`, git history of this file.
- **Live:** notes-api-csharp container 8 (:8888) in fix rounds at 18/18 criteria; notes-api-java container 4 (:1234) at 0/18,
  two fixers alternating on its start (checked each audit).
- Scored today: web-todo 3 and 4 (10/10, 6/6), Ruby 2 and 3 (9/9, 8/8; 64 and 56 min against 267 before), Java 3 (9/9, 8/8),
  PHP 6 and 7 (9/9, 8/8; 42 and 78 min), C# 7 (9/9, 8/8), Go 3 (9/9, 8/8), tasks-api 5 (10/10, 7/7; 175 min).
  **Java 2 failed 0/9** (never started: an invented "SQLite via H2" mode; LF.1145-1147 fixed the evidence and the ceiling).
- Every local family scored full hidden marks today except Rust (0/9 in four local runs; Haiku-built 9/9 twice).
- Each run's product review: `reports/product-reviews/`.

## Next actions
1. Score the live runs when they finish (full run id), update this file, write the end-of-run review to `reports/product-reviews/`,
   start the next family on each port through the gated start (`ready` must print ALL READY).
2. Internet lookups: WL.3 (the user's Off / When stuck / Always setting), then WL.7, WL.4 T2-T4, WL.5, WL.6
   (`docs/improvement-plan.md` 3.1). Owner action: a free Stack Apps key and a no-scope GitHub token; a paid key optional.
   Turn `WEB_LOOKUP_WHEN_STUCK` on for a measuring pair on C#, Java and Rust.
3. Workspace view: WS.3 and WS.1 built (LF.1164, LF.1165); next WS.2 timeline, then WS.4 preview, then the WS.3 remainder (plan gate): `docs/improvement-plan.md` 3.2.
4. Backlog (plan 3.3): contested tests past their repair cap; stack-decision check
   for a database named as one engine "via" another; the restart re-read pattern; Rust routing (owner).
5. Open audit item: the per-role audit (suite writers, technical lead, prompts per role) is unfinished; its report goes to
   `reports/audits/`.

## Rules that are never optional
`AGENTS.md`. In short: the model is the owner's (`loop.sh ready` must say ALL READY); fixes are stack-agnostic
(packs, `plugins/seed.py`, per-language tables); every fix has a test proven failing on the old code; both suites
green; commit and push after every change (`git push main harness-hardening-session`); no secrets printed; the
operator account only (`docs/HANDOVER.md`, "Accounts, access and the operator login"); times in JST; reports in
`reports/`; this file and `docs/PRODUCT.md` updated in the same commit as the change; nothing left uncommitted.
