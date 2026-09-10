# Context Compaction — Remediation Steps

This document records, step by step, everything that was done to remediate the
defects listed in [`context-compaction-remediation-plan.md`](context-compaction-remediation-plan.md),
the codebase-wide bug hunt that followed, and the improvements implemented on top.
Every step includes the evidence that proves it works.

**Final state:** `611 passed, 1 skipped` (full suite), coverage **83.00%** (> 80% target),
bandit **0 medium / 0 high** severity issues, `tsc -b` exit 0, Docker stack healthy.

---

## Part 1 — Plan defects (D-1 … D-3)

### Step 1: D-1 (critical) — restore the destroyed `start_review` import

**Problem.** `src/app/graph/workflow.py` referenced `start_review` in a node body,
but the import had been lost. Any run that reached the review stage would raise
`NameError` at runtime — and because the name only appears inside a function body,
the module imported fine, so nothing caught it at startup.

**Fix.** Restored the import at the top of `workflow.py` alongside the other agent
imports, and added `import logging` / `logger = logging.getLogger(__name__)` which
the overflow handling (Step 2) needs.

**Proof.** `tests/test_graph_invariants.py::test_every_name_the_graph_calls_is_imported`
statically extracts every name the graph node bodies call and asserts each one is
importable from the module. It fails on exactly this class of defect.

### Step 2: D-2 (low) — remove the duplicated overflow-helper block

**Problem.** The context-overflow helpers (`_CONTEXT_OVERFLOW_MARKERS`,
`_is_context_overflow`, `_context_overflow_update`) had been pasted into
`workflow.py` **twice**. Python silently rebinds the names, so it "worked" — but
the duplicate is a maintenance trap: fixing one copy and not the other would be
invisible.

**Fix.** Kept exactly one definition, placed between `WorkflowState` and
`def _is_paused(stage)`, and deleted the second copy.

**Proof.** New regression test
`tests/test_graph_invariants.py::test_the_overflow_helpers_are_defined_once`
counts occurrences of each helper's `def`/assignment in the source text and asserts
the count is exactly 1.

### Step 3: D-3 (low) — fix the stale `"truncated"` assertion

**Problem.** `tests/test_sandbox_in_container.py` asserted that truncated output
contained the literal word `"truncated"`, but `_truncate()` in
`src/app/tools/sandbox.py` produces a pointer of the form
`...[N bytes omitted; full output saved as {reference}]...`. The assertion was
stale relative to the implemented behavior.

**Fix.** Updated the assertion to check for the actual marker text produced by
`_truncate()`.

**Proof.** The test passes against the real `_truncate()` implementation (see
Part 4 verification).

---

## Part 2 — Plan defects in the compaction tests (P-1 … P-3)

All three were in `tests/test_context_compaction.py`, which was asserting against
the *shape* of the feature rather than its actual contract.

### Step 4: P-1 — assert on behavior, not on a private class name

**Problem.** The test asserted that the middleware object's class is named
`SummarizationMiddleware`. The real object deepagents constructs is
`_DeepAgentsSummarizationMiddleware` (a private subclass), so the assertion was
fragile against an implementation detail.

**Fix.** Replaced the class-name check with a behavioral one:
`hasattr(middleware[0], "wrap_model_call")` — i.e., assert the middleware actually
implements the hook LangChain calls, whatever its class name is.

### Step 5: P-2 — monkeypatch the module that actually looks up the symbol

**Problem.** The test patched `build_default_chat_model` at a path that
`role_agent.py` does not resolve through, so the patch was a no-op and the test
was exercising the real model factory.

**Fix.** Patch `"app.agents.role_agent.build_default_chat_model"` — the exact
attribute lookup performed inside the module under test.

### Step 6: P-3 — make the truncation-pointer regex match reality

**Problem.** The test parsed the journal reference out of the truncation pointer
with `saved as (\S+)`. The real pointer is `...saved as {ref}]...` — the closing
`]` is part of the same non-whitespace run, so `\S+` captured `ref]` and the
assertion compared against a corrupted value.

**Fix.** Changed the pattern to `r"saved as ([^\]\s]+)"`, which stops at the
bracket. Verified against `_truncate()`'s actual output.

---

## Part 3 — Regression tests for the graph (Step 6 of the plan)

`tests/test_graph_invariants.py` gained two structural guards so the D-1/D-2 class
of defects can never return silently:

1. **`test_every_name_the_graph_calls_is_imported`** — parses the node function
   bodies, extracts called names, and asserts each resolves in the module's
   namespace. Catches destroyed imports (D-1).
2. **`test_the_overflow_helpers_are_defined_once`** — asserts each overflow helper
   is defined exactly once in the source. Catches duplicate pastes (D-2).

Result: `35 passed` in that file.

---

## Part 4 — Triage of the 10 sandbox test failures (environmental, not code)

After the plan fixes, the full suite showed **10 failures**, all in
`tests/test_sandbox_in_container.py`. Investigation proved they are **host
environment** problems, not defects in the sandbox code:

**Root-cause chain:**

```
in-container mode
  → _execute_here()
    → _resolve_executable("python")
      → shutil.which("python", path=os.environ.get("PATH", ""))
        → None on this host (only `python3` exists, no bare `python`)
          → error dict instead of a result
            → KeyError: 'returncode' / 'stdout' in the test
```

**Proof.** A PATH shim that makes bare `python` resolvable — exactly what the
Docker image provides at runtime — turns all 31 in-container sandbox tests green:

```bash
mkdir -p /tmp/pyshim && ln -sf "$(pwd)/.venv/bin/python" /tmp/pyshim/python
PATH="/tmp/pyshim:$PATH" PYTHONPATH=src ENV=development .venv/bin/python -m pytest tests/ -q --no-cov
# → 611 passed, 1 skipped
```

The Docker image always ships `python`, so CI and the deployed stack exercise every
one of these paths; only this particular host lacks the bare name.

---

## Part 5 — Codebase-wide bug hunt (latent bugs found and fixed)

### Step 7: `principal_architect.py` crashed at import on a malformed env var

**Problem.** `INITIAL_DOCUMENT_BUDGET = int(os.environ.get("CTX_ARCHITECT_DOCUMENT_BUDGET", "40000"))`
ran at module scope. A typo like `CTX_ARCHITECT_DOCUMENT_BUDGET=40k` raised
`ValueError` **at import time**, taking the whole app down at startup — while every
other `CTX_*` value in the codebase degrades to a default with a warning.

**Fix.** Wrapped the parse in `_initial_document_budget()`, which catches
`ValueError`, logs a warning, and returns the default 40 000 — the same
never-raise convention as `ContextPolicy.from_environment`.

**Proof (smoke test).** Setting the env var to `"40k"` and importing the module:
warning logged, value is `40000`, no exception.

### Step 8: `runs.py` deleted context keyed by the wrong id

**Problem.** `delete_run` called `discard_context(record.thread_id)`. But the
compaction scratch space is keyed **per agent name**, not per run thread — see the
keying decision documented in `_compaction_middleware()` in
`src/app/agents/role_agent.py`. The call was therefore a silent no-op that
misrepresented intent.

**Why it must NOT be "fixed" by deleting the per-agent directory:**
the worker runs with `--concurrency=${CELERY_CONCURRENCY:-2}`
(`docker-compose.yml:207`), so two runs execute simultaneously and **share** the
per-agent context directories. deepagents keys each offloaded conversation by a
*per-invocation* session id (see
`.venv/lib/python3.12/site-packages/deepagents/middleware/summarization.py`), so
files never collide — but deleting the directory at one run's end would clobber
the other active run's in-flight scratch data.

**Fix.** Removed the no-op call and replaced it with a comment documenting the
decision and the accepted limitation (slow accumulation of small markdown files).
`discard_context()` itself remains available and is still unit-tested directly.

### Step 9: Cosmetic cleanups in `role_agent.py`

- Dropped the unused `checkpointer: Any` parameter from `_compaction_middleware()`
  (call sites verified single-arg by grep: definition + one call site in src, three
  in tests).
- Moved mid-file imports to the top of the module.
- Fixed inconsistent indentation.

---

## Part 6 — Improvements

### Step 10: `needs_python` skipif guard for honest host behavior

**Problem.** On a host without bare `python`, the 10 in-container tests *failed*
with `KeyError` — blaming the sandbox code for a PATH problem. Failing is less
honest than skipping, because the code under test is not what is broken.

**Fix.** Added a module-level marker in `tests/test_sandbox_in_container.py`:

```python
needs_python = pytest.mark.skipif(
    shutil.which("python") is None,
    reason="bare 'python' not on PATH; in-container mode resolves it via shutil.which",
)
```

and applied it to exactly the **10 tests that invoke bare `python`**. Tests that
never resolve a bare name (allowlist refusals, containment refusals, echo/curl
mode-selection tests) are deliberately unmarked and still run everywhere.

**Proof.**
- Without shim: `21 passed, 10 skipped` in the file — clean skips with an
  explanatory reason, zero failures.
- With shim (authoritative): full suite `611 passed, 1 skipped` — no new skips,
  because `shutil.which("python")` succeeds.

### Step 11: Removed a dead duplicate call in a test

`test_extra_env_reaches_the_command` contained a **pre-existing** (committed at
HEAD) duplicate `SandboxExecutor.execute(["python", "probe.py"], ...)` call that
ran *before* `probe.py` was written and whose result was discarded. It was removed;
the test now writes the probe, executes once, and asserts on stdout.

---

## Part 7 — Verification evidence

| Check | Command | Result |
|---|---|---|
| Full suite (authoritative) | `PYTHONPATH=src ENV=development PATH="/tmp/pyshim:$PATH" .venv/bin/python -m pytest tests/ -q --no-cov` | **611 passed, 1 skipped** (92.88 s) — exact plan match |
| Suite without shim | same, minus the PATH prefix | sandbox file: 21 passed, 10 skipped; no failures |
| Coverage | `pytest --cov` | **83.00%** (> 80% target) |
| Bandit | `.venv/bin/python -m bandit -r src/app -ll` | severity: **Low 15, Medium 0, High 0** |
| Frontend types | `npx tsc -b` in `langchain-ui/` | exit 0 |
| Graph routing | `pytest tests/test_graph_routing.py` | 38 passed |
| Docker stack | `docker compose up -d` | all 5 containers healthy; health endpoint `{"status":"ok","db":"ok","redis":"ok","celery":"ok"}` |
| Worker middleware | worker log check | `enabled: True, trigger: 60000 tokens, attached: True` |

**Bandit reading note:** bandit prints *two* summary sections — "by severity" and
"by confidence". The numbers that matter for the plan's gate are the **severity**
ones (Medium 0 / High 0); a Medium/High count seen in the tail of the output may
belong to the confidence section.

---

## Changed files

| File | Change |
|---|---|
| `src/app/graph/workflow.py` | D-1 import restored; D-2 duplicate block removed; overflow handling wired into both `_run_gated_agent` branches; logging added |
| `src/app/agents/role_agent.py` | `_compaction_middleware()` finalized (single-arg, per-agent keying documented); cosmetic cleanups |
| `src/app/agents/principal_architect.py` | Import-safe budget parsing (`_initial_document_budget()`) |
| `src/app/server/runs.py` | No-op `discard_context` call removed + decision documented |
| `src/app/tools/sandbox.py` | `_truncate()` journal pointer (pre-existing feature, now covered by fixed tests) |
| `tests/test_sandbox_in_container.py` | D-3 assertion fixed; `needs_python` marker (10 tests); dead duplicate call removed |
| `tests/test_context_compaction.py` | P-1/P-2/P-3 fixes |
| `tests/test_graph_invariants.py` | Two structural regression tests added |
| `.env.example`, `docker-compose.yml` | 12 consistent `CTX_*` entries each (feature config) |
| `src/app/agents/context_policy.py`, `src/app/agents/context_store.py`, `src/app/tools/journal.py` | New feature modules (context policy, per-agent store, truncation journal) |

## Concepts introduced

- **Structural regression tests** — parsing the module's own source to assert
  invariants (imports present, helpers defined once) that unit tests cannot see.
- **Never-raise env parsing** — malformed `CTX_*` values log a warning and fall
  back to defaults instead of crashing import/startup.
- **Per-agent vs per-run keying** — compaction scratch space is keyed by agent
  name because the thread id is minted per attempt inside `_run_gated_agent`;
  safe under worker concurrency > 1 because deepagents keys files by a
  per-invocation session id.
- **Honest test skipping** — `skipif` on an environment precondition
  (`shutil.which("python")`) so host PATH gaps skip with a reason instead of
  failing the code under test.
- **Truncation journaling** — oversized sandbox output is head/tail-truncated in
  context, with the full output journaled to `DATA_DIR/journal/` and a reference
  embedded in the pointer.

## Remaining limitations (accepted, documented)

1. ~~**Per-agent context accumulation.**~~ **Resolved** by the follow-up work.
   Both scratch trees - `DATA_DIR/context/<agent_name>/` and `DATA_DIR/journal/` -
   are pruned by age at every terminal stage via `WorkflowRunner._prune_scratch`,
   configurable through `CTX_CONTEXT_RETENTION_HOURS` and
   `CTX_JOURNAL_RETENTION_HOURS` (default 72 hours; 0 disables). Age-based rather
   than run-scoped, because worker concurrency means two runs share the per-agent
   directories and deleting one at a run's end would clobber the other's
   in-flight scratch data. Empty directories are deliberately left in place for
   the same reason.
2. **Pre-existing crash-on-malformed-env pattern.** ~18 other module-scope
   `int(os.environ.get(...))` sites across `src/app/server/` and `tools/sandbox.py`
   share the old unguarded pattern. This is a codebase-wide convention; only the
   site on the compaction feature's critical path (`principal_architect.py`) was
   hardened. A mass refactor was deliberately out of scope.
3. **Docker production image excludes pytest** (runtime-only deps), so the
   in-container full suite is not a verification path — host runs with the PATH
   shim are authoritative.
