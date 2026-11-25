# Deep review: what the model is told vs what is true

Date: 2026-11-25 (written 2026-11-26 JST). Read-only review; nothing in `src/`, `tests/`, config or docs was changed.

## Scope and method

- **Runs read (17, all stacks in use):**
  - FastAPI + React medium brief: run-8f0be29e, run-c53e7bd2, run-bc3cbd00, run-32362f3b
  - fullstack-bookmarks (Express): run-b6c5c636, run-2f653f55
  - notes-api: JavaScript run-031094d4, Go run-127780fe and run-1d79334d, Rust run-c4fd577a, Java run-cc265cee, C# run-c46d5d9a, PHP run-f4bab632
  - tasks-api run-ec516cd8, wordstats-cli run-2c83118a, textkit-lib run-88549ebb, web-todo run-972956f5
- **What was read:** the `model_request` records themselves, rebuilt to the full conversation from the transcript's
  deltas (`carried` + `messages`): system prompt, project memory, request blocks, workspace digest, mid-stage notices,
  and every tool result.
- **How each claim was checked:** against the tool list of the same request, the tool results that followed, the
  workspace on disk (4 runs), the sandbox images, and the code that writes the sentence.
- **"Acted on"** means a call the model made that the false statement explains (a refused call, an extra read, an
  install later undone).
- Times are JST. Transcripts log UTC.

## Findings, ranked by impact

### 1. The interface contract's criterion ids are line numbers in 7 of 15 runs, and are handed on as fact

- **Evidence.** In run-32362f3b (fixer `defect_fix_1_2`, 22:00 JST 11-25) the request says, under "The interface
  contract: the acceptance suite and the release check these lines ... Build to them word for word":
  - `AC-6 POST /api/register -> 201` - AC-6 is "Task categories and tags"
  - `AC-3 page /tasks textbox "Search"` - AC-3 is "Assign tasks to team members"
  - `AC-5 page /analytics textbox "Total Tasks"` - AC-5 is "Due dates and reminders"
- **Same request, contradicting it:** "What later sprints build - not this sprint's work: AC-6 ... A failing test of a
  later criterion is never a reason to change code now." Registration is this sprint's AC-1.
- **How general.** The architect numbered the lines 1..n instead of naming the criterion each serves:

  | Run | Family | Lines | Example |
  |---|---|---|---|
  | run-ec516cd8 | tasks-api | 20 | `AC-2 POST /signup -> 409` (AC-2 is sign in) |
  | run-2c83118a | wordstats-cli | 14 | `AC-7 command wordstats <file> -> exit 0` |
  | run-bc3cbd00 | medium | 10 | `AC-2 page /login ...` (AC-2 is task CRUD) |
  | run-c53e7bd2 | medium | 6 | `AC-3 page /tasks ...` |
  | run-cc265cee | notes-api Java | 6 | `AC-6 GET /health -> 200` (AC-6 is "survive a restart") |
  | run-f4bab632 | notes-api PHP | 6 | same |
  | run-32362f3b | medium | 9 | partly sequential, as above |

- **What depends on the id.** `interface_contract.py` titles each probe `[AC-n] contract ...`, charges a failure to
  that criterion, and excuses a missing page control when "its criterion's own tests passed"
  (`_its_criterion_passed`, `src/app/acceptance/interface_contract.py:2086`). With a wrong id these read another
  criterion's result.
- **Root cause.** `src/app/agents/ledger.py:63-77` and `interface_contract.py:43` take the leading `AC-n` as written.
  Nothing compares a line with the criterion it names. `specification_consistency.py` checks statuses only.
- **Fix (stack-agnostic, always on).** At specification time, for each contract line:
  - HTTP lines: the route must appear in the named criterion's text, or in a test case tagged with it.
  - Page and command lines: the control name or command must appear there.
  - If the ids are exactly 1..n in order and fewer than half pass, send the section back once with the mismatches
    listed; after that, drop the id (the code already handles a line with no criterion).
- **Test from real output.** The `interface_contract` list and criteria of run-ec516cd8 (20 lines) as a fixture: the
  check flags `AC-2 POST /signup -> 409`. The list of run-2f653f55 (ids correct) passes untouched.

### 2. "Which side stands" rulings pair statements that do not conflict, and a brief criterion loses

- **Evidence.** run-2c83118a (wordstats-cli), in all 27 builder and fixer requests:
  "DR-9: 'Returns the string.; returns: str: Compact JSON string ...' stands, over 'AC-7: Character count includes
  newlines; line count includes a final line even if it lacks a trailing newline.' ... Build and test to the
  statement that stands." DR-10 and DR-11 say the same against AC-7.
- **What followed.** The same request's "specification for your files" gives "AC-4: TestStdinSupport ... stdout
  contains `lines: 0`" as decided. Fixer `defect_fix_1_0` (08:28 JST 11-25) changed `count_lines` to return 0 for
  "hello world", against AC-7, and wrote: "the acceptance suite has an internal contradiction ... I prioritized the
  explicitly assigned defect." The fix was reverted (the product review records "one fix reverted").
- **How general.** 5 of 13 runs carrying the block have at least one ruling of the form `X stands, over "AC-n: ..."`:
  run-2c83118a (3), run-972956f5, run-b6c5c636, run-ec516cd8, run-f4bab632 (there, "AC-1 POST test stands, over
  AC-5/AC-12 delete test").
- **Root cause.** `src/app/agents/specification_rulings.py:437-440` prints whatever pair the ruling stage returned.
  Nothing checks that the two quotes are about the same thing, or that a criterion is never the side that gives way
  to a specification sentence.
- **Fix (always on).**
  - A ruling whose `gives_way` quote starts with a criterion id, or is found in `acceptance_criteria.md`, is not
    shown to builders. It is filed as a suite or specification dispute.
  - A ruling whose two quotes share no route, name, field or command token is dropped and recorded under
    `rule_could_not_apply`.
- **Test from real output.** `.harness/specification_rulings.json` of run-2c83118a: DR-9, DR-10 and DR-11 are not
  rendered. The rulings of run-031094d4 (none against a criterion) render unchanged.

### 3. The stack block says "already decided ... build on exactly this" with tools the specification replaced

- **Evidence.** run-32362f3b, every builder and fixer request: "Other tools: ... python-jose (JWT), passlib (password
  hashing) ... Build on exactly this."
  - The same request's pack guidance says passlib 1.7.4 fails with bcrypt 5 and to hash with bcrypt directly.
  - The specification (ADR-04, ADR-13) decided bcrypt and PyJWT.
  - `requirements.txt` on disk has `pyjwt` and `bcrypt`.
- **Acted on.**
  - `specialist_database_0` added and installed `python-jose[cryptography]` (14:00-14:11 JST 11-25).
  - `specialist_backend_1`'s work note records "JWT authentication via python-jose and passlib".
  - Architecture review raised "JWT library is ambiguous".
  - `specialist_backend_0` removed the dependency again at 20:39 JST.
  - run-8f0be29e: the database specialist installed `passlib[bcrypt]` and `python-jose` the same way.
- **Related.** The same requests carry "Library calls, as their documentation gives them: Library: PyJWT 1.4.0",
  while "Versions here" says pyjwt 2.15.1 (21 messages in run-32362f3b; no other run had a major-version mismatch).
- **Root cause.**
  - `src/app/agents/specialists.py:685` renders the stack selector's `additional_tools` as binding. The specification
    is written later and nothing reconciles the two.
  - `specialists.py:987` labels the architect's own lines "as their documentation gives them".
- **Fix (always on).**
  - Render "Other tools" as "named at stack selection; the specification decides the libraries".
  - Drop any tool the specification's ADRs or `library_usage` replace, and any the pack's known-errors text warns
    against.
  - Replace a library version in `library_usage` that disagrees with `.harness/stack-facts.json` by the installed
    one, and say so.
- **Test from real output.** `technology_stack.md`, the specification and `stack-facts.json` of run-32362f3b: the
  rendered block has no `passlib` or `python-jose`, and the PyJWT line says 2.15.1.

### 4. "Still listed, but refused" names only the first 12 withheld tools

- **Evidence.** run-031094d4 `specialist_backend_0` (14:59 JST 11-24): the notice lists `delete_artifact` ...
  `read_web_page` and stops. The model called `run_terminal_command`, which was not in the list, and was refused.
  Same in run-32362f3b `specialist_database_0` (14:17 JST) and `specialist_backend_1` (15:01 JST, `write_artifact`).
- **How often.** 139 "withheld" refusals in 12 runs. 24 of them (17%, 5 runs) were calls to a tool the notice had left
  out. The other 115 named the tool and the model called it anyway.
- **Root cause.** `src/app/agents/settled_answer.py:1876`: `sorted(withheld)[:12]`. Alphabetical order always drops
  `research`, `run_terminal_command`, `run_validation`, `search_the_web`, `use_runtime`, `write_artifact` - the tools
  most likely to be called next.
- **Fix (always on).** When every tool is withheld, say "every tool except your answer"; otherwise list all of them.
- **Test from real output.** The 15-tool list of the 14:59 request: the notice names `run_terminal_command` and
  `write_artifact`.

### 5. Three statements about which programs exist, each wrong for the image the command runs in

- **Evidence, one request** (run-32362f3b `defect_fix_1_2`, Python pack image):

  | Source | Says | True in `harness-sandbox-python:pw1.64.0` |
  |---|---|---|
  | Environment contract, "Available commands" | jest, mocha, pnpm, poetry, ruff, ts-node, tsc, uv, yarn, ... | pnpm, poetry, ruff, uv, jest, mocha, tsc, ts-node not on PATH |
  | Stack note | "`make`, `pnpm` and `yarn` are not installed here either" | make and yarn are installed |
  | Refusal text | "Allowed and installed: cargo, ... go, ... make" | cargo and go are not in the image |

- **How often.** "Available: pnpm, yarn" and "pnpm and yarn are not installed" sit in the same request in 449
  messages across 12 runs.
- **Acted on.** Low. No command in the 17 runs tried poetry, uv, ruff, pnpm, make, cargo or go on the wrong stack.
  The cost is three contradicting lines in every request, and a refusal that advises the wrong thing when it does
  matter.
- **Root cause.**
  - `src/app/tools/sandbox.py:2081` (`_installed`) calls `shutil.which` in the worker, while commands run in the
    pack's image (`SANDBOX_EXECUTION_MODE=container`).
  - `src/app/agents/environment_contract.py:245` prints the testing role's allowlist as "Available".
  - `src/app/agents/specialists.py:453` is a constant measured on the worker image.
- **Fix (always on).** One source: the pack image's program list, recorded when the image is built (or probed once
  per run and cached in `.harness/`). The contract, the stack note and the refusal all read it. Per-stack lists stay
  in the sandbox's toolchain table.
- **Test from real output.** With the Python image's recorded list, the three texts for that request agree: yarn and
  make present, cargo, go, pnpm and poetry absent.

### 6. "Code cannot be handed to a program as an argument. This is refused every time" - it is run

- **Evidence.** 526 messages in 10 runs carry the sentence for `python -c` / `node -e` / `php -r`. Of 209 inline-code
  commands the models sent anyway, 207 were run from a `tmp-inline-*` file ("Ran the code you passed on the command
  line from ..."). None was refused for being inline.
- **Acted on.** Models that obeyed wrote 28 `tmp-<x>` scratch files, ran them in 34 commands and deleted 11 - about
  70 extra calls, mostly in the medium runs. Leftover `tmp-diag-*.py` files were still in the workspace digest of
  run-32362f3b.
- **Root cause.** `src/app/agents/specialists.py:527` predates the rewrite in `src/app/tools/agent_toolkit.py:745`
  (owner decision 2026-10-20).
- **Fix (always on).** Say what happens: "code passed on a command line is saved to a `tmp-inline-*` file and run
  from there; the harness removes it."
- **Test from real output.** The rendered note for the stack of run-32362f3b has no "refused"; the tool result of a
  real `python -c` call from that run still matches the note's wording.

### 7. "Do not run them yourself" beside "Run `npm run test:acceptance`" and "Run every unit test with `npm test`"

- **Evidence.** 80 fixer and tester messages in 7 runs hold both:
  - "Reproduction steps: Run `npm run test:acceptance -- --grep ...`", and
  - "Kept by the harness: ... and the manifest scripts `test`, `test:acceptance`, `start`. They are test setup ...
    do not change them, test them, run them yourself or build on them."
  - The workspace digest adds "do not change, run or test it" on `playwright.config.js`.
  - A guard's own refusal says the opposite (run-c53e7bd2 `test_round_0`, 19:17 JST 11-24): "Run `npm test` and
    `npm run test:acceptance` ... as they are."
- **True rule.** Running the scripts is allowed and works: 73 runs of the acceptance command across stages, none
  refused for being run. Only the setup files must not be executed directly.
- **Root cause.** `src/app/stacks/contract.py:870` lists the manifest scripts in the "do not ... run" sentence;
  `src/app/agents/workspace_digest.py:193`; `src/app/graph/acceptance_nodes.py:2549`.
- **Fix (always on).** Split the sentence: files not to change or execute directly; scripts not to change, which are
  the way to run the tests.
- **Test from real output.** The setup block rendered for the pack of run-2f653f55 does not put "run" and
  `test:acceptance` in one prohibition.

### 8. Project memory says "whole and current ... reading returns nothing new" after the file has changed

- **Evidence.** In 675 of 1,089 requests that carry both notes, the same file is named in the opening "[Already in
  front of you, whole and current, in the project memory ... Reading any of them returns nothing new]" and in the
  tail "[Project memory update] Changed since the project memory was taken (read for the current text)".
  First seen in run-031094d4 `acceptance_author_1` (14:46 JST 11-24).
- **Acted on.** Not measured as costly: mostly the stage's own writes, and only about 16 "could not find that text"
  edit failures in all 17 runs.
- **Root cause.** `src/app/agents/project_memory.py:1069` is written once at the start and never amended.
- **Fix (always on).** Word the opening note as "as they were when this stage began; a note at the end of each
  request lists any that changed since". The tail note stays as it is.
- **Test from real output.** The pair of notes from the 14:46 request: no file is called both current and changed.

### 9. The architect is told to read library calls "with `read_docs`, not recalled" and has no such tool

- **Evidence.**
  - With tools: `read_docs` was offered to the architect in 4 of 17 runs (Go ×2, Java, PHP) and not in 13.
  - Toolless part and revision calls carry the same instruction in 18 requests across 13 runs
    (`src/app/agents/principal_architect.py:269` and `:596`).
- **Consequence.** Library lines are recalled, then labelled "as their documentation gives them" (finding 3).
- **Fix (always on).** Print the sentence only when the tool is in the request's tool list. Otherwise say "from the
  stack facts and usage notes above; where unsure, say so in `open_questions`".
- **Test from real output.** The run-2f653f55 architect request (no `read_docs` in `tools`): the system prompt has
  no `read_docs`.

### 10. "The tool returns 100 lines unless asked for more"

- **Evidence.** 4,372 of 7,587 `read_file` calls with no `limit` returned more than 100 lines. The real default is
  the whole file up to 400 lines (`src/app/tools/agent_toolkit.py:43`). The sentence is at
  `src/app/agents/role_agent.py:575`.
- **Acted on.** 128 files were first read in windows of 150 lines or fewer; 68 of them needed 268 further window
  reads. Some of these were deliberate partial reads.
- **Fix.** "returns the whole file up to 400 lines". No test (copy change).

### 11. Smaller ones

- **`docs/` "holds only these files" (9 named).** On disk there are 11-17, including `acceptance_criteria.md`, which
  the project memory itself shows, `acceptance_tests.md`, `decision_log.md` and sprint summaries.
  `src/app/agents/role_agent.py:545`. No cost measured.
- **A testing work order given product build steps.** run-c4fd577a `specialist_testing_2` (23:37 JST 11-24): "Steps:
  1. file: notes-api/src/database.rs add: Define structs ..." and "Build order: file: notes-api/src/lib.rs add: ..."
  while owning only `tests/*.rs`. It was refused 19 writes to `src/lib.rs`; its stated reason was a product that did
  not compile. 1 of 7 testing work orders with steps had this. `_the_entries_about_its_files`
  (`src/app/agents/specialists.py:960`) matches implementation-order entries by any file name they mention. Fix:
  keep only entries whose `file:` is one of the work order's own files.
- **Fixers get "The specification for your files" for files they may not touch.** run-32362f3b `defect_fix_1_2`: a
  backend fixer was given six `acceptance/test_*.spec.js` entries (none exists; the suite's files are
  `auth.spec.js` etc.) and test cases whose ids disagree with the criteria (`AC-15 test_search_and_filter`; AC-15 is
  "Database migrations required"). Fix: for a fixer, leave out entries for locked suite paths.
- **"Where things stand" naming files that had moved.** Old run only (run-8f0be29e, 9 failed reads). On run-32362f3b,
  run-2f653f55, run-ec516cd8 and run-2c83118a every file it names is on disk.

## Checked and fine

- **Tool names in prompts vs tools offered.** Every backticked tool name in system, human and tool messages was
  compared with the request's tool list. The only misses are finding 9 and a "what went wrong earlier" digest
  quoting other stages' tools.
- **Model-call budget notice.** 148 conversations. The stated count was never off by more than 1, and no
  conversation ran more than 1 call past the stated limit.
- **Workspace digest "Files already in this conversation (call N; lines a-b)".** 24,750 entries; each has its read
  result still whole in the same request. No entry points at a result a summary removed.
- **"A fix with no named regression test cannot be accepted".** Enforced (`src/app/graph/workflow.py:3971`); 3 of 41
  answers came without one.
- **"Started again from an empty conversation" at the step ceiling.** True apart from the carry-over note.
- **Ownership refusals.** "QA writes only `acceptance/`", "test round does not change the product", "first attempt
  writes tests only", "belongs to another work order": the request states the same rule before the guard applies it.
- **Wrong-mode text.** The CLI and library runs (run-2c83118a, run-88549ebb) carry no page, server or `/api/` setup
  text in the request blocks; only the generic environment contract mentions a browser.
- **`cd`, `rm`, shell operators, `NAME=value`.** Told plainly; the refusals match the telling.

## Not checked

- Reviewer, security and milestone-review prompts were only scanned for tool names and blocks, not read claim by
  claim.
- The acceptance author's and scrum master's requests were not read in full.
- Hosted-model runs.
