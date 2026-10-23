# Handover - the harness improvement loop

**Written for:** any coding agent (or person) taking over the loop, with none
of the previous sessions' context. Last updated **2026-10-18 18:40 JST**.


Read this file first, then `docs/monitoring-handover.md` §0 (the mechanics and
the full gate history), §0.4.1 (the product audit checklist), §0.7 (how a
sprint runs) and §0.9 (where a run's time goes). `AGENTS.md` at the repo root
points here.

The previous agent's private notes (Claude Code's memory) do not travel.
Everything they held that is not a secret is in this file.

**Documentation map (consolidated 2026-10-19; one file per topic).**

| Topic | File |
|---|---|
| Product brief: what DevFlow is, how it works, feature status | `docs/PRODUCT.md` |
| Architecture decisions and the reasons for them (ADR-0001…0011) | `docs/architecture-decisions.md` |
| Agent handover: start here, the standing instruction, where it stands | `docs/HANDOVER.md` (this file) |
| Testing, auditing and improvement-loop handover, with every script | `docs/monitoring-handover.md` |
| Unified improvement plan, with the master index and the ledger | `docs/improvement-plan.md` |
| Research findings, each linked to plan items | `docs/research-findings.md` |
| Review findings (evidence), each linked to plan items | `docs/review-findings.md` |

`docs/ui/` holds the theme screenshots that the UI parts of the plan refer
to. The older files were merged into these on 2026-10-19:
- `harness-improvement-plan.md` and
  `high-steering-software-company-implementation.md` became improvement plan
  section E;
- `redesign-software-company.md` became ADR-0005;
- `review-findings-wip.md` and the session-4 review became
  `review-findings.md`;
- the research parts became `research-findings.md`.

**2026-10-18:** the implementation phase for the deep-review appendix of
`docs/improvement-plan.md` (Initiatives J–V + addenda, P0→P3) has started.
Per-item status lives in the *Implementation Progress Ledger* at the end of
that document and is updated in the same commit as every implementation
change. Evidence archive for the review: `docs/review-findings.md`.

**2026-10-18 18:40 JST:** Appendix 2 (second review) of the same document is
being implemented in its resume order (`docs/review-findings.md` §13.8):
the whole resume order is done - X.1/X.2, AD, AE, W.3, W.1, W.4, W.5 (ledger
rows "Appendix 2 rows"). W.2 baseline runs are the owner's. New: `loop.sh kpi`
(run by every `loop.sh score`) keeps each run's KPIs in `data/kpi/` and flags
regressions; a score against another brief's hidden suite is marked
`brief_mismatch` and kept out of the false-acceptance count. Deep analysis 18:45 JST of the medium run added
two general fixes (unserved code named to fixers and at release; memory
pointers count toward withholding the read tool) - see monitoring §0.
Two sessions share this tree: one drives deploys/starts/cancels, the other
sends pushed commits; announce a suite run before starting it.

## 0. Your first ten minutes

The owner's direction (2026-10-12): test on **`tests/brief_medium.md`**, in
**parallel** execution mode first and linear mode after; a run taking unusually
long is cancelled, improved, deployed and started again. Check what is live
before anything else:

```sh
cd /home/arun/Desktop/langchain
git status --short                      # clean (docs/logs.md was removed from git by the owner on 2026-10-19)
export LOOP_USER=harness-test LOOP_PASSWORD=loop-test-only-pw-2026
scripts/loop/loop.sh status             # the current run, and whether anything is live
scripts/loop/loop.sh ready              # last line ALL READY, exit 0 - otherwise start nothing (§5)
scripts/loop/loop.sh start tests/brief_medium.md   # only when nothing is live
scripts/loop/loop.sh wait 10            # every ~10 min for 40 min, then `wait 18`
```

**One-time step after 2026-10-19:** `docs/logs.md` was removed from git. A
working tree that still has local edits to it stops `git pull` ("local
changes would be overwritten"). Keep a copy outside the repository, then
let the pull delete it:

```sh
cp docs/logs.md ~/logs-backup.md && git checkout -- docs/logs.md && git pull main harness-hardening-session
```


Execution mode is a global setting read at every dispatch (`runtime_settings`
`execution_mode`); there is no per-run override. Switching to linear is the
owner's setting change - ask them, never write the settings table.

`loop.sh wait N` blocks for up to N minutes and then prints the status, key
log lines and the audit. Run it so that its output reaches you when it ends:
as a background task your agent is notified about, or in the foreground with
a timeout longer than N minutes. Never detach it with a bare `&` and forget
it. Each time you start a wait, tell the owner the clock time of the next
check **in JST**. Containers and transcripts log UTC; JST = UTC+9.

Then work through §2.2 ("Verify on the next run") as the run goes.

## 1. The standing instruction

The owner wants a loop that **never stops on its own**:

1. Start a run (`loop.sh bench <name>` from `benchmarks/`, or
   `loop.sh start <brief>` for a brief with no hidden tests).
2. Audit it: transcripts, worker logs, the database, tool calls - especially
   failed and unnecessary ones.
3. Fix what you find **technology-agnostically**: the harness must build any
   product in any language or framework. Never fix for one stack, one product
   or one run.
4. Add tests (each proven to fail on the old code) and run the full suite
   (`loop.sh suite`).
5. Commit and push (`git push main harness-hardening-session` - the remote is
   named `main`), deploy (`loop.sh deploy`), and start the next run.

**Gate** (since the 2026-10-03 redesign, `docs/architecture-decisions.md`,
`benchmarks/README.md`). A run is clean when its product scores 100% on its
benchmark's hidden tests (`loop.sh score`), the run needed no harness fix, and
the product audit (monitoring §0.4.1) passes. Any fix resets the current
stage's count. Stages, in order:

1. `web-todo`: two consecutive clean runs.
2. `notes-api`, `wordstats-cli`, `textkit-lib`: one clean run each.
3. `fullstack-bookmarks`: two consecutive clean runs.
4. `tests/brief_medium.md`, then `tests/brief_high.md`, audited by hand.

**Gate:** stage 1 (`web-todo`) passed - run-49dec2db and run-5aadbddd scored
10/10 with no harness fix during them (49dec2db's scaffold was "left to the
agents" over the browser-version mismatch below, and it still scored 10/10).
By the owner's direction the loop now tests `tests/brief_medium.md`, which has no
hidden tests: audit it by hand (§0.4.1 of the monitoring handover).

**Unusually long (owner, 2026-10-12):** a run that stalls - one stage visit over
~30 minutes, a fix loop that keeps reopening the same failure, no sprint
accepted after ~2.5 hours on brief_medium - is cancelled (`loop.sh cancel`),
the cause fixed in general, deployed, and the run started again.

**Early stop.** If you find a bug in a run's first 40 minutes, cancel the run
(`loop.sh cancel`), fix, deploy and start again. If you find a major harness
bug or gap at any time, cancel immediately.

**Shakedown runs (owner 2026-10-22 20:00 JST):** for the first couple of runs with every group 2 switch on, a confirmed harness bug is fixed immediately and the run paused, deployed and rewound to the earliest affected stage - `loop.sh rewind --pause-only; BOUNDARY_WAIT=0 loop.sh deploy; loop.sh rewind <stage>` - whatever the run's age (the 40-minute rule does not apply). Their scores are not arms; the gated runs start once a run passes with no new harness bug. Only a bug that changes the run's outcome or wastes its time is deployed this way; a fix that does not (measurement, log wording, tooling) is pushed and deployed with the next significant one (owner, 20:19 JST).

**Mid-run deploys when defect fixed (owner instruction 2026-10-10 18:45 JST):**

- When a harness defect or bottleneck is caught during a run, implement the fix and test immediately.
- Deploy mid-run (`loop.sh deploy`) and wait for orphan recovery to resume it (`loop.sh resumed`) once the fix is verified (not at an exact scheduled time).
- This ensures the run is not held on the same defect and can be observed through its remaining stages for further defects and improvements.

**Design each batch fully before deploying it.** For each fix:

- trace every other path it touches;
- replay it on the real evidence (the transcript, the workspace's `.harness/`
  files) rather than a made-up fixture;
- fix the cause once, not one symptom per run.

Two lessons behind this rule:

- `38ef971` introduced a regression.
- The sprint-scope fixes (`3b01d8a` → `6ff499e` → `c3a5fca` → `d833edb` →
  `351d1ec`) arrived one run at a time when one design would have done.

**Product audit, every run, at the end.** Run `loop.sh product <run-id>`, then
read every product source file against the brief (monitoring §0.4.1). Check:

- every brief feature is built *and reachable by a user*;
- edge inputs and the brief's constraints;
- that the tests exercise the real code;
- that every claim in the sprint summaries and the milestone review is true.

**After each run:**

1. `loop.sh score <run> web-todo` and `loop.sh product <run>`.
2. Record the run in §2 of this file and in the gate row of monitoring §0.2.
3. Commit and push.
4. Deploy the batch, if there is one.
5. Start the next run.

**Code rules:**

- **No run ids** in code, comments, prompts or tests
  (`tests/test_no_run_ids_in_the_source.py`). The placeholders `deadbeef` and
  `abc12345` are fine. Evidence goes in commit messages, and in docstrings as
  "one run".
- **No language- or framework-specific instructions in code.** They belong in
  `src/app/plugins/seed.py` (the `plugin_instructions` table, injected
  dynamically) or in a stack pack (`src/app/stacks/packs/`).
- **Rules for agents are product-agnostic.** No examples from the test brief,
  and no UI-only words in rules meant for every product. Every new prompt rule
  gets a test that bans the whole words task, tasks, to-do, todo, button,
  click and checkbox (e.g. `tests/test_a_suite_that_asserts_an_unstated_order.py`).
- **Preserve the owner's features:**
  - dynamic agent-instruction injection;
  - the parallel/linear execution toggle;
  - the sprint summary;
  - work orders, document templates and the Sprint Record (monitoring §0.7).

  Fix them where wrong; never remove them.
- **Do not force the model to pick only from pre-existing scaffolds:**
  If the best open-source option for a product's requirements is not in the
  existing scaffolding (`app.stacks.packs`), do not force the model to select a
  non-ideal technological stack. The stack selector chooses the optimal stack
  for the product, and the harness supports and scaffolds open-source stacks
  cleanly. Extend scaffolding to cover known open-source frameworks.
- **Implement only what adds value** (owner, 2026-10-04). That holds for the
  owner's own plans too. Where an existing implementation does not fit the
  product vision (a software-company harness: auto mode decides, approval mode
  asks), replace it rather than patch it. Say which items you drop and why.
- **Use the LangChain docs MCP server** (or the docs site) when changing
  LangChain/LangGraph behaviour.

**Standing permissions and habits:**

- **You may edit any file in the repo, `.env` and `docker-compose.yml`
  included** (owner, 2026-09-28). Back `.env` up first and never print its
  values. Don't wait for the owner's input: make the best decision and keep
  the loop going. The exceptions are the owner's decisions in §7 and the
  model (§5).
- **Commit and push after every change**, handover updates included. Never
  leave the tree dirty between steps.
- **Keep monitoring §0 current in the same commit** as any change to how runs
  are tested: the gate, the cadence, the scripts, the healthy numbers or the
  suite size.
- **When idle and waiting on the owner** (for example a model mismatch), use
  one long passive watcher, not periodic wake-ups. Credits are limited.
- **When the shell fails** for an infrastructure reason (a tool-approval check
  that gives no verdict), stop retrying. Schedule a check about 10 minutes
  later, or tell the owner when you will retry, and resume. Testing comes
  first when it returns: deploy the pending fix and start the next run, then
  commit and push. A failing git step must never stop the testing.

## 2. Where it stands (2026-10-12 13:40 JST)

| | |
|---|---|
| branch | `harness-hardening-session`, pushed to `https://github.com/marunsct/DevFlow.git` (remote named `main`). `docs/PRODUCT.md` describes the whole product. |
| deployed | `d5e6465` deployed 23:24 JST 2026-10-13 into run-c2e62179 (resumed); the rewind-points grouping fix after it is pushed, deploy with the next fix. `verify_packs.py` for the 35 packs has NOT been run in the worker yet - run it when no run is live (`loop.sh nightly` does). |
| current run | `run-77c6650e-042a-4310-bf72-bb819a8f8fee` (low brief `benchmarks/web-todo/brief.md`, fast mode, 100% local model `unsloth/Qwen3.6-35B-A3B-MTP-GGUF`) COMPLETED and released at 00:52 JST 2026-10-18 (82m wall). Acceptance suite: 15/15 passed (100%), unit tests: 38/38 passed (100%), product size: 489 code lines (within 500-line limit). Hidden benchmark score: **10/10 (1.0)**! |
| model | Two tiers set by the owner: build model `qwen3.8-flash-next-coder-iq1_m` (Strata on the owner's `localhost:9090`; reached as `host.docker.internal` with `Host: localhost:9090` - every client must go through `app.models.endpoints.reached_from_here`), frontier (judgement) `qwen3.8-flash` on `https://token-plan.maas.qwencloudapi.com/compatible-mode/v1` (it refuses a forced tool call while thinking - handled). Qwen cloud's free quota ran out on qwen3.8-max(-0902) on 2026-10-13; a quota refusal now parks a run as `waiting_for_budget`. Execution mode **parallel**, `HARNESS_MAX_PARALLEL=6`. |
| Celery limits | soft 43,200 s (12 h), hard 43,500 s - in `tasks.py`, `docker-compose.yml` and `.env.example` (the handover had claimed this before it was done). |
| suite | 9,840+ pass, 29 skip, 3 expected S3 fails (`tests/test_codebase_seeding_api.py`). |

### 2.0000 Owner decisions of 2026-10-18 and what they built (`77289d6`..`c56d166`)

The owner accepted every recommendation (list: `docs/improvement-plan.md`,
"Owner decisions 2026-10-18"). One session is the main driver
(`langchain-63`); the others stay read-only. Built and tested, each with a
test that fails on the old code:

- **Fast mode:** keeps up to 5 of the lead's test files when the plan names
  none. A work order of more than 3 files is split into parts of 3 (soft cap,
  measure over 2 runs).
- **Design tokens (A):** every web pack's stylesheet starts with accessible
  design tokens.
- **Suite strength (AF):** at release, up to 3 deliberate breaks for suites
  that drive no browser; an unnoticed break is a completion gap. Not at lock
  time: the suite locks before the build.
- **Interface contract (C + J.3):** `interface_contract` in the
  specification, in strict lines. It is shown to the acceptance author, kept
  at lock, and compiled into Playwright checks at release; a failure is a gap.
- **Lessons (AI):** `plugins/lessons.py`. Only owner-approved lessons reach a
  prompt. Commands: `lessons.py list|propose|approve|reject`, in the worker;
  list new proposals in each run's report.
- **UI:**
  - a Changes view of the workspace's git history;
  - each criterion opens to its tests;
  - the view lives in the URL;
  - steering: notes in `.harness/steering.json`, added to every later call
    by the instruction middleware.
- **Database (K.2):** a product that stores data defaults to an embedded
  database under `DATA_DIR`.

**Still to do:**
- Remaining plan work: K.6 after the W.2 baselines (Fast notes-api-hono,
  then fast fullstack-bookmarks-py), the UI timeline, and log virtualization.

### 2.000000 Part 21 in progress (2026-10-19, owner: "implement every open item, in Part 21's order")

- **Stage 0 (owner's):** run-846b8d62 cancelled at the owner's choice. W.2 baseline 1, fast
  `notes-api-hono`, run-419b8ff6 (13:48 JST, on the deployed `e608003`): 9/9 hidden tests,
  completed with 3 gaps (the owner paused it 14:25-14:27; read `active_minutes`). AR probe
  14:30 JST: the server honours only thinking on/off (per-request budget +7%, effort low
  +13%, high +18%, thinking off -30%), so AX is not built - advice to the owner in the
  ledger. Baseline 2, fast `fullstack-bookmarks-py`, run-c00868a9: failed 15:53 JST after 5
  acceptance rounds, 0/8 hidden tests (see the plan's W.2 row). Baseline 3, thorough
  `notes-api-hono` (the same bench as baseline 1, so the two modes compare), run-606ff231:
  completed 16:47 JST, 9/9 hidden tests, 46 min. **Stage 0 is done**; stage 1 and the UI kit are
  deployed after it (see monitoring §0 for the deploy time), and its gate runs are brief_medium.
  The model server now reports 2 slots (the owner's change). **Nothing is deployed while a baseline runs**, and stage-1 code waits on
  the branch until every baseline is scored and in `loop.sh kpi`.
- **Stage 1, built on the branch, not deployed:** BF (each request's `blocks`; KPI
  `prompt_block_share_*`, `cache_miss_after_tool_change`); BC (two pointer answers in a row
  stall the stage); BK (a failed release file is a completion gap); AQ step 3 (a window read again is a pointer); AO.9 (a command's result names the files it
  changed). From the baseline-1 analysis: a missing unit report with no unit test file is the
  "ships no unit tests" gap, and a run no review stage read gets a gap; BL (owner's yes): a sprint
  accepted on its suite with no review yet goes through the reviews first, and the custom setup
  is held to the smallest app and to tests its runners collect; a failed setup install names its
  cause, and Python setups are told how a setuptools install names its package; a suite's own
  `run.json` in the wrong shape is refused as written and the send-back names the shape; the custom
  setup writes its declaration first. **Owner, 17:40 JST: group 1 (no before/after runs needed) is
  built first, then the validation runs for group 2** - the list is in monitoring §0. When group 1
  is done: deploy at a stage boundary, let the shakedown run (run-894282e3) finish, then the gate
  run. Done: AO.10, AO.5, K.6/AW (two AW deliverables dropped, premise false), AU, S, B, U.1 (bench `tasks-api`), BH registry, M.5/M.6, Q-amend (off by default), T spike (streaming works now; rollout is group 2), G. Now: the UI track (BG.2 done); AQ steps 1-2 need the baseline KPIs.
- **UI track (owner, 2026-10-19: start it while the baselines run):** UI-P, the component kit in
  `langchain-ui/src/ui/` with `/dev/ui` and `scripts/ui/axe_kit.mjs` (0 violations per theme).
  Not deployed: rebuilding the app restarts it, so UI work ships with group 1. Done since: BG.2
  (the needs-you inbox, tab badge, opt-in notifications; `/api/runs` carries `gate_deadline`) and
  UI-0 (types generated from the server's schema: after any API change run `npm run api:types` in
  `langchain-ui`, or `tests/test_the_ui_s_api_types_are_current.py` fails) and UI-S1/S2 (pages of
  50, the `Ctrl K` command palette, the `?` shortcuts sheet), BG.1 (tokens, "not priced", typical
  time, ceiling bars; the run payload carries `max_run_tokens`/`max_run_cost_usd`) and BG.5
  (`GET /api/health/server`, never a model call; the header's server dot; Settings in tabs).
  BG.6 (`GET /runs/{id}/sprints` from the graph state; the fix loop's open defects) and BG.3 (a
  review shows its document and what changed; `GET /runs/{id}/artifacts/diff`) and BG.4 (rail,
  work area in real tabs, ledger; each column scrolls inside itself) and UI-S5 run defaults (the
  start form opens as the owner last started a run) and BG.7 (the Audit tab: `GET /runs/{id}/usage`
  and `/transcript`), BG.8 (feed: held-back chips, decisions, lanes) and BG.9 (per-file diffs; a
  criterion links to the change that first made it pass) and BG.11 (every graph node has words; a
  test holds the table to the graph) and BG.12 (contrast borders on controls only; a 12 px floor).
  BG.13 (no `/logs` paging while the stream is open; the feed announces headlines only; disclosures
  say their state) and UI-S3 = BG.10 (a written brief, its criteria shown before the run, existing
  code, no orphans), BG.15 (model pressure in the rail), BG.14 (the run's timeline above the feed)
  the BG.16 housekeeping and UI-S6 (a run's KPIs on its page; `/runs/compare`). **Group 1 is
  built.** Deployed e0c73cc (app + worker) at 13:28 UTC into the shakedown run, which resumed; the
  app alone since, last at cf75b399 (14:15 UTC: the owner's LF.31-LF.34 - estimates by brief size, the
  frontier model checked before a run, flush sticky headings, the Delivery pane by its own width). LF.35 (a look
  through the command tool refused only when the stage already has what it shows) and LF.36 (a compacted
  stage keeps its request; the summary is never empty) need the worker: deployed together into the
  shakedown (a828a9f, 14:56 UTC). LF.37 (an empty folder's listing runs) and LF.38 (a product that did not
  start loses no acceptance test by name) followed. The shakedown run-894282e3 was **cancelled at 00:08 JST
  2026-10-20** on the owner's word (no longer useful: 426 min, 34 defects, 3 fixed, 8 fixes reverted; KPIs in
  `data/kpi/`). App and worker deployed at ee47e4e4 (the worker carries `run_kpis`). The first gate run, run-7622ead3,
  was cancelled at 00:51 JST (LF.40: its specification planned server-only column types for a product tested
  on the file database; not a measurement). run-ffa6599b (00:56 JST) was cancelled at 15 min for LF.41 (the layout repair named the
  served files without their folder). run-46d7cb71 (01:17 JST) was cancelled at 29 min for LF.42 (the review undid the
  file-database fallback). run-e601377f (the findings run: 8 mid-run deploys, LF.43-LF.55) was cancelled at 05:59 JST 2026-10-20 after its first real
  acceptance result - the product's own import error (`models.user` that does not exist) stops its service; KPIs in `data/kpi/`.
  **Clean gate run 1 is run-01a1ab9c**, started 06:00 JST on a39807de: `tests/brief_medium.md`, `DELIVERY=fast FRONTIER=false`;
  gate run 2 follows it on the same code, then `kpi_ledger.py compare` against the baselines, then group 2.
  **Owner, 2026-10-20 22:20 JST: group 2 also takes CM.1-CM.5** (agent communication through harness-owned
  records, `docs/agent-communication-feasibility.md`, plan Appendix 6); **OS.0-OS.8 (object storage, SeaweedFS) is
  implemented later**, after group 2.
  **Both gate runs measure one code version (a39807de):** fixes found meanwhile are pushed but deployed only after gate
  run 2, unless a bug would spoil the measurement. LF.56/LF.57 were deployed into gate run 1 at 07:35 JST
  (73aaa5ef): the pip false positive kept the product from starting; the run was rewound to its round-1 test round.
  **10:35 JST: run-01a1ab9c is a findings run now, not gate run 1.** Its locked suite holds tests no product can pass
  (a helper calling `http://localhost`, LF.74) and the fixers began bending the product to them (a port-80 proxy in
  `main.py`), so the run could not measure delivery - the owner's rule for a major bug: fix, deploy, rewind.
  LF.59-LF.74 (and LF.58) deployed at 3d8b0a3c; rewound to attempt 3's round-1 test round (00:02 UTC), so the
  round re-measures with the fixes and sends the suite back to QA. The two clean gate runs both run on the new code
  after it (the redundant-read KPI is not comparable across LF.63). Listing the rewind points took over 2 minutes on
  this run's history; `loop.sh rewind` waits for it (its curl has no timeout) - a manual call needs `-m 600`.
  **17:57 JST: run-01a1ab9c completed** (555 min, four rewinds, LF.58-LF.90 deployed into it): acceptance 62/62,
  unit 118/118 (52 page + 66 service). Every acceptance test goes through the API; the page kept 1 of 10 interface
  contract lines at release (labels not tied to inputs, views not routes) and only the release evidence says so -
  the case for EF.11/EF.12. **Clean gate run 1 = run-b7a20bad** (`tests/brief_medium.md`, `DELIVERY=fast
  FRONTIER=false`), started 18:00 JST on e6a86dee; gate run 2 follows on the same code, then `kpi_ledger.py compare`.
  LF.91 (a UI-only fix, the app alone redeployed at 18:15 JST) went in during it; the owner counts it as clean.
  LF.92 (the file plan read as its headings) was found at 18:45 JST; owner: pause, fix, deploy, rewind - rewound
  to `technical_lead` at about 18:55 JST, so its fast work orders are made from the real file plan.
  The rewound plan then showed LF.93 (32 path problems); paused, fixed, deployed and rewound again (~19:00 JST).
  LF.94 (deploy waited on a paused call's marker) and LF.95 (the undeclared-packages defect named code, not the
  manifests) followed; paused 19:29, deployed, rewound to the CI gate.
  LF.96 (the gate's findings merged into one defect through a failing test) followed; paused 19:50, deployed, rewound
  to the CI gate.
  LF.97 (the gate's cap counts files) followed at 19:54, the same way.
  LF.98 (a merged finding falsely closed by its recheck) followed at 19:58, the same way.
  LF.99 (direct model calls recorded) and LF.100 (an unknown import names its module) at 20:16, the same way. KPIs
  of fast runs before LF.99 undercount drafting and rewrite calls.
  LF.101 (a module-first finding names the module alone) at 20:23, the same way.
  LF.102 (a merged defect keeps every finding's guidance; a finding is settled by asking the service) at 20:38.
  LF.103 (test cases from the sprint's criteria; tests named by their language's pattern) at 21:09.
  LF.104 (a plan's checks judged as the tool runs them) at 21:18.
  LF.105 (a round that finds the product not starting raises the language service's findings) at 22:45, no rewind.
  LF.106 (another spelling of a kept file is the harness's; a shadow is removed) at 23:10, no rewind.
  LF.107 (TS2613, a default import of a named-only module, is kept) at 23:20, no rewind.
  **00:15 JST 2026-10-21: run-b7a20bad failed** (4 attempts, acceptance 0/31, reached the product only in the last
  round); with LF.91-LF.107 deployed into it, it was a findings run. Gate run 2 starts on 5c19b81 next.
  **Gate run 2 = run-d48f049e** (00:18 JST); LF.108 (fields written in tag form taken apart) found at 00:29, rewound
  to `principal_architect` - inside its first 40 minutes, so it still measures one version from there.
  LF.109 (a misspelt, unwritten project folder is the project) deployed at 00:55 before its plan step, no rewind.
  LF.110 (a write that changes nothing counts as nothing new) deployed at 01:05 mid-stage, no rewind.
  LF.111 (a specification requiring a setting at startup goes back) at 01:29; rewound to `principal_architect`.
  LF.112 (each package's manifest named; a failed install says why) at 02:30, no rewind.
  LF.113 (a failed install is raised as a defect) at 02:40, no rewind.
  LF.114 (a stage's call budget counts across a compaction) at 03:12, no rewind.
  03:18 JST: the product starts, 31 of 34 tests pass. LF.115 (a failed install raised in every round) at 03:45.
  04:08 JST: 33 of 34. LF.116 (lost replies counted across a compaction) at 04:40, no rewind.
  LF.117 (a failed test's own source is read for test bugs) at 05:25, no rewind.
  06:42 JST: 34 of 34. LF.118 (a unit failure's cause from the whole run) at 06:55; attempt 3 re-planning. 07:08: test round 2 of attempt 3 passed everything; milestone reviews. LF.119 at 07:20 (the sprint panel showed the failed attempt 2 as the sprint's state; owner report): the attempt under way is served while the run is live.
  **07:15 JST: run-d48f049e completed** (351 min, 3 attempts, accepted): acceptance 34/34, unit 30/30; 59% of its product
  lines are modules nothing imports (the fixers built a working copy in `main.py` and `App.tsx`), and its compose stack
  would not start. LF.108-LF.119 went into it. **The next gate run is run-f4f0030b** (07:25 JST on d3de13a3, brief_medium,
  `DELIVERY=fast FRONTIER=false`). LF.120 (modules nothing imports are named to fixers and at release) deployed into it at
  about 07:40 JST. Group 2 (CM.1-CM.5 first, then M.4, EF.11) is built from now on and deployed after this gate run.
  **Owner, 2026-10-21 13:45 JST: group 2 also takes the Appendix 6 additions RL, PH and CG** (plan, owner's commit
  a5edf9c9), in Part 21's placement: PH.2/PH.3 in stage 3 after AY; PH.1, CG.1-CG.2 in stage 4 after BJ and CM.2;
  RL.1-RL.3 in stage 7; CG.3-CG.4, PH.4 in stage 8; CG.5 on the UI track after BG.3/BG.4.
  **Owner, 2026-10-21 14:20 JST: Appendix 7 (the discipline layer).** Group 1, built now in this order: MF.1-MF.6, RC.1-RC.3,
  OP.1-OP.4, CH.1-CH.3, IN.2, BW.3, EV.1, SF.1-SF.2; group 2: IN.1, BW.1-BW.2, PN.1-PN.2, EV.2; MF.4 (Measure/Fix cycle)
  is ADOPTED (owner, 14:25 JST) from the run after gate run 3. Built: MF.1 (provenance; `HARNESS_COMMIT` in the image), MF.3, MF.5.
  **Gate brief from the next run (MF.2, owner): `benchmarks/tasks-api/brief.md`**, scored by its hidden suite
  (`loop.sh score <run> tasks-api`); `tests/brief_medium.md` is no longer the gate. **Measure/Fix (MF.4):** a Measure run
  is one frozen SHA, no mid-run deploys, two runs per family; bugs found are filed for the next Fix batch, not deployed. **Set aside by the owner 2026-10-22 18:40 JST:** from Measure pair 4 run 1's end every switch is on (compose defaults them on), the next run is the all-on baseline, and verified fixes that save harness or model time are deployed mid-run at a stage boundary again (`loop.sh deploy`, `loop.sh resumed`); features are turned off later to measure them. RL.4 (learning judged on
  hidden tests only) applies now; RL.5 is rejected. Build order from here: PH.2, PH.3 (they extend CM.2's ledger),
  then PH.1, CG.1, CG.2, then RL.1-RL.3; each behind a switch, off until the gate run ends.
  Each group 2 item is behind its own switch, off by default (any mid-run deploy carries the branch); CM.1 =
  `SHARED_FACTS` (`app.agents.shared_facts.ON_BY_DEFAULT`); CM.2/EF.11 = `DECISION_LEDGER` (`app.agents.ledger.ON_BY_DEFAULT`); AY = `FIX_CYCLE` (`app.graph.bounded_fixes.ON_BY_DEFAULT`).
  `.gitignore` matches `fix_*.py`: name no source module so (`tests/test_no_source_module_is_ignored_by_git.py`). After the gate run: turn the built ones on, deploy, measure.
  LF.121 (a suite file left out of a request points at the memory) deployed into it at about 08:00 JST.
  LF.122 (every direct model call recorded), LF.123 (the restart sweep's grace 120 -> 60 s) and LF.124 (a brief
  feature the specification defers goes to the architecture review) at about 08:25 JST; rewound to `architecture_review`.
  LF.125 (a rewind crosses out the stage notes the restored files hold) at about 08:35 JST; rewound to it again.
  LF.126 (a rewound stage is handed no stray decision; the record names the stage rewound to) at about 08:38 JST;
  rewound to the FIRST `architecture_review` (22:37 UTC): a gate whose revisions are spent cannot send work back.
  LF.127/LF.128 (deferred-requirement evidence by sentence; the workflow raises a deferred brief feature) at about
  08:46 JST; rewound to the first review again.
  The rewind-points listing still runs out of memory on a long history: post the checkpoint id to
  `/api/runs/<id>/rewind` directly (points computed in the worker).
- **Owner, 2026-10-20: every fix is language- and framework-agnostic.** Anything specific to a language or
  framework goes through the harness's existing dynamic setup - a stack pack, the plugin instructions in
  `plugins/seed.py`, a per-language table or service (`sandbox.CODE_AS_A_FILE`, `language_service`) - never
  a special case in generic code, and a fix for one stack must not hinder another: check it against the
  others before it ships (LF.70).
- **Owner, 2026-10-23: the product works on small and large codebases.** Plan every change for both: ask what
  it does at 10 files and at 10,000. Keep the small-codebase path exact and switch to the bounded one (ranking,
  skeletons, caps that say what they cut) only past a measured size, chosen at run time; test both sides of the
  threshold (plan SZ.1-SZ.11).
- **Owner, 2026-10-20: the routine audit runs every 10 minutes** (cron `3,13,23,33,43,53 * * * *`).
  After a restart of this session the crons are gone and must be re-created: the 10-minute audit and the two
  90-minute deep analyses (`13 0,3,6,9,12,15,18,21` and `43 1,4,7,10,13,16,19,22`). After a host restart check
  `loop.sh status`: a run recovery could not resume is `failed` with "the worker ... stopped" - resume it with
  `POST /api/runs/<id>/resume` once `loop.sh ready` says ALL READY.
- **Owner, 2026-10-20: the stages reach what is newer than the model.** The `searxng` service (private,
  compose network only; `SEARXNG_SECRET` in `.env`) backs `search_the_web` / `read_web_page`; a library's official
  remote MCP server is found in the MCP Registry and attached read-only (LF.72, LF.73). Package MCP servers are not
  run: they would execute third-party code in the worker outside the sandbox - the owner's decision.
- **A bug in a live run is fixed, then the run rewound - not cancelled and started again (owner, 2026-10-20):**
  `loop.sh rewind --pause-only` → `BOUNDARY_WAIT=0 loop.sh deploy` → `loop.sh rewind <stage> [run] [at-or-before]`.
  Rewind to the earliest stage whose behaviour the fix changes (a specification fix: `principal_architect`; the
  suite: `acceptance_author`; drafting or a builder: `specialist_dispatch`; a measurement or the environment:
  `test_and_triage`), with its files and `.harness/` as they were then; the stages before it are kept. In a gate
  run only when the fix changes nothing before that stage (say so in the ledger); the KPIs then measure the run as it
  stands (`run_kpis.live_branch`). A new run only when the fix reaches the intake or the stack, or no snapshot exists.
- **Owner, 2026-10-19: every completed fix gets an Appendix M row in `docs/improvement-plan.md`**, in
  the fix's own commit: plan items in the main table, audit fixes in M.2 (`LF.n`).
- Gates: two brief_medium runs on the new code against the baselines (`kpi_ledger.py compare`).

### 2.00000 Appendix 3 built (2026-10-19)

Wave 0 and most of Wave 2 are done and ledgered (`docs/improvement-plan.md`,
Appendix 3 rows); the W.2 baselines (Wave 1) are the owner's gate and wait for
run-8b0c94df to end. Worth knowing:

- Budgets survive a restart (the transcript seeds the total), a fix stage that
  spends its calls is recorded from its writes, the mutation probe journals
  before it breaks anything, and a steering note says when it was read.
- The interface has a theme system: `index.css` tokens, `lib/appearance.ts`,
  `scripts/ui/theme_contrast.mjs` (run it after any colour change),
  `scripts/ui/axe_measure.mjs` (axe per theme; `SHOTS=1` writes `docs/ui/`).
  UI-only changes: `docker compose build app && docker compose up -d --no-deps app`.
- The interface has tests: `cd langchain-ui && npm test` (Vitest, in the suite too).
- `loop.sh reasoning-probe run` measures whether the server shortens replies when
  asked to think less; it needs the model server free.
- Lessons: `lessons.py list|approve|reject`, or Settings -> Lessons.

### 2.000 Fast delivery (2026-10-14, `e55dd6f`)

The owner judged the harness too slow to be worth using: run-c2e62179
(notes-api-hono, thorough) took 13.3 h for 1.5 of 4 sprints - 1,081 model
calls one after another (only one in flight 91% of the time even in
parallel mode, the local server serves one at a time), 2.84 M output tokens
of which 48% reasoning, 54 M input tokens, 549 lines of product and 5,058
lines of tests. `DELIVERY_MODE` (`app.delivery`; settings page "Delivery
Mode"; compose default `fast`, code default `thorough`) adds a fast path:
one sprint for <=20 criteria; work-order files drafted from the
specification one call per file (`app.graph.drafting`, unattended runs
only, agent loop as fallback); harness-run test rounds once the locked suite
has run (unit failures -> a product-owner defect); tests limited to the
specification's file plan; building/fixing with reasoning off
(`thinking.without_reasoning`). Benchmark: notes-api-hono on fast vs the
13.3 h thorough baseline. Owner 2026-10-14 (frontier only where its reasoning is
needed): in fast delivery the intake, comparison, stack choice,
consultations, sprint plan, work orders and acceptance-test authoring run
on the build model; the specification and every review stay on the
judgement model, and a judgement stage gathers (reads, docs, lookups) on
the build model with reasoning off and writes on the judgement model
(`app.agents.gathering`, registered by `gather_with`). Owner 2026-10-15: the
architect's reading is done before it starts - the harness looks up every
library of the stack in its registry, the build model names the documentation
topics once, the harness reads them, and the notes go into the architect's
request (`app.agents.research_brief`, kept in `architect_research`); the
architect is then offered no documentation or registry lookups
(`research.researched`). Only read-only calls
(`GATHERING_TOOLS`) are gathering - a write or a command, as in a building
stage escalated to the judgement model, is the judgement model's. One architecture
revision and one acceptance send-back, then open findings are decided
risks. Owner 2026-10-15: each run chooses whether to use the frontier model ('Use the
frontier model' on the start form; `use_frontier_model` in the start request,
`runs.local_only`, `app.models.roles.on_the_build_model_only`); unchecked, every
stage runs on the build model. `loop.sh start` takes `FRONTIER=false`. Owner
2026-10-15: a milestone review still asking for changes after
`MAX_MILESTONE_REVISIONS` records its findings as risks (a decision, carried to
the next sprint) and goes on to the checks - a red suite, a criterion due that
fails or a sprint not done still stop it; thorough still escalates. Research has a share per stage visit (8 docs, 12 packages;
`app.tools.research`), carries to a fresh attempt, and package lookups
batch. A cut-off answer keeps its whole fields and asks for the rest
(`app.models.tool_arguments`); a specification revision sends only what
it changes. 2026-10-15: the harness does what needs no model in fast delivery -
fixes by rewriting (`app.graph.rewritten_fixes`), compile-and-repair after
drafting, a silent suite run file by file (`app.acceptance.per_file`), work
orders from the specification (`app.graph.planned_work`; only to build the
product - once half its planned files exist the lead plans the change, and
files the harness keeps are never listed), no model code
review. Analysis and next steps (project source in memory, parallel
candidate fixes, type errors refused at the write, specification in parallel
parts): https://claude.ai/artifact/SBZagb9VAP9P5Q4bHMsVgJ. Built the same night: the project memory
(`app.agents.project_memory`, `PROJECT_MEMORY` on/off, default on in fast),
candidate fixes, errors refused at the write, the specification in parts.
Owner 2026-10-15: the delivery mode is each run's own - chosen on the start
form (`StartRunRequest.delivery_mode`), kept in `runs.delivery_mode`, applied by
the worker with `delivery.for_the_run`; a run started without one takes
`DELIVERY_MODE` (`loop.sh start` passes `DELIVERY=fast|thorough` if set). The
settings page no longer has it. On in BOTH modes: project memory, errors
refused at the write, a silent suite run file by file, gathering on the build
model, candidate fixes. Fast only: one sprint, drafting, harness work orders
and test rounds, rewrite fixes, no code review, one revision/send-back,
planning on the build model, the specification in parts. The harness-run test
round stays fast-only: it measures existing tests, while the model round also
writes tests for what the sprint built.
A read of a file the project memory holds, unchanged, is answered with a
pointer to it - a window (`offset`/`limit`) too: a third of all reads were
windows. Files over `LARGEST_FILE_CHARACTERS` (60k; the specification is often
~200k) are not held and are still read from disk.
A withheld tool that a model keeps calling (a 1-bit model did, 23 times)
takes every looking tool away (`settled_answer._a_withheld_tool_still_called`);
the stall rule counts distinct calls, so one tool asked about one thing after
another with nothing new is a stall too.
A call to a tool name not offered that plainly means one offered tool
(`Read` for `read_file`) is taken as that tool (`tool_arguments`).
Fast delivery's milestone review sends a sprint back once
(`FAST_MILESTONE_REVISIONS`), then records the findings as risks.
`loop.sh deploy` deploys between model calls (owner 2026-10-15): it builds,
sets `/app/data/loop/gate/hold` (new calls wait), waits for
`gate/inflight/` to empty (`GATE_WAIT`, default 1800 s), restarts, lifts the
hold (`app.models.call_gate`).
A call to a tool the model call withheld is refused, not run
(`SettledAnswerMiddleware.wrap_tool_call`).
`loop.sh diagnose [--again]` prints the served model's diagnosis (plan MD.1): tools offered, required and
named, stage-shaped structured answers, recall, the fitness and edit probes, each reasoning switch's cost, and
reply salvage (RS.1). A model never seen is diagnosed automatically at a run segment's start (~2.5 minutes, once
per model) and kept in `DATA_DIR/model-fitness/<served name>.json`; `--again` re-measures. Owner 2026-10-23:
every new model is diagnosed and the harness adapts from the result; no reasoning cap - reply salvage instead.

`loop.sh fitness` probes the build model with five scripted tool calls
(`app.models.fitness`: FIT/USABLE/UNFIT + advice); run it after `ready`,
before a run, never beside a live one. While every test command passes, a
milestone finding that names no criterion or test case (AC-n, TC-...) is
recorded as minor (`_findings_no_measure_holds`).
Project memory: a markdown document over 60k is held as its outline (line
ranges) plus the sections the request's ids and words point at
(`project_memory.digest_of`); files left out are listed with the lines that
define something (`map_of`, a repo map without a parser per language).
Proven setups are kept in `/app/data/proven-setups/<stack>.json`
(`PROVEN_SETUP_LIBRARY`); a later run on the same stack replays and re-proves
one before asking the setup stage (`custom_setup.replay`).
Research before the architect looks up only package-shaped names: no runtimes,
files, built-ins, versions or words of a sentence, and reads documentation
only for names the registry knows. A server's refusal of a forced tool call
is kept in `/app/data/loop/no-forced-tool.json` across restarts. Project
memory states the workspace top level and an empty project directory.
A stage whose test runs fail identically with edits between them is told so
at 3 and left only its answer at 5 (`settled_answer._the_same_failure_running`).
A model call over 60 s on a server another run was also using is reported on
the run page (`call_gate`: in-flight markers carry run and server).
Per run, `approval_timeout_minutes` (start form: "Approve a waiting gate
automatically after N minutes"; column `runs.approval_timeout_minutes`): the
API sweeps every 60 s and approves a gate that waited past it
(`app.server.approval_timeouts`).
`GET /api/runs/{id}/handover` (run page: "Handover pack") zips docs/, the
acceptance suite and `.harness/decisions.json` (`app.sprint.handover`).
`GET /api/runs/outcomes` lists finished runs with hours and hidden-test score
(`loop.sh score` also leaves a summary in `/app/data/outcomes/`) and a typical
time per delivery mode; the runs list shows the table, the start form the
forecast (`app.server.outcomes`).
QA's request shows the acceptance smoke test that passed at setup (a pack's
`smoke_files`, or a proven setup's kept `acceptance_example`) as the shape to
copy (`requests._a_test_that_ran_here`). Grammar-constrained tool calls: the
owner's llama.cpp-style server (1 slot) returns an invented tool name even
with `tool_choice: required`, so it is not available there; names are mapped
after the fact (`tool_arguments._the_offered_tool_meant`).
A stage a stopped worker cut off carries on in its own conversation from its
last saved step (`app.graph.abandoned_threads`, `.harness/stage-threads.json`):
the gate alone was not enough - a deploy that waited for a 10-minute frontier
call restarted the architect from nothing 50 s later.
A note carries the worker process that wrote it; only a note from a process
that has stopped is a cut-off (a send-back in the same process once carried
on the old conversation because a reminder path never crossed its note out).
The harness's own request is never moved to `conversation_history/` (deepagents
evicted every architect request over 50k tokens; the architect read its own
instructions back in windows): `human_message_token_limit_before_evict=None`.
Fast revisions are made in place: one call names the sections the required
changes touch, they are rewritten at once, the rest kept
(`specification_parts.revised_in_place`); the architect agent only if that fails.
`stack-setup.json` is checked as it is written (`custom_setup.problems_with`,
from `write_artifact`): the files it names may come later; every other rule
refuses the write with why.
A call to an unknown tool name with arguments only one offered working tool
takes (all given accepted, all required given) is taken as that tool; never
an answer tool (`tool_arguments._the_one_its_arguments_fit`).
Each stage names itself on the run's row as it starts (`RunStore.record_stage`,
only while `running`): the row used to change only at a pause or the end.
Files a sprint names: `<stem>.env` and a name followed by `.member`, `(` or
`[` are code, not files; `x.js` is the planned `x.ts` compiled
(`work_orders._COMPILED_TO`). `test_the_other_sections_are_written_at_once_from_the_core`
is timing-flaky under suite load (2 of 3 parts overlapping).
Separate save mode and profiles for local build model and frontier model:
`PUT /api/settings/local` saves and remembers local build profiles (`target='build'`),
`PUT /api/settings/frontier` saves and remembers frontier profiles (`target='frontier'`).
An explicit "No model" option (`no_model=true`) clears all frontier model configuration
and disables all frontier model calls so the entire workflow executes purely on the local model.
Settings UI provides separate "Save Local Model" and "Save Frontier Model" controls,
dedicated saved profile pickers, and a one-click "Select No Model" action with status indicator.
Truncated structured tool call recovery (`tool_arguments`, `settled_answer`, `workflow`):
a tool call cut off at `max_tokens` with incomplete JSON is preserved via `invalid_tool_calls`
instead of being misdiagnosed as all-reasoning. Whole fields are retained in memory (`_HELD`),
`cut_off_notice` explicitly commands the model not to restart from the beginning but continue
only with the missing fields, and partial list fields are concatenated across continuation calls.
Incremental document filling & targeted repair continuation (`tool_arguments`, `workflow`, `principal_architect`):
when whole fields arrive from a cut-off tool call, the partial document (`docs/technical_specification.md`, `docs/sprint_plan.md`)
is immediately rendered and synced to disk (`_sync_partial_document`), and `cut_off_notice` informs the model that the document has been populated
with the sections received so far so it continues only with the remaining fields. Furthermore, specification repair comments
instruct the model not to regenerate the whole specification from the beginning, but return only the missing or corrected sections,
with `_with_the_sections_it_dropped` preserving all existing sections from the previous specification and `TechnicalSpecificationOutput.product_scope` defaulting cleanly.
Infinite jump-to-model loop break, uncapped output tokens & focused revision context (`settled_answer`, `context_budget`, `models`, `principal_architect`):
When a model call truncates due to token limits or server cutoffs (`finish_reason == "length"`), `settled_answer.py` prevents infinite model invocation loops by tracking consecutive lost reasoning replies (`_is_lost_reasoning_message`, `_consecutive_lost_reasoning_replies`) and breaking after 2 retries, returning `jump_to: "end"` with `BUDGET_STOP_MARKER`. Output token caps are made optional for local inference: when `model_max_output_tokens <= 0` (or empty), `ContextBudget` sets `output = 0` (uncapped), and `CompatibleChatOpenAI._get_request_payload` removes `max_tokens` and `max_completion_tokens` from request payloads so local servers (LM Studio, llama.cpp) can naturally use full context headroom without artificial premature cutoffs. Revision context bloat is eliminated: `build_architecture_revision_request` caps previous specification text to `REVISION_SPECIFICATION_BUDGET` (25,000 chars), pointing to the full specification stored in project memory and instructing the model to return only revised sections, proven clean of banned words (`tests/test_uncapped_output_and_loop_break.py`).
Specification parts without reasoning & fallback (`specification_parts`):
When writing remaining specification sections in parts in fast delivery, `with_the_parts_written` calls the model with `without_reasoning(model)` so local reasoning models answer directly with structured JSON rather than spending 15+ minutes in chain-of-thought, and `_the_object_in` falls back to `reasoning_content` if `reply.content` is empty (`tests/test_the_specification_is_written_in_parts_at_once.py`).
Architecture reviewer write prompt contradiction removed (`architecture_reviewer`):
`architecture_reviewer._SYSTEM_PROMPT` had contradictory `write_artifact` and edit instructions despite `can_write=False`, causing models to attempt failed `edit_file` calls when reviewing; removed contradictory write instructions from the reviewer prompt and verified with banned words test (`tests/test_architecture_reviewer_agent.py`).
Page view overlay directory tolerance (`page_view`):
`look_at_page` prepares an overlay directory (`test-results/page-view`) for Playwright inspection of the running web page. `overlay.mkdir(parents=True, exist_ok=True)` now permits the directory to already exist if an earlier inspection or `shutil.rmtree` left it intact, avoiding `FileExistsError` during specialist inspection (`tests/test_a_fix_stage_can_see_the_page.py`).
Acceptance suite negative assertion matchers detection (`suite`):
`assertions_that_do_not_exist` previously checked `_ASSERTION_CALL` with `r"\.(to[A-Z][A-Za-z]*)\s*\("`, missing negative matchers written directly like `notToHaveAttribute` or `notToBeVisible` as well as callable `.not()` invocations. Updated regex to `r"\.((?:not[A-Z]|to[A-Z])[A-Za-z]*|not)\s*\("` to flag nonexistent runner methods and invalid `.not()` calls with instructions to use `.not.` as a property before the matcher (`tests/test_a_suite_finds_controls_the_way_a_person_does.py`).
Fast-delivery rewrite fallback model when model is None (`rewritten_fixes`, `workflow`):
`fix_by_rewriting` in fast delivery attempted to call `model.invoke(...)` when `model` was `None`, throwing `'NoneType' object has no attribute 'invoke'` and forfeiting single-file defect rewrites. Added safe fallback to `build_default_chat_model()` and checked `hasattr(active_model, "invoke")`, and updated `_fixed_by_rewriting` in workflow to pass `fix_model or model or building_model` (`tests/test_a_defect_is_fixed_by_rewriting_its_files.py`).
False-positive file URL detection in comments & .harness exclusion (`integration_checks`):
`_a_browser_test_that_opens_a_module_page_from_disk` previously scanned raw file text without stripping comments, causing comments explaining why HTTP was used instead of `file://` to trigger false positive "opens the page from disk" defects graded as BREAKS. Updated `_without_comments` to preserve string literals using tokenization (`_NOT_CODE`) while blanking comments, passed `_without_comments(text)` to `_OPENS_A_FILE`, and added `.harness` and `test-results` to `_SKIP` so locked acceptance snapshots and test logs are not cross-checked as project source files (`tests/test_a_browser_test_opens_the_page_the_way_a_browser_can_run_it.py`).
Milestone review output extra fields tolerance (`milestone_reviewer`):
`MilestoneReviewOutput` and `MilestoneReviewFinding` had `model_config = ConfigDict(extra="forbid")`, causing Pydantic to reject structured outputs when local models output valid fields alongside harmless extra commentary keys (such as `changes_required_note`, `notes`, `summary`), resulting in failed tool call parsing, repeated failed attempts, and stage retries. Set `model_config = ConfigDict(extra="ignore")` so harmless extra keys are safely discarded while all required fields are validated (`tests/test_milestone_review_accepts_extra_fields.py`).



_Sections dated before 2026-10-14 moved to [`archive/handover-before-2026-10-14.md`](archive/handover-before-2026-10-14.md) on 2026-10-21 (plan MF.6)._

### 2.2 Verify on the next run

1. **The scaffold.** The decision record says the pack's title. On brief_medium
   that is `fullstack-react-fastapi` or a sibling, not "left to the agents".
   `.harness/stack-pack.json` has `"scaffolded": true`.
2. **Batching.** In `loop.sh defects`, a bundled defect's story reads "bundled",
   then either "closed without a fixer" (by measurement) or a fixer of its own -
   never "fixed in batch".
3. **The procedural test round.** "skipping specialist LLM invocation" appears
   only when the locked suite ran green.
4. **Builders in parallel.** No `belongs to another work order` refusal follows
   an IDE note about an import.
5. **A custom stack (after `58600ee` is deployed).** The decision record says
   "a proven setup" or "left to the agents" with the failing smoke test; with a
   proven one, `.harness/stack-pack.json` has `"pack": "proven-setup"` and QA
   writes into the declared acceptance directory. `look_up_package` and
   `use_runtime` calls appear in transcripts without failing.

### 2.3 Recent runs (newest first; full history in monitoring §0.2)

- **run-d48f049e** (gate run 2, `tests/brief_medium.md`, Fast, local; 2026-10-21 00:18 → completed 07:15 JST, 351 min). Acceptance 34/34, unit 30/30, release accepted on attempt 3. 470 model calls, 75% reasoning, cache 74%, 25 defects / 8 fixed. Product audit: 1,883 of 3,167 lines unreached (duplicates in `main.py`/`App.tsx`), compose names an undeclared async driver, no migration, no reminders. LF.108-LF.119 deployed into it.

- **run-8b0c94df** (Medium brief `tests/brief_medium.md`, Fast, local only; 2026-10-18 07:02 → cancelled 2026-10-19 07:11 JST, 24.1 h). **Hand score: 9 of 30 locked acceptance tests passing (13 criteria: AC-8 4/6, AC-1 3/5, AC-13 3/7, AC-12 2/3, the other nine 0); unit tests 17 of 42; 4,455 lines of product plus an unserved second copy (`frontend/`, `backend/`).** Cancelled at the owner's threshold (20 or more of 30 failing after a test round) on sprint-1 attempt 4. KPIs: 2,593 model calls, 160 M input tokens (73% cached), 5.2 M output (about 32% reasoning where measurable, 35% of output in replies lost to length), redundant reads 47%, 10 test rounds, 25 fix stages, 62 defects raised, 8 fixed, 6 fixes reverted. Causes, in order: the file plan built a second app beside the pack's served one (fixed at the source by `8cacab9` for future runs); fixers read without writing (now withheld after 12 calls, `9275b8f`); a specification naming PostgreSQL on a sandbox with none (fixers now told the store is the embedded file, `d7902be`). Twelve harness fixes came out of it; see monitoring-handover §0.2 2026-10-18/19.

- **run-d1899b44** (brief_medium, 08:19-09:02 JST 2026-10-13, on `79089ea`):
  CANCELLED at 44 min. The selector chose "Browser app in React with its own
  HTTP service in FastAPI" in its rationale but left the frontend field "not
  stated", so no pack fitted (custom stack). Fixed in `e95d943`: a pack the
  rationale names alone is chosen when the fields fit none.
- **run-c7a1f6cf** (brief_medium, 21:19 JST 2026-10-12 - 07:11 JST 2026-10-13,
  parallel, on `b0c092c`): FAILED in sprint 1's defect fixing at 9 h 52 min.
  - First medium run on a proven pack (`fullstack-react-fastapi`, scaffolded).
  - `defect_fix_1_3` spent its 40 calls three times over on one defect (login
    422: email validation); the third attempt found the cause on its last call.
  - Fixed in `2e4e2ef`: fix and work-order stages out of retries leave their
    work open (the defect stays open; the blocker carries where the attempt
    ended) instead of failing the run.
  - 80% of output tokens were reasoning; verification took 197 min. Lost
    replies were all recovered by `b0c092c`.
  - The operator session was paused overnight, so the run was not cancelled
    for its length; it should have been, around hour 6.
- **run-c83ee867** (brief_medium, 13:40-14:34 JST 2026-10-12, on `b2f837b`):
  FAILED at sprint planning.
  - The scrum master reasoned through its whole 25,000-token reply twice.
  - The first loss was carried by the graph's one nudge, with thinking off;
    the second ended the stage with thinking never switched off for the rest
    of the visit.
  - Fixed in `b0c092c`: a lost reply jumps straight back to the model.
  - The architecture, consultation and acceptance-authoring stages before it
    had 0 failed tool calls.
  - The loop then sat idle about seven hours: the operator session had hit its
    usage limit.

- **run-fe7854b9** (brief_medium, 23:50 JST 2026-10-11 - 02:29 JST
  2026-10-12): cancelled in a defect fix.
  - Its stack decision said no pack fits (Python/FastAPI + React), yet the
    contract lookup wrote a `node-http-api` contract two minutes in.
  - It inferred that from a stack-document sentence explaining why a
    JavaScript option was rejected.
  - Fixed in `6314d91`.
- **run-fd3a244d** (brief_medium, 17:16-23:17 JST 2026-10-11): FAILED at the
  6-hour Celery limit.
  - It was given a guessed `python-http-api` contract; that pack's
    `pytest.ini` and `acceptance/conftest.py` were written into a project with
    a browser page.
  - The pack's acceptance command never produced a report (13/13 criteria
    "untested").
- **run-fdc1385c** (brief_medium, 12:59-16:45 JST 2026-10-11): FAILED. Its
  test round could not answer, which `f9987af` now records as blocked.
- **run-5aadbddd / run-49dec2db** (web-todo, 2026-10-10/11): the stage 1 gate
  runs, 10/10 each.
  - 49dec2db took 327 min (4 defect-fix stages over one ambiguous locked
    locator); 5aadbddd took 80 min with no defects - same code.
  - 49dec2db's scaffold was "left to the agents" over the browser-version
    mismatch.

- **run-d96ae4c7** (12:15-17:32 JST, 2026-10-10): COMPLETED, score 10/10 (1.0).
  Product audit clean: 323 LOC, 47 unit tests pass (exit 0), working tree clean.
  Not clean: locked acceptance suite had `locator('button', { name: 'Edit' })`
  and `locator('button', { name: 'Delete' })` asserting `toHaveCount(1)`. In
  Playwright, `locator()` does not accept `name` options (only `hasText`, `has`,
  `hasNot`), so Playwright ignored `name` and matched all buttons (2 buttons in
  sprint 2), trapping specialists in 102 minutes of defect remediation until
  auto-escalation deferred criteria. Fixed before next run with
  `suite.locators_with_invalid_name_option` and `PLAYWRIGHT_LOCATORS_RULE`.
- **run-d211dc86** (14:10 JST, 2026-10-08): cancelled within seconds.
  `loop.sh ready` printed NOT READY but exited 0, so the run started while
  LM Studio served gpt-oss and the settings named qwen. Fixed in `344b4a9`,
  so `ready` exits 1.
- **run-7b219f82** (07:47-13:57, on `97d9dd1`): cancelled by the owner in
  sprint 2's second revision. Not clean. Findings, each fixed in the commit
  named:
  - A fix stage built later sprints' features (`d833edb`).
  - `style.css` against `styles.css` in the plan check (`8da1e0d`).
  - Two locked tests contradicted each other on order (`60971c5`; the
    mid-attempt dispute then worked).
  - `npm test` failed only on sprint 3's tests and was recorded as a defect
    (`351d1ec`).
  - The scaffold smoke test failed once, so no contract kept the pack's files.
    A tester then switched sprint 3's tests off in the runner configuration
    (`1dde0ed`).
- **run-0e484d19** (00:17-07:44): COMPLETED. Hidden tests 10/10, locked suite
  25/0, product audit clean. Not clean: seven fixes were deployed during it
  (`c3a5fca`, `f3d2409`, `9cc524a`, `fa8da1a`, `4bdf05c`, `cc875e7`, and
  `548a63d`/`97d9dd1` after it).
- **run-379e32c0** (23:24-00:06): cancelled. The sprint plan put sprint 2's
  work in sprint 1 (`6ff499e`).
- **run-d43cb02c** (21:00-23:14, 2026-10-07): cancelled. Sprint 1 built every
  sprint's features (`3b01d8a`), and the rewrite guard refused a stage its own
  code (`46be22f`).
- **run-f7f82c39** (12:15-14:15, 2026-10-07): COMPLETED 10/10 with no harness
  fix during the run. It was not clean only because the release record was left
  uncommitted (`6ff9456`). It is the closest any run has come.

### 2.4 Why runs got long, and what to expect now

Runs went from 1-3 hours to 5-8 hours on 2026-10-07. Three causes:

- **The owner's model switch.** `qwen3.6-35b-a3b-mtp` writes 2,100-3,700
  output tokens and takes 19-32 s per call, against gpt-oss-20b's 400-840
  tokens and 5-8 s.
- **Thinking left on.**
- **Sprints that now really are sprints** (the scope fixes above).

Back on gpt-oss-20b, expect calls about 4× faster. The thinking budget is the
biggest remaining lever, and it is the owner's decision (§7).

## 3. Setting up on a new desktop

Skip this section on the same machine (`/home/arun/Desktop/langchain`):
everything is already set up there.

1. `git clone https://github.com/marunsct/DevFlow.git` and
   `git checkout harness-hardening-session`. Name the remote `main`
   (`git remote rename origin main`) so the push command above works.
2. **`.env`**: copy it from the old machine yourself, by a private route. It
   holds secrets: never commit it, print it or paste it into a chat. The old
   machine's `/home/arun/harness-handover-2026-09-19.zip` contains a `.env`
   too; treat it the same way.
3. **Database**: Postgres data lives in `./data/postgres` (git-ignored). Copy
   that directory across to keep runs, settings and users, or start fresh. A
   fresh database's admin password comes from `ADMIN_PASSWORD` in `.env`, or is
   printed once in the app log. Transcripts and workspaces live in the Docker
   volume `appdata` and do not travel; they are only needed for history.
4. `docker compose build app worker && docker compose up -d`. The containers
   are `langchain-app-1`, `langchain-worker-1`, `langchain-db-1` and
   `langchain-redis-1`; the API is on `http://localhost:8000`.
5. **Model server**: the owner sets `model_name`, the base URL and the
   reasoning settings in the admin UI's settings. A model on the host is
   reached from the containers as `host.docker.internal`.
6. **Loop operator account.** Do not use the admin account for the loop. Use
   user `harness-test`, password `loop-test-only-pw-2026`, role `operator`.
   - It is written here at the owner's request (2026-10-07) so any agent can
     run the scripts.
   - It exists only in the local Postgres, and the owner deletes it when
     development completes.
   - Run `export LOOP_USER=harness-test LOOP_PASSWORD=loop-test-only-pw-2026`
     in your shell.
   - If a fresh database lacks it:
     `docker exec langchain-app-1 python -m app.server.manage create-user harness-test --password loop-test-only-pw-2026 --role operator`.
7. **Tests** need a Python venv at `.venv` with the project and its test extra
   (`uv sync --extra test --inexact`), and Node on the host (some tests run
   `node --check`). Then run `loop.sh suite`.

## 4. Commands

```sh
scripts/loop/loop.sh status              # current run + anything live
scripts/loop/loop.sh ready               # served model matches the settings? last line ALL READY, exit 0
scripts/loop/loop.sh bench web-todo      # a gate run; needs LOOP_USER / LOOP_PASSWORD (§3 step 6)
scripts/loop/loop.sh start [brief]       # a brief with no hidden tests; same credentials
scripts/loop/loop.sh cancel [run-id]
scripts/loop/loop.sh wait [minutes]      # blocks until the run ends or N minutes, then audits
scripts/loop/loop.sh audit [run-id]      # failures, redundant reads, stage order
scripts/loop/loop.sh stage <stage> [HH:MM]  # trace one stage (HH:MM is UTC)
scripts/loop/loop.sh timing [run-id]     # model vs tool time, reasoning share
scripts/loop/loop.sh product [run-id]    # the generated product, the harness's claims, its own tests
scripts/loop/loop.sh score [run] [name]  # the hidden tests of a finished run
scripts/loop/loop.sh failures [run-id]   # each failing acceptance test, its error and the page
scripts/loop/loop.sh defects [run-id]    # each round's defects: what raised each, how it ended
scripts/loop/loop.sh asked [run-id] <stage> [visit] [--full] [--system]  # what a stage was told, and its answer
scripts/loop/loop.sh mutate [run] [n]    # how many small product changes the locked suite catches
scripts/loop/loop.sh bench-report        # false acceptances across every scored run
scripts/loop/loop.sh resumed             # after a deploy into a live run: waits for it to resume
scripts/loop/loop.sh deploy              # rebuild, restart, verify the image matches the tree
scripts/loop/loop.sh suite               # full suite -> data/loop/suite.log (~3 min)

docker exec langchain-db-1 psql -U postgres -d langchain -tAc "<sql>"   # read-only; tables: runs, runtime_settings, ...
docker compose logs --since 20m worker   # model calls, stage failures
```

**State files:**

- The current run id is in `data/loop/current_run.txt`, and the current brief
  in `data/loop/current_brief.txt` (both git-ignored).
- A run the owner starts from the UI is not written there; put its id in by
  hand.
- A run started by the admin account may refuse a cancel from the operator
  account. If so, ask the owner to cancel it from the UI.

**Where a run's evidence lives:**

- **Transcripts:** `/app/data/transcripts/<run-id>*.jsonl` inside the worker.
  - Record kinds: `model_request`, `model_response` (text, usage,
    finish_reason, tool_calls), `tool_call` (`tool`, `call_id`, `args`),
    `tool_result` and `defect`.
  - `model_request` records are windowed: use the `carried` offset for
    absolute message positions.
- **Workspace:** `runs.repo_root`, e.g.
  `/app/data/workspaces/default/workspace-<run-id>/`.
  - The harness's own state is in its `.harness/` folder (git-ignored):
    - `stack-pack.json` (the scaffold contract);
    - `acceptance.json` and `acceptance-result.json`;
    - `acceptance-locks/vN/` (every locked suite version, each with its diff);
    - `ci.json`, `decisions.json` and `sprint-scope.json` (this sprint, the
      total and the criteria not yet due).
- **Truncated tool output:** the full text is under
  `/app/data/journal/<reference>` in the worker.

**For one-off analysis:** pipe a Python script into the worker
(`docker compose exec -T worker python - <args> < script.py`), as
`scripts/loop/*.py` do. Put a helper you will reuse in `scripts/loop/`, never
only in a scratch directory: a deploy wipes the worker's `/tmp`, and
scratchpads don't travel between agents.

## 5. Things that bite

**Deploys and the worker:**

- There is no source mount, so a restart deploys nothing. A deploy wipes
  `docker logs` and the worker's `/tmp`.
- Orphan recovery resumes any `running` run after a deploy. Cancel a
  superseded run, or it competes for the worker and the model server.

**Editing while something runs:**

- Do not edit `src/` while the suite runs. Tests that read source with
  `inspect` see shifted lines and fail.
- Do not edit `loop.sh` while a `wait` is running: bash reads the script as it
  goes. Check with `pgrep -f "loop.sh wait"` first.

**Tests:**

- The suite baseline is in §2. Apart from the three expected S3 failures, any
  failure is real. Tests that need the TypeScript compiler or Pyright skip on
  the host; verify those inside the worker after a deploy.
- A test must reproduce the state production really produces. Prove that a new
  test fails on the old code (stash the fix, run the test, restore) before
  trusting it.

**The environment:**

- `uv add` / `uv remove` re-sync `.venv` without the test extra and drop
  pytest. Restore it with `uv sync --extra test --inexact`, then
  `uv pip install uvloop watchfiles` if they went too.
- Auth is a form-encoded `POST /api/auth/token`; there is no JSON login.

**Before starting a run, check the model:**

- Never start a run while the model server's loaded model differs from
  `runtime_settings.model_name`. The owner changes both without saying so.
  Run `loop.sh ready` before every `bench`/`start`; it exits 1 when they
  differ.
- With no model loaded, do not load one. Leave one long background watcher on
  the endpoint, the settings and live runs, and start when they agree.
- Check passively with `curl <base url>/v1/models`. `lms ps` wakes LM Studio's
  background service when the app is closed.
- A model server that needs a key answers 401 to a bare `curl`. Ask through
  the harness's own settings instead, inside the worker, and print names only:

  ```sh
  docker compose exec -T worker python - <<'PY'
  import json, urllib.request
  from app.models import _runtime_settings
  s = _runtime_settings()
  r = urllib.request.Request(s.openai_base_url.rstrip("/") + "/models",
      headers={"Authorization": f"Bearer {s.openai_api_key}"} if s.openai_api_key else {})
  served = [m.get("id") for m in json.load(urllib.request.urlopen(r, timeout=10)).get("data", [])]
  print(s.model_name, "at", s.openai_base_url, "served:", s.model_name in served)
  PY
  ```

**Your own session:**

- Waits, watchers and scheduled retries belong to the session that started
  them. After a restart there are none, so start them again.
- **Two agents in one tree:** before any commit, deploy, start or cancel, look
  for edits that are not yours (`git status`) and for another agent's waits
  (`pgrep -af "loop.sh"`). One agent drives (commits, deploys, starts and
  cancels); any other audits read-only and passes its findings on. If the
  driver has gone, take the role so the loop does not stall.

**Reading the evidence:**

- About 63% of reported defects in a 46-run study were about tests and their
  set-up, not the product. When a run stalls, read the failing test command's
  raw output before believing any defect description.
- Ordinals in guard messages count the whole run, not the stage.

## 6. Security rules

- Never print or copy secret values from `.env`. Change only the keys that
  need changing, and back the file up first.
- Do not kill the owner's GPU or model processes (llama-server, Bonsai,
  unsloth, the server on port 9090, LM Studio), and do not take over the
  port-8888 server.
- Do not change the owner's model-server settings, and never load a model
  yourself.
- Never add knowledge or documentation credentials to
  `sandbox._ENV_PASSTHROUGH`.
- Do not read or reset the admin password, use the admin account, escalate
  the loop account, or write the settings table directly.
- Credentials once committed in removed `scratch/` files are still in git
  history. Never repeat them; recommend rotation; rewrite history only if the
  owner asks.
- API keys that appear in `ps` output or logs are never repeated.
- For GitHub tokens, the owner uses their own terminal.
- Docker socket access is root-level; don't enable it more widely.
- The loop account's password is in this file by the owner's decision
  (2026-10-07). It is the only credential that may be written down.
- `docs/logs.md` was removed from git by the owner on 2026-10-19; do not recreate it (plan Part 22.4 holds its points).
- Never route shell work through another command-running tool to get around
  the tool-approval check.

## 7. Open, parked, and awaiting the owner

**The owner's decisions - do not change these on your own:**

**Decided by the owner on 2026-10-20 (05:30 JST), on the agent's recommendations:**

- **The gate measurement:** run-e601377f (8 mid-run deploys, LF.43-LF.50) is a
  findings run, not the "before". Once it has its first real acceptance result
  it is cancelled, and two clean `tests/brief_medium.md` gate runs (fast, local
  only) are run one after the other on the current code.
- **The thinking budget:** low reasoning (or thinking off) for fix and
  acceptance-writing stages, planning and review as now - built and measured as
  group 2's M.4 against the clean gate runs, not switched on mid-gate.
- **`python -c` / `node -e`:** no longer refused. The harness saves the snippet
  as a recorded `tmp-` file in the project and runs that file.
- **LF.46** (the memory kept across agent rebuilds) is removed: it moved no
  measured number.
- **Recording the specification's model calls** in the transcript: after the
  gate comparison, with a ledger note (it changes what the KPIs count).
- **Kept as they are:** a regression test for every fix (LF.49 made the reason
  accurate); `tests/brief_medium.md` unchanged (its repeated criteria stay, for
  comparison with the baselines); the severity policy, browser coverage and the
  CLI UI/UX consult; the sandbox's configured memory limit (LF.50 gives Node
  packs 4 GB).
- **Yes:** `loop.sh nightly` in cron; the start page leaves "use the frontier
  model" unticked when no frontier model is configured.
- **Group 2** starts after the two clean gate runs.

The decisions below that these settle are marked; the rest stand.

- **The thinking budget** (thinking effort / thinking mode per role). This is
  the biggest time lever (§2.4).
- **Whether every fix must add a regression test.** A run-7b219f82 attempt
  failed over a code-review defect two fixers left without one.
- **The CRITERION severity policy** (minor vs blocking grading).
- ~~**The `node -e` policy.**~~ Settled 2026-10-20: run from a recorded `tmp-` file.
- **Whether a browser test must cover every action the brief names.**
- **Whether CLI products get the UI/UX consultation.**
- **Deleting the `harness-test` account** when the loop ends.

**Parked** (details in monitoring §0.5.1):

- A milestone review may ask for later sprints' work to be removed.
- The plan check's action table has no persistence: sprint 1 may build storage
  early, which is minor.
- A scaffold whose smoke test fails twice leaves its files unkept, though
  their comments say the harness keeps them.
- A stage's own notes (`blocker.txt`, `verification.log`) may ship in the
  product.
- Wildcard arguments are not expanded, because commands run without a shell.
- Tools are offered when command execution is disabled.
- `test/` and `tests/` suites are duplicated.

**Throughput** (monitoring §0.9). Proposals measured but not built:

- two-step lead planning;
- per-role reasoning effort (the owner's setting);
- one sprint for a small brief (conflicts with the product design).

In parallel mode with auto-approve, gated calls pause and drain one per
superstep. Fixing that would be a redesign of the runner's auto-approve loop,
not a fix.
