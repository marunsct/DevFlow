# Harness review (HR): every capability, measured, researched, planned

Owner request, 2026-11-07 10:4x JST: review all harness capabilities the way scaffolding was reviewed
(`docs/scaffolding-plan.md`) - current implementation, how leading products do it, what fits our harness - as
one complete workup. Six read-only reviews ran in parallel; each read the code (file:line), measured the 522
stored transcripts, `data/kpi/ledger.csv` (217 rows) and `data/bench` (248 scored runs), counted the LF rows in
its area, and researched products and 2024-2026 papers. This document joins them. Items are HR.<area>.<n>;
scaffolding stays SF.n.

## 1. Where the time goes

Busy model time, 157 runs since 2026-10-28 (fast delivery, linear dispatch):

| Area | Share | Per run (median / p90) |
|---|---|---|
| Acceptance suite (write, review, reopen, repair, dispute) | 27-37% | 21% median of model time; post-lock work 44.7 h > pre-lock 40.6 h |
| Defect fixing | 21-36% | 23 min / 92 min; agent-loop attempt 6.3 / 23.8 min |
| Design (architect, reviews, revisions) | 18-20% | 16.4 min of an 89-min median run |
| Planning (scrum master, technical lead) | 12% | 10.3 / 29 min - 2.6x the building it plans |
| Building + drafting | 8% | 3.9 / 32 min |
| Reviews (security, advice, milestone) | ~8% | advice 3.9, milestone 2.0, security 1.1 min |

Hidden-score outcome: 0.89 mean on pack runs, 0.82 on custom stacks; full-score rate by family 0.67 (fullstack)
to 0.88 (notes-api); 11.3% false acceptances overall, **21% on browser and full-stack runs**, 7% on APIs.

## 2. Five findings that cut across every area

1. **Point fixes have grown into layers of text heuristics, and the layers misfire.** The suite has 25 text-based
   "cannot pass" checks beside its one real oracle (the JS dry run); the milestone review needs 9 deterministic
   filters after its verdict; the write guards have 114 raise sites; the dispute quote guard needed four patches in
   a row. At least 19 LF rows in the acceptance area alone corrected an over-strict harness check (LF.628, 633,
   640, 641, 654, 656 tonight). Each patch was right; the shape - match text, then patch the false match - is not.
2. **Opinion gates do not move the score; execution does.** No LLM review shows a measurable lift in hidden score
   (milestone sent back 0.941 vs accepted 0.965 vs not run 0.941); reopened suites score the same as unreopened
   (0.886 both); runs that escalated design with findings open scored no lower (0.93 vs 0.87). What does move it:
   the locked suite, the dry run, contract probes, the build and start checks.
3. **Several mechanisms are built but not working, and nothing measures that.** Multi-candidate fixes: 3 kept
   fixes ever, 0 since 11-01. `SURRENDER_TO_REWRITE` (built in 11-05): all 8 empty budget-scale fix stages since were
   left open. LF.607's "the criterion's own failing tests": 61 of 625 fixer requests carry it; 521 still carry "the
   last failing command". The ledger writes an unreported cache as 0% (112 of 217 rows). A proven setup's pack is
   blind (scaffolding plan). NON-DELIVERABLE is right 16-23% of the time (100 of 179 full-score runs carry it).
4. **We ask models for whole artifacts again when a small change was needed.** 120 readiness resends and 42
   revisions each ask the lead for "the whole plan again" (median 4k, p90 21.7k tokens); revisions rewrite spec
   sections; the second design review reads the whole spec again and mostly finds new, not remaining, issues.
5. **The measurement cannot yet tell good changes from bad.** Hidden scores are at the ceiling (25 of the last 30
   runs scored 1.0 on 8-10 tests a family); 58% of ledger rows are mixed versions; one family is 42% of the ledger;
   fixes were written right after specific hidden failures (LF.569, 579, 599) on six briefs tuned for 217 runs.

## 3. Area by area (condensed; the full reviewer reports are summarised here)

### 3.1 Intake, stack and design (HR.D)
- Today: deterministic intake enrichers, `choose_pack`, consults, architect writes a 7-section core plus 3 parallel
  parts, bounded repair chain, LLM review + harness findings, in-place revision, escalation after 2 reviews.
- Measured: review 1 asks for changes in 87%; 69% escalate after review 2; only 16-19% of review-1 findings recur;
  blocking/major findings are 52% interface/contract, 23% the harness's own files, and review 2 is dominated by
  sections contradicting each other (LF.590: 19 of 31). 117 LF rows; ~15 are "the spec planned what the setup
  decides", each fixed by adding a fact to the prompt.
- Others: GitHub Spec Kit's read-only *analyze* consistency pass; Kiro requirements -> design -> tasks with EARS;
  Tessl links each requirement to its test; one review, then execution (Factory, Devin, Claude Code plan mode);
  self-refine research: gains come in round 1-2, later rounds regress.
- Fit: **D1** deterministic cross-section consistency check (limits, codes per route, env names, paths, start
  command) before the review, clashes to a targeted repair; **D2** the harness writes the setup-owned sections itself
  after generation; **D3** one LLM review plus deterministic gates (`DESIGN_SINGLE_REVIEW`, measured); **D4** typed
  interface-contract records instead of text lines; **D5** requirement-to-test links at design; **D7** stack choice
  as a pack id (coordinates with SF); **D8** fix the escalation count text (bug).

### 3.2 Acceptance suite and QA (HR.Q)
- Today: author, mechanical review (~51 checks, 13 pack hooks), LLM QA lead, lock, contract probes, reopen with
  per-test and per-run limits, disputes with a quote guard; mutation only for suites that drive no browser.
- Measured: lock median 7.3 min; 1.42 send-backs per lock, 47% hit the 3-round limit; 44% reopen after the build;
  disputes in 141 runs, 60% named a test; false acceptances concentrated in filtered-view actions and filters.
  301 of 653 LF rows (46%) are in this area.
- Others: Meta TestGen-LLM and Qodo keep a test only if it builds, passes repeatedly and adds coverage; SWE-bench
  validates tests two-sidedly against a reference; ACH targets mutants; Playwright isolates by fixture, not by rule;
  >47% of neural assertion oracles are false positives - measure them.
- Fit: **Q1** record every check finding with its outcome and demote checks below ~0.8 precision (bug, first);
  **Q2** isolation by a pack fixture (per-test namespace, `mine()` helper) replacing prose rules and four shared-count
  checks; **Q3** generalise the dry run to Python and retire overlapping text checks to notes once parity is shown;
  **Q4** validate the suite before the lock against a generated contract-conforming stub and a seeded-fault stub
  (switch); **Q5** targeted mutants for browser suites (switch); **Q6** executable dispute verdicts instead of quote
  heuristics; **Q8** relational assertions for list and filter criteria (switch).

### 3.3 Planning and building (HR.P)
- Today: scrum master with deterministic corrections; harness-made work orders in fast delivery until half the files
  exist, then the lead; readiness check resends "the whole plan"; drafting per file; dispatch; 114 guard sites.
- Measured: lead 3.24 plan replies per run; 120 readiness resends (top cause mechanical: a scoped file no work order
  lists); `edit_artifact` fails 33% in building; ownership refusals 27% of building failures; 176 of 182 builder
  deletes were the harness's own scratch files; 30% of draft calls are second drafts.
- Others: Cursor and Aider split plan from apply; whole-file is the most reliable format for weaker models and
  line-numbered diffs collapse (Diff-XYZ, matching our 41-44% `replace_lines` failure); CodePlan repairs a plan
  incrementally; multi-turn re-generation degrades.
- Fit: **P1** repair the plan (harness fixes mechanical readiness problems; the lead returns a delta keyed by label);
  **P2** re-plan work orders made from the failures (switch); **P3** edit format by model tier and file size (switch);
  **P4** ownership refusal becomes a `request_change` hand-off (bug); **P5** the harness deletes its own scratch files
  (bug); **P6** two draft candidates for files the compiler rejects (switch); **P7** readiness rules into the schema.
  The owner's work orders, templates, Sprint Record and the parallel/linear toggle are unchanged by all of these.

### 3.4 Test rounds and fixing (HR.F)
- Today: test round with three merge passes; per-defect fix with a 60-call cap, localisation, candidates or a
  one-file rewrite, then an agent loop (16-call cap), surrender to rewrite, revert on regression, disputes.
- Measured: fix stages median 8 per run; agent loop fixes 39%, leaves 44% open; candidates 0 since 11-01;
  acceptance defects 16% fixed but **57% closed without a fixer** (symptoms of one earlier cause); page-check defects
  17% fixed; 43 of 93 runs re-planned.
- Others: Agentless and CodeMonkeys sample several patches and select by regression tests; AutoCodeRover gains from
  spectrum-based fault localisation; the Debugging Decay Index: effectiveness falls 60-80% within 2-3 attempts and a
  fresh restart recovers it.
- Fit: **F1** find why candidates never win, then select the best by net passes and smallest diff, with diverse
  candidates (bug + switch); **F2** make `SURRENDER_TO_REWRITE` record wrote/declined and close the declining branch
  (bug); **F3** put the defect's own failing tests' output first (bug); **F4** fix in cause order - start, install,
  compile, unit, acceptance, page, mutation - re-measuring after the first two (switch); **F5** light SBFL feeding the
  localiser on larger codebases (switch); **F6** attempt 2+ as a fresh context with a reflection (switch); **F8** a
  stable defect id across rounds for outcome KPIs (bug).

### 3.5 Gates, reviews and release (HR.G)
- Today: deterministic CI gate; code review off in fast delivery; security, advice and milestone reviews (only the
  milestone review can send a sprint back); lexical brief check; deterministic release; regex verdict.
- Measured: no review lifts the hidden score; milestone send-backs cost +19 min; the brief check fired 6 times, all on
  products that scored 1.0; NON-DELIVERABLE precision 16-23%; the security review's categories describe an agent
  harness (isolation, audit trail, retention) and never look for injection, authorisation or XSS; its source filter
  skips Go, Java, Ruby, PHP and Rust.
- Others: SonarQube gates on a short list of measurable conditions on new code; LLM reviewers are ~50% precise and no
  product lets an AI comment block a merge alone; Copilot review runs CodeQL and linters and the LLM explains them;
  Semgrep gates agent writes by rules; OWASP ASVS gives checkable, traceable requirements.
- Fit: **G1** calibrate the verdict against hidden scores (probe gaps block only with the documented request shape;
  KPI test precision >= 0.6, recall >= 0.9) (bug); **G2** the brief check reads routes and needs a failing probe, or
  becomes a note (bug); **G3** a milestone finding sends a sprint back only when a failing test, check or probe backs
  it - the code review's existing rule - collapsing the nine filters (bug, measured on the 64 sent-back runs); **G4**
  security review on ASVS chapters with sources from pack tables, plus a deterministic scanner whose high findings
  become defects (scanner behind a switch); **G5** one batched advice review, or advice turned into contract lines
  (switch); **G6** a deferred criterion that has a locked test or is named by the brief blocks release until the
  escalation accepts it (bug). Keep every deterministic gate.

### 3.6 Context, runtime and evaluation (HR.C, HR.R, HR.E)
- Context: memory 30% of the prompt, spec 24%, tools 11%; reasoning 66-72% of output; on :8888 cache share 0.73,
  with 28% of uncached input from the opening changing; no decode-time constrained output (~103 LF rows of repair);
  a withheld tool called anyway is 22% of tool failures; `finish_reason=None` (6.7%) unclassified.
- Runtime: orphan gaps 61 h over 40 runs; every deploy pause cancels the call in flight (278 in 120 runs); the rewind
  bug's likely cause: points read across all branches of the history, and `update_state` without `as_node`.
- Evaluation: ceiling (see finding 5); mutation median 0.58 recently; only tasks-api has quality tests; no large or
  brownfield codebase in recent runs.
- Others: Manus (KV-cache hit rate as the first metric, mask tools instead of removing them, append-only prefix);
  Anthropic context engineering; llama.cpp GBNF/json_schema, XGrammar; LangGraph time travel via `as_node`; Temporal
  never cancels in-flight work on deploy; SWE-bench Verified, LiveCodeBench (fresh held-out tasks), tau-bench pass^k.
- Fit: **C1** record an unreported cache as unknown, regenerate the ledger (bug); **C2** constrained answers
  (`json_schema`/`tool_choice`) for answer-only steps where the server supports it (switch); **C3** mask withheld tools
  instead of refusing them (switch); **C4** opening-stable memory with tail deltas (switch); **C6** reference-ranked
  repo map for large codebases (switch); **C7** classify `finish_reason=None` (bug). **R1** rewind lineage (bug);
  **R2** drain deploys at the next model-call boundary instead of cancelling (bug class); **R3** heartbeat orphan
  detection (bug); **R6** state the environment contract once in the stable system block (bug). **E1** ledger
  integrity and a harness SHA per segment, `impact.py` excluding mixed segments (bug); **E2** pass^k with Wilson
  intervals, the RC target as pass^k per family on a frozen SHA; **E3** held-out briefs never used for fixing
  (including a ~20k-line brownfield change, a CLI, a library, forms with validation); **E4** 20-30 hidden tests per
  family, core plus extended; **E5** mutation score of the shipped tests as a gate KPI; **E6** Measure batches
  round-robin by kind.

## 4. Assessment on merit

The harness's architecture is sound: a brief-derived, locked acceptance suite as the definition of done, packs for
known stacks, and deterministic gates around model work are what the leading systems converge on too. What needs
to change is how it has grown: incident-by-incident text heuristics, opinion gates that cannot show value, and
mechanisms nobody checks are working. The recommendation is not a rewrite; it is three moves applied everywhere -
**measure each mechanism's effect, prefer execution over text, ask for deltas** - plus the evaluation needed to tell
whether each move helped.

## 5. Plan (order across all areas)

Rules for every item: a targeted test proven to fail on the old code, the full suite read before committing,
technology-agnostic (stack facts only in packs and `seed.py`), the banned-word test for any new prompt rule,
small and large codebases. Bug fixes are always on; optional improvements sit behind a switch in a meaningful group
and are kept only with a measured no-loss result. Owner 11-07: build and hold deploys until agreed.

**Phase 0 - measurement first (bug fixes; nothing else can be judged without them).**
Progress: R1 BUILT as LF.660 (a race, not lineage; verified live). F2 telemetry BUILT as LF.663. G2 covered by LF.648 for the measured case: replayed on the surviving fired workspace (notes-api-hono 1, hidden 9/9) the current check is clean; the other firings' workspaces are gone - watch the next firings before rebuilding it. G1 NOT BUILT, measured 2026-11-07 (107 scored runs, last 4 days): the verdict's precision is 0.23 at recall 0.88; demoting the noisiest kinds (unit tests failing beside a green suite, bare-visit or unsigned probe gaps, the brief check's MUST FIX) moves precision to 0.22 and recall to 0.75 - full-score runs carry several kinds at once; even hard evidence alone (no start, failing suite, unproven setup, release re-check) gives 0.33 / 0.25. Most partial runs score 0.88-0.9: one hidden test the harness never sees. No gap relabelling can make the label predict the hidden score; the lever is the false acceptances themselves (Q2, Q4, Q5). The verdict stays a list of concerns. P5 NOT BUILT on merit: deleting the saved command-line code after it runs breaks the owner's 2026-10-20 decision (the code is kept in the project so what ran can be read afterwards; saved outside the project, a Python file would lose the project's imports), and LF.602 already answers a delete of it as done - about one tool call a run. F3 BUILT as LF.664 (unit-test defects; measure the request mix with `loop.sh` over the next runs). Progress: C1 BUILT 2026-11-07 (`run_kpis.cached_token_share` is None when no call reported a cache read; 112 ledger rows corrected, backup `data/kpi/ledger.csv.bak-c1-20261107`; `tests/test_an_unreported_cache_is_unknown_not_zero.py`).
E1 + C1 ledger integrity; Q1 check-precision telemetry with guard reason codes; F8 stable defect ids; telemetry for
the silent mechanisms (F1 candidate rounds, F2 surrender-to-rewrite, C7 finish reasons). Then E2 pass^k and
intervals in `kpi_ledger report` and `impact.py`.

**Phase 1 - bug fixes with the largest measured waste (always on).**
G1 verdict calibration; G2 brief check by routes; F2 close the surrender branch; F3 the defect's own test output;
R1 rewind lineage; P5 harness scratch cleanup; P4 ownership hand-off; D8 escalation count; G6 the deferral hole;
R6 environment contract in the system block; SF.0 remainder.

**Phase 2 - deterministic replacements for opinion and text (quality; each measured on two runs per family).**
D1 + D2 spec consistency and setup-owned sections (one bundle); P1 + P7 plan repair and deltas; G3 evidence-gated
milestone review; Q2 isolation by fixture; Q3 dry run for Python, text checks to notes on measured parity; Q6
executable dispute verdicts; SF.1 composed proven setups.

**Phase 3 - optional improvements behind switches (measured arms).**
Fixing: F1 selection, F4 cause order, F6 fresh attempts, F5 SBFL. Suite: Q4 two-sided stub validation, Q5 browser
mutants, Q8 relational assertions. Design: D3 single review. Building: P3 edit format by tier, P2 failure-made
re-plans, P6 draft candidates. Context: C2 constrained answers, C3 tool masking, C4 stable opening, C6 repo map.
Gates: G4 scanner, G5 advice merge. Runtime: R2 drain deploys, R3 heartbeat. Setup: SF.2, SF.3.

**Phase E - evaluation, in parallel with Phases 0-1 (host side, no deploy).**
E3 write the held-out briefs (start with the brownfield change and a forms page); E4 extend hidden suites with a core
and extended split; E5 mutation as a KPI; E6 round-robin Measure batches. The `notes-api-falcon` benchmark added
today is the first custom-stack baseline.

Expected effect, from the measured shares: Phases 0-1 remove most false labels and forced revisions at little run
time; Phase 2 targets the 44.7 h of post-lock suite work, the lead's re-asks (about half of planning time) and the
milestone send-backs (+19 min on a third of runs); Phase 3 targets fixing (21-36% of time) and the 21% browser false
acceptances. Each is judged by Phase 0's measures, not by single runs.

## 6. How this review changes how I work

A standing rule (memory `step-back-on-a-subsystem`): after three point fixes in one subsystem, review its design
unasked; re-check filed items weekly. And from finding 3: no mechanism counts as done until a measure shows it
firing on live runs (`loop.sh effects`).

Progress 2026-11-07 15:4x JST: F4 built in its measured form as LF.669 - fixers after a fix undone for a broken start are told the streak and the error raised (128 such reverts over 37 runs, 11 runs with 3+ in a row). Failure-evidence subsystem had five point fixes (LF.607, 664, 667, 667b, 668): its design review is the next item.

Progress 2026-11-07 17:0x JST: D8 BUILT as LF.674 (the design escalation names the revisions it took - fast delivery's 2, not the full limit). G6 NOT BUILT, measured: of 256 scored runs, 49 shipped a deferred criterion - 41 full score, 8 partial (16%, against 24% for runs with no deferral); blocking release on a deferral would hold 41 good runs to catch 8, and under auto-approval the escalation accepts and ships the same product. Since LF.337's last try (10-27) only 3 deferring runs lost a hidden test, 2 of them on the deferred criterion itself (a missing record's 404, a tag filter): the lever is a last try that fixes, not a gate. Next: R6, measured first (which environment rules tool calls still break).

Progress 2026-11-07 19:1x JST: built since 17:00 - C7 (LF.677), Q1 recording and `loop.sh suite-checks` (LF.678), P4 measured form (LF.679), F8 (LF.680), E1 (LF.681). Measured and not needed: R3 (no orphan since LF.595; LF.682 fixed the KPI that suggested one) and R2 (178 cancellations in 30 runs, all refused before sending; none lost in flight). Remaining Phase 0-1: SF.0b, SF.0c. Register: docs/measuring.md.

---

# Part 2 - second review (HR2), 2026-11-07 22:3x to 11-08 JST

Owner request (11-07 22:3x JST): a deep review and research of every stage, the harness's own steps and the
shipped product; read the old review and plan; append what is new. Eight read-only reviewers ran in parallel (one
per area, plus the product itself and the loop's own tooling), each measuring today's 13 runs and the 536 stored
transcripts, 263 scored runs and the KPI ledger, and researching 2025-2026 products and papers. Their full
reports, with file:line evidence, measurement scripts and citations, are in `docs/reviews/hr2/` (the brief is
`00-brief.md`; `09-external-review-assessment.md` judges the owner's independent review by another agent). This
part keeps one line per item; the reports hold the evidence. Items are `HR2.<area>.<n>`.

## 7. Six findings the first review missed or under-weighed

1. **Repairs that run after the check that needs them, and gates satisfied by the harness's own files.** The
   technical lead's plan is sent back 1.1 times a run for problems the harness then fixes itself: the two
   largest readiness causes (a work order naming the locked suite file - 50 since 11-01; a `cd`-prefixed command
   - 30) are repaired by code that runs *after* readiness (`workflow.py:10265, 10291`); 125 of 140 resends are
   mechanical, 6 sent the harness's own plan back to the lead (one cost 30 min). The handoff README is written
   only on the clean release path (`delivery.py:289`), so 41 of 104 products (39%; 16 of 51 last week) ship
   with none - every one NON-DELIVERABLE, notes-api 4 (hidden 9/9) among them. The README's route table never
   fires because the workspace's own `docs/technical_specification.md` "names the routes" (`release_docs.py:107`).
   The part writers are given the specialists' advice without its ids while the repair demands the ids word for
   word: 224 "advice owed" rounds in 120 runs, 57 at the cap, ~2 architect minutes every run. Nine milestone
   filters silently relabelled 6 of 21 `changes_required` verdicts as accepted with no record.
2. **The whole artifact is re-sent, re-read and re-reasoned.** The specification is 25% of every prompt character a
   run sends (62.9M characters over 9 runs; 57-77% of the design reviewer's prompt, 55-70% of the scrum master's)
   while the fix stages, which get a slice, run at 5-12%. The design reviewer reads `technical_specification.md`
   by tool in 236 of 222 reviews after being handed it (2.25 model calls a review, each a full reasoning pass);
   the technical lead's reads are answered by the memory pointer 75% of the time (3.7 full-context turns a run);
   capped planning replies are 17% of planning replies and **48% of planning minutes** (each 80-105k characters of
   reasoning before a plan the salvage extracts) - LF.683 stopped the reopened reasoning, not the cause.
3. **The fix loop's cost is one path.** "A whole-file rewrite that declined, then the 16-call agent loop" is 177 of
   729 fix stages and **63% of fix minutes** (median 13 min and 1.06M input tokens when left open). The rewrite
   answers "unchanged" 42% of the time (206 of ~240 before a loop), is aimed at a test or scratch file 24% of the
   time (the localiser is skipped when the failure names 1-2 files), and candidates ran 9 times in 730 stages. Fix
   rate by attempt 29% -> 22% -> 11%; `loop > loop` fixes 65% on the second try, `rewrite > rewrite` 16%. The
   surrender branch (F2) covers the 42 left-open loops that wrote nothing; the 138 that wrote and failed have their
   half-change committed and the next fixer is not told.
4. **The suite's send-backs are the QA lead's, and judgement correlates with false acceptance.** 53 of 86 suites
   lock with problems "still open": 295 items, 240 the QA lead's, 37 the harness's (13%); 49 (17%) are
   non-findings ("no finding", "acceptable") kept as problems. Disputes: 20 of the 30 false acceptances had one;
   hidden score 0.864 with a dispute vs 0.897 without; the executable legs' outcomes are warnings only.
   `QA_SAYS_THE_PRODUCT_IS_AT_FAULT` (built in): shown in 17 runs, 0 claims. Mutation: 15% of mutants break the
   product outright and count as caught; 218 "did not notice" gaps nobody acts on; boolean operators survive
   50-80%, comparisons 5-26%. Contract probes raised 3 gaps in 1,421 and record nothing of what they probed.
5. **What ships is not what a customer can use.** Of five 1.0-scored products, 5/5 install, start and test, 0/5
   name the port, the environment variables or the routes; 16 ship their own unit tests failing (falcon 8: 26
   erroring from one test-side cause; notes-api 4: 7); 4 of 104 configure logging; 61 broad excepts; 20 ship the
   data directory the harness's runs filled; 16 carry the browser pack's untouched template; both falcon products
   serve through `wsgiref` while declaring uvicorn/gunicorn unused; 21 of 68 start scripts ignore `HOST`. Every
   JSON-file store is lockless load-modify-save (the most-failed quality test, 17 of 49). The hidden score is at
   the ceiling and says nothing about any of this (Sonar 2025: no correlation between pass rate and quality).
6. **The setup library has never replayed, and the nightly never completes.** 0 "replayed" decisions in 106
   workspaces; the live Falcon entry cannot replay (a layered entry keeps only kept and smoke files, never the
   framework files, and `replay` never writes the layer); three entries were set aside on 11-07, each after a run
   paid replay, proof and the setup stage. `verify_packs` crashed at `go-gin-api` on both of its last two runs
   (a read-only Go module cache under `rmtree(ignore_errors=True)`) and was skipped 15 of 18 nights because a run
   was live: nine packs unverified since 10-29, the LF.685 library check never executed. The layered path itself
   is measured as the right design: 6 of 6 proven, median 5.5 min, against 1 of 12 hand-written, median 14 min.

Measured by the second review and unchanged from the first: no review or gap kind predicts a hidden failure
(precision 0.16-0.28 per gap kind over 260 runs; 27 of 33 milestone send-back findings restate advice or security
findings; the milestone review accepted both 0/9 runs); escalated designs score the same as approved ones
(0.927 vs 0.942, 102 runs); the deterministic gates caught what the reviews did not.

## 8. The owner's independent review (another agent, 11-07 22:34 JST)

Judged in `docs/reviews/hr2/09-external-review-assessment.md`. Mostly the first review restated (same numbers;
its bugs 3-5 and plan items are F1, F2, Q6, F3 (built), Q3, Q2, P1/P7, G3 (built as M7), C3, M8; two file names
wrong). Valid and new: unit tests shipped failing (confirmed and larger - now HR2.PR.13), psycopg2 pools returning
dead connections after a Postgres restart (HR2.RT.1), and pre-flight model diagnostics leaving no transcript record
(HR2.OB.1, rare: no run in the last 40 waited over two minutes).

## 9. Items by area (one line each; evidence, tests and KPIs in `docs/reviews/hr2/`)

Class: **B** bug or quality fix (always on, no switch); **S** doubtful (own switch, default off, measured two
runs per family on and off); **H** host-side tooling or evaluation (no run code). Size S/M/L.

**Intake and design** (`01`; design is 12-39% of a run, 61% escalate at review 2)
- HR2.D.1 B S - the part writers and in-place revisions get the advice with its ids (`advice_block`, not raw JSON): ends 224 "advice owed" rounds / 120 runs, ~2 min a run.
- HR2.D.2 B S - a harness-made repair names its sections; no "Name every section" call (347 calls, 1.1 min a run).
- HR2.D.4 B S - the harness findings' revision guard uses fast delivery's limit (2), not 6.
- HR2.D.3 S S - `DESIGN_REVIEW_IN_ONE_CALL`: the reviewer has no read tools and the specification once (2.25 -> ~1.1 calls a review; -3 to -5 min).
- HR2.D.7 B M - D1 in its measured form: a deterministic lint (ids exist and are unique, every route has a contract line and a test case, status codes per route listed where sections differ) always on; the pair-wise "contradiction or not" call behind D1's switch.
- HR2.D.6 S M - D3 reshaped: after review 1's revision, the lint, the harness findings and the ruling replace review 2; review 2 only when a gate fails (-6 to -10 min on 61% of runs).
- HR2.D.5 S M - `SPEC_SLICES_BY_STAGE`: the per-stage specification slice the fix stages already use, generalised (25% of prompt characters).
- HR2.D.8 S S - `tools_models` folded into the stack selector (0.5-0.8 min; measure first). Reshaped from the first review: D5 -> the lint; D3 -> D.6; D2 and D4 stay.

**Scaffold and setup** (`02`)
- HR2.SS.5 B S - the nightly verify removes read-only trees and runs past one pack's failure, in a throwaway container so a live run no longer skips it.
- HR2.SS.1 B S - a layered library entry carries its layer's framework files and `replay` writes the layer first; `check_the_library` replays the same way (0 replays ever -> every second run of a stack skips its setup stage: ~5.5 -> ~1 min).
- HR2.SS.4 B S - setup telemetry: replay attempt and problem in the decision, proof level reached, lines beyond scope, as `effects` rows (M6's KPI source).
- HR2.SS.2 B S - the layered setup stage reads configuration and library usage, not the whole specification (89-99k characters for four files; falcon 6's cause).
- HR2.SS.3 B M - `framework_files` declared on every service, page, CLI and library pack (1 of 38 today); **SF.2b parked** on evidence (the measured cause was runner/declaration disagreement, which the layer removes; generators add network, drift and a layout that fights kept files; the research reuses or synthesises, never generates).
- HR2.SS.6 B S - SF.0a's remainder: the six `pack_named` readers read `contract.the_pack`.
- HR2.SS.7 S M - `SETUP_PROOF_FEEDBACK`: the retry carries the proof level, the command and the three lines where it failed, and keeps the generated tree (hand-written path only; EvoConfig/EnvBench).
- SF.3a (patch on replay) is premature until SS.1 gives it a replay to patch.

**Acceptance suite and QA** (`03`; 21.6% of work minutes today)
- HR2.Q.1 B S - every sender of a send-back recorded per check: each of the 36 `tests_that_cannot_pass` checks by name, the QA lead's findings as `qa_lead` by criterion (Q1 completed).
- HR2.Q.2 B S - a non-finding is not a problem (17% of open items); the findings field asks for criterion, test and fault as fields.
- HR2.Q.4 B S - dispute outcomes recorded as one decision (shown, called wrong, passed alone, service stopped, past the cap, quote refused, reopened); retire `product_at_fault.py` unless the record shows a need.
- HR2.Q.9 B S - probe coverage recorded (lines checkable / probed / skipped with the reason).
- HR2.Q.10 B S - audits and `run_timing` subtract gaps over ten minutes (deploy pauses read as stage cost: 83, 73 and 44 min today).
- HR2.Q.6a B S - a mutant that breaks the product outright is inconclusive, not caught (15% of 2,247); the release's three changes drawn from the operators that survive most.
- HR2.Q.3 S M - `SUITE_PASSES_TWICE`: a green suite runs once more against the same product; a test green then red is an executable isolation finding for that test (replaces the four shared-count text checks on parity).
- HR2.Q.5 B S - the dispute ruling chooses the standard by id from the list shown, never by quote (ends the quote guard's patch stream: LF.628/633/640/641).
- HR2.Q.8 S M - `CONTRACT_LIST_PROBE`: a harness-written relational probe on filtered and ordered list lines (the blind-spot list: filtered action x12, filter by tag x4, newest first x2).
- HR2.Q.6b S M - `MUTATION_SURVIVORS_TO_QA`: at most three release survivors become bounded findings for the testing role.
- HR2.Q.7 S M - `REVIEW_THE_SUITE_DELTA`: round 2+ of the QA lead reviews the diff and its prior findings marked settled/open (12.2k output tokens a call, 14% at the cap).
- HR2.Q.11 H S - `loop.sh blind-spots`: hidden tests failing in partial runs since the last fix that named them. Reshaped from the first review: Q3 (Python dry run) deprioritised - one harness finding in 11 Python runs; Q4's stub leg dropped (pass-on-current filters lock bugs); Q5 kept after Q.6a; Q6 -> Q.5; Q8 -> Q.8.

**Planning and building** (`04`; planning 11.5% of stage minutes, builders ran in 6 of 14 runs)
- HR2.P.1 B S - the readiness repairs run before the check, not after; the harness's own plan never goes to the lead for a problem the harness made (125 of 140 resends).
- HR2.P.6 B S - a data file or the harness's start script is never "a file nobody is given" (~35 resends; pack-less stacks sent back for `notes.json`).
- HR2.P.3 B S - a read of a held, unchanged file is answered without a model turn: the pointer carries the asked lines, `read_file` is masked for planning stages whose memory holds the file (C3's masking applied first here; 453 of 602 lead reads were pointers).
- HR2.P.5 B S - draft outcomes recorded (first/refusal/repair-n, accepted, left to the loop); P6 cannot be judged without it.
- HR2.P.8 H S - audit lines for capped planning minutes and pointer reads.
- HR2.P.2 S M - `PLANNING_THINK_BOUND`: a soft thinking budget sized from the plan, and after a capped reply the next planning call runs with thinking off (the fix-stage rule extended); 48% of planning minutes.
- HR2.P.4 B M - plan repair by delta keyed by work-order label; the harness merges (P1's model half; Cursor/Claude Code "approve with edits", CodePlan).
- HR2.P.7 B S - the proven setup's files are named to the ownership table: a whole-file rewrite of one is warned once with the proven lines (LF.666 made measurable).
- HR2.P.9 S M - P3 reshaped: whole-file under a size, lenient anchored search/replace above, whole-file after one failed edit (Diff-XYZ, Aider); low priority while builders rarely run. WB.5 (plan batching) not supported by the data: the cost is per thinking turn.

**Test rounds and fixing** (`05`; 23.5% of wall time since 11-01)
- HR2.fix.1 B S - the ledger records the rewrite's reply class (unchanged / changed / no block / edit not applied) and the path on every outcome; `loop.sh defects` and `effects` report by path and list LF.669.
- HR2.fix.7 B S - `loop.sh defects` by defect id across rounds (the attempt curve and endings).
- HR2.fix.3 B S - a criterion's rewrite is never aimed at a test, scratch or data file, and the localiser runs when nothing remains (24% mis-aimed).
- HR2.fix.6 B S - every fixer sees the output that defines its defect: the suite's problem text when no failed test carries the tag, the `caught_by` unit command's failures for a test-round defect, "what settles this" for a mutation finding (F3 completed; 124:64 today).
- HR2.fix.4 B S - a second attempt never repeats an all-unchanged rewrite; it goes to candidates or the loop with one line saying so (16% -> 33-65%).
- HR2.fix.2 S M - `FIRST_TRY_CANDIDATES`: three whole-file rewrites on the first try, "unchanged" discarded, the first whose own tests pass applied (plan AY step 2); targets the 63% of fix minutes.
- HR2.fix.8 S S - `STOP_WHEN_OWN_TESTS_PASS`: the loop ends when verify-after-write says the defect's tests pass (median 12 -> ~8 calls).
- HR2.fix.5 S M - `SURRENDER_AFTER_A_FAILED_WRITE`: a loop that wrote and did not pass hands its diff to one rewrite; always on and small: the next request names the files the loop changed.
- HR2.fix.9 H - M8's measurement plan: unchanged-reply rate, rewrite fix rate, "declined then loop" share. Reshaped: F1 -> fix.2; F2 -> fix.5; F3 -> fix.6; F5 -> fix.3 first, SBFL stays Phase 3; F6 wrong shape (every attempt is already a fresh stage) -> fix.4; F4's cause order stays low.

**Gates and release** (`06`; reviews ~13 min a run; no gap kind above 0.28 precision)
- HR2.G.4 B S - the README names the port, environment variables and routes whatever the workspace's docs say (route table from the locked contract; a Settings block from the pack's declared environment; start and test commands in separate blocks).
- HR2.G.8 B S - an escalation-closed sprint's release says so and lists the accepted known issues beside the criteria.
- HR2.G.1 B S - the nine milestone filters record what they drop or demote (6 of 21 verdicts relabelled with no record).
- HR2.G.7 H S - run M7's on arm now: 27 of 33 send-back findings restate advice/security findings no test shows.
- HR2.G.9 B S - the release re-measures with a fresh process when any file changed after the last suite run (generalises LF.676; the throwaway clearing runs after the suite today).
- HR2.G.2 B M - the security review becomes a spec-conformance pass with ASVS 5.0 ids; a finding naming a criterion or contract line becomes a defect record; source suffixes from the packs (0 vulnerabilities on 5 scanned products; the 2 true findings were spec defects the milestone review raised again).
- HR2.G.6 S M - `ADVICE_ONE_CALL`: one advice request per sprint with the diff; `not_built` items become unchecked contract lines (6.2 min a run; 18% of findings become a change).
- HR2.G.3 H S - each gap kind printed with its measured precision; the "may not work" sentence only for hard-evidence kinds.
- HR2.G.5 S S - G4 reshaped: a scanner as a CI step and release note under `RELEASE_AUDITS`, a defect only once measured above 0.5 precision on the brownfield brief.

**The shipped product** (`07`; a customer's view)
- HR2.PR.1 B S - the handoff is written for every product that ships, not only on the clean path (41 of 104 without a README).
- HR2.PR.2 B S - the README a stranger can use: configuration (from the environment contract), start on its own, test, what it serves (from the locked contract), known gaps in plain words.
- HR2.PR.13 B M - (from the external review) when the locked suite is green and the product's own unit tests fail, one bounded tests-only pass by the testing role fixes or removes tests failing for a test-side reason, settled by the harness running the unit command; a test that catches a real bug becomes a defect (16 products ship red; falcon 8's 26 errors are one test-side cause).
- HR2.PR.4 B S - an untouched pack template no entry loads is deleted at release; an unreached module is a named gap.
- HR2.PR.11 B S - the data directory the run's own tests filled does not ship.
- HR2.PR.5 B S - the pack's kept entry file carries the stack's one-line logging setup and an error handler that logs before answering 500 (4 of 104 configure logging).
- HR2.PR.3 B S - one start path: `start.sh` honours `HOST` and `PORT`, the Dockerfile's CMD runs it, custom setups ship an image too, the stranger start also runs with `HOST=0.0.0.0`.
- HR2.PR.12 B S - a development server (`wsgiref`, `http.server`, `php -S`, `webrick`; a `seed.py` table) is refused as a declared start.
- HR2.PR.8 B S - a whitespace-only required value is a bad-body probe, not a catalogue line (LF.255 left 12 of 49 failing).
- HR2.PR.7 B M - a parallel-writes probe on the locked create line (N sent, M kept): every JSON-file store is lockless.
- HR2.PR.6 S M - `PRODUCT_LINT`: a per-pack lint command at the CI gate, errors as defects, plus a deliberation-comment check (77 lines of "Wait, spec says" shipped in 15 runs).
- HR2.PR.9 H M - one generated edge set for every HTTP family from its reference contract (E4 reshaped: the tasks-api quality set's seven shapes are brief-free).
- HR2.PR.10 H M - `handoff_score` in `loop.sh score` and the ledger: README facts, start honours its variables, no dev server, no template, no shipped data, unit tests green, lint 0, CI present.

**Runtime and observability** (from the external review; the context/runtime/evaluation report is appended as §12 when it lands)
- HR2.RT.1 B S - the psycopg2 pools discard a dead connection (`putconn(conn, close=True)` on OperationalError/InterfaceError) and retry the borrow once.
- HR2.OB.1 B S - one transcript record per pre-flight diagnosis step, so the audit's "stalled at 0%" cannot be a diagnosis.

## 10. The merged order

Bug and quality fixes come first and always on; each with a test proven to fail on the old code and the suite;
deployed in bundles at run boundaries (a bundle at a time, so `impact.py` can attribute). Switched items follow,
each a row in `docs/measuring.md` with its arms. Expected effects are the reviewers' estimates on a 60-110 minute
run; they add up only loosely because the bundles overlap in what they remove.

| # | Bundle | Items | Expected effect |
|---|---|---|---|
| 1 | **Telemetry** (everything later is judged by it; no outcome change) | Q.1, Q.4, Q.9, Q.10, G.1, fix.1, fix.7, P.5, P.8, SS.4, OB.1, Q.6a (score), Q.11, G.3, PR.10 | the audit sees capped minutes, pointer reads, per-check and per-filter precision, dispute and probe outcomes, fix paths, setup levels, handoff quality |
| 2 | **What ships** (zero run time, the largest customer-visible defects) | PR.1, PR.2, G.4, G.8, PR.4, PR.11, PR.5, PR.3, PR.12, PR.13, RT.1 | 39% of products without a README -> 0; a stranger's start 0/5 -> 5/5; red unit tests at ship 16 -> ~0; two 0/9 classes closed |
| 3 | **Design bugs** | D.1, D.2, D.4 | -3 to -5 min a run, every run |
| 4 | **Planning bugs** | P.1, P.6, P.3, P.7 | -4 to -6 min a run; the 30-minute harness-plan loop gone |
| 5 | **Fix-loop bugs** | fix.3, fix.6, fix.4 | fewer mis-aimed and repeated rewrites; +8 fixed per 100 multi-round defects |
| 6 | **Suite and release bugs** | Q.2, Q.5, G.9, PR.8, PR.7 | one send-back fewer on a third of runs; the quote guard's patch stream ends; a false-acceptance class closed at release; two quality tests from 17/49 and 12/49 toward 0 |
| 7 | **Setup bugs** | SS.5, SS.1, SS.2, SS.6, SS.3 | the nightly completes; the library replays (second run of a stack -5 min); the next custom family gets the layered result |
| 8 | **Switched, measured** (two runs per family on and off, one SHA each) in this order of expected effect | fix.2, P.2, D.3, G.7 (M7 on arm), D.7+D.6, Q.3, G.6, G.2, D.5, Q.8, fix.8, Q.7, fix.5, Q.6b, PR.6, SS.7, G.5, M6 arm, M8 arm, D.8, P.9, Q5 | fixing -8, planning -6, design -9 to -15, reviews -8 to -11 min a run if they hold; false acceptances on full-stack down |
| 9 | **Evaluation** (host side, in parallel) | PR.9, PR.10, Q.11, E3 held-out briefs, E2 pass^k | a quality and a handoff score on every family; the ceiling problem measured, not guessed |

Each bundle is one commit series and one deploy; bundles 1-7 are expected to take about ten days of cycles at the
current pace (the first review's Phase 0-1 took one day for 15 items). The register `docs/measuring.md` lists every
switched item and its arm; nothing in bundle 8 is deployed on before its row exists.

## 11. What this review changes in how the loop works

- A mechanism is not built until `loop.sh effects` shows it firing (first review, finding 3) **and** its outcome is
  a record the audit can read without re-deriving it from message text (bundle 1).
- A check that runs after the step that needed it is a bug of its own class (finding 1); every "the harness fixes
  this anyway" note in a transcript is one.
- The product is scored as a customer would see it (`handoff_score`, the generated edge set) beside the hidden
  score, so quality that the hidden tests cannot see is measured, not assumed.
