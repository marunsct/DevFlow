# Per-role audit: suite writers, technical lead, prompts per role

2026-11-20 (JST). For the owner and the agents that build the harness. Read-only audit: no code, tests or documents
changed. Data: `loop.sh patterns` (replies since 11-17), `loop.sh timing`, `loop.sh disputes` (110 runs with a
dispute), the transcripts and `.harness/` records of six finished runs on the local model (Qwen3.6-35B-A3B), and
`check-findings.jsonl` from all 218 stored workspaces. Prompt sizes are the system message as actually sent (taken
from the transcripts' `model_request` records, largest seen per stage family), not reconstructed from source.

| Run | Family | Hidden | Wall min | Model min | Author calls / model min / reasoning | Lead plans |
| --- | --- | --- | --- | --- | --- | --- |
| run-d2d6fd42 | notes-api-csharp | 9/9 | 138 | 52 | 75 / 25 / 84% | 1 |
| run-aa3693b6 | notes-api-php | 9/9 | 78 | 68 | 13 / 3 / 51% | 2 |
| run-09fc4306 | web-todo | 10/10 | 125 | 104 | 21 / 14 / 69% | 1 |
| run-9c875db7 | notes-api-java | 9/9 | 64 | 52 | 18 / 5 / 51% | 0 |
| run-ea01f85c | tasks-api | 10/10 | 179 | 143 | 29 / 8 / 60% | 5 |
| run-62a7d976 | notes-api-ruby | 9/9 | 57 | 49 | 49 / 18 / 83% | 1 |

## Summary

- **A suite check has a confirmed false positive that costs whole rounds.** `tests_that_want_json_from_a_204`
  (`suite.py:3963`, `:4027-4036`) takes the `'Content-Type': 'application/json'` header a test *sends* as an
  assertion. On the C# run it returned the same finding on the same line 7 times and kept the post-lock repair open
  for about 10.6 model minutes (10:14-10:29 JST). Reproduced against the current source.
- **Identical findings are re-sent with no limit.** Across all workspaces, 187 findings came back unchanged 3 or more
  times; 118 of them from three checks: `views_never_acted_within` (10 runs), the 204 check (5) and
  `contract_lines_with_no_test` (7). The fingerprints are recorded and nothing reads them.
- **QA's system prompt contradicts its request.** It still says "define and run unit, integration ... tests", "build
  code ... end-to-end development" and "tests live beside the code". The request says "Product code is not yours". The
  C# author tried unit-test and product files 3 times and was refused each time.
- **The reclassification cap costs time far more often than score.** 60 rulings went past the cap in 23 of 110 dispute
  runs, and only 3 of those runs lost hidden marks. The tasks-api run's three late re-plans followed failures of locked
  tests later ruled wrong. `CONTESTED_TESTS_CONFIRMED` is built and still unmeasured.
- **The environment contract lists the wrong commands** for C#, PHP, Java and Ruby runs: cargo and go, but no dotnet,
  php or mvn (`environment_contract.py:217-219`).
- **Read-only roles carry writer material:** 2.9k-9.7k characters of how-to-write guidance, a command guide without a
  command tool, and fixer lessons.
- **The technical lead:** 0-1.4 model minutes on small briefs, 19 on tasks-api. Requests run 96k-234k characters, with
  the highest p90 reply (20,117 tokens) and the most cut-offs (14 of 547). The harness's own C# work order is refused
  for a `;` inside a pack argument (`work_orders.py:244`).
- **46 banned-word hits in 13 of 28 rendered prompts**, plus stack text in the lead's prompt (`technical_lead.py:737`).

## 1. Suite writers

**What they are told.** The author's system prompt is the testing role's prompt with `writing_the_suite=True`: role
description, responsibilities, "Beginner documentation requirement", command constraints, the dependency exemption,
directory and layout rules, the write-tool table, "REASONING IS NOT WORK", the stack's plugin blocks and lessons. That
came to 13.2k-16.6k characters. The request (`acceptance/requests.py:264-392`) holds the criteria, the pack's suite guide,
the brief, the interface contract, the API reference, the specification rulings (DR-n) and about 20 rules. The C#
request was 50.5k characters, plus 33k of project memory and 22k of tool schemas. Some rules apply only to products
with a page ("Where the user adds records through a page", "Where a view shows only the records in some state",
`requests.py:355-369`). They are worded conditionally, but every service and CLI suite still receives them.
`requests.py:384` is missing a space ("right.A syntax error").

**Tools.** Readers, `write_artifact`, `edit_artifact`, `delete_artifact`, `move_artifact`, `run_terminal_command`,
`read_command_output`, `look_up_package`, `read_docs`, `run_validation`, plus `module_exports` and `look_at_page` where they
apply. The C# author used `run_terminal_command` 18 times and `run_validation` 5 times.

**How the output is checked.** About fifty mechanical checks run before the QA lead (`acceptance_review`). They send
work back up to `MAX_ACCEPTANCE_ROUNDS` = 3 (`acceptance_nodes.py:39`), then `ONCE_AT_THE_LIMIT` (`:908`). After the
lock come reopens, disputes and the cap `max(2, locked // 10)` (`acceptance_nodes.py:2268-2285`). `CONTESTED_TESTS_CONFIRMED`
(`graph/contested_tests.py`, off) re-proves a ruling past the cap. Write guards keep QA inside the acceptance folder.

**What the data says.**

- *Cost sits in repeat rounds, not in the first draft.* C#: the first draft took 3.6 model minutes, the two pre-lock
  send-backs 2.8, and the post-lock repair 18.2. Ruby: the first draft took 4.5. The second round, for one
  `requests_with_a_fetch_body` finding, took 13.6 (07:20-07:35 JST). The author probed Playwright's internals with
  `node -e` 14 times, then called `delete_artifact` 31 times on the harness's own `tmp-inline-*.cjs` copies, 8 files four
  times over, each answered "the harness removes it itself". The rule "Scratch files ... remove them with
  `delete_artifact`" (`role_agent.py:521`) invites that loop. It recurred in only 2 runs since 11-17.
- *The 204 check is wrong on C#, verified.* The flagged test (`integration.spec.js:55`) asserts `status() === 204` on
  the DELETE and reads no headers. `_ASSERTS_JSON_CONTENT` matched the request header on line 101. With no `.headers(`
  read in the block, `if not read` flags it (`suite.py:4035`). On Java run b668a924 the same check fired 4 rounds
  running, but the current source would not flag that test. That case is probably fixed already; I did not verify
  which version was deployed when it fired.
- *Reasoning is most of the author's output:* 84% on C#, 83% on Ruby, 51-69% elsewhere. Patterns since 11-17 show 2,087
  author replies, none cut off, p90 6,152 tokens. So the cost is call count, not long replies.
- *Writes outside the suite.* There were 3 refusals on C#. Patterns show "'X' is product code, and this is the testing
  work order" 38 times in 18 runs, which is the testing work order's unit-test writer editing product code. On PHP the
  unit-test writer (`specialist_testing_1`) tried `src/Database.php` twice. The refusal works. The prompt contradiction
  is what produces the attempts.
- *The QA lead* raised 1,287 of the 2,267 stored findings (57%). Its p50 reply is 163 tokens and its p90 17,273, so it is
  bimodal, with reasoning off (`reviews_without_reasoning`). Java: 6 calls, 8 model minutes, 49.9k tokens, 5 findings
  over two send-backs, hidden 9/9. Nobody measures the precision of suite checks or QA-lead findings against hidden
  scores. `check_precision.py` does that for integration checks only.
- *Disputes* (110 runs): 164 disputes, 682 tests shown, 191 called wrong, 125 reopened, 60 past the cap in 23 runs.
  Three of the 23 past-cap runs scored under full hidden marks (0.75, 0.75, 0.7). So the cap costs time far more often
  than it costs score.

## 2. Technical lead

**Prompt** (`technical_lead.py:716-800`, 16,683 characters as sent): pick one sprint; delegate only to the roles needed;
test files go to `testing`; one file one owner; the full work-order schema (title, description, files, interfaces,
steps, edge cases, test cases, verification, out of scope, acceptance criteria); "a milestone that changes code includes
one testing work order"; the readiness checks it will face; "every milestone must change what the product does". Then
scope discipline, WHERE FILES GO, constraints, the stack's plugin blocks and lessons. Tools: readers and
`MilestonePlanOutput`.

**Inputs.** The sprint goal, specification, due criteria, carried items, the last failed attempt, the cause journal and
review comments. As sent, a request is 96k-234k characters. In medians: project memory 134k, specification 56k, request
29k, conversation 28k. That is about 60k tokens per call before the lead reads a file.

**Decisions and rework.**

- *Fast delivery.* `planned_work.work_orders_from_the_specification` should make the first plan with no model call. In all
  five runs that planned, the lead was still called for the first plan. A likely cause, read from the code and not
  confirmed by a log: `BUILT_SHARE` (`planned_work.py:79-80`) counts the scaffold's stub entry file as built. A one-file
  service then has half its planned source "built" before anything runs. On C# the planned files are `Program.cs`
  (a 12-line stub) and `NoteApiTests.cs`.
- *Readiness send-backs* were 3 in 6 runs. On web-todo the plan named no owner for `main.spec.js`. On tasks-api a
  re-plan handed out no work orders. On C# the harness's own testing work order failed the harness's own check:
  `" ".join(pack.unit_test)` (`work_orders.py:244`; also `building.py:43`) turned the argument
  `junit;LogFilePath=...;MethodFormat=Class` from `csharp_aspnet_api.py:239` into a line with a shell `;`.
- *Re-plans.* Over the last 60 ledger rows, runs with 0-1 plans had a median 77 active minutes and 17 of 18 scored full
  hidden marks. Runs with 3 or more plans had a median 96 minutes and 17 of 27, mostly Rust. That is correlation: a
  re-plan follows a failed attempt. On tasks-api the plans were not the cause. Each re-plan came after a round that
  failed on locked tests the dispute later called wrong.
- *Reply size.* p90 20,117 tokens, 14 cut-offs and 9 text replies in 547 replies. The 05:15 JST tasks-api visit took 9
  calls, 11.8 model minutes and one cut-off.

## 3. Prompts per role

Characters of the full system message as sent, including the 1,890-character environment contract. It varies by stack
through the plugin blocks. "Framework" is the stack's plugin block.

| Role (stage family) | Prompt chars | Tools | Main sections | Issues |
| --- | --- | --- | --- | --- |
| product_manager | 5,177 | read_file | responsibilities, constraints, finish | none |
| tools_models | 5,220 | readers | responsibilities, constraints, finish | none |
| stack_selector | 12,209 | readers, look_up_package, read_docs | constraint-as-boundary, dependency exemption | "click a button" (`environment_contract.py:93`) |
| advisors (consult_*) | 9,259-14,387 | readers | finish, framework | framework 4.6k-9.7k, 50-67% of the prompt |
| principal_architect | 25,072 | readers | scope, testability, dependency exemption, layout, framework 9.7k | largest; "task dashboard" |
| architecture_review | 20,660 | readers | scope, dependency exemption, framework 9.7k incl. setup modules | writer setup guidance for a reviewer; "task dashboard" |
| acceptance_author (QA) | 13,165-16,636 | 13-15 writers, run_validation | testing role, beginner docs, constraints, layout, write table, reasoning, framework 4.0k, lessons | contradicts its request (section 1); fixer lessons; product-code plugin rules ("wrap async route handlers") |
| acceptance_review (QA lead) | 12,157 | readers | would-it-fail, record shape, views, shared test rules, contradicting pairs, finish | framework 4.0k of writer guidance; command guide without a command tool; fixer lessons |
| acceptance_dispute | 7,996 | readers | ruling rules, finish | framework 2.9k; input about 200k characters; p90 reply 20,096 |
| scrum_master | 12,160 | readers | responsibilities, scope, framework | "task dashboard" |
| technical_lead | 16,683 | readers | work-order schema, readiness, scope, layout, framework | 12 banned hits; "vanilla JavaScript and browser storage" (`:737`) |
| specialists, defect_fix | 16,493-19,885 | 13-15 writers (+run_validation for testing) | responsibilities, beginner docs, constraints, testability, dependency exemption, layout, write table, reasoning, framework, lessons | 3-5 banned hits; finishing rule said three times; tool schemas 21.8k-22.7k, more than the prompt |
| security_review | 10,789 | readers | scope, framework | "task dashboard" |
| milestone_review | 14,330 | readers | scope, dependency exemption, framework | "task dashboard" |
| advice_review_* | 7,285-8,493 | readers | finish, framework | writer framework |
| drafting / escalation | 138 / 91 | none | one line | fine |

**Overlap and contradiction.**

- The finishing rule appears three times in writer prompts: "How to finish", "ARTIFACTS ARE NOT YOUR STRUCTURED
  RESPONSE" and "Return the response in the required output schema only".
- "NEVER remove or disable application logic" appears twice in the testing prompt.
- Scope discipline (1,420 characters) is one shared constant in six roles, which is fine. Its example is the
  task-dashboard and Kubernetes story.
- The real contradictions:
  - The suite writer's role text against its request.
  - "Tests live beside the code they test" (`project_layout.py:46`) against a fixed acceptance folder.
  - The environment contract's command list against the sandbox.
  - `GUIDE:STOP_WHEN_DONE` ("when the checks you were asked to make pass, stop") given to roles that run no checks.
- The lead's "a milestone that changes code includes one testing work order" is enforced anyway: the harness adds one
  (`work_orders.py:248`).

**Stack-specific text outside packs and `seed.py`.**

- `technical_lead.py:737`.
- `environment_contract.py:84-95,193` names Playwright in every stage. It is derived from the allowlist, so this is
  borderline.
- The page-only suite rules at `requests.py:355-369` are product-kind specific rather than stack specific. They belong
  behind the product kind, the way `actions_within_a_view` already is.

**Banned words.** The 46 hits come from older shared text:

- `scope_discipline.py:35,44` ("a task dashboard", six roles);
- `technical_lead.py:725-792` (12 hits);
- `specialists.py:135,1342-1343,1363`;
- `environment_contract.py:78-79,93` ("click a button");
- `work_orders.py:1026`.

The rule bans these words in each new prompt rule, and each new rule has its own test. No test scans the rendered
prompts, which is why the older hits survive.

## Recommendations, ranked by expected value

1. **Fix `tests_that_want_json_from_a_204`** (sure fix, always on). Count only assertions: `expect(...)` or
   `headers()[...]` reads, never `headers: {...}` in a request. Test: the C# suite above must not be flagged.
   *Measure:* identical repeats of this check (39 in 5 runs, should be 0), and repair rounds and author model minutes
   on notes-api runs (C# 25 minutes).
2. **Stop re-sending an identical mechanical finding** (sure fix). After the same check, test and text survive one
   repair round, the next round does not send that finding back again. It goes to the QA lead as a suspected false
   positive and is recorded as a gap. Then extend `check_precision.py --write` to the suite checks: a finding on a
   test that stayed locked in a run that scored full hidden marks counts as wrong. *Measure:* findings repeated 3 or
   more times (187 in all, should be 0), acceptance rounds per lock, author model minutes. Hidden score
   and false acceptances must not move.
3. **Measure `CONTESTED_TESTS_CONFIRMED`** (doubtful, already behind a switch). Give it a measuring pair on tasks-api
   and the web and CLI families with the most past-cap rulings: wordstats-cli, fullstack-bookmarks, web-todo.
   *Measure:* past-cap rulings left standing (60 in 23 runs), active minutes on tasks-api (175 on ea01f85c), lead
   re-plans after a past-cap ruling. False acceptance must stay 0.
4. **Give QA its own system prompt** (sure for the contradictions, doubtful for the trimming). Always on: drop "unit,
   integration ...", "build code ... end-to-end development" and the layout rule that tests live beside the code from
   the suite writer, and state the acceptance folder once. Behind a switch: drop beginner docs, fixer lessons and
   product-code plugin modules for QA. *Measure:* QA write refusals (3 on C#), "product code" refusals (38 in 18 runs),
   author model minutes and reasoning share.
5. **Per-run command list in the environment contract** (sure fix). Derive it once per run from the pinned stack's
   allowlist, so it stays byte-stable within a run. *Measure:* "not permitted for role" refusals (21 in 8 runs), and
   `prefix_break_system_changed` in the ledger must not rise.
6. **Pass the pack's command as argv in harness-made work orders** (sure fix): `work_orders.py:244` and `building.py:43`,
   or exempt the pack's own command from the shell-operator check. Also check `BUILT_SHARE` against the scaffold's stubs,
   for example by counting a file as built only if it differs from the scaffold's version. *Measure:* lead model calls
   for a fast-delivery first plan (1-5 now, the target is 0) and readiness send-backs.
7. **Reviewer-shaped plugin content** (doubtful, behind a switch). Read-only roles get the plugin's review lines only,
   with no command guide and no fixer lessons. *Measure:* input characters per review call (advisor framework 4.6k-9.7k),
   QA-lead and reviewer finding precision, no hidden score loss.
8. **A smaller lead request on a re-plan** (doubtful, behind a switch). Send the sprint's own files whole and the rest as
   the digest, instead of 134k characters of project memory. *Measure:* lead cut-offs (14 of 547), lead model minutes per
   plan (tasks-api: 19 for 5), plan readiness rate.
9. **Hide the harness's `tmp-inline-*` copies from the workspace listing**, and say in the scratch-file rule that the
   harness removes them (sure fix). *Measure:* `delete_artifact` calls on harness files (39 lines in 2 runs, should
   be 0).
10. **Wording and one scan test** (sure fix, copy change). Reword the 46 banned-word hits and `technical_lead.py:737`,
    replace the task-dashboard example, and fix `requests.py:384`. Add one suite test that renders every stage's system
    prompt and bans the words. *Measure:* banned-word hits in rendered prompts (46, should be 0).

## Not verified

- Why the lead was called for the first plan in fast delivery. The `BUILT_SHARE` cause comes from the code and the C#
  file plan. I read no worker log, because the audit was limited to `docker exec` cat and ls.
- The Java run with 54 author model minutes is not in this sample. Java run 9c875db7 spent 5.
- Whether the 191 dispute rulings were right. There are no labels, and hidden scores are only a proxy.
- Which harness version raised the 204 finding on b668a924. The current code does not flag that test.
- Prompt sizes are the largest seen per family in six runs. Other stacks and model-guidance tiers change them.
