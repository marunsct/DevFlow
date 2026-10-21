# State of the loop

The one file every session reads first (plan MF.6). At most 150 lines, rewritten, not
appended: what is live, what is off, the last three runs, the next action. Everything
else is reference - `docs/HANDOVER.md` (rules, accounts, commands), `docs/monitoring-handover.md`
(mechanics and the run log), `docs/improvement-plan.md` (the plan). Narratives older than a
week are in `docs/archive/`.

**As of:** 2026-10-22 00:05 JST. Times are JST; containers and transcripts log UTC.

## Live now

| | |
|---|---|
| Run | **Measure gate run 2: run-aedcd228** - `benchmarks/tasks-api/brief.md`, `DELIVERY=fast FRONTIER=false`, started about 23:00 JST (FastAPI, 2 sprints, suite locked at 11 tests); at 00:00 in sprint 1's fixes. **No deploys into it** (MF.4) |
| Frozen | harness commit **039ad84** (source as 9218b3e6: everything through LF.166) |
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
| `INTERFACE_CLASH_CHECK` | CM.3 join: a removed definition another work order still uses is a defect | `app/agents/interface_clashes.py` |
| `PROJECT_GRAPH_FIXES` / `PROJECT_GRAPH_BUILDERS` | CG.2 / CG.3 code-graph neighbourhood for fixers / builders | `app/analysis/project_graph.py` |
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
| run-aedcd228 | tasks-api (Measure 2) | live |
| run-650d812f | tasks-api (Measure 1) | completed 22:49 JST, 80.7 min, 144 calls; 21/21 inside, **0/10 hidden - false acceptance** (start.sh rewritten to a Python without Flask); 10/10 with start.sh restored |
| run-f4f0030b | brief_medium | stopped at 15:08 JST in test round 2's fixes: 367 min, 383 calls, 1.66M output tokens, 13 fix stages, 1 of 13 criteria (5 of 34 tests); a findings run (LF.119-LF.140) |

No hidden tests exist for `brief_medium`: its results are hand audits (`loop.sh product`).

## Next actions

1. When gate run 2 ends: `loop.sh score run-aedcd228 tasks-api`, `loop.sh kpi run-aedcd228`, compare with run 1 (`kpi_ledger arms`), and update the end-of-run product review.
2. Then, with no run live and ALL READY: `loop.sh deploy 20dcdfbe` - **Fix batch 1**: LF.167 a rewriting fix never targets an ignored file; **LF.168 the suite starts a service through its `start.sh`**; LF.169 the architect is told the setup's `start.sh` works; LF.170 a held stage's command is held to its files (gate run 1 was a false acceptance: 0/10 hidden, 10/10 with start.sh restored). Then **Measure pair 2**: two tasks-api runs on that one SHA, no deploys; compare arms 039ad84 vs 20dcdfbe.
3. **Filed for Fix batch 2** (seen in gate run 2): one fixer ran the same `__pycache__` clean three times in a row with near-identical reasoning (no repeat guard caught it); `find tasks-api` run from inside `tasks-api` (the working directory named again as an argument); redundant reads 56% (healthy 8-19%); the 11-test suite is thin for 16 criteria; dead `models.py`.
4. Then group 2 as measured switch arms, one subsystem at a time (table above - all built, all off), then the brownfield family `benchmarks/tasks-api-change` (owner 2026-10-21: never stop the testing). Not built: CM.4, CG.4/CG.5, BH preference, M.4.

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
