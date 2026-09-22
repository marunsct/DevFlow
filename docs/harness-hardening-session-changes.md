# Harness Hardening Session — Changes, 20–22 September 2026

**What this is.** Every change made to this harness on this machine between 20 and 22 September
2026, why it was made, and the measurement behind it. Written to be picked up on another machine.

**Read section 1 first.** Nine commits exist only on this machine.

**Scope.** 41 commits on branch `harness-hardening-session`, 102 files, +13,554 / −228 lines, of
which 47 are new test files (this document is the 41st commit). Nothing here is speculative: every change names the run, the transcript
or the workspace it came from.

**Method.** The work was a loop — start a run against a fixed brief, read its transcript and its
product, find what the harness did wrong, fix it, redeploy, run again. Fourteen runs went through
that loop. The evidence is the runs' own transcripts (`DATA_DIR/transcripts/<run-id>.jsonl`,
21,841 rows and 6,387 tool calls in total), their stored workspaces, the `runs` and `checkpoints`
tables, and the container logs.

---

## 1. State of the tree

| | |
|---|---|
| branch | `harness-hardening-session`, tracking `origin/harness-hardening-session` |
| base | `fix-workflow-bugs` |
| commits ahead of base | 41 since 2026-09-20 |
| **unpushed** | **9** — `56faee7` through this document. `git push` before leaving this machine. |
| working tree | clean |
| deployed image | built 2026-09-22 03:16 JST, contains everything up to `5347ae0` |
| **not deployed** | the 8 code commits among them. `docker compose build worker app && docker compose up -d worker app` |
| suite | **4,493 passing, 46 failing, 32 skipped** |

The 46 failures are the floor on this machine and are not regressions — they are the tests that
need a model server on `localhost:1234`, which this Mac does not run. Run the suite with:

```sh
rmdir /tmp/empty.env 2>/dev/null; : > /tmp/empty.env
docker run --rm -v "$PWD:/app:ro" -v /tmp/empty.env:/app/.env:ro \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e TESTCONTAINERS_HOST_OVERRIDE=host.docker.internal \
  devflow-tests:latest python -m pytest tests/ -q --no-cov -p no:cacheprovider
```

All four parts matter. The whole-repo mount is needed because several tests read
`docker-compose.yml`; the `.env` shadow stops the suite picking up the real `OPENAI_BASE_URL` and
retrying against an unreachable model server for twenty minutes; the docker socket is needed by
testcontainers; `--no-cov` is needed because a read-only `/app` cannot take `coverage.xml`.

**Do not edit `src/` while a suite run is in flight.** Several tests assert on
`inspect.getsource(...)`, and a function imported before an edit keeps its old `co_firstlineno`, so
the assertion fails on code that is correct. This produced three phantom regressions before it was
understood.

**Stale baselines to ignore.** `/tmp/base2.txt` and `/tmp/base_fresh.txt` were captured with a
partial mount and carry 78 failures including 32 `test_graph_routing` errors. Those errors are
artefacts of the invocation. Diffing against them invents regressions.

---

## 2. The runs this evidence comes from

One brief throughout (`tests/brief_low.md`, a to-do list app with add/edit/delete, filtering,
persistence and responsive design, capped at 500 lines of code). The model is
`unsloth/Qwen3.6-35B-A3B-MTP-GGUF` reached over a Cloudflare quick tunnel, which imposes a fixed
~100-second origin timeout that cannot be configured.

| # | run | outcome | what ended it |
|---|---|---|---|
| 1 | `b598780b` | completed | — |
| 2 | `9c0fc48d` | cancelled | — |
| 3 | `8904f87b` | **failed** | milestone review still required changes after 3 revisions |
| 4 | `b0db10b1` | completed | shipped three dead filter buttons |
| 5 | `35424714` | **failed** | 3 revisions, findings still open |
| 6 | `c97f5a88` | completed | — |
| 7 | `e7ef79a2` | **failed** | reviewer used `blocked` for something fixable |
| 8 | `0cbbb28b` | completed | `edit` never built |
| 9 | `86a60de1` | completed | `edit` built and tested |
| 10 | `9f14d645` | **failed** | superstep ceiling inside one stage |
| 11 | `7c0bf755` | cancelled | — |
| 12 | `6b511391` | **failed** | reached the model-call budget 3× with no answer; 13.5M tokens, nothing delivered |
| 13 | `d483f554` | completed | **0 restarts**, 32 min, 42 unit + 10 browser tests passing |
| 14 | `3c8e772e` | completed | **0 restarts**, 45 min, 66 tests passing |

Runs 13 and 14 are the first two runs in this harness's history to finish without a single stage
being killed and restarted on a fresh conversation.

---

## 3. What changed, by theme

### 3.1 Stages that could not finish

**`9264980` — Take the tools away at the end of the budget instead of asking again.**
Run 12 died being *asked* to answer. Its last request read "You have made about 39 of the 40 model
calls this stage is allowed … Return your structured response now", and the model replied with an
`edit_artifact` call. It did that on three consecutive fresh conversations and the run failed.

Across the twelve transcripts stored at the time, that correction was sent on **276 model calls**.
13 returned the answer; 263 went back to work — 132 `read_file`, 68 `run_terminal_command`,
29 `edit_artifact`. So on the last two calls of the budget, with no answer written, every tool is
withheld. `_get_bound_model` appends the structured-output tools to whatever `request.tools` holds,
so the model is left bound to exactly one tool — the one that ends the stage. A real agent graph is
driven in the tests, because the whole change rests on that detail of `create_agent`.

Not at the warning threshold, which was the tempting version: 23 of the 28 stages ever warned went
on to answer, some after forty further calls of real work.

*Measured in production:* fired 4 times in run 13 and 5 times in run 14; both runs had zero
restarts. `src/app/agents/settled_answer.py`, `CALLS_RESERVED_FOR_THE_ANSWER = 2`.

**`3c29191` — Let a stage reach the call budget before the superstep ceiling stops it.**
Run 10 died at a `GraphRecursionError` around 25 model calls, before the 40-call budget guard could
salvage anything. `INNER_AGENT_RECURSION_LIMIT` is now derived from `MODEL_CALLS_PER_STAGE` rather
than written separately, so the two ceilings cannot disagree.

**`774bd48`, `47fec5d`, `a13b2ef` — Carry what a dying attempt learned into the fresh one.**
A restarted stage began from nothing. It now carries a note naming the files the previous attempt
read and what it had established. `47fec5d` made those paths workspace-relative
(`todo-list-app/app.js`), because the first version emitted
`/app/data/workspaces/default/todo-run12-…/todo-list-app/app.js`, which no tool accepts. `a13b2ef`
wired the repository root through to the call site — the parameter existed and nothing passed it,
so the unit test covering the `None` case passed while production emitted absolute paths.

### 3.2 Reviews that could not converge

**`cffd27e` — Let the milestone reviewer hear what it said last round.**
Both runs that died at the revision limit died chasing a moving target.

- `35424714`, milestone two: round 2 raised, at **minor**, "init() is the main DOM wiring entry
  point exported from ui.js, but no automated test exercises it". Round 3 raised the same defect at
  **blocking**, and round 3 was the last one, so the run ended with nothing delivered.
- `8904f87b`: round 1 wrote into its own acceptance evidence "Confirmed 447 code lines (non-blank,
  non-comment) is under the 500-line brief limit". Round 3 raised **major** "Application source
  files total 631 lines … exceeding the brief's stated constraint" — on the one round where raising
  it ends the run.

`revision_comments` carried the findings forward to the technical lead all along, so the builders
always knew what was asked. The reviewer was the only party to the argument that could not hear
itself: each round is a fresh conversation over the same code. It now receives its own previous
findings and the rule that follows — a defect it called optional last round is optional this round —
and it is told which revision this is, with the last one spelling out that `changes_required` there
is the end of the run rather than another round of fixes.

Severities are deliberately **not** clamped: matching "init() has no test coverage" to "no automated
test exercises init()" needs fuzzy text matching, and a wrong match silences a real blocking
finding, which is worse than the failure being fixed.

Gated on `milestone_revision_count`, because `sprint_advance_node` resets that and leaves
`milestone_review` in state — on the first review of a new sprint that field still holds the last
sprint's verdict.

**`bfd2ea7` — Stop a fixable milestone review from killing the run**, and **`87ced2e` — Refuse a
descope the run authorised itself.** Run 7 ended because the reviewer wrote `blocked` for something
a specialist could have fixed; the status field now states its consequence ("the run ENDS HERE") and
a validator refuses `blocked` for anything the findings describe as fixable. Run 5 wrote
"ADR-08 — Inline Editing: Deferred" and its reviewer cited that ADR to accept the milestone; a
decision record the run wrote cannot descope a criterion the brief states.

### 3.3 Checks that were wrong about the product

**`56faee7` — Check the product against the brief, not the run's restatement of it.** *(the most
important change in this session)*

Run 14 completed with no way to edit a task and nothing in the workspace disagreed. The brief states
"Users can add, edit, delete tasks". The run's technical specification records:

> Q3: Is inline editing of title/description desired beyond toggling completion status? The
> acceptance criteria mention 'edit' but the core workflows only describe marking
> complete/incomplete. Decision recorded: 'Edit' refers to toggling completion status. Inline text
> editing is deferred.

From there the documents enumerate create, update, complete and delete and never edit, so
`_actions_the_documents_require` returns a set with no `edit` in it,
`_a_required_action_nothing_implements` finds nothing missing, and every gate passes. **`edit` is
absent from four of the eight stored products** (runs 7, 8, 11, 14).

The run is allowed to *defer* a requirement — that path exists and reports it in the right words,
which is how runs 7, 8 and 11 were each caught. What it may not do is redefine one out of existence,
because after that every check in the workspace reads the restatement and agrees with it. So
`summarise_integration` now takes the brief, the two requirement checks union it with the documents,
and an action the brief asks for that the documents no longer mention gets its own finding. The
deferral the run did record is quoted inside it, because the reasoning was sound; it is the
authority that was missing.

**`eef6f55` — A suite naming a feature is not the product having one.** The "is it built?" check was
reading the test files: run 12 was reported clean for `edit` because `app.test.mjs` mentions it,
while `app.js` has none. The two requirement checks now read strictly different files — product
versus suites — and neither may borrow the other's evidence.

**`6e668b2` — A filter bar built from radios is a control group too.** `_CLICKABLE_WITH_DATA`
requires a `data-*` attribute, so it saw `<button data-filter="all">` and not
`<input type="radio" name="filter">`. Run 4's three dead filter buttons were caught only because
that run happened to choose the first spelling. Handles are the spellings a script actually uses —
`name="filter"`, `getElementsByName('filter')` — never the bare word, because `filter` alone matches
`tasks.filter(t => ...)`, which is `Array.prototype.filter` and is how the first version of that
check vouched for the dead buttons it was written to find.

**`0747fc2` — Check the responsive criterion nothing was checking.** "Responsive design for mobile
and desktop" was the one acceptance criterion with no check behind it in either direction. The check
is deliberately broad about technique: run 13's stylesheet has no `@media` in it and is fluid
throughout (`clamp()`, `min()`, viewport units), so a check demanding breakpoints would have filed a
blocking finding against the best product this harness has produced.

**`4c186fb` — Say which constraint the Playwright finding crosses.** The finding tells a project it
MUST install `@playwright/test`, which on a brief reading "No external dependencies" is an
instruction to break a stated constraint, with no mention that the constraint exists. Both of run
13's reviewers worked the answer out themselves and filed the result as `suggestion` against a
finding the module grades as blocking. A check two consecutive reviewers have to overrule is the
check's problem.

**`b81ff49`, `f3a9679`, `1c00208`, `c31df57`** — the rest of the cross-file work: an attribute the
script sets itself counts as set; a requirement is read from the section it sits in rather than only
its wording (run 8's intake stated its CRUD list under `## Success measures`, which named no actor
and so matched nothing); and five checks added for what four runs actually shipped.

### 3.4 Tools that told the model untrue things

**`5347ae0` — Tell a workspace that has a browser the truth about its timeouts**, and **`82b0b36` —
Name the route that serves a page.**

A timed-out `npx playwright test` was answered with "there is no browser to open a page with … To
check a page, read the file and assert on its contents from a test". Seven minutes later
`npx playwright test --project=Desktop` ran 34 tests in the same sandbox with real passes and
failures. The same sentence was in the `serve` refusal, which fired 16 times, while that run's own
`playwright.config.ts` carried `webServer: { command: 'npx serve .' }` and it worked — the same
program, in the same container, refused to the agent and granted to the test runner.

The remedy was worse than the false fact: "read the file and assert on its contents from a test"
describes the hand-built DOM that another part of this harness refuses. Both messages now depend on
what the workspace has installed, and name Playwright's `webServer` as the route that finishes.

**`ea542f5` — Refuse the third hand-built browser, and stop telling app.js its assertions never
execute.** Two findings in one commit:

- `a_dom_built_by_hand` noted and let the write through, which is right the first time and the
  second. Run 12 is the third: its testing specialist was told **nine times**, grew `app.test.mjs`
  from 145 lines to 1,195 while being told — a `Proxy` over a `Map` standing in for `dataset`, a
  `mockStorage` throwing `QUOTA_EXCEEDED` — and then spent three whole conversations debugging the
  mock instead of the product. The third write is now refused, on the same threshold as the undo
  refusal, and names three ways out including the honest one (test the logic that does not touch the
  DOM and say in the response that the UI is untested).
- `_the_test_command_will_not_run_this` ran on every write with no check that the file was a test.
  Across the thirteen transcripts it fired **215 times on files that are not tests** and 41 times on
  files that are. `app.js` was told 83 times that "this one's assertions never execute" and to "Add
  it to the script", which would put the application file into `node --test`.

**`82b0b36`, tool description half.** `node -e` was refused 54 times across fourteen runs, the
largest single class of command failure. The refusal *works* — measured on what the model did next,
27 of 55 wrote a file immediately and only 5 tried an inline flag again — it just arrives one model
call too late, and 12 of the 20 stages that hit it hit it more than once. Both corrections moved
into `run_terminal_command`'s own description, where they are read before the first call.

### 3.5 Reading that went nowhere

**`db23018` — A narrower window of lines you have read is not a new read.** The withholding ladder
keyed on a digest of the returned bytes, so asking for `limit=100` instead of `limit=120` reset it.
Measured live on run 13's `specialist_ui_ux_0`, reading a 391-line `app.js` it had written itself
two minutes earlier: reads 2–11 withheld from the 4th on, read 12 (`limit=120`) returned 3,483 bytes
in full, read 15 (`limit=100`) returned 2,897 in full — about 19,000 characters of lines the stage
had already been given, after ten withholdings, and those six calls are what carried the stage to
the edge of its budget.

**`2ef623a` — Make a read that returns nothing new fail instead of succeeding quietly.**
Every rung of the ladder was a notice attached to a *successful* result, and notices do not stop the
reading. Measured by what the stage did on its very next tool call:

| after | read the same file again | read a different file | did any work |
|---|---|---|---|
| a note | 27.3% | 42.0% | 31% |
| a withholding | 30.0% | **61.5%** | 8% |
| the stage-wide exit notice | — | — | **93% read again** |

The exit notice fired **515 times across 29 stages**; run 4's `specialist_ui_ux_0` received it 115
times. Withholding the bytes cuts what a redundant read costs and moves the stage to a different
file rather than to work. What moves this model is an error: the `node -e` refusal is answered
correctly 49% of the time and retried 9% of the time — the opposite profile — because a refusal
arrives in the channel the model reads as "that did not work".

So past twice the exit threshold, a read that returns nothing the stage has not already been given
**fails**. Only a provably redundant read is refused; a range never read still returns content,
`grep` still works, and a write resets the count.

**Context for whoever picks this up:** 55% of every file read in this harness's history (2,134 of
3,888 across 13 runs) asked for a file nothing had touched since that same stage last read it, and
five files — `app.js`, `index.html`, `package.json`, `app.test.mjs`, `styles.css` — are 78% of it.

### 3.6 Control plane and operations

| commit | change |
|---|---|
| `43e3bf9` | per-run cost accounting with a real price table, and a `MAX_RUN_COST_USD` ceiling that pauses rather than fails |
| `b436eca` | a bound on how many runs may execute at once — there was none, and two runs contending for the single model server halved throughput |
| `56cfb69` | cancellation reaches the graph between supersteps instead of only at the task |
| `eb03e39` | a cancellation no longer tries to store a `SystemExit` it cannot serialise |
| `de9254d` | the startup sweep no longer resurrects a run that is already running; a 120-second grace defers the judgement, and the deferral is logged rather than silent |
| `0129517` | workspaces are segmented by tenant |
| `a8c7284` | run metrics are reduced from the transcript instead of a second table that could disagree with it |
| `1d98fea` | the context window is measured by probing when the server refuses to name it |
| `29fab13` | a transport that cannot carry the reply budget says so before the run pays for it — `trycloudflare.com` cuts off any reply over ~100s, and at 30 tokens/second a 13,000-token answer needs 433s, so a full-length reply cannot arrive |
| `e7bc644` | proxy origin timeouts are named, and metrics cross the process boundary |
| `7653ad7` | schema creation is serialised so a cold start does not race |
| `6625392` | the deployment generators emit non-root images with a `.dockerignore` and refuse unsupported languages instead of writing a comment into a `Dockerfile` |
| `7fb8ca9`, `4445705` | `manage.py workspaces` — reports size, age and run status; two separate flags to delete anything; and it now finds the six workspaces that predate tenant segments, which it had been listing as `.git` and `docs` directories |
| `c268b70` | `manage.py checkpoints` — the same shape for graph state. Nothing pruned these: 144 MB of database for 14 runs, 136 MB of it checkpoints, across 522 threads |
| `fc7740b` | restored 47 routing tests and stopped counting guards as failures |

---

## 4. Verified working in production — do not rebuild

Each of these was checked against live output, not inferred.

- **Budget-edge tool withholding** — fired 9 times across runs 13 and 14; both runs finished with
  zero stage restarts, against run 12's three restarts and death.
- **The read escalation ladder**, including the window-resize hole: verified in the deployed image,
  whole file 3,410 chars, then three narrowed windows of already-served lines, then withheld at 628.
- **Orphan recovery and its grace** — deferred correctly on a live run ("too recent to call
  abandoned"), recovered a genuinely dead one, and salvaged its structured response without a retry.
- **The security reviewer now finds things.** It was 33 consecutive `passed` with no finding ever
  recorded; run 13 produced two substantive ones (plaintext localStorage, `npx serve .` exposing the
  whole working directory). It is handed its source inline, which is why.
- **No XSS in any generated product** — zero instances of `innerHTML` with interpolated user data
  across all eight products; every one uses `textContent`.
- **Playwright genuinely runs in this sandbox** — 34 browser tests with real pass/fail in run 5;
  10 browser tests executed at both verification gates in run 13.
- **The milestone reviewer scopes correctly** — run 14 accepted a milestone whose goal excluded
  `edit` and filtering, and held the product-wide findings as minor rather than blocking.

---

## 5. Measured and rejected

Three things that look like obvious improvements and are not. Each cost an hour to measure and would
have cost days to build.

- **Pre-loading the product's files into every specialist request.** 55% of all reads are redundant
  and five files account for 78% of them, so inlining looks obvious. The security reviewer is the
  one role already handed its source inline, and in run 13 it still made 13 `read_file` calls across
  8 model calls. Inlining raises the context floor and does not remove the reads.
- **Playwright correlating with failure.** The harness pushes every UI product toward Playwright,
  and two failed runs blocked on a Playwright suite nothing executed — so it looked like the harness
  causing its own failures. Of the eight stored products, the only earlier one that installed
  Playwright (run 9) is also the only earlier one that built and tested `edit`.
- **The security reviewer rubber-stamping.** Three of 41 reviews returned `passed` having made no
  tool call. They are handed the source in the request, so a review with no reads has still read the
  code — and the stage now produces real findings.

---

## 6. Open items

Nothing below is started.

1. **Push and deploy.** 9 commits are unpushed; the 8 code commits among them are not in the
   running image. Nothing else on this machine holds this work.
2. **`replace_lines` is the least reliable tool** — 27 of 46 calls errored (58.7%). Most are correct
   syntax refusals, but a distinct class is "Line N is not what you expected", the model's line
   numbers having gone stale between the read and the edit. Worth deciding whether the tool earns
   its place beside `edit_artifact`.
3. **The repeat-timeout refusal never changes.** The counter reached "already timed out 8 time(s)"
   on the same argv, with identical wording every time. Cheap, and it never escalates.
4. **Run 12's product ships red.** `6b511391`'s `todo-list-app` fails 5 of its own 45 tests — the
   four inline-edit cases and one filter case, all against the hand-built DOM mock. Nothing marks a
   failed run's workspace as not deliverable.
5. **One product parses localStorage unguarded.** Run 10's `task-manager/app.js` does
   `return raw === null ? null : JSON.parse(raw)` with a comment explaining why it is safe. Corrupt
   storage throws during load and the page renders nothing. No check reads storage parsing.
6. **Disk.** ~1.35 GB for 14 runs: 1.1 GB workspaces, 144 MB database, 107 MB transcripts. Both
   reclamation commands now exist and **neither has been run**.
7. **Part I items 3, 4, 5, 6, 10, 11, 13–16** of `harness-hardening-plan.md`, and Part III item 5
   (wiring the `deploy/` generators — their security defects are fixed, the wiring is not done).

---

## 7. Picking this up on another machine

```sh
git fetch && git checkout harness-hardening-session     # push from this machine first
docker compose build worker app && docker compose up -d worker app
docker compose exec -T worker celery -A app.server.tasks inspect active   # confirm idle first
```

**Never rebuild the worker while a run is in flight.** Replacing it kills the in-flight Celery task.
The run is not lost — the graph checkpoints and the startup sweep resumes it — but it costs a stage
and two minutes of orphan-recovery grace, and it muddies whatever the run was being observed for.

To start a run, POST the brief to `/api/runs` and then `/api/runs/{id}/start` with
`{"auto_approve": true}`. To audit one afterwards:

```sh
docker compose exec -T worker cat /app/data/transcripts/<run-id>.jsonl > /tmp/run.jsonl
python3 scripts/audit_run.py /tmp/run.jsonl [workspace]
```

The three numbers that matter from that script are refusals that prevented damage (the checks
working — deliberately not counted as waste), failures that cost the run (the number to drive down;
it went 2.6% → 1.5% → 0.4% across this session), and identical repeats in a stage.

The other half of an audit is the product itself: copy the workspace out, `npm install`, run its own
suite, and run `summarise_integration` over it with the brief. Every run in this harness's history
that shipped something broken shipped it with a green suite.
