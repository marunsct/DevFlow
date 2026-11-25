# Deep review, evidence integrity: how a fact produced in a run reaches the stage that needs it

Date: 2026-11-25 (JST). Read-only review: nothing in `src/`, `tests/`, the configuration or the documents was changed,
nothing was committed, deployed, started or stopped. Times are JST.

## What was checked, and how

Every hop was checked on the request the model actually received, not on counts.

- **Transcripts of 17 runs** of 11-22 to 11-25 (the two then live were copied at 23:33 on 11-25, before they ended;
  "live" below means those two): the two live runs (`run-32362f3b` medium, thorough, FastAPI + React;
  `run-2f653f55` fullstack-bookmarks, fast), three other medium runs (`run-8f0be29e`, `run-bc3cbd00`, `run-c53e7bd2`)
  and twelve small ones (Go, Rust, Java, C#, PHP, JavaScript, Python, a CLI and a library). I took the opening request
  of every stage (a fixer's, a test round's, a review's, the lead's re-plan, a builder sent back) and read what it held.
- **Saved measurements of 108 workspaces** of the last six days (`.harness/acceptance-result.json`,
  `unit-result.json`, Playwright's `error-context.md`): 263 failed tests in 19 runs.
- **The harness's own extractors run in the worker on those real outputs** (`what_the_server_logged`,
  `the_server_hid_the_cause`, `where_errors_become_5xx`, `what_it_said`, `page_it_failed_on`, `failure_pages`,
  `_pyright_diagnostics`, `ci.the_distinct_causes`, `fresh_evidence.with_the_tests_now`). Each number below is what the
  deployed code returned on a real record.

Not re-reported: LF.1318-1407 and FX.1-FX.11. Where a finding below changes what an FX item must do, it says so.

## Summary

| # | Finding | Runs | Cost seen |
|---|---|---|---|
| 1 | A type checker's opinion is written into a defect as "this fails when the code runs" when the harness's own tests ran that code and passed | 2 of 4 medium runs | 43 fixer minutes on 3 false defects, 2 right fixes reverted, the sprint planned again twice |
| 2 | The server-log extractor keeps access-log lines as "errors", stops at the first 12 lines, and misses most stacks' exception lines; an access line also switches off the "handler hid the cause" hint | 2 medium runs, 10 fixers; PHP, Java, Rust lines dropped | the exception was in the output and not in 7 briefs; the hint FX.1 rebuilds was silenced in the live run |
| 3 | The fallback "what the last failing command actually printed" shows a fixer an unrelated command as the machine's word to believe | 13 of 17 runs, 53 briefs | 45 of 49 name none of the defect's files |
| 4 | In thorough delivery a measured unit failure reaches every stage only as a count; the lead re-plans a failed sprint from test names alone, and its guess becomes the task and the defect's title | the live medium run; counts in 4 of 4 medium reviews | 19 minutes of re-plan, a false root cause passed on as fact |
| 5 | A refreshed defect loses the label of its page snapshot, so the page at load reads as the page at failure | the live fullstack run, 15 briefs | "No bookmarks yet" shown under a test whose page listed the bookmark |
| 6 | A failed page test's line keeps the matcher and drops what it looked for | 6 of 19 runs, 45 of 263 lines | every page failure reads the same |
| 7 | The page a test failed on is cut at 900 characters and kept for 8 tests | 12 of 27 pages cut; 2 with the sought field past the cut; 23 page failures with no page | a field on the page reads as absent |
| 8 | A reviewer's opinion is filed under "Actual behavior" of "a test failure" | the live medium run, 2 fixers | 21 minutes of the first fixer on a claim nothing measured, then a second fixer |
| 9 | Smaller: a 4xx answer's body is never captured; three more first-line reads of a test message; a stale sentence in a release document | | |

---

## 1. A type checker's opinion is quoted as "this fails when the code runs"

**Evidence.** `run-bc3cbd00` (medium, FastAPI in `task-management-dashboard/backend/`), test round 0, 11-25 06:59. The
language service raised `backend/app/routers/auth.py line 10: "settings" is unknown import symbol - this fails when the
code runs`, then the same for `"Task"` (`routers/tasks.py` line 8) and `"Category"` (`services/task_service.py` line 10).
At the same moment the harness's own measurement read "acceptance tests: 15 of 15 pass" and the backend's 18 unit tests
passed: the code ran.

Six fixers were sent (07:08-07:16, 07:37-07:44, 08:38-08:44, 08:44-08:48, 08:49-09:00, 09:00-09:07), 43 minutes. Their
own words: "This is a **false positive** from the language service (Pyright), not an actual runtime failure. The code
is correct." Two of them wrote the regression test the brief demanded; both were reverted with "it wrote code the
language service is sure fails when it runs" (the test imports the same names). Both rounds ended "exhausted
remediation attempts; the sprint is planned again" (07:45 and 09:08). The run's review
(`reports/product-reviews/2026-11-25-medium-3.md`) does not mention it.

Reproduced in the worker on that workspace: `_pyright_diagnostics(<project>)` returns 14 "certain" findings, all
`"X" is unknown import symbol`; with the root at `backend/`, where the service and its tests run, it returns none in
the product (one in a scratch file).

A second form, `run-c53e7bd2` (medium), code review at 11-24 23:47: `tests/test_models.py line 56: Cannot assign to
attribute "priority" for class "Task" ... "Literal['high']" is not assignable to "Column[str]" - this fails when the
code runs`. Assigning a string to a mapped column does not fail when it runs. Raised as a defect and left open.

**What the stage had and needed.** It had a static finding stated as a certainty. It needed either a finding that is
true, or the harness's own contrary measurement beside it.

**Root cause.**
- `src/app/analysis/language_service.py:479-513` (`_pyright_diagnostics`): `"executionEnvironments": [{"root": here}]`
  takes the project directory as the one import root. A service kept in a subfolder with its own import root gets
  every absolute import underlined. `_a_local_import` (line ~470) filters only `Import "x" could not be resolved`, not
  `unknown import symbol`.
- `language_service.py:452`: `_PYTHON_RULES` holds `reportAttributeAccessIssue` whole. That rule also carries
  "Cannot assign to attribute ... is not assignable", a type opinion, not a runtime failure.
- `src/app/graph/engineering.py:186, 367, 492`: every kept finding gets `FAILS_WHEN_IT_RUNS`, and the fix guard reverts
  on the same certainty. Nothing compares the claim with a measurement that loaded the file.

**General?** Any Python product whose import root is not the project directory (a `backend/` folder, a `src/` layout
with an installed package), and any code assigning to typed attributes. 2 of the 4 medium runs; none of the small ones,
whose products sit at the project root.

**Fix (always on, a bug).**
1. Take the import roots from what the harness already knows: the directory the pack's unit command and start command
   run in, and every directory holding the manifest the runner reads (`.harness/stack-pack.json`, the contract). One
   execution environment per root. This is the Python table's detail in `language_service.py`, where it lives today.
2. Keep from `reportAttributeAccessIssue` only messages that say a name or attribute does not exist; drop "is not
   assignable".
3. Stack-agnostic guard, for every language service: a finding that says an import or a name fails is not raised, and
   never reverts a fix, when the latest unit or acceptance measurement passed with tests that load that file. Record it
   as "underlined, contradicted by the measurement" in the check findings so an audit sees it.

**Test from a real output.** Copy the tree shape of that workspace (`backend/app/{config,models}.py`,
`backend/app/routers/auth.py`, `acceptance/conftest.py`, the real import lines) into a fixture and assert no finding
for `routers/auth.py`; today it returns the three real messages. For the second form, the real `test_models.py`
line 56 and its model: no finding.

---

## 2. The server log a failing criterion's defect carries

One function decides what "the product's server logged": `src/app/acceptance/suite.py:1322-1352`
(`what_the_server_logged`). I ran it on 41 real suite outputs holding `[WebServer]` lines, from 13 runs.

**2a. Access-log lines are kept as errors, and they use up the room.** `_STATES_AN_ERROR` (line 1324) is
`\b(?:\w*Error|Exception|Traceback|panic|FATAL)\b`. Uvicorn's `"POST /api/register HTTP/1.1" 500 Internal Server
Error` matches `\w*Error`. The loop stops at 12 kept lines (`MOST_SERVER_LINES`, line 1327).

`run-8f0be29e` (medium), three outputs (11-23 09:12 test round 2, 12:31 test round 0, 14:58 `defect_fix_1_10`): 157-161
server lines each, two tracebacks each, ending `sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such
table: users`. Kept: 12 access lines, 0 of the 2 error lines. The briefs of `defect_fix_1_11`, `1_12`, `1_13`, `2_11`,
`2_12`, `2_13`, `2_14` (from 15:02) show "What the product's server logged while the suite ran:" followed by access
lines only. The cause was in the output four minutes earlier.

**2b. An access line switches off the hint for a hidden cause.** `the_server_hid_the_cause`
(`src/app/graph/acceptance_nodes.py:2253-2267`) returns nothing when `logged` is not empty. In the live medium run
`run-32362f3b` the saved log is five `500 Internal Server Error` access lines. Run in the worker on that workspace:

- with the real log: `''`;
- with an empty log: "The service answered a 5xx status and logged nothing while it did: its error handler hides the
  cause. First make that handler write the error it caught - message and stack - to the process's standard error ...".

That is the instruction FX.1 is being built to give. It exists, and it was silenced for `defect_fix_1_2` (22:00),
`2_2` and `2_5` (22:29), 77 fixer minutes with no change kept. `affected_files` is filled only when the hint fires
(line ~2551), which is one reason those briefs read "Affected files: (none identified)".

**2c. The lines that answer 5xx are not found when the status is a named constant.** `_A_5XX_ANSWER` (line 2271) is
`(?<![\w.])5\d\d(?![\w.])`. The product's four handlers answer `status.HTTP_500_INTERNAL_SERVER_ERROR` inside
`except Exception:` (`routes/auth.py` lines 118-121, 182-185, 207-210, 263-266). `where_errors_become_5xx` returned
`[]` on that workspace. Named constants are the idiom in most frameworks.

**2d. Frames are recognised in one language's form.** `_A_FRAME` (line 1325) is `^\s*at\s`. Python's
`File "...", line N, in f` is neither a frame nor an error: 0 of 22-50 Python frames kept in every sample. A Python
traceback is kept as `Traceback (most recent call last):` and its last line, with no file of the product. Java's
library frames are all kept (only `node_modules` and `node:internal` are left out).

**2e. Most stacks' exception lines do not match.** `Exception` has no `\w*` before it and `error` is matched only
with a capital E. Real lines the function dropped:

| Run, stage, time | Line dropped |
|---|---|
| `run-f4bab632` (PHP), suite authoring, 11-25 09:58 | `PHP Fatal error:  Uncaught Slim\Exception\HttpNotFoundException: Not found. in .../RoutingMiddleware.php:76` (17 times) |
| `run-cc265cee` (Java), builder, 11-25 01:37 | `org.sqlite.SQLiteException: [SQLITE_ERROR] SQL error or missing database (no such table: notes)`; `Caused by: ...DialectResolver$NoDialectException: Cannot determine a dialect ...; Please provide a Dialect`; `ERROR ... Servlet.service() ... threw exception` |
| `run-c4fd577a` (Rust), tester, 11-24 23:47 | `error[E0252]`, `error[E0599]`, `error[E0505]`, `error: could not compile` (kept instead: source lines that happen to contain `rusqlite::Error`) |

Checked against the regex directly: `java.lang.NullPointerException: ...`, `System.InvalidOperationException: ...`,
`thread 'main' panicked at src/main.rs:10:5`, `level=error msg=...` and `fail: Microsoft.AspNetCore...` all fail to
match.

**2f. First 1,500 characters.** On the Java sample three Spring lines fill the 1,500 characters (line 1352); the root
cause, the last `Caused by:`, is cut. A saved Java result (`run-bf96efa0`) holds the same `WARN ... SQL Error: 0,
SQLState: null` six times, because the timestamp defeats the duplicate check.

**There are two extractors.** `src/app/acceptance/what_went_wrong.py` (`what_the_server_printed`, `the_errors_stated`)
on the same Java and Rust samples returned the root `Caused by:` line and the four compiler errors. A product that
does not start is read by the good one; a failing criterion's server log by the poor one.

**Fix (always on).** One reader for both paths: `what_went_wrong`'s. In it: an access-log line (a request line with a
status) is never an error line; the last error of each distinct trace is kept before any frame, a trace's frames in the
product's own files after it (any language's frame form, from the per-language tables); duplicates compared with
digits and timestamps removed; the cap applied to the tail of a chain, not its head. `the_server_hid_the_cause` asks
"did the log state a cause", not "is the log empty". `_A_5XX_ANSWER` also takes a constant whose name holds
`5\d\d` or `INTERNAL_SERVER_ERROR` (other names from the per-language tables).

**For FX.1.** Its condition is "the server's log states no error for that request". Built on `what_the_server_logged`
as it is, that condition is false whenever the access log prints "Internal Server Error", which is the case it is for.

**Tests from real outputs.** The three `run-8f0be29e` outputs: the result holds `no such table: users` and no line
with `HTTP/1.1"`. The `run-32362f3b` saved log with a real `Received: 500` message: the hint is returned, and
`where_errors_become_5xx` on the real `routes/auth.py` returns its four lines. The PHP, Java and Rust lines above: each
is kept.

---

## 3. "What the last failing command actually printed" is usually another defect's, and sometimes no failure at all

**Evidence.** A fixer whose defect is neither a criterion nor an opening "The unit tests fail" falls through to
`last_failing_command`. 53 briefs in 13 of 17 runs carry it; 5 in the live fullstack run, 1 in the live medium run. Of
the 49 I could parse, 4 mention any of the defect's affected files. By defect: 25 written by a model (test round or
review), 10 language service, 7 suite, 5 unit tests, 2 page check. By what was shown:

| Shown as "the machine's own output" | Briefs | Example (run, fixer, time) |
|---|---|---|
| an acceptance run, whole or of another test | 20 | `run-2f653f55` `defect_fix_1_0`, 19:41: the defect is `tests/bookmarks.test.js line 19: Cannot find name 'before'`; shown `npm run test:acceptance`, 22 acceptance test titles and the server's stack for a test that sends bad JSON on purpose |
| a unit run of something else | 14 | `run-bc3cbd00`, 09:31: "assign_task does not validate the assignee"; shown forty `PASSED` lines |
| a stage's own inline script | 10 | `run-bc3cbd00` `defect_fix_2_1`, 09:00: shown `FileNotFoundError: ... pyrightconfig.json` from an earlier fixer's `python -c`; `run-031094d4`, 11-24 15:00: "the product does not start" shown `TypeError: Socket.pair is not a function` from a `node -e` |
| a listing, an install, a missing tool | 4 | `run-bc3cbd00` `defect_fix_2_0`, 07:28: a duplicate-token defect shown `npx playwright install` failing on a read-only folder, run by stack setup 3 h 38 min earlier; `defect_fix_2_3`: `docker: Error response from daemon ... exec: "pytest": executable file not found` |
| a harness refusal | 1 | `run-c4fd577a` `defect_fix_2_1`, 11-24 23:59: `cargo test -p notes_api --lib` with "Not running this again. It has already passed 3 time(s)" |

Each is followed by: "this is the machine's own output. Where the two disagree, believe this".

**Root cause.** `src/app/observability/transcript.py:190-244`.
- It reads the whole transcript (`read_transcript`, not `read_live`): any stage, any age, rewound branches included.
- `_exit_code` (281-292) takes `"returncode": -1`, which `run_validation` returns with its withheld notice, as a
  failure. The command had passed three times.
- `_runs_a_probe` (254-261) looks for a scratch file name in the first four words; `python -c` and `node -e` carry
  none (the sandbox writes `tmp-inline-*` itself), and `ls` or an install is not a test.
- Nothing asks whether the output concerns the defect.
- The chain before it (`src/app/graph/nodes/fixes.py:67-70`, `385-388`) misses: a unit failure merged under a
  language-service finding (the description no longer opens "The unit tests fail", so
  `suite.py::what_the_unit_tests_printed` returns nothing); every model-written defect; page-check and review
  defects.

**Fix (always on).**
1. The fallback is shown only when the command is a test, build or start command of the contract, ran on the live
   branch after the last kept write, exited above zero, and its output names one of the defect's files or tests.
   Otherwise the section is left out.
2. A merged defect keeps each source's evidence: a unit failure merged in still gets its own failing tests from the
   unit report.
3. A defect with a file and line (language service, static checks) gets that file's lines around the finding.
4. The sentence "believe this" stays only on evidence selected for the defect.

FX.7 gives a criterion its own first failing test; these are the defects it does not reach.

**Tests from real outputs.** The five `tool_call`/`tool_result` pairs above, replayed through `last_failing_command`
with the real defect: None for each. The `run-2f653f55` merged defect with its real JUnit unit report: the brief holds
`ReferenceError: before is not defined` and no acceptance title.

---

## 4. Thorough delivery: a measured unit failure travels as a count, and the lead re-plans without the failures

All from the live medium run `run-32362f3b`, 11-25.

**4a. The harness measured it and told no stage.** `.harness/unit-result.json` holds the unit run the harness made
itself: 9 of 32 failing, 17,883 characters of output. `ci.the_distinct_causes` on it gives, with nothing a model has
to do: "8 failing ... `sqlalchemy.exc.InvalidRequestError: One or more mappers failed to initialize`" and "1 failing
... `AmbiguousForeignKeysError: ... Specify the 'foreign_keys' argument`". Earlier in the run the same tests failed with
`'SQLiteTypeCompiler' object has no attribute 'visit_ARRAY'`, printed in nine command results from 19:49 to 22:22,
one of them the builder's own (20:45).

Across the opening requests of all 19 stages of that sprint (two code reviews, two test rounds, the lead, four
builders, eight fixers): `visit_ARRAY` appears 0 times. Eleven of them carry the line "Unit tests: 23 of 32 pass". Only
two fixers (`defect_fix_2_3`, `2_4`, 23:00) were shown the mapper error. The fixers of AC-1 (registration answers 500)
never saw that the unit test of the same function fails with a named exception, most likely the cause of that 500.

The harness raises its own "The unit tests fail" defect, with the grouped causes, only when it runs the round itself:
fast delivery, or thorough behind `MEASURED_ROUND_WHEN_RED`, which is off
(`src/app/graph/nodes/triage.py:203-232`). In thorough delivery the report is left to the tester's prose, and LF.1394
now tells the tester the unit failures are its to report. FX.8 then tries to re-attach the error by matching the
prose's words against command results.

**4b. The lead plans a failed sprint again from test names.** Re-plan request at 20:15: "Find the one cause behind
these failures first - the step they all stop at", then per criterion "currently FAILED" and up to four test names.
Occurrences of `Received`, `500`, `Expected: 201` or any server line in the request: 0. The lead has `ls`,
`read_file`, `glob`, `grep`; it wrote three times that it would "run the acceptance tests to see the actual failures"
and could not. A test round's script had printed the real traceback at 20:13.

In 19 minutes (20:15-20:34, one reply of 83,914 characters of reasoning, three plans) it settled on: "database.py line
91 calls synchronous command.upgrade() on an async engine URL ... causing a crash at module import time ... all /api
endpoints are unreachable". The same request lists AC-15 "service starts with migrations applied" as PASSED and 8 of 21
tests passing: the product starts.

**4c. The guess becomes a fact downstream.** The builder's request (20:34) opens its delegated task with that sentence.
The code-review defect is titled "Code review (Fix the root cause of all auth endpoint failures: database.py line
91...)", shown to `defect_fix_1_0` (21:38) and `2_0` (23:11) and written into two commit titles. This is where the
migration theory that the next fixers adopted began, before the fixer's claim the research report names.

**4d. Reviews get counts.** "What CI measured after the batch" in the code review of 4 of 4 medium runs: "Unit tests:
23 of 32 pass; acceptance tests: 8 of 21 pass" (also 0/0 and 5/97; 37/53 and 18/18). Both reviews of the live run then
explained failures they were not shown.

**Root cause.** `src/app/graph/foundation.py:139-146` (`replan_guidance`) and
`src/app/graph/acceptance_nodes.py:1688-1716` (`criteria_brief`: status and `tests[:4]` from the coverage list, which
are the first four tests, not the failing ones). `src/app/agents/where_things_stand.py:149` and the code review's CI
section print `ci`'s summary line. `later_work_needs` computes the step the failures stop at (`failure_step`) and
does not hand it over.

**Fix (always on; evidence that exists and is not passed on).**
1. One block, "What the last measurement found failing", built once from the saved acceptance result and the unit
   report: per failing criterion its failing tests with `what_it_said`, the server's stated error, and the unit
   report's distinct causes. Used by the lead's re-plan, a builder sent back, the code review and the test round, in
   place of the count. About 1,500 characters.
2. In every delivery mode the harness raises the unit-test defect itself from the report (`_the_unit_tests_fail` with
   `ci.the_distinct_causes`). The tester reports only what the reports do not hold. This is surer than FX.8's
   word matching, which stays useful for errors outside the reports.
3. A criterion's fixer whose tests received a 5xx is also shown the unit report's distinct causes when unit tests
   fail.
4. A re-plan's stated cause is a hypothesis: the delegated task says "the lead's reading, not measured", and a defect's
   title is the finding, not the work order's title.

**Tests from real outputs.** The saved `acceptance-result.json` and `unit-result.json` of that workspace: the re-plan
request holds `Received: 500` and `AmbiguousForeignKeysError`; the code review's CI section names the failing tests.
A thorough test round over that unit result raises one unit-test defect whose text holds the exception.

---

## 5. A refreshed defect loses the label of its page snapshot

**Evidence.** `run-2f653f55`, `defect_fix_1_8`, 20:56. "Actual behavior" reads:

```
[AC-3] Delete a bookmark via the page: ui.spec.js:224:1 › [AC-3] Delete a bookmark via the page ───
- main:
  ...
  - text: No bookmarks yet — add one above.
```

Further down, the same test's fresh output: "What the page showed when this failed: ... link "AC3 Delete Me" ...
button "Delete bookmark AC3 Delete Me"". The first tree is the page at load, before any test; its label is gone, so
it reads as what the test met. The real fault was that the item is not a `listitem`. The same in `defect_fix_2_3`
(23:13). 15 of that run's criterion briefs hold an unlabelled tree; in the 16 briefs of earlier runs the label is
there.

**Root cause.** `src/app/graph/acceptance_nodes.py:2402, 2593`: `WHAT_THE_PRODUCT_SHOWS` opens with a space, not a
line break, so it sits at the end of the defect's first line. `src/app/graph/fresh_evidence.py:153-162`
(`with_the_tests_now`, LF.1270) replaces the first line whole. Confirmed in the worker with the real constant: the
label is dropped. Where a server log stands between (the medium run) it survives.

**Fix (always on).** The label starts its own line. `with_the_tests_now` replaces only the failed-tests sentence. When
the latest measurement holds the page the first failing test met, that goes in "Actual behavior" and the page at load
after it, each labelled.

**Test.** The real stored text and saved result of that defect: the refreshed text still holds "before any test
touches it".

---

## 6. A failed page test's line says the matcher, not what it looked for

**Evidence.** `what_it_said` (LF.1393) on the 263 failed tests: for value matchers it is right
("...toBe(expected); Expected: 201; Received: 500"). For 45 lines in 6 of 19 runs it returns only
`Error: expect(locator).toBeVisible() failed` (32), `TimeoutError: locator.fill: Timeout 3000ms exceeded.` (8) or
`toHaveCount` / `not.toBeVisible` (5). The locator, `Expected: visible`, `Error: element(s) not found` and the
`waiting for getByLabel('Email')` line follow under "Locator:" or "Call log:". Real case: `run-2f653f55`
`defect_fix_2_3`, 23:13, opens "[AC-15] ...: Error: expect(locator).toBeVisible() failed".

**Root cause.** `src/app/acceptance/failure_said.py:26, 41-47`: after the error line only lines starting `Expected`
or `Received` are taken; the first other line (`Locator:`) ends the read.

Three more places still read a test message by its first line, which for this runner is its title:
`acceptance_nodes.py:2624` (`due_criteria_failing`, for the milestone review), `graph/last_try_on_deferred.py:82`,
`graph/rewritten_tests.py:116`. I found none of the three in a request of these runs; they are the bug LF.1393 fixed,
left in place.

**Fix (always on).** `what_it_said` also takes `Locator:`, `Timeout:`, a second `Error:` line, and the first
`waiting for` line of a call log (runner wording belongs in the pack's table). The three sites call `what_it_said`.

**Test.** The 45 real messages: each result holds the locator text.

---

## 7. The page a test failed on: 900 characters, 8 tests

**Evidence.** Of 27 failing tests that carry a page, 12 were cut at 900 characters (`FAILURE_PAGE_CHARS`). 15 of 44
real `error-context.md` trees are longer (largest 5,015). In `run-418ca472` (medium) two cut pages hold the sought
field past the cut: "[AC-6] user login with valid credentials succeeds" waits for `getByLabel('Email')`; "Email" is at
character 990 of 1,303, after the navigation. The brief then shows a page without the field the test could not fill.
23 failing page tests carry no page at all (`MOST_FAILURE_PAGES = 8`, or no file matched the title).

**Root cause.** `src/app/acceptance/suite.py:1660-1661, 1697-1707`: a head cut, the same for every failure.

**Fix (always on).** Keep the lines around the nearest match to what the locator sought (the pack's `_a_near_miss`
already finds it) and the landmarks above them, within the same room; say "N more lines" at each cut. Give the room to
the first failing test of each criterion before a ninth test of one.

**Test.** The two real trees and messages: the kept part holds `textbox "Email"`.

---

## 8. A reviewer's opinion under "Actual behavior" of "a test failure"

**Evidence.** `run-32362f3b`, `defect_fix_1_0` (21:38) and `2_0` (23:11). The brief opens "A test failure has been
assigned to you to fix"; "Actual behavior" is the reviewer's text, word for word the description: "FastAPI processes
middleware in reverse order of registration. Since the router is mounted before the error handler, any unhandled
exceptions from route handlers won't be caught". Nothing measured it, and a middleware wraps the routes whichever is
registered first. "Reproduction steps": "Read the files the work order names." The first took 21 minutes, changed
`main.py` and "moved forward" on another test.

**Root cause.** A review finding is mapped onto the test-defect shape, its text copied into both fields
(`src/app/agents/code_reviewer.py`, where findings become `ReportedDefect`). The request's opening sentence is the
same for every source (`src/app/agents/specialists.py`, `build_defect_fix_request`).

**Fix (always on).** By source: a review's finding opens "A reviewer's finding has been assigned to you: check it
against the code before changing anything", its text under "What the reviewer says (not measured)", and "Actual
behavior" holds only what the harness measured, or says nothing was. A fixer that finds it untrue answers so and the
defect closes as disputed.

**Test.** The real finding through the brief builder: the reviewer's sentence is not under "Actual behavior".

---

## 9. Smaller

- **A 4xx answer's body is never captured.** `run-2f653f55` `defect_fix_1_2`, 20:04: "4 acceptance tests ... stop at
  the request `POST /api/bookmarks`, answered 400". The brief holds four identical "Expected: 201, Received: 400" and
  not the body, where the product says why it refused. The harness can send that request again, as its probes do. This
  belongs with FX.7's fresh evidence.
- **"Earlier attempts"** still prints a fixer's own claim after "changed no file" (`src/app/agents/ledger.py:179-197`,
  `did` taken from the fixer's first decision). The research report lists it under "what not to do"; none of FX.1-FX.11
  owns it.
- **A stale sentence in a release document.** `run-cc265cee`, `docs/reviews/release-evidence.md`: line 81 says the
  suite run again at release failed AC-15; line 95 quotes an escalation as "every locked test passes at release". I did
  not trace the cause.

---

## Checked and fine

- **Paths printed by the sandbox.** Command output prints `/workspace/...` in 493 results. 57 calls used such a path;
  46 worked and the 11 that failed did so for other reasons (a refused command, a missing scratch file).
- **Colour codes.** None in any of the 108 saved results.
- **Statuses in a failed test's line** (LF.1393): right for value matchers, and they reach the test round's opening
  request in the live medium run.
- **A criterion's fixer is shown its own tests**: in all 39 such briefs "What its failing tests printed" holds that
  criterion's tests from the latest measurement, whole.
- **A product that does not start**: on the real Go, Rust and Java samples `what_went_wrong` kept the panic, the
  compiler errors and the root `Caused by:`.
- **The release document** of the Java run names its failing criterion and its four failing unit tests truthfully.
- **The transcript's defect records** cut the description at 300 characters and carry no detail. That is the audit's
  view only; no stage I traced reads it back.

## Not covered

- Sprint escalations: the 14 escalation requests in these runs are all the design review's; none carried run evidence
  to judge.
- The suite's dispute and repair paths, the security review's inputs, hosted-model runs.
- Whether the head-and-tail cut of long command output loses the error: the cut keeps both ends and a reference; I
  did not measure it.
- The fixes proposed are not built or tested. The numbers are of the records named; the fix-time gains are not
  estimated.

## Where the captured outputs are

Fixtures can be cut from the records named above by run, stage and time. The 41 real server outputs I extracted are in
`/tmp/claude-1000/-home-arun-Desktop-langchain/d4298d72-a977-42bb-8a37-f5c3120002bc/scratchpad/ev/ws_samples.json`
(a session folder, not kept); the failing-test messages are in each workspace's `.harness/acceptance-result.json`.
