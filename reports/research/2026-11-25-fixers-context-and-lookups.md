# Fixers, context and internet lookups: why no bug lookup fired, and what to build

Date: 2026-11-25 (JST). Read-only review; nothing in `src/`, `tests/` or the configuration was changed.
Evidence: the transcript of the live medium run `run-32362f3b-ab2f-4298-b04c-baf1a5ca2638` (4,084 records, thorough
delivery, FastAPI + React, sprint 1 attempt 2), its workspace (`.harness/fix-journal.json`, the product's files),
`loop.sh defects` and `loop.sh effects`, the transcripts of the 39 runs of the last three days, the code named in each
section, and published work on other harnesses (sources at the end).

The owner's questions: "why is internet look up not being used for solving bugs, also are the fixers struggling because
of context pollusion? ... find a better solution".

## Short answers

1. **No bug lookup fired because no defect of this run ever carried an error to look up.** The lookup needs a defect
   that is stuck *and* states an error line. Of the eight fixers shown a defect, two were stuck and none had an error
   line: the product catches its own exceptions and answers 500 without logging them, and the defects a model wrote
   paraphrased the error away. The lookup never got as far as building a query. The tools offered to the model
   (`research`, `read_docs`, `look_up_package`, `module_exports`) were in 571 requests of this run and called 0 times.
2. **Yes, the failing fixers suffer context pollution, and it is structural.** A fixer opens at 26,400-34,000 tokens
   against a summary trigger of 43,020: 61-79% is spent before its first read. The five files on the failing
   request's path are about 12,800 tokens, so reading them once forces a summary. Each summary threw away what the
   fixer had worked out, and it read the same files again: 91 reads in the three failing fixers, 63 of them re-reads
   of a file that had not changed (69%).
3. **Context is not the only cause, and not the first.** The first cause is missing evidence: no fixer was ever shown
   the exception behind the 500, and none reproduced it. The others: no localisation ("Affected files: (none
   identified)"), thinking switched off into a read loop, two edit refusals at the last calls, and two defects no
   fixer can close inside its rules.
4. **The better solution** is the order other harnesses use: reproduce and capture the error, localise, then give a
   small fixer a small request. Lookups then have an error to search, and they should run on the harness's side.
   Eleven items, FX.1-FX.11, in section 4; FX.1-FX.4 carry most of the effect.

## 1. Why no bug lookup fired

### 1.1 The conditions, as the code has them

`src/app/graph/nodes/fixes.py` (`_what_others_found`) calls `stuck_lookup.for_a_fixer` for every fixer. It tries three
triggers in order (`src/app/graph/stuck_lookup.py`):

| Trigger | Fires when | This run |
|---|---|---|
| T2 install | the defect's actual behaviour contains the install-failed marker and the registry does not explain it | no install failed |
| T3 recurring build error | a compiler error code or a located `file:line: error:` in this round was also in the round before | `.harness/build-errors-by-round.json` is `{"0:1": [], "0:2": []}`: no build error in any round |
| T1 stuck | `WEB_LOOKUP_WHEN_STUCK` on, **and** `_stuck` (an earlier attempt on the defect ended not fixed, or the fix journal counts at least one failed fix of its problem), **and** not a mutation finding, **and** `_the_error_line` is not empty | see below |

`_the_error_line` takes the server's own line after "the server printed:" where a probe quoted one; otherwise the last
line that matches `what_went_wrong._AN_ERROR` (a capitalised name ending in `Error` or `Exception` followed by `:` or
`(`, a line starting `Error:`, `Caused by:`, `panic`, `FATAL`, `ERROR`) and is not the harness's or the test runner's
wording (`_NOT_THE_PRODUCT_S_WORDS`, which drops lines starting `Expected` or `assert`).

`WEB_TOOLS_AFTER_TWO_FAILED_FIXES` (`src/app/graph/web_tools_after_two_failed_fixes.py`) offers `search_the_web` and
`read_web_page` to a fixer once `failed_fixes >= 2` for its problem over the whole run.

The switches were on: the run's provenance lists `WEB_LOOKUP_WHEN_STUCK`, `WEB_TOOLS_OFFERED` and
`WEB_TOOLS_AFTER_TWO_FAILED_FIXES`.

### 1.2 Each fixer of this run against those conditions

I ran `_the_error_line` and `build_errors_in` in the worker on the text each fixer was shown. Every one returned
nothing.

| Fixer (JST) | Defect | Stuck? | Error line found | Why not |
|---|---|---|---|---|
| `defect_fix_1_0` 21:38 | code review: error middleware registered after the router | no | none | first fix; prose |
| `defect_fix_1_1` 21:38 | page check: raw colours | no | none | first fix; no error |
| `defect_fix_1_2` 22:00 | AC-1 registration answers 500 | no | none | first fix: attempt 1 ended on its time budget before any fixer ran, so no failed fix was counted |
| `defect_fix_2_2` 22:29 | AC-1 again | **yes** (journal: 1 failed fix) | none | the only text is Playwright's `Error: expect(received).toBe(expected)` in the middle of a line, `Expected: 201`, `Received: 500`, and five access-log lines `POST /api/register ... 500 Internal Server Error` |
| `defect_fix_2_5` 22:29 | AC-13 error handling | no | none | first fix; same kind of text |
| `defect_fix_2_3` 23:00 | SQLAlchemy mapper: ambiguous foreign keys | no | none | first fix; the test round wrote "fail ... with sqlalchemy.exc.InvalidRequestError." - a full stop, no message, so `_AN_ERROR` does not match |
| `defect_fix_2_4` 23:00 | JWT key 31 bytes | no | none | first fix; a warning |
| `defect_fix_2_0` 23:11 | code review again | no (its earlier fix "moved forward") | none | prose |

So the lookup returned at its gates every time and no query was built. That is why `effects` shows "HK.4 looked-up
defects closed by the next fix: not reached" and "KS.6 lookup sources answering: not reached", and why the outbound
gate counted 0 queries with the product's words removed and 0 not sent: the product's-words filter was never reached.
The 11 outbound queries were 9 advisory checks (`api.osv.dev`) and 2 support-date checks (`endoflife.date`).

Two-failed-fixes: AC-1 had one failed fix before `defect_fix_2_2` and has two now, so its *next* fixer will be offered
the web tools. The record says what to expect: over the last 39 runs the offer was made 19 times and the model made 0
web tool calls.

### 1.3 The three root causes

**a. The product hides its own error.** `routes/auth.py` wraps each handler in `except Exception:` and answers 500
with no log line (lines 99, 118, 182, 207, 263). The harness reads the server's log correctly
(`acceptance/suite.py::what_the_server_logged`); there is nothing in it but access lines. The plan's leftover from
LF.1401 ("a 500's server traceback fed into the fix brief") cannot work on this product as written: there is no
traceback to feed.

**b. The well-known error was seen and then lost.** The run's first test round (19:49 JST) had the exact text in a
command result: `AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_ARRAY'`. The model raised the
defect as "SQLAlchemy ARRAY type blocks SQLite table creation in test fixtures" with no error line. Attempt 1 then
ended on its time budget (219 active minutes against 102) before any fixer was sent, and attempt 2 did not raise the
defect again. `sa.ARRAY` is still in `models.py` (lines 145, 148) and in the migration (lines 77-78).

**c. Lookups wait for a failure that the structure rarely produces.** T1 needs a failed fix first. A sprint attempt
gets about two fix rounds and each fixer 16 model calls, so a defect meets "stuck" late or never. On the small
families this still fires (39 runs: 78 lookup records, about 37 of them T1 or T3; one run closed a defect right after its lookup).
On both medium runs of the period (this one and `run-bc3cbd00`, 22 fixers shown) it fired 0 times.

### 1.4 What the fixers actually needed from the web

Not an error search first. The failing fixers needed *how a library is used*:

- how to run Alembic migrations from application code with an async engine (both AC-1 fixers proposed
  `alembic.command.upgrade(alembic_context.get_context())`, which is not that function's signature);
- what to use in place of `ARRAY` on an engine that has none;
- how `relationship(foreign_keys=...)` resolves two foreign keys to one table.

None of the three triggers covers a usage question. `read_docs` and `research` are offered for it and were never
called.

## 2. Are the fixers struggling because of context pollution?

### 2.1 What happened, per fixer

Times are JST. "First input" is the server's token count for the opening request; the trigger is 43,020 tokens.

| Fixer | Calls | Summaries | Minutes | Reads / files | Re-reads | Changes kept | Ended |
|---|---|---|---|---|---|---|---|
| `1_0` code review | 18 | 2 | 21 | 18 / 5 (`main.py` 11) | 13 | 1 edit, 1 write | no answer; moved forward |
| `1_1` styling | 12 | 0 | 21 | 9 / 4 | 5 | 4 edits | closed by the round |
| `1_2` AC-1 | 19 | 2 | 15 | 34 / 10 (`auth.py` 11) | 24 | 0 (2 edits refused) | claimed a change it had not made |
| `2_2` AC-1 | 17 | 2 | 31 | 31 / 9 (`database.py` 8) | 22 | 0 | no answer |
| `2_5` AC-13 | 19 | 2 | 31 | 26 / 9 | 17 | 0 (1 edit refused) | no answer |
| `2_3` mapper | 16 | 1 | 11 | 4 / 1 | 3 | 8 edits, 1 write | unverified |
| `2_4` JWT key | 17 | 1 | 11 | 8 / 3 | 5 | 4 edits | its tests still fail |

The split is clear. Where the defect named its file (`styles.css`, `models.py`, `auth.py`), the fixer edited within a
few calls and was summarised once or never. Where the defect was an acceptance criterion with "Affected files: (none
identified)", the fixer read 26-34 times and changed nothing.

### 2.2 What fills the window

The opening request of `defect_fix_2_2`, in characters (31,776 tokens as the server counted it, 74% of the trigger):

| Part | Characters | Share | Needed for this defect? |
|---|---|---|---|
| Tool descriptions (16 tools) | 23,564 | 18% | 4 of the 16 were used by any fixer of the run: read, edit, write, run |
| System prompt (the backend builder's role) | 21,084 | 16% | builder rules: empty fields, length limits, normal forms; little of it is about fixing |
| Project memory: files held whole | 36,000 | 28% | `database.py` (5,400) yes; `helpers.js`, `auth.spec.js`, `alembic/env.py`, `models.py` at best partly. The route and service files the request passes through were **not** held |
| Project memory: criteria, specification outline, file index | 12,200 | 9% | little |
| Defect, steps, expected, actual | 2,100 | 2% | yes |
| What its failing tests printed | 5,600 | 4% | six blocks; five say the same thing as the first |
| Earlier attempts | 1,100 | 1% | carried the earlier fixer's untested theory forward |
| Standing sections (stack, setup, later sprints, API, contract, facts) | 20,200 | 16% | versions and the data-directory fact; the rest not |
| Workspace listing | 7,566 | 6% | partly |
| **Total** | **129,400** | | **about a quarter bears on the defect** |

The one fact that decides the fix, the exception behind the 500, is 0 characters of it.

Across the eight fixers the opening was 26,403-34,028 tokens. That leaves 9,000-16,600 tokens before the first
summary. The files on the path of `POST /api/register` (`routes/auth.py` 10,466 characters, `auth.py` 14,534,
`main.py` 8,317, `schemas.py` 10,857, `database.py` 6,399) come to about 12,800 tokens. A fixer cannot read the code
it must fix without being summarised.

Why the budget does not catch it: `request_budget.opening_target` sizes the *message* (target about 77,000
characters) and does not subtract the 45,000 characters of system prompt and tool descriptions. PA.1's gate
(`opening_room.OPENING_SHARE = 0.8`) is just missed at 0.61-0.79.

### 2.3 How summaries degrade it

Each failing fixer was summarised twice. What a summary did, measured on `defect_fix_2_2`:

- **It did not free room.** The request before the first summary was 41,578 tokens; the first request after it was
  42,243. The opening is carried whole and the kept tail was the last three file reads (33,000 characters).
- **It kept descriptions, not findings.** Its "Found" list: "`routes/auth.py:1`: Defines `POST /api/register`
  endpoint handler and imports auth functions", and five more of the same kind. The prompt forbids exactly this
  (LF.1360); the model wrote it anyway, because the summary call sees the files and not the fixer's reasoning.
- **It added a false lead.** "`requirements.txt:7` lists bcrypt but omits passlib, which is required for password
  hashing in standard FastAPI setups", with the next step "Add passlib". Nothing in the run supports it.
- **It lost the fixer's analysis.** Before the summary the fixer had reasoned for 12,119 tokens (5 minutes) about the
  migration code. The harness carries 800 characters of each reply's reasoning, in messages the summary then deletes.
- **After it, the fixer started again.** "Now let me read the full content of the key files that were folded", then
  the same three files. In `2_5`: "Let me re-read the key files I need to see in full, since the summaries were
  truncated".

### 2.4 What else makes them fail

In the order I judge their weight on this run:

1. **No reproduction, so no cause.** In 55 model calls the three failing fixers ran three commands. One was refused
   (`rm`), one printed "engine ok", one ran the suite and showed status codes. None printed the exception. The real
   chain behind AC-1, read from the workspace: `database.py` looks for `alembic/alembic.ini`, the file is at the
   project root, so the migration block never runs and no table exists; the block would not migrate if it did run;
   the migration creates `ARRAY` columns the embedded database cannot; the mapper has two ambiguous relationships.
   Four stacked causes behind one "500", and each fixer guessed at the second.
2. **Stale evidence.** `2_5`'s brief said three AC-13 tests received 429 and 404. Its own run of those tests
   received 500 and 404. The 429s came from the rate limiter filling up during the whole-suite run, not from the
   code under test.
3. **Thinking switched off into a loop.** Two replies in each failing fixer reasoned to the 12,000-token cap (about
   5 minutes each, 10 of 31 minutes). After the second, `SALVAGED_REPLIES_TURN_THINKING_OFF` keeps thinking off for
   the stage. 24 of the 55 calls then ran without reasoning. `2_2` asked for `database.py` six times running; each
   was answered "it is in the project memory", and the note that "a second read the memory answers ends reading"
   was not enforced. `2_5`'s last call, after a refused edit, was "I need to read the files to understand the
   current state".
4. **Edits refused at the last calls.** `2_5`: the `find` text carried the read tool's gutter as two extra spaces of
   indentation, the replacement kept them, and the file no longer parsed ("unexpected indent"). `1_2`: the edit used
   a name the file did not import; the language service refused it twice, correctly, and told the fixer to add the
   import in a separate edit when two calls were left.
5. **Anchoring on an earlier guess.** `1_2` reported a change it never made. The next brief said "changed no file"
   and then quoted the claim in full; `2_2` and `2_5` both adopted the same theory.
6. **Two defects no fixer can close.** Three of AC-13's six failing tests call `/api/tasks`, which the same brief
   says a later sprint builds and must not be built now (they receive 404). The specification's limit of 5 sign-ups
   per address per 15 minutes meets a suite that signs up more often than that from one address (429). The first
   attempt's code review and a tester's note both said so.
7. **The model's limits.** It does not know Alembic's API and does not ask. Published numbers agree: Qwen3-32B
   resolved 15.2% of 100 SWE-bench Verified tasks in a minimal agent, with passed runs averaging 8,854 tokens and
   failed ones 17,627; successful runs "typically remain under 20k tokens". These fixers *start* at 26,000-34,000.

### 2.5 The build in flight (LF.1404-1406)

Read from its worktree, not run.

- **LF.1404, a fixer that gave no answer gets the rewrite.** A sound net. On this run it would rewrite `database.py`
  on the same unproven theory, because the rewrite is shown the same evidence. Worth having; it does not close AC-1.
- **LF.1405, a read the call withheld is refused, not pointed at.** Correct and narrow. In `2_2` six of the seven
  pointer answers came before reading was withheld; it reaches the seventh.
- **LF.1406, a fixer's memory holds what it was reading after a summary (switch, off).** It removes re-reads, the
  largest visible waste. It also adds held files to an opening already at 61-79% of the trigger, so the next summary
  comes sooner. Measure it only after FX.3 and FX.4; alone I expect little.

All three treat the loop after it has started. None gives the fixer the error or the file.

## 3. What comparable harnesses do

| Practice | Who | What it says for this harness |
|---|---|---|
| Localise before editing, as its own step | Agentless: files, then functions, then edit lines, then repair, then validate against tests; 32% of SWE-bench Lite at $0.70 a task with no agent loop. AutoCodeRover and Moatless search by code structure first | The fixer should start with the files and lines, not find them inside its 16 calls |
| Small windows on files | SWE-agent's viewer shows 100 lines a turn with scroll and in-file search; its search lists matching files only, because more context "proved too confusing" | Whole-file reads dominate this run (`effects`: 193 whole against 30 by range in the test rounds; the builders 0-2 by range) |
| Edits checked and refused with the reason | SWE-agent's linter gate; Aider's and Codex's patch formats tolerate whitespace and carry several hunks in one patch | The gate exists here; the tolerance and the multi-hunk edit do not |
| Mask old observations instead of summarising | "The Complexity Trap" (NeurIPS 2025): replacing old tool outputs with a placeholder matched LLM summaries on solve rate at half the cost of the raw agent; the window size must be tuned per agent | Supports replacing the summary call in fix stages |
| Short trajectories | "The Limits of Long-Context Reasoning in Automated Bug Fixing" (2026): agent success comes from decomposition; longer contexts correlate with failure; single-shot 64K-token prompts solved 0-7% | Supports a lean opening over a larger window |
| Search in a separate context | Claude Code's Explore sub-agents and Deep Agents' `task` tool return a conclusion, not the files read | A localisation call that returns paths and lines is this pattern at one call |
| A map instead of file bodies | Aider's repository map: ranked signatures within a token budget | The memory's "What those files define" list is this; it should be ranked by the failing request |
| Tests as the loop | Aider runs the test command after each edit and feeds back the failure; Agentless filters patches by reproduction and regression tests | AY.3 is the start of this; the fixer should not spend calls on it |
| Web and docs | Hosted agents search because their models choose to. For weaker models the evidence is about *documentation in the prompt*: with no documentation, 42.6% of code for updated APIs ran in the target environment (270 API updates, 11 models); retrieved docs help with less common APIs and can hurt on common ones when the retrieval is poor; code examples help most | The harness, not the model, should fetch; fetch from the installed version; keep it short and exact |
| Earlier reasoning kept across tool calls | Qwen3.6's template has `preserve_thinking`; a 2026 study reports 2-5% better multi-turn tool calling with thinking history kept | Worth one measured trial on the llama.cpp servers |

The earlier finding stands (`reports/research/2026-11-24-agents-that-work-like-a-team.md`): this model does not call
offered web tools, so lookups must be run by the harness at fixed points. This run adds a second: the fixed points
need an error to exist.

## 4. Recommended design

One sequence for every stack: **capture the error, find the place, hand a small request to a small fixer, check after
each change, look up when the error names a library.** Nothing below names a language or a framework; where a stack
needs its own detail it goes in its pack.

| Item | What | Where | Size | Measured by | On or switch |
|---|---|---|---|---|---|
| **FX.1** | **A server error with no logged cause is the first defect.** When a failing test received a 5xx (or the process died) and the server's log states no error for that request, the brief says so and asks for one thing first: make the handler that answers the error log the exception with its trace, then run the failing test. The harness re-reads the log after that run and re-issues the defect with the error line and the product's frames as its affected files. Also one builder rule: a handler that answers a server error logs the exception first | `acceptance/suite.py::what_the_server_logged`, `graph/acceptance_nodes.py` (`server_log_block`), the brief builder in `graph/nodes/fixes.py`; builder prompt | M | share of 5xx defects whose brief carries an error line (this run: 0 of 3); fixers closing a 5xx defect | on (a bug: evidence missing) |
| **FX.2** | **Localise before the fixer.** From the failing test's request (method and path) or the trace's frames, find the handler and the modules it imports (`.harness/project-graph.json`), hold those whole and drop the files only the test names. Where the graph gives nothing, the one cheap localisation call that the rewrite path already has (`graph/localisation.py`, AY.1) | `agents/project_memory.py` (the "Held whole" choice), `graph/localisation.py`, `nodes/fixes.py` | M | "Affected files: (none identified)" count; share of a fixer's first three reads already held; reads per file | on |
| **FX.3** | **A lean fixer request.** A fixer's own short system prompt in place of the builder's; six tools (read by range, search, edit, write, run, answer); repeated test failures printed once with the others as one line each; standing sections kept only where the defect touches them; `opening_target` subtracts the system prompt and tool descriptions. Target: opening at most half the trigger, about 21,000 tokens | `agents/stage_tools.py`, the fixer's prompt, `agents/request_budget.py`, `nodes/fixes.py` | M | opening tokens (now 26-34K; target 21K or less); summaries per fixer (target 0 in 16 calls) | on for the duplicates and the budget arithmetic; the short prompt and tool set behind one switch until two runs show no loss |
| **FX.4** | **Fix stages keep old reads as one-line stubs and are not summarised by a model.** An earlier read of an unchanged file becomes "read `path` lines a-b, unchanged"; the fixer's own words, its carried reasoning, command results and refusals stay. The trigger for a fix stage is computed from its own 12,000-token reply cap, not the 32,000 every stage reserves (about 59,000 tokens by my reading of the same arithmetic; confirm in `ContextBudget.from_window`) | `agents/compaction.py`, `agents/context_budget.py` | M | summaries in fix stages (target 0); re-reads of unchanged files (now 69%); false leads cannot occur | switch (it changes cost and speed); the trigger arithmetic on once measured |
| **FX.5** | **The fixer's conclusion survives.** After a reply that reasoned to its cap, the end of that reasoning is pinned in the request as "what you worked out", kept through any compaction. After thinking goes off for the stage, the next call is offered only the tools that change a file, run a command or answer | `agents/settled_answer.py`, `models/reply_salvage.py`, `agents/compaction.py` | S | calls without reasoning that repeat the call before them (this run: 6 running in one fixer); fixers ending with no answer | on (the loop is a bug) |
| **FX.6** | **Edits that land.** The replacement is re-indented by the difference between the `find` text and the lines it matched; one edit call may carry several changes to one file, applied together and checked once (an import and its use) | the edit tool behind `edit_artifact` | S-M | edits refused for indentation or for a name the same call would have added (this run: 3, all in the failing fixers' last calls) | on |
| **FX.7** | **Fresh, first-failure evidence, and the check after a change.** Before a fixer is shown a criterion, the harness runs that criterion's first failing test alone and shows that result; after each kept write it runs it again and returns the first failure and any server error in at most 1,500 characters | `graph/fresh_evidence.py`, AY.3's path | M | briefs whose evidence differs from the isolated run (AC-13's did here); command output characters per fixer | on |
| **FX.8** | **A defect a model raises carries the error as printed.** When a test round or a review raises a defect, the harness attaches the error lines from that stage's own command results that the description's words match. `_AN_ERROR` also accepts a dotted exception name with no colon | `observability/defect_ledger.py` at "raised", `acceptance/what_went_wrong.py` | S | test-round defects with an error line (this run: 0 of 3; the `ARRAY` error was in the stage's results word for word) | on |
| **FX.9** | **Look up at first sight when the error is a library's.** Where the error line or its trace names an installed third-party package, the lookup runs for the defect's first fixer, not after a failed fix. Still once per distinct error per run, through the one outbound gate | `graph/stuck_lookup.py` (a fourth trigger) | S | lookups per run on medium briefs (now 0); HK.4's closed-by-the-next-fix rate against T1's | switch, in the "Internet lookups" group |
| **FX.10** | **A usage note from the installed package.** Where an edit is refused for a name or attribute of an installed library, or the localised lines call one, the harness attaches that function's own signature and docstring from the installed version (what `module_exports` returns), and one official example where the search service finds it. Stop offering `research`, `read_docs`, `look_up_package` and `module_exports` to fixers of a model that has never called them (`WEB_TOOLS_BY_MEASURED_TIER`, built, off) | `tools/research_tool.py`, `nodes/fixes.py`, `tools/lookups.py` | M | fixes that call a library function with a signature it does not have; tool-description characters saved | switch |
| **FX.11** | **Say why no lookup ran, and route what no fixer can fix.** One ledger record per fixer shown: looked up, or the gate that stopped it (not stuck, no error line, mutation finding, nothing found). And before a criterion goes to a fixer, a failing test whose route this sprint does not build, or that fails on a limit the specification sets, is held as a dispute for the lead instead | `graph/stuck_lookup.py`, `scripts/loop/effects.py`; the dispute path of LF.185/LF.202 | S + M | `effects` prints the gate counts; fixer minutes spent on tests that cannot pass in the sprint | on |

Optional trial, not an item: set Qwen3.6's `preserve_thinking` through `chat_template_kwargs` on the two llama.cpp
servers for one run pair and compare re-reads and calls to first write. It costs prompt tokens; measure before
keeping. It is a model setting, so it is the owner's to try.

### Order and bundles

1. **Bundle A (evidence): FX.1, FX.7, FX.8, FX.11's record.** Without the error nothing else helps, and the existing
   lookup starts firing by itself once defects carry an error line.
2. **Bundle B (request): FX.2, FX.3, FX.5, FX.6.**
3. **Bundle C (behind switches, one measuring pair each): FX.4, FX.9, FX.10, then LF.1406 on top.**

### Expected effect on this run's open defects

| Defect | Today | With the design |
|---|---|---|
| AC-1 registration answers 500 (two fixers, 46 minutes, nothing changed) | no error shown; four stacked causes | FX.1 exposes the first error (no such table); FX.2 holds `routes/auth.py`, `auth.py`, `database.py`; FX.7 shows the next cause after each fix. Each of the four causes becomes one short fix with its own error line. The `ARRAY` and mapper errors are library errors, so FX.9 looks them up at first sight and FX.10 supplies the migration call's real signature. I expect it to close in two or three fix rounds; I cannot promise fewer, because there are four causes |
| AC-13 error handling | three tests need routes of a later sprint; the others showed stale 429s | FX.11 holds the three as a dispute for the lead; FX.7 shows the true result (500) for the rest, which then share AC-1's cause |
| SQLAlchemy `ARRAY` on the embedded database (raised once, never fixed, not raised again) | error text lost | FX.8 keeps `'SQLiteTypeCompiler' object has no attribute 'visit_ARRAY'` on the defect; it surfaces again as AC-1's third cause |
| Mapper: ambiguous foreign keys (unverified) | fixed blind | FX.7's check after the write says whether it held |
| JWT key length (tests still fail) | file known; four edits | little change; FX.6 and FX.7 shorten it |
| Code review: middleware order | moved forward | little change |

What I have not shown: that the model fixes each cause once it sees the error. The small families suggest it does (a
lookup closed a defect on the next fix on 11-25), but that is one case. Bundle A is cheap to check on this run's
workspace by rewinding to the fix round.

## 5. What not to do

- **Do not raise the window or the trigger as the main fix.** Longer contexts go with failure for models of this
  size. Shrink the opening first; FX.4's trigger change only stops needless summaries.
- **Do not add more offered tools or more wording asking the model to search.** 571 requests, 0 calls. Each offered
  tool costs every request its description.
- **Do not wait for two failed fixes before the first lookup** on a library's error. Two failed fixes cost this run
  46 minutes on one defect.
- **Do not paste raw search results into the brief.** Poorly matched documentation lowers results on well-known
  APIs. One short note, version-checked, from the installed package first.
- **Do not hold more files whole (LF.1406) before the opening is lean.** It trades re-reads for earlier summaries.
- **Do not give fixers more calls.** The failing fixers had no new information after call 5; calls 6-16 repeated
  calls 1-5.
- **Do not keep thinking off for a whole stage with the full tool set.** Without reasoning this model repeats its
  last call.
- **Do not send a rewrite, or a second fixer, at a defect whose cause has not been reproduced.** It rewrites on the
  same guess, and the next brief then carries the guess as an earlier attempt.
- **Do not quote a fixer's claim in "Earlier attempts" when the harness measured that it changed no file.** Say what
  was measured only.
- **Do not put framework names in any of this.** "A handler that answers a server error logs it" and "the files a
  failing request passes through" hold for every stack; a pack supplies its own way to read a route table.

## Sources

- Agentless: https://arxiv.org/abs/2407.01489v2
- SWE-agent, the agent-computer interface: https://arxiv.org/abs/2405.15793v3 and https://princeton-nlp.github.io/SWE-agent/background/aci
- The Complexity Trap (observation masking against summaries): https://arxiv.org/abs/2508.21433
- The Limits of Long-Context Reasoning in Automated Bug Fixing: https://arxiv.org/html/2602.16069v1
- mini-SWE-agent: https://github.com/SWE-agent/mini-swe-agent
- Context Rot (Chroma): https://research.trychroma.com/context-rot
- When LLMs Lag Behind (evolving APIs): https://arxiv.org/pdf/2604.09515
- On Mitigating Code LLM Hallucinations with API Documentation: https://arxiv.org/abs/2407.09726
- Retrieval for less common libraries: https://arxiv.org/html/2503.15231v1
- Qwen3.6 `preserve_thinking`, third-party reports, not checked against the model card: https://github.com/NousResearch/hermes-agent/issues/56004 and https://docs.fireworks.ai/fine-tuning/thinking-history
- Thinking history and tool calling: https://arxiv.org/pdf/2606.00135

Aider's repository map, Codex's patch format, Claude Code's sub-agents and Deep Agents' `task` tool are described from
their documentation as I know it; I did not re-read those pages for this report.
