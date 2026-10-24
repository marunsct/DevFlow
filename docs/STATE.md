# State of the loop

The one file every session reads first (plan MF.6). At most 150 lines, rewritten, not
appended: what is live, what is off, the last three runs, the next action. Everything
else is reference - `docs/HANDOVER.md` (rules, accounts, commands), `docs/monitoring-handover.md`
(mechanics and the run log), `docs/improvement-plan.md` (the plan). Narratives older than a
week are in `docs/archive/`.

**As of:** 2026-10-24 01:00 JST.

## Live now

| | |
|---|---|
| Run | **run-2b891f3f** (tasks-api gate, Ornith-1.5-35B-A3B, all switches on, harness 2744a74 -> bfc8bfb at 00:34 -> 413a4d3 at 00:59 JST, mixed_versions) started 23:54 JST after the owner's reboot. LF.247 and LF.248 (an in-place revision is given each section's schema: an empty section had no form and the reply's records failed to join) deployed mid-run (an in-place spec revision was dropped for an empty-list section: 9.5 min lost, then a full rewrite). Before it: run-c6d33923 cancelled 23:14; LF.241-LF.246 deployed (diagnosis state, cancel, settings page naming, no image to a server without vision). Owner's Ornith diagnosis kept: tier standard 0.667, guides keep_to_role + one_program_a_command. |
| Frozen | none - the baseline is not a Measure run; Measure pair 4 (f8b3c82a) ended at run 1 |
| Model | **Ornith-1.5-35B-A3B** (owner, ~23:15 JST) at :8888, 3 slots, 262,144 tokens; reply ceiling the deployment's own; vision off (server). Diagnosed 23:32 JST: tier standard, 2 guides on; reasoning_effort=none honoured. |
| Owner's model settings | the owner's; never changed by the loop |
| Peer sessions | none since 04:57 JST 2026-10-23 (this session, langchain-90, drives alone) |

## Last runs

- **run-2b891f3f** (first Ornith run, tasks-api, 2744a74 -> 57e55c04, mixed_versions): **completed 05:35 JST 2026-10-24, hidden 10/10, quality 7/7**, locked suite 39/0, 226 active min, 998k output tokens, 159 calls, 97% model busy; 7 harness defects fixed in it (LF.245-LF.252), batching tried and refused (WB.2), reply ceiling 24,000 set from the tail. 8 release gaps, 7 of them locked tests over-asserting error text.
- **run-85ad15b0** (first QM.2 run, 1f30088f): **cancelled 09:21 JST** under MF.4's major-bug rule, hidden 0/10. Gunicorn listened but its routes were never served; the readiness request's 404 was cut from the start excerpt, the defect read "does not start", and four fixes over two sprint attempts rewrote start-up and hashing (each reverted). LF.221 fixed and deployed (0df9ec3c); QM.2 never got to act.
- **run-1409658f** (1246bb22, all-on baseline): **completed 08:12 JST, hidden 10/10**, quality 6/7, mutation 0.667, 81 active min, 180 calls, 458k output tokens, 0 lost replies; sprint 1's first attempt left 4 defects open (KPI flag) and its replan fixed them.
- **run-77f7752f** (1246bb22, not mixed): **completed 06:38 JST, hidden 10/10, quality 7/7** (best quality yet), 98 active min, 147 calls, 545k output tokens, 2 lost replies. **Mutation regression: 0.333 vs 0.708 mean** - 4 `True->False` success-flag mutants and `or`/`and` flips in app.py/models.py uncaught; direct evidence for turning on QM.2 (mutation-guided tests, still off).
- **run-f13f7438 and run-8cced4a9 are the gated pair**, both on 1246bb22, hidden 10/10 each. run-8cced4a9 ran the whole way on 1246bb22 (not mixed); run-f13f7438 likewise (1246bb22, not mixed) - **59 active min**, 133 calls, 337k output tokens, 0 replies lost, 0 tool failures, quality 6/7, mutation 0.5; sprint 1 took 2 attempts (a unit test the fixers' writes kept failing), sprint 2 passed with no defect; first scored 0/10 by a half-built hidden-test runner (LF.219, built and fixed by the other session) - corrected. run-8cced4a9: 108 active min, 507k output tokens, 2 lost replies, quality 6/7, mutation 0.625; LF.214-class import fixed live; LF.217 (UI sprint counter) bundled. **Gate verdict: the all-on baseline holds 10/10 hidden on both, at 108 and 59 active minutes against 199-233 before.**
- **run-3bfd71ee** (a third all-on run, crossed by the two sessions' deploys: 1246bb22 -> bc153af (LF.219) -> 323e2f5 (LF.220), mixed_versions): **completed 03:21 JST, hidden 10/10**, quality 6/7 (20 items created at once: not all kept with their own ids), 100 active min, 195 calls, 511k output tokens, 1 lost reply. LF.220 (a fixer twice told its defect's tests pass is left only its answer) found and deployed in it by the other session. Mutation not taken: the two sessions' mutation runs collided.
- **run-bf8a972f** (shakedown 1, all 24 switches on, 07ef4de -> 9e881ff -> fc93ecd, mixed_versions): **completed 22:18 JST, hidden 10/10**, 140 active min (previous tasks-api runs 199-233), 715k output tokens (-33%), 2 replies lost to the cap (4-6), 247 calls. Sprint 1 took 3 attempts (a locked test contradicting the spec - dispute, QA repair; two identical rewrites reverted - LF.216); sprint 2 passed on its first measurement (AC-7 placed with the item routes). Bugs fixed live: LF.214, LF.216; bundled: LF.212, LF.213, LF.215. **LF.217 built 23:41 JST, bundled (UI only - never counted against a gate run's score):** fast delivery's sprint-planning path makes no model call, so the run page's sprint counter (counts `technical_lead` visits) silently skipped the sprint it opened; the next sprint's header wore the wrong number (owner screenshot, run-8cced4a9). Now narrates itself.
- **run-10d79850** (Measure pair 4 run 1, f8b3c82a): **cancelled 19:56 JST** by the owner's rule (no value left) after 206 min in sprint 1 attempt 2; hidden **4/10**. Sprint 1 could not pass AC-7 (its only test needs sprint 2's item routes - LF.202); 6 replies lost to the output cap (32 min, 23% of model time); a docstring read as an import put `of==0.0.1` in the manifest (LF.207).

## Built 2026-10-23 ~20:10 JST, pushed, not deployed (gate run 1 live): general model steering (MD.3)

Owner: guidance general, not per model; weaker models steered more; each guide its own switch; a settings
action to diagnose and save; keep growing the checks. Eight guides (`GUIDE_<ID>`, on in compose), eleven
stage-shaped checks, a steering profile per model (tier, chosen guides, owner overrides, end-of-request
reminder for weak models), Settings > Models "Diagnose this model and set its guidance". Deploy before gate
run 2, then re-diagnose LFM2.5 from the settings page (its profile then replaces MD.2's two kept lines).
MD.4 (research roadmap) planned.
## Built and deployed (b408660, 11:18 JST): model diagnosis and reply salvage (owner ~10:50-11:10 JST)

- **MD.1:** a model never seen is diagnosed at a run segment's start (and before the next call when the server's
  model changes): stage-shaped tool checks, reasoning cost per switch, recall, the fitness and edit probes. Kept in
  `DATA_DIR/model-fitness/<served name>.json`, applied (forced vs offered answers, reasoning switch), shown by
  `loop.sh ready`; `loop.sh diagnose [--again]` by hand. ~2.5 min once per model.
- **RS.1 `REPLY_SALVAGE` (on, per model as measured):** a reply cut off at the cap is finished from its own reasoning
  (owner: no reasoning cap - it costs accuracy); cut-off text is continued.
- LF.224 (qwen3-coder names), LF.225 (a model swap is a server change), LF.226 (fitness file merged, not rewritten).

## Built and deployed (b408660, 11:18 JST): small and large codebases (owner 10:2x JST)

Owner: the product must work on small and large codebases; where the two need different approaches, choose by
measured size at run time. Re-review of the DevFlow review (`docs/improvement-plan.md` M.2 LF.222-LF.223, rows
SZ.1-SZ.11). A small project is unchanged by every item but SZ.8. Not deployed: the live run would be mixed.
- Bugs: **LF.222** old `write_artifact`/`edit_artifact` arguments were never shortened (deepagents only knows
  `write_file`/`edit_file`); **LF.223** a reply cut off inside its code block was written as the file.
- **SZ.1 `OBSERVATION_FOLDING` (new switch, off):** old long tool results folded past half the window, in steps of 10.
- Size-gated, no switch: SZ.2 files over 24,000 characters fixed by SEARCH/REPLACE edits; SZ.3 runtime frames
  collapsed in over-budget output; SZ.5 listings/searches cut at 200 and say so; SZ.6 code graph cached, definitions
  in 8 more languages; SZ.7 walks skip dependency folders; SZ.9 overflowing maps ranked, left-out list capped at 60;
  SZ.10 no whole-project read at a stage's start under the memory; SZ.11 long files read whole return a window.
- **SZ.8 is not size-gated:** a file named two or more folders down is now found (fixes and drafts may get more files).

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

0. **Now (2026-10-24 19:54 JST) - owner away for a long time, hands off until ~11-01 14:35 JST; pointers are reviewed, not built straight away; ship only through `loop.sh ship "<msg>"`.** Model: **openai/gpt-oss-20b on LM Studio :1234** (owner's; window 131,072; no /props; string tool choices only; tier standard 0.778, structured answers required). **run-06546eb9** (first gpt-oss baseline, tasks-api, workers wrote the product from a FastAPI pack): crashed once on a harness bug (LF.264, git output not UTF-8; fixed, deployed, resumed), then **cancelled 17:48 JST, hidden 1/10**, locked suite 5/28, 13 defects open, sprint 1 five attempts and none closed: fixers cannot repair cross-module faults. **run-2f73386c** (notes-api-hono) was cancelled 18:08: the model pick of a library setup had never worked (LF.265, a TypeError hidden by a broad except; now picks the Vitest+Playwright Hono entry) and a rewound run skips replay (it re-enters setup as a resumed stage), so a fresh run **run-73e5c929** (notes-api-hono, gpt-oss) FAILED 18:30 JST: the library pick worked but the Hono entry could not replay (its smoke test imports product code; SP.2a), the setup agent invented `hono/testing` `createTestClient`, and the acceptance suite could not run in 5 rounds - nothing built, not scored. Fixes from it: LF.264 (git bytes), LF.265 (model pick TypeError), LF.266 (Node memory room, exit 133). **run-ec0c9589** (notes-api, Python pack, gpt-oss, 18:37-19:43): stopped by escalation count, but **hidden 9/9** (score 1.0): 17/18 criteria passed (the 18th a test flaw, deferred), the model's own unit tests would not pass and each release hold used an escalation. **RL.1 (57bb8b51, switch RELEASE_WITH_FAILING_UNIT_TESTS, on in compose, owner away): such a product is now released with the failing unit tests as a named gap.** **SP.3a Hono pack node-hono-api** (4ca11392) deployed with it. **run-314376ee** (notes-api-hono, Fast, 57bb8b51, started 19:53 JST) is live: the first Hono run with a pack. Open: closed run-and-fix loop for workers (SP/SW rows), fixer shown the failing line and declared type, pack-first setup; stopping-when-tests-pass and answer-as-a-call fail 0/3 on this model; reasoning_effort low on gpt-oss not measured; the milestone review's grading of an unbuilt deliverable. Product review doc updated with this run.
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
|---|---|---|| 2026-10-21 to 10-24 (langchain-90) | LF.119-LF.252, CM.1-3, EF.11, AY.2, PH.1-4, CG.1-3, RL.1-3, SZ.1-11, RS.1, MD.1-MD.7, WB.2 (off), WB.8, WB.9, MF.1/3/5 | taken over 10-21 14:18 JST; owner hands off from 10-24 02:35 JST |
