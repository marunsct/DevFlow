# Remediation Plan — Context Compaction Implementation Review

**Reviewed:** the implementation of `docs/context-compaction-implementation-plan.md`
**Method:** every claim below was produced by running the code, not by reading it.
**Verdict:** the implementation is substantially correct. One critical defect, one cosmetic duplicate, and one stale assertion. Three further test failures are defects in **my** plan, not in your work.

---

## Part 0 — Summary

### What you got right

All seven phases landed, and the parts that are easy to get wrong are right:

| Phase | Status |
|---|---|
| 1 — `context_policy.py` | Correct. 101 lines, `CTX_*` read from the effective environment. |
| 2 — `context_store.py` | Correct. 80 lines, `FilesystemBackend`, contained under `DATA_DIR`. |
| 3 — `role_agent.py` wiring | Correct. `middleware=` passed, **no `backend=` added** — the security constraint held. |
| 4 — overflow guards | Logic correct, both invoke paths guarded. Placement damaged — see D-1. |
| 5 — `INITIAL_DOCUMENT_BUDGET` | Correct, applied to the first request. |
| 6 — journal + `_truncate` | Correct, both call sites labelled, head **and** tail kept. |
| 7 — `.env.example`, compose, `runs.py` cleanup | Correct. 11 `CTX_` entries in `.env.example`, 9 in compose, `discard_context` wired. |

Two judgement calls you made that the plan did not spell out, and both were right:

- You added a local `import logging` inside `_context_overflow_update`. My snippet called `logger.error(...)` assuming a module-level logger. **`workflow.py` has none.** Following my text literally would have raised `NameError` on the first overflow. You noticed and worked around it.
- You did not add `backend=` to `create_deep_agent`. That was the single most dangerous thing in the original draft, and it stayed out.

### What is broken

```
13 failed, 596 passed, 1 skipped
```

| ID | Severity | What |
|---|---|---|
| **D-1** | **Critical** | `start_review` import destroyed. All three review gates raise `NameError`. 10 test failures. |
| D-2 | Low | The overflow block is present twice, identically. Dead code. |
| D-3 | Low | `_truncate` wording changed; one pre-existing test asserts the old word. |
| P-1 | — | *My plan's* test asserts the wrong class name. |
| P-2 | — | *My plan's* test monkeypatches an unreachable target. |
| P-3 | — | *My plan's* test regex cannot parse the format *my plan* specified. |

D-1 is the only one that affects a running system. It is also the only one that is genuinely your paste rather than my text — and Part 3 explains why my text made it likely.

---

## Part 1 — Defect register

### D-1 — `start_review` import destroyed (critical)

**Evidence:**

```
NameError: name 'start_review' is not defined
  src/app/graph/workflow.py:658 in _run_review_gate
    review = reviews.get(review_point) or start_review(
```

```
$ git diff src/app/graph/workflow.py | grep -E "^[-+].*(start_review|import logging)"
-    start_review,
+    import logging
+    import logging
```

**What happened.** The Phase 4 block was pasted *inside* the `from app.review import (...)` statement, overwriting the line `    start_review,`. The import list is still syntactically valid — it just lost one name — so Python imports the module fine and fails only when a review gate actually runs.

**Current state:**

```python
from app.review import (
    ReviewRerunLimitExceeded,
    approve_review,
    build_revision_prompt,
    request_changes,
    skip_review,
)                       # <- start_review was here
```

`app.review` does export it:

```
['DEFAULT_MAX_REVIEW_RERUNS', 'ReviewRequestStatus', 'ReviewRerunLimitExceeded',
 'ReviewStatus', 'WorkflowStage', 'approve_review', 'build_revision_prompt',
 'request_changes', 'skip_review', 'start_review']
```

**Blast radius.** `_run_review_gate` is the shared implementation behind all three optional review gates:

- `user_review_product_intake`
- `user_review_specification`
- `user_review_sprint`

Any run started with `review_policy` enabling any of them fails at that gate. Ten routing tests catch it.

Note it does **not** affect unattended runs — those disable every review gate, which is why the failure could sit unnoticed if you only ran unattended.

---

### D-2 — The overflow block exists twice (low)

**Evidence:**

```
103:_CONTEXT_OVERFLOW_MARKERS = (
113:def _is_context_overflow(error: BaseException) -> bool:
123:def _context_overflow_update(stage_name: str, error: BaseException) -> dict[str, Any]:
370:_CONTEXT_OVERFLOW_MARKERS = (
380:def _is_context_overflow(error: BaseException) -> bool:
390:def _context_overflow_update(stage_name: str, error: BaseException) -> dict[str, Any]:
```

`diff` of the two ranges: identical.

**Impact.** None at runtime — the second definition shadows the first and they are the same code. It is dead code and a maintenance trap: a future fix applied to one copy silently does nothing.

It is the second symptom of the same bad paste as D-1.

---

### D-3 — Stale assertion on truncation wording (low)

**Evidence:**

```
E  AssertionError: assert 'truncated' in
   'xxx...\n\n...[4921 bytes omitted; full output saved as
    1788968302-backend_specialist-python-stdout-96c66888.log]...\n\nxxx'
```

`tests/test_sandbox_in_container.py::test_output_is_truncated` asserts the word `truncated`. The new `_truncate` says `omitted`.

**The implementation is correct; the test is stale.** The new message is better — it reports the exact byte count and the journal reference. The old test asserted an implementation detail rather than the behaviour.

My plan changed `_truncate` and never told you to update the test that asserted its old wording. That is my omission, listed here because it still has to be fixed.

---

### P-1 — My test asserts a class name that does not exist

```python
assert type(middleware[0]).__name__ == "SummarizationMiddleware"
```

The real object:

```
[<deepagents.middleware.summarization._DeepAgentsSummarizationMiddleware object at 0x...>]
```

`SummarizationMiddleware` is a factory that returns a `_DeepAgentsSummarizationMiddleware`. **Your middleware is attached and working.** My assertion was written from the name I called, not from the object I got.

---

### P-2 — My test patches a target that cannot take effect

```python
monkeypatch.setattr("app.models.build_default_chat_model", lambda *a, **k: ...raise...)
```

`role_agent.py:34` has `from app.models import build_default_chat_model` at module level. The name is bound in `app.agents.role_agent` at import time, so patching the attribute on `app.models` never reaches it.

The correct target is `app.agents.role_agent.build_default_chat_model`.

---

### P-3 — My regex cannot parse my own format

```python
match = re.search(r"saved as (\S+)", _truncate(text, "demo"))
read_entry(match.group(1))
```

The format I specified ends `...saved as {reference}]...`. `\S+` is greedy over non-space, so it captures `NAME]...` and `read_entry` returns `None`.

I wrote both the pointer format and the regex that cannot read it back.

---

## Part 2 — Remediation

Apply in order. Run the verification after each step.

### Step 1 — Restore the destroyed import (fixes D-1)

**File:** `src/app/graph/workflow.py`

Find this exact block:

```python
from app.review import (
    ReviewRerunLimitExceeded,
    approve_review,
    build_revision_prompt,
    request_changes,
    skip_review,
)
```

Replace with:

```python
from app.review import (
    ReviewRerunLimitExceeded,
    approve_review,
    build_revision_prompt,
    request_changes,
    skip_review,
    start_review,
)
```

Only the one added line changes. Keep alphabetical order as shown.

**Verify:**

```bash
cd /home/arun/Desktop/langchain
PYTHONPATH=src ENV=development python -c "
import app.graph.workflow as w
print('start_review reachable:', callable(w.start_review))
"
```

Must print `True`.

---

### Step 2 — Delete the duplicated block (fixes D-2)

**File:** `src/app/graph/workflow.py`

There are two identical copies. **Keep the second** (it sits after `WorkflowGraphState`, among the other module helpers) and **delete the first** (it is the corrupted paste site).

Delete everything from this line:

```python
_CONTEXT_OVERFLOW_MARKERS = (
```

through the end of the first `_context_overflow_update`, i.e. up to and including its closing:

```python
        "pending_decision": None,
    }
```

**How to identify the first copy unambiguously:** it is the one that appears *immediately after* the `from app.review import (...)` block and *before* any `class` or `def` other than the two overflow functions. The copy to keep is the one that appears immediately after these lines:

```python
    pending_inner_thread_id: str | None
    inner_thread_ids: list[str]
    pending_decision: dict[str, Any] | None
    error: str | None
```

**Verify exactly one copy remains:**

```bash
cd /home/arun/Desktop/langchain
grep -c "^_CONTEXT_OVERFLOW_MARKERS = (" src/app/graph/workflow.py
grep -c "^def _is_context_overflow" src/app/graph/workflow.py
grep -c "^def _context_overflow_update" src/app/graph/workflow.py
```

Each must print `1`.

---

### Step 3 — Give `workflow.py` a module-level logger

**File:** `src/app/graph/workflow.py`

The module has no logger, which is why `_context_overflow_update` imports one locally. Re-importing inside a function that runs on every overflow is noise; do it once at module scope.

Find the last import line in the file's import block (the `from app.review import (...)` block after Step 1) and add after it, separated by a blank line:

```python
logger = logging.getLogger(__name__)
```

Then add to the standard-library imports near the top of the file (alongside the other plain `import` statements):

```python
import logging
```

Then, in the remaining `_context_overflow_update`, delete these three lines:

```python
    import logging

    logger = logging.getLogger(__name__)
```

leaving the `logger.error(...)` call that follows them.

**Verify:**

```bash
cd /home/arun/Desktop/langchain
grep -n "^import logging" src/app/graph/workflow.py
grep -n "^logger = logging.getLogger" src/app/graph/workflow.py
grep -c "    import logging" src/app/graph/workflow.py
```

The first two must each print one line. The third must print `0`.

---

### Step 4 — Update the stale truncation assertion (fixes D-3)

**File:** `tests/test_sandbox_in_container.py`

Find:

```python
    assert "truncated" in result["stdout"]
```

Replace with:

```python
    assert "omitted" in result["stdout"]
    assert "saved as" in result["stdout"]
```

The second line is new coverage: it asserts the journal reference is present, which is the behaviour that actually matters — the discarded bytes are recoverable.

Also read the surrounding test. As written in the current file it calls `run(...)` twice, the first time before the script exists. That is harmless but confusing; if the first call is dead, delete it.

---

### Step 5 — Fix my three broken test snippets (fixes P-1, P-2, P-3)

**File:** `tests/test_context_compaction.py`

**5a — class name.** Find:

```python
    middleware = _compaction_middleware("product_manager", None)
    assert len(middleware) == 1
    assert type(middleware[0]).__name__ == "SummarizationMiddleware"
```

Replace with:

```python
    middleware = _compaction_middleware("product_manager", None)

    assert len(middleware) == 1
    # `SummarizationMiddleware` is a factory; the object it returns is a
    # `_DeepAgentsSummarizationMiddleware`. Assert on behaviour rather than on
    # a private class name that the package is free to rename.
    assert hasattr(middleware[0], "wrap_model_call")
```

**5b — patch target.** Find:

```python
    monkeypatch.setattr(
        "app.models.build_default_chat_model",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no provider")),
    )
```

Replace with:

```python
    # `role_agent` does `from app.models import build_default_chat_model` at
    # module level, so the name is bound in *that* module. Patching
    # `app.models.build_default_chat_model` would never reach it.
    monkeypatch.setattr(
        "app.agents.role_agent.build_default_chat_model",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no provider")),
    )
```

**5c — regex.** Find:

```python
    match = re.search(r"saved as (\S+)", _truncate(text, "demo"))
    assert match
    assert read_entry(match.group(1)) == text
```

Replace with:

```python
    # The reference is followed by "]...", so a greedy \S+ swallows it.
    match = re.search(r"saved as ([^\]\s]+)", _truncate(text, "demo"))
    assert match
    assert read_entry(match.group(1)) == text
```

---

### Step 6 — Add a regression test for D-1

The import loss was invisible to import-time checks and to unattended runs. Add a structural test so it cannot recur silently.

**File:** `tests/test_graph_invariants.py` — append:

```python
# ---------------------------------------------------------------------------
# Imports the graph depends on
# ---------------------------------------------------------------------------
#
# `start_review` was once deleted from the import block by a bad paste. The
# module still imported cleanly - the list was merely one name shorter - and
# nothing failed until a review gate actually ran, which unattended runs never
# do. Assert the names exist rather than waiting for a gate to find out.


def test_every_name_the_graph_calls_is_imported():
    """A missing import here fails at gate time, not at import time."""
    import app.graph.workflow as workflow_module

    for name in (
        "start_review",
        "approve_review",
        "request_changes",
        "skip_review",
        "build_revision_prompt",
        "ReviewRerunLimitExceeded",
    ):
        assert hasattr(workflow_module, name), f"workflow.py is missing {name}"


def test_the_overflow_helpers_are_defined_once():
    """Two identical copies means a later fix to one silently does nothing."""
    import inspect

    import app.graph.workflow as workflow_module

    source = inspect.getsource(workflow_module)
    assert source.count("def _is_context_overflow") == 1
    assert source.count("def _context_overflow_update") == 1
    assert source.count("_CONTEXT_OVERFLOW_MARKERS = (") == 1
```

---

### Step 7 — Full verification

```bash
cd /home/arun/Desktop/langchain

# 1. The whole suite, with the coverage gate.
PYTHONPATH=src ENV=development python -m pytest tests/ -q --tb=short

# 2. No new security findings.
python -m bandit -r src/app -ll

# 3. Frontend still compiles.
cd langchain-ui && npx tsc -b && cd ..

# 4. Rebuild and bring the stack up.
docker compose build app worker
docker compose up -d
sleep 25
docker compose ps
curl -s http://localhost:8000/api/health/ready

# 5. Compaction is attached in the deployed worker.
docker compose exec -T worker python -c "
from app.agents.context_policy import ContextPolicy
from app.agents.role_agent import _compaction_middleware
p = ContextPolicy.from_environment()
mw = _compaction_middleware('principal_architect', None)
print('enabled  :', p.enabled)
print('trigger  :', p.trigger_tokens, 'tokens')
print('attached :', len(mw) == 1)
"

# 6. Review gates work again - the specific thing D-1 broke.
PYTHONPATH=src ENV=development python -m pytest tests/test_graph_routing.py -q --no-cov
```

Expected after remediation: **611 passed, 1 skipped** (609 existing, plus the two added in Step 6), coverage above 80%, bandit 0 medium / 0 high, step 5 printing `attached : True`, step 6 all green.

If step 1 still shows failures in `test_graph_routing.py`, Step 1 was not applied correctly — re-check the import block.

---

## Part 3 — What went wrong with my instructions

D-1 was a paste error, but the plan made it easy to make and impossible to catch. That is a defect in the instructions, not in your execution. Here is the analysis, and the rules I will follow from now on.

### 3.1 What my instruction actually said

> **4.1a — Add a detector.** Insert immediately **before** `def _run_gated_agent(`:

Then ~30 lines of code.

Three problems with that sentence:

1. **"Insert before X" gives one anchor, not two.** It says where the block starts and nothing about what must remain intact around it. An editor that lands slightly high overwrites whatever was there, and nothing in the instruction says what that was.
2. **It never showed the surrounding context.** `def _run_gated_agent(` is preceded by an import block. I knew that; the instruction did not say it.
3. **The verification could not detect the failure.** My Step 4.2 check imports `_is_context_overflow` and `_context_overflow_update` and asserts they behave. Both were true. A destroyed *unrelated* import passes that check perfectly.

The same three problems produced D-2: with no "this block must appear exactly once" check, a double paste is invisible.

### 3.2 Rules for future instructions

**R1 — Every insertion gets two anchors, not one.**
Not "insert before X" but "insert *between* X and Y", quoting both. An edit that cannot find both anchors is a stop, not a guess.

**R2 — Show the code being replaced, in full, verbatim.**
Replacements state the *exact* text to find. Insertions quote the 3–5 lines on each side. If the surrounding lines are an import block, say so explicitly: *"the lines above are part of a multi-line import statement; do not overwrite any of them."*

**R3 — Every step verifies what it might have damaged, not only what it added.**
Step 4.2 should have been:

```bash
# what the step added
python -c "from app.graph.workflow import _is_context_overflow; ..."
# what the step could have destroyed
python -c "import app.graph.workflow as w; assert callable(w.start_review)"
# that it was added exactly once
grep -c "^def _is_context_overflow" src/app/graph/workflow.py   # must be 1
```

**R4 — Run the full suite after every phase, not only at the end.**
My plan ran targeted checks per phase and the full suite once at the end. Ten routing tests would have caught D-1 the moment Phase 4 landed, naming the exact symbol. Instead it surfaced at the very end, mixed in with unrelated noise.

**R5 — Never assert on a class name I have not printed.**
P-1 came from asserting `__name__ == "SummarizationMiddleware"` without ever constructing one. Assert on behaviour (`hasattr(obj, "wrap_model_call")`), or print the real value first and paste it in.

**R6 — Check where a name is bound before writing a monkeypatch.**
P-2 came from patching `app.models.X` when the consumer did `from app.models import X` at module level. The rule: `grep -n "import X" <consumer>` first, and patch in the consumer's namespace if the import is module level.

**R7 — Any format string and the regex that parses it get written and run together.**
P-3 is the clearest case: I invented `...saved as {ref}]...` and `saved as (\S+)` in the same document without ever running one against the other.

**R8 — When a step changes a string another test asserts on, say so.**
D-3 exists because I rewrote `_truncate`'s message and did not grep for tests asserting the old wording. The rule: after changing any user- or test-visible string, `grep -rn "<old wording>" tests/` and list the updates as part of the same step.

### 3.3 What you should do differently

Very little. But two habits would have caught D-1 in seconds:

- **Run the full suite after each phase.** Not just the phase's own check.
- **`git diff` the file after each edit.** The single line `- start_review,` is unmissable in a diff and was sitting there the whole time.

---

## Part 4 — After remediation

Nothing further is required for this feature. The deferred list from the original plan still stands and is unchanged:

1. Settings-API exposure of `CTX_*` (needs `SettingsUpdate`, `SettingsView`, `SETTABLE_KEYS` and the Settings page changed together).
2. Per-thread context directories rather than per-agent-name.
3. A model-specific tokenizer instead of `count_tokens_approximately`.
4. Compaction of the outer `WorkflowGraphState` — measure before acting.
5. Restructuring document intake to an on-demand `INDEX.md`.

Item 2 is worth doing sooner than the others: `discard_context(record.thread_id)` in `runs.py` currently deletes a directory keyed by thread id, while `_compaction_middleware` creates one keyed by agent name. The cleanup is therefore a no-op today. It is harmless — the directories are small and bounded by the number of roles — but the two halves should agree.
