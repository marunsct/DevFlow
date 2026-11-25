# Per-agent audit: what each role is asked, given and does, and how to make it work better

2026-11-25 (JST). For the owner and the agents that build the harness. Read-only audit: no code, tests, runs or
switches were changed. It builds on `reports/audits/2026-11-20-per-role-audit.md`.

**Data.** Fourteen transcripts, read record by record (`model_request`, `model_response`, `tool_call`, `tool_result`,
`defect`, `request_budget`), and `loop.sh effects` for the live run. Prompt and request sizes are the `blocks` each
request recorded as sent, not reconstructed from source. Model minutes are the time between a request and its reply,
with waits across a pause removed.

| Group | Runs |
|---|---|
| Small, 11 runs (fast delivery, both ports) | run-972956f5 web-todo 6 (10/10); run-1d79334d notes-api-go 13 rerun (9/9); run-2c83118a wordstats-cli 17 (6/8, false acceptance); run-b6c5c636 fullstack-bookmarks 15 (8/8); run-ec516cd8 tasks-api 24 (10/10); run-cc265cee notes-api-java 12 (9/9, not deliverable); run-c46d5d9a notes-api-csharp 16 (9/9); run-c4fd577a notes-api-rust 4 (9/9); run-031094d4 notes-api-js 1 (9/9); run-88549ebb textkit-lib 9 (8/8); run-127780fe notes-api-go 13 (9/9, not deliverable) |
| Medium brief, thorough delivery, custom stack | run-8f0be29e (Medium 1, failed at 17 of 97); run-c53e7bd2 (Medium 2, failed in sprint 2); run-bc3cbd00 (Medium 3, live; read up to 09:57 JST 11-25, in sprint 2) |

Totals: the 11 small runs made 1,448 model calls in 557 model minutes; Medium 3 so far 1,133 calls in 443 minutes.

**Limits of the numbers.** "Calls" include the summariser's own calls (one per summary). A refused write is a tool
result that opens with an error, a refusal or "failed the same way". Fix outcomes are the ledger events in the
transcript, not re-measured. Medium runs had deploys into them, so their stage counts include restarts.

## Summary

1. **The reading loop is fixed for reviews and not for the suite writer.** On Medium 3 the code, security, advice and
   milestone reviews read each file 1.0 to 1.4 times with no summary (LF.1284-1286 work). The suite writer made 462
   calls in 150 minutes with 74 summaries, 710 reads of 42 files (16.9 a file) and 34 writing calls: 34% of the
   run's model time. Its request starts at 45,000 to 50,000 input tokens against a window that summarises a few
   thousand tokens later, so it is summarised after every two or three calls.
2. **A summary describes the files read, not the work.** Every summary in that loop opens "Establish the foundational
   backend architecture for a FastAPI application" - written for a stage whose job is the acceptance suite. It holds
   nothing of what the stage found, decided or meant to do next, so the stage starts reading again.
3. **A stage is asked to fix a file it may not write.** After a testing stage answered, the harness's check on "files
   modified in this stage" named a compiler error in the product's entry file. The stage went on to 12 refused
   writes (5 after its first answer) and answered 4 times in one visit (run-c4fd577a), while its budget notice said it had not answered.
4. **The unit-test writer is sent to a product that does not build.** In 3 small runs it had 25 writes refused
   (product files) beside 32 writing calls, and returned 40 blockers and 41 defects that restate compiler errors.
5. **The technical lead's plans go back for things the harness can write.** On Medium 3: 12 plans in 4 visits; the
   send-backs were "no testing work order" and shell operators in a command. Each is a fresh 147,000-character request.
6. **The custom setup stage cost 96 minutes and proved nothing** (193 calls, 31 summaries; the declaration file not
   written, then a browser install that cannot work in the sandbox).
7. **Design goes to escalation on 9 of 11 small runs.** The architecture review asks for changes on 9 of 11 first
   drafts (12 blocking and 14 major findings, mostly contradictions between sections written in separate calls).
8. **Reviews drift and repeat.** A security review's one critical finding was a missing import, and five of its six
   findings were not about security; the next review repeated three of them. The milestone review said "changes
   required" on 5 of 8 small-run sprints, all of them delivered; in the one followed through, the evidence gate
   let the run go on, so the verdict changed nothing.
9. **A first fix of a failing unit test rarely works when held to test files:** of 44 defects given that mode, the
   ledger shows 1 fixed, 2 closed by the next round, 9 left open or unverified; 29 later records allow product code.
10. **Writers carry 22,000 to 25,000 characters of tool descriptions on every call** for 15 to 18 tools; in 13 runs
    seven of those tools were never called and `grep` was called 15 times against 4,300 file reads.

## What changed since the 2026-11-20 audit

| 11-20 finding | State now |
|---|---|
| The 204 check counted a header a test sends (7 repeats, 10.6 minutes) | Fixed, LF.1177 |
| Identical findings re-sent without limit (187 findings 3+ times) | Fixed, LF.1177 (held back as suspected false; 3 such events in this sample); a check that ran the test's code is never held back, LF.1183 |
| The suite writer's prompt contradicted its request | Fixed for the contradictions, LF.1178. The suite writer still tried product files 5 times in this sample; the unit-test writer 25 times (finding 4) |
| The environment contract listed the wrong commands | Fixed, LF.1176 |
| A pack command with `;` refused in a harness work order; scaffold stub counted as built | Fixed, LF.1176 |
| 46 banned-word hits in rendered prompts | Fixed, LF.1178, with a scan test |
| `tmp-inline-*` copies listed and deleted by agents | Fixed, LF.1178 (0 such deletes in this sample) |
| Read-only roles carry writer guidance | Built behind `REVIEWER_SHAPED_PLUGIN_CONTENT` and `QA_PROMPT_TRIMMED`, both off after arms that showed no saving on a small brief. **Still holds and is larger on a custom stack:** Medium 3's scrum master, code reviewer and QA lead each carry about 14,000 characters of framework blocks, 5,700 of them setup instructions (section "Cross-role patterns", C4) |
| The lead's re-plan request is 96k-234k characters | Built behind `LEAD_REPLAN_REQUEST_SMALLER`, off. Still holds: 140k-159k characters of memory on Medium 3, 151k on tasks-api 24 |
| `CONTESTED_TESTS_CONFIRMED` unmeasured | Still unmeasured. Only 3 dispute calls in these 14 runs |
| Precision of suite checks and QA-lead findings unmeasured | Suite checks now written by `check_precision.py --write`; QA-lead findings still unmeasured |
| The lead called for the first plan in fast delivery | Mostly fixed: 7 of 11 small runs called the lead, 36 calls and 35 minutes in all (was 1-5 calls every run) |

New since then, and used below: files held in a reading stage's memory (LF.1284-1289), one input budget per request
(LF.1274, cut applied only to fixers), the suite locked a sprint at a time (LF.1266), sprints sized by work (LF.1315),
a tester's refused product change kept as its blocker (LF.1310, not reached in this sample).

## The roles

Small-run columns are totals over the 11 small runs. "Read-only" is the share of model calls whose tool calls only
read or listed.

| Role | Small: calls / model min / share of time | Read-only | Medium 3: calls / min | Medium 3: summaries, reads per file |
|---|---|---|---|---|
| Suite writer (QA) | 338 / 128 / 23% | 34% | 462 / 150 | 74, 16.9 |
| Principal architect | 102 / 111 / 20% | 1% | 6 / 17 | 0 |
| Fixers | 344 / 104 / 19% | 27% | 181 / 59 | 12, 2.8 |
| Technical lead | 36 / 35 / 6% | 58% | 72 / 31 | 10, 4.1 |
| Drafting (one file a call) | 140 / 28 / 5% | 0% | not used (thorough) | |
| Advice reviewers | 25 / 25 / 4% | 24% | 12 / 14 | 0, 1.0 |
| Unit-test writer | 125 / 21 / 4% | 31% | 8 / 2 | 0 |
| QA lead | 26 / 20 / 4% | 46% | 59 / 17 | 7, 6.3 |
| Architecture reviewer | 23 / 16 / 3% | 48% | 1 / 4 | 0 |
| Specialist advisors | 58 / 15 / 3% | 14% | 11 / 13 | 0 |
| Builders (agent loop) | 120 / 15 / 3% (2 runs) | 28% | 23 / 5 | 1, 2.5 |
| Scrum master | 14 / 13 / 2% | 7% | 6 / 10 | 0 |
| Tools and models | 20 / 7 / 1% | 45% | 2 / 2 | 0 |
| Security reviewer | 14 / 7 / 1% | 36% | 8 / 7 | 0, 1.4 |
| Milestone reviewer | 12 / 7 / 1% | 33% | 3 / 2 | 0, 1.0 |
| Product manager | 11 / 2 / 0.4% | 0% | 1 / 0.2 | 0 |
| Stack selector | 14 / 2 / 0.3% | 7% | 2 / 2 | 0 |
| Suite dispute | 2 / 2 (2 runs) | 0% | not reached | |
| Custom setup stage | not used (packs) | | 193 / 88 | 31, 3.0 |
| Test engineer (test round) | no model call (fast) | | 75 / 16 | 5, 2.8 |
| Code reviewer | skipped (fast) | | 7 / 4 | 0, 1.0 |

### 1. Product manager
- **Job.** Turn the brief into the intake (`agents/product_manager.py`). **Given:** the brief; 3,100-3,300 character
  prompt, 2,900 of schema. **Tools:** `read_file`, its answer.
- **Measured.** One call and about 12 seconds a run, every run; no retries. 37 open questions and 50 deferred items
  over 11 runs; the harness puts back what the brief states and the model dropped.
- **What goes wrong.** Nothing costly. Its open questions (3.4 a run) are not answered by anyone on an unattended run.
- **Improve.** None worth building now. (`INTAKE_ASKS_FIRST` never fired; keep.)

### 2. Tools and models architect
- **Job.** Compare frameworks, storage and providers before the stack is chosen (`agents/tools_models.py`).
  **Given:** intake. **Tools:** readers. Its answer schema is 22,800 characters, seven times its 3,300-character prompt.
- **Measured.** 1-2 calls, 0.7 minutes a run. Over 11 small runs it listed 47 open questions and compared queue
  systems, observability and model providers for products that have none (a notes service, a word counter).
- **What goes wrong.** Sections that the brief rules out are filled anyway, and the stack selector reads the document.
  Cost is small; the risk is scope carried forward.
- **Improve.** (PA.14, small) Offer only the sections the intake's product kind needs; an empty section is not asked.

### 3. Stack selector
- **Job.** One stack and the pack that fits (`agents/stack_selector.py`). **Given:** intake, the tools document, the
  brief's constraint lines, the supported stacks (request 22k-38k characters). **Tools:** readers, `look_up_package`,
  `read_docs`, web tools.
- **Measured.** 1-2 calls, 10 seconds a run. `look_up_package` called 4 times in 13 runs, the docs and web tools 0.
- **What goes wrong.** The medium brief (a Python service with a React page) fits no pack, so the run takes the
  custom path and pays for it in the setup stage (role 8). Nothing tells the selector what that choice costs.
- **Improve.** (PA.10) Where the chosen stack is one service pack plus one page pack, compose the two instead of
  going custom.

### 4. Specialist advisors (`consult_*`)
- **Job.** Numbered advice per specialist before the specification (`agents/specialist_advice.py`). **Given:** brief,
  intake, stack (request 6.5k-10.7k). **Tools:** readers. Cap: 10 items each.
- **Measured.** 38 consultations in 11 small runs returned 359 items: 9.4 of a possible 10 each, about 33 a run for
  products with 8 to 10 criteria. Medium 3: 44 items, which became 88 advice decisions in the specification.
- **What goes wrong.** The cap is the target. Every item must be adopted or declined by the architect, then checked
  by an advice reviewer each sprint. Medium 1's rate limit, which no suite could run under, was adopted advice.
- **Improve.** (PA.9) Size the cap to the brief (for example 3 items up to 10 criteria, 5 up to 20, 10 beyond), and
  have each item say whether the brief asks for it; an item beyond the brief is declined unless the architect quotes
  the brief line that needs it.

### 5. Principal architect
- **Job.** The technical specification, written in parts, plus the interface contract
  (`agents/principal_architect.py`, `graph/specification_parts.py`, `agents/research_brief.py`). **Given:** intake,
  stack, advice, scaffold layout, the harness's pre-read notes. **Tools:** readers (the docs tools are read for it).
- **Measured.** Small runs: 8-11 calls and 10 minutes a run, 20% of all model time, 70% of its output reasoning; 86
  of 102 calls are the section calls. Medium 3: 6 calls, 17 minutes, a conversation of 176,000 characters on the
  second pass and one reply cut at the cap.
- **What goes wrong.** Sections written in separate calls disagree with each other: the reviewer's findings are
  "entry file name inconsistent across the specification", "title validation contradictory across three sections",
  "advice marked declined but its limit still specified" (runs b6c5c636, cc265cee). 9 of 11 first drafts go back, the
  second pass takes 3.5 to 5.4 minutes, and 9 of 11 designs still end at the escalation call.
- **Improve.** (PA.7) After the sections are written and before the review, compare what the sections repeat (file
  names, routes and status codes, limits, each advice item's decision) and ask one call to settle only the lines that
  disagree. `DESIGN_REVISION_CROSS_CHECKED` does this for a revision; the first draft has no such pass.

### 6. Architecture reviewer
- **Job.** Independent review of the specification (`agents/architecture_reviewer.py`). **Given:** the specification
  (45k-72k characters), brief; prompt 12k-25k. **Tools:** readers.
- **Measured.** Small: 2 calls, 1.4 minutes a run; "changes required" on 9 of 11; 45 findings (12 blocking, 14 major,
  15 minor, 4 informational). Medium 1: 18 calls, 16 reads of one file.
- **What goes wrong.** Its findings are good and mostly mechanical (contradictions). It carries the stack's setup
  instructions in its prompt. It re-reads the specification it already holds (reads per file 1.8 on small runs).
- **Improve.** PA.7 removes most of what it finds; then its verdict is about feasibility, which is its job.

### 7. Scrum master
- **Job.** Split the work into sprints (`agents/scrum_master.py`). **Given:** specification (80k-107k characters in
  its memory), criteria. **Tools:** readers.
- **Measured.** Small: 1 call, 1.2 minutes. Medium 3: 6 calls and 10 minutes over two visits; the first plan put all
  13 criteria in sprint 1 and the run was rewound (LF.1315 now splits). 15 open questions in 11 small runs.
- **What goes wrong.** On a custom stack its prompt is 21,000-23,000 characters, of which 14,000 are framework
  blocks (TypeScript setup 4,145, React setup 1,549, test-runner modules) that have nothing to do with sprints.
- **Improve.** PA.5 (prompt content by role kind). Nothing else: LF.1315 covers the sizing.

### 8. Custom setup stage (`stack_setup_*`, only when no pack fits)
- **Job.** Make the project's tests run and declare the commands in `stack-setup.json`. **Given:** the specialist
  prompt (28,800 characters), the specification (62k), a 20k request. **Tools:** the full writer list plus
  `use_runtime` and `run_validation`.
- **Measured (Medium 3, 02:31-04:07 JST).** 193 calls, 88 model minutes, 31 summaries, 129 commands (20 of them
  `python3 -c import ...`, 3 browser installs), 32 writing calls, 17 refusals. Result twice "not proven": first the
  declaration was never written although the request says to write it first; then a browser install that needs
  root. The run went on with an unproven setup, and the lead's plans were then sent back because no contract names
  the unit-test folder (role 11).
- **What goes wrong.** The stage builds product folders instead of the two smoke tests; it is summarised every six
  calls; it does not know that browsers are already installed and that nothing can be installed as root.
- **Improve, in order.** (PA.10) Compose two packs where the stack is their union - no model call. (PA.11) Otherwise
  the harness writes the first `stack-setup.json` from the stack selection and the language table, and the request
  states the sandbox facts the harness already knows (browsers present, no root, no shell); the stage only corrects
  the file and makes the two smoke tests pass.

### 9. Suite writer (QA, `acceptance_author_*`)
- **Job.** Write, and after a review or reopen repair, the acceptance suite (`agents/specialists.py` with
  `writing_the_suite`, `acceptance/requests.py`, `graph/acceptance_nodes.py`). **Given:** criteria, contract, brief,
  review feedback; the specification and the files in its memory. **Tools:** 15-18 (writers, commands,
  `run_validation`, package and docs tools). Limits: 40 calls a stage, then a fresh conversation; 3 rounds.
- **Measured.** Small: 29 stage visits in 11 runs (2.6 a run), 31 calls and 11.6 minutes a run, 76% of output
  reasoning; 124 writing calls, 14 refused (5 on product files). One run (127780fe) took 56 minutes and 76 calls.
  Medium 3: eight visits of 11 to 97 calls each; one visit of 88 calls made no write in 43 minutes (04:48-05:31 JST:
  234 reads of 21 files, 17 summaries).
- **What goes wrong.**
  - Its request is built at 120,000-127,000 characters of memory (the specification alone 87,000) plus 26,000 of
    prompt and 24,000 of tool descriptions: about 47,000 tokens before it reads anything. `loop.sh effects`: 31
    stage memories past the budget were "sent as built" because `REQUEST_BUDGET_FOR_EVERY_STAGE` is off for this run
    (it was on for the later part of Medium 2, whose suite writer made 104 calls with 9 summaries).
  - The summary it gets describes the product's code (summary finding 2), so each life starts by reading again.
  - A visit that passes 40 calls is started again from an empty conversation and does the same.
  - On a sprint's addition it reads the product's code (routers, services, models: about 100 of the 234 reads) and
    fits tests to it; the request says the product is not its to read from.
  - It is asked for all of a sprint's test files in one conversation.
- **Improve, in order.** PA.1 (a stage never starts within a few reads of its summary), PA.2 (a summary that is a
  work note), PA.4 (the suite written and repaired a file at a time once it is past the room, as product files are
  drafted in fast delivery), PA.12 (the routes the started product really serves handed over in place of its
  source).

### 10. QA lead (`acceptance_review_*`) and suite dispute
- **Job.** Judge whether each test would fail were its criterion unmet; lock; rule on disputed locked tests
  (`agents/acceptance_reviewer.py`, `agents/suite_dispute.py`). **Tools:** readers. Reasoning off for the review.
- **Measured.** Small: 14 reviews, 11 approved, 9 findings; 1.9 calls and 1.4 minutes a review; each file read once.
  Medium 3: 59 calls, 17 minutes, 85% of calls read-only, 7 summaries, 6.3 reads a file. Medium 2: 4 reviews, none
  approved, 21 findings. Dispute: 2 calls, 7 rulings in the sample.
- **What goes wrong.** Past the room it is in the same loop as the suite writer, smaller. On a custom stack its
  prompt is 21,700 characters with the same framework blocks.
- **Improve.** PA.1, PA.2, PA.5. Its finding precision is still unmeasured (11-20 item, open): add it to
  `check_precision.py` the way suite checks were added.

### 11. Technical lead
- **Job.** Plan one sprint as work orders (`agents/technical_lead.py`, `analysis/work_orders.py`,
  `graph/planned_work.py`). **Given:** sprint goal, specification, due criteria, the last failed attempt, the cause
  journal; memory 140k-159k characters on Medium 3. **Tools:** readers, `changed_since_sprint`.
- **Measured.** Small: called in 7 of 11 runs; 5 calls and 5 minutes a run where called; 15 plans. Medium 3: 72
  calls, 31 minutes, 10 summaries, **12 plans in 4 visits**; the reasons sent back were "No `testing` work order"
  and "there is no shell here, so `&&` ... do nothing"; one plan had an empty title. One reply spent 20,849 output
  tokens. tasks-api 24: 4 plans in 2 visits. Medium 2 (before LF.1286): 131 calls, 603 reads of 82 files.
- **What goes wrong.** The harness adds a missing testing work order itself only when a pack's contract names the
  unit-test folder (`work_orders.with_a_testing_work_order`); a custom stack has no contract, so the plan goes back
  whole, to a fresh conversation, each time. A command joined with a shell operator is also sent back although
  splitting it is mechanical. The lead's request budget is recorded as applied with nothing cut at twice its target.
- **Improve.** (PA.6) Repair what is mechanical in the plan (testing work order from the declared unit folder of a
  custom setup too, shell operators split into separate commands, an empty title taken from the description's first
  line) and send back only what needs judgement, as one more turn of the same conversation. Then PA.1 for its memory.

### 12. Builders (`specialist_backend|database|ui_ux|security_reliability|documentation_*`) and drafting
- **Job.** Build a work order's files (`agents/specialists.py`, `graph/drafting.py`). Fast delivery drafts one file
  a call with no tools (system prompt 138 characters); the agent loop is used on thorough runs and after a failure.
  **Tools (loop):** 16-17.
- **Measured.** Drafting: 140 calls, 28 minutes in 11 runs - 12 seconds a file, the cheapest writing in the
  harness. Agent-loop builders, small (2 runs): 120 calls, 25 writing calls, 4 refused. Medium 2: 261 calls, 152
  minutes, 43 summaries, 463 reads of 86 files, 14 refused writes, and features handed over as stubs. Medium 3 so
  far: 23 calls, 5 minutes, 1 summary (after LF.1287-1289 and LF.1315's smaller sprints).
- **What goes wrong.** Past the room the loop builder re-reads (Medium 2); 21 calls in the sample went to tools that
  were withheld but still listed. Drafted products are handed to the tester without a build (role 13).
- **Improve.** PA.3 (build before the tester), PA.1 and PA.2. Medium 3's first builders look healthy; judge again
  when its sprint 2 has run.

### 13. Unit-test writer (`specialist_testing_*`, the testing work order)
- **Job.** Write unit tests against the work orders' interfaces; never product code. **Tools:** writer list plus
  `run_validation`. Its first refused product write is kept as a blocker (LF.1310).
- **Measured.** 3 small runs: 125 calls, 21 minutes, 32 writing calls and **25 writes refused** (17 on Rust 4, 8 on
  Java 12, product files), 13 answers carrying 40 blockers and 41 defects (27 blocking). Rust 4, one visit: 38
  calls, 12 refusals, 4 answers.
- **What goes wrong.**
  - It runs on a product that does not compile. Its answers are accurate compiler diagnoses with the fix written
    out ("declare the module public", "use the async listener"), and it then tries to make the fix itself.
  - After it answers, the harness's check on the stage's files reports the compiler's error in the product's entry
    file and says "Fix these errors now"; every such write is refused. Its budget notice says "You have NOT written
    a structured response yet" after it has (run-c4fd577a, 23:56-23:58 JST 11-24).
  - Both runs predate LF.1310's deploy, so whether that fix stops the retries is not yet seen.
- **Improve.** PA.3 (the product builds before the testing work order starts; a build error goes to the code's
  owner with the compiler's output), PA.8 (the post-answer check names only files the stage may write).

### 14. Code reviewer (thorough delivery only)
- **Job.** Read the sprint's diff against the work orders (`agents/code_reviewer.py`). **Tools:** readers.
- **Measured.** Medium 3: 4 reviews, 7 calls, 4 minutes, each file read once, **0 findings, 4 approvals**; the run's
  ledger has 7 defects raised in the same sprints. Medium 2: 2 reviews, 8 findings (2 blocking). Medium 1: 46 calls, 83% read-only.
- **What goes wrong.** After the reading fix it is cheap; on Medium 3 it has yet to find anything the test round
  then finds. Too few reviews to call it blind.
- **Improve.** Measure before changing: record, per review, the defects the next test round raises in the files it
  approved (PA.13 scoreboard). Skipped in fast delivery, where the security reviewer does its work instead (role 18).

### 15. Test engineer (`test_round_*`, thorough delivery only)
- **Job.** Report defects from the round's measurements; may write test files only. **Tools:** the writer list.
- **Measured.** Medium 3: 11 answers in 75 calls and 16 minutes, 6 defects, 7 writing calls, 5 summaries. Medium 1:
  305 calls, 165 minutes, 563 reads of 80 files, 47 summaries. Fast runs make no model call here: the harness
  measures alone.
- **What goes wrong.** It holds 17-19 tools and the 29,000-character specialist prompt to report what the harness
  has already measured; on a large product it reads the code to explain failures (Medium 1).
- **Improve.** PA.1, PA.2. Then compare its defects with the harness's own for the same round: if it adds few, the
  thorough path can use the fast path's measurement alone (a measurement, not a build item yet).

### 16. Fixers (`defect_fix_*`, and the one-file rewrite `defect_fix`)
- **Job.** Fix one defect; the measurement after decides (`graph/nodes/fixes.py`, `graph/fixer_request_shape.py`).
  **Tools:** 15-16. Limits: 16 calls a fix stage, 12 before it must write, then the rewrite path.
- **Measured.** Small: 344 calls (97 are tool-less rewrite calls), 104 minutes, 19% of model time; 61 writing calls,
  5 refused, 13 commands refused; 12 replies answered from their own reasoning. Ledger over 12 runs: **fixed 20,
  left open 42, reverted 5, unverified 7, closed with no fixer 17.** Defect sources: acceptance suite 24, test round
  22, language service 12. Medium 3: 181 calls, 59 minutes; left open 10, unverified 4, closed by a round 3,
  reverted 2, fixed 0.
- **What goes wrong.**
  - About one fix stage in three ends in a kept fix.
  - 44 defects were first worked "tests only" (a failing unit test beside a green suite): 1 fixed, 2 closed by the
    next round, 9 left open or unverified; 29 later records allow product code. The rule protects against red unit
    tests shipped (owner decision, in force) but its first attempt is mostly a lost stage.
  - 26 fixer calls went to a tool that was withheld but still listed.
  - It is the one role whose opening request is cut to the budget, and the one whose reads per file are low (1.8).
- **Improve.** (PA.15, behind a switch, the owner's rule kept) choose the side from the failure before the first
  attempt: an error raised inside product code with no assertion reached (an import, a compile error, an exception
  in a product file) allows product code at once; an assertion that fails stays tests-only. PA.16 for withheld
  tools.

### 17. Advice reviewers (`advice_review_*`)
- **Job.** Each consulted specialist says which adopted advice the sprint should have built
  (`agents/advice_review.py`). **Tools:** readers. Findings join the Sprint Record as minor.
- **Measured.** Small: 19 reviews in 6 runs, 25 minutes (4% of model time, 96% of output reasoning), 11 "not built"
  items, 0 design problems. Medium 3: 8 reviews, 14 minutes, 13 items.
- **What goes wrong.** It costs more than the security and milestone reviews together and can only produce minor
  findings. Its load follows the number of adopted items.
- **Improve.** PA.9 shrinks its input. Then one call for all specialists instead of one each (the plan's
  `ADVICE_ONE_CALL`, never built): the request is the same memory three or four times over.

### 18. Security reviewer
- **Job.** Security and reliability findings on the sprint's changes (`agents/security_reviewer.py`).
  **Tools:** readers.
- **Measured.** Small: 8 reviews, 14 calls, 7 minutes; 18 findings (1 critical, 2 high, 3 medium, 4 low, 8 info).
  Medium 2 before the reading fix: 52 calls, 240 reads of 24 files; Medium 3 after: 8 calls, 1.4 reads a file.
- **What goes wrong.** On tasks-api 24 its critical finding was a missing type import; its info findings were an
  unused model class and comments in a test file. Five of six findings were not about security. The second review of
  the same sprint repeated three of them, and the milestone review repeated two as suggestions.
- **Improve.** (PA.17) A finding names the security or reliability harm (who can do what to which data or service);
  one that names none is recorded as a code note, not a security finding, and cannot be critical or high. A finding
  already recorded for the sprint and not acted on is not raised again.

### 19. Milestone reviewer
- **Job.** Accept, ask for changes or block the sprint (`agents/milestone_reviewer.py`). **Given:** acceptance
  evidence, due criteria, work orders, findings; memory 72k-149k characters. **Tools:** readers.
- **Measured.** Small: 8 verdicts, **5 "changes required"**, 3 accepted; 18 findings (2 blocking, 7 major). 1.5
  calls and under a minute each. Medium 3: 2 accepted.
- **What goes wrong.** Its verdict and what the run does disagree. On tasks-api 24 (10/10 hidden) sprint 1's
  "changes required" (a work order's promised change not made) was followed at once by sprint 2:
  `MILESTONE_EVIDENCE_GATE` let the run go on. Whether the other four verdicts cost a re-plan was not traced. It
  also repeats the security review's info findings as suggestions (role 18).
- **Improve.** Low priority. Tell the reviewer what a send-back needs on a green sprint (the gate's own rule), so
  its status says what will happen, and count the verdicts the gate overrides (PA.13). PA.17 removes the repeats.

### 20. Escalation call
- **Job.** Decide a stuck design or sprint in one tool-less call (`graph/escalation.py`).
- **Measured.** 9 of 11 small runs and all three medium runs reach it after the design review, 0.2 minutes each.
- **What goes wrong.** Cheap, but it is the normal path, not the last rung: the design review does not converge.
- **Improve.** PA.7.

## Cross-role patterns

**C1. Fixed load fills the window before the stage works.** The slot is 91,776 tokens; 32,000 are held for the
reply. On Medium 3 the opening request of the suite writer, QA lead, scrum master, unit-test writer and builders is
built at 120,000-133,000 characters of memory against a 75,300 target, plus 18,000-29,000 of prompt and up to 24,600
of tool descriptions. The cut that would fix it is recorded and not applied (31 of 92 openings). Fixers, whose cut is
applied, have the lowest re-read rate. Small runs are unaffected: their requests are built under the target.

**C2. The summary keeps the wrong thing.** The summariser is the library's general one. Given a conversation that is
mostly file reads, it writes a description of the files; the files are in the project memory anyway. The stage's
findings, decisions and next step are lost at every summary, and at the 40-call restart. 74 summaries in one role in
one run.

**C3. A stage is told to do what a guard then refuses.** The testing stage and the product's compiler errors (role
13); the tests-only first fix of an error that is in product code (role 16); a withheld tool that stays listed (29
refused calls on Medium 3; 49 file reads, 15 commands and 9 writes in the sample); the setup stage and a root
install (role 8). Each refusal is a whole model call of 35,000-50,000 input tokens.

**C4. Every role reads every framework block.** On the custom stack 14,000 characters of framework text, 5,700 of
them setup steps, go to the scrum master, the reviewers and the QA lead on each call. The switch that shapes this
for reviewers was measured only on a small pack-based brief, where the saving is small.

**C5. Roles doing another role's job.** The unit-test writer diagnoses and tries to fix the build. The security
reviewer does code review in fast delivery. The suite writer reads the product's code to shape its tests. The setup
stage creates product folders. The tools architect designs queues the product does not have.

**C6. Work the harness can do is sent back to a model.** A missing testing work order, a shell operator in a
command, an empty title (lead); contradictions between specification sections (architect and reviewer); the first
`stack-setup.json` (setup).

**C7. Caps are targets.** Advisors return 9.4 of 10 allowed items; the advice becomes specification, tests and
review load.

**C8. Handoffs that lose information.** A summary (C2). A stage restarted at 40 calls. A plan sent back as a fresh
request. A tester's exact diagnosis, which reaches the fixer as free text in `blockers` rather than as the fix
request. Findings repeated by the next review because nothing says they were already recorded.

**C9. Tools carried and not used.** In 13 runs writers never called `read_docs`, `search_the_web`, `read_web_page`,
`research`, `module_exports`, `look_at_page` or `move_artifact`; `look_up_package` 6 times, `delete_artifact` 5.
`grep` 15 times against about 4,300 `read_file` calls: the model finds a name by reading whole files.

## Build list

Ranked by expected effect. "Always on" follows the owner's policy for bug and quality fixes; a size threshold keeps
the small path as it is. Each item gets a test proven to fail on the old code; each new prompt rule also gets a test
that its text holds none of the whole words task, tasks, to-do, todo, button, click, checkbox. No item names a
language, framework or product; stack facts stay in packs, `plugins/seed.py` and the language table.

| Item | What | Files | Size | Measured by | On or switch | Test |
|---|---|---|---|---|---|---|
| PA.1 | A stage's opening request leaves room to work: where prompt, tool descriptions and memory together pass a set share of the summary trigger, the memory is cut to the budget for that stage (the cut `request_budget` already computes), whatever the stage. Under the threshold nothing changes | `agents/request_budget.py`, `agents/project_memory.py`, `agents/role_agent.py` | M | summaries per stage and reads per file in `loop.sh effects` (suite writer 74 and 16.9; target under 5 and 2); "sent as built" openings (31, target 0); small-run hidden scores unchanged | Always on, by measured size | A request built past the threshold is cut and one under it is byte-identical to today's; fails on old code for the suite writer's stage |
| PA.2 | The summary is the stage's work note: the summariser is given the role and the request's aim and asked for what was found (file and lines), what was decided, what was changed, what is still to do; it is told not to describe file contents the memory holds. The same note is what a 40-call restart starts from | `agents/compaction.py`, `agents/carry_over.py` | M | reads in the three calls after a summary; calls per writing call (suite writer 13.6 on Medium 3); stages restarted at the call ceiling | Always on | The summariser's request for a conversation of reads carries the stage's aim and the four headings, and the restart request carries the note; plus the banned-words test on the new text |
| PA.3 | The product builds before the testing work order starts: after drafting or the builders, run the contract's build (or the language service where there is none); a failure goes to the code's owner with the compiler's output, and the testing work order waits | `graph/nodes/building.py`, `graph/drafting.py`, `graph/unfinished_build.py` | S-M | refused product writes by the testing role (25 in 3 runs, target 0); its calls a run (42); blockers that restate a compiler error | Always on | A plan whose drafted product fails its build dispatches the owner's repair first; fails on old code, which dispatches the tester |
| PA.4 | Past the room, the suite is written and repaired a file at a time: one call sequence per test file, holding that file, its criteria, the contract lines it uses and its failure output; the harness picks the files from the review's findings and the dry run | `graph/acceptance_nodes.py`, `graph/acceptance_batches.py`, `acceptance/requests.py`, `acceptance/by_sprint.py` | L | suite-writer calls and minutes per locked test; visits with no write (1 of 88 calls on Medium 3); rounds to lock | Switch, on for the next medium run, then always on by size | A repair of findings in two files makes two bounded requests, each without the other file; a suite under the size makes one, as today |
| PA.5 | Prompt content by role kind for every stack: planning and reviewing roles get no setup, install or command blocks and no command guides; a custom stack's generated blocks are marked setup, build or review when stored. Measure the existing `REVIEWER_SHAPED_PLUGIN_CONTENT` on a medium run first, then extend it to the scrum master, lead and QA lead | `agents/prompt_size.py`, `plugins/middleware.py`, `plugins/registry.py` | S | prompt characters per call for read-only roles (21k-25k on Medium 3, target under 12k); findings per review unchanged | Switch (existing), measured on medium | A scrum-master prompt rendered for a two-framework custom stack holds no setup block; fails on old code |
| PA.6 | Mechanical plan repairs by the harness: a testing work order also from a custom setup's declared unit folder and pattern; a verification command joined by a shell operator split into separate commands; an empty title filled from the description. What still needs judgement goes back as one more turn of the same conversation | `analysis/work_orders.py`, `graph/nodes/building.py`, `agents/technical_lead.py` | S-M | plans per lead visit (3.0 on Medium 3, target 1.2); lead minutes a sprint | Always on | A plan with no testing work order on a workspace with only `stack-setup.json` gains one; a joined command is split; both fail on old code |
| PA.7 | A consistency pass on the first draft of the specification: values the sections repeat (file names, routes with their status codes, limits, each advice item's decision) are compared, and one call settles only the lines that disagree, before the review | `graph/specification_parts.py`, `graph/design_revision_cross_checked.py`, `analysis/` (a section comparer) | M | first-draft "changes required" (9 of 11, target under 4); designs reaching escalation (9 of 11); architect minutes a run (10) | Always on | Two sections naming different entry files, and an advice item declined in one section and specified in another, are found and sent to the settle call; fails on old code |
| PA.8 | The post-answer check asks a stage to fix only files it may write; a compiler or language-service error in another role's file is added to the answer's blockers by the harness and the stage ends. The budget notice reads the answer that exists (confirm why it did not: `settled_answer` saw none after the check's turn) | `graph/workflow.py` (`_diagnostics_in_files_touched`, `_ask_about_high_confidence_diagnostics`), `agents/settled_answer.py` | S | answers per stage visit (4 on one visit, target 1); refused writes after a first answer (5, target 0) | Always on | A testing stage whose manifest change surfaces an error in a product file gets no "fix these" turn and its answer gains the blocker; fails on old code |
| PA.9 | Advice sized to the brief: the cap follows the criteria count; each item states whether the brief asks for it; an item beyond the brief is declined unless the architect quotes the brief line; advice reviews run as one call | `agents/specialist_advice.py`, `agents/principal_architect.py`, `agents/advice_review.py` | S-M | advice items a run (33); specification characters; advice-review minutes (4% of model time); hidden and quality scores | Switch (`ADVICE_SIZED_TO_THE_BRIEF`), two runs a family | Cap by criteria count; a beyond-brief item with no quoted line is declined; banned-words test on the new rule |
| PA.10 | A stack that is one service pack plus one page pack is set up from the two packs, each in its folder, with one contract; no setup stage | `stacks/__init__.py`, `stacks/scaffold.py`, `stacks/contract.py`, `agents/stack_selector.py` | L | setup minutes on the medium brief (96, target under 5); "setup not proven" (2 of 2) | Always on (a new pack path; `verify_packs` after) | A selection naming a supported service stack and a supported page stack scaffolds both and writes one contract; fails on old code, which goes custom |
| PA.11 | Custom setup starts from the harness's own draft of `stack-setup.json` (from the stack selection and the language table) and its request states the sandbox's facts: browsers present, nothing installed as root, one program a command | `stacks/` (the custom setup module), `agents/environment_contract.py` | S | declaration present at the first proof (0 of 1); setup calls (193); browser-install commands (3, target 0) | Always on | The setup request for a custom stack carries a draft declaration and the facts; fails on old code; banned-words test |
| PA.12 | The suite writer of a later sprint is given the routes or commands the started product answers (read by the harness) and the contract, in place of the product's source in its memory | `acceptance/requests.py`, `agents/project_memory.py`, `acceptance/by_sprint.py` | M | suite-writer reads of product files (about 100 in one visit, target 0); tests later ruled wrong in a dispute | Switch, one medium run | The memory for a sprint addition holds no product source and the request holds the served routes |
| PA.13 | The per-role scoreboard as a command: calls, model minutes, read-only share, refused writes, answers per visit, summaries, plans per lead visit, milestone verdicts the evidence gate overrode, and defects the next round raised in files a review approved - per role, per run | `scripts/loop/`, `observability/transcript_metrics.py` | S | this audit's tables printed by `loop.sh effects`; used at every audit | Always on (tooling) | Fixture transcript with known counts |
| PA.14 | The tools-and-models answer offers only the sections the intake's product kind needs | `agents/tools_models.py` | S | open questions and empty-topic sections a run (47 questions in 11 runs) | Always on | A command-line product's answer schema has no queue or provider section |
| PA.15 | The first fix of a failing unit test chooses its side from the failure: no assertion reached and the error raised in product code allows product code at once; an assertion that fails stays tests-only | `tools/tests_only_writes.py`, `graph/defect_fix_modes.py`, `stacks/languages.py` (error shapes per language) | M | first-attempt outcome of such defects (1 fixed of 12 measured); fix stages a run; red unit tests shipped must stay 0 | Switch; the owner's rule stays in force | An import error in a product file gets the product mode; an assertion mismatch gets tests-only |
| PA.16 | On the calls where only the answer is allowed, ask the server for the answer tool by name (the tool list's bytes unchanged); where the server does not honour it, as today | `agents/settled_answer.py`, `agents/stable_tools.py`, `models/` | S | withheld-tool refusals (29 on Medium 3); stages ended without an answer | Switch (server-dependent; probe both ports first) | The last-calls request carries the named tool choice when the model's capabilities allow it |
| PA.17 | A security finding names its harm; one that names none is a code note and cannot be critical or high; a finding already recorded for the sprint is not raised again | `agents/security_reviewer.py`, `agents/finding_category.py`, `agents/milestone_reviewer.py` | S | security findings with no security harm (5 of 6 on one review); findings repeated across reviews of a sprint (3) | Always on | A finding with no harm is re-labelled and capped; a repeat is dropped; banned-words test |
| PA.18 | Tool lists by measured use: a writer's list leaves out tools never called for that role across the last N scored runs unless the stage's request asks for one; a guide to search for a name before reading whole files | `agents/stage_tools.py`, `agents/lean_prompts.py`, `models/guidance.py` | S | tool-description characters per writer call (22k-25k); `grep` share of reads; hidden scores | Switch (`WEB_TOOLS_BY_MEASURED_TIER` exists, off: measure it first), one guide switch | The suite writer's list for a model measured never to call the docs tools omits them; banned-words test on the guide |

**Order.** PA.8 and PA.3 first (bugs, small, they stop refused-write loops on every family). PA.1 and PA.2 next: they
are what the medium brief needs and they are measured on the run already live. PA.6, PA.7 and PA.11 after them. PA.4
and PA.10 are the large ones; build PA.4 only if PA.1 and PA.2 leave the suite writer above 5 summaries a visit.

**For the main session now (no code).** Medium 3 runs with `READS_SIZED_TO_THE_ROOM` only. Medium 2 also had
`REQUEST_BUDGET_FOR_EVERY_STAGE` and `REPLY_ROOM_SIZED_PER_ROLE` on, and its suite writer was summarised 9 times in
104 calls against 74 in 462 here. Turning both on for Medium 3 at its next sprint boundary would test PA.1's effect
before it is built.

## Not verified

- Why the budget notice said no answer had been written after one had (role 13): read from one transcript, not
  traced in `settled_answer`.
- Whether LF.1310 stops the tester's retries: no run in the sample reached it.
- Fix outcomes are ledger events; "fixed" was not re-measured, and outcomes with no recorded mode (most of them)
  could not be split by fix path.
- What four of the five "changes required" milestone verdicts cost: only tasks-api 24's was followed, and there the
  run went on to its next sprint.
- Model minutes on :8888 and :1234 are pooled; reasoning share is taken from reported reasoning tokens, or from
  reasoning characters where the server reports none.
- Medium 3 is mid-run: its numbers stop at 09:57 JST 11-25.
