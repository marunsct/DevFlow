# Per-role audit: the latest 30 scored runs

**Scope:** 30 runs, from 885a8285 (2026-11-08 21:45 JST) to efaecb0f (2026-11-10 06:30 JST), 8 families. Each figure below was checked again by a second pass; where that pass corrected the first report, the corrected value is used. Times are in JST.

## 1. Summary

- 26 of 30 runs scored full. 4 were false acceptances and lost 8 hidden tests: efaecb0f 7/10, 5447eb12 6/8, aaf136ca 7/8 and 4c98359a 6/8.
- All 4 losses have one root cause: something overrode the brief's own wording, and the locked suite then tested the override.
  - In 5447eb12 and 4c98359a it was an intake assumption about casing.
  - In efaecb0f it was a spec label (`All (0)`).
  - In aaf136ca it was a ruling that keeps only a fragment of the JSON shape.
- 3 of the 4 losses were in sprints accepted at escalation, and those sprints ship with no code review. efaecb0f also locked its suite with no QA-lead call at all.
- The model was busy 48% of run time (44.8 of 93.1 h). Fixers take 38% of model time, and half of fixer time (530 min) goes on replies that were capped or salvaged.
- 6 defects used 523 fixer calls and 288 min, and 5 of them were never fixed. The cause is the per-defect call cap, which restarts at every re-plan.
- 66% of the technical lead's time (178 of 267 min) is replies salvaged from reasoning. The rule that turns thinking off after a salvaged reply covers `defect_fix_` stages only.
- The fixes that would move hidden score most:
  - the brief's wording wins everywhere;
  - a ruling may not stand on a fragment;
  - a review always runs before the lock and at escalation.
- The fixes that would save the most run time:
  - count the defect budget across the whole run (about 200–250 min per 30 runs);
  - turn thinking off for planning after a salvaged reply (at least 50 min).

## 2. Role groups at a glance

| Role group | Model min | Share of model time | Share of run time (5,585 min) | Main waste | Top fix |
|---|---|---|---|---|---|
| Fixers (`defect_fix*`) | 1,055 | 38% | 18.9% | 530 min of capped or salvaged replies; 288 min on 6 defects across re-plans | Count the defect budget across the whole run |
| Suite writers (author, review, dispute, specialist testing) | 669 | 23.6% | 12.0% | Locked tests follow the spec or a ruling over the brief; 62 installs; 35 refused writes | The brief's wording outranks the spec in every suite request |
| Design and review (architect, reviews, consults, rulings) | 576 | 21% | 10.3% | 22 of 30 runs escalated; 35% of second-review findings repeat the first; fragment rulings | Rulings carry the full side; no assumed or advised change to brief behaviour |
| Planning (lead, scrum master, drafting, escalation) | 385 | 14.6% | 6.9% | 178 min of salvaged lead replies; a sprint limit that is cut later; 23 send-backs | Thinking off after a salvaged reply for lead and scrum master |
| Prompts (cross-cutting) | – | – | – | 57 refusals of withheld tools; a false `cd &&` rule (159 uses); unchecked framework notes | The refusal names the tools still usable |

**How the shares were counted:**
- The total model time differs between reviewers: 2,628 to 2,835 min, because they paired responses with requests in different ways.
- The groups overlap slightly. `consult_testing` (24 min) and escalation (2 min) appear in two groups each.
- With the overlap removed, the four groups sum to about 2,660 min. That matches the wall-clock model time: 44.8 h, 48% of run time.

## 3. Role groups

### 3.1 Fixers (`defect_fix*`)

**Measured**

| Metric | Value |
|---|---|
| Calls | 2,003 (1,570 in the agent loop, 433 rewrite/localise) |
| Model min | 1,055 (loop 971, rewrite 84) |
| Runs where fixers took most model time | efaecb0f 74%, 023f2c45 73%, aaf136ca 55%, 1e6f6436 54%. The first three named here used 62.6% of all fixer minutes. |
| Attempts | 62 fixed, 121 left open, 25 reverted (30% fixed) |
| Fix rate by source | mutation 13/16, language service 6/13, test round 15/51, acceptance 25/101, page check 0/18 |
| Fix rate by visit length | ≤15 calls 56/174 (32%); exactly 16 calls 6/24; 17 or more 0/10 |
| Capped or salvaged replies | 186 calls (9.3%), 530 min; 23 calls ran over 5 min each (208 min, 15 of them in efaecb0f) |
| One-file rewrites | 274 replies; 171 came back unchanged (62%) |
| Tool failures | 81 of 1,498 (5.4%), 36 of them stall-guard refusals |

**Findings**

1. **The call cap is counted per remediation cycle, so it restarts at every re-plan.**
   - `defect_budget.spent()` follows `recurrence_chain` within one cycle only.
   - The cap fired once in 30 runs (efaecb0f, 74 calls).
   - Six defects went over 60 calls:

     | Run | Defect | Calls | Model min | Ended |
     |---|---|---|---|---|
     | 023f2c45 | c6e2ca8c55 | 132 | 81 | left open |
     | 023f2c45 | b087dfd918 | 126 | 71 | left open |
     | 023f2c45 | 90c3486595 | 74 | 26 | left open |
     | aaf136ca | c6e2ca8c55 | 64 | 26 | fixed |
     | 1e6f6436 | 66865b2b92 | 64 | 64 | left open |
     | aaf136ca | 6a5b206fc2 | 63 | 20 | left open |

   - Together: 523 calls (26% of fixer calls) and 288 min. 5 of the 6 were never fixed.
   - `DEFECT_CALL_CAP` was on in every run's switch list, but `ON_BY_DEFAULT=False` in the code. The default needs checking.
2. **Fixers are sent back to criteria whose locked test a dispute has already ruled wrong.**
   - 16 surrenders in 7 runs blamed a wrong locked test.
   - In 023f2c45 the dispute returned `cannot_pass` at 19:08 JST, naming `test_ac3_json_output` (25 characters, where the test expects 24). Fixers still made 60 more calls after it.
   - LF.772 removes this class of bad test at the source. The routing after a verdict is still not covered.
3. **Accessibility defects from the page check carry no files.**
   - They are built with `affected_files=[]`. Result: 0 of 10 attempts fixed.
   - In e16844fb, every rewrite went to `main.js`, including for `color-contrast`, which is a stylesheet problem.
   - The other 8 page-check attempts were the disabled-control defect, which LF.793 now handles.
4. **The rewrite after a surrender fixed nothing.** It fired 38 times, wrote files twice and fixed nothing. 31 of the 38 came right after a rewrite that returned the file unchanged.
5. **Thinking-off works within a visit, not across visits.**
   - Within a visit: 0 of 141 replies after a reasoning salvage were salvaged again.
   - Across visits: 73 visits started with a capped reply, costing 143 min.
6. **Unit-test defects improve only a little.**
   - By defect, 14 of 43 test-round defects were fixed (33%), against the LF.580 baseline of 19%.
   - 29 failing unit tests shipped, in 5 runs: e16844fb 14, 57a4b355 10, aaf136ca 3, 5447eb12 1, 6fbbf838 1.

**Proposed fixes**

1. **Run-wide defect budget.** `spent()` also counts attempts from earlier cycles under the same ledger `defect_id`. A spent defect is deferred with its history. Expected: 200–250 min saved over 30 runs.
2. **After `cannot_pass`, stop sending fixers to that criterion.** Defer it, carry the deferral across re-plans, and name test, line, expected value and spec value in `blockers`. Expected: 40–60 calls per affected run. Measure it on wordstats-cli first, because LF.772 may already shrink the need.
3. **Accessibility defects name their files.** Map each axe selector to the markup, stylesheet or script that defines it.
4. **Extend LF.729's guard to the surrender path.** Skip the rewrite when the last rewrite in the same attempt came back unchanged. Expected: about 31 calls saved.
5. **Carry thinking-off across visits after a capped visit.** Behind a switch, and measured. Expected: at most about 140 min per 30 runs.

### 3.2 Suite writers

**Measured**

| Stage | Calls | Model min | Share of model time |
|---|---|---|---|
| acceptance_author | 1,041 | 393 | 13.9% |
| acceptance_review (27 runs) | 108 (46 verdicts) | 143 | 5.1% |
| specialist_testing (8 runs) | 378 | 68 | 2.4% |
| acceptance_dispute (15 runs) | 26 | 38 | 1.3% |
| consult_testing | 42 | 24 | 0.8% |
| test_round (model) | 11 | 3 | 0.1% |
| **Group** | **1,606 (32% of 5,013)** | **669** | **23.6%** |

- **Heaviest runs:** bec09178 spent 60% of its model time here (author: 185 calls, 68 min). 4c98359a spent 51%, 5814234a 49% and bbbf1e3d 48%.
- **Unit cost:** a review verdict costs about 3.1 min; an author call about 0.38 min.
- **Reviews:** 11 of 27 runs were approved at the first verdict. 3 runs locked with no QA-lead call: efaecb0f, 57a4b355 and daab28e9.
- **Disputes:** 25 verdicts in 15 runs. They covered 82 tests and found 58 of them wrong (71%).
- **Waste inside the stages:**
  - 62 install commands, 17 of them in bec09178;
  - 35 writes refused outside the stage's own files;
  - 21 withheld-tool refusals;
  - 7 deletes of the harness's own `tmp-inline-` files.
- **Defect events:**
  - 140 raised, 25 fixed;
  - 102 left-open events on 41 distinct defects;
  - 61 closed without a fixer, 59 raised again.

**Findings**

1. **The suite writer's request contradicts itself on which wording wins.**
   - The `api_reference` header says "as the specification decides it … word for word". `QA_RULE` and the rulings block say the brief stands.
   - **efaecb0f:** the brief names the controls "All", "Active" and "Completed". The suite used `All (0)` and `/^All \(/`.
   - **aaf136ca:** the brief gives `{"top": [...]}`. The suite followed DR-10's bare array.
   - **5447eb12 / 4c98359a:** the brief says words are compared in lower case. The products printed `The 3`.
2. **A truncated ruling was handed to the writer as the thing to build to.**
   - In aaf136ca, DR-10 stands on `"[{\"word\": w, \"count\": c}, ...]}"`, which has an unbalanced `}`.
   - `verified()` checks only that the quote is present and its length. So the fragment passed, and the run lost `test_json_top_words`.
3. **The QA lead is skipped when mechanical problems remain at the last round.**
   - The model is called only when `not problems and not targeted` (`acceptance_nodes.py:784`).
   - That skipped 3 runs; efaecb0f was a false acceptance.
4. **Hand-typed counts start in the specification, and the suite copies them.**
   - 5447eb12: `'abc def \n'` is given as 8/3/2; the real values are 9/2/1.
   - 023f2c45: 24 characters (real: 25) and 2 lines (real: 1).
   - 885a8285: 12 bytes (real: 14) and 15 (real: 16).
   - 5447eb12 ran with LF.772 and still locked the wrong counts.
5. **The reviewer opens product files against its own rule:** 71 reads in 17 runs. After approvals, disputes later called these tests wrong: 5447eb12 4, 2c3182ed 6, 1e6f6436 4.
6. **Disputes repeat while refused.** 3f858a3b called the same 2 tests wrong twice, 21 min apart.

**Proposed fixes**

1. **The brief's wording wins in the writer's, QA lead's and dispute judge's requests.** The harness also lists each quoted brief literal that the spec renders differently. Partly built: LF.792 (named controls, product side) and LF.780 (casing, architect).
2. **`specification_rulings.verified` rejects a weak quote.** That covers quotes with unbalanced brackets or quotes, quotes that are a strict fragment of a longer literal, and rulings that contradict a brief literal. Not built.
3. **The QA lead reviews every suite once before the lock,** even when mechanical problems remain, and its findings go back with them. Optionally, limit its `read_file` to the suite, `docs/` and `.harness/`. Not built.
4. **No hand-typed count upstream of a test.** The spec states a count of example text as "computed from the text". This extends LF.772 to the architect. Not built.

LF.787 already covers the out-of-scope writes but is not yet measured; only efaecb0f and e16844fb ran with it.

### 3.3 Design and review

**Measured**

| Stage | Calls | Busy min |
|---|---|---|
| principal_architect | 281 | 236 merged (358 summed; up to 3 calls run at once) |
| architecture_review | 110 | 143 |
| milestone_review (22 runs) | 57 | 67 |
| advice_review | 77 | 64 |
| consult (testing 42, ui_ux 40, database 30, backend 27, security 18) | 157 | 45 |
| security_review | 34 | 18 |
| escalation | 22 | 2 |
| research_brief | 32 | 1 |
| **Group** | | **about 576 (21% of model time)** |

- **Design review:**
  - 29 of 30 runs had two design reviews.
  - 22 runs built through an escalation.
  - All 7 runs that ended approved scored full.
  - 35% of second-review findings (23 of 66) repeat the first review's.
- **Milestone review:**
  - 8 runs had none, including 3 of the 4 losing runs (efaecb0f, 5447eb12, aaf136ca).
  - 6 send-backs led to fix work. They cost about 118 min, 90 of them in ebde7fac, and changed no score.
  - 6 runs shipped with a final "changes_required".
- **Advice review:** `design_problems` was empty in 56 of 56 outputs.
- **Security review:** 0 of 1,505 defects came from a review.
- **Command-line runs:** the UI/UX consult plus its advice review cost 40 calls and 12.6 min.

**Findings**

1. **The casing rule that lost 4 hidden tests started at intake.**
   - 5447eb12: "ASSUMPTION: Plain text output preserves original casing".
   - 4c98359a: "output preserves the original casing of the first occurrence".
   - The consult repeated it, and it became AC-12 and UX-4.
   - The code contradicts itself on such additions. `scope_discipline.py:33-35` says unrequested work is "never a blocking or major finding". `advice_review.py:187-189` makes adopted advice that is not built blocking or major.
2. **The specification's parts are written in parallel.**
   - `function_contracts` (part 1) and `error_catalogue` (part 2) are written concurrently (`specification_parts.py:186`, `:360`).
   - Contradictions between the parts drive repeat findings: 13 runs had repeats, 5 of them in bec09178.
3. **Rulings keep a fragment, or the wrong side.**
   - aaf136ca: the DR-10 fragment, with the false reason "only the top array".
   - 1e6f6436: rulings kept the 1 KB body limit and WAL over decisions the advice step had declined.
   - 023f2c45: rulings let statements stand whose own reasons say the brief excludes them.
4. **LF.590 has not moved its measure.**
   - 47 of 86 first-review blocking or major findings (55%) are contradictions, against the 61% baseline.
   - Limit findings did fall, to 3–5.

**Proposed fixes**

1. **No assumed or advised change to behaviour the brief states.**
   - The intake's assumptions, the consult prompts and the architect's adopt step each get one rule: never change an output form, format, shape or comparison rule the brief states.
   - `findings_block` rates adopted advice beyond the brief as minor.
   - Skip the UI/UX consult and its advice review when the product has no page.
   - Partly built: LF.780.
2. **Write part 2 after part 1,** with `function_contracts` in hand. Revise sections that name each other in one call. Not built.
3. **A ruling carries its side in full.**
   - Reject a fragment: under about 8 words, or starting or ending inside a bracket.
   - Reject a ruling that keeps something the advice step declined.
   - Reject a set of rulings that lets opposite sides stand.
   - Not built; this merges with fix 2 in 3.2.
4. **At escalation, hand over the open findings where the spec departs from the brief,** so the escalation settles them. In aaf136ca, the open major finding was exactly the hidden test that was lost. Partly built: LF.499, LF.501 and LF.718.
5. **Drop security findings that repeat the milestone review's own.** The evidence (55a58483, ed4e910f) was not re-checked. The evidence-gate half is LF.687, which is still off.

### 3.4 Planning

**Measured**

| Stage | Calls | Model min | Salvaged from reasoning |
|---|---|---|---|
| technical_lead (27 runs) | 164 | 267 | 50 of 151 replies, 178 min (66% of its time) |
| scrum_master (30 runs) | 70 | 88 | 6 replies, 28 min |
| drafting (30 runs) | 225 | 27 (undercounted: the calls run in parallel) | 0 |
| escalation | 22 | 2 | 0 |
| **Group** | **481 (9.6%)** | **385** | |

- **Plans:** 69 plans with 153 work orders; 75 of the orders have an empty `title`.
- **Send-backs:** 23 in 13 runs.
  - 9 for a work order with no files;
  - 7 for a scope file that no order lists;
  - 6 for a refused `verification` command;
  - 1 for `carried_forward_decisions`.
- **Re-plans:** 14 runs needed 21 extra sprint attempts. 9 runs were accepted at escalation.

**Findings**

1. **Planning has no thinking-off rule.**
   - 22 of the 50 salvaged lead replies only read files, and 15 came right after another salvaged reply.
   - The rule's gate checks `startswith("defect_fix_")` (`settled_answer.py`), so it never reaches planning.
   - Worst runs: 023f2c45 11, 1e6f6436 7.
2. **The re-plan text tells the lead to fix the test.**
   - `technical_lead.py:643` says the fix may be "in the test if the test asks for something the product was never meant to do". The system prompt forbids any work order on the locked suite.
   - That produced 6 orders in 023f2c45 and aaf136ca, which were stripped and sent back 4 times.
   - Both runs were escalated, and aaf136ca was a false acceptance.
3. **The readiness check sends back things the harness could repair.**
   - 5 `verification` send-backs in 4 runs after LF.726 were for shell syntax. `with_refused_commands_noted` never scans the `verification` field.
   - 051cda30 was sent back twice for a test input file (`nonexistent_file_xyz.txt`) read as a deliverable.
4. **The scrum master is told a sprint limit that is then cut.**
   - The request says 3 or 4 sprints, but `_how_many_sprints` omits `fast=`. `workflow.py:9825` then cuts to 1 sprint.
   - The final plan has 1 sprint in 26 of 30 runs, after 494k output tokens of scrum-master work.
   - Stale "(deferred to Sprint 3)" lines remain in 5 runs.
5. **Escalated sprints ship without a code review.**
   - 3 of the 9 escalated runs were false acceptances, against 1 of the 21 others.
   - All 3 record "No review read the product's code".

**Proposed fixes**

1. **Extend `SALVAGED_REPLIES_TURN_THINKING_OFF` to `technical_lead` and `scrum_master`.** Measure it on and off. Expected: at least 50 min per 30 runs. Not built.
2. **The re-plan text routes a wrong locked acceptance test to `blockers`,** for the dispute to decide. Unit tests stay fixable. Not built.
3. **Repair `verification` before the readiness check.**
   - Split `&&` and `;` into separate commands. Drop `||`, redirections and a trailing `&`, and note what was dropped.
   - A file that appears only as a command argument or a suite literal is not a deliverable.
   - Expected: about 31 min. Not built.
4. **Use one sprint limit everywhere:** pass `fast=delivery.fast()`, and strip a folded sprint's old number from the text. Not built.
5. **At escalation, still run the milestone code review,** and count reclassified or deferred criteria as unverified. Partly built: LF.718, LF.778 and LF.779.

### 3.5 Prompts (cross-cutting)

**Measured**
- 261 system-prompt variants. 178 of them (68%) contain a banned word, in 12 of 22 families.
- Every technical_lead variant has one, with up to 21 hits in one variant.
- The source holds 56 string literals with 102 hits:
  - technical_lead.py 39;
  - specialists.py 25;
  - project_layout.py 9, including the `task-manager/` and `todo-app/` examples.
- The existing banned-words test checks only selected strings.

**Findings**

1. **The `cd … &&` rule is false in practice.**
   - The prompts say it "does not work" (`specialists.py:1364`, `guidance.py:82`), but the sandbox rewrites a leading `cd <dir> &&`.
   - 159 calls in 24 runs used the form, and 152 of them ran (1e6f6436 alone: 56).
2. **The refusal for a withheld tool does not say which tools are usable.**
   - The PX.2 notice was sent 123 times in 023f2c45 and efaecb0f, which still made 21 refused calls.
   - There were 57 refusals in 18 runs: defect_fix 36, specialist_testing 15, acceptance_author 6.
3. **Framework notes written by the model are stored unchecked** (`middleware.py` about line 466).
   - `--watch` and `pip install pytest` reach builder prompts; `--watch` appears in the largest prompt of 11 families.
   - Measured harm is small.
4. **Contradictory pairs.**
   - The "IF YOU ARE REVIEWING / BUILDING" blocks appear together in 9 families.
   - Reviewers are told both "read widely" and "stop, do not look further".
   - The REASONING IS NOT WORK rule is absent from the architect and the lead; defect_fix has it and still had 23 cut-offs.

**Proposed fixes**
1. **Make the shell rule match the tool:** state that a leading `cd <dir> &&` is read as the working directory and nothing else joins. Or refuse every join consistently.
2. **The refusal and `stable_tools_notice` list the tools still usable.** This keeps the stable tool list. Expected: about 25–30 min per 30 runs.
3. **Filter framework notes before storing them:** drop watch modes, bare global installs and commands that are not allowed.
4. **A test that renders every role's real system prompt** and checks for banned words, repeated rule blocks and the paired blocks. Then clean the 102 hits.

## 4. Did the 2026-11-05 fixes (LF.580–590) work?

| Fix | Target | Result in these 30 runs | Verdict |
|---|---|---|---|
| LF.580 | Unit tests drafted before their code; unit-test defects | 33% of test-round defects fixed, against a 19% baseline. 29 failing unit tests shipped in 5 runs. "0 of 41 batches drafted a test first" was not re-checked. | Modest gain; not enough |
| LF.583 | QA findings sent back once | Fired in 8 runs, with 0 false acceptances (not re-checked). It never fires when the QA lead is skipped (3 runs). | Works where it fires |
| LF.584 | Drafting reply cap | 0 reply-cap hits in drafting | Worked |
| LF.585, LF.587 | – | Firing counts not verified | Unknown |
| LF.590 | Architect self-contradictions and limits | 29 of 30 runs still had two design reviews (baseline: 21 of 23). Contradictions are 55% of first-review findings (baseline 61%). 41 "settled finding" gaps in 18 runs. Limit findings fell to 3–5. | Limits fixed; contradictions not. Next step: write the spec parts in order (3.3 fix 2). |
| LF.581, 582, 586, 588, 589 | – | No role report measured them | Not measured |

## 5. Ranked fix list

*Status of the "Built?" column checked again 2026-11-14 17:3x JST.*

Ranked by hidden score first, then by run time.

| # | Fix | Expected effect | Built? |
|---|---|---|---|
| 1 | The brief's literal wording wins along the whole chain: intake assumptions, consult, architect adopt step, suite writer, QA lead, dispute judge. The harness also lists brief literals the spec renders differently. | The 4 false acceptances (8 hidden tests) turn into failing tests on the build | Partly (LF.780 casing, architect; LF.792 named controls, product side) |
| 2 | A ruling may not stand on a fragment, contradict a brief literal, keep advice the advice step declined, or let opposite sides stand | aaf136ca's lost test; the 023f2c45 and 1e6f6436 rulings | No |
| 3 | An escalated sprint still gets the milestone code review, and reclassified or deferred criteria count as unverified | 3 of the 4 false acceptances were escalated runs | Partly (LF.718, LF.778/779) |
| 4 | The QA lead reviews every suite once before the lock | 3 runs had no QA-lead call (1 false acceptance); about 3 min per firing | No |
| 5 | Run-wide defect call budget across re-plans | About 200–250 min per 30 runs; 5 of the 6 heaviest defects were never fixed | No (the cap exists per cycle; check `DEFECT_CALL_CAP`'s default) |
| 6 | After a `cannot_pass` verdict, stop sending fixers; the re-plan text routes a wrong locked test to `blockers` | 40–60 calls per affected run; stops orders that target the suite | Partly (LF.772, LF.183; 11-14: LF.899 sends no fixer to a defect naming only deferred criteria, LF.894/895/900 add measured cannot-pass checks) |
| 7 | Thinking off after a salvaged reply for `technical_lead` and `scrum_master` (existing switch) | At least 50 min per 30 runs | No |
| 8 | The spec states counts of example text as "computed from the text" | Stops wrong counts in 3 runs and the fixer loops they cause | Partly (LF.772 suite rule; 11-14: LF.900 catches a hand-counted expected text by measurement - the spec's own contract line was miscounted too on L textkit-lib 9) |
| 9 | Repair `verification` before the readiness check; command-line arguments are not deliverables | About 31 min per 30 runs | No |
| 10 | One sprint limit (`fast=`) in the scrum-master request; strip stale sprint numbers | Less scrum-master output (494k tokens); clean plans in 5 runs | No |

**Next tier, unranked:**
- the withheld-tool refusal names the usable tools (about 25–30 min);
- skip the surrender rewrite after an unchanged reply (about 31 calls);
- accessibility defects carry `affected_files`;
- thinking off across visits (switch, at most 140 min);
- filter framework notes;
- make the shell rule true;
- write the spec parts in order;
- skip the UI/UX consult for products with no page (12.6 min);
- a banned-words test over the rendered prompts.

**Rules for building these:** each new prompt rule (1, 6, 8, and the next-tier wording changes) needs a test that bans task, tasks, to-do, todo, button, click and checkbox. Fixes 5, 7 and thinking off across visits are efficiency changes, so they go behind a switch and are measured.

**Data caveats:**
- The bench files do not record the harness SHA, so whether LF.781 was live in efaecb0f and e16844fb is unknown.
- The quote-form dispute refusals could not be re-counted; the worker log no longer holds them.

**Check scripts:** all are in `/tmp/claude-1000/-home-arun-Desktop-langchain/d4298d72-a977-42bb-8a37-f5c3120002bc/scratchpad/`, in the subfolders `v/`, `v2/` and `ver/`, and as the files `ver2.py`–`ver9.py` and `vv3.py`–`vv15.py`.