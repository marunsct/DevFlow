# 06 Gates, reviews and release (HR2.G) - second review, 2026-11-08 JST

Reviewer scope: code_review, security_review, advice_review x4, milestone_review (+ M7 `MILESTONE_EVIDENCE_GATE`),
sprint_advance, the last-sprint brief check, release (`src/app/graph/delivery.py`), escalation, change_request.
Everything below is read-only evidence; nothing was written under `src/`, `docs/`, `tests/` or a workspace.
Work files: `scratchpad/review2/work06/` (transcript extraction: `extract.py`, `aggregate.py`, `strict.py`,
`facts40.jsonl`, `agg40.txt`), `work06b/` (scanner runs, 5 copied products, `out/`), `work06c/` (research notes).

## 1. What exists

| Stage | Code | Kind | Notes |
|---|---|---|---|
| code_review | `workflow.py:12837` | LLM; a finding gates only if `engineering.what_shows_it` ties it to a failing test/check/underline | off in fast delivery |
| security_review | `workflow.py:11940`, `agents/security_reviewer.py:32-84` | LLM, structured `SecurityReviewOutput`; categories `isolation, permissions, data_leakage, secrets, external_integration, filesystem, command_execution, timeouts, checkpoint_recovery, audit_trail, retention` (`:42-54`); `_WORTH_REVIEWING` js/ts/py/html/json only (`:84`) | cannot block; findings are injected into the milestone request (`workflow.py:12236-12240`) |
| advice_review x4 (backend, database, security_reliability, ui_ux) | `workflow.py:12116`, `agents/advice_review.py:41-60, 84-137` | LLM, `AdviceReview{not_built[], design_problems[]}`; the request carries the sprint's changed file *names* (`:11-18`) | cannot block; all findings go to the milestone review |
| milestone_review | `workflow.py:12205-12700`; `_findings_that_block` `:5400-5440`; nine post-hoc filters `:7559, 7722, 7777, 7825, 7886, 7930, 8275, 5322, 5710` | the only LLM gate in fast delivery; then deterministic gates: red suite (`_a_red_suite_the_review_called_green`), `due_criteria_failing`, `definition_of_done_gaps`, last-sprint brief check `_a_brief_requirement_the_run_never_built` (`:7994`) | fast delivery: one send-back, then `record the findings as risks and go on` |
| M7 `MILESTONE_EVIDENCE_GATE` (LF.687, G3) | `graph/milestone_evidence.py`, `workflow.py:5354-5367` | blocking findings gate only when `what_shows_it` returns a reason | OFF (`docker-compose.yml:50`); measured 0 on-arm runs |
| release | `delivery.py:207-447` | deterministic: naming-back-to-QA, last try on deferred, locked suite, vacuous green, own-start (`:229-259`), production build (`:264`), unit tests (`:269-283`), handoff and secrets hold (`:287-297`), ~20 gap sources (`:352-421`), `completion_verdict.split` (`:428`) | `MAX_RELEASE_ATTEMPTS=2`; `RELEASE_DOCS_REQUIRED` and `RELEASE_AUDITS` are ON through `PREMIUM_DEEP_VERIFICATION` (`switches.py:92`, `docker-compose.yml:46`) |
| handoff writer | `stacks/release_docs.py:194-258` (`complete_the_handoff`), `:107-120` (`_the_product_s_documents`), `:136-147` (`_routes_not_named`), `:150-183` (`what_the_handoff_lacks`) | writes "## Running it" and a route table only for routes no document names | the document set includes the workspace's `docs/**/*.md` minus five harness names (`:37`) |
| audits | `stacks/release_audits.py:360` (`secrets_found`, six shapes), `licence_gaps`, `AUDIT_COMMANDS` per language into the generated CI (`:333`) | no SAST; the dependency audit runs only in CI, never in the run | |
| verdict | `completion_verdict.py:27-57` | regex: 14 note kinds; every other kind blocks | consumer: `NON-DELIVERABLE.json`, bench export, dashboards |

Today's fixes in this area: LF.670 (`_no_unit_tests_ran` re-measures an empty report, `delivery.py:639-646`), LF.671
(a probe's finding settled by the probe), LF.676 (reused measurement still runs the own-start check: falcon 6
shipped 0/9 before it), LF.687 (M7 built, off). No stage names "release" in any transcript: the release makes no
model call (release decision minus last transcript record: median 0.2 min, max 2.3, 37 runs).

## 2. Measured

### 2.1 Completion gaps vs hidden failure (extends G1; 260 scored runs, 204 full / 56 partial; last 40 runs = 11-05 to 11-07)

Verdict as a classifier of "lost a hidden test" (`completion_verdict.split` on `data/bench`):
all runs precision 0.16, recall 0.36 (older partial runs carry no gaps at all); last 40: precision 0.21, recall 0.83,
base rate 0.15; 24 of 40 runs labelled blocking, 19 of them scored 1.0. Of the 30 `false_acceptance` runs, 20 are
labelled blocking. Gap counts on the last 40: median 5 per run, max 14; 3 runs with none.

Precision per gap kind (runs carrying the kind; partial = scored < 1.0; base rate 0.22):

| Gap kind | Runs | Partial | Precision | Verdict today |
|---|---|---|---|---|
| N contract line(s) not checked at release | 156 | 23 | 0.15 | note |
| No review read the product's code | 62 | 10 | 0.16 | note |
| N own unit tests ship failing beside a green suite | 57 | 9 | 0.16 | blocks |
| At release the product does not keep its contract (probe) | 34 | 6 | 0.18 | blocks |
| Locked suite did not notice a deliberate change (all files) | ~110 | ~9 | 0.03-0.25 | note |
| AC ships deferred, unproven | 25+ | 7+ | 0.28 | blocks |
| Milestone findings recorded as risks | 12 | 3 | 0.25 | blocks if `[blocking]` |
| Escalation left a settled design finding open | 11 | 3 | 0.27 | note |
| Code the product does not run | 10 | 2 | 0.20 | note |
| Suite locked with "the brief narrows ..." still open | 6 | 3 | 0.50 | note |
| Setup never proven | 4 | 1 | 0.25 | blocks |
| Ships no unit tests | 4 | 1 | 0.25 | note |

No kind reaches 0.5 but one with six runs. The blocking kinds (0.16-0.28) are not more predictive than the notes
(0.03-0.27). This confirms the first review's G1 measurement from the other side: the split between "blocks" and
"note" carries no information about the hidden score; the information is in the false acceptances (Q area).

### 2.2 Milestone review (40 most recent scored runs; `work06/agg40.txt`)

- 29 of 40 runs had a milestone review; 49 verdicts: accepted 28, changes_required 21, blocked 0. Minutes in the
  stage: 85 total, median 2.7 per reviewed run. Send-backs: 12 (11 runs); a send-back cycle (re-plan, rebuild,
  re-review) costs median 13.5 min, 163 min over the 40 runs (4.1 min per run). 75-run partial set: median 15 min,
  485 min, max 83 min.
- 77 findings in changes_required reviews: blocking 9 / major 24 / minor 34 / suggestion 10; categories
  correctness 32, code_quality 26, security 14. Kinds: error handling 24, contract mismatch 18, style 8, test 6,
  missing feature 4, docs 3, harness files 1, other 13. Reach: 24 reached a builder or fixer, 23 the lead only,
  30 nowhere.
- **27 of the 33 blocking/major send-back findings restate an advice-review or security-review finding** (advice 8,
  security 6, both 13); only 6 are the reviewer's own. The milestone review is the enforcement arm of the advice
  and security reviews, not an independent reading of the code.
- Hidden score: sent back 0.98 mean (11 runs); reviewed, not sent back 0.889 (18; the two falcon 0/9 false
  acceptances are here, both *accepted* by the review); no review at all 0.966 (11). The review accepted both 0.0 runs.
- 9 changes_required verdicts were overridden: 3 "record the findings as risks and go on", 6 relabelled accepted by
  `_accepted_when_nothing_in_it_gates` (`workflow.py:5710`) after the nine filters demoted every gating finding -
  runs 7aa9533c (fcntl never used), a9f73836, adae4da8, bc931812, 8374fd12, 7c0b4466 - with nothing recording
  which filter did it. The filters only `logger.warning`; none writes to `.harness/check-findings.jsonl`
  (`workflow.py:7559-8300`). Their precision is unmeasured, as the first review's finding 1 says of every text filter.
- 11 runs had no review because the only sprint closed through the escalation decision ("accept the sprint with its
  open problems recorded as known issues" x6, "defer AC-n" x2) or had no decisions at all (3); the escalation path
  skips security, advice and milestone reviews entirely, which is what the "No review read the product's code"
  note (62 runs, 24%) records. Those 8 runs scored 1.0 x6, 0.875, 0.75.

### 2.3 Advice reviews (40 runs)

207 calls, 145 outputs, 9.2M input / 1.05M output tokens; 190 min total, **median 6.2 min per run** (max 16.4) - the
largest review cost. 134 findings in 21 runs (median 3). Reach: all 134 enter the milestone request; 56 (42%) reach a
technical-lead request; **24 (18%) reach a builder, fixer or defect** (shingle match: a lower bound); 78 (58%) go no
further than the review. No advice finding is a defect record.

### 2.4 Security review (40 runs, plus scanners on 5 stored products)

- 28 of 40 runs; 48 outputs (29 findings / 19 passed); median 2.0 min per run (64 min total). 81 findings: critical 1,
  high 8, medium 33, low 32, info 7; categories data_leakage 19, retention 15, isolation 12, audit_trail 11,
  checkpoint_recovery 10, filesystem 8, permissions 6. 24 (30%) reached a builder/fixer, 14 of them through a fixer's
  revision text; none is a defect record of its own.
- Scanners: the worker image has no semgrep, bandit or eslint (`work06b` report). On five 1.0-scored products
  (tasks-api, notes-api, notes-api-falcon, bookmarks, web-todo; host venv bandit 1.9.4 + semgrep 1.184.0): bandit
  medium+ = 5 findings in total, all B310 `urlopen` in the harness's own `acceptance/conftest.py:56` fixture (false
  positive) or B108 `/tmp/notes_data` default (one real but minor); semgrep `p/default`+`p/owasp-top-ten`: 3, the
  same urllib line. Low tier: 598 `assert` in tests, 26 test passwords. **Ten distinct rules fired, no injection,
  authz or crypto finding on either side.**
- The LLM review's five distinct findings on those products are all spec-conformance: a missing global exception
  handler (true, fixed next sprint), `done: bool` lax coercion (true, duplicated by the milestone review as DR-15), a
  shutdown handler (wrong: connections close per request, `main.py:59-69`), a sort tiebreaker graded "medium /
  retention" (an ordering nit), a 422 echoing `exc.errors()` (FastAPI's default). Net: 2 real spec defects, 1 harmless,
  2 wrong severity/category; 0 security vulnerabilities. Only the last pass survives into `docs/security_review.md`.
- Three of five reviews say "over part of the source": the unit-test file did not fit and the reviewer was told to
  open it; in one run it opened only two `tmp-inline-*` scratch files instead.

### 2.5 Release docs (same 5 products; stranger's start test)

Every README is the 12-14 line template `complete_the_handoff` writes ("## Running it" + commands); every named
command exists. Install 5/5, start 5/5, tests 5/5; **port/URL 0/5, environment variables 0/5, routes or main
flows 0/5**. The route table is never written because `_the_product_s_documents` (`release_docs.py:107-120`) counts
the workspace's `docs/acceptance_criteria.md` and `docs/specification.md` as the product's documents - they name
every route, so `_routes_not_named` returns nothing and the README stays route-less even for a product handed over
as its project directory alone. `PORT`, `HOST`, `DATA_DIR` (read by all four services via `${PORT:-8000}` in
`start.sh`) and `ACCEPTANCE_PORT` are never named. `sh start.sh` execs the server, so the README's lines cannot be
pasted top to bottom; the Playwright suites need `npx playwright install --with-deps chromium`, said only in the CI
workflow outside the product. Three of the five 1.0 products carry `NON-DELIVERABLE.json` beside a release page that
reads as a plain success.

### 2.6 Release gate, escalation, brief check, change requests

- Release decisions (40 runs): release 37, "fix the failing criteria first" 1 (own unit tests failing, released on
  the next attempt), "fix the handoff first" 0. Held back 2 of 68 in the first review's window.
- `escalation`: 28 of 40 runs, one 0.0-0.2 min call each, every request a design-review contradiction ruling;
  `escalation_accept` never appears in any transcript. decisions.json `escalation` points: 14 in 12 runs.
- Brief check (`_a_brief_requirement_the_run_never_built`): 2 firings in the last 40 (both scored 1.0), consistent
  with the first review's 6 of 6; LF.648 covers the measured case.
- change_request: no scored run used it (the approval mode is off in the loop); the code path is unchanged.

Recurring notes totalled: "N contract line(s) not checked at release" on 156 of 260 runs (60%) - the single most
common gap, a note, and a Q-area cause (probes that cannot shape a request); "the locked suite did not notice" on
~110 runs at 0.03-0.25 precision - a note that is right to be one.

## 3. The first review's items in this area

| Item | Status | Evidence and judgement |
|---|---|---|
| G1 verdict calibration | NOT BUILT, measured (first review); **confirmed per kind here** | no gap kind predicts a hidden failure above 0.28 (one at 0.50 on 6 runs); relabelling cannot help. Reshape: stop treating the verdict as a classifier; show each gap with its measured precision (HR2.G.3). |
| G2 brief check | covered by LF.648 | 2 more firings on 1.0 runs in the last 40; keep watching; demote to a note if the next firing is on a 1.0 product again. |
| G3 / M7 evidence gate | BUILT behind a switch, OFF, 0 on-arm runs | new evidence changes the expectation: 27 of 33 blocking/major send-back findings are advice/security restatements that no test shows, so M7 on will remove most send-backs (~4 min/run and 13.5 min per cycle). The 2 real findings on the 5 products (exception handler, bool coercion) were spec items a contract line could show. Run the on arm now. |
| G4 scanner + ASVS | to build; **reshape** | measured yield on 5 products: 0 real vulnerabilities from bandit/semgrep, 10 rules, the medium ones in the harness's own fixture. The scanner belongs in the generated CI beside `AUDIT_COMMANDS` and in the release audit as a note, not as a run-time gate; its value is on larger and brownfield codebases (E3), where it must be measured before any defect is raised from it. The LLM review's real yield is spec conformance: see HR2.G.2. |
| G5 advice merge / advice into contract lines | to build; **reshape toward the second form** | advice costs 6.2 min/run and 18% of findings become a change; the milestone review re-raises them. Fold the four reviews into one call on the changed files is the cheap half; the measured half is to make `not_built` items contract lines at spec time (Q/D area) so a test, not a review, shows them. |
| G6 deferral hole | NOT BUILT on evidence (first review) | consistent here: deferred ships at 0.28 precision; `last_try_on_deferred` (`delivery.py:237-239`) is the right lever. |
| "Keep every deterministic gate" | right | the two 0.0 runs were caught by nothing until LF.676 re-ran the own-start check; the reviews accepted both. |
| "code review stays off" | right | no new evidence. |

What the first review missed: (a) the milestone review is mostly re-enforcing advice/security findings, so G3 and
G5 are one measurement, not two; (b) the nine milestone filters silently decide 6 of 21 changes_required verdicts
with no record (finding 1 applied to this stage); (c) the handoff check is satisfied by the harness's own spec
documents, so the route table it was built to write (LF.189) is never written; (d) the escalation-closed sprint
skips every review and produces a quarter of the "no review read the code" notes.

## 4. Research (dates and sources in `work06c`; one line each)

- SonarQube "Sonar way" (docs, Server 2026.5): four deterministic conditions on new code - 0 new issues, 100% of new
  hotspots reviewed, coverage >= 80%, duplication <= 3% - with a 20-line "fudge factor" before ratio conditions fire;
  the 2026 "Sonar way for agentic AI" gate tightens severities and adds dependency risk, still with no opinion
  condition. Fit: gates on the sprint's delta with a size floor; an LLM verdict is not a gate condition anywhere.
- GitHub (docs; changelogs 2025-09-10, 2025-10-28, 2025-11-20, 2026-08-07): merge queues and rulesets block only on
  named required checks and code-scanning alerts above a severity; Copilot review "does not count toward required
  approvals" by default and now surfaces CodeQL/ESLint/PMD findings beside its own; Code Quality stopped auto-adding
  Copilot as a reviewer. Fit: the LLM explains tool findings; it does not gate.
- Semgrep (blog 2025-01, 2025-09-10, 2025-12): Assistant agrees with researchers 96% on true positives but 41% on
  false positives; it auto-triages ~60% of findings only above a confidence and only to *dismiss*, with human-approved
  memories; for agent code Semgrep recommends a deterministic stop-hook scan and fix-until-zero loop, not an LLM
  security opinion. Fit: an LLM may add findings, never clear a scanner's.
- OWASP ASVS 5.0.0 (May 2025): 17 chapters, ~350 requirements, three nested levels; L1 is the automatable layer
  (encoding/validation V1-V2, communication V12, configuration V13, data protection V14, logging V16); V6-V10
  (auth, session, authz, tokens) need scenario tests; V15 is review-only. Fit: the security review's categories should
  be ASVS ids and most of them should be acceptance-style tests, not a reading.
- DORA 2025 (2025-09-24) and the AI Capabilities Model (2025-12): AI raises throughput and still lowers stability; the
  seven capabilities include small batches and strong version control, not review. Fit: the harness's analogues are
  hidden pass rate per sprint (change-fail), send-backs (rework) and wall time (lead time).
- LLM review precision 2024-2026: Google AutoCommenter ~40% resolved; Mozilla/Ubisoft RevMate 7-8% accepted,
  functional comments ~5%; Meta MetaMateCR 19.7% applied and reviews >5% slower with AI patches; CodeRabbit in the
  wild (arXiv 2607.03316) 36% accepted / 56% rejected; PATCHEVAL (2025-11) LLM judge ~80% consistent with tests;
  DeepSWE (2026) the judge over-approves 19-28%; SWE-bench Verified audit 7.8% of passing patches fail developer
  tests. Fit: our 0.16-0.23 verdict precision and 18-30% finding reach are the ordinary regime of unverified opinion.
- Agent products (Cursor Bugbot, CodeRabbit, Greptile, Devin Review, Qodo; docs 2025-2026): every default is
  advisory (neutral status, `fail_commit_status: false`, strictness thresholds); blocking is opt-in and deterministic
  (required checks, docstring coverage, secrets); none generates a README - they generate a PR summary. Vendor
  benchmarks: best catch rate 82%, critical 58% (Greptile 2025-07); precision 64-96% on curated bug PRs (Signal65
  2026-03). Fit: keep reviews advisory; what ships is a summary plus deterministic checks.

## 5. New items

**HR2.G.1 - record what the nine milestone filters and the scope cap decide** (bug class: silent mechanism; always
on). Evidence: 6 of 21 changes_required verdicts in 40 runs were relabelled accepted by filters that only log
(`workflow.py:7559-8300, 5400-5440, 5710`); their precision is unmeasured. Change: each filter that drops or demotes
a finding appends `{check, finding fingerprint, severity before/after, reason}` to `.harness/check-findings.jsonl`
through `acceptance.check_findings.noted` (LF.678), and `loop.sh suite-checks` reports them with the suite checks,
so the first review's finding 1 gets numbers for this stage too. Test: a review with one blocking finding about the
harness's own files leaves one recorded demotion; fails on the old code (no record). KPI: demotions per run, share
later contradicted by a defect. Size S. Risk none.

**HR2.G.2 - the security review becomes a spec-conformance pass with ASVS ids, and its real findings are defects**
(quality fix; always on for the record shape; the ASVS mapping is a prompt change with the banned-word test).
Evidence: 81 findings in 40 runs, 0 vulnerabilities on 5 scanned products; the 2 true findings were spec defects
(exception catalogue, type coercion) that the milestone review raised again; the 11 categories are an agent
harness's (`security_reviewer.py:42-54`). Change: (a) categories = ASVS 5.0 chapter ids (V1-V17) plus
`spec_conformance`; (b) a finding whose `affected_files` names a product file and whose description names a locked
criterion or contract line is raised as a defect record (F8 ids) through the test round, not re-read by the
milestone review; (c) the other findings are notes on the release page; (d) `_WORTH_REVIEWING` comes from the pack's
source suffixes (`seed.py`/pack table), closing the Go/Java/Ruby/PHP/Rust blind spot the first review named.
Test: a review finding naming AC-n becomes one defect record and the milestone request carries no security block;
fails on the old code. KPI: security findings that reach a fixer (30% today), duplicate findings across reviews
(both reviews raised the same bool-coercion defect). Size M. Risk: a defect raised from an opinion costs a fix stage;
bounded by (b)'s requirement that it name a criterion.

**HR2.G.3 - calibrated gaps instead of a label** (quality fix on the record; host side; always on). Evidence: no gap
kind predicts a hidden failure above 0.28; 19 of 24 labelled runs in the last 40 scored 1.0; `NON-DELIVERABLE.json`
sits beside three 1.0 products. Change: `loop.sh score` and the release page print beside each gap kind its measured
precision from `data/bench` ("preceded a lost hidden test in 7 of 25 runs"), computed by a small host script
(`scripts/loop/gap_precision.py`) that reads the kinds from `completion_verdict` fingerprints; the run's file is
named `COMPLETION-GAPS.json`, and the "may not work" sentence is kept only for the hard-evidence kinds (no start,
failing suite, unproven setup, failed build). Test: the script on a fixture bench directory yields the table; fails
on the old code (no script). KPI: none (reporting); it is the measurement G1 asked for, kept current. Size S.

**HR2.G.4 - the README names the port, the environment variables and the routes, whatever the workspace's docs say**
(bug: LF.189's route table never fires; always on, inside `complete_the_handoff`, which already runs under
`RELEASE_DOCS_REQUIRED` = on). Evidence: 0/5 READMEs name port, env or routes; `_the_product_s_documents`
(`release_docs.py:107-120`) counts `docs/acceptance_criteria.md` and `docs/specification.md` as the product's.
Change: (a) the document set for the route rule is the project directory's own files only (README and the project's
`docs/`), never the workspace `docs/`; (b) the route table is written from the locked contract whenever the project's
documents lack a route; (c) a "Settings" block lists the environment names the pack declares (`pack.env`, a new pack
attribute seeded from the pack's start script: `PORT`, `HOST`, `DATA_DIR` for the Python and Node packs; a custom
setup contributes what its `stack-setup.json` declares) with defaults and the URL the suite measured; (d) "Running
it" says the start command keeps the terminal and the tests run in another. Test: a workspace whose `docs/` names
every route still gets the table; a pack with `env` gets the Settings block; both fail on the old code. KPI: handoff
holds (0 today) unchanged; the five-product stranger test goes 0/5 to 5/5 on c, d, f. Size S. Risk none.

**HR2.G.5 - the scanner as a CI step and a release note, measured on the brownfield brief first** (reshapes G4;
doubtful; behind `RELEASE_AUDITS`, which already holds the dependency audit). Evidence: 0 real findings on 5 small
products; Semgrep's and GitHub's own practice is deterministic scan plus explain. Change: `SAST_COMMANDS` per
language beside `AUDIT_COMMANDS` (`release_audits.py:333`: bandit for Python, `eslint-plugin-security` or semgrep CE
where installed in the image), run once at release when the tool exists, findings of high severity as notes on the
release page and a CI step; never a defect until measured on E3's brownfield brief shows a true-positive rate above
0.5. Test: a pack with a SAST command adds the CI step; fails on the old code. KPI: true findings per run on the
held-out briefs. Size S. Risk: image size; the tools are installed only in the worker image, not in products.

**HR2.G.6 - one advice call with the diff, and `not_built` items as contract lines** (G5 reshaped; doubtful; switch
`ADVICE_ONE_CALL` in group `Review gates`). Evidence: 6.2 min/run, 9.2M input tokens over 40 runs for 134 findings
of which 24 became a change; 27 of 33 milestone send-back findings restate them. Change: (a) the four advice requests
become one request per sprint carrying the sprint's diff (`git diff --stat` + hunks for the changed files, capped),
answering the four roles' adopted advice in one structured reply; (b) each `not_built` item that names a route,
status code, field or command is appended to the interface contract as an unchecked line, so the release's contract
check and the probes, not the milestone review, show it (coordinates with D4 typed contract records). Test: four
adopted-advice items yield one model call and two contract lines; fails on the old code (four calls, no lines). KPI:
advice minutes per run, contract lines added, milestone send-backs. Size M. Risk: one long request on a weak model;
measure per tier.

**HR2.G.7 - M7 on arm now, and the send-back cycle as its KPI** (measurement; no code). Evidence in 2.2: a send-back
cycle costs 13.5 min median and the review accepted both 0.0 runs; M7 has 0 on-arm runs. Change: schedule 2 on-arm
runs per family on one SHA; report send-backs, minutes and hidden score; if no score falls, M7 becomes built in and
`_milestone_findings_that_block` loses the filters that `what_shows_it` subsumes (G3's "collapse the nine filters",
after HR2.G.1's record shows which ones still fire). Size S.

**HR2.G.8 - an escalation-closed sprint still gets the deterministic release evidence it skipped** (bug; always on).
Evidence: 8 of 40 runs closed the only sprint through the escalation decision and skipped every review; the "No
review read the product's code" note fires on 24% of runs and reads as a review failure when it is a routing fact.
Change: (a) the note says "the sprint was accepted at an escalation; no review ran" and names the decision id;
(b) the release page of such a run carries the known-issues list the escalation accepted beside the criteria table
(today `_settled_and_open` folds them into gaps with no link to the decision). Test: a state with an escalation
decision and no review stage yields the new wording and the linked list; fails on the old code. Size S. KPI: none.

**HR2.G.9 - the release re-measures with a fresh process, never a reused measurement, when any file changed after
the last suite run** (bug class; always on; generalises LF.676). Evidence: falcon 6 shipped 0/9 on a reused
measurement; `MEASURE_ONCE` has no off arm (M5). Change: `suite.run` at release compares the product's tree hash
with the one the reused measurement recorded; any difference (including `clear_the_code_of_command_lines` and
`_clear_the_throwaways`, which run *after* the suite at `delivery.py:343, 415`) re-runs the suite and the own-start
check before the gaps are written. Test: a workspace whose tree changed after the measurement runs the suite again;
fails on the old code. Size S. Risk: one extra suite run (~1-3 min) only when something changed.

Not proposed, with the reason: a code review in fast delivery (no evidence it would move the score; G3's data says
the opinion gate re-raises what advice said); blocking on scanner findings (yield 0 on the products measured); an
LLM-written README (every fact a stranger lacked is the harness's own: port, env, routes).

## 6. Priority order

1. **HR2.G.4** README port/env/routes (S, bug; stranger test 0/5 to 5/5; no run time) and **HR2.G.8** escalation
   wording (S) - ship together as one release-docs bundle; UI/record only, no clean-count reset.
2. **HR2.G.1** filter telemetry (S) - the prerequisite for collapsing the filters; then **HR2.G.7** M7 on arm
   (expected: send-back cycles 4.1 min/run to ~1, no score change; decides G3 for good).
3. **HR2.G.9** release re-measure on a changed tree (S) - the only item here that can stop a false acceptance.
4. **HR2.G.2** security review as spec-conformance with defect records (M) and **HR2.G.6** one advice call plus
   contract lines (M, switch) - together they remove most of the ~13 min/run the three reviews cost (advice 6.2,
   milestone 2.7 + 4.1 of send-backs, security 2.0) and give the two true findings per run a test instead of a reading.
5. **HR2.G.3** calibrated gaps (S, host) - reporting honesty; and **HR2.G.5** scanner as CI/note (S, switch) after
   E3's brownfield brief exists to measure it on.

Expected effect: 8-11 minutes of model time per run out of ~100 active (reviews from ~13 to 2-5), no hidden-score
loss expected (no review has shown one), one class of false acceptance closed at release (G.9), and a handoff a
stranger can start.
