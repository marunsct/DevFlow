# State of the loop
The one file every session reads first (plan MF.6): what is live, what is running, the last runs, the next action.
At most 150 lines and 16,000 characters, rewritten, never appended. Updated in every commit that changes any of those;
the block below is written by `loop.sh state`. The map of all documents is `docs/README.md`; open work is
`docs/improvement-plan.md`; how the product works is `docs/PRODUCT.md`; how to run and test it is `docs/HANDOVER.md`;
decisions in force are `docs/owner-decisions.md`; old information is found through `docs/ARCHIVE.md`.
<!-- state:generated -->
**As of:** 11-24 14:25 JST (written by `loop.sh state`). Harness 23ddd869 committed; d75ddbcf deployed (not the same).
**Live, and stopped in the last day:** run-972956f5 running at acceptance_author_0; run-8f0be29e failed at failed
**Last scored:** run-88549ebb textkit-lib 8/8 (completed, handoff 0.833; scored 11-24 14:25 JST); run-127780fe notes-api-go 9/9 (completed, mixed, 108 active min, handoff 0.857; scored 11-24 14:15 JST); run-eded4941 notes-api-java 9/9 (completed, mixed, 0 active min, handoff 1.0; scored 11-24 14:07 JST).
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
BATCH_ACCEPTANCE_AUTHOR (web tools are on since 11-23, measured from there). Hosted-model
runs only when the owner starts them. Everything under measurement: `docs/improvement-plan.md` section 2.

## The last three runs (11-20, hidden / quality; local model)
Earlier runs (11-22 and before): `reports/product-reviews/`, `reports/status-board/`, git history of this file.
- **Live (11-24 14:20 JST):** run-031094d4 `L notes-api-js container 1` on :8888 (14:26 JST) and run-972956f5 `L web-todo container 6` on :1234 (14:05 JST; both ports
  after both ports sat idle 10:55-14:04 while the Opus usage limit stopped the audit and the build agents).
- **Deployed 11-23/24:** LF.1227-LF.1256, each in `docs/archive/plans/fix-log.md`; the largest: builders and reviews on written code hold that code
  (LF.1232/1233/1236), the release probes sign in and read the contract from the criteria (LF.1242/1249), a fix round starts with its round's defects
  (LF.1244), full-stack packs carry their service's known errors (LF.1245), cannot-pass checks for own-record picks and whole-list counts (LF.1237/1246),
  a round-trip probe (LF.1254), `LONG_REASONING_BEFORE_A_READ` on and measured (LF.1238/1247), stale command containers stopped at worker start (LF.1250).
  Web tools on for every run (LF.1234, owner 11-23).
- **Bundle 1 of the scale review deployed 11-24 (LF.1257-1265, LF.1267):** the fix cursor, the time budget read inside the attempt,
  one cause from the first failing step, no closing on a claim, the step limit goes on from its checkpoint, unit tests kept where their runner
  collects them and a zero-test gate, no deferral past a foundation, due-only suite runs, a repair whose finding no longer holds settled.
- Scored 2026-11-24: **textkit-lib 9 (8/8, 7/7; delivered in 18 min)**, **notes-api-go 13 (9/9, 7/8; not deliverable: a false check finding kept a right suite in repair until the budget ran out - LF.1256/1267)**, **notes-api-java 11 (9/9, 8/8; delivered with cuts: AC-18; the :8888 server was down 6 h 47 min)**, **wordstats-cli 7 (6/8, 6/6; delivered, 36 min; "The 3" where words are compared in lower case - LF.1255)**, **notes-api-ruby 6 (9/9, 6/8; delivered, 72 min; delete-twice and a long body lost - LF.1254 building)**, **notes-api-php 12 (9/9, 7/8; not deliverable: a blank title answered 500, left open two attempts - LF.1252; 117 min)**, **fullstack-bookmarks 8 (8/8, 7/7; delivered, 66 min, mutation 0.73)**, **tasks-api 15 (10/10, 7/7; delivered, 3 h 7 min, mutation 0.36; the probes signed in and reached every write - LF.1242/1249)**,
  **web-todo-react 5 (10/10, 6/6; delivered, 66 min, mutation 0.58)**, **notes-api-csharp 15 (9/9, 8/8; delivered, 78 min, mutation 1.0; NU1202 from a lookup offering EF Core 11 on net8.0, LF.1248)**.
- Scored 2026-11-23: **fullstack-bookmarks 7 (8/8, 6/7; not deliverable: AC-8, AC-15, AC-17 deferred on page tests counting a shared list, LF.1246; 186 min)**, **notes-api-go 12 (9/9, 8/8; delivered, 48 min, mutation 0.89; LF.1242's probes reached every write)**, **tasks-api 14 (10/10, 5/7; delivered with cuts: AC-21; 63 min; blank title and concurrent creates lost - the release probes never signed in, LF.1242)**, **textkit-lib 8 (8/8, 7/7; delivered from the first draft in 10 min, mutation 1.0)**, **notes-api-rust 1 (9/9, 8/8; delivered, 97 min, mixed, mutation 0.50; one own unit test shipped failing - the fifth run with that note)**, **fullstack-bookmarks 6 (8/8, 7/7; delivered with cuts: AC-4 deferred on a locked test that could not pass, AC-14; 114 min, mixed, mutation 0.50)**.
- Every local family scored full hidden marks today except Rust (0/9 in four local runs; Haiku-built 9/9 twice).
- Each run's product review: `reports/product-reviews/`.

## Next actions
0. **Scale review (owner 11-24): `reports/audits/2026-11-24-why-medium-briefs-fail.md`** - bundle 1 (seven loop bugs) building; then bundle 2
   (foundation smoke, due-only suite, fair judging of a fix), bundle 3 (input budget, sprint sizing). Owner to decide: per-sprint suite lock, a scored
   medium benchmark. **Owner 11-24: rerun the medium brief once bundles 1 and 2 are deployed** (the same upload, `brief_medium.md`, run name
   Medium, on :1234 as before; the first run was `thorough` delivery).
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
