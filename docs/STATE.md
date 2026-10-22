# State of the loop

The one file every session reads first (plan MF.6). At most 150 lines, rewritten, not
appended: what is live, what is off, the last three runs, the next action. Everything
else is reference - `docs/HANDOVER.md` (rules, accounts, commands), `docs/monitoring-handover.md`
(mechanics and the run log), `docs/improvement-plan.md` (the plan). Narratives older than a
week are in `docs/archive/`.

**As of:** 2026-10-23 01:50 JST.

## Live now

| | |
|---|---|
| Run | **run-3bfd71ee** - tasks-api, fast, all-on; started 01:40 JST on 1246bb22 by another session's loop cron (not this one - asked to stand down), then crossed the 01:47 deploy of bc153af (Fix batch 5: LF.218) and was resumed: **mixed_versions**, so not a gated run. Kept as a third all-on run. LF.220 (a fixer twice told its defect is fixed is left only its answer) deployed into it 02:30 JST. |
| Frozen | none - the baseline is not a Measure run; Measure pair 4 (f8b3c82a) ended at run 1 |
| Model | Qwen3.6-35B-A3B (owner, back from LFM2.5 at 21:19): 2 slots, 262,144 tokens; server sampling = Qwen's *precise coding* profile (temperature 0.6, top_p 0.95, top_k 20, min_p 0, presence 0, repetition 1.0, max tokens 32,768); DevFlow context 260,000, reply ceiling 32,768 |
| Owner's model settings | the owner's; never changed by the loop |
| Peer sessions | none drive this workspace; this session is the only one that edits, deploys and starts runs |

## Last runs

- **run-f13f7438** (gated 1, 1246bb22): **completed 01:35 JST, hidden 10/10**, **59 active min** (fastest of 3 all-on runs: 140, 108, 59), 0 tool failures, 0 lost replies, quality 6/7, mutation 0.5. No KPI regression. 1 gap: 218 lines of drafted routes/validate code never wired into app.py (release correctly flagged it; watch for pattern). LF.218 built, filed for next Fix batch (gated run, no mid-run deploy).
- **run-f13f7438** = **gated run 2** (1246bb22, not mixed): **completed 01:35 JST, hidden 10/10**, quality 6/7 (a whitespace-only title accepted), mutation 0.5, **59 active min**, 133 calls, 337k output tokens, **0 replies lost to the cap**, 0 tool failures. Sprint 1 took 2 attempts (a unit test the fixers' writes kept failing - `auth.py` imported `get_db` directly, bypassing the test's substitute); sprint 2 passed with no defect. First scored 0/10 by a half-built hidden-test runner (LF.219) - corrected. **Gate verdict: the all-on baseline holds 10/10 hidden on both frozen runs, at 108 and 59 active minutes against 199-233 before.**
- **run-8cced4a9** = **gated run 1** (owner 00:50 JST; ran entirely on fc93ecd, mixed_versions False, no bug found): **completed 00:17 JST, hidden 10/10**, 108 active min (faster than run 1's 140), 507k output tokens, 2 lost replies, quality 6/7, mutation 0.625. Bugs: LF.214-class import fixed live; LF.217 (UI sprint counter, bundled - never counted against the score, owner's rule). Gated run 2 runs on 1246bb22: fc93ecd -> 1246bb22 adds only measurement (QM.1), QM.2 (off) and a UI narration event (LF.217) - no change to what the model does.
- **run-bf8a972f** (shakedown 1, all 24 switches on, 07ef4de -> 9e881ff -> fc93ecd, mixed_versions): **completed 22:18 JST, hidden 10/10**, 140 active min (previous tasks-api runs 199-233), 715k output tokens (-33%), 2 replies lost to the cap (4-6), 247 calls. Sprint 1 took 3 attempts (a locked test contradicting the spec - dispute, QA repair; two identical rewrites reverted - LF.216); sprint 2 passed on its first measurement (AC-7 placed with the item routes). Bugs fixed live: LF.214, LF.216; bundled: LF.212, LF.213, LF.215. **LF.217 built 23:41 JST, bundled (UI only - never counted against a gate run's score):** fast delivery's sprint-planning path makes no model call, so the run page's sprint counter (counts `technical_lead` visits) silently skipped the sprint it opened; the next sprint's header wore the wrong number (owner screenshot, run-8cced4a9). Now narrates itself.
- **run-10d79850** (Measure pair 4 run 1, f8b3c82a): **cancelled 19:56 JST** by the owner's rule (no value left) after 206 min in sprint 1 attempt 2; hidden **4/10**. Sprint 1 could not pass AC-7 (its only test needs sprint 2's item routes - LF.202); 6 replies lost to the output cap (32 min, 23% of model time); a docstring read as an import put `of==0.0.1` in the manifest (LF.207).

## Owner 2026-10-22 18:40 JST: all improvements on

After Measure pair 4 run 1 completes: `loop.sh deploy` Fix batch 4 (LF.186-LF.190) with **every switch below on** -
`docker-compose.yml` now defaults all 24 to `on` (empty host value = on), so no export is needed and no later deploy
can turn one off - then start the next tasks-api run as the **all-on baseline**. Pair 4 run 2 is dropped. Mid-run
deploys are allowed again at a stage boundary, as soon as possible, for any defect that wastes harness or model
time (`loop.sh deploy` + `loop.sh resumed`; marks `mixed_versions`). Later, features are turned off one at a time
to measure the unproven ones (set `NAME=off` on the host before `loop.sh deploy`). Checked before the switch: the
whole suite with every switch on - the failures were the switches' intended behaviour, plus LF.189 and LF.190. **Owner 19:50 JST: start the baseline immediately after the run** (score, `loop.sh deploy`, ready, bench); the reasoning probe waits for a later gap: `loop.sh reasoning-probe run` (ten calls; changes no setting) - Measure 4 run 1 lost 32 of 140 model minutes (23%) to six fix-stage replies that reasoned to the 32,768-token cap with no answer; if a per-request `reasoning_budget` is honoured, cap fix-stage reasoning per reply (the spiral recovery already switches thinking off after one).

## Off until measured (group 2 switches - all default on from the next deploy)

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
| `STABLE_TOOLS` | PX.2 a withheld tool stays listed and is refused (prefix cache) | `app/agents/stable_tools.py` |
| `CANONICAL_MEMORY` | PX.3 memory and snapshot in the same bytes across a sprint's visits | `app/agents/canonical_memory.py` |
| `STEERING_AT_THE_TAIL` | PX.5 the owner's steering note after the transcript, not in the system message | `app/plugins/steering_at_the_tail.py` |
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
| run-ef034768 | tasks-api (Measure pair 3 run 2, fadd5a58) | **cancelled 16:18 JST** after 4 failed attempts at sprint 1 (unstable acceptance tests closed at dispatch and raised again - LF.185 - after LF.181/LF.184 cost attempt 1); its product still scores **10/10 hidden**; 29 defects left open, 6 replies lost to length |
| run-7e5c11af | tasks-api (Measure pair 3 run 1, fadd5a58) | completed 12:22 JST, 199 min, **10/10 hidden**; 5 fix stages (was 15-16), but 2 suite repairs (two broken locked tests) and 3 milestone reviews; 4 replies lost to length |

No hidden tests exist for `brief_medium`: its results are hand audits (`loop.sh product`).

## Next actions

1. **Measure pair 2 result (arms 039ad84 vs 20dcdfbe, tasks-api, n=2 each):** hidden 0/10, 0/10 -> **10/10, 10/10**; active minutes 101 -> 227 (+125%), model calls +61%, output tokens +137%, defect-fix stages +63%, defects fixed +133%, lost-reply output share 0 -> 10%, memory pointers +64%. Fix batch 1 turned false acceptances into real products; the cost is fix stages.
2. **Fix batch 4 (built, not deployed):** LF.186 - every stage and every drafted file told which manifests the install reads. LF.187 - an undeclared-package defect is settled by the reconciliation that raised it. LF.188 - a stage is given each project file once (the memory), not the memory and a snapshot (~24,000 characters per fix-stage call). LF.189 - under `RELEASE_DOCS_REQUIRED` the release writes the README's run commands and route table from the pack and the locked contract (a 10/10 product had no README: every release would have gone back to the lead). LF.190 - `DEFECT_CALL_CAP` counts nothing for an attempt with no start time (it counted every call under the stage's name). **LF.202** - a criterion is planned where a test of it can pass (sprint 1 spent ~75 min on AC-7, whose only test needs sprint 2's item routes). **LF.218 (2026-10-23 00:47 JST, gated run deep analysis)** - localisation ran twice per retry (candidates then a fallback rewrite asked the same question); now once, carried into both. **Deep review (19:25-20:00 JST, execution-based, seven reviewers, every finding checked): LF.203-LF.211** - the lead is told why a release was held; secret-scan placeholders/example files; assumptions recorded once; clash check import-line rule + re-check at settlement; answers.json lock. Filed, not built: linear-mode work orders diff against HEAD so reports/ledger misattribute and the clash gate is blind (fix: diff against a start snapshot); ledger block has no de-dup/supersession; graph neighbourhood cut mid-line and repeats the memory's defines; graph file rewritten every call; PEM fixtures under tests/ hold the release; no git or nested git ⇒ no secret scan; a README naming only the entrypoint passes. Also filed: a stalled stage's withholding lasts one call (stages run 2-3x past the notice); `load_dotenv` after the terminal tool's description is built (one prefix break per process outside compose); the tail is 3-4 consecutive user messages (strict templates reject it); `lessons_shown_calls` undercounts ~10x (reads only new messages); `evidence_runs` never grows; the auxiliary model client can block 6 min per call when unreachable; LF.202 counts `describe` titles as tests; `.env.example`-style README checks; linear-mode work orders diff against HEAD. **Group 2 review (2026-10-22 19:30 JST, five reviewers, every finding checked): LF.191-LF.201** - approved lessons never reached a prompt; false interface-clash defects; the code graph file committed into the review diff; empty specification answers; checks after failed writes; unchecked candidates; withheld tools run after an approval pause and their refusals uncounted; research tools under stable tools; release-docs false holds; parallel batches skipping the AY bounds; secret-scan false holds. Filed, not built: a change-request copy drops nested `target`/`venv` dirs and a failed seed blocks a retry; `loop.sh` has two `lessons)` cases; assumptions pile up when intake re-runs; README at the workspace root gets commands without `cd`; a resume resets the cap's start; 16 older `lstrip("./")` sites. Data: L-1/L-2 rules no longer name `bcrypt` (owner OK 20:13 JST; backup `/app/data/lessons.json.bak-20261022`); L-3 proposed, awaiting the owner. Done: when Measure pair 3 run 2 completed: approve lessons L-1 and L-2** (owner 2026-10-22 12:45 JST: after this run, so both Measure runs stay comparable) - `POST /api/lessons/L-1/approve`, `/L-2/approve`; then deploy Fix batch 3 with `LESSON_DISTILLER` and `CHANGE_REQUEST_RUNS` on (they do not change how the model works). Done 09:00 JST: deployed fadd5a58 (Fix batch 2); Measure pair 3 is running. **LF.185 built (Fix batch 3): unstable acceptance tests.** Measure 3 run 2, attempt 2: AC-1, AC-4, AC-5 closed at 14:32 JST by a passing re-measure at dispatch, then raised again at 14:54 with the only product change in between reverted - order- or state-dependent tests treated as product defects, fixers sent at them. Proposal: a criterion that passes and then fails on an unchanged product (same commit) is marked unstable and goes to a dispute/QA repair, not a fixer. Also: a unit test asserting 400 where the framework answers 422 for the same invalid input. **Measure pair 3 run 2:** attempt 2 also failed (14:54). Sprint 1 attempt 1 failed (14:03 JST) - its async unit tests needed `pytest-asyncio`, refused three times by the LF.184 bug. **Fix batch 3 (built, not deployed):** LF.181 - a package only `pyproject.toml` declares is undeclared when the install reads only requirement files. LF.182 - every service and full-stack suite writer is told the store is shared by every test. LF.183 - a fixer naming a locked test by its name (not its file) is read as blaming the suite, so a dispute is held. LF.184 - a rationale sentence mentioning "no external dependencies" no longer forbids installing the product; the refusal's advice follows the ecosystem. Seen live: LF.172 grouped Measure 3 run 1's start failure into one defect (2 raised, not 11) - two tasks-api runs on that SHA - then the AY arm (`VERIFY_AFTER_WRITE`, `DEFECT_CALL_CAP`, `LOCALISE_FIRST`) as the first group 2 arm.
3. **Fix batch 2** (seen in gate run 2): **LF.171 built** - the opening request names the files the memory holds (24 of 142 tool-calling replies only re-read held files). **LF.172 built** - a service that crashes in every test's setup is one start defect, not one per criterion (Measure 2 run 1: six fixers, six left open). **LF.173 built** - a fix that made nothing pass and wrote a line the language service is sure fails is reverted (the same run: one fix wrote the `get_db_sync` crash and was kept). **LF.174 built** - a test run with the same counts as the last identical run and no file changed since says re-running shows nothing new. **LF.175 built** - a defect's own tests are judged by the tests carrying its criterion, not by the exit of the file they share (AC-9 left open while AC-8 failed beside it). **LF.176 built** - in a run a test this stage did not write cannot be moved out of the runner's sight (a fixer moved a drafted unit test to `.bak`). **LF.177 built** - timing, KPIs and stage usage pair each stage's parallel calls oldest first (they dropped all but one). **LF.178 built** - a package manager's lookup (`pip show fastapi`) is never refused as a server. **LF.179 built** - Python stages are told PyJWT 2.10+ needs a string `sub` (the 401 behind 8 criteria in Measure 2 run 2). Candidate, not built: criteria that fail behind one shared layer (Measure 2 run 2: every item route answered 401 to a valid token, 8 criteria failing as `assert 401`, `KeyError: 'id'`, `KeyError: 0`) as one defect for that layer - needs a signature beyond the first message line. Filed, not built: one fixer ran the same `__pycache__` clean three times in a row with near-identical reasoning (no repeat guard caught it); `find tasks-api` run from inside `tasks-api` (the working directory named again as an argument); redundant reads 56% (healthy 8-19%); the 11-test suite is thin for 16 criteria; dead `models.py`; the intake keeps both the paraphrase and the brief's line of each measure (9 measures for 5) - replace a close paraphrase rather than append. A role's command refusal for `pip` advises `pip install <tool>` in the same message, and `python3 -m pip install` then runs: make the hint and the rule agree (Measure 2 run 1, acceptance author).
4. **Appendix 9 (2026-10-22 12:30 JST, owner's prefix-cache question):** BA absorbed by PX.1–PX.8 in `docs/improvement-plan.md` — measure prefix-break reasons first (PX.1, group 1), then canonical memory order / no clock, stable tools, append-only transcript, steering at the tail, compaction, slot affinity, with the snapshot side-car as a decision gate (PX.8). Nothing built.
5. Then group 2 as measured switch arms, one subsystem at a time - **first arm: AY (`VERIFY_AFTER_WRITE`, `DEFECT_CALL_CAP`, `LOCALISE_FIRST`)**: on Measure 2 run 1 fix stages took 95 of 132 model minutes (91% reasoning, 14 visits); one fixer's defect passed at call 20 and it went on 18 more calls fixing other fixers' failures. VERIFY_AFTER_WRITE's pass note now tells it to answer (2026-10-22) (table above - all built, all off), then the brownfield family `benchmarks/tasks-api-change` (owner 2026-10-21: never stop the testing). Not built: CG.5 (UI), BH preference, M.4; AY steps 5-6 deferred (plan says why).

## Measuring

- Quality (QM.1, owner 2026-10-22): `loop.sh score` also runs the quality set (`benchmarks/<b>/quality/`) and the mutation test; the ledger carries `hidden_score`, `quality_score`, `mutation_score`. run-bf8a972f: 10/10, 7/7, 0.6. **QM.2 built (2026-10-22), behind `MUTATION_GUIDED_TESTS`, off** - a survivor the hidden suite misses becomes a finding for the testing role, settled by the harness re-running the unit tests with the one change back in; never measured live yet.
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
