# State of the loop

The one file every session reads first (plan MF.6). At most 150 lines, rewritten, not
appended: what is live, what is off, the last three runs, the next action. Everything
else is reference - `docs/HANDOVER.md` (rules, accounts, commands), `docs/monitoring-handover.md`
(mechanics and the run log), `docs/improvement-plan.md` (the plan). Narratives older than a
week are in `docs/archive/`.

**As of:** 2026-10-22 05:20 JST.

## Live now

| | |
|---|---|
| Run | **Measure pair 2, run 2: run-403f7479** - `benchmarks/tasks-api/brief.md`, `DELIVERY=fast FRONTIER=false`, started 05:19 JST on **20dcdfbe** (Fix batch 1), the same SHA as run 1. **No deploys into it** (MF.4) |
| Frozen | **20dcdfbe** for Measure pair 2 (039ad84 + LF.167-LF.170); later work - group 2 switches (off), LF.171 - sits above it, undeployed |
| Model | Qwen3.6-35B-A3B (owner, back from LFM2.5 at 21:19): 2 slots, 262,144 tokens; server sampling = Qwen's *precise coding* profile (temperature 0.6, top_p 0.95, top_k 20, min_p 0, presence 0, repetition 1.0, max tokens 32,768); DevFlow context 260,000, reply ceiling 32,768 |
| Owner's model settings | the owner's; never changed by the loop |
| Peer sessions | none drive this workspace; this session is the only one that edits, deploys and starts runs |

## Off until measured (group 2 switches)

| Switch | Items | Module |
|---|---|---|
| `SHARED_FACTS` | CM.1 judges read the builders' facts | `app/agents/shared_facts.py` |
| `DECISION_LEDGER` | CM.2/EF.11 contract lines, CM.3 reports, PH.2 attempt records | `app/agents/ledger.py` |
| `LOCALISE_FIRST` | AY step 1 one cheap call says where a defect is before a rewrite | `app/graph/localisation.py` |
| `FIX_CYCLE` | AY step 2 candidates from the fix's own model | `app/graph/bounded_fixes.py` |
| `VERIFY_AFTER_WRITE` | AY step 3 a fix stage's write followed by its defect's tests | `app/graph/verify_after_write.py` |
| `DEFECT_CALL_CAP` | AY step 4 at most 60 model calls per defect across attempts | `app/graph/defect_budget.py` |
| `WHERE_THINGS_STAND` | PH.1 the sprint's state at the top of builder/fixer requests | `app/agents/where_things_stand.py` |
| `STATE_AT_DISPATCH` | PH.4 files changed since the CI gate measured (inside PH.1's block) | same |
| `INTERFACE_CHANGES_NAMED` | PH.3 a builder's report names the interfaces it changed | `app/agents/interface_changes.py` |
| `ASK_SPECIFICATION` | CM.4 a bounded question to the specification, the architect on a miss | `app/agents/ask_specification.py` |
| `INTERFACE_CLASH_CHECK` | CM.3 join: a removed definition another work order still uses is a defect | `app/agents/interface_clashes.py` |
| `PROJECT_GRAPH_FIXES` / `PROJECT_GRAPH_BUILDERS` / `CODE_GRAPH_TOOL` | CG.2 / CG.3 code-graph neighbourhood for fixers / builders; CG.4 the `code_graph` tool | `app/analysis/project_graph.py` |
| `REGRESSION_CONTRACT` | BW.1 a seeded product's green tests are the first baseline | `app/acceptance/regression_contract.py` |
| `CHANGE_REQUEST_RUNS` | BW.2 a run seeded from a completed run's product | `app/server/change_request_runs.py` |
| `LESSON_DISTILLER` | RL.1-RL.3 lessons proposed from recorded defects, owner approves | `app/plugins/lesson_distiller.py` |
| `ASSUMPTIONS_GATE` | IN.1 open questions answered by recorded assumptions | `app/agents/assumptions.py` |
| `RELEASE_DOCS_REQUIRED` | PN.2 README with run commands and the routes it serves | `app/stacks/release_docs.py` |
| `RELEASE_AUDITS` | PN.1 secret scan, licence listing, dependency audit in CI | `app/stacks/release_audits.py` |
| `SCREENSHOT_RUBRIC` | EV.2 page screenshots scored on a fixed checklist, KPI only | `app/acceptance/screenshot_rubric.py` |

Each module's `ON_BY_DEFAULT` turns its items on for the before/after runs.

## The last three runs

| Run | Brief | Result |
|---|---|---|
| run-bf3f222f | tasks-api (Measure pair 2 run 1, 20dcdfbe) | completed 05:12 JST, ~240 min, 2 sprints (sprint 1 ~220 min, 14 fix stages; sprint 2 green at drafting), 40/40 inside, **10/10 hidden** - Fix batch 1's start.sh fixes held; KPI flags: 10 defects left open, 2 replies lost to length |
| run-aedcd228 | tasks-api (Measure 2, 039ad84) | completed 01:00 JST, ~120 min, 2 sprints, 21/21 inside, **0/10 hidden - false acceptance again**: the work orders rewrote start.sh to a bare `python` without the product's packages; 10/10 with `.venv/bin/python` |

No hidden tests exist for `brief_medium`: its results are hand audits (`loop.sh product`).

## Next actions

1. Measure pair 2 (20dcdfbe): score each run (`loop.sh score <run> tasks-api`), `loop.sh kpi`, then `kpi_ledger arms` 039ad84 vs 20dcdfbe. Pair 1 on 039ad84 scored 0/10 and 0/10 hidden, both from start.sh; LF.168/LF.169 are what pair 2 measures.
2. Done 01:10 JST: `loop.sh deploy 20dcdfbe` (Fix batch 1: LF.167-LF.170).
3. **Fix batch 2** (seen in gate run 2): **LF.171 built** - the opening request names the files the memory holds (24 of 142 tool-calling replies only re-read held files). **LF.172 built** - a service that crashes in every test's setup is one start defect, not one per criterion (Measure 2 run 1: six fixers, six left open). **LF.173 built** - a fix that made nothing pass and wrote a line the language service is sure fails is reverted (the same run: one fix wrote the `get_db_sync` crash and was kept). **LF.174 built** - a test run with the same counts as the last identical run and no file changed since says re-running shows nothing new. **LF.175 built** - a defect's own tests are judged by the tests carrying its criterion, not by the exit of the file they share (AC-9 left open while AC-8 failed beside it). **LF.176 built** - in a run a test this stage did not write cannot be moved out of the runner's sight (a fixer moved a drafted unit test to `.bak`). **LF.177 built** - timing, KPIs and stage usage pair each stage's parallel calls oldest first (they dropped all but one). Filed, not built: one fixer ran the same `__pycache__` clean three times in a row with near-identical reasoning (no repeat guard caught it); `find tasks-api` run from inside `tasks-api` (the working directory named again as an argument); redundant reads 56% (healthy 8-19%); the 11-test suite is thin for 16 criteria; dead `models.py`; the intake keeps both the paraphrase and the brief's line of each measure (9 measures for 5) - replace a close paraphrase rather than append. A role's command refusal for `pip` advises `pip install <tool>` in the same message, and `python3 -m pip install` then runs: make the hint and the rule agree (Measure 2 run 1, acceptance author).
4. Then group 2 as measured switch arms, one subsystem at a time - **first arm: AY (`VERIFY_AFTER_WRITE`, `DEFECT_CALL_CAP`, `LOCALISE_FIRST`)**: on Measure 2 run 1 fix stages took 95 of 132 model minutes (91% reasoning, 14 visits); one fixer's defect passed at call 20 and it went on 18 more calls fixing other fixers' failures. VERIFY_AFTER_WRITE's pass note now tells it to answer (2026-10-22) (table above - all built, all off), then the brownfield family `benchmarks/tasks-api-change` (owner 2026-10-21: never stop the testing). Not built: CG.5 (UI), BH preference, M.4; AY steps 5-6 deferred (plan says why).

## Measuring

- KPIs: `loop.sh kpi <run>` -> `data/kpi/<run>.json` and `data/kpi/ledger.csv`; each row now carries
  `harness_commits`, `mixed_versions`, `served_model`, `switches_on` (MF.1), `gate_wait_minutes`,
  `accepted_criteria` and the cost per accepted criterion (MF.3).
- Comparing two harness versions: `python3 scripts/loop/kpi_ledger.py arms data/kpi/ledger.csv
  <commit-a> <commit-b> [benchmark]` - runs of exactly one commit, at least two per arm (MF.5).
- A mixed-version run is never compared.
- Backups: `loop.sh backup` (nightly), `loop.sh backup --check`, `loop.sh restore <dir> <new-db>` (OP.3).
- Notices: set `NOTIFY_WEBHOOK_URL` / `NOTIFY_EMAIL` (+ `SMTP_HOST`) for stalls and long gates (OP.2).
- Across every run: `loop.sh patterns [since]` - reply health per stage family, fix outcome by bundle size, recurring failures; read it at each deep analysis (LF.152).
- Reader corpus: `loop.sh corpus` (sizes, changes), `corpus harvest <run>`, `corpus accept`; the suite replays `data/corpus` (RC).

## Rules that are never optional

`AGENTS.md`. In short: the model is the owner's (`loop.sh ready` must say ALL READY);
fixes are stack-agnostic (packs, `plugins/seed.py`, per-language tables); every fix has a
test proven failing on the old code; `loop.sh suite` green but for the three S3 tests;
commit and push after every change (`git push main harness-hardening-session`); no secrets
printed; the operator account only (`docs/HANDOVER.md` §3).

## Loop cost

Session reading at start, before this file existed: about 12,000 lines (MF.6). Now: this
file, then only what the next action needs. Each session notes its fixes and their cost here
when it hands over.

| Session | Fixes | Notes |
|---|---|---|
| 2026-10-21 (langchain-90) | LF.119-LF.170, CM.1-CM.3, EF.11, AY.2, PH.1-PH.4, CG.1-CG.3, BW.1-BW.3, RL.1-RL.3, IN.1, PN.1-PN.2, MF.1/3/5 | taken over from the earlier window at 14:18 JST |
