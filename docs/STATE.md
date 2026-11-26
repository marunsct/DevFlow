# State of the loop
The one file every session reads first (plan MF.6): what is live, what is running, the last runs, the next action.
At most 150 lines and 16,000 characters, rewritten, never appended. Updated in every commit that changes any of those;
the block below is written by `loop.sh state`. The map of all documents is `docs/README.md`; open work is
`docs/improvement-plan.md`; how the product works is `docs/PRODUCT.md`; how to run and test it is `docs/HANDOVER.md`;
decisions in force are `docs/owner-decisions.md`; old information is found through `docs/ARCHIVE.md`.
<!-- state:generated -->
**As of:** 11-27 06:10 JST (written by `loop.sh state`). Harness e3867632 committed; e3867632 deployed.
**Live, and stopped in the last day:** run-f6502d06 running at defect_fix_2_2; run-e3acafda running at acceptance_author_1; run-c13e7189 paused at awaiting_approval:defect_fix_2_2; run-e799301e failed at failed; run-7259e30d failed at ?; run-17098b4b failed at awaiting_approval:specialist_testing_1
**Last scored:** run-5071b7ef web-todo-react 10/10 (completed, handoff 1.0; scored 11-26 18:03 JST); run-a79c55df notes-api-go 9/9 (completed, mixed, 77 active min, handoff 1.0; scored 11-26 13:54 JST); run-6c1444a0 tasks-api 10/10 (completed, mixed, 140 active min, handoff 1.0; scored 11-26 11:19 JST).
<!-- /state:generated -->

## Live now
| | |
|---|---|
| Phase | **Learning runs, fixes deployed at once** (deep-review plan, owner 11-18: implement all; frozen-version measuring for Measure batches). The release-candidate count starts only when a full audit cycle finds nothing to fix. |
| Models | olla `host.docker.internal:4001/olla/openai/v1`, model `qwen3.6-35b-a3b` (the owner's; two llama.cpp instances, 93K-token slots). Runs pinned to it. |
| Harness | e386763 deployed 11-27 06:10 JST: LF.1503-1589 (LF.1589: a browser suite that cannot finish is given a short per-test limit before anything is built, and a timed-out run is not repeated under another spelling). Latest for the owner's model under test, inkling-2-mini (olla, 2 slots over 2 llama.cpp instances): LF.1576 sessions spread calls over both servers, LF.1577-1578 re-read loop bounded and a writer's step limit settles, LF.1579 a balancer's capacity summed, LF.1580-1587 reasoning control and registry fixes, LF.1588 a reasoning budget measured by where reasoning stops (enforced and usable on this model; REASONING_BUDGET on). Runs: L notes-api-hono 17 (run-f6502d06), L web-todo (inkling) 1 (run-e3acafda). Medium 5 (Qwen) failed on the fixed loop, not resumed; the bookmarks run paused by the owner. Left in the plan: PA.10, PA.13, PA.18, PA.4 repair, measurements. |
| Switches | 53 fixes built in (always on). 29 optional switches (9 groups, `docs/measuring.md`); `WEB_LOOKUP_WHEN_STUCK` is off and set per run. Measure arms use `SWITCHES_OFF` per run. |
| Operations | Nightly backups (`loop.sh backup --check`). **One model endpoint since 11-25 ~17:45 JST** (owner): olla `host.docker.internal:4001/olla/openai/v1` over two llama.cpp instances, model `qwen3.6-35b-a3b`, 4 requests at once; **at most 2 runs, each in parallel execution mode** (owner 17:54: test the parallel mode; `.env` `MAX_CONCURRENT_RUNS=2`). :8888 and :1234 are gone. Audit cron `0a7ebf80` every 15 minutes. |
| Suites | both green at 22,765 passed on e386763 (11-27 06:08 JST), at SUITE_WORKERS=2. |

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
- **Bundle 2 deployed 15:09 JST 11-24 (7aa2e97; LF.1266, LF.1268-1272):** a foundation smoke before the suite's failures are
  fixed, a limit the specification adds reconciled with the suite before the lock, the suite written and locked a sprint at a time
  (thorough runs and fast runs past 20 criteria), a fixer's request with fresh evidence sized to its defect and its last call kept for a
  write, a fix that stops the product repaired forward before a revert, progress read from where tests fail.
- **LF.1273 deployed 15:53 JST 11-24 (f8d644c):** a kept-when-empty probe - where the brief names the fields refused empty, the
  record's other text fields are kept when empty (the hidden deleted-twice test lost in 5 notes-api families on an empty body refused).
- **LF.1274 deployed 16:09 JST 11-24 (b34052a), LF.1275 16:15 (a29f64a):** one input budget per request - the rewrite path's fix request
  sized like the agent loop's; every other stage's memory cut behind `REQUEST_BUDGET_FOR_EVERY_STAGE` (off; `docs/measuring.md` M17,
  its would-be cuts recorded). LF.1275: a sentence limiting two routes limits each (the medium rerun's sign-ups were missed).
- **LF.1276-1277 deployed 16:55 JST 11-24 (1576e3b; the three Rust packs scaffold):** a run stopped mid-drafting or mid-rewrite ends the stage instead of leaving its
  files to the loop; every Rust pack has cargo choose the crate releases its toolchain builds (`.cargo/config.toml`,
  `incompatible-rust-versions = "fallback"`) - a likely root cause of Rust's 0/9: rustc 1.85 met crates needing 1.86-1.88.
- **LF.1278-1289 deployed 11-24 17:21-22:56 JST:** Rust pack faults answered (sqlx macros, crate exports from source), a forward repair may
  rewrite the start error's file, reviews, the lead and the suite author hold the files they judge (re-read loop, `reports/audits/2026-11-24-*`).
- Scored 2026-11-25: **notes-api-go 13 (9/9, 8/8; delivered, 63 min; a stuck lookup closed by the next fix, HK.4)**, **wordstats-cli 17 (6/8, 6/6; delivered - a false acceptance: "The 3" printed where the brief compares in lower case, LF.1317)**, **fullstack-bookmarks 15 (8/8, 7/7; delivered, 3 h 24 min - unit tests sharing one store, LF.1316)**, **tasks-api 24 (10/10, 7/7; delivered, 94 min; HK.6 advisories asked)**, **notes-api-java 12 (9/9, 8/8; not deliverable - 4 own unit tests failing, locked 15/16)**, **notes-api-csharp 16 (9/9, 8/8; delivered, 40 min - the first with stack facts; the empty-body probe asked 3)**, **notes-api-rust 4 (9/9, 7/8; delivered, 58 min - the second local Rust pass; a body limit the spec added, LF.1298)**.
- Scored 2026-11-24: **notes-api-hono 11 (9/9, 8/8; delivered, about 51 min active; the empty body kept - LF.1283 for the probe that asked nothing)**, **notes-api-rust 3 (9/9, 8/8; delivered, 74 min - the first local Rust pass, after LF.1277; three fixes reverted, LF.1282)**, **notes-api-rust 2 (0/9, 0/8; failed: never built - rustc 1.85 vs newer crates, then sqlx macros and three one-line faults, LF.1277-1279)**, **notes-api-js 1 (9/9, 7/8; delivered, 50 min, mixed; an empty body refused - the fifth family with that loss, LF.1273 building)**, **web-todo 6 (10/10, 6/6; delivered, 57 min, mixed; a unit test set aside, the sprint accepted at an escalation)**, **textkit-lib 9 (8/8, 7/7; delivered in 18 min)**, **notes-api-go 13 (9/9, 7/8; not deliverable: a false check finding kept a right suite in repair until the budget ran out - LF.1256/1267)**,
  **notes-api-java 11 (9/9, 8/8; delivered with cuts: AC-18; the :8888 server was down 6 h 47 min)**, **wordstats-cli 7 (6/8, 6/6; delivered, 36 min; "The 3" where words are compared in lower case - LF.1255)**,
  **notes-api-ruby 6 (9/9, 6/8; delivered, 72 min; delete-twice and a long body lost - LF.1254 building)**,
  **notes-api-php 12 (9/9, 7/8; not deliverable: a blank title answered 500, left open two attempts - LF.1252; 117 min)**,
  **fullstack-bookmarks 8 (8/8, 7/7; delivered, 66 min, mutation 0.73)**, **tasks-api 15 (10/10, 7/7; delivered, 3 h 7 min, mutation 0.36; the probes signed in and reached every write - LF.1242/1249)**,
  **web-todo-react 5 (10/10, 6/6; delivered, 66 min, mutation 0.58)**, **notes-api-csharp 15 (9/9, 8/8; delivered, 78 min, mutation 1.0; NU1202 from a lookup offering EF Core 11 on net8.0, LF.1248)**.
- Scored 2026-11-23 and earlier: in `reports/product-reviews/`.
- Every local family has scored full hidden marks; Rust first did on 11-24 (container 3) after four 0/9 runs.
- Each run's product review: `reports/product-reviews/`.

## Next actions
0a. **HK plan, all phases (owner 23:45 JST 11-24): built and deployed by 02:44 JST 11-25** - LF.1291-LF.1309 (HK.1-HK.12, KS.1-KS.7, the
   stale-knowledge trap family and replay fixtures); doubtful items behind switches, off (HK.7, HK.9, HK.10, `STUCK_LOOKUP_CONDENSED`,
   `WEB_TOOLS_BY_MEASURED_TIER`). Also LF.1310 (a tester's refused product change kept as its blocker). LF.1311
   (the brief's release line wins over a pack's pin) and LF.1313 (an editable install is not a package) deployed 03:20 JST; packs:
   java-spring-api and @4 scaffold, node-nest-api scaffolds, node-nest-api@12 does not (ESM; a 12 brief falls back to 11 and says so).
   LF.1312 (a unit test's stand-in hides a rule) deployed 04:29 JST; LF.1314 (a leading `NAME=value` answered plainly) and LF.1315 (sprints
   sized by work: at most 6 criteria, an empty or oversized sprint sent back once, then split) deployed 05:32; LF.1316 (unit tests that share
   one store shown the leaked records; actual values kept in the defect listing) deployed 07:56; LF.1317 (a group compared in a normal form
   is reported in it) deployed 09:05. Owner: a GitHub token.
0b. **Owner 11-25:** thorough delivery resolves every blocking/major/critical/high design finding before development (LF.1318, a person
   decides past 6 revisions, even on benchmark runs); review findings organised into waves A-E (`docs/improvement-plan.md` 3.0), A and B
   built 11-25. **Medium 3 (run-bc3cbd00) failed 10:27 JST** in sprint 3's suite authoring (no answer, no fallback; LF.1365 builds one),
   9 of 13 criteria, quality 31: `reports/product-reviews/2026-11-25-medium-3.md`. **Medium 4 live: run-32362f3b** (thorough, :1234,
   started 11:25 JST): design approved at review 6 (13:0x JST), all 17 gating findings resolved in the review rounds (DR-7 to DR-23),
   criteria 13 -> 16 (interface, migrations, Docker; DR-26), 3 sprints with every adopted item placed (2 declined). Watch: sprint 1
   carries 29 adopted items; PA.2/PA.12's reads in the later suite writers.
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
