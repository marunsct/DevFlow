# Deep review: parsers and extractors against real formats

Date: 2026-11-25 (finished 2026-11-26). Reviewer scope: every place in `src/app` that reads output it does not
control with a regex or string match. Read-only: nothing in `src/`, `tests/`, config or docs was changed.

## Method

Each parser was run on real captured output, not on its tests' fixtures.

- **Transcripts:** 31 runs, 2026-11-22 to 11-25, covering Node, Python (FastAPI, Flask, CLI, library), Go, Rust,
  Java, C#, PHP and Ruby. 9,892 model replies and about 12,000 tool results.
- **Workspaces:** the 260 most recent, 16 packs. 250 `unit-result.json`, 253 `acceptance-result.json`, 756 JUnit
  reports, and the product source files themselves.
- **How:** the harness's own functions were imported and called on that data. Where a parser returned nothing, the
  input was opened and read.

All times are JST.

## Summary

| # | Finding | Decision it changes | Seen in |
|---|---------|---------------------|---------|
| 1 | A thrown error is never read from a real Playwright failure: the message opens with the runner's header line | One-cause grouping, fix kept or reverted, deferral of a sprint | 412 of 466 real failed tests |
| 2 | The localiser's map and the memory's map hold no C# or Java product file, and few PHP ones | Which files a fixer is pointed at | 42/42 C#, 91/91 Java, 39/55 PHP product files |
| 3 | The server log kept for a fix brief is 12 access-log lines on a FastAPI product; the traceback is dropped | What the fixer is shown for a 500 | every uvicorn product |
| 4 | Test totals are wrong for nextest failures, pytest errors, two runners in one command, and long Playwright output | "N of M passed", false "the suite has shrunk" warnings | 4 shapes, 6 runs |
| 5 | "Distinct causes" groups unlike failures under one generic assertion line | The unit-test defect's text | 7 of 34 groups (C#, Rust, Go) |
| 6 | Small gaps: `toContain` status checks, "Error invoking tool" not counted as a refusal | Minor | a few each |

Findings 1 to 4 each have a test that passes on a hand-made input the real tool does not produce (section
"Fixtures that do not match the real format").

---

## 1. A thrown error is never read from a real Playwright failure

**Impact: high.** Three decisions read it: one defect for one cause, whether a fix moved forward, and whether a
sprint may be deferred.

**What the real data is.** A failed test's message, as the suite's result keeps it, opens with Playwright's own
header line, then a blank line, then the error:

```
tasks.spec.js:16:1 › [AC-2][AC-9] create a task returns 201 with the created object ──────────────

    Error: Login rate limited

       at test-utils.js:75
```

412 of the 466 failed tests in the 253 saved acceptance results open this way.

**What the code does.** Three readers take "the first non-empty line" as the error:

- `src/app/acceptance/first_failing_step.py:96-103` (`what_it_threw`) returns the header line. In all 79 real
  cases where a test threw an error on purpose, `Failure.thrown` is the header, not the error.
- `src/app/graph/foundation.py:55` (`failure_step`) returns the header for 226 of 466 failures. The header is
  unique per test, so two tests never "stop at the same step".
- `src/app/graph/judged_fixes.py:163-170` (`_nearness`) is given the header as `thrown`. For 133 of 357 real
  assertion failures it answers "cannot be read" where it should say "an assertion on what came back". For 88 of
  103 real thrown errors it also answers "cannot be read". Four assertion failures read as "threw an error" only
  because the test's title contains the word "error" or "refused".

**Evidence.** run-8f0be29e (Medium, FastAPI+React), saved acceptance result of 2026-11-23. Its failures read as:
429 for 42 tests, 409 for 10, 404 for 13, and **no answer for 27**. Of those 27, 24 threw `Login rate limited`
or `Login failed with status 401` at `test-utils.js:75` and `:83`. This is the run the module's own docstring
cites ("18 threw Login rate limited ... 8 threw Login failed with status 401"). The frame-sharing fallback did
not recover them on the saved result.

**Consequences.**
- `one_refusal_for_all` and `first_failing_step.clusters` (`acceptance_nodes.py:2446-2450`) under-count the tests
  behind one cause, so the "one in ten" share is missed and each criterion gets its own defect and fixer.
- `judged_fixes._compared` falls back to line numbers only. A fix that moved a test from a thrown error to an
  assertion is not seen as progress (LF.1272) unless the failing line also moved.
- `foundation.later_work_needs` cannot find later sprints' tests failing "at the same step", so that reason for
  not deferring a foundation sprint never fires for thrown errors.

**General:** yes. Every pack whose acceptance runner is Playwright, which is all but the Python CLI and library
packs.

**Fix (always on).** One shared function, "the message without the runner's header", used by all three readers:
drop a first line that matches `<file>:<line>:<col> › ` (and pytest's `____ name ____` rule line), then read the
first line with text. Better still, strip the header once where the message is saved (`junit._text_of` or
`suite._judged`), so no reader sees it.

**Test from real output.** Take three failed-test messages verbatim from run-8f0be29e's
`.harness/acceptance-result.json` (one `Login rate limited`, one `Login failed with status 401`, one
`Expected: 201 / Received: 429`). Assert: `what_it_threw` returns `Error: Login rate limited`; `read()` answers
429, 401, 429; `failure_step` is equal for the two rate-limited tests; `_nearness` is 3 for the assertion.

---

## 2. The localiser's map holds no C# or Java product file

**Impact: high for those stacks, and FX.2 ("localise before the fixer") is being built on this map.**

**What the code does.** `src/app/agents/project_memory.py:252-256` (`_DEFINES`) accepts a definition line only
when it begins with `export`, `pub`, `async` or the keyword itself. It does not accept `public`, `private`,
`protected`, `static`, `final`, `abstract`, `sealed`, `partial` or `internal`. `map_of` (line 322) then drops any
file with no definition found, silently: the file is not even named.

**Measured on real product files** (tests, configs and harness-kept files left out; files of 25+ lines):

| Language | Product files | Absent from the map |
|----------|--------------:|--------------------:|
| C# | 42 | 42 |
| Java | 91 | 91 |
| PHP | 55 | 39 |
| JavaScript | 110 | 12 |
| TypeScript / TSX | 162 | 2 |
| Python, Go, Rust, Ruby | 1,003 (all files) | 5 |

**Evidence: the localiser's actual map** (`graph/localisation.py:49-61`, `_the_map`) on three real runs:

- run-cc265cee (Java, 24 files in memory): 4 lines. The acceptance helper, `service.cjs`, and two test classes.
  `NoteService.java`, `NotesController.java` and `Application.java` are absent.
- run-c46d5d9a (C#, 26 files): 1 line, the harness's own `acceptance/service.cjs`. No product file.
- run-f4bab632 (PHP, 23 files): 12 lines. Classes declared `final class` (`PdoNoteRepository`, `Service`) are
  absent, and no method of any class is listed (`public function ...`).

The JavaScript misses are route files that only register handlers (`router.get('/api/bookmarks', ...)`), for
example run-915a9bcb `src/routes.js`: the file that answers a failing route is the one not in the map.

**Consumers.** `localisation._the_map` (the cheap call that names files before a rewrite, AY.1) and the project
memory's "What those files define" for files it does not hold whole (`project_memory.py:760`).

**Why tests missed it.** `analysis/outline.py` and `project_graph._DEFINES_ELSEWHERE` already read these
languages correctly (0 C# and 0 Java files without an outline entry). `map_of` was never moved to them.

**Fix (always on).** `_definitions` reads a file with `outline.entries` (or `_DEFINES` plus
`_DEFINES_ELSEWHERE`), and a file with no definition is still named in the map with its line count. Language
keywords stay in the one shared pattern; nothing stack-specific is added elsewhere.

**Test from real output.** `NoteService.java` from run-cc265cee and `SQLiteRepository.cs` from run-c46d5d9a,
verbatim: `map_of` names both files and their classes; `localisation._the_map` on a copy of that workspace lists
every file under `src/`.

---

## 3. The server log kept for a fix brief is access-log lines; the traceback is dropped

**Impact: high on Python services.** The plan already lists "a 500's server traceback (not the access log) fed
into the fix brief" as a leftover of LF.1401. This finding gives its root cause and corrects one statement: the
fixers research (2026-11-25, section 1.3a) says the harness "reads the server's log correctly". It does not when
a traceback is there.

**What the code does.** `src/app/acceptance/suite.py:1322-1355` (`what_the_server_logged`):

- Line 1324, `_STATES_AN_ERROR`, matches `\w*Error`. uvicorn's access line
  `INFO: 127.0.0.1:41792 - "POST /api/register HTTP/1.1" 500 Internal Server Error` matches it.
- Each access line has a different client port, so the "already kept" check never removes one.
- Line 1352 stops at 12 lines. The first 12 failing requests fill it.
- Line 1325, `_A_FRAME`, knows only JavaScript frames (`at ...`). Python's `File "...", line N, in f` lines are
  never kept.

**Evidence.** run-8f0be29e, test round 2, 2026-11-23 09:12. The suite's output held 159 server lines, among them
`Traceback (most recent call last):` and `sqlite3.OperationalError: no such table: users` many times. Kept: 12
lines, all 12 of the form `"POST /api/register HTTP/1.1" 500 Internal Server Error`. The sibling function
`what_went_wrong.what_the_server_printed` on the same text returns
`sqlite3.OperationalError: no such table: users ... (File ".../routers/users.py", line 91, in register)`.

In test round 1 of the same run (08:47) 4 of 6 kept lines were access lines.

**Consumers.** `AcceptanceResult.server_log` (`suite.py:1586`), read by the criterion defect
(`acceptance_nodes.py:2505`) and by `fresh_evidence.py:73`.

**Smaller faults in the same function.**
- Node: frames in `node_modules` are dropped, but `at JSON.parse (<anonymous>)`, `node:async_hooks` and
  `node:events` frames are kept (run-2f653f55, 2026-11-25 19:09). Only `node:internal` is filtered.
- PHP: the same fatal error is kept once per second because its timestamp differs (run-4702bef3).
- Java: nothing is kept from a Spring log in the runs seen, which is right (no error was logged).

**General:** every uvicorn/gunicorn product (three packs), and any server whose access log prints a status
phrase.

**Fix (always on).** `what_the_server_logged` calls `what_went_wrong.what_the_server_printed` (which already
reads tracebacks in each runtime's shape) on the `[WebServer]` lines, and keeps its own stopped-service part. An
access-log line is never an error line: drop lines that carry `HTTP/1.x" <status>`. Compare lines with numbers
and timestamps taken out.

**Test from real output.** The `[WebServer]` lines of run-8f0be29e's test round 2 output, verbatim: the result
contains `no such table: users` and `routers/users.py`, and no line containing `HTTP/1.1"`.

---

## 4. Test totals are wrong in four real shapes

**Impact: medium.** `sandbox._the_counts_a_test_run_reported` (`src/app/tools/sandbox.py:3926-3976`) feeds the
execution ledger. The model is then told "N of M passed", "the same result as before", or
`[WARNING: Semantic Regression Detected. The test suite has shrunk ... DO NOT remove tests]`. The sprint
summary's case counts come from it too. Of 1,062 real test-like command results, the totals were checked by hand
for every distinct summary shape.

**4a. cargo-nextest with a failure reads as "0 of 1".** nextest prints each failing test's captured output, which
contains libtest's own `test result: FAILED. 0 passed; 1 failed`. The `cargo` pattern (line 3825) comes before
`nextest` (line 3831) in the table and wins.
- run-e625936e, 2026-11-23 17:02: `Summary [0.141s] 44 tests run: 29 passed, 15 failed` recorded as
  `{passed: 0, failed: 1, tests: 1}`.
- Same run, 17:06: `42 passed, 2 failed` recorded as 0 of 1. The green run at 17:07 recorded 44 of 44.
- Every red nextest run of the Rust pack is affected.

**4b. pytest errors are not counted.** Line 3821 reads `passed` and `failed` only.
- run-32362f3b (Medium 4), 2026-11-25 20:45: `23 passed, 9 warnings, 9 errors in 4.34s`, exit 1, recorded as
  23 of 23 passed. This is the run whose nine tests errored at setup on `visit_ARRAY`.
- Same run, 19:59: `11 passed, 9 warnings, 1 error` recorded as 11 of 11.
- run-607e8e9a, 2026-11-24 00:45: `7 failed, 80 passed, 19 errors` recorded as 87 tests, 7 failed.
- A change that turns passing tests into setup errors therefore reads as a smaller suite, and the model is
  warned not to delete tests it did not delete.

**4c. Two runners in one command: only the first is counted.** The fullstack packs' `npm test` runs Vitest and
then pytest. `_the_first_runner_s_totals` returns at the first match.
- run-c53e7bd2, test round 0, 2026-11-24 19:20: output held `Tests 10 failed | 10 passed (20)` (Vitest) and
  `33 passed` (pytest). Recorded: 20 tests. The earlier run of the same command had recorded 33 (Vitest then said
  "No test files found"). The model was told: "The test suite has shrunk ... found 33 test(s), but now only found
  20 ... DO NOT remove tests". Nothing had been removed; 20 page tests had been added.
- The TAP path does add a second runner (line 3950). The others do not.

**4d. Long Playwright output loses its "N failed" line.** The totals are read from the output after it is cut
for the model (`sandbox.py:5696-5750`: `_run` returns the cut text; `_truncate`, line 3689, keeps the head and
the tail). Playwright prints `N failed`, then the list of failed tests, then `N passed`. With many failures the
`N failed` line is in the middle that is cut.
- run-8f0be29e, acceptance authors, 2026-11-23 01:02 to 06:11: `Running 97 tests`, 92 or 93 failing, recorded as
  `{passed: 5, failed: 0, tests: 5}`. 27 results in that run. Twice (01:45 and 06:11) one fewer test passed and
  the author was told the suite had shrunk by one test and not to remove tests.
- 127 of 249 Playwright results in the corpus were cut. The fault grows with suite size, so it is a
  medium-and-large-brief fault.

**Fix (always on).**
- Read totals from the whole output before it is cut (pass the uncut text, or the counts, out of `_run`).
- Sum every runner found, not the first, and take each runner's last summary line.
- Put `nextest` before `cargo`. For cargo's own runner, sum all `test result:` lines (one per test binary).
- Count pytest `errors` as failed.
- When the pack's JUnit report is fresh, prefer it over printed totals (`_the_counts_its_report_holds` does this
  only when no total was printed).

**Test from real output.** Four captured outputs, verbatim: the nextest run of 17:02 (44 tests, 15 failed); the
pytest run of 20:45 (23 passed, 9 errors); the `npm test` output of 19:20 (53 tests: 43 passed, 10 failed); the
97-test Playwright output from the journal with the cut applied by the real `_truncate`.

---

## 5. "Distinct causes" groups unlike failures under one generic line

**Impact: medium-low.** `src/app/ci.py:266-271` (`_its_cause`) groups failing unit tests by their first stated
error line. That line is the assertion's generic header in several runners, so different failures share a
"cause". The text goes into the unit-test defect ("It says: ...", `workflow.py:3132`).

Real groups from saved unit runs (34 groups of two or more tests, 7 generic):

- Rust: `18 failing, e.g. ...: assertion 'left == right' failed` (workspace 1e04154a). The values (`left: 405`,
  `right: 404`) are on the next lines and are not in the cause.
- C#: `Assert.Equal() Failure: Values differ` (5 groups). `Expected: BadRequest / Actual: InternalServerError`
  and `Expected: 2 / Actual: 0` are one cause.
- Go (gotestsum): the message is `Failed`, so every Go failure is one cause, `Failed`. The real line
  (`handlers_test.go:619: Content-Type = ""; want "application/json"`) matches no pattern in `_STATES_THE_ERROR`.
- Playwright contract tests in the unit run: `Error: expect(received).toBe(expected)` for every status mismatch.
- PHP: the first line is the test's own name, so no two failures ever group.

pytest, JUnit 5 and RSpec group correctly: their first error line carries the values.

**Fix (always on).** The cause is the first stated error line plus the value lines that follow it (`Expected`,
`Received`, `Actual`, `left`, `right`, `got`, `want`), numbers kept. A message whose first line is a bare
`Failed` or the test's own name is read from its next line with text.

**Test from real output.** The JUnit reports of workspaces 1e04154a (Rust), 092a40cb (C#) and 6d577fad (Go),
verbatim: tests with different values land in different groups.

---

## 6. Smaller gaps

- **A status inside `toContain` is not read.** `expect([400, 422]).toContain(res.status())` prints
  `Expected value: 500 / Received array: [400, 422]`. `first_failing_step.the_wrong_answer` (lines 84-93) reads
  no answer. 6 real tests (Rust run 1e04154a, Medium run 418ca472). Fix: one more pattern for
  `Expected value: <status>` beside `Received array:`.
- **"Error invoking tool ... Field required" is not counted as a refused call.** `settled_answer._REFUSED`
  (line 592) expects `Error:`. 2 real results (run-1d79334d 2026-11-25 09:24, run-b6c5c636). Every other refusal
  shape in 12,000 results is matched. Fix: accept `Error invoking tool`.
- **`dotnet test` with detailed verbosity** prints `Total tests: 1 / Passed: 1`, which no pattern reads. One
  agent command in one run; the pack's own command is read correctly.
- **Data for FX.9 and FX.10 (in flight, not a new finding).** `installed_packages.missing_in` reads 44 of 231
  real "this name is missing" lines, and 41 of the 44 name the product's own module, not a library. Not read:
  Python `'X' object has no attribute 'y'` (the `visit_ARRAY` line, 13 times), Rust `E0599`, `E0433` "could not
  find", single-name `E0432`, Java `cannot find symbol`, C# `CS1061` and `CS0246`, JavaScript `x is not a
  function`. A lookup keyed on this reader will stay silent on those stacks.
- **The memory numbers a held file with a tab gutter** (`review_files.py:86`, `{number:>6}\t`) and says it is "as
  a read of the file shows it". The read tool uses two spaces. Nothing parses it wrongly today (the edit tool
  strips both), but the model sees two numbering forms for one file.

---

## Fixtures that do not match the real format

The LF.1399 failure mode, found again in these tests. Each passes on an input the real tool does not produce.

| Test | Its fixture | The real output |
|------|-------------|-----------------|
| `tests/test_failing_tests_that_stop_at_one_step_are_one_defect.py` (`_thrown_by_the_helper`, `_direct`) | Message starts `Error: Login rate limited` | Starts with `file:line:col › title ────`, then a blank line, then the indented error (finding 1) |
| `tests/test_a_sprint_later_sprints_build_on_is_not_deferred_past.py:178` | `failure_step("Error: Login rate limited\n at login ...")` | Same header line first |
| `tests/test_a_failing_criterion_carries_what_the_product_s_server_logged.py` | A Node/Hono log with one error and five frames | A uvicorn log: an access line per request, each containing "Internal Server Error", and Python frames (finding 3) |
| `tests/test_nextest_minitest_and_gradle_report_countable_totals.py` | nextest `PASS`/`FAIL` lines and the `Summary` line | A failing test's captured output with libtest's `test result: FAILED. 0 passed; 1 failed` before the `Summary` (finding 4a) |
| `tests/test_a_second_runner_in_one_command_is_counted.py` | TAP followed by Playwright | Vitest followed by pytest, the fullstack packs' real pair (finding 4c) |
| Same file, `PLAYWRIGHT_RED` | `2 failed` directly above `8 passed` | The list of failed tests between them, and for long runs a cut in the middle (finding 4d) |
| `tests/test_runner_totals_are_read_within_their_summary_line.py` and the others for pytest | `passed` and `failed` only | `N passed, N warnings, N errors in Ns` (finding 4b) |
| Tests of `map_of` and of localisation | JavaScript and Python sources | No C#, Java or PHP source in any of them (finding 2) |

**Proposal.** A folder `tests/captured/` of real outputs, one file per runner and per tool, each named for the
tool and its version and taken from a run. Parser tests read from it. When a pack's runner is upgraded,
`verify_packs` writes the new output there, so a format change fails a test instead of returning zero.

---

## Checked and fine

- **`read_file` numbering.** 9,339 real results. The three readers of the gutter (`compaction.py:230`,
  `workspace_digest.py:470`, `repository.py:612` and `:669`) all accept the two-space form. No tab-only pattern
  is left in `src/app` or `scripts/`. `workspace_digest` does not match a long line's continuation marker
  (`12.1`), which does not change its first and last line.
- **`ls`, `glob`, `grep` results.** Nothing in `src/app` parses their list or match text. Only the harness's own
  notes are matched, and those match.
- **JUnit XML** (`acceptance/junit.py`). 756 real reports from 16 packs: Playwright, node:test, pytest, Vitest,
  gotestsum, nextest, Surefire, the .NET JUnit logger, PHPUnit and RSpec. Parsed test and failure counts equal
  the files' own `tests`, `failures` and `errors` attributes wherever those exist. No suite-level error was
  missed. The 3 unparseable files are reports cut off at 52 bytes by a killed runner, and that case is handled
  (`ci.py`, `UNIT_TESTS_DID_NOT_RUN`).
- **Totals for** jest, Vitest alone, pytest without errors, Playwright not cut, TAP and the spec reporter,
  gotestsum, `go test -v`, Maven (quiet and per class), .NET, PHPUnit and RSpec: correct on every distinct real
  summary seen.
- **"The product did not start" / "crashed"** (`suite.py:2500-2700`). 10 real results with that problem are all
  true ones (a Go build error, a missing toolchain). No false one among 243 results with tests.
- **Refusal counting** (`settled_answer._REFUSED`, `_NOTHING_NEW`): matches every real refusal shape but the one
  in finding 6.
- **Tool calls written as text** (`text_tool_calls.py`). 5 of 9,892 replies held call markup in their text, and
  all 5 also carried real calls. No reply was lost to it.
- **Reasoning token counts.** The llama.cpp servers report none (`output_token_details.reasoning` absent on 1,721
  reasoned replies; all 418 replies of run-2f653f55). Every reader has the length fallback
  (`deliberated_reads.py:68`, `run_kpis.py:209`, `scripts/loop/run_timing.py:120`).
- **`loop.sh effects`** on run-32362f3b: reads per file and summaries are non-zero and plausible after LF.1399.
- **Language service** (pyright and the TypeScript server): read as JSON, not by pattern.
- **Git output.** Reads are `--name-only`, `--porcelain` and `-z` forms. One theoretical gap: `diff --name-only`
  without `-z` quotes a non-ASCII path, which `ci.changed_since` (line 613) would then drop. No such path exists
  in the 260 workspaces.

## Not covered

- Structured answers in prose (`settled_answer._answer_in`): 471 real final texts parsed, but whether each stage
  expected a structured answer could not be told from the transcript, so no failure rate is given.
- The `<think>` text at the start of 104 recorded replies looks like the reply-salvage prefill; not traced to
  its end.
- The acceptance suite's static checks of test source (`suite.py`, about 200 patterns over the suite's own code)
  and `integration_checks.py` (172 patterns over product source) were not run pattern by pattern.
- `scripts/loop` audit scripts other than `effects` and `run_timing`.
- Package-manager output beyond `missing_in` (the dependency gate, resolved packages).

## Suggested order

1. Finding 1 (one shared header strip): small change, three decisions corrected.
2. Finding 3: before FX.1 and FX.7 are measured, or their evidence will still be access lines on Python services.
3. Finding 2: before FX.2 is measured on any C#, Java or PHP run.
4. Finding 4, then 5 and 6, with the `tests/captured/` folder.
