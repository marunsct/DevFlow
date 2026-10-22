# Monitoring handover - sections before 2026-10-14

Moved from `docs/monitoring-handover.md` on 2026-10-21 (plan MF.6): run narratives older than a week.
Nothing here is current; `docs/STATE.md` is.

### 0.6 Removed on 2026-09-29

`scratch/` (`check_run.py`, `get_run_logs.py`, `get_runs.py`,
`resume_run.py`, `run_monitor.py`, `start_run_api.py`, `run_logs.json`,
`worker.log`) and the root-level `audit_output.txt`. They logged in as
`admin`/`dev`, named fixed run ids and the old `langchain_auth` database, and
carried plain-text credentials; everything they did is covered by
`scripts/loop/`. **Those credentials remain in git history and should be
treated as exposed and rotated.**

### 0.7 How a sprint runs now (work orders, templates, the Sprint Record) - 2026-09-30

Built at the operator's request, modelled on how a software team hands work to a
developer who is new to the codebase. The loop was paused for it; audit the next
runs against this section.

**Every document comes from a template.** `src/app/doc_templates/templates/*.md.j2`
holds one Jinja template per workflow document (the nine in `docs/`, the sprint
summary, the stage summaries). A model supplies the content of each section; the
template fixes the headings, their order, the labels inside a record and what an
empty section says, so a different model produces the same document shape.
`tests/test_document_templates.py` fails if a schema field is not placed in its
template or if the heading skeleton varies with the content. The sprint panel in
the UI parses `sprint_N_summary.md`; its template's header comment says which
lines must not change.

**The technical lead writes work orders.** `SpecialistTask` now carries `title`,
`files`, `interfaces`, `steps`, `edge_cases`, `test_cases`, `verification` and
`out_of_scope`. The lead is given the specification's contract sections to copy
from. Each specialist's brief shows its own work order; the `testing` specialist
also gets every other work order's interfaces and test cases and writes the tests
against them while the code is written (contract first).

**Definition of ready** (`app.analysis.work_orders.readiness_problems`), checked
before dispatch: a code work order with no `files` or no `test_cases`, a file
outside the pinned project directory or in `docs/`, code with no `testing` work
order, a `verification` command the sandbox refuses, or carried-forward items with
no `carried_forward_decisions`. An unready plan goes back to the lead once with the
list and the plan it was (log line: "Milestone plan is not ready to hand out");
after the retry budget it is dispatched with the problems in `integration_notes`.
`WORKFLOW_WORK_ORDER_READINESS=off` disables it - only the test suite does that.
Commands a task names are also checked against the sandbox and a refusal is
written onto the task (`app.analysis.planned_commands`).

**Definition of done** (`app.sprint.record.definition_of_done_gaps`), checked when
the milestone review accepts: every work order returned a result and no tracked
defect is open. A gap sends the sprint back (bounded by `MAX_MILESTONE_REVISIONS`,
then escalates) - the next sprint never starts on an unfinished one.

**The Sprint Record** (`docs/sprint_N_summary.md`) keeps the old header, test
counts, "Planned", "Features Implemented" (task titles now) and "Defect Summary",
and adds: Work Orders (outcome, files planned vs changed, verification, blockers),
Defect Log (reproduction, expected/actual, how it was fixed, what verified it,
regression test), Review Findings (every round of the milestone and security
reviews, with a disposition), Carried Forward, and Lessons for the Next Sprint.
Everything in it comes from state, the execution ledger and the transcript, not
from an agent's account.

**Carry-forward and lessons.** Non-blocking findings from a sprint's last review
round are handed to the next sprint's lead, who must take or decline each in
`carried_forward_decisions`. Tool failures repeated in a sprint (from the
transcript) are handed on as lessons. Both reach the lead's request under
"Carried forward from earlier sprints" and "What went wrong earlier in this run".

**What to audit on the next runs:** does the lead fill the work-order fields (read
`docs/milestone_plan.md` - "not stated" everywhere means it did not); how often
the readiness check bounces a plan and whether the second plan fixes it; whether
specialists follow their work orders (fewer refused commands, fewer files outside
`files`); whether the Sprint Record's dispositions and carried items match what
the reviews said; and whether a carried item is actually taken in the next sprint.

**The intake keeps the brief's acceptance criteria** (19c5033). They join the
success measures verbatim, a comma list without "and" counts as a list, and a
deferred item naming (whole word) a capability the brief's own acceptance
criteria require is marked `(the brief requires X: "..." - only what goes
beyond that is deferred)`; nothing is removed. Audit `docs/product_intake.md`
first on every run: nothing the brief's acceptance criteria require may appear
unmarked under Deferred scope, nor as an exclusion in the specification's
Product Scope (run-557346a2 deferred "Task editing" for "Users can add, edit,
delete tasks"). Also check the marks are right: a mark on an unrelated item
means the matching is too loose again.

---

### 0.8 What the model is given (review of 2026-09-30, commits 6719aec..15a6241)

A review of 23 runs (2,604 tool calls) found most of the struggle was context,
not capability: 26% of calls repeated a read/list/search the stage had already
made, and failed calls were led by missing files, answers written to files and
line-number edits. What changed, and what to audit on the next runs:

- **Locked dependencies.** Both images install `uv.lock` exactly (`uv export
  --frozen`); production had been running 38 packages the suite never saw,
  including deepagents 0.7.20, whose `read_file` has no line numbers. Check
  after any deploy: `docker exec langchain-worker-1 python -c "import
  importlib.metadata as m; print(m.version('deepagents'))"` equals the lock.
- **Reasoning carried across tool calls** (`app.models.with_the_reasoning_carried`):
  the tail of each of the last four tool-calling replies' reasoning is sent back
  in that reply's `content` (LM Studio ignores every reasoning field). Audit:
  the repeated-identical-call share should fall well below 26%.
- **Tools**: `inspect_repository` and `read_repository_file` removed from role
  agents; the answer tool's description now says it is the only way to finish.
  Audit: "answer saved as a file" refusals.
- **Prompts**: writing rules ~9,100 -> ~5,000 chars, testing rules halved, a
  framework block shared by several seeded modules injected once; generated
  framework notes now describe the tool, not the product, and rows generated
  under the old prompt are regenerated. Specialist system prompt ~25,300 ->
  ~12,500 chars before framework notes.
- **Saved models** (settings page): every applied model configuration is kept
  and can be picked again; credentials are never stored with it.
- **Model settings are the operator's.** The review found gpt-oss-20b loaded
  with 10 experts per token (trained with 4). The loaded model and
  `runtime_settings.model_name` must agree before a run starts - check
  `/v1/models` on the model server; do not start a run while they differ, or
  LM Studio either refuses it or unloads the operator's model to serve it.

### 0.9 Why a run takes ~3 hours (review of 2026-10-01, run-482cd03b)

163 minutes for a 347-line app: 1,024 model calls, 950 tool calls. The model
is busy 98% of the wall clock; tools 2%, idle ~0%. Measure a run with
`loop.sh timing [run-id]` (per phase, per stage family, model vs tool time,
reasoning share, how far model calls overlapped) and LM
Studio's `print_timing` lines (`prompt eval time = ... / N tokens` is the
part of the prompt re-read; `f_keep` is the share of the cache kept).

- 91% of output tokens are reasoning (838k of 918k). gpt-oss at its default
  effort reasons ~1,000 tokens before each tool call; "low" measured 6-25x less
  on a probe. Effort is the operator's setting - propose an A/B, do not change it.
- The first reasoning carry-over (last 4 replies) re-wrote the prompt 4 replies
  back every call: median 6,390 prompt tokens re-read per request vs 1,068
  before, 44 min a run vs 6. Now append-only, per OpenAI's gpt-oss guidance
  (keep analysis since the last final message). Check `f_keep` stays ~0.9.
- 82% of tool calls look (read/ls/glob/grep), 8% write. `ui.js` was read 60
  times across 27 stages; every stage starts fresh on a ~10-file product.
- Parallel mode overlaps model calls only 1.0-1.3x (>1 in flight 13-28% of
  specialist time): every gated write/command pauses and pauses drain one per
  superstep. LM Studio's 8 slots go unused.
- The lead spends ~37 min a run: one huge structured plan, 94% reasoning, the
  25k ceiling hit almost every run.
- Verification is the biggest phase (62 min: 7 test rounds, 6 defect fixes).

Implemented after a self-review the owner asked for: the whole small product in
each stage's opening request (`app.agents.project_snapshot`), and, instead of
approving in-line, every queued parallel pause answered in one resume under
auto-approve (`queued_parallel_pauses`, `_GateCount`) - linear and attended runs
never have a queued pause and are unchanged. Not implemented: two-step lead
planning (measure first), per-role reasoning effort (the operator's setting -
an A/B with thinking mode on / effort low needs no code), one sprint for a
small brief (sprints and the Sprint Record are the product's design).

**2026-10-08: why runs went from 1-3 hours to 5-8.** From 2026-10-07 the
owner's model was `qwen3.6-35b-a3b-mtp`, with 2,100-3,700 output tokens and
19-32 s per call. gpt-oss-20b runs at 400-840 tokens and 5-8 s. Thinking stayed
on, and sprints now really are sprints: the scope fixes keep each sprint to
its own criteria, so there are more rounds. Back on gpt-oss-20b (since 14:12
JST, 2026-10-08), expect calls about 4× faster. The thinking budget remains the
owner's decision and the biggest lever.

**2026-10-10: run-b30deacb-081d-4ce5-b10c-c6bc39f6b25b early stop & empirical post-mortem (24 min wall clock).**
Started at 11:42 JST on 2026-10-10, caught and failed at 12:06 JST (24 min).
- Outcome: Acceptance suite failed to run with `ENOENT: Could not read package.json` (exit 254) in rounds 1-5.
- Root cause: Premature contract inference in architecture stages. `contract.the_pack()` ran during workspace file checks in `principal_architect` and `architecture_review`, triggering `_infer_contract()` which persisted `.harness/stack-pack.json` to disk before the `scaffold` node ran. When the `scaffold` node ran in `src/app/graph/acceptance_nodes.py`, `if pack is not None and contract.read(root) is None:` evaluated to false because `.harness/stack-pack.json` already existed. Scaffolding was completely skipped, leaving `simple-to-do-list-app/` with no `package.json`, `index.html`, or dependencies.
- Fix: In `src/app/graph/acceptance_nodes.py`, replaced the flawed `contract.read(root) is None` gate with `already_done = bool((state.get("scaffold_result") or {}).get("ok"))` and `if pack is not None and not already_done:`.
- Verified by `tests/test_scaffold_not_skipped_by_inferred_contract.py` (proven failing on old code, 1/1 passed, zero banned words, zero run IDs).

---

### 0.10 How a product is tested now (2026-10-04)

`docs/PRODUCT.md` describes the whole product; this is what a monitor needs to
know about its testing, and what changed most recently.

- **A stack pack scaffolds every project and keeps its test setup**
  (`src/app/stacks/packs/`). For `browser-javascript`: `playwright.config.js`,
  `playwright.setup.mjs` (the page check), `test-setup.mjs` (a jsdom page for
  unit tests), `scripts/serve.mjs`, and the manifest scripts `start`, `test`,
  `test:acceptance`. Agents are refused writes to them and the workspace digest
  labels them "the project's test commands run it". The scaffold proves itself
  with two smoke tests before any agent writes. A pack scaffold that cannot be
  proven is retried whole once and then stops the run at an escalation
  (2026-10-18, Initiative J.1) - it no longer continues "left to the agents";
  stacks no pack covers keep that documented escape.
- **Acceptance suite.** Written by QA from the criteria, then locked
  (`acceptance/`); the harness runs it every round. A failing test carries what
  the page showed when it failed, and - when nothing on the page matches its
  locator but something differs only in case, punctuation or role - a
  "Nearly there" line naming it (`near_misses` in the JavaScript packs). The
  page check records uncaught errors, console errors, failed requests and HTTP
  errors on load (`test-results/page-load.json`).
- **One-off scripts.** Code on the command line (`node -e`, `python -c`) is
  refused; the refusal says to put it in a file named `tmp-<what it checks>`.
  Files named as throwaways (`file_kinds.is_scratch`) that a stage created and
  nothing references are swept before every test round and at release; any
  other name is taken for the product and ships.
- **Unit tests** use the pack's runner. In `browser-javascript`, `npm test` is
  `node --import ./test-setup.mjs --test ... tests/`, so every test file has
  `document`, `window`, `localStorage` and the page's own `Event`/`FormData`
  classes (jsdom 26.1.0 - the last release for the image's Node 20). One file:
  `node --import ./test-setup.mjs --test tests/<module>.test.js`; a bare
  `node --test` skips the page. A test that builds a page of its own is told to
  use the one it has, and refused on the third time in a stage. `browser-react`
  gets the same from Vitest's jsdom environment.
- **Instructions follow the pack.** Seed rows `<key>:setup` (how to install and
  configure runners) are left out where a pack set the project up, and so are
  the stack block's rules for projects that set themselves up (one command
  running both suites, the module-system choice).
- **IDE-grade checks.** The TypeScript language service (JavaScript/TypeScript)
  and Pyright (Python) report names nothing defines, missing exports and
  imports, and use before declaration: a note on every write, a defect at the
  CI gate once the batch is done.
- **CI gate.** Regressions are measured against both the last accepted state
  and the last measurement; a fix that breaks a passing test is reverted; code
  review runs on each batch.
- **A suite that proved nothing is not green (2026-10-18, Initiative J.1).**
  `suite.vacuous_green` names the results that prove nothing while every count
  reads green: a runner that reported zero tests, a run whose tests name no
  criterion, or a declared test the runner never collected. These are never
  waivable: the acceptance review refuses to lock while one stands (and fails
  the run after the last round instead of locking with it open), a test round
  treats one as the suite's defect to repair, and a release is held back even
  when every criterion is deferred or passing. Before this, a round count
  waived them at lock time and a release only asked whether a criterion was
  failing - the path by which runs shipped at hidden-test 1/10.
- **A completed run carries what it did not prove (2026-10-18, Initiative
  J.4/J.5).** The release records `completion_gaps` - deferred criteria,
  problems the suite was locked with, plan problems noted at dispatch, an
  unproven setup, no locked suite at all - and every record shows them: the
  runs row (new column, migrated), the release decision's rationale, the
  release-evidence page (a "Completion gaps" section), the run dashboard
  (amber panel beside the green badge), the outcomes dashboard row, and
  `loop.sh score`'s export (`data/bench/<run>.json` and
  `<data>/outcomes/<run>.json` both carry `completion_gaps`; the score script
  takes them as its fifth argument, so an old database answers empty). A
  completed run with gaps is never plain "completed" on any surface.
- **Every stage is told the environment it runs in (2026-10-18, Initiative
  K.1).** The sandbox truth - the commands the allowlist permits, the browser
  facts, no network, nothing running, containers written-but-not-built,
  installs must land where the product's own commands read - used to reach
  only the stack selector. It is now one derived, byte-stable block
  (`app.agents.environment_contract`) appended to every role agent's calls
  ahead of the workspace digest, so the architect cannot specify a database
  server that does not exist and a fixer cannot loop on installs that land
  nowhere. `ENVIRONMENT_CONTRACT=0` switches it off.
- **A defect is re-measured before a fixer is spawned (2026-10-18, Initiative
  L.3).** The queue a test round writes is stale by dispatch time - sixteen
  defects a day were closed "already fixed" from stored measurements, and nine
  fixer stages were named and stood down. When no stored measurement settles a
  defect, dispatch now runs its own tests (`_the_defect_s_tests_pass`, the same
  per-file acceptance probe the post-fix check uses); a green probe closes the
  defect with a `closed without a fixer` ledger note and no model call, a probe
  that cannot answer dispatches the fixer as before. The cheaper stored answers
  still come first.
- **A fix closes on its own tests, measured (2026-10-18, Initiative AD).**
  Settlement used to mark a fix that broke nothing as fixed when the fixer
  named a test. `after_a_fix` has already run both suites, so settlement now
  reads the defect's own tests (its criteria's acceptance tests, else the unit
  tests) from that snapshot: red leaves it open with a `left open ... its own
  tests still fail, measured after the fix` ledger note and counts the failed
  attempt at once. No extra test run.
- **One list of tests that cannot pass (2026-10-18, Initiative AE).** The
  review and every test round use `suite.tests_that_cannot_pass`; the
  too-lenient checks stay review-only. Release adds three gap sources:
  escalation `known_issues`, fast-mode findings recorded as risks, and a
  release re-read of the files (`problems_that_break_the_product`).
- **New bounds and checks (2026-10-18, AH).** `MAX_RUN_TOKENS` (empty: none)
  pauses a run at a stage boundary once it has used that many tokens, priced
  or not. `loop.sh ready` also prints `READY commands (...)`. A judgement
  model that could not be built is a completion gap at release.
- **Deploys wait for a stage boundary (2026-10-18).** `loop.sh deploy` builds,
  then waits up to `BOUNDARY_WAIT` seconds (default 1800; 0 skips) for the
  live run's transcript to name a new stage, then the call gate. A resume
  restarts the running stage's conversation, so mid-stage deploys cost the
  stage its progress.
- **The server bounds the run (2026-10-18, M.1/O.2/AB).** Each run segment
  reads `/props` once (worker log: "Model server: N slot(s), T tokens per
  slot"). The context window is no larger than a slot's context, and each
  fan-out wave no wider than the slots. On the owner's 1-slot, 126k server
  nothing changes in the window; parallel waves go one at a time.
- **Prefix-cache layout (2026-10-18, AA/O.3).** Project memory is taken once per
  stage visit and kept byte for byte; a "[Project memory update]" note at the
  end names files changed since. The environment contract is in the system
  prompt. Expect the KPI `cached_token_share` to rise; compare with the ledger.
- **Code the product does not run is named (2026-10-18).** A folder that
  repeats two or more paths of a served entrypoint's folder (a drafted
  `frontend/src/` beside the served `src/`), and unit tests whose files and
  `conftest.py` never name the served folder, are listed in every fix request
  ("Code the product does not run") and as completion gaps
  (`scaffold.code_the_product_does_not_run`). Measured on the medium run: both
  were true, and a fix rewrote a migration file nothing ran.
- **Project-memory pointers count toward the read rung (2026-10-18).** Eight
  reads answered "is in the project memory at the start of this conversation"
  withhold the read tool for the rest of the stage, like three refusals (one
  testing stage spent ~35 of 70 calls cycling read batch -> stall -> one write).
  The audits (`audit_live.py`, `kpi.py`) now count those pointers as redundant
  reads, so the redundant-read rate reads higher than before for the same
  behaviour.
- **Each run's KPIs are kept (2026-10-18, Initiative W.4/W.1).** `loop.sh kpi
  [run]` writes `data/kpi/<run>.json` and a row of `data/kpi/ledger.csv` and
  prints `REGRESSION ...` for any rate past 1.5x its 5-run mean; `loop.sh
  score` runs it after scoring. A score is `brief_mismatch` when the run's
  uploaded brief is not byte-identical to `benchmarks/<name>/brief.md`, and
  such a score is never a false acceptance. The harness switches (LINE_EDITS,
  ENVIRONMENT_CONTRACT, WORKSPACE_DIGEST, PROJECT_MEMORY, HARNESS_TASK_LIST,
  ESCALATE_AFTER_ATTEMPTS) now reach the worker from
  `.env` (W.3), so A/B runs are possible without editing compose.
- **Prompts match tools and routing (2026-10-18, Initiative X).** A suite test
  builds every role agent and fails if its prompt names a tool it is not
  offered; the milestone review's `blocked` text now says the sprint is
  planned again (the owner's sprint re-run), not that the run ends.
- **A stage circling identical calls ends deterministically (2026-10-18,
  Initiative L.5).** Twelve identical calls that returned nothing new - counted
  from the read-refusal, same-answer and identical-failure markers in the stage's
  own conversation - end the stage with no answer written, instead of spending
  the rest of its budget on refusal turns (budget warnings ran 47 in a day). The
  stop is marked `NO_PROGRESS_MARKER` beside the budget marker, so recovery
  skips the nudge and retries on a fresh conversation; a stage that already
  wrote its answer is left to finish.
- **The last permitted fix attempt changes strategy (2026-10-18, Initiative
  L.6).** Once a defect has failed `escalate_after()` fixes, its work order says
  so and changes shape: rewrite the implicated files whole rather than patching
  lines, with a named blocker as the way out when the specification itself
  cannot produce a passing file - not a third variation of the instruction that
  failed twice.
- **A phantom write claim costs no model call (2026-10-18, Initiative Q.4).** A
  stage answer naming files nothing in it wrote used to be sent one full model
  call of clarification (×11/day) - and two measured stages named the same file
  again. The claim is now dropped from the record deterministically against the
  conversation's write receipts; the warning "claimed N file(s) nothing in it
  wrote ... dropped from the record" is the line to count for the per-model
  claim rate when U.2's KPI ledger lands.
- **A locked test is not reclassified on the QA lead's word alone (2026-10-18,
  Initiative J.2).** Before the suite reopens for a test the dispute stage
  calls unpassable, the harness re-measures it: its own file, run alone
  against the delivered surface in the project's own runner, no model in the
  loop. A test that passes alone stays locked ("Disputed test(s) ... pass when
  run alone"). And a run may reclassify at most max(2, a tenth of the locked
  suite) tests through its disputes - past the cap the tests stay failing
  ("past this run's reclassification cap"). Every reclassification is tracked
  (`suite_reclassified_tests`) and named in the release's completion gaps.
- **The workspace says so when a run did not deliver (2026-10-18, Initiative
  J.6).** Every terminal state but a clean release - failed, cancelled,
  completed with gaps - writes `NON-DELIVERABLE.json` into the workspace root
  (status, reason, gaps, timestamp), and a clean release clears it. The run
  status API reports what it says (`non_deliverable`) and the run dashboard
  shows it in a red panel beside the badge. The sweeper also learned the two
  stage-note names measured shipping inside stored products: `blocker.txt`
  and `verification.log` are throwaways now.
- **An import no manifest declares is one bundled defect (2026-10-18,
  Initiative K.4).** At the CI gate, once the batch is done, the harness
  reconciles the code's third-party imports against the manifests
  (`package.json`; `requirements*.txt`/`pyproject.toml`) and bundles every
  gap into a single defect for the fixer - the jsdom class, where a bare
  install had landed the package somewhere a clean `npm ci` never reads.
  The warning "The CI gate found N package(s) the code imports that no
  manifest declares" is the line to count when U.2's KPI ledger lands.
- **A served app that is still the scaffold's stub is named as such
  (2026-10-18, Initiative K.3).** The packs that serve declare the file
  their drafted routes live in (`entrypoint`); the harness's own measurement
  rounds compare it byte for byte against the scaffold's stub, and while it
  is unchanged one bundled defect says "The served app is still the
  scaffold's stub" instead of 31 failing criteria saying nothing about the
  wiring. This was the dominant live failure: the suite ran against the stub
  while everything drafted sat in files nothing served.
- **A sandbox install lands where the product reads (2026-10-18, Initiative
  K.5).** The project's virtualenv - found through the contract record, the
  same `.venv/bin` the pack's commands use - now goes in front of every
  sandbox command's PATH. A bare `pip install` used to land in the system
  environment while a Python pack serves through `.venv/bin/python`: the
  contract said installs must land where the product's commands read, and the
  sandbox contradicted it. Now it does not.
- **A reverted fix goes to the judgement model next (2026-10-18, Initiative
  L.4).** The revert is the proven failure signal, so the attempt after it
  does not wait for the generic two-failure rung: one revert note on a
  defect's record escalates its next fix to the judgement model ("the fix it
  retries was reverted once" in the log). A second revert reaches the generic
  rung on its own, so this escalates at most once per defect - the cap that
  protects cost. Both reverted fixes in the live run came from the local
  build model; its fixes and reviews are the measured weak link.

**Watch on the next runs:** unit-test churn on page code (five web-todo runs in
a row before `80e97e7`; should now be gone); probes named like the product
(`src/import-ui.mjs` in run-5cfba2c8, beside twelve `tmp-*` ones the sweep
handles) - the refusal now names the throwaway form; fix rounds that circle a
locked test whose locator nearly matches the page (six stages in run-5cfba2c8;
the "Nearly there" line should end it); agents adding their own scripts to
the manifest; a fullstack run churning on unit tests of its page
code (`fullstack-node` has no unit DOM yet; see
`docs/improvement-plan.md` §3).

