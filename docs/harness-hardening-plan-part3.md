# Harness Hardening Plan — Part III

**Additional improvement opportunities found in code review, beyond Parts I and II.**

**Date.** 2026-09-18.
**Method.** Read of `src/app` (36,603 lines across 8 packages), `tests/` (187 test files),
`pyproject.toml`, and the compose stack. Every finding below names a file and states how it was
verified. Where a claim is a measurement rather than a reading, it says so.

**Scope.** Part I hardens the agent loop against its own measured failures. Part II adds live API
knowledge. Neither addresses the *platform* the harness runs on: the control plane, the
observability stack, the deployment artifacts, and the resource model that decides whether two
runs can coexist. That is what this part covers.

**Relationship to Parts I and II.** Every item here is independent of the first two. Two have a
dependency on Part I's Phase 1 and are marked for it — the rest can be taken in any order. Nothing
here re-opens a decision Parts I or II made.

---

## 1. What the review found: five areas Parts I–II do not touch

Part I is about the model and the tools. Part II is about knowledge. Five things sit outside both,
and each contains at least one component that is silently not working today.

| area | what is there | what is missing |
|---|---|---|
| **A. Observability** | a transcript that works, a metrics endpoint that mounts, a cost handler that exists | the metrics and cost handlers are never wired, so `/metrics` reports zeros and no run has a cost |
| **B. Deployment artifacts** | three generators that emit Dockerfile, compose and CI for the product | they are unreachable from the workflow, and what they emit is not secure by default |
| **C. Resource model** | a worker that will run any number of runs concurrently | no concurrency control, no per-run cost ceiling, no isolation between tenants on disk |
| **D. Lifecycle** | cancellation by flag and task revoke | no cooperative cancellation inside the agent loop; a run cannot be stopped between supersteps cheaply |
| **E. Dependency hygiene** | a pinned dependency list | one undeclared load-bearing dependency, one declared dependency never imported, and a coverage configuration that hides the whole pattern |

The single most consequential finding is in **E**, because it is the mechanism that let **A** and
**B** happen undetected. It is stated first below for that reason.

---

## 2. The mechanism that hid it: coverage omits every unwired module

`pyproject.toml`, `[tool.coverage.run]`:

```toml
omit = [
    "src/app/main.py",
    "src/app/deploy/*",
    "src/app/scaffolding/*",
    "src/app/analysis/*",
    "src/app/build/*",
]
```

Every module in §3 and §4 below lives in a directory this list omits. Nothing measures whether
they are called, so nothing discovers that they are not. Part I's §1-B established the codebase's
own recurring mistake — a rule defined over part of the set it applies to. This is that mistake in
build configuration: the omit list was written to exclude entry points and generators exercised
end-to-end, and it silently grew to cover an entire class of defect.

**Fix (item 1).** Replace the directory globs with per-file entries for the genuinely
end-to-end-only modules, and add a test that asserts every public class and function in `src/app`
has at least one caller outside its own module. That test is the §1-B rule applied here: it fails
on the next unwired module rather than on the ones already found.

**Priority, measured.** This is the cheapest item here and it unlocks the detection of the rest.
It is also the only one whose absence has already cost real work: `BuildVerifier` carries a
comment noting it is not wired in, which means the pattern was noticed once and nothing prevented
it recurring.

---

## 3. Observability: two handlers that never run

### 3.1 `MetricsTracker` has no callers — `/metrics` reports zeros

`src/app/observability/metrics.py` defines three counters and a histogram:
`defects_resolved_total`, `defects_failed_total`, `stage_duration_seconds`, `run_total`. A grep
for `record_run|record_defect_resolution|record_stage_duration|get_metrics_payload` across all of
`src/` returns four matches — all four inside `metrics.py` itself. The endpoint in
`api.py::_mount_metrics` mounts and serves, and every counter stays at its initial value forever.

This matters more than an unused feature, because the endpoint is the basis for an operator's
trust. A dashboard that reports `defects_resolved_total 0` on a system that has resolved defects
is worse than no dashboard: it reads as "nothing has ever worked."

**Fix (item 2).** Wire the three recorders at the points that already know the answer —
`record_run` in `runner.start_run`, `record_stage_duration` in the stage-transition event
publisher, `record_defect_resolution` in the sprint remediation loop where a defect is closed or
abandoned. Then add a test that asserts each counter increments on the corresponding path. The
test is the deliverable; the wiring is small.

### 3.2 `CostTrackingCallbackHandler` is never registered, and its rates are fictional

`src/app/observability/cost_tracker.py` is a complete, careful handler — it even has the fix for
streamed responses reading `usage_metadata` off the aggregated message rather than
`llm_output["token_usage"]`, which is the exact bug that makes most cost trackers report zero.
It is not attached to any model. A grep for `CostTrackingCallbackHandler` across `src/` finds only
its own definition.

Two further problems wait inside it once it is wired:

1. **The rates are hardcoded to GPT-4o-mini.** Line 58: `(p_tokens * 0.15 / 1_000_000) +
   (c_tokens * 0.60 / 1_000_000)`. This deployment's default is a *local* model
   (`LLM_PROVIDER=local`), whose marginal cost is electricity. Reporting a fabricated dollar
   figure for a local model is not an approximation, it is a wrong number presented as a
   measurement.
2. **It has no per-run scope.** The handler accumulates into instance attributes with no run id,
   so it cannot answer "what did this run cost", which is the only question an operator has.

**Why this is urgent now.** `docker-compose.yml` wires `ANTHROPIC_API_KEY` and `GOOGLE_API_KEY`
through to the worker, and `settings.py` lets an administrator add either at runtime. The harness
can already spend real money, and it has no cost accounting, no budget ceiling and no alert. Every
other resource in the system — memory, CPU, PIDs, gates, supersteps — has a bound. Token spend
does not.

**Fix (item 3).** Register the handler on model construction in `models/__init__.`, scope
accumulation per run id, and replace the constant rates with a price table keyed by provider and
model id, absent for local providers. Pair it with item 8 (§5): a per-run cost ceiling that pauses
the run for a human decision rather than silently continuing.

### 3.3 The transcript is the one observability component that works — build on it

`observability/transcript.py` is well-designed and is wired: it records unclipped
`model_request`/`model_response`/`tool_call`/`tool_result`/`note` lines to
`DATA_DIR/transcripts/<run_id>.jsonl`, post-middleware, and never raises. Part I's §3.5 proposes
`run_metrics` as a table; the cheaper path is to derive it from the transcript that already
exists, because the transcript already holds every number §3.5 wants (tool calls by kind, failure
rate, repeat rate, latency) and the audit scripts from the original session already read it.

**Fix (item 4).** A `transcript_metrics(run_id)` function that reduces the JSONL into the
`run_metrics` shape, called at stage end and run end. No new table until the reduction is proven;
the transcript is already the source of truth and adding a second one repeats the two-copies-drift
mistake the codebase made with run state.

---

## 4. Deployment artifacts: three generators that nothing calls

`src/app/deploy/` contains `DockerGenerator`, `ComposeGenerator` and `CIGenerator`. A grep for
those three class names across all of `src/` returns three matches — one per file, each the class's
own definition. Nothing imports the package. This is the same shape as Part I's B5
(`app/scaffolding/` is unreachable, discovered while auditing run-04576307), in a different
package, and it has the same cause: no caller, no test that asserts a caller, and a coverage omit
that would not have shown the gap.

Part II's §3.2 makes the harness able to *build and test* any language. These three modules are how
the product it built becomes deployable, and they are not reachable.

### 4.1 What they emit is not secure, independent of being unwired

Read on their own terms, the templates have four defects that would ship the moment they were
connected:

| file | defect | consequence |
|---|---|---|
| `compose_generator.py` | `POSTGRES_PASSWORD: password`, `MYSQL_ROOT_PASSWORD: password` | a generated compose file ships plaintext default credentials; the harness's own compose refuses to start without a real one |
| `docker_generator.py` | no `USER` directive in any of the five language branches | every generated image runs as root, which is the exact posture `docker-compose.yml` was written to avoid |
| `docker_generator.py` | `COPY . .` after `npm ci`/`uv pip install` | layer caching is defeated and the source is copied over the installed tree |
| `ci_generator.py` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | generated CI pipes a script from the internet into a runner |

The last one is worth pausing on. The harness's own `seeding.py` refuses `ext::` git transports
because a URL should not be able to execute code, and `sandbox.py` refuses `python -c` for the same
reason. The CI generator writes the pattern those two modules exist to prevent into a file that
will run on every push of the product it builds.

### 4.2 The language coverage is narrower than the stack selector's

`docker_generator.py` handles python, node, go and java/kotlin. `ci_generator.py` handles the same
four. The stack selector and the sandbox toolchains also know about rust, csharp, ruby, php, swift,
dart and elixir — the set Part I's B2 measured as 34 allowed executables. A Rust or C# product
falls through to `# Unsupported language {{ lang }}` in the Dockerfile and
`echo "No automated CI steps defined for this language"` in CI, which is a silent no-op rather
than a refusal.

**Fix (item 5).** Two parts, deliberately in this order.

1. **Decide whether to wire them at all.** That is a product question, not a code one, and it
   should be answered before any work: does this harness ship deployment artifacts for the
   products it builds, or does it stop at a tested working tree? If no, these three modules should
   be deleted rather than fixed — 340 lines of unreachable code that emits insecure output is a
   liability, and `verifier.py` in `build/` is a fourth.
2. **If yes:** fix the four defects in the table, extend coverage to every language the stack
   selector can choose (the §1-B rule — one test asserts the generator set equals the toolchain
   set), and add a test that asserts a generated Dockerfile contains a non-root `USER` and no
   default password.

---

## 5. Resource model: no bound on what a run may consume

Part I's class C is about constants measured on one model. This is a different problem with the
same symptom: thresholds that cannot fire because the quantity they bound is unbounded.

### 5.1 No concurrency control

There is no `MAX_CONCURRENT_RUNS`, no Celery prefetch configuration, and no per-tenant limit
anywhere in `src/` (a grep for `MAX_CONCURRENT|worker_concurrency|prefetch|rate.*per.*tenant`
returns nothing). `tasks.py` sets `worker_max_tasks_per_child` but nothing limits how many tasks
run at once. Two unattended runs started against one local model server share that server's queue,
and neither has any way to know its latency is being caused by the other.

**Why that contaminates Part I.** Phase 1 of the existing plan derives the request timeout from a
*measured* generation rate, replacing `MIN_EXPECTED_TOKENS_PER_SECOND = 40` which broke on
North-Mini-Code's 33.0. That derivation is only valid if the probe measures the model when it is
the only load. On a contended server the probe measures a rate the run will not see, or vice versa,
and the timeout is wrong in whichever direction the contention happens to push it. Item 2 of the
existing backlog should be gated on this, or it will measure a number that is true at probe time
and false for the rest of the run.

**Fix (item 6).** A configurable concurrency limit enforced at dispatch in `runner._dispatch`,
with the current in-flight count exposed on the readiness endpoint so an operator can see it.
Celery's `worker_concurrency` is the mechanism; the limit should also be visible to the API because
a full worker is the difference between "queued" and "broken" and nothing currently distinguishes
them.

### 5.2 No per-run cost ceiling

As §3.2: the harness can spend money and has no bound on it. Every other resource is capped.

**Fix (item 8).** A `MAX_RUN_COST_USD` setting, checked at stage boundaries against the
accumulating cost from item 3. On exceeding it the run pauses at the next gate with a message
naming the spend, exactly as `_context_overflow_update` handles the one other resource that can
exhaust silently. A pause, not a failure: the work is good and the operator may simply raise the
ceiling.

### 5.3 Tenants are isolated in the database and shared on disk

`tenant_id` is enforced consistently in the API (`_require_run` returns 404 across tenants, and
`progress.py` re-checks it on the WebSocket) and in `run_store` queries. It is not enforced in
workspace allocation: `workspaces.py::allocate_workspace` places every run under one flat
`WORKFLOW_WORKSPACE_ROOT`, with no tenant segment in the path.

Nothing today reads another tenant's workspace through the API — the containment checks hold. But
the boundary is *accidental*: it depends on every path-taking tool resolving inside the workspace,
and on no future tool accepting an absolute path. The database boundary is deliberate; the
filesystem one is not.

**Fix (item 9).** Segment the workspace root by tenant —
`WORKFLOW_WORKSPACE_ROOT/<tenant>/<label>-<run_id>` — with the existing containment check
unchanged beneath it. Low effort, and it makes the two boundaries agree by construction rather
than by coincidence.

---

## 6. Lifecycle: cancellation cannot reach the agent loop

`runner.cancel_run` does two things: sets `cancel_requested` in the database, and calls
`celery_app.control.revoke(..., terminate=True, signal="SIGTERM")`. The flag is checked in
`tasks.py:152` and at two points in `runner.py`. That is correct as far as it goes, and the
two-mechanism design is the right one — revoke handles a task that has not started, the flag
handles a clean stop at the next checkpoint.

The gap is granularity. A SIGTERM to a worker mid-`agent.invoke` kills the turn wherever it is,
and the run resumes from the last *checkpoint*, which for a specialist stage can be a full stage
of work back. There is no cooperative signal into the invoke loop itself, so there is no way to
stop a run between supersteps without losing the in-flight one.

**Fix (item 7).** Check the cancel flag inside the stage-transition callback that already runs
between supersteps, and raise a dedicated `RunCancelled` exception that the invoke loop catches to
persist state and exit cleanly. This is a small change to the existing callback seam — the
infrastructure is there, it is simply not consulted at the finest available granularity.

---

## 7. Dependency hygiene

### 7.1 `cryptography` is undeclared and load-bearing

`runtime_settings.py::_fernet` imports `cryptography.fernet.Fernet` to encrypt provider API keys
stored in the `runtime_secrets` table — the credentials an administrator sets through the Settings
page. `cryptography` is **not** in `pyproject.toml` (verified by grep). It resolves only
transitively, and is present in the working venv at 50.0.1.

This is the highest-severity item here, and it is not theoretical. A dependency upgrade that drops
the transitive pull, or a fresh container resolved differently, breaks *credential decryption at
runtime* — not at install, and not with an import error at a startup check. The failure surfaces
as provider keys that cannot be read, on a deployment that was working the day before, with an
error message that names the credential and not the missing package.

**Fix (item 10).** Add `cryptography>=42.0.0` to `[project].dependencies`. One line. Verify with a
clean-container install afterwards.

### 7.2 `hvac` is declared and never imported

`pyproject.toml` declares `hvac>=2.3.0` (HashiCorp Vault client). A grep for `hvac|Vault|vault`
across `src/` returns three matches, all in `runtime_settings.py` docstrings referring to
`SETTINGS_ENCRYPTION_KEY`. The only secret backend is Fernet.

**Fix (item 11).** Either remove the declaration, or — if Vault integration is intended — record
that as a decision. Leaving an unused security-adjacent dependency declared is how an audit later
concludes Vault is configured when it is not.

### 7.3 Part II's dependency needs a compatibility check

Part II §10.1 adds `tree-sitter-language-pack>=1.20.0`. Verified in the working venv: no
`tree_sitter` module is present, so it is a genuinely new dependency. Part II already notes the
manylinux/glibc requirement and asks for a clean-container confirmation; that check should also
confirm the pack's `tree-sitter==0.26.0` pin does not conflict with anything else in the tree.
This is a reminder, not a new finding.

---

## 8. Prioritised backlog

| # | item | area | effort | impact | acceptance test |
|---|---|---|---|---|---|
| 1 | Coverage omit narrowed to per-file; dead-code test asserts every public symbol has a caller | E | S | **high** — detects the class, not the instances | the test fails on the next unwired module |
| 2 | Wire `MetricsTracker` recorders at the points that know the answer | A | S | high | each counter increments on its real path |
| 3 | Register `CostTrackingCallbackHandler`, scope per run, replace hardcoded rates with a price table | A | M | high | a run reports its own cost; a local model reports none |
| 4 | `transcript_metrics(run_id)` reduces the existing transcript into the `run_metrics` shape | A | M | med | stage-end metrics come from the transcript, not a new table |
| 5 | Decide on `deploy/` + `build/`: delete, or fix the four defects and extend to every stack selector language | B | S–M | high | generated Dockerfile has a non-root `USER` and no default password; generator set == toolchain set |
| 6 | Concurrency limit at dispatch, in-flight count on the readiness endpoint | C | S | high | a second run waits rather than contending; Phase 1's probe measures an uncontended rate |
| 7 | Cooperative cancellation in the superstep callback | D | S | med | a run stops between supersteps without losing the in-flight turn |
| 8 | `MAX_RUN_COST_USD` ceiling, pauses at the next gate naming the spend | C | S | high | a run pauses rather than continuing past the ceiling |
| 9 | Tenant segment in the workspace path | C | S | med | two tenants' workspaces are disjoint by construction |
| 10 | Declare `cryptography>=42.0.0` | E | S | **high** | clean-container install resolves it directly |
| 11 | Remove or implement `hvac` | E | S | low | declared dependencies are all imported |

Effort: S ≤ half a day, M 1–3 days.

**Order.** 10 first — it is one line and it is the only item here that can break a working
deployment. Then 1, because it is the detection mechanism for the rest. Then 5's *decision*, which
costs nothing and determines whether 5 is work or deletion. Then 2, 3 and 8 together, because they
are the same feature at three layers (measure, account, bound) and 8 is unsafe without 3.

**Two items gate Part I.** Item 6 must land before the existing backlog's item 2 (`ModelProfile`
probe), or the probe will measure a rate contended away from it. Item 1 should land before any of
Part II's new packages, or `src/app/knowledge/` can accumulate unwired modules the same way
`deploy/` and `build/` did.

---

## 9. What this part deliberately does not do

- **No rewrite.** Every item extends an existing module; the transcript, the callback seam, the
  dispatch point and the stage-transition publisher all already exist.
- **No new security surface.** Items 9 and 10 close gaps; none opens one. Item 5's CI-template fix
  *removes* an insecure pattern rather than adding a control.
- **No measurement from a single run.** Unlike Part I, this part is grounded in code reading, not
  run transcripts, because the defects here are that nothing ran at all. Where a quantity is
  asserted (34 executables, 187 tests, 36,603 lines), it was counted.
- **No overlap with Parts I or II.** Checked item by item. The two dependencies noted in §8 are
  sequencing constraints, not re-opened decisions.

---

## 10. One observation about the codebase, not a finding

The modules in §3 and §4 are individually well-written. `cost_tracker.py` contains the exact
streamed-response fix that most cost handlers get wrong. `transcript.py` is the most careful
component in the repository. `deploy/docker_generator.py` handles five languages with correct
multi-stage builds. Their failure is not quality of implementation; it is that nothing connects
them to the system they were written for, and nothing was configured to notice.

That is the same root cause Part I §1-B names — a rule applied to part of the set it governs —
arriving in a place Part I did not look. Item 1 is the fix for the pattern rather than for any one
instance of it, which is why it is ranked above the individual modules it would have caught.
