# Deep review: mechanisms that are built but never fire, or fire and do nothing

Date: 2026-11-25 (written 2026-11-26 JST). Read-only review; nothing in `src/`, `tests/`, config or docs was changed.

## What was read

- `loop.sh effects` on the last 30 transcripts (runs of 2026-11-23 15:19 JST to 2026-11-25 23:32 JST): 25 fast, 4 thorough,
  1 empty (4 records). 29 runs carry provenance.
- My own pass over the same 30 transcripts (9,567 model requests, 12,416 tool calls): which switch signals appear, which
  tools each request offered and which were called, how each stage's conversation ended.
- 40 workspaces: `.harness/fix-journal.json`, `.harness/acceptance.json`, `docs/decision_log.md`, and which `.harness/`
  files exist at all.
- The code of each mechanism that came out at zero, and three reproductions inside the worker with a stub model
  (no call reached the owner's model).

All times below are JST. The two runs that were live when this started (run-32362f3b, run-2f653f55) ended during the
review; the `effects` files for them were taken mid-run, the transcript passes after they ended.

## Summary

| # | Mechanism | State | Evidence in one line |
|---|---|---|---|
| 1 | `DIAGNOSE_A_RECURRING_CAUSE` | Dead in every local run | 0 diagnoses in 40 runs; 7 causes went to a third fix or later without one |
| 2 | Candidate fixes (`FIX_CYCLE`, AY step 2) | Dead in every local run | The candidate model resolves to `None`; reproduced in the worker |
| 3 | `SCREENSHOT_RUBRIC` | Dead in every local run | `.harness/screenshot-rubric.json` in 0 of 40 workspaces |
| 4 | `ASK_SPECIFICATION`, `CODE_GRAPH_TOOL` | On, but removed by another switch | Recorded on in 29 of 29 runs; their tools offered in 0 of 9,567 requests |
| 5 | Web tools (`WEB_TOOLS_OFFERED`, `WEB_TOOLS_AFTER_TWO_FAILED_FIXES`) | Offered, never called | 4,192 offers, 0 calls |
| 6 | Switch-firing register (`switch_firing.fired`) | Reports acting switches as never fired | `ONE_DESIGN_REVIEW`: 0 of 29 by the register, 33 of 40 decision logs say it acted |
| 7 | `DEFECT_CALL_CAP` (AY.4) | Cannot be reached | 0 of 30 runs; one defect cost 75 calls with a cap of 60 |
| 8 | `REPEATED_REWRITE_PROMPT_STOP` | Trigger almost never met | 0 stops; 1 identical request in 221, but 35 identical replies in 215 |
| 9 | `read_docs` | Fires and returns the wrong thing | 3 calls in 30 runs, all on a Java run, answered from a Rust crate of the same name |
| 10 | Architect told to use `read_docs` with no tools | Guidance contradicted by the request | 62 of 68 architect requests naming it did not offer it |
| 11 | The call budgets | Bind in about half of fix and builder stages | 66 of 138 fix stages ended with tools withheld and no answer |
| 12 | The budget warning | Injected, ignored | Next reply after it: 1,125 tool calls, 114 answers |
| 13 | `PAGE_PROBE` | Reached, leaves no record | Reached in 8 of 45 workspaces; nothing says whether it ran clean or could not run |

Findings 1 to 3 share one root cause and are the most important result: **in a local-only run the workflow's own
`model` and `judgement_model` are both `None`, and every helper that guards with `model is None` silently skips.**

---

## Finding 1 - `DIAGNOSE_A_RECURRING_CAUSE` has never run (root cause shared with 2 and 3)

**Impact.** The switch was built for the deep review of 11-18 (item 1.4: the fix rate falls from 29% to 22% to 11% on
repeated attempts). It is on in 29 of 29 runs and has produced no diagnosis in any of 40 workspaces.

**Evidence.**
- Across 40 `fix-journal.json` files: 222 causes, 204 failed attempts, 48 causes with two or more failures,
  **0 `hypothesis` entries**.
- 7 causes went on to a third fix or later with no diagnosis (runs eebf5e67, 0d55d869, 4702bef3, eded4941, df1ac51d,
  b6c5c636, 1d79334d). One in df1ac51d had six failed attempts.
- No request in the 30 transcripts contains the diagnosis role text ("You diagnose why earlier attempts").
- Case, run-1d79334d, 11-25 09:15 to 09:28: the defect "The product does not start" failed at 09:15:59 and 09:18:13.
  The third fix started at 09:18:16, 0.2 s after the test round, with no call in between. Three rewrites in a row
  rewrote the test files; the cause (`panic: parsing "/{any:.*}"` in `server.go`) was found only by the fourth
  attempt's agent loop at 09:28.

**Root cause.**
- `src/app/graph/nodes/fixes.py:314` passes `ctx.judgement_model or ctx.model` to `cause_journal.diagnosed`.
- `src/app/graph/cause_journal.py:276` returns `""` when `model is None`.
- The worker builds its runner with no model (`src/app/server/tasks.py:514`), so `build_workflow_graph` gets
  `model=None` unless the run has model overrides. All nine runs I checked in the run store have none.
- `src/app/graph/workflow.py:10169` then calls `build_judgement_model(None)`. Every run is recorded `local_only: true`,
  so `src/app/models/roles.py:188` returns the default it was given: `None`.
- Reproduced in the worker with the local-only flag set: `judgement_model None | fix_model None | candidate_model None
  | diagnosis model None`.
- With a stub model and a real journal (run-1d79334d), `needs_a_diagnosis` is `True` and `diagnosis()` returns its
  hypothesis. The mechanism itself works; it is never handed a model.

**General.** Every local run. Other call sites already work around the same `None`
(`fix_model or ctx.model or ctx.building_model` at `fixes.py:409, 438, 452, 495`; `specification_parts.py:145` builds
the default model, with a comment describing this exact failure).

**Fix proposal (always on, a bug).** Give `GraphContext` one method that returns a model that can be called for a
direct call (the judgement model, else the stage's model, else the built default), and use it at every direct-call
site. Then a `model is None` guard in a helper means "no model exists", not "nobody passed one".

**Test idea.** Build the context exactly as the worker does for a local-only run (`model=None`, local-only flag set),
load the captured `fix-journal.json` of run-1d79334d as it stood after its second failure, and assert that
`_diagnosed_if_it_keeps_failing` makes one model call. It makes none on the current code.

## Finding 2 - candidate fixes never run on a local model

**Impact.** `src/app/graph/bounded_fixes.py` says in its own header why it exists: candidates were asked "only from a
judgement model distinct from the build model, so a run on one local model never reached them". The fix for that
does not work, for the reason in finding 1.

**Root cause.**
- `src/app/graph/context.py:68-70`: `the_build_model(..., reasons=True)` returns `self.model` when the judgement
  model is the same object. Both are `None`, so the fixer's `fix_model` is `None`.
- `src/app/graph/bounded_fixes.py:38-41`: `the_candidate_model(None, None, None)` returns `fix_model or model`, which
  is `None`.
- `src/app/graph/nodes/fixes.py:403`: `if failed_tries >= 1 and candidate_model is not None` is never true.

**Evidence.** The reproduction above. In the transcripts, second and third attempts send rewrite requests one after
another (run-1d79334d 09:16:02, 09:16:25, 09:16:56, 09:17:27), not the parallel batch of candidates.
I did not find a transcript marker that separates a candidate from a single rewrite, so the code path and the
reproduction are the proof here, not a count.

**Fix proposal.** The same context method as finding 1. This is the larger of the two wins: candidates are kept only
when the defect's own tests pass.

**Test idea.** Same local-only context; a defect with one failed attempt and a passing `check`; assert
`fix_by_candidates` is called.

## Finding 3 - `SCREENSHOT_RUBRIC` never scores a page

- `src/app/graph/delivery.py:550` passes `ctx.judgement_model` (`None`); `src/app/acceptance/screenshot_rubric.py:69`
  returns `None`.
- `.harness/screenshot-rubric.json` exists in 0 of 40 workspaces, including completed page products.
- The switch is on in 29 of 29 runs through the deep-verification bundle.
- A local model may not be able to judge an image at all. If so, the honest state is "off for a model without
  vision", shown as such, not "on".

## Finding 4 - two switches recorded as on whose tools are never offered

- `ASK_SPECIFICATION` and `CODE_GRAPH_TOOL` are on in 29 of 29 provenance records.
- `LEAN_TOOL_LISTS` (also on) removes both tools: `src/app/agents/stage_tools.py:33-35` lists `code_graph` and
  `ask_specification` as seldom called.
- Offered in 0 of 9,567 requests. `.harness/answers.json` exists in 0 of 40 workspaces.
- Consequence: every KPI row says these two were on, and any measurement that compares runs by `switches_on` counts
  them as active.

**Fix proposal.** Either drop the two switches (their tools were measured unused on 11-18), or make provenance
record a switch as on only when nothing else removes what it adds.

## Finding 5 - the web tools: 4,192 offers, no call

| Tool | Requests offering it | Calls |
|---|---|---|
| `search_the_web` | 4,192 | 0 |
| `read_web_page` | 4,192 | 0 |
| `research` | 2,040 | 0 |
| `move_artifact` | 6,182 | 0 |
| `module_exports` | 4,845 | 1 |
| `read_docs` | 6,232 | 3 |
| `look_up_package` | 6,232 | 18 |
| `look_at_page` | 3,463 | 6 |
| `changed_since_sprint` | 1,010 | 2 |
| `use_runtime` | 162 | 0 |
| `delete_artifact` | 6,182 | 30 |
| `read_command_output` | 6,182 | 34 |
| `glob` / `grep` / `ls` | 7,796 each | 90 / 82 / 193 |

By role, the web pair was offered and never called in: defect fix 1,330, acceptance author 1,040, testing builder 711,
backend builder 394, test round 324, database builder 136, UI builder 126, setup 57.

- `LEAN_TOOL_LISTS` removed the web pair on 11-18 for exactly this ("never called in about 3,500 offers").
  `WEB_TOOLS_OFFERED` put them back on 11-23 (`stage_tools.py`, `without_the_seldom_called`). The result is the same.
- `WEB_TOOLS_AFTER_TWO_FAILED_FIXES` put its note in 13 requests in 5 runs ("Two fixes of this defect have failed, so
  `search_the_web` and `read_web_page` are offered to you"). No search followed. With `WEB_TOOLS_OFFERED` on, the
  tools were already offered to that fixer, so the note is the only thing the switch adds.
- Tool schemas are a median 22,600 to 25,300 characters per request in the fix, builder and suite-writing stages.

**Fix proposal.** The model does not look things up; the harness-side lookup does (67 `lookup` events in 21 runs).
Turn `WEB_TOOLS_BY_MEASURED_TIER` on, or stop offering the pair to this model, and stop offering `move_artifact`,
`research` and `module_exports` where they were never called. This is an efficiency change, so behind the existing
switch.

## Finding 6 - the switch-firing register cannot see decisions, so it reports acting switches as dead

**Evidence.**
- `ONE_DESIGN_REVIEW`: `switch_firing.fired` finds it in 0 of 29 runs. Its words ("revised once and not reviewed
  again") are in the decision log of 33 of 40 workspaces.
- `NEAR_GREEN_REPAIR_TO_ROUND`: 0 of 29 by the register, 1 decision log.
- `SPRINT_TIME_BUDGET`: 2 by the register, 4 decision logs.

**Root cause.** `src/app/observability/switch_firing.py:113` reads model requests, tool results and ten harness record
kinds. These switches write their words to `docs/decision_log.md`, which is not a transcript record.
`scripts/loop/kpi.py:49-55` writes `fired(records)` to the ledger as `switches_fired`, and
`scripts/loop/switch_gate.py:133-137` counts `runs_fired` from it.

**Impact.** The gate that decides whether a switch earned its place sees "on in 29 runs, fired in 0" for a switch that
acted in most of them. A second gap of the same kind: 90 of the 125 switches recorded on have no signal at all, so
the register can say nothing about them (findings 1 to 4 were all in that blind part).

**Fix proposal.** Write one transcript record when a decision is taken (`kind: decision`, with its text), and read it
in `fired`. For the switches with no signal, have each write a harness record when it acts, as the newer ones do.

**Test idea.** Replay the stored transcript and decision log of a run whose log says "revised once and not reviewed
again" and assert `ONE_DESIGN_REVIEW` is in the fired list.

## Finding 7 - `DEFECT_CALL_CAP` cannot be reached

- Cap: 60 model calls per defect (`src/app/graph/defect_budget.py:24`), summed over the attempts kept on the
  remediation cycle (`spent`, checked at `defect_budget.py:153`).
- A fix stage stops at 16 calls (`src/app/agents/settled_answer.py:2172`) and a sprint attempt allows two fix rounds
  (`src/app/sprint/__init__.py:315`), so one cycle holds about 32 calls plus rewrites. A re-plan starts a new cycle
  and the count starts again.
- 0 of 30 runs hit it. In run-b6c5c636 one defect ("The unit tests fail ... Command timed out after 300 seconds")
  cost 75 calls over four attempts (11-25 05:38 to 07:46), two before a re-plan and two after. In run-df1ac51d one
  cost 56.

**Fix proposal.** Count from the fix journal by problem key, as `cause_journal.failed_fixes_in_the_run` already does
for the web tools after it hit the same reset.

**Test idea.** The journal of run-b6c5c636 with its recorded `attempt calls`: assert the
fourth attempt is refused. It is dispatched on the current code.

## Finding 8 - `REPEATED_REWRITE_PROMPT_STOP` watches the wrong side

- 221 rewrite requests in 30 runs: 1 byte-identical to an earlier one. The switch stops at three. 0 stops.
- 215 rewrite replies: **35 byte-identical to an earlier reply in the same run, in 15 runs.** 86 of 211 rewrite
  replies left their file unchanged.
- Case, run-1d79334d 09:16 to 09:21: the rewrite of `server_test.go` came back at 13,848 to 13,886 characters six
  times, the request differing by a few hundred characters each time.

**Root cause.** `src/app/graph/repeated_rewrite_prompts.py` fingerprints the prompt. The prompt changes a little
every attempt (the attempt list grows), while the model's answer does not.

**Fix proposal (always on).** Fingerprint the reply per file. A reply identical to one already measured failing is
not applied or measured again; the defect goes straight to the agent loop.

**Test idea.** Feed the six captured replies for `server_test.go` from run-1d79334d through the rewrite path; assert
the second identical one is not measured.

## Finding 9 - `read_docs` answers from the wrong ecosystem

- Called 3 times in 30 runs, all by the architect of run-eded4941 (a Java Spring Boot service, morning of 11-24).
- One answer: nothing found. Two answers: `"source": ["https://crates.io/api/v1/crates/spring-boot"]`, the README of
  an unrelated Rust crate, labelled "Reference text from the project's own documentation".
- Root cause: `src/app/tools/docs.py:212-240` knows npm, PyPI, crates and Go. With no ecosystem given it tries each,
  and a Maven name that also exists on crates.io matches.

**Fix proposal (always on).** Default the ecosystem to the run's stack. For a stack whose registry the tool does not
read, say so instead of trying the others. The per-language table already exists in `package_registry`.

**Test idea.** The captured call (`name="spring-boot"`, topic "JdbcTemplate query update methods") with the stack's
language set to Java and a stub fetch: assert no request goes to crates.io.

## Finding 10 - the architect is told to read with a tool it does not have

- `src/app/agents/principal_architect.py:269`: third-party calls are to be given "as that version's documentation
  gives it - read with `read_docs`, not recalled".
- 68 architect requests carry that line. 62 of them offered no `read_docs` (for example run-1d79334d 11-25 08:44,
  tools `[]`: the specification written in parts).
- Also: 16 drafting requests name `module_exports` with no tools offered.
- Effect: the specification's interface section is written from recall while saying it was read. The 11-25 research
  report covers lookups for fixers; this is the same gap one stage earlier.

**Fix proposal.** When the specification is written in parts, put what the harness already read
(`research_brief`, the stack facts) under that section and word the line as "from the notes below". Keep the
tool-naming line only in requests that offer the tool.

**Test idea.** Take a captured in-parts architect request; assert that no tool named in backticks in the request is
missing from its `tools` field. A general check of this kind over stored requests would have caught both cases.

## Finding 11 - the call budgets bind in about half of the stages that matter

Stage conversations that ended with "Your tools have been withheld" (budget spent, no answer written):

| Stage | Ended at the budget | Stages |
|---|---|---|
| Defect fix (cap 16) | 66 | 138 |
| Testing builder (cap 40) | 14 | 24 |
| Backend builder | 7 | 13 |
| Test round | 7 | 10 |
| Database builder | 3 | 3 |
| Setup | 2 | 2 |
| Technical lead | 6 | 20 |
| Acceptance author | 8 | 93 |

Fix stages by calls and outcome (stages with a measured outcome):

| | Fixed | Not fixed | Fix rate |
|---|---|---|---|
| Agent loop under 16 calls | 18 | 12 | 60% |
| Agent loop at the cap | 17 | 62 | 22% |
| Rewrite only | 18 | 22 | 45% |

This does not show the cap causes the failures: hard defects use more calls. It does show the cap is the normal end
of an agent-loop fix (79 of 109), not a guard for the rare runaway it was sized as (median productive fix 12 calls).
Reply caps, by contrast, rarely bind: about 33 of 9,435 replies ended on length.

## Finding 12 - the budget warning is sent 1,247 times and ignored

- "You have NOT written a structured response yet" (`settled_answer.py:927`) was in 1,247 requests in 23 runs.
- The next reply was a tool call 1,125 times and the answer 114 times (9%).
- The code's own comment at `settled_answer.py:505-512` measured the same thing earlier (13 of 276). The block is
  still sent; what works is withholding the tools at the end.
- Low cost, but it is context the model demonstrably does not act on, in the requests closest to the window's limit.

## Finding 13 - `PAGE_PROBE` leaves no record

- Reached in 8 of 45 workspaces (`page_probe_persists` written to `.harness/acceptance.json`). 0 findings.
- `src/app/acceptance/page_probe.py` returns `None` both when the probe could not run and when its report was not
  found, logged at debug level only. Nothing separates "four checks passed" from "did not run".
- The contract probes do keep such a record (`.harness/contract-probe.json`: asked, probed, skipped and why).

**Fix proposal.** Write the page probe's outcome to the same file.

---

## Rare and fine (not dead)

- Contract probes: probing in most runs (server error 18 of 21, bad body 17 of 24, concurrent write 16 of 24);
  findings are rare, which is the expected state.
- `SPEC_DRY_RUN` (2 runs), `EDGE_PROBE` (3), `MUTANT_CHECK_IN_THE_FIX_STAGE` (4), `FIX_STAGES_THAT_CLOSE_NOTHING` (6),
  `UNIT_TEST_QUARANTINE` (4 workspaces), `SETTLE_SPEC_CONTRADICTIONS` (24 of 29).
- `IDS_READ_WITHOUT_A_CREATE`: 0 findings; 25 of 38 stored suites request a literal id somewhere, and every such
  test also creates a record, has a setup hook or expects a refusal. The check's exclusions cover every real case so
  far. Cheap, no action.
- `SETUP_SCOPE_GUARD`: acts only on a layered setup for a stack no pack covers; `.harness/setup-scope.json` in 0 of 40
  workspaces because no such run happened.
- `LEAN_PROMPTS_FOR_STRONG_MODELS`: acts only for a model measured strong; documented as inert on local models.
- Too new to judge (first deployed 11-25): LF.1310, LF.1312, LF.1316, PA.3, PA.8, LF.1299. LF.1310's 39 refusals in 6
  runs all predate its deploy at 02:22 on 11-25; no refusal has happened since.
- Not reached and by design: LF.188 (should stay 0), LF.203, LF.202, LF.185, LF.1271 kept (reverted fired once).

## Checked and fine

- Journal shown to fixers (42 requests, 7 runs) and to the lead at a re-plan (50 requests, 16 runs).
- `research_brief` is absent as a stage in thorough runs (0 of 4) but the reading still happens with fallback topics.
- `held_for_review`, `with_the_parts_written`, `the_review_model` and the rewrite path all handle a `None` model.
- No tool was called that was not offered. No invalid tool calls were recorded.
- Localisation (AY.1) fires in fast runs (70 calls in 20 runs).

## Not covered

- The other 85 or so switches with no firing signal were not checked one by one; I checked those that leave a file
  in `.harness/` or a tool in the request. Finding 6 is the fix that makes the rest checkable.
- Stuck lookups and their notes (in flight as FX items) were left alone as briefed.
- Whether the 16-call cap costs fixes (finding 11) needs a measured comparison; the numbers here are observational.
- Per-stage call counts are per stage name per run, so a stage restarted on a fresh conversation counts once.
