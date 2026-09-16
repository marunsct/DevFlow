# Harness Hardening Plan

**Goal.** Make this multi-agent product-development harness work with any model from a 7B local GGUF to a frontier API, and build any product in any technology — and make it improve itself from its own runs.

**Basis.** Findings 45–93 of the current session (31 runs, five models: gpt-oss-20b, Qwen3.5-9B, Qwen2.5-Coder-7B, North-Mini-Code-1.0, plus earlier runs on the original model) and a targeted read of the code. Every bug below is tagged **verified** (read in the code or measured in a run) or **inferred** (a pattern the evidence predicts but no run has yet hit). Run 42 is deliberately *not* used here; it is left for a separate diagnosis.

---

## 1. What the findings taught: eight root-cause classes

Ninety-three findings look like ninety-three bugs. They are eight designs, each of which fails the same way whenever a new model or stack exercises it. Fixing the design retires the whole class.

### A. Guidance loses; corrections win
A rule stated in a prompt does not change behaviour. A correction delivered *in the result of the call that broke the rule* does — on the very next call, repeatedly, across models.

| rule, where stated | outcome |
|---|---|
| "Maximum 500 lines of code" — brief, intake, spec (6 mentions) | exceeded on 4 runs; 671 → 859 lines *after* a blocking review (finding 88) |
| "The workspace is rooted at '/'" — every brief | `/workspace/…` invented 18× in one run (91); `/docs/docs/` doubled every run (61) |
| "'Manual browser testing' cannot be carried out here" — stack prompt | chosen anyway until a validator refused it |
| "Pass the command as a list, not a string" — tool docstring | `["wc -l", …]` (84) |

**Design rule:** every constraint that matters must be enforced by a check that fires at the point of failure and names the fix. Prompt text is documentation for humans.

### B. A check that reaches twelve of thirteen
The codebase's own tests describe this as "the mistake this codebase has made four times". It is now at least seven:

- `node` added to `ui_ux`, then `backend`, then `testing`, then `database` — one role per run (82)
- repeat-read notice on `read_file` but not `ls`/`grep`/`glob` (86)
- "already failed" note but no "already passed" (76) and no "already refused" (77)
- budget checked at review but not at write (88)
- step-budget warning log line shared with the schema-failure line (81)

**Design rule:** a notice, allowlist or guard is defined once over the *set* it applies to, and a test asserts the set is complete. Never add the missing member; add the rule that generates all members.

### C. Constants measured on one model
| constant | measured on | broke on |
|---|---|---|
| `MIN_EXPECTED_TOKENS_PER_SECOND = 40` | Qwen3.5-9B (40.9) | North-Mini-Code (33.0) → timeout became a length limit (90) |
| `DEFAULT_REQUEST_TIMEOUT_SECONDS = 300` | "twice the longest call" on the original model | wedges *and* long answers (79, 89) |
| `INNER_AGENT_RECURSION_LIMIT = 60` | "twice the longest healthy stage across fourteen runs" | its own docstring says "measured against a different model and no longer true" |
| `BUDGET_WARNING_FRACTION = 0.7` of 60 | — | applied to the wrong unit (85) |

**Design rule:** anything that depends on the model — rate, window, tool-call format, thinking delimiters, structured-output mode — is *measured at startup* and stored, not typed into source.

### D. Unit mismatches
Supersteps vs AI messages (85); a total timeout vs a per-read timeout (79); "lines" counted with vs without tests (92). Each produced a threshold that could not fire when needed.

### E. Keyed on the request, not the response
The repeat notice keyed on `path|args`; the model varied the spelling and the range and defeated it (80). The command ledger keyed on argv without `working_directory` (68, and again on run 41). The right key is *what came back* — bytes, exit status — plus the identity of what it came from.

### F. Feedback at the wrong time
The budget check ran at review, one full cycle after the write (88). The line count, the orphan check, the cross-file checks all run after a specialist has finished. A specialist that learns at the moment the file lands fixes it for free; one that learns from a reviewer costs a re-plan, a re-delegation and a rewrite.

### G. Model-format leakage
- `<|END_THINKING|><|START_ACTION|>` written into a source file, breaking a 963-line suite the model could not see was broken (93)
- tool calls emitted as `<tools>…</tools>` *text*, invisible to the harness (run 40)
- a trailing `</tool_call>` on structured answers (run 31)
- JSON answers written into prose documents (existing guard)
- streaming default that killed every run because the agent path differs from a bare model (79 regression)

**Design rule:** the harness never trusts model output to be in the format it asked for. One sanitiser, one fallback parser, both driven by what the startup probe observed.

### H. Technology assumptions baked in
Ninety mentions of node/npm/jest/python across `sandbox.py`; the cross-file checks understand HTML, CSS and ESM JavaScript and nothing else; the scaffolding registry knows five layouts; the server-command list is JS and Python. A Go, Rust, Java, .NET, Ruby or PHP product would get no build, no tests, no size count and no cross-file review.

---

## 2. Bugs found in code review (open)

Ordered by impact. Each names the file, the evidence, and the fix.

### B1 — Cross-file checks are JavaScript-only  *(verified)*
`src/app/analysis/integration_checks.py`: `_dangling_class_selectors`, `_dangling_id_selectors`, `_orphaned_scripts`, `_module_system_mismatch`, `_application_embedded_in_html`, `_redefined_instead_of_imported` all parse HTML/CSS/ESM. `_COUNTED_SUFFIXES` (line 772) is `{html, htm, css, js, mjs, cjs, ts, tsx, jsx, py}`. A product in any other language is invisible to the reviewer's evidence and uncounted against its budget — so the milestone review, which has blocked correctly on every JS product, would accept anything.
**Fix:** a `LanguageAnalyser` protocol (`counts`, `references`, `entry_points`, `test_files`) with per-language implementations registered by suffix; the existing JS/HTML code becomes the first implementation. A generic analyser (line count, comment stripping by a table, "file referenced by nothing" via grep) covers every language on day one.

### B2 — Per-role executable allowlists are a fixed table  *(verified)*
`sandbox.py:53` `ROLE_EXECUTABLES`. `go` and `cargo` appear only under `backend`; `dotnet`, `java`, `mvn`, `gradle`, `ruby`, `bundle`, `php`, `composer`, `swift`, `dart`, `flutter` appear nowhere. Finding 82 was the fourth one-role fix; the table guarantees a fifth.
**Fix:** derive the allowlist from the stack the stack selector chose (`technology_stack.language`, `framework`, `testing_framework`) — runtime, package manager and test runner for *every* code-writing role — plus a small per-role extra set. Keep `_FORBIDDEN_ARGS` as the generic interpreter-escape blocklist and extend it per interpreter (`ruby -e`, `php -r`, `dotnet script`).

### B3 — Command timeouts are a fixed four-entry table  *(verified)*
`sandbox.py:195` `TIMEOUTS = {"install": 300, "build": 180, "test": 300, "default": 120}`, category chosen by the model. A Rust, Java or Android build routinely exceeds 180s; a first `npm install` on a slow link exceeds 300s. The ledger already records every command's wall time.
**Fix:** per-(stack, category) timeout = max(table floor, p95 of the ledger's successful durations × 2). Refuse a category the model chose that contradicts the executable (`node --test` as `install`).

### B4 — Server detection is a JS/Python word list  *(verified)*
`sandbox.py:636` `_SERVER_COMMANDS`, `_SERVER_MODULES`. `rails s`, `flask run`, `uvicorn`, `dotnet run`, `go run` of an HTTP main, `php -S` are not detected; the call sits until the timeout and returns nothing, then the agent retries it (the pattern that cost run-e9e7f48f).
**Fix:** behavioural detection — a process still alive at 20s with a listening socket in its namespace is a server; kill it, return the port and the first stdout, and say so. Keep the word list as the fast path.

### B5 — Scaffolding knows five layouts  *(verified)*
`scaffolding/registry.py`: vite-react-ts, nest, next, and two `mkdir`-based Python layouts. Any other stack has no scaffold path and the architect improvises a layout the checks do not recognise.
**Fix:** for an unknown stack, scaffold an empty project with the layout the architect declared in `docs/technical_specification.md` (`src/`, `tests/`, manifest) and pin it — the harness's own layout rules then apply.

### B6 — The line budget is read from prose by regex  *(verified)*
`integration_checks.py:818` `_DECLARED_BUDGET` finds "N lines" in any `.md`. A brief with no cap is silently unbudgeted; a cap in files or kilobytes is missed; "500 lines" in an unrelated sentence becomes the cap ("most frequent number wins").
**Fix:** the product manager's structured output gains a `constraints` object (`max_code_lines`, `max_files`, `max_dependencies`, …) filled from the brief; the checks read that, and the regex becomes the fallback with a log line saying so.

### B7 — Token budgets are a `CHARS_PER_TOKEN = 4` guess  *(verified)*
`context_budget.py:61`. Code, JSON and non-Latin text run 2.5–3.5 chars/token; the budgets over-fill the window on exactly the content this harness handles most. `usage_metadata.input_tokens` is returned on every call and never read back.
**Fix:** measure `chars / input_tokens` over the first ten calls of a run and re-derive the budgets; persist the ratio per model (see §4).

### B8 — Every OpenAI-compatible endpoint is treated as llama.cpp  *(verified)*
`models/__init__.py:300` `speaks_llama_cpp = bool(openai_base_url)`. LM Studio, vLLM, Ollama and llama.cpp differ in thinking flags, tool-call parsing and `response_format` support; this session hit two of those differences (runs 40, 41).
**Fix:** the startup probe (§3.1) identifies the server from `/v1/models` metadata and behaviour, not from the presence of a URL.

### B9 — Reasoning delimiters are not sanitised  *(verified, partial)*
Finding 93 refuses `<|name|>` tokens. `<think>…</think>` (DeepSeek-R1, Qwen3 thinking mode), `<reasoning>`, and `<tools>` wrappers are not covered by any write guard or answer parser. `thinking.py` handles the *request* side only.
**Fix:** one `sanitise_model_output(text, profile)` used by `write_artifact`, `edit_artifact` and `settled_answer._answer_in`, with the delimiter set taken from the probe.

### B10 — No fallback for text-embedded tool calls  *(verified — run 40)*
Qwen2.5-Coder via LM Studio emitted `<tools>{"name": …}</tools>` as content with `tool_calls: None`. The harness has no parser for it, so the run crawled forward on answer recovery alone and never wrote a file.
**Fix:** a `wrap_model_call` middleware that, when the probe flagged the model as text-tool-calling, parses `<tools>`, `<tool_call>` and fenced-JSON call blocks into `tool_calls`. Off by default; on only when the probe proves it necessary.

### B11 — The event stream cannot see middleware notes  *(verified)*
Events record tool output as the tool produced it; anything `wrap_tool_call` appends reaches the model but not the record. Findings 86–87 were mis-measured because of this until a live agent was driven directly.
**Fix:** emit the post-middleware `ToolMessage` to the event stream (one line in the tool-result callback). Without this the self-learning loop in §4 would learn from wrong data.

### B12 — Reviewer findings are not checked for stage appropriateness  *(verified — run 42 error text)*
The architecture reviewer rejected a *specification* six times for lacking "class constructors, public method contracts, exact DOM elements where `escapeHtml` must be called" — implementation detail a spec should not contain — until `MAX_ARCHITECTURE_REVISIONS` failed the run.
**Fix:** each reviewer's schema gains `check_reference: str | None` — the harness check or acceptance criterion that produced the finding. A finding with no reference is capped at `minor` and cannot block; a finding demanding content outside the stage's declared scope is rejected by a validator with a message naming the stage that owns it.

### B13 — A stage restart discards everything the stage learned  *(verified)*
`workflow.py:947` says so in its own comment. Three attempts each re-read the same files and re-run the same commands (run-37476645: 170 tool calls across three attempts of one stage).
**Fix:** on restart, inject a compact carry-over — files read (paths + digests), commands run with exit status, the last three errors — as the first user message of the fresh attempt.

### B14 — Gate ceilings are absolute counts  *(verified)*
`main.py:58` `MAX_GATES = 50`; `WORKFLOW_MAX_GATES_PER_STAGE`. With auto-approve every write is a gate. Low-tier models write more, smaller files, so they meet the ceiling doing legitimate work.
**Fix:** ceilings on *repeated identical* gates (already the repeat guard) and on *supersteps*; the absolute gate count becomes a soft warning.

### B15 — The workspace digest truncates at 40 files  *(verified)*
`workspace_digest.py:36` `MAX_FILES = 40`. Beyond that, the agent rediscovers the tree with `ls` — the exact waste findings 86 targets.
**Fix:** a tree summary (directories with counts, then the files of the project directory in full) sized to a token budget, not a file count.

### B16 — The execution ledger omits `working_directory`  *(verified)*
`sandbox.py` `_record_execution` stores `command` only. Run 41 ran `node --test` under `/simple-to-do-list-app` and `simple-to-do-list-app` as if they were one command. `_written_since` also walks the whole workspace on every command.
**Fix:** record `working_directory` and `category`; key `failed/succeeded_this_way_before` on all three; cache the workspace mtime walk per call batch.

### B17 — "What is a test file" is defined twice  *(verified)*
`repository.py` `_LOOKS_LIKE_A_TEST` and `integration_checks.py` `_NOT_APPLICATION` are separate regexes. Finding 92 was a third definition. The codebase's own comment names this pattern: "the two halves never spoke."
**Fix:** one `classify_file(path) -> {application, test, config, document, stray}` in a shared module; every consumer imports it.

### B18 — Validators sniff strings in model answers  *(verified, low)*
`tools_models.py` `_must_be_runnable` rejects any value containing "browser testing" — including "headless browser testing with Playwright", which is runnable. Same shape as finding 83 (grep exit 1 called a failure).
**Fix:** the validator checks for a *runner the sandbox can execute* (a name in the allowlist) rather than for forbidden words.

---

## 3. Improvement programme

Five phases. Each phase is independently shippable and each retires a root-cause class from §1.

### 3.1 Phase 1 — Measure the model, don't assume it  *(classes C, D, G)*

**Deliverable:** `app/models/profile.py` — a `ModelProfile` produced by a startup probe and stored in Postgres keyed by `(model id, base url)`.

| probed | how | replaces |
|---|---|---|
| context window | `/v1/models` metadata, confirmed by a large prompt (as done this session at 70k) | `MODEL_CONTEXT_WINDOW` env |
| generation rate | one 800-token completion, floor = 0.8 × measured | `DEFAULT_MIN_TOKENS_PER_SECOND` |
| chars per token | `len(prompt) / input_tokens` on the probe | `CHARS_PER_TOKEN` |
| tool-call format | one forced tool call: `tool_calls` populated, or text-wrapped, or absent | B10 fallback on/off |
| structured-output mode | `with_structured_output` vs `json_schema` vs prompt-only | strategy selection |
| thinking delimiters | one call with reasoning on; record any `<|…|>`, `<think>`, `reasoning_content` seen | B9 sanitiser set |
| server family | `/v1/models` `owned_by`, `/props`, `/slots` | B8 |

Derived from the profile at run start: request timeout, budgets, `INNER_AGENT_RECURSION_LIMIT` (scaled from measured tool calls per healthy stage in §4's store), thinking arguments. The probe runs once per model, is cached, and re-runs when the model id changes — which is exactly the moment every constant-on-one-model bug in this session appeared.

**Acceptance:** switching between any two models used this session requires no `.env` change beyond the model id, and every derived number is visible in the run's first event.

### 3.2 Phase 2 — Technology-agnostic execution  *(class H; B1–B6)*

1. **Stack descriptor.** The stack selector's output becomes the single source: `language`, `runtime`, `package_manager`, `test_runner`, `build_command`, `entry_point`. The scaffolder, the allowlist, the timeouts, the server detector and the analysers all read it.
2. **Allowlist by capability** (B2). `runtime_for(stack) ∪ package_manager_for(stack) ∪ test_runner_for(stack) ∪ COMMON ∪ role_extras`. One test: every code-writing role can run the stack's runtime and test runner, for every stack in the descriptor table.
3. **Language analysers** (B1, B17). Generic first, JS/HTML second, Python third; Go/Rust/Java/.NET as thin implementations of `references()` and `test_files()`. The milestone reviewer's evidence block states which analyser ran, so "no cross-file problems" can never mean "no analyser".
4. **Timeouts and servers from behaviour** (B3, B4).
5. **Constraints from the brief, structured** (B6).

**Acceptance:** `tests/brief_low.md` rewritten for Go, for Python-FastAPI and for Rust each reach a milestone review with a non-empty cross-file evidence block and a correct line count.

### 3.3 Phase 3 — Corrections at the point of failure, as a system  *(classes A, B, E, F)*

Today's notices are eleven separate mechanisms in four files. Consolidate into one **Notice registry** at the tool boundary (extending `repeated_queries.py`):

| notice | key | fires on |
|---|---|---|
| identical result again | (tool, resolved target, result digest) | every read-only tool |
| identical failure again | (tool, args, error digest) | every tool |
| standing refusal | `validate_command` says no | commands, before execution |
| would change nothing | content before == after | every mutating tool |
| over a declared constraint | constraints object | every mutating tool |
| path rewritten | resolved ≠ given | every path-taking tool, *told* to the model |
| budget nearly spent | `langgraph_step` | every model call |

One registration table; one test that walks the agent's tool list and asserts every tool is covered by every applicable notice — the "thirteen of thirteen" test, written once.

Escalation ladder, applied automatically (§4 supplies the data): *hint → note in result → rewrite the call → refuse the call*. A notice that fires three times on one stage without changing the next call is promoted one rung for that model.

Reviewer discipline (B12): findings carry a `check_reference`; a reviewer prompt receives the list of checks that ran and their results, and its schema validator rejects findings outside the stage's scope.

### 3.4 Phase 4 — Self-learning and self-improving  *(all classes, over time)*

The harness already has the two ingredients: a per-run ledger of every command and every event, and Postgres. LangGraph's `BaseStore` (`PostgresStore`) gives cross-run, namespaced, searchable memory that every node and middleware can read through `runtime.store`, and Deep Agents' `StoreBackend` mounts it as `/memories/` for the agents themselves (both per the LangChain docs consulted for this plan).

**Namespaces**

| namespace | holds | written by |
|---|---|---|
| `("harness", "model", <id>)` | the `ModelProfile`; measured rates; observed tool-call quirks | probe + Phase 5 metrics |
| `("harness", "stack", <language>)` | commands that succeeded (from the ledger), layouts that passed review, test runners that ran | end-of-run extractor |
| `("harness", "notices", <model>)` | per-notice efficacy: fired / next-call-changed | Phase 5 metrics |
| `("harness", "reviews")` | findings later confirmed by a failing test vs. not | end-of-run extractor |
| `("agents", "instructions", <role>)` | the role's own accumulated notes, editable by the role via `/memories/<role>.md` | the agent (bounded) |

**Feed-forward.** The workspace-digest middleware already injects a map on every call; it gains a second block: the top-k store items for `(model, stack, role)` — "on this stack `node --test` needs `--experimental-vm-modules`", "this model writes `/workspace/` prefixes". Bounded to 800 tokens.

**Feed-back (learning).**
- *Notice efficacy* drives the escalation ladder in §3.3 automatically — the manual method used throughout this session (count fires, check whether the next call changed), run by code.
- *Threshold tuning within bounds*: `REPEATS_BEFORE_SAYING_SO`, `BUDGET_WARNING_FRACTION`, per-stack timeouts, `INNER_AGENT_RECURSION_LIMIT` adjust per model from measured distributions, each inside a hard range set in source. Safety limits (sandbox resources, forbidden arguments, approval gates) are never tuned automatically.
- *Restart carry-over* (B13) reads the stage's own ledger, so the second attempt starts where the first stopped.
- *Reviewer calibration*: a reviewer whose blocking findings are repeatedly not confirmed by any test or check has its severity vocabulary constrained in the next run's prompt.

**Guardrails.** Agents may write only to their own `/memories/<role>.md`, capped in size, and never to policy namespaces — the docs note store items shared across users should be read-only to agents to prevent prompt injection. Every automatic tuning is logged as an event with the before/after value and the evidence, and can be pinned by an operator.

**Acceptance:** a second run on the same (model, stack) shows fewer tool calls, fewer repeated calls and fewer notices than the first, with the difference attributable to store items that were injected.

### 3.5 Phase 5 — Observability that can see every layer  *(B11)*

- Post-middleware tool messages in the event stream.
- A `run_metrics` table: tool calls by kind, failure rate by kind, repeat rate, notices by type with next-call-changed, stage superstep counts, timeouts, restarts, model-call latency percentiles.
- The audit scripts from this session (`scan.py`, `live.py`) become `app/analysis/run_audit.py`, run at stage end and at run end, writing to the table and to the store.

---

## 4. Prioritised backlog

| # | item | class | effort | impact | acceptance test |
|---|---|---|---|---|---|
| 1 | Event stream records post-middleware tool messages (B11) | G | S | high — everything in §4 depends on it | a repeated `ls` note appears in the run's events |
| 2 | `ModelProfile` probe + derived timeout/budgets (§3.1) | C, D | M | high | model switch needs only the id |
| 3 | Output sanitiser + text-tool-call fallback (B9, B10) | G | M | high | Qwen2.5-Coder writes a file; `<think>` never reaches disk |
| 4 | Notice registry + thirteen-of-thirteen test (§3.3) | A, B, E | M | high | every tool covered |
| 5 | Stack descriptor → allowlist, timeouts, servers (B2–B4) | H | M | high | Go and Rust briefs build and test |
| 6 | Generic language analyser + `classify_file` (B1, B17) | H | M | high | non-JS product gets a size count and reference check |
| 7 | Structured constraints from the brief (B6) | A | S | med | no-cap brief is unbudgeted explicitly, not silently |
| 8 | Reviewer `check_reference` + scope validator (B12) | A | S | med | spec review cannot demand code |
| 9 | Restart carry-over (B13) | F | S | med | attempt 2 re-reads 0 of attempt 1's files |
| 10 | `PostgresStore` + namespaces + feed-forward block (§3.4) | learning | L | high | second run on same stack uses fewer calls |
| 11 | Notice efficacy → escalation ladder (§3.4) | learning | M | high | a notice ignored 3× is promoted, logged |
| 12 | Ledger records working dir + category (B16) | E | S | low | same argv, two dirs, two entries |
| 13 | Digest by token budget not file count (B15) | F | S | low | 80-file project fully mapped |
| 14 | Gate ceilings on repeats and supersteps, not count (B14) | C | S | low | legitimate 60-write stage passes |
| 15 | Scaffold unknown stacks from the declared layout (B5) | H | S | med | unknown stack reaches implementation |
| 16 | `_must_be_runnable` checks the allowlist, not words (B18) | A | S | low | "headless Playwright" accepted |

Effort: S ≤ half a day, M 1–3 days, L a week. Items 1–4 are the order to start in: 1 makes the rest measurable, 2–4 retire the classes that produced two-thirds of this session's findings.

---

## 5. Method to keep

The procedure that produced these findings is itself the most valuable artefact of the session, and §3.5/§4 exist to automate it:

1. Watch decisions, rejections, tool calls, retries and errors on a live run.
2. On a suspect pattern, **verify against previous run data** before acting — three of this session's instruments were wrong before they were right (a digest that included a random id; mis-paired parallel tool calls; the event stream that cannot see middleware notes).
3. Prefer a check at the point of failure over a rule in a prompt; prefer a rewrite over a hint the model has ignored three times; prefer refusing a corrupted write over saving it.
4. Test the integration, not the component — the one regression shipped this session passed every unit test and failed on the agent's first call.
5. Derive constants; never type a number measured on one model.
6. Record provenance in the commit: run id, stage, count. The next reader is deciding whether a constant still holds.

## 6. Non-goals and risks

- **Not a rewrite.** Every phase extends existing modules; the middleware chain, the ledger, the checks and the reviewers stay.
- **Self-tuning is bounded.** Nothing that protects the host (sandbox limits, forbidden arguments, approval gates) is learned. Ranges live in source; the store holds the position within the range.
- **Learning from bad measurements is worse than not learning.** Item 1 is first for that reason.
- **Frontier models will hit different classes.** Expect fewer of A–G and more of "the model did something the harness has no vocabulary for" — the store's `notices` namespace is where those will first show up as zero-efficacy entries.
