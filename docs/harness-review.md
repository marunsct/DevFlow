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
