# HR2 01 - Intake, stack and design (second review, 2026-11-07 night)

Scope: product_manager, tools_models, stack_selector, specialist_consultation (consult_*), research_brief,
principal_architect (core + parts + repairs + in-place revisions), architecture_review (+ four harness findings),
design escalation (+ rulings), the intake enrichers, `choose_pack`. Read-only; numbers from today's 9 finished runs
(the 6 falcon runs, tasks-api 4-5, notes-api 4) and the last 120 stored transcripts (102 with a hidden score).

## 1. What exists

Pipeline (`src/app/graph/workflow.py`):
- `product_manager_node` :9075 - one agent call, then four deterministic enrichers (:9096-9110: brief constraints,
  brief measures, workflows its measures require, deferred scope marked), `assumptions` (IN.1), directory pin,
  seeded-product move. 0.2-0.3 min, 1-3 calls.
- `tools_models_node` :9145 - an agent writes a framework/storage comparison (`docs/tools_and_models.md`) and the
  `technology_stack` fields; pins languages for the sandbox (:9215). 0.5-0.8 min, 2 calls, ~4.5k output tokens.
- `stack_selector_node` :9228 - agent call given the brief constraints and `supported_stacks_note()`; the browser
  runner correction (:9279); `_the_stack_pack_for` -> `choose_pack` (`src/app/stacks/__init__.py:581`, fit by kind,
  language, framework, frontend; rationale-named fallback :620; plain-page fallback :633). 0.2 min.
- `specialist_consultation_node` :9315 - one call per role from `roles_to_consult` (`specialist_advice.py:107`:
  ui_ux / database / backend / security_reliability / testing). 4 roles on an API, ~1.0-1.2 min in all.
- `research_brief` - 1 call, ~0.0 min (`research_brief.py`).
- `principal_architect_node` :9357 - first pass: core (7 sections, `specification_parts.CORE`) by the architect agent
  with research, naming standard, scaffold layout, assumptions; then `with_the_parts_written` (3 part calls in
  parallel, `specification_parts.py:136`). Any later pass with `required_changes` goes through `revised_in_place`
  (:9453): one `sections_to_revise` call ("Name every section", `specification_parts.py:214`) then one revise call per
  3 sections (:286). Repair chain after each pass (:9507-9585): empty sections, served files, start settings,
  advice owed (`what_the_specification_owes`, `specialist_advice.py:413`), unrunnable testing - each bounded by
  `MAX_SPECIFICATION_REPAIRS = 2` (:204).
- `architecture_review_node` :9588 - reviewer agent (`architecture_reviewer.py`, `can_write=False`, read tools
  kept) given the spec as JSON (`_as_text`, :6522) plus brief constraints, setup facts, section list, deferral hints,
  previous findings; then four harness findings (:5114 coverage, :5200 deferral, :5171 unread contract lines
  [switch], :5265 kept-file behaviour), `_a_pass_over_its_own_findings` :5322, `_findings_that_block` :5368
  (severity + scope), routing :9668-9713: approve, revise, or escalate at `limit = 2` in fast delivery (:9692).
- Escalation (`src/app/graph/escalation.py:172`): `kind: design` -> `_build_from_the_latest_specification` :143 records
  the decision, calls `specification_rulings.settle` (`SETTLE_SPEC_CONTRADICTIONS`, now in `BUILT_IN`,
  `switches.py:67`), writes `known_issues`. `delivery.py:389` reads them at release.

Today's fixes in this area: D8 built as LF.674 (confirmed: tasks-api 5 says "after 2 revisions"; tasks-api 4,
falcon 7/9 before the deploy still say "after 6 revisions"). LF.665/666/672/673 touch the setup, not the design.
`BRIEF_OVER_SPEC_ADDITIONS` and `SETTLE_SPEC_CONTRADICTIONS` are both in `BUILT_IN` (always on).

## 2. Measured

### 2.1 Time (design = principal_architect + architecture_review + escalation, first to last record)
- 120 stored runs: median 13.8 min, mean 14.7, p90 20.5. Today's 9: 20.8, 14.4, 11.3, 26.6, 20.3, 22.4, 12.6, 13.4,
  30.6 = mean 19.2 min of runs with 52-160 active minutes (ledger): 12-39% of the run (falcon 4 = 30.6 of 65.8).
- Intake (PM + tools_models + stack + 4 consults + research): 1.9-2.6 min a run, 9-12 calls. Nothing to win here
  except `tools_models` (0.5-0.8 min, a comparison document no stage checks; the architect and the stack selector
  read its `technology_stack` fields only).
- Architect calls by kind, 120 runs: agent calls 466 (510 min, 4.3/run), `sections_to_revise` 347 (135 min,
  1.1/run), revise calls 246 (230 min, 1.9/run). 1,570 architect requests = 13 a run.

### 2.2 The architect's rounds, by cause (120 runs, from the "Name every section" requests)
| cause | rounds | note |
|---|---|---|
| advice owed (`what_the_specification_owes`) | **224** | 107 runs have >=1 round; **57 runs have 2** (the cap) with the same ids still missing |
| design review revision | 106 | |
| empty sections | 26 | |
| served files (layout) | 1 | |
| start settings, unrunnable testing | 0 | |
Root cause of the 224 (new, §5 HR2.D.1): `parts_context()` (`workflow.py:9429`) hands the part writers and every
in-place revision the advice as the raw state JSON (`_as_text(state["specialist_advice"])[:20_000]`), a dict of
role -> plain strings **with no ids**. The ids (`DB-1`, `TS-3`...) exist only in `advice_block()` / `_numbered()`
(`specialist_advice.py:280-289`), which the architect's own first request gets (`principal_architect.py:427`) and
the part writer of `specialist_advice_decisions` never does. `unanswered()` (:318) then requires each id word for
word; the repair text names the ids but the revise call's context still has none. Verified on three transcripts:
the "Specialists' advice" section of the part request carries 0 ids (6.7-9.1k chars). The missing sets are whole
roles (`SR-1..SR-10, TS-1, TS-2`), as expected. Cost: ~2.9 which_sections+revise rounds a run of which ~1.9 are this
repair: about **2 min of architect time a run**, every run since parts were introduced, for a section that then
reads "Not specified" for the roles the writer could not name.

### 2.3 The review (222 reviews in 120 runs; 101 runs with 2 reviews, 11 with 1, 6 with 0)
- Status: changes_required 174, approved 48 (review 1 asks for changes in 87%, as the first review found).
- **73 of 120 runs (61%) escalated** the design; today 5 of 9.
- Severities: blocking 150, major 375, minor 346, informational 38.
- **499 model calls for 222 reviews = 2.25 a review; 281 reviewer tool calls, 236 of them `read_file
  docs/technical_specification.md`** - the document the request already carries as JSON (60-77% of the review's
  prompt characters, 85-100k chars a call). In 187 of 516 review requests (36%) the project memory carried the
  markdown rendering as well, so the reviewer had the specification three times. Each extra call costs a full
  reasoning pass (10-56k reasoning chars before the tool call in today's runs). The review stage took 5.2-10.8 min
  today; one call a review would make it 2-5 min. Likely cause: the request names the path
  "(/docs/technical_specification.md)" and the prompt says "approval must be grounded in what you actually
  verified"; the agent has read tools (`create_role_agent(can_write=False)` keeps them).
- Gating findings (blocking + major, 525), multi-label by words in the description: **contradiction between
  sections 307 (58%)**, "not specified / does not handle" 195 (37%), framework-specific (names Falcon, FastAPI,
  Flask, Pydantic, gunicorn...) 172 (33%), **harness-owned files (start.sh, pyproject, package.json, kept) 103
  (20%)**, interface detail (signatures, parameters, dependency injection) 74 (14%), other 41.
- The four harness findings: in the last 120 transcripts the deferral finding fired once as a revision cause, the
  others never; 3 of 96 stored workspaces have one in their final review document. They cost nothing and catch
  little (the suite catches the same gaps later). Their guard `architecture_revision_count + 1 >=
  MAX_ARCHITECTURE_REVISIONS` (:5135, :5181, :5213, :5277) uses the full limit 6, while fast delivery escalates at
  2: a harness finding first raised on review 2 goes straight to escalation with no revision - never happened in
  120 runs (0 escalation rationales carry "by the workflow"), but the docstrings promise otherwise.

### 2.4 Today's five escalations, finding by finding (the hidden score of every one: full)
| run | open finding(s) at review 2 | class | what happened downstream |
|---|---|---|---|
| tasks-api 4 (44a25a80) | [major] gunicorn missing from pyproject deps in `file_plan` | harness-owned file (the setup's `pyproject`/venv decide) | ruling kept: ".venv ... containing ... gunicorn"; 10/10 |
| tasks-api 5 (94ad3d57) | [major] `get_db()` never in handler signatures; [major] signup response body differs between API and data-flow sections; [minor] umask in `init_db` vs `start.sh` | interface detail; **contradiction**; contradiction (harness file) | ruling kept for the signup body; 10/10 |
| falcon 5 (eee50710) | [blocking] 413 vs 400 for an oversized body across sections; [major] "400/422" in the advice-decision line vs 400 elsewhere | **contradiction** (about a limit the brief never asks for); contradiction | no ruling recorded (call made, 0 output); 9/9 |
| falcon 7 (7aa9533c) | [major] "preserve extra fields" (ADR-11, DB-8) vs AC-7 "exactly three keys"; [major] SR-8 graceful shutdown needs a Python signal handler | **contradiction** (advice vs brief); invented requirement from the advice | ruling kept for AC-7; 9/9 |
| falcon 9 (adae4da8) | [blocking] `python3 -m wsgiref.simple_server --bind ...` has no such CLI | **real defect** in a harness-kept file's description | the builder wrote `python -c "... make_server ..."` (checked: the shipped start.sh); 9/9 |
Across 102 scored runs of the 120: escalated n=66 mean 0.927, full-score 85%, 10 false acceptances; not escalated
n=36 mean 0.942, full 83%, 6 false acceptances. Same as the first review: the open findings do not predict the
score. 3 of today's 5 escalations were contradictions and the ruling (`SETTLE_SPEC_CONTRADICTIONS`, built-in since
11-05) settled 3 of the 4 it was given - it is the one design mechanism measured working after the review.
Note (sum of recurring notes): "valid JSON that is not an object" was a minor finding in 5 of today's 9 runs - the
reviewer repeats the same framework nitpick on every custom Python stack; it never blocked and never failed a test.

### 2.5 What the specification costs downstream (`blocks.specification`, today's 9 runs)
- Total: **62.9M characters re-sent over 9 runs (7.0M a run, ~1.75M tokens), 25% of every prompt character the run
  sends** (19-34% per run; ledger input tokens 4.5-16.6M a run). The document itself is 42-64k chars (markdown);
  as JSON (`_as_text`) 75-100k.
- By stage (chars a run, share of that stage's prompt): acceptance_author 0.9-3.4M (27-38%); stack_setup (custom
  stacks) 1.0-3.6M (25-38%; 78 calls in falcon 6); specialist_testing 0.95-2.4M (25-31%); architecture_review
  0.22-0.72M (**57-77%**); scrum_master 0.11-0.52M (55-70%); technical_lead 0.12-0.92M (22-38%); security and
  advice reviews ~0.1-0.57M each (26-35%); milestone review 0.13-0.36M (25-31%); defect_fix 0.09-5.1M but **only
  5-12%** of its prompt - the fix stages already get a slice (`_the_specification_for_the_fix`, `workflow.py:7304`,
  via `specification_for_the_work_order`, `specialists.py:892`: the API reference, the ledger lines and the entries
  naming the order's files). Work orders get the same slice; every other stage gets the whole document through the
  project memory (`project_memory`) and, for the review and the scrum master, the JSON again in the request.
- With the cache share at 0.68-0.79 the time cost is smaller than the token count, but every new conversation
  prefills ~20k tokens of specification, and the reviewer's and the scrum master's prompts are 55-77% specification.

## 3. The first review's items in this area

| item | state | evidence / what should change |
|---|---|---|
| D1 cross-section consistency check before the review | open; evidence stronger | 58% of gating findings are contradictions; 3 of today's 5 escalations. But the cheap half already exists at the end: the ruling settles them. D1's value is to run *before* review 1 on candidate pairs (same route / same field / same status code in two sections - the pair-wise form the papers recommend, §4) and to make review 2 unnecessary. Keep; bundle with D3-reshaped. |
| D2 harness writes the setup-owned sections | open | 20% of gating findings name harness files; today's gunicorn case. Keep. Note `stack_setup` on custom stacks has no pack to write from (M6 covers that side). |
| D3 one LLM review + deterministic gates (`DESIGN_SINGLE_REVIEW`) | open; **reshape** | Review 2 costs 5.5 min median (first review) and today 7-12 min with the revision; its findings are 84% new; the escalated ones never moved the score. Reshape: after review 1's revision, run the deterministic gates (D1, the four harness findings, the ruling call on review 1's still-open contradictions) and go on; keep review 2 only when a harness gate fails. Switch as planned; KPI design minutes, hidden score, false acceptances. |
| D4 typed interface-contract records | open | No new evidence today; the contract lines parsed fine (the one unread-line finding was minor). Keep at the end of the order. |
| D5 requirement-to-test links at design | open; partly exists | `interface_contract` lines and `test_cases` already carry AC ids; what is missing is the check (every AC id has a contract line and a test case; every id cited exists). Reshape as a deterministic lint in D1 (ids unique, referenced ids exist), not a new section. |
| D7 stack choice as a pack id | open | `loop.sh stack-misses`: every stored miss now fits; the 9 unfitted are Falcon (no pack). Lower priority than before; keep for robustness. |
| D8 escalation count text | **built** (LF.674) | confirmed in tasks-api 5. |
| R6 (reviewer notes) clarify cap 3 | not in the plan | Spec Kit caps at 5 questions; IN.1 assumptions already answer them; nothing to add. |

## 4. Research (web, 2026-11-07; details and URLs in the research notes)
- **GitHub Spec Kit** `/speckit.analyze` (templates, main): read-only, six fixed passes (duplication, ambiguity,
  underspecification, constitution, coverage requirement<->task table, inconsistency: terminology drift, entity in
  one file not another, conflicting tech choices), fixed severity rubric, reads "only the necessary sections".
  `/speckit.clarify`: at most 5 questions a session, answers *replace* contradictory text. `/speckit.checklist`:
  every item cites a section id; items question the requirement, never the implementation. Transfer: a fixed
  taxonomy and a per-requirement coverage table computed once; every finding must cite the section pair.
- **Kiro** (docs 2026-09/10): requirements -> design -> tasks, consistency enforced directionally ("Sync Files"
  regenerates downstream), "Analyze Requirements" optional by spec size; steering files included by fileMatch.
  Transfer: derive downstream sections from upstream ones; include spec parts by file match (the slice).
- **Tessl** / intent-integrity-kit (2026-02): `[@test](path)` links and `targets:`; CI fails on a dead link; at most
  three `[NEEDS CLARIFICATION]` markers. **OpenSpec** v1.13: `openspec validate --strict` is a deterministic lint
  (requirement has >=1 scenario, SHALL, unique name; archive refuses on failure); changes are deltas under
  ADDED/MODIFIED/REMOVED, never full rewrites. Transfer: a structural lint with an exit code before any LLM review;
  revisions as named-requirement deltas (what `revised_in_place` half does).
- Papers: Fukuda et al. SANER 2025 (arXiv:2509.09975) - LLMs find cross-document inconsistencies reliably, the one
  review skill worth paying for; Jin & Chen (arXiv:2603.00539, Feb 2026) - LLM reviewers systematically flag
  compliant work, and a finding is worth keeping only when a test derived from it fails; RefineBench
  (arXiv:2511.22173) and "Self-Correction as Feedback Control" (arXiv:2604.22273, Apr 2026) - unguided re-review
  degrades after round 1, guided by a concrete failed check it converges; requirements-contradiction work (ALICE
  ASE 2024, RE@Next! 2025) - pre-selected candidate pairs beat whole-document reading; Pereira & Garcia
  (arXiv:2608.13742, Aug 2026) - JSON vs prose spec changes correctness by <=0.023: structure buys checkability,
  not better code; Chroma "Context Rot" (2025-07), Du et al. (arXiv:2510.05381), Lodha et al. (arXiv:2606.10209) -
  irrelevant context lowers accuracy even with perfect retrieval; slices raised completion 71% -> 79% at -64% tokens.
- What fits here: (1) deterministic lint + pair-wise contradiction check before review 1; (2) one guided review,
  then rulings, no second unguided reading; (3) sections derived from one source (API contract -> data flows,
  error catalogue) rather than restated; (4) section slices per stage. None of the products reviewed re-send a
  whole design document to every later step.

## 5. New items

**HR2.D.1 - the part writers and in-place revisions are given the advice without its ids (bug, always on).**
Evidence: §2.2 - 224 "advice owed" rounds in 120 runs, 57 runs hit the cap of 2 with the same ids missing; the
part request's advice section carries 0 ids (3 transcripts checked); `unanswered()` demands them.
Change: `parts_context()` (`workflow.py:9429`) carries `advice_block(state["specialist_advice"])` (numbered, with
the rule) instead of the raw JSON; the same context reaches `revised_in_place`. Also stop asking for the id form
twice: when a repair is owed only because ids are absent, the part writer should have been told them.
Test (fails on old code): with advice for two roles, `part_request(spec, ("specialist_advice_decisions",...),
parts_context)` contains every id `DB-1`, `BE-1`...; today it contains none. Banned-word test for the new text.
KPI: advice-repair rounds a run (224/120 -> ~0), architect minutes. Size S. Risk: none; the architect's own request
already has this form.

**HR2.D.2 - a harness-made repair names its sections; do not ask the model which (bug, always on).**
Evidence: 347 `sections_to_revise` calls (1.1 min a run); 251 of 357 rounds are harness repairs whose text already
says "Return only `specialist_advice_decisions`" / "`testing`" / `file_plan, component_boundaries,
implementation_order`; `_bounded_by_what_the_review_names` (`specification_parts.py:248`) then discards most of
what the model named anyway.
Change: `revised_in_place` takes an optional `sections` argument; the repair sites (:9521-9583) pass the sections
they name; `sections_to_revise` is called only for review findings. Test: a repair with named sections makes no
"Name every section" call (model stub counts calls; fails on old code). KPI: architect calls a run (-2 to -3),
minutes (-1). Size S. Risk: none.

**HR2.D.3 - the reviewer re-reads the specification it was handed (switch `DESIGN_REVIEW_IN_ONE_CALL`, default
off; efficiency).**
Evidence: §2.3 - 236 reads of the file in 222 reviews, 2.25 calls a review, each extra call a full reasoning pass;
36% of review requests also carry the markdown in memory. Review stage 5-11 min today.
Change: the reviewer is created with no tools (`create_role_agent(..., extra_tools=None, can_write=False)` plus a
`tools=()` option, or a reviewer-specific agent without the repository readers), its request says "the whole
specification is below; nothing else is in the repository yet", and the request's memory block leaves
`docs/technical_specification.md` out when the JSON is in the request (one copy). Where the setup facts are
needed they are already in the request (`_the_setup`). Test: the reviewer's tool list is empty and the request
carries the specification once (fails on old code). KPI: review calls a review (2.25 -> ~1.1), review minutes (-3
to -5 a run), hidden score and finding counts unchanged. Size S. Risk: a reviewer that wanted `product_intake.md`
(15 reads) loses it - include the intake's success measures in the request, which the harness coverage finding
already compares against.

**HR2.D.4 - the harness findings' revision guard uses the full limit in fast delivery (bug, S).**
Evidence: §2.3; `workflow.py:5135, 5181, 5213, 5277` compare with `MAX_ARCHITECTURE_REVISIONS` (6) while
`:9692` escalates at 2. A harness finding first raised at review 2 (count 1) passes the guard and escalates
unrevised. Not yet seen in 120 runs (the checks rarely fire) - correctness, not time.
Change: one helper `_the_revision_limit()` used by all five sites. Test: in fast delivery with
`architecture_revision_count=1`, `_a_success_measure_the_specification_drops` returns None (fails on old code).

**HR2.D.5 - specification slices per stage (switch `SPEC_SLICES_BY_STAGE`, default off; efficiency, measured).**
Evidence: §2.5 - 25% of all prompt characters are the specification; the fix stages already use a slice and
work at 5-12%; the acceptance author (0.9-3.4M chars a run), the custom-stack setup (1.0-3.6M), the testing
specialist and the reviews read the whole document on every call. Research: irrelevant context lowers accuracy
(§4), and no product reviewed re-sends a whole design document.
Change: generalise `specification_for_the_work_order` (`specialists.py:892`): a per-stage section table
(acceptance author and QA: api reference, interface contract, acceptance criteria, test cases, error catalogue,
data contracts; setup: configuration, deployment, file plan, library usage; scrum master: product scope,
component boundaries, implementation order, acceptance criteria; security review: security, configuration, error
catalogue, api; milestone/advice reviews: the sections their findings cite) and the project memory carries the
document only for stages not in the table. Small codebases lose nothing (the document is 40-60k chars; the slices
are 10-25k); large ones gain most. Test: the acceptance author's request carries `error_catalogue` and no
`decisions` records (fails on old code). KPI: input tokens a run, cache share, suite lock minutes; hidden score
and false acceptances must not fall (two runs per family on/off). Size M. Risk: a section a stage silently relied
on - the table starts wide and the measurement narrows it. Related, not duplicate: HR.C4 (stable opening), C6
(repo map), M8 (rewrite memory) - those cut memory and code context, none cuts the specification.

**HR2.D.6 - D3 reshaped: review 2 is replaced by gates and rulings (switch `DESIGN_SINGLE_REVIEW`, as planned).**
Evidence: §2.3-2.4 - 61% of runs escalate; review 2's open findings are contradictions (settled by the ruling in
3 of 4 cases today), harness-file matters (D2) or framework detail; none moved a score in 102 runs; the second
reading costs 7-12 min with its revision. Research: unguided second rounds are net-negative (§4).
Change: after review 1's in-place revision run D1's lint, the four harness findings and
`specification_rulings.settle` on review 1's findings not shown resolved by the revision's changed sections
(the revise reply says which sections it rewrote); review 2 runs only when a deterministic gate fails. Test: with
the switch on and a clean lint, the second `architecture_review` request is not made (fails on old code).
KPI: design minutes (-6 to -10 on 61% of runs), hidden score, false acceptances. Size M. Depends on D1's lint
(HR2.D.7).

**HR2.D.7 - D1 in its measured form: a lint of ids and a pair-wise contradiction check (quality, always on for
the lint; the LLM pair check behind D1's switch).**
Evidence: 58% contradictions; today's cases were all "the same route/field/status differs in two sections"
(signup body, 413/400, three keys vs extra fields, get_db's file). Research: pre-selected pairs beat whole-document
reading; Spec Kit's inconsistency pass and OpenSpec's validate are the models.
Change: deterministic: every `AC-n` cited exists, every id unique, every route in `api_and_event_contracts` has
an `interface_contract` line and a `test_cases` entry, every setting in `configuration` that the function contracts
name, status codes per route collected from every section and listed where they differ (that list is the finding,
with the two quotes - the ruling's input form). Candidate pairs (same route, same field name, same setting) go to
one call that answers "contradiction or not" per pair, only when the lint finds a difference. Test: a spec with
`POST /signup -> 201 {username}` in one section and `{username, token}` in another yields the pair (fails on old
code). KPI: review-2 findings of the contradiction class, escalations. Size M.

**HR2.D.8 - `tools_models` folded into the stack selector (switch, low priority).** 0.5-0.8 min and ~4.5k output
tokens a run for a comparison document nothing reads but its three stack fields; the stack selector is given the
same intake. Measure before building: two runs per family with the stage's agent call skipped and the fields
filled by the selector. Size S. Not before D.1-D.7.

Not proposed: changing the consults (1 min, their advice is what the design review's best findings cite); the
intake enrichers (deterministic, cheap, no misfire found today); raising the review limit.

## 6. Priority order and expected effect

1. **HR2.D.1** (S, bug): -2 architect rounds and ~2 min a run on every run; ends a misfiring repair that has run
   224 times. Build first, with D.2.
2. **HR2.D.2** (S, bug): -1 call a repair round, ~1 min a run.
3. **HR2.D.4** (S, bug): correctness of the guard; no time.
4. **HR2.D.3** (S, switch): -3 to -5 min a run of review time; measure two runs per family.
5. **HR2.D.7 + D2** (M, Phase 2 bundle as planned): the lint always on; fewer contradictions reach any review.
6. **HR2.D.6** (M, switch, needs D.7): -6 to -10 min on the 61% of runs that escalate today.
7. **HR2.D.5** (M, switch): -20-25% prompt characters a run; time effect to be measured (cache share 0.7-0.8).
8. HR2.D.8 (S, switch): measure, then decide.

Together D.1-D.4 take 5-8 min off a 60-110 min run with no quality lever touched; D.5-D.7 are the measured arms
for the next launch cycle. Everything above is product-, stack- and framework-agnostic (the slice table names
specification sections, not stacks); each prompt change takes the banned-word test.
