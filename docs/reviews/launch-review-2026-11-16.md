# Launch review and plan (2026-11-16)

Plan only: nothing here is built. Six read-only reviews (past findings, security, reliability and operations,
product and UX, core engine, run data) at HEAD 4953f71c, deployed build a88c9671 (same `src/` and `scripts/`).
"Checked" means the main session re-read the code or log; "reported" means a reviewer's finding not yet re-checked.
No exploit was run and no test was executed, so every "fails on the old code" is still to be proven at build time.

## 1. Verdict

**Not launch ready as a general "build a product from a brief" tool. Launchable in a narrow scope after Phases 1-3.**

- On its 12 small benchmark briefs the harness scores full on about 90% of runs (353 of 422 scored; 92% in the
  latest full week). Reported.
- On briefs that are not a benchmark (the low, medium and high test briefs), 1 of 19 admin-account runs has ever
  completed. The two 12-hour runs of 11-15 were killed by a job time limit with one sprint of three or four
  accepted. Reported; the time-limit kills are checked in the worker log.
- RC35's 12 of 12 is weak evidence: at the measured loss rate (13 of the last 150 runs, 8.7%) a clean streak of
  12 happens about one time in three with no improvement, and the count was restarted after each break. Three of
  the twelve runs carry the harness's own `NON-DELIVERABLE.json` (checked: run-9ab7f322, run-9e6566c6, run-5a2ad76f).
- Every loss is silent: all 13 losses in the last 150 runs were reported "completed". Release gaps appear on 148
  of 150 runs, so they do not tell a good release from a bad one. Reported.
- Code that agents run is not isolated from the harness's own secrets, data and network. Reported, code-read only.
- A new user cannot install it from the docs, is shown a login that does not work, cannot download the product,
  and "start from existing code" does nothing. Checked (login text, start payload, handover pack contents).

## 2. Needs the owner now

| # | Decision | Why |
|---|---|---|
| O1 | Cancel run-c6c942bb (admin's run, on the paid Anthropic API) | Its job was delivered 10 times; 2 copies run in one workspace and 7 wait (checked in the worker queue and log). Both worker slots are held |
| O2 | Launch scope: narrow first (section 6) or wait for general briefs | Decides whether Phase 5 gates the launch |
| O3 | Single-user/self-hosted launch, or several users on one deployment | Decides whether the sandbox work (LR.30) gates the launch |
| O4 | Allow a hosted-model test matrix (LR.44) | The standing rule is no Anthropic API in testing |
| O5 | The RC rule: replace "12 clean, restart on a break" with a fixed-size frozen batch and a reported interval (LR.20) | Changes how readiness is counted |

## 3. The plan

Order: Phase 1 and 2 first (bugs that lose work, then a verdict a user can trust), Phase 3 (a user can install,
run and take the product), then 4-7. Each item is built with a test proven to fail on the old code, suite green,
one deploy per bundle. Effort: S under a day, M a few days, L a week or more.

### Phase 1 - bugs that lose work, money or secrets (one to two weeks)

| Id | Item | Evidence | Status | Effort |
|---|---|---|---|---|
| LR.1 | A queued run is redelivered hourly and run several times at once: exclusive per-run lock, visibility timeout above the job limit, prefetch 1, queued runs held in the database, `start_workflow` refuses a thread that has checkpoints | `src/app/server/tasks.py:43-70` (no transport options: checked), `driving.py:38-66`, `runner.py:1432-1464` | checked in logs; mechanism reported | M |
| LR.2 | The 12-hour job limit kills healthy runs and nothing resumes them; it is recorded as cancelled, then failed. Stop at a stage boundary and re-dispatch a resume, bounded by a total budget; or a no-progress watchdog in its place | worker log 22:48:57 and 23:09:41 UTC 11-15 (checked); `runner.py:2083-2105` | checked | M |
| LR.3 | Disk guard: `loop.sh ready` and the audit refuse to start below a free-space threshold and warn earlier; LM Studio logs rotated by cron; build cache pruned after a deploy | LM Studio logs back to 89G (checked); no free-space check in `src/app` or `scripts/loop` | checked | S |
| LR.4 | A fix that broke tests is committed as clean when the revert fails | `src/app/graph/engineering.py:954-973` (checked: the fall-through commits and saves) | checked | S |
| LR.5 | The best-attempt record is never reset across sprints or suite versions, and a tie keeps the oldest commit, so a put-back can erase later work | `src/app/graph/best_attempt.py:56-147`; no reset call anywhere in `src` (checked) | checked in part | S-M |
| LR.6 | An at-limit suite send-back can fail a run whose suite was lockable: snapshot the suite first and put it back if the result does not run | `src/app/graph/acceptance_nodes.py:843-880, 965-969` | reported | S |
| LR.7 | The three "once" flags of the suite lock are never reset (once per workspace, not per suite) | `acceptance_nodes.py:874, 879, 968`; `suite.unlock` | reported | S |
| LR.8 | A workspace file chooses which tool server the worker starts, with the worker's environment expanded into it: keep the cache outside the workspace, accept https addresses only, never a local command | `src/app/tools/mcp_registry.py:41` and `mcp_tools.py:50` (file and `stdio` transport checked) | checked in part | S |
| LR.9 | Harness git commands run on uploaded repositories with the full environment and no hardening: one helper with a minimal environment and safe settings; regenerate `.git/config` and hooks after seeding | only `src/app/server/changes.py:41` is hardened (checked) | checked in part | S-M |
| LR.10 | The viewer role can steer a run; `GET /api/settings` open to viewers | `src/app/server/runs.py:1189-1204`, `settings.py:50-56` | reported | S |
| LR.11 | Launch configuration: `ENV=production`, no literal signing key or admin password in `docker-compose.dev.yml`, `/metrics` and `/docs` closed, app behind TLS | reviewer's list M3, M5, M7 | reported | S-M |
| LR.12 | Login page prints "Default credentials: admin / admin", which is untrue | `langchain-ui/src/pages/Login.tsx:124` (checked) | checked | S |
| LR.13 | "Start from existing code" uploads the archive and never sends it with the start | `langchain-ui/src/pages/Home.tsx:251` (checked) | checked | S |
| LR.14 | A built-in fix can be silently turned off by a stored setting or host variable | `src/app/switches.py:193-214` | reported | S |
| LR.15 | Parallel mode: fix workers measure in one workspace with no lock; the mode is read per visit while the batch persists; the parallel request builder lacks the earlier reports | `src/app/graph/workflow.py:12032-12153, 10822-10928` | reported | S each |
| LR.16 | Hosted models: the diagnosis assumes an OpenAI-style client; a side call 404s on the Anthropic address; three hosted starts failed outright | worker log; reviewer's table | reported | M |

### Phase 2 - a verdict a user can trust (two weeks, partly runs)

| Id | Item | Why | Effort |
|---|---|---|---|
| LR.20 | Replace the RC rule: one frozen build, 8 runs per family (about 100), no restart on a break; report the full-score rate with its interval and the count of silent losses | 12 of 12 does not bound the loss rate below 22% | runs, about 5 days |
| LR.21 | Run status says what the harness itself believes: a run with `NON-DELIVERABLE.json` is not "completed"; one user-facing verdict (delivered / delivered with stated cuts / not deliverable) | 3 of 12 RC35 runs | S-M |
| LR.22 | Measure each release gap kind against hidden results over the last 150 runs; keep only gaps that predict a loss; the "contract not checked" gap is on 93% of runs | gaps carry no signal | M |
| LR.23 | Vacuous acceptance tests on larger briefs: a suite is not locked while its tests pass on the empty scaffold (52 of 97 on one run), including `if (response.ok())` guards | false "green" from the first round | M |
| LR.24 | Run the test suite under production switch defaults (today an autouse fixture turns all 39 built-in fixes off; checked at `tests/conftest.py:43-54`); then delete each dead off-branch | the shipped combination is tested only by benchmark runs | M |
| LR.25 | A quality set for every family (concurrency, limits, bad input, session lifecycle), as tasks-api has | delivered products ship plain-text non-expiring tokens, silent data loss, parallel-write timeouts | M |
| LR.26 | The single end-of-attempt decision (already designed, trigger met), with the suite-lock limits as one table | four point fixes in one day; LR.5-LR.7 are the same class | M |
| LR.27 | Lock held while a "cannot pass" finding stands; brief wording wins along the chain (per-role audit #1); the release re-measure fails closed | the recurring false-acceptance class (LF.910, LF.912) | M |

### Phase 3 - a new user can install, run and take the product (two weeks)

| Id | Item | Effort |
|---|---|---|
| LR.30a | Download the product (zip with its git history) and a "How to run it" card from the pack's commands | M |
| LR.31 | README quick start, licence, a user guide (model sizing, writing a brief, modes, reading the evidence, failures, steering), `.env.example` as the documented path; remove the operator password from `docs/HANDOVER.md` before any public release | M |
| LR.32 | Setup checklist on Home (model answers, commands can run, window detected); Start blocked with the reason; "Test connection" for any OpenAI-style server | M |
| LR.33 | Defaults for a first run: hands-off or timed reviews; notification prompt; webhook and email passed through compose (today the variables never reach the containers) | S-M |
| LR.34 | Failure cards: a class, what the user can do, the recommended action; raw text under Details. `awaiting_approval:` no longer shown as a failure place | M |
| LR.35 | Request a change on a delivered product and resume a failed run with a direction, from the UI | M |
| LR.36 | Users page, change password, logout, token rotation | M |
| LR.37 | One Controls page for the owner's features (instruction injection, parallel/linear per run, work orders, templates, the Sprint Record by that name); diagnose prompted after a model is saved | M |
| LR.38 | Small UI fixes: cancel copy, budget-stop status, server-side run search, one-tap approve restricted, example briefs, glossary | S each |

### Phase 4 - isolation (gates a multi-user launch only)

| Id | Item | Effort |
|---|---|---|
| LR.30 | Product commands run in a separate sandbox with no harness environment, only that run's workspace, and no route to the database, Redis or the host; until then a second uid, read-only `/app/src`, secrets in files, a non-superuser database role | M to L |
| LR.39 | Address pinning restricted to saved model profiles; private-address checks pinned to the resolved address; lessons kept per tenant; uploads bound to their run; rate limiter keyed on the verified user | S-M each |
| LR.40 | Per-run resource limits (processes, CPU, disk); installs without lifecycle scripts where the stack allows; image digests and `.dockerignore`; untrack the virtualenv in `.langchain/` | S-M each |

### Phase 5 - does it generalise (three to four weeks, mostly runs)

| Id | Item | Effort |
|---|---|---|
| LR.41 | Held-out briefs, written without sight of the fixes and never tuned against: 4 small with no Interface section, 3 medium (1,500-4,000 lines), 2 changes to an existing codebase, 1 data pipeline; 3 runs each | L |
| LR.42 | Scale the process to the brief: bounded specification and one design review, a time budget per sprint, visible scope cuts; target a medium brief inside a stated budget | L |
| LR.43 | Pack sweep: 2 runs each on Go, Rust, Java, C#, Django, Vue, Nest; a pack under 1 of 2 is marked unsupported (about 18 of 30 packs have no scored run) | runs |
| LR.44 | Model matrix on 4 families: one hosted frontier model, one mid hosted model, one small local model; publish a supported-models list (needs O4) | runs |
| LR.45 | Remove benchmark nouns from model-facing text (`agents/project_layout.py:26-36`, `agents/principal_architect.py:188-191`, `models/deep_diagnosis.py`) with a test banning them in assembled prompts | S |
| LR.46 | Narrow rules that misfire off-benchmark (closed CRUD verb list, "with ease and confidence" read as fields, sign-in detected only as Bearer tokens, runner totals for 5 runners): move behind the pack interface; a "rule could not apply" counter per check meanwhile | L |

### Phase 6 - engine structure and efficiency (after launch scope is met)

| Id | Item | Effort |
|---|---|---|
| LR.50 | Lift nodes out of the 4,178-line `build_workflow_graph` closure, node by node; convert source-pinning tests (338 files) to behaviour tests as each node moves | L |
| LR.51 | One workspace transaction layer for git and measurement that fails closed | M |
| LR.52 | Prompt cache: stop the reasoning-carry reset rewriting the prefix, stable documents before code in fixer memory, fold refusals on fixed boundaries, pin a model slot per stage thread | S-M each |
| LR.53 | Stop re-plans after a green or near-green suite; bound fix stages that close nothing (64% of defects stay open) | M |
| LR.54 | Prompt pass per role: remove contradictions and repeats; a contradiction test over assembled prompts | M |

### Phase 7 - operations and records

| Id | Item | Effort |
|---|---|---|
| LR.60 | Retention: nightly pruning of old checkpoints, workspaces and transcripts (Postgres 8.4G, workspaces 44G) | S |
| LR.61 | Backups off the data disk, the restore check run nightly, a written restore procedure | S |
| LR.62 | Notices for failed, queued too long, model unreachable, low disk; park a run when the model server is down and resume when it answers | S-M |
| LR.63 | Images tagged by commit with a rollback command; smaller connection pools; readiness used by the container health checks | S each |
| LR.64 | Records: rewrite STATE's switch tables and header, the per-role audit table, Appendix M status columns; one glossary | S |
| LR.65 | Conclude or remove: 13 switches on with no off runs, 9 built and never on; bundle 8 of the second harness review (24 switches, none built) is dropped or rescheduled explicitly | M |

## 4. Past findings

No item claimed fixed was found missing from the code. Approximate counts: 133 fixed with code and a test file
found, 73 partial, 87 open, 17 deferred (4 with their trigger met), 17 superseded, about 150 taken from the docs
only. The 13 items filed during the RC count are all still open or partial; they fold into the plan as:

| Filed item | Goes to |
|---|---|
| Single end-of-attempt decision; suite file as unit of repair; LF.911 for any green suite | LR.26 |
| Cause grouping for acceptance failures; fixers ending at their call budget | LR.53 |
| Uniqueness rule; save-then-type tests that do not wait | LR.25, with a measured check |
| Scratch-file deletes; redundant reads (M12); plan readiness self-repair | LR.52 bundle, S each |
| README usage second wording; `create_app` read as "create" | LR.46 |
| Milestone evidence gate (built, off, never measured) | LR.65 |

## 5. What is sound (keep)

Route authentication and tenant checks, password and token handling, archive extraction, encrypted model keys,
the child-process environment filter, orphan recovery, the deploy script's safeguards, run deletion, the plain
stage wording and evidence panels of the run page, pause/resume/rewind/clone, and the brief criteria preview.

## 6. Narrow launch scope (if launching after Phases 1-3)

Small, well-specified, single-service Python or JavaScript products on Qwen3.6-35B, single-user self-hosted,
with a stated time budget, the supported stacks listed, and the verdict of LR.21 shown. Everything else labelled
experimental until Phase 5 reports.

## 7. Not covered by this review

The path-escape and command-safety logic of `tools/repository.py` and `tools/sandbox.py` beyond a search; rewind
and resume after a kill mid-call (design read, not exercised); an actual restore; the live UI (source read only);
about 150 older findings and about 890 LF rows not sampled; known-vulnerability status of locked dependencies.
