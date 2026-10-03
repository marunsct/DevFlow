# Harness improvement plan

**What this is.** The one current plan for improving the harness. It replaces
`harness-hardening-plan.md` (Parts I–III, 2026-09-16 to 09-23) and
`harness-hardening-plan-part3.md` (2026-09-18), which were reviewed item by item
on 2026-10-04 against the code at `366fcf8`. Both originals stay in git history
(last present at the commit that deleted them); their item numbers (B1–B20,
Part III items 1–11, Part II items 17–30) are kept here so code comments that cite
them still resolve.

**The standard each item had to meet.** The harness exists to build any product
the way a software company does: in auto mode it makes every decision and review
itself and finishes development and testing; in approval mode it asks a person at
the points they chose and finishes on their review (`redesign-software-company.md`).
An item is kept only if it moves the harness toward that, by evidence from runs or
from the code. Where an existing implementation does not fit that vision, the item
replaces it rather than patching it.

**What changed since the old plans were written.** The redesign of 2026-10-03 made
a locked acceptance suite, written from the brief before anything is built, the
definition of done, and added stack packs, a CI gate, code review, a release gate,
decision records and an escalation ladder. Many old items were about giving
reviewers better evidence because nothing else decided whether a product worked.
A test now decides that, so those items matter less; items about stopping runs, or
about the model and the environment, matter as much as before.

---

## 1. Bugs from the earlier plans: status on 2026-10-04

Each was re-checked against the code, not taken from the plans' own status notes.

| item | what it said | status | evidence |
|---|---|---|---|
| B1 | cross-file checks are JavaScript-only | **open, low** | size counting covers ~40 suffixes; reference checks are still web/JS-centred. With a locked suite they are hints, not the verdict (`integration_checks._grade`) |
| B2 | role allowlists are a fixed table | fixed | `sandbox.allowed_executables` unions the toolchain of every language the stack names |
| B3 | timeouts are a four-entry table | fixed | `sandbox.timeout_for` scales by toolchain; a command that used its whole limit gets a short retry |
| B4 | server detection is a JS/Python word list | fixed | word list covers seven ecosystems; scripts are read for a listener; refusal gives pack-aware advice |
| B5 | scaffolding knows five layouts and is never called | superseded | stack packs (`app.stacks`) scaffold and prove every project; the old `app/scaffolding` package is dead code (R5) |
| B6 | line budget read from prose | fixed | `agents/brief_constraints.py` |
| B7 | `CHARS_PER_TOKEN` is a guess | open, low | now 3, still a constant; no run has failed on it since compaction landed (§3) |
| B8 | every OpenAI-compatible endpoint treated as llama.cpp | **open, now urgent** | `speaks_llama_cpp = bool(openai_base_url)`; the base URL also defaults to `localhost:1234` for provider `openai`, and a judgement model on another provider inherits the default model's address. Breaks the first hosted judgement model configured (R3) |
| B9 | reasoning delimiters not sanitised | fixed | `model_output.find_leaked_marker` refuses writes; `strip_reasoning` cleans answers |
| B10 | no text-embedded tool-call fallback | fixed | `agents/text_tool_calls.py` |
| B11 | event stream misses middleware notes | fixed | the transcript records `tool_result` post-middleware |
| B12 | reviewer findings not checked for stage appropriateness | **open, reframed** | an architecture review that never converges still fails the run outright, in auto mode too. Fixed by deciding instead of stopping (R2), not by a citation field |
| B13 | a restart discards what the stage learned | fixed | `agents/stage_memory.py` |
| B14 | gate ceilings are absolute counts | fixed for the server | the server's ceiling is `WORKFLOW_MAX_GATES` (1000); `MAX_GATES = 50` remains only in the CLI |
| B15 | digest truncates at 40 files | open, low | `MAX_FILES = 40`; every benchmark product is under it |
| B16 | ledger omits `working_directory` | fixed | part of the record and the repeat identity |
| B17 | "what is a test file" defined twice | fixed | `analysis/file_kinds.py` |
| B18, B19, B20 | runner validator, one-language stack pin, browser contradiction | fixed | `test_capability_agreement.py`; `pin_project_stack` is variadic |
| §4bm | a reply cut off while reasoning is retried unchanged | fixed | `thinking.answering_without_reasoning`; a stage that ran out twice is asked without reasoning from its first call |
| Part III 1 | coverage `omit` hides unwired modules | half fixed | per-file omit list and a caller test exist, but the test counts a mention in `tests/` as a caller, so modules only their tests import still pass (R5) |
| Part III 2 | `MetricsTracker` never called | fixed | `runner.py`, `sprint/__init__.py` |
| Part III 3 | cost tracker unregistered, rates fictional | fixed | `agent_stream.py` registers it per run; priced per provider |
| Part III 4 | `transcript_metrics` | built | used by `scripts/audit_run.py`; no runtime consumer is needed (§3) |
| Part III 5 | `deploy/` and `build/` unwired and insecure | **open** | ADR-0003 chose to wire the generators; their security defects were fixed, the wiring never was. Replaced by pack-owned release files (R4) |
| Part III 6 | no concurrency limit | fixed | `MAX_CONCURRENT_RUNS`, `CELERY_CONCURRENCY` |
| Part III 7 | cancellation cannot reach the agent loop | fixed | `_stop_if_cancelled` at every node, flag plus revoke |
| Part III 8 | no per-run cost ceiling | fixed | `MAX_RUN_COST_USD` parks the run naming the spend |
| Part III 9 | workspaces not segmented by tenant | fixed | `workspaces.allocate_workspace` |
| Part III 10, 11 | `cryptography` undeclared, `hvac` unused | fixed | `pyproject.toml` |
| Part II 17, 18, 26 | parse gate, project symbols, multi-language pin | fixed | `analysis/grammar_parse.py` (tree-sitter), `analysis/project_memory.py` |
| Part II 19–25, 27–30 | dependency probes, live docs, LSP, diagnostics gate | not built | see §3 |

**Found in this review, not in either plan:**

| bug | evidence | fix |
|---|---|---|
| Work orders target files the harness keeps | run-84832a29: the lead planned "Configure Playwright server" and "Update serve.mjs for reliable acceptance test execution" although its prompt forbids it; 16 refused edits of kept files and 19 refused attempts to run the kept server in one run | R1 |
| A sprint plan that "assigns nothing" fails the run even when the harness then assigns every criterion itself | `workflow.scrum_master_node` stops before `with_every_criterion_assigned` runs | R2 |

---

## 2. The revised plan

| item | state |
|---|---|
| R1 what the harness owns is enforced where the plan is made | done, `88356da` |
| R2 auto mode decides at the last two stopping points | done, `d12b138` |
| R3 a model endpoint is treated as what it is | done, `139cf0f` |
| R4 release files from the stack pack | done, `c9b5400` (ADR-0004) |
| R5 dead code removed and kept out | done, `05b01a3` |
| R6 `docs/` holds current documents only | done, with this file's commit |

Each is then judged by the benchmark gate (`benchmarks/README.md`), like every
other change: the improvement loop restarted on it.

### R1 — What the harness owns is enforced where the plan is made

**Why.** Class A of the old plan, measured again: a rule stated in a prompt does not
hold; a correction at the point of failure does. The lead is told that kept files
and the locked suite are not its to plan, and still writes work orders for them.
Each such work order is a specialist's whole stage spent on a file the harness
puts back.

**Change.**
- One answer to "who owns this path": `app.stacks.contract.owned_by_the_harness`
  (the harness's records, the test setup it keeps, the locked acceptance suite).
  The write guards, the definition of ready and the digest all use it.
- The definition of ready (`analysis/work_orders.readiness_problems`) sends a plan
  back when a work order names such a file, saying the fix belongs in the product.
- A plan dispatched anyway has those files taken off its work orders, so no
  specialist is told to change them.
- The workspace digest, which every stage reads on every call, marks those files
  as the harness's, where the agent actually looks.

**Test.** A work order naming a kept file or a locked test is not ready; the
dispatched plan does not name it; the digest marks it.

### R2 — Auto mode decides at the last two points where it still stops

**Why.** The vision is that auto mode finishes the work. Two stopping points remain
that a decision can replace:
1. An architecture review that is still not satisfied after
   `MAX_ARCHITECTURE_REVISIONS` fails the run (one stored run failed this way after
   six revisions). The acceptance suite, written from the brief, now decides whether
   the product works, so a specification with open review points is a risk to record,
   not a reason to stop.
2. A sprint plan that assigns none of the release's requirements fails the run,
   although the harness assigns every acceptance criterion to a sprint itself right
   after that check.

**Change.**
- Escalation (`graph/escalation.py`) learns a second kind of stuck point, the design.
  In auto mode it accepts the latest specification, records the unresolved findings
  as known risks in a decision record, and goes on to scaffold. In approval mode, when
  the escalation review is on, the person sees the findings and either approves or
  says what to change, which goes back to the architect with their guidance.
- The "assigns nothing" stop applies only when there are no acceptance criteria to
  assign. Otherwise the harness's own assignment stands, and is recorded.

**Test.** Exhausted design review → `escalation` → scaffold (auto) with a decision
record, or the review page (approval); a plan that assigns nothing continues when
criteria exist and still stops when none do.

### R3 — A model endpoint is treated as what it is

**Why.** B8, and it now has a deadline: choosing a judgement model is the owner's
open decision, and the obvious choice, a hosted model, is broken three ways today.
`chat_template_kwargs` is sent to every base URL (a hosted OpenAI endpoint rejects
unknown request fields); retries are turned off for every base URL (a hosted
endpoint's 429 then fails the stage); provider `openai` with no address calls
`localhost:1234`; and a judgement model on another provider inherits the default
model's address.

**Change.**
- `app.models.endpoints.is_self_hosted(base_url)`: loopback, private and link-local
  addresses, the Docker host aliases, single-label and `.local`/`.internal`/`.lan`
  names are self-hosted; anything else is hosted. `OPENAI_ENDPOINT_KIND` overrides it
  for the rare self-hosted server on a public name.
- The llama.cpp template switch and the no-retry policy apply to self-hosted
  servers only.
- Provider `openai` with no address uses the provider's own API; provider `local`
  keeps the LM Studio default.
- A judgement model whose provider differs from the default model's does not
  inherit the default model's address.

**Test.** One table of URLs and their kind; the client arguments for each kind; a
judgement model on provider `openai` with no address is built with none.

### R4 — The release carries the files to deploy and verify the product, from its pack

**Why.** A software company hands over something that can be built, tested and
deployed by someone who did not write it. ADR-0003 chose to ship deployment files
through three generic generators in `app/deploy`. They were made safe but never
wired, and wiring them as they are would be the wrong design: they hold a second,
unverified model of every stack (base images, start commands, test commands) beside
the stack packs, which hold the commands the harness has actually run.

**Change.** Each pack declares its release files, rendered from its own verified
commands:
- every pack: a CI workflow that installs and runs the same unit and acceptance
  commands the harness ran;
- service packs: a container definition (non-root user, dependency layer first, the
  pack's own start command) and an ignore file;
- written at the release stage, never over a file the product already has, and
  committed and listed in the release evidence. `app/deploy` is deleted
  (ADR-0004 supersedes ADR-0003).

**Test.** Every pack renders its release files; a container definition runs as a
non-root user and carries no default credential; the CI file runs the pack's own
commands; an existing product file is not overwritten.

### R5 — Dead code is removed, and stays out

**Why.** Unreachable modules mislead every reader: `tests/test_graph_routing.py`
monkeypatches the old scaffolder, which reads as though the graph called it.

**Change.** Delete `app/scaffolding` (replaced by `app.stacks`), `app/build/verifier.py`
(replaced by `app.ci`), `app/analysis/static_analyzer.py`, `app/tools/testing/runner.py`,
and `app/deploy` after R4. Add a module-level rule: every module under `src/app` is
imported by another module there, by a known entry point, or by a script, and
a test's import does not count.

### R6 — `docs/` holds current documents only

Delete the plans that are implemented or superseded, the documents of the product the
workflow was first built for, its templates (now `app/doc_templates`), run artifacts
that landed in this folder, and the session logs that git history already holds. Keep
the handovers, the redesign, the architecture decisions and this plan.

---

## 3. Not done, and what would bring each back

| item | why not now | what would justify it |
|---|---|---|
| B1 language analysers | the locked suite and the benchmarks' hidden tests decide whether a product works; cross-file checks are hints | a Python or Go benchmark run whose defect only a cross-file check would have found |
| B7 measured chars per token | no run has overflowed since compaction | a context-overflow failure on a model whose tokenizer differs |
| B15 digest by budget | every benchmark product has fewer than 40 files | a product past 40 files whose stages re-list the tree |
| B12 `check_reference` on findings | R2 removes the stop; severity of criterion findings is the owner's open decision | repeated design revisions on out-of-scope findings |
| Phase 1 full model profile | the parts that broke runs (window, reasoning effort, endpoint) are probed; R3 covers the server kind | a model switch that needs more than the model name and address |
| Phase 3 notice registry | a refactor with no measured change in outcome | a notice found missing from one tool of a set |
| Phase 4 cross-run learning store | agent-written memory shared across runs is a prompt-injection and drift risk; stack packs hold what was learned, deterministically, and this loop is the learning loop | — (dropped) |
| Part II 19–25 dependency probes, live documentation, LSP | needs network egress and credentials in the sandbox; packs pin versions the model knows | repeated failures from calling an API that does not exist in the installed version |
| Part II 28–30 diagnostics gate | the CI gate runs the tests after every batch, and the parse gate refuses broken writes | a type error that reaches a test round on a typed stack |
| Task list middleware | built and switched off (old §4au); no measurement favours it | a measured win in five paired runs |

## 4. Method to keep

- Re-verify an item against the code before implementing it; a plan's status notes
  age faster than the code.
- Enforce a rule where it is broken, with a message that names the fix; a prompt is
  documentation.
- Define a rule once over the set it governs, with a test that the set is complete.
- Judge every item by what runs measure: the benchmark gate in `benchmarks/README.md`.
