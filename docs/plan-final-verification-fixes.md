# Final Verification Fixes

Five items to close out the follow-up implementation. Steps 0-7 are already
implemented and verified; nothing here changes production behaviour except
Item 4, which repairs database rows.

**Measured state right now:**

| Gate | Result |
|---|---|
| Suite | `630 passed, 2 failed, 1 skipped` (633 collected) |
| Coverage | 83.00% |
| Bandit | severity low=15, medium=0, high=0 |
| `tsc -b` | exit 0 |

**Target after this document:** `645 passed, 1 skipped` (646 collected), all
other gates unchanged.

This target is **measured, not predicted**: Items 1-3 were applied to a scratch
copy of `tests/test_run_recovery.py`, the full suite was run, and it reported
`645 passed, 1 skipped`. The scratch copy carried the same five test functions
with their comments condensed; the count and behaviour are identical to the
block in Item 3. The file was then restored byte-for-byte (md5 verified).

Arithmetic, so you can check your work: 633 collected, minus 1 (Item 2), plus 14
(Item 3) = 646. Item 1 turns a failure into a pass without changing the count.

---

## Item 0 — Recover the deleted plans, then commit them (do this first)

Something in this environment deletes `docs/context-compaction*.md`. It has now
happened twice: once mid-session a few turns ago, and again between two commands
during this verification pass.

**Three files are recoverable from HEAD:**

```bash
git checkout HEAD -- docs/context-compaction-remediation-steps.md \
                     docs/context-compaction-remediation-plan.md \
                     docs/context-compaction-implementation-plan.md
```

**One is not.** `docs/context-compaction-followup-plan.md` - the 3,826-line plan
containing Part 7 (the run dashboard: `_derive_stages`, `agent_stream.py`,
`ExecutionFlow.tsx`, `AgentActivity.tsx`, the three-column layout) and Part 8
(the execution ledger, `VerificationRun`, the widened allowlist) - was never
committed. It is not in git, not in any stash, and not anywhere on disk. That
content is gone.

Two consequences:

1. **The stray test in Item 2 is the only surviving trace of Part 8.** Removing
   it, as Item 2 says, is correct - but be aware you are removing the last
   on-disk reference to that workstream.
2. **Commit before doing anything else in this document.** The recovered files
   and this one are only safe once they are in git:

   ```bash
   git add -A && git commit -m "docs: recover compaction plans; verify follow-up implementation"
   ```

Note that `git checkout HEAD --` on `context-compaction-remediation-steps.md`
restores the *original* text, discarding the partial Step 7c edits that were in
your working tree (`83.00%` on line 8, `14 consistent` on line 261). That is
fine and intended: Item 5 reapplies all of Step 7c cleanly, and one of those two
edits was wrong anyway.

If you want Part 7 and Part 8 regenerated, say so - they can be rewritten from
the conversation, but not recovered from disk.

---

## Item 1 — A test asserts a message that no longer exists

**Why this is here:** Step 1b of the follow-up plan told you to rewrite the
refusal message in `resume_failed_run`. It did not tell you to update the
existing test that asserts the old wording. Your implementation is correct; the
test is stale.

This is the same class of defect as D-3 in the previous round (`_truncate`'s
"truncated" -> "omitted"), which was written up as a rule and then repeated. The
rule, stated properly this time: **a step that changes a user-visible string must
grep the test suite for that string within the same step.**

**File:** `tests/test_run_recovery.py`

Find:

```python
    with pytest.raises(WorkflowResumeError, match="nothing safe to rewind"):
        resume_failed_run(graph, "thread-1")
```

Replace with:

```python
    with pytest.raises(WorkflowResumeError, match="safe point to retry"):
        resume_failed_run(graph, "thread-1")
```

Match on `safe point to retry` rather than on the whole sentence: the parenthetical
that follows names the stage, so a longer pattern would couple this test to a
message that legitimately varies.

**Verify Item 1:**

```bash
PYTHONPATH=src ENV=development .venv/bin/python -m pytest \
  tests/test_run_recovery.py::test_resume_refuses_rather_than_restarting_from_the_beginning \
  -q --no-cov
```

Expect `1 passed`.

---

## Item 2 — Remove the Part 8 test whose implementation does not exist

**Why this is here:** `test_a_specialist_must_be_able_to_state_its_evidence` is
from Step V-5 of Part 8. It imports `VerificationRun`, which Step V-2 would have
added to `src/app/agents/specialists.py`. V-2 was not implemented, so the test
fails at import:

```
ImportError: cannot import name 'VerificationRun' from 'app.agents.specialists'
```

My V-5 block said "append to `tests/test_run_recovery.py`" without flagging that
it depends on V-2. Removing it is the right call unless you intend to implement
Part 8 now - a test that cannot import its subject is not a pending task, it is a
red suite.

**File:** `tests/test_run_recovery.py`

This is the last block in the file. Delete from the separator comment to the end,
inclusive - everything shown here:

```python
# ---------------------------------------------------------------------------
# The execution ledger
# ---------------------------------------------------------------------------


def test_a_specialist_must_be_able_to_state_its_evidence():
    """`tests` as prose was the only evidence; this makes a claim checkable."""
    from app.agents.specialists import SpecialistOutput, VerificationRun

    output = SpecialistOutput(
        changed_files=["thehub/api/main.py"],
        verification=[VerificationRun(command=["pytest", "-q"], exit_code=0, summary="17 passed")],
    )

    assert output.verification[0].exit_code == 0
    assert SpecialistOutput().verification == [], "must default to empty, not fail"
```

Also remove the two blank lines that preceded the separator, so the file ends
one blank line after
`test_the_repair_budget_is_smaller_than_the_review_budget`'s last assertion.

The file should now end with:

```python
def test_the_repair_budget_is_smaller_than_the_review_budget():
    """Repairs must not be able to exhaust the architecture revision budget."""
    from app.graph.workflow import MAX_ARCHITECTURE_REVISIONS

    assert MAX_SPECIFICATION_REPAIRS < MAX_ARCHITECTURE_REVISIONS
```

**Verify Item 2:**

```bash
grep -c "VerificationRun" tests/test_run_recovery.py
tail -1 tests/test_run_recovery.py
```

The first must print `0`. The second must print the
`assert MAX_SPECIFICATION_REPAIRS < MAX_ARCHITECTURE_REVISIONS` line.

---

## Item 3 — Add the missing Part 4a block (the important one)

**Why this is here:** `tests/test_run_recovery.py` had 15 test functions at HEAD
and has 16 now - only the stray test from Item 2 was added. All five tests from
Part 4a are absent. Parts 4b, 4c and 4d all landed; this is the only gap, and it
accounts for the count exactly (633 collected instead of 645, short by 14).

**The third test in this block is the one that matters.**
`test_every_node_in_the_graph_has_a_declared_rewind_target` is the structural
guard that makes F-1 unable to recur. Without it, someone adding a node to
`_NODE_NAMES` and forgetting `_REWIND_TARGETS` silently reintroduces the
full-restart bug and nothing fails. The other four prove the fix works today;
this one keeps it working.

**File:** `tests/test_run_recovery.py`

Insert the block below **after** `test_a_rewind_clears_both_revision_counters`
and **before** the "Specification completeness" separator. The anchor to find:

```python
    assert values["stage"] == "principal_architect"
    assert values["error"] is None


# ---------------------------------------------------------------------------
# Specification completeness
# ---------------------------------------------------------------------------
```

Replace that with:

```python
    assert values["stage"] == "principal_architect"
    assert values["error"] is None


# ---------------------------------------------------------------------------
# Where a resume rewinds to
# ---------------------------------------------------------------------------
#
# The bug these cover: the rewind chain was an if/elif over an initialiser that
# defaulted to stage="product_manager", so any node the chain did not name
# restarted the run from intake - discarding every approved artifact and
# re-billing the whole pipeline. That was unreachable until context compaction
# gave every agent node a route to stage="failed", at which point seven nodes
# started restarting runs from the beginning.


def _resume_from(node: str):
    """Resume a run whose failure is attributed to `node`; return the update."""
    history = [_snapshot(()), _snapshot(("failed",)), _snapshot((node,))]
    graph = _FakeGraph(history)
    resume_failed_run(graph, "thread-1")
    return graph.updates[0]


@pytest.mark.parametrize(
    "node",
    [
        "tools_models",
        "stack_selector",
        "principal_architect",
        "scrum_master",
        "technical_lead",
    ],
)
def test_a_stage_that_failed_is_retried_not_restarted_from_intake(node):
    values, as_node = _resume_from(node)

    assert values["stage"] == node
    assert as_node == node
    assert values["error"] is None


@pytest.mark.parametrize(
    "node, target",
    [
        ("architecture_review", "principal_architect"),
        ("milestone_review", "scrum_master"),
        ("test_and_triage", "technical_lead"),
        ("sprint_advance", "technical_lead"),
        ("specialist_dispatch", "technical_lead"),
        ("defect_remediation", "technical_lead"),
    ],
)
def test_a_stage_with_no_useful_retry_rewinds_to_the_node_that_feeds_it(node, target):
    """Retrying these as themselves reproduces the same failure immediately."""
    values, _ = _resume_from(node)

    assert values["stage"] == target


def test_every_node_in_the_graph_has_a_declared_rewind_target():
    """The structural guard: a new node cannot silently inherit a restart.

    This is the invariant the old if/elif chain could not express. Without it,
    adding a node to `_NODE_NAMES` and forgetting the rewind table reintroduces
    exactly the defect this suite exists to prevent.
    """
    from app.graph.workflow import _NODE_NAMES, _UNREWINDABLE_NODES, _rewind_target

    for node in _NODE_NAMES - _UNREWINDABLE_NODES:
        target = _rewind_target(node)
        assert target is not None, f"{node} has no rewind target"
        assert target in _NODE_NAMES, f"{node} rewinds to unknown node {target}"


def test_a_terminal_node_refuses_the_resume_rather_than_rewinding():
    from app.graph.workflow import _rewind_target

    assert _rewind_target("complete") is None
    assert _rewind_target("failed") is None
    assert _rewind_target("__start__") is None
    assert _rewind_target(None) is None
    assert _rewind_target("a_node_that_does_not_exist") is None


def test_an_unrecognisable_failure_names_the_stage_in_its_refusal():
    graph = _FakeGraph([_snapshot(()), _snapshot(("failed",)), _snapshot(("complete",))])

    with pytest.raises(WorkflowResumeError, match="complete"):
        resume_failed_run(graph, "thread-1")


# ---------------------------------------------------------------------------
# Specification completeness
# ---------------------------------------------------------------------------
```

No import changes are needed. `pytest` (line 12), `WorkflowResumeError` (line 17)
and `resume_failed_run` (line 21) are already imported at the top; `_snapshot`
and `_FakeGraph` are defined earlier in the file; and `_NODE_NAMES`,
`_UNREWINDABLE_NODES` and `_rewind_target` are imported inside the two tests
that use them.

**Verify Item 3:**

```bash
PYTHONPATH=src ENV=development .venv/bin/python -m pytest \
  tests/test_run_recovery.py -q --no-cov
```

Expect `29 passed` (16 currently, minus 1 from Item 2, plus 14 from this item).

Then confirm the structural guard actually guards. Temporarily break it:

```bash
PYTHONPATH=src ENV=development .venv/bin/python - <<'PY'
import app.graph.workflow as w
w._NODE_NAMES = w._NODE_NAMES | {"a_new_node_someone_forgot"}
from app.graph.workflow import _UNREWINDABLE_NODES, _rewind_target
missing = [n for n in w._NODE_NAMES - _UNREWINDABLE_NODES if _rewind_target(n) is None]
assert missing == ["a_new_node_someone_forgot"], missing
print("OK: the guard catches an undeclared node")
PY
```

A guard that cannot fail is not a guard. This proves it can.

---

## Item 4 — Repair the four stranded runs (Step 0e)

**Why this is here:** Step 0e was not run. Four rows still carry the state the
bug produced:

```
run-3df74a1b-aa21-48a4-85db-bfcc618bd7fa  waiting_for_approval  auto_approve=t
run-eb13e3f9-6002-4dd7-bacf-761acadd4ddd  waiting_for_approval  auto_approve=t
run-55ba3724-8924-4980-808f-2b01a2907bdb  waiting_for_approval  auto_approve=t
run-852f0696-7b4d-437e-9f5d-f05d7b775608  waiting_for_approval  auto_approve=t
```

These are now **unreachable by any route**, which is new since Step 0d landed:

- `submit_approval` refuses them outright - the new guard rejects any run with
  `auto_approve` set.
- `resume_run` refuses them - it requires `status == "failed"`, and these say
  `waiting_for_approval`.
- `cancel_run` would work, but leaves them cancelled rather than diagnosable.

So Step 0d closed the door these rows were standing in. They stay stranded until
this runs.

```bash
docker compose exec -T db psql -U postgres -d langchain_auth -c \
  "UPDATE runs SET status = 'failed',
          error = 'Interrupted: this run predates the auto-approve status fix and may have had two workers on one thread. Clone it rather than resuming.'
     WHERE auto_approve = true AND status = 'waiting_for_approval';"
```

`failed` rather than `running`: `run-3df74a1b` demonstrably had two Celery tasks
writing to one graph thread, so its checkpoint history may be interleaved.
Marking it resumable would invite the one resume that cannot be trusted. Clone
instead.

**Note the database name.** It is `langchain_auth`, not `langchain` - the latter
does not exist on this deployment. Confirm before running:

```bash
docker compose exec -T db psql -U postgres -lqt | cut -d'|' -f1
```

**Verify Item 4:**

```bash
docker compose exec -T db psql -U postgres -d langchain_auth -c \
  "select count(*) from runs where auto_approve = true and status = 'waiting_for_approval';"
```

Expect `0`.

---

## Item 5 — Apply Step 7c cleanly to the recovered document

**Why this is here:** Step 7c was partly applied and partly wrong, and Item 0's
`git checkout` reverts it to the original text anyway. Reapply all three edits to
the recovered file.

**File:** `docs/context-compaction-remediation-steps.md`

### 5a. Two coverage figures

There are **two** occurrences of `82.92%`, on lines 8 and 235. The earlier
partial edit changed only the first. Change both:

```bash
sed -i 's/82\.92%/83.00%/g' docs/context-compaction-remediation-steps.md
grep -c "82.92%" docs/context-compaction-remediation-steps.md   # must print 0
```

### 5b. The `CTX_*` entry count

Find:

```markdown
| `.env.example`, `docker-compose.yml` | 11 consistent `CTX_*` entries each (feature config) |
```

Replace with:

```markdown
| `.env.example`, `docker-compose.yml` | 12 consistent `CTX_*` entries each (feature config) |
```

**12, not 14.** The original claim of 11 was wrong (the real count was 9); Step 7a
and 7b added three more - `CTX_JOURNAL_RETENTION_HOURS`,
`CTX_CONTEXT_RETENTION_HOURS`, `CTX_SPECIFICATION_BUDGET` - giving 12. The
working-tree edit said 14, which matched neither the before nor the after. Check
rather than trust either number:

```bash
grep -c '^CTX_' .env.example        # 12
grep -c 'CTX_' docker-compose.yml   # 12
```

### 5c. Limitation 1

Find the first entry under "Remaining limitations":

```markdown
1. **Per-agent context accumulation.** Markdown summaries under
   `DATA_DIR/context/<agent_name>/` accumulate slowly across runs and are not
   cleaned up at run end (deleting them would clobber concurrent runs). Bounded by
   file size; a retention policy is deferred work.
```

Replace with:

```markdown
1. ~~**Per-agent context accumulation.**~~ **Resolved** by the follow-up work.
   Both scratch trees - `DATA_DIR/context/<agent_name>/` and `DATA_DIR/journal/` -
   are pruned by age at every terminal stage via `WorkflowRunner._prune_scratch`,
   configurable through `CTX_CONTEXT_RETENTION_HOURS` and
   `CTX_JOURNAL_RETENTION_HOURS` (default 72 hours; 0 disables). Age-based rather
   than run-scoped, because worker concurrency means two runs share the per-agent
   directories and deleting one at a run's end would clobber the other's
   in-flight scratch data. Empty directories are deliberately left in place for
   the same reason.
```

**Verify Item 5:**

```bash
grep -c "82.92%" docs/context-compaction-remediation-steps.md          # 0
grep -c "83.00%" docs/context-compaction-remediation-steps.md          # 2
grep -c "12 consistent" docs/context-compaction-remediation-steps.md   # 1
grep -c "Resolved.. by the follow-up work" docs/context-compaction-remediation-steps.md  # 1
```

---

## Final verification

Run all of these. Every one must pass.

```bash
# The python shim: 10 sandbox tests skip without a bare `python` on PATH.
export SHIM=/tmp/pyshim
mkdir -p "$SHIM" && ln -sf "$(pwd)/.venv/bin/python" "$SHIM/python"

# 1. Full suite.
PATH="$SHIM:$PATH" PYTHONPATH=src ENV=development \
  .venv/bin/python -m pytest tests/ -q --no-cov
# expect: 645 passed, 1 skipped

# 2. Coverage gate.
PATH="$SHIM:$PATH" PYTHONPATH=src ENV=development \
  .venv/bin/python -m pytest tests/ -q
# expect: "Required test coverage of 80% reached", total >= 83%

# 3. Security. Read the *severity* section, not the confidence section.
.venv/bin/python -m bandit -r src/app -ll
# expect: Medium 0, High 0

# 4. Frontend types (untouched by this document; confirms nothing was disturbed).
cd langchain-ui && npx tsc -b && echo "tsc OK" && cd ..

# 5. No node restarts a run from intake.
PYTHONPATH=src ENV=development .venv/bin/python - <<'PY'
from types import SimpleNamespace
from app.graph.workflow import resume_failed_run, _NODE_NAMES, _UNREWINDABLE_NODES

def snap(n): return SimpleNamespace(next=n, values={})
class G:
    def __init__(s, h): s._h = h; s.updates = []
    def get_state(s, c): return SimpleNamespace(values={"stage": "failed"})
    def get_state_history(s, c): return iter(s._h)
    def update_state(s, c, v, as_node=None): s.updates.append((v, as_node))
    def invoke(s, i, config=None): return {}

for node in sorted(_NODE_NAMES - _UNREWINDABLE_NODES):
    g = G([snap(()), snap(("failed",)), snap((node,))])
    resume_failed_run(g, "t")
    stage = g.updates[0][0]["stage"]
    assert not (stage == "product_manager" and node != "product_manager"), node
print("OK: no node restarts a run from intake")
PY

# 6. No stranded runs.
docker compose exec -T db psql -U postgres -d langchain_auth -c \
  "select count(*) from runs where auto_approve = true and status = 'waiting_for_approval';"
# expect: 0

# 7. Commit, before anything eats the docs again.
git add -A && git commit -m "test: close out follow-up implementation; repair stranded runs"
```

---

## If a verification fails

- **Suite count is 632, not 646** - Item 3 was not applied. `grep -c "def test_"
  tests/test_run_recovery.py` must show 20 test functions.
- **Suite count is 647** - Item 2 was not applied; the `VerificationRun` test is
  still there and still failing.
- **`test_every_node_in_the_graph_has_a_declared_rewind_target` fails** - a node
  exists in `_NODE_NAMES` that is neither in `_UNREWINDABLE_NODES` nor
  resolvable by `_rewind_target`. That is the test working. Add the node to one
  or the other; do not weaken the test.
- **`test_an_unrecognisable_failure_names_the_stage_in_its_refusal` fails** - the
  refusal message no longer interpolates the failed node. Check that Step 1b's
  f-string survived, including the `or 'an unrecognised stage'` fallback.
- **Item 4's UPDATE reports `UPDATE 0`** - either it already ran, or you are on
  the wrong database. `\l` and check for `langchain_auth`.

## Not in scope here

Part 7 (the run dashboard) and Part 8 (code verification) were never
implemented, and their plan file is gone from disk. Nothing in this document
depends on them. The one thing to know: **no run has ever produced a source
file** - every workspace on the volume contains only `docs/*.md`, and
`DATA_DIR/journal/` does not exist, meaning no command has ever run. Steps 0 and
1 were the two reasons runs kept dying before the specialist stage; with them
fixed, the next run is the first that can actually reach code generation. Watch
that run rather than assuming it works.
