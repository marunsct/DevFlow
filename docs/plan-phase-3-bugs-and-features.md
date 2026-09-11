# Phase 3 — Bugs and Missing Features

Written after validating the phase-2 implementation (`645 passed, 1 skipped`,
coverage 83.04%, bandit medium=0/high=0, `tsc -b` exit 0, commit `1b7f539`).

Two halves:

- **Part A — four bugs**, all found by reading the code that phase 2 touched and
  the paths that touch it back. B-1 and B-2 both *undo* phase-2 work, so they
  matter more than their size suggests.
- **Part B — two missing features**: the run dashboard, and the agents' ability
  to prove the code they write works. These were planned in
  `context-compaction-followup-plan.md`, which was lost from disk before it was
  ever committed; this regenerates them.

**Current state:** `645 passed, 1 skipped` (646 collected), coverage 83.04%.

**Target after Part A:** `651 passed, 1 skipped` (6 new tests).
**Target after Part B:** `665 passed, 1 skipped` (14 more: 6 for M-1, 8 for M-2).

---

## Part 0 — How to use this plan

1. **Part A first, in order.** B-1 and B-2 are both regressions of work you have
   already done and paid for.
2. Every edit gives the exact text to find and what to put in its place.
3. Run each step's own verification before the next.
4. Do not reformat code you are not told to change.
5. Line numbers are from commit `1b7f539`. If yours differ by more than a few,
   find the anchor text instead.

---

# Part A — Bugs

## A.0 — What is wrong, with evidence

### B-1 (HIGH) — A maintenance command silently undoes Step 0

`python -m app.server.manage reconcile-runs` walks every run whose
`current_stage` starts with an approval or review prefix and forces:

```python
# src/app/server/manage.py:158-167
        expected = _api_status(stage)
        if record.status == expected or record.status in ("cancelled", "completed"):
            continue
        ...
        record.status = expected
        record.stage_meaning = _stage_meaning(stage)
```

It calls `_api_status`, not `_stage_narration`. It has never heard of
`auto_approve`. Two consequences, both bad:

1. **It re-strands the four runs you just repaired.** Their `current_stage` is
   still `awaiting_approval:product_manager` - Item 4 only changed `status`. So
   `expected` is `waiting_for_approval`, the row says `failed`, they differ, and
   the command sets them straight back. They are then unreachable again, because
   `submit_approval` now refuses any `auto_approve` run.
2. **It can reintroduce F-0 on a *live* run.** An unattended run sitting inside
   `resume_pending_approval` has `status=running` and
   `current_stage=awaiting_approval:...`. Running this command at that moment
   flips it to `waiting_for_approval`, which is exactly the row state that let
   `submit_approval`'s compare-and-set pass and put two Celery tasks on one graph
   thread. Step 0d's guard blocks that specific route, but the row is wrong for
   every other reader too.

The command's own docstring says it exists to fix rows where "the failure path
used to record a flat `failed` without touching `current_stage`". That reasoning
predates auto-approve, and the command was never revisited.

### B-2 (HIGH) — Clone produces an unstartable run with none of the original's settings

This is the recovery path recommended for every run damaged by F-0, so it needs
to work.

```python
# src/app/server/runs.py:334-341
        clone = runner.register_run(
            run_id=f"run-{uuid.uuid4()}",
            thread_id=f"thread-{uuid.uuid4()}",
            document_names=record.document_names,
            document_paths=record.document_paths,
            owner=user.username,
            tenant_id=user.tenant_id,
        )
```

`register_run` (`runner.py:251-270`) accepts nothing else. So a clone silently
drops **`auto_approve`, `review_policy`, `reviewer`, `repo_root`,
`model_overrides`** and the workspace source. Clone an unattended brownfield run
and you get an attended greenfield one.

Worse, the clone never starts. `register_run` leaves `status="created"`, and
`clone_run` does not dispatch. The dashboard then offers no way to start it -
`handleClone` navigates to the new run (`RunDashboard.tsx:229`), and the only
buttons there are Resume (shown when `status === 'failed'`), Clone and Cancel.
`POST /runs/{id}/start` exists and `startRun` is in the API client, but only
`Home.tsx` ever calls it.

So "Clone Run" currently means: create a run with default settings that nothing
can start, and navigate to it.

### B-3 (MEDIUM) — The repaired runs invite the one resume that cannot be trusted

Item 4 set four rows to `status='failed'` with an error saying "Clone it rather
than resuming." Nothing enforces that. `resume_run` requires exactly `failed`
(`runner.py:345-350`), and the dashboard shows Resume for exactly `failed`
(`RunDashboard.tsx:294`). So the button is right there, and `run-3df74a1b`
demonstrably had two Celery tasks writing to one graph thread - its checkpoint
history may be interleaved.

A message in a field nobody has to read is not a guard.

### B-4 (LOW) — A cancelled run never prunes its scratch space

`_prune_scratch` is called only in the `complete`/`failed` branch
(`runner.py:579`). `_finish_cancelled` (`runner.py:699-704`) persists, logs and
closes the bus without pruning. Cancelled runs are a normal outcome, and they
leave the same journal and context files behind as any other.

## A.1 — Steps

### Step A-1 — Teach `reconcile-runs` about unattended runs (fixes B-1)

**File:** `src/app/server/manage.py`

Find:

```python
    from app.graph.workflow import APPROVAL_PAUSE_PREFIX, REVIEW_PAUSE_PREFIX
    from app.server.run_store import RunStore
    from app.server.runner import _api_status, _stage_meaning
```

Replace with:

```python
    from app.graph.workflow import APPROVAL_PAUSE_PREFIX, REVIEW_PAUSE_PREFIX
    from app.server.run_store import RunStore
    from app.server.runner import _stage_narration
```

Then find:

```python
        expected = _api_status(stage)
        if record.status == expected or record.status in ("cancelled", "completed"):
            continue

        print(f"{record.run_id}: {record.status} -> {expected}  (stage: {stage})")
        repaired += 1
        if dry_run:
            continue
        record.status = expected
        record.stage_meaning = _stage_meaning(stage)
        store.save(record)
```

Replace with:

```python
        # An unattended run answers its own gates, so a row that says
        # `awaiting_approval:...` is not evidence that anything is waiting. This
        # command used to call `_api_status` directly and would set such a row to
        # `waiting_for_approval` - which is the exact row state that lets
        # `submit_approval`'s compare-and-set pass and puts a second Celery task
        # on a thread the first is still driving.
        expected_meaning, expected = _stage_narration(
            stage, auto_approve=bool(record.auto_approve)
        )
        if record.status == expected or record.status in ("cancelled", "completed"):
            continue

        # A run repaired out of the F-0 damage was deliberately marked `failed`
        # while its stage still names a gate. Do not undo that: its checkpoint
        # history may have had two concurrent writers, and the whole point of
        # marking it failed was to stop it being resumed.
        if record.auto_approve and record.status == "failed":
            print(f"{record.run_id}: leaving failed (unattended run, repaired out of band)")
            continue

        print(f"{record.run_id}: {record.status} -> {expected}  (stage: {stage})")
        repaired += 1
        if dry_run:
            continue
        record.status = expected
        record.stage_meaning = expected_meaning
        store.save(record)
```

Two separate protections, and both are needed. The first stops the command
computing `waiting_for_approval` for an unattended run at all. The second is
belt-and-braces for the rows already repaired: even if a future change makes
`_stage_narration` return something else, a `failed` unattended run is left
alone.

**Verify Step A-1:**

```bash
PYTHONPATH=src ENV=development .venv/bin/python -m app.server.manage reconcile-runs --dry-run
```

Must print either `All runs agree with their graph state.` or lines saying
`leaving failed (unattended run, repaired out of band)` - and **must not** offer
to move any run to `waiting_for_approval`.

Then confirm the four repaired runs are untouched:

```bash
docker compose exec -T db psql -U postgres -d langchain_auth -c \
  "select count(*) from runs where auto_approve = true and status = 'waiting_for_approval';"
```

Still `0`.

### Step A-2 — Make Clone actually clone (fixes B-2)

#### A-2a. Let `register_run` carry the settings

**File:** `src/app/server/runner.py`

Find:

```python
    def register_run(
        self,
        run_id: str,
        thread_id: str,
        document_names: list[str],
        document_paths: list[str],
        *,
        owner: str = "unknown",
        tenant_id: str = "default",
    ) -> RunRecord:
        """Register a new run without starting it."""
        record = RunRecord(
            run_id=run_id,
            thread_id=thread_id,
            document_names=document_names,
            document_paths=document_paths,
            owner=owner,
            tenant_id=tenant_id,
        )
        self._persist(record)
        return record
```

Replace with:

```python
    def register_run(
        self,
        run_id: str,
        thread_id: str,
        document_names: list[str],
        document_paths: list[str],
        *,
        owner: str = "unknown",
        tenant_id: str = "default",
        review_policy: dict[str, bool] | None = None,
        reviewer: str | None = None,
        auto_approve: bool = False,
        model_overrides: dict[str, Any] | None = None,
    ) -> RunRecord:
        """Register a new run without starting it.

        The optional settings exist for cloning. A clone that dropped them
        produced an attended, greenfield run from an unattended brownfield one -
        silently, and on the path recommended for recovering a damaged run.

        `repo_root` is deliberately *not* among them: a workspace belongs to one
        run, and two runs writing to the same directory is the problem cloning
        exists to avoid. A clone gets a fresh workspace when it is started.
        """
        record = RunRecord(
            run_id=run_id,
            thread_id=thread_id,
            document_names=document_names,
            document_paths=document_paths,
            owner=owner,
            tenant_id=tenant_id,
        )
        if review_policy is not None:
            record.review_policy = dict(review_policy)
        if reviewer is not None:
            record.reviewer = reviewer
        record.auto_approve = bool(auto_approve)
        if model_overrides is not None:
            record.model_overrides = dict(model_overrides)
        self._persist(record)
        return record
```

Check that `Any` is imported in `runner.py` (it is - `from typing import Any`
near the top). Check the `RunRecord` field names against `runner.py:180-210`
before you run: `review_policy`, `reviewer`, `auto_approve` and
`model_overrides` must all exist as declared fields. If any is named
differently, use the real name.

#### A-2b. Pass them from the source run

**File:** `src/app/server/runs.py`

Find:

```python
        record = _require_run(runner, run_id, user)
        clone = runner.register_run(
            run_id=f"run-{uuid.uuid4()}",
            thread_id=f"thread-{uuid.uuid4()}",
            document_names=record.document_names,
            document_paths=record.document_paths,
            owner=user.username,
            tenant_id=user.tenant_id,
        )
        record_audit(
            actor=user.username, tenant_id=user.tenant_id, action="run.clone",
            subject=clone.run_id, detail={"cloned_from": run_id},
        )
```

Replace with:

```python
        record = _require_run(runner, run_id, user)
        # Carry the source run's configuration. Dropping it meant cloning an
        # unattended run produced an attended one - on the path recommended for
        # recovering a run damaged by the auto-approve status bug, where the
        # whole point is to repeat the original attempt.
        clone = runner.register_run(
            run_id=f"run-{uuid.uuid4()}",
            thread_id=f"thread-{uuid.uuid4()}",
            document_names=record.document_names,
            document_paths=record.document_paths,
            owner=user.username,
            tenant_id=user.tenant_id,
            review_policy=record.review_policy,
            reviewer=record.reviewer,
            auto_approve=record.auto_approve,
            model_overrides=record.model_overrides,
        )
        record_audit(
            actor=user.username, tenant_id=user.tenant_id, action="run.clone",
            subject=clone.run_id,
            detail={
                "cloned_from": run_id,
                "auto_approve": bool(record.auto_approve),
                "review_policy": record.review_policy,
            },
        )
```

#### A-2c. Give the dashboard a way to start a created run

**File:** `langchain-ui/src/pages/RunDashboard.tsx`

Find the import of the API functions and add `startRun` to it. It will look
something like:

```tsx
import { getRun, getLogs, getPendingApproval, getPendingReview, cloneRun, cancelRun, resumeRun } from '../api';
```

Add `startRun` to that list. (Match your file's actual import line; the point is
that `startRun` becomes available.)

Then find:

```tsx
  const handleClone = async () => {
    if (!runId) return;
    try {
      const clonedRun = await cloneRun(runId);
      navigate(`/runs/${clonedRun.run_id}`);
    } catch (err: any) {
      alert("Failed to clone: " + (err.response?.data?.detail || err.message));
    }
  };
```

Replace with:

```tsx
  const handleClone = async () => {
    if (!runId) return;
    try {
      const clonedRun = await cloneRun(runId);
      navigate(`/runs/${clonedRun.run_id}`);
    } catch (err: any) {
      alert("Failed to clone: " + (err.response?.data?.detail || err.message));
    }
  };

  /**
   * Start a run that is registered but not running.
   *
   * A clone lands in `created` and nothing on this page could move it, so the
   * recommended recovery path - clone the damaged run - produced a run that sat
   * there. The settings the clone carried are already on the record; an empty
   * payload keeps them rather than overwriting them with defaults.
   */
  const handleStart = async () => {
    if (!runId) return;
    setActionLoading(true);
    try {
      await startRun(runId, {});
      await fetchState();
    } catch (err: any) {
      alert("Failed to start: " + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };
```

Then find:

```tsx
          {run.status === 'failed' && (
            <button
              onClick={handleResume}
```

Insert this **above** that block:

```tsx
          {run.status === 'created' && (
            <button
              onClick={handleStart}
              disabled={actionLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-success/80 hover:text-success border border-success/30 hover:border-success/60 rounded-lg transition-all hover:bg-success/5 disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5" />
              Start Run
            </button>
          )}
```

`Play` is already imported for the Resume button, and `actionLoading` /
`fetchState` already exist in this component - confirm both before building.

#### A-2d. Stop `/start` overwriting a clone's settings with defaults

**This is required, not optional.** I checked: `start_run` does overwrite.

```python
# src/app/server/runs.py:282-294
            await runner.start_run(
                run_id,
                document,
                repository,
                review_policy=body.review_policy or {},
                reviewer=body.reviewer or user.username,
                auto_approve=body.auto_approve,
                ...
```

`StartRunRequest.auto_approve` is `bool = Field(default=False)`, so an omitted
value and an explicit `False` are indistinguishable, and `startRun(runId, {})`
would set `auto_approve=False` on every clone - silently turning the unattended
run you cloned into an attended one at the moment you start it. `reviewer` has
the same shape via `or user.username`.

**File:** `src/app/server/models.py`. Find:

```python
    auto_approve: bool = Field(
        default=False,
        description="Approve artifact writes automatically. Does not bypass execution gates.",
    )
```

Replace with:

```python
    auto_approve: bool | None = Field(
        default=None,
        description=(
            "Approve artifact writes automatically. Does not bypass execution gates. "
            "Omit to keep whatever the run was registered with - which is what a clone "
            "of an unattended run needs."
        ),
    )
```

**File:** `src/app/server/runs.py`. Find:

```python
                review_policy=body.review_policy or {},
                reviewer=body.reviewer or user.username,
                auto_approve=body.auto_approve,
```

Replace with:

```python
                # Omitted means "keep what the run was registered with". A clone
                # carries the source run's settings, and a Start button that sent
                # an empty body used to overwrite every one of them with a
                # default - turning an unattended run attended on start.
                review_policy=body.review_policy if body.review_policy is not None else record.review_policy,
                reviewer=body.reviewer or record.reviewer or user.username,
                auto_approve=record.auto_approve if body.auto_approve is None else body.auto_approve,
```

Check the audit-detail block a few lines below, which also reads
`body.auto_approve`; change it to log the value actually applied rather than the
submitted one.

`Home.tsx` always sends an explicit `auto_approve`, so the create-and-start path
is unaffected.

### Step A-3 — Stop the dashboard offering an untrustworthy resume (fixes B-3)

Two layers: the server refuses, and the UI stops asking.

#### A-3a. Server

**File:** `src/app/server/runner.py`

Find:

```python
    async def resume_run(self, run_id: str) -> None:
        """Resume a failed run from its last checkpoint."""
        now = datetime.now(timezone.utc).isoformat()
        if not self.run_store.compare_and_set_status(
            run_id, "failed", "running", updated_at=now, clear_error=True
        ):
            raise RunConflict(f"Run {run_id} is not in the 'failed' state.")
        self._dispatch(run_id, resume=True, decision_payload=None)
```

Replace with:

```python
    UNRESUMABLE_ERROR_MARKER = "Interrupted:"
    """Prefix on the error of a run whose checkpoint history cannot be trusted.

    Set by the out-of-band repair for runs damaged by the auto-approve status
    bug, where two Celery tasks wrote to one graph thread. Their history may be
    interleaved, so resuming reads a state no single run ever produced.
    """

    async def resume_run(self, run_id: str) -> None:
        """Resume a failed run from its last checkpoint."""
        record = self.run_store.load(run_id)
        if record is not None and (record.error or "").startswith(self.UNRESUMABLE_ERROR_MARKER):
            raise RunConflict(
                f"Run {run_id} was interrupted in a way that may have left its checkpoint "
                "history inconsistent, so resuming it would read a state no single run "
                "produced. Clone it to repeat the attempt from the beginning."
            )

        now = datetime.now(timezone.utc).isoformat()
        if not self.run_store.compare_and_set_status(
            run_id, "failed", "running", updated_at=now, clear_error=True
        ):
            raise RunConflict(f"Run {run_id} is not in the 'failed' state.")
        self._dispatch(run_id, resume=True, decision_payload=None)
```

Marking on the error text is deliberately cheap. The alternative is a new
`resumable` column and a migration, for a condition that applies to four rows
created by a bug that is now fixed. If that condition ever becomes ordinary,
promote it to a column then.

#### A-3b. UI

**File:** `langchain-ui/src/pages/RunDashboard.tsx`

Find:

```tsx
          {run.status === 'failed' && (
            <button
              onClick={handleResume}
```

Replace with:

```tsx
          {run.status === 'failed' && !run.error?.startsWith('Interrupted:') && (
            <button
              onClick={handleResume}
```

Then find the error banner:

```tsx
        {run.error && (
          <div className="mt-4 p-3 bg-danger/10 border border-danger/30 rounded-xl text-danger text-sm">
            <strong>Error:</strong> {run.error}
          </div>
        )}
```

Replace with:

```tsx
        {run.error && (
          <div className="mt-4 p-3 bg-danger/10 border border-danger/30 rounded-xl text-danger text-sm">
            <strong>Error:</strong> {run.error}
            {run.error.startsWith('Interrupted:') && (
              <p className="mt-2 text-text-secondary">
                Resume is unavailable for this run. Use <strong>Clone Run</strong> to repeat
                the attempt from the beginning with the same documents and settings.
              </p>
            )}
          </div>
        )}
```

### Step A-4 — Prune on cancellation too (fixes B-4)

**File:** `src/app/server/runner.py`

Find:

```python
    async def _finish_cancelled(self, record: RunRecord) -> None:
        record.status = "cancelled"
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(record)
        logger.info("Run %s cancelled", record.run_id)
        await self.event_bus.close(record.run_id)
```

Replace with:

```python
    async def _finish_cancelled(self, record: RunRecord) -> None:
        record.status = "cancelled"
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(record)
        logger.info("Run %s cancelled", record.run_id)
        # Cancellation is a terminal outcome like any other, and leaves the same
        # journal and context files behind. Pruning only on complete/failed meant
        # a deployment where runs are frequently cancelled never pruned at all.
        await asyncio.to_thread(self._prune_scratch)
        await self.event_bus.close(record.run_id)
```

### Step A-5 — Tests for Part A

`tests/test_runner_lifecycle.py` has a `runner` fixture, a `dispatched` fixture
that captures Celery dispatches, and a `_register(runner, run_id=..., **overrides)`
helper. Async tests there use `@pytest.mark.asyncio`. Use those - do not invent
new ones. Append:

```python
# ---------------------------------------------------------------------------
# Cloning and resuming
# ---------------------------------------------------------------------------


def test_a_clone_carries_the_source_runs_settings(runner):
    """Dropping them turned an unattended run into an attended one - on the
    path recommended for recovering a run damaged by the auto-approve bug."""
    clone = runner.register_run(
        run_id="run-clone", thread_id="thread-clone",
        document_names=["brief.md"], document_paths=["/tmp/brief.md"],
        review_policy={"product_intake": False, "technical_specification": False, "sprint": False},
        reviewer="Product Manager",
        auto_approve=True,
        model_overrides={"model_name": "pinned-model"},
    )

    assert clone.auto_approve is True
    assert clone.review_policy == {
        "product_intake": False, "technical_specification": False, "sprint": False
    }
    assert clone.reviewer == "Product Manager"
    assert clone.model_overrides == {"model_name": "pinned-model"}


def test_registering_without_settings_still_defaults_to_attended(runner):
    """The new parameters must not change an ordinary registration."""
    record = _register(runner, run_id="run-plain")

    assert record.auto_approve is False
    assert record.status == "created"


@pytest.mark.asyncio
async def test_a_run_with_an_inconsistent_history_refuses_to_resume(runner):
    """Two Celery tasks wrote to one graph thread; resuming reads a state no
    single run produced."""
    record = _register(runner, run_id="run-damaged")
    record.status = "failed"
    record.error = "Interrupted: this run predates the auto-approve status fix."
    runner.run_store.save(record)

    with pytest.raises(RunConflict, match="Clone it"):
        await runner.resume_run("run-damaged")


@pytest.mark.asyncio
async def test_an_ordinary_failed_run_still_resumes(runner, dispatched):
    record = _register(runner, run_id="run-ordinary")
    record.status = "failed"
    record.error = "OpenAIModelNotFoundError: the model was not found"
    runner.run_store.save(record)

    await runner.resume_run("run-ordinary")

    assert [c["run_id"] for c in dispatched] == ["run-ordinary"]
```

Confirm `RunConflict` is imported at the top of that file; if not, add it to the
existing `from app.server.runner import ...` block.

`tests/test_manage_cli.py` has a `run_store` fixture and a
`_stored_run(run_store, run_id, status, stage)` helper, and already contains
`test_a_row_that_drifted_from_its_gate_is_repaired`, which proves an *attended*
run still gets repaired. Do not duplicate that. Append only these two:

```python
def test_reconcile_leaves_a_live_unattended_run_alone(run_store, capsys):
    """The command used to set an unattended run to `waiting_for_approval`,
    which is the row state that lets a second Celery task be dispatched onto a
    thread the first is still driving."""
    record = _stored_run(run_store, "run-unattended", "running",
                         "awaiting_approval:product_manager")
    record.auto_approve = True
    run_store.save(record)

    manage.reconcile_runs(dry_run=True)

    assert "waiting_for_approval" not in capsys.readouterr().out
    assert run_store.load("run-unattended").status == "running"


def test_reconcile_does_not_unrepair_a_damaged_run(run_store):
    """Item 4 of the previous phase marked these `failed` deliberately."""
    record = _stored_run(run_store, "run-repaired", "failed",
                         "awaiting_approval:product_manager")
    record.auto_approve = True
    run_store.save(record)

    manage.reconcile_runs()

    assert run_store.load("run-repaired").status == "failed"
```

Six new tests in total for Part A.

**Verify Part A:**

```bash
export SHIM=/tmp/pyshim && mkdir -p "$SHIM" && ln -sf "$(pwd)/.venv/bin/python" "$SHIM/python"
PATH="$SHIM:$PATH" PYTHONPATH=src ENV=development .venv/bin/python -m pytest tests/ -q --no-cov
# expect: 651 passed, 1 skipped
cd langchain-ui && npx tsc -b && cd ..
```

---

# Part B — Missing features

## B.0 — What is missing, with evidence

### M-1 — The run dashboard shows one node and no reasoning

Three findings, each naming the line that causes it.

**The execution flow chart has no data source.** `RunStatusResponse.stages` is
hardcoded empty:

```python
# src/app/server/runs.py:781
        stages=[],
```

`DynamicWorkflowUI` gets an empty list and falls through to its fallback
(`DynamicWorkflowUI.tsx:84-95`), which fabricates *one* node from
`current_stage`. That is why a run which had finished three stages showed a
single box. The component is fine - it draws a connected, colour-coded vertical
timeline already. It has never been given more than one node.

A working derivation already exists at `GET /runs/{run_id}/stages`
(`runs.py:387-405`), built from `stage_change` history. Nothing in the UI calls
it.

**There is no stream of what the agent is thinking.** `RunEvent.event_type` is a
closed `Literal` of eight values (`events.py:30-39`), none carrying model output
or tool calls. `_run_gated_agent` calls `agent.invoke(...)`, which returns only
when the whole turn is done - minutes of silence on a real model.

**The two panels are different heights.** `LogViewer`'s scroll area is
`max-h-[400px]` (`LogViewer.tsx:52`); `ArtifactList` has no height constraint and
grows with its content, so the row's height is whichever is taller.

Two smaller things worth fixing while in there: `RunEvent.files_modified`,
`tests_passed` and `tests_failed` (`events.py:41-43`) have **no writer anywhere**
in the codebase, and the log column renders the raw routing key
(`awaiting_appro…`, truncated, on every row).

### M-2 — Nothing establishes that generated code works

The capability exists. Every specialist has `run_terminal_command`
(`agent_toolkit.py:117`, wired at `specialists.py:257`); the testing specialist
also has `run_validation`. The sandbox is argv-only with a per-role allowlist,
returns `{"returncode", "stdout", "stderr"}`, and `ALLOW_COMMAND_EXECUTION=true`
with `SANDBOX_EXECUTION_MODE=in-container` in your `.env`.

**It has never been used.** Every workspace on the volume contains only
`docs/*.md` - no source files, no `package.json`, no tests. `DATA_DIR/journal/`
does not exist, so `_truncate` has never fired, so no command has produced more
than 50 KB of output, because no command has run. Every run has died in the
first four stages. F-0 and F-1 were the two reasons; both are now fixed, so the
next run is the first that can reach `specialist_dispatch`.

**Verification is self-reported prose.** `SpecialistOutput.tests` is `list[str]`,
described as "Tests added, updated, or run" (`specialists.py:113`). A specialist
satisfies it with `["ran pytest, all green"]`. `is_sprint_acceptable`
(`sprint/__init__.py:171-190`) checks defect bookkeeping - every field of which a
model also fills in. The executor knows the truth on every call and discards it.

**Allowlist gaps a first real sprint will hit** (`sandbox.py:47-53`): no `make`
for any role; `database_specialist` has `prisma`/`psql`/`alembic` but no
`python`, so it cannot run the migration it just wrote; `ui_specialist` has no
`python3`; `backend_specialist` has no `npm`.

## B.1 — Steps for M-1

### Step M-1a — Give the flow chart real data

**File:** `src/app/server/runs.py`

Insert above `_build_status_response`:

```python
def _derive_stages(events: list[Any], current_stage: str | None) -> list[dict[str, Any]]:
    """Build the execution timeline from this run's `stage_change` history.

    `stages` was returned as a hardcoded empty list, so the dashboard's flow
    chart fell through to a fallback that fabricates a single node from
    `current_stage` - which is why a run that had finished three stages showed
    one.

    One entry per distinct stage, in the order first seen, carrying the duration
    to the next transition. A stage that repeats (the specialist loop, a review
    revision) increments `retry_count` rather than adding a second node, so the
    chart stays a readable spine instead of growing a row per iteration.
    """
    from datetime import datetime

    def _parsed(value: str):
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    ordered: list[dict[str, Any]] = []
    by_name: dict[str, dict[str, Any]] = {}

    for event in events:
        if event.event_type != "stage_change":
            continue
        name = event.stage or ""
        if not name:
            continue
        existing = by_name.get(name)
        if existing is not None:
            existing["retry_count"] += 1
            existing["meaning"] = event.message
            existing["ended_at"] = None
            continue
        entry = {
            "name": name,
            "meaning": event.message,
            "started_at": event.timestamp,
            "ended_at": None,
            "status": str(event.metadata.get("status") or "running"),
            "duration_seconds": None,
            "retry_count": 0,
        }
        by_name[name] = entry
        ordered.append(entry)

    # A stage ended when the next one began. The last stays open.
    for earlier, later in zip(ordered, ordered[1:]):
        earlier["ended_at"] = later["started_at"]
        start, end = _parsed(earlier["started_at"]), _parsed(later["started_at"])
        if start and end:
            earlier["duration_seconds"] = max((end - start).total_seconds(), 0.0)
        if earlier["status"] not in {"failed", "cancelled"}:
            earlier["status"] = "completed"

    return ordered
```

`EventBus` has only an **async** `get_history` (`events.py:159`). Do not add a
sync variant and do not call `asyncio.run` inside a running loop. Make the
builder async instead.

Find:

```python
def _build_status_response(record: RunRecord, runner: WorkflowRunner) -> RunStatusResponse:
```

Replace with:

```python
async def _build_status_response(record: RunRecord, runner: WorkflowRunner) -> RunStatusResponse:
```

Add as the first statements of its body:

```python
    # Derived from the event history rather than stored: the history is already
    # the authority on what ran, and a second source would drift from it.
    try:
        history = await runner.event_bus.get_history(record.run_id)
        stages = _derive_stages(history, record.current_stage)
    except Exception:  # noqa: BLE001 - a timeline is never worth failing a status call for
        stages = []
```

Find:

```python
        stages=[],
```

Replace with:

```python
        stages=stages,
```

Find:

```python
        return _build_status_response(record, runner)
```

Replace with:

```python
        return await _build_status_response(record, runner)
```

`grep -n "_build_status_response" src/app/server/runs.py` must show exactly two
lines afterwards - the `async def` and the `await`. If it shows more, await each
of the others too.

**Verify:**

```bash
PYTHONPATH=src ENV=development .venv/bin/python - <<'PY'
from types import SimpleNamespace
from app.server.runs import _derive_stages
def ev(s, m, t, st="running"):
    return SimpleNamespace(event_type="stage_change", stage=s, message=m, timestamp=t,
                           metadata={"status": st})
stages = _derive_stages([
    ev("product_manager", "Reading.",  "2026-09-10T10:00:00+00:00"),
    ev("tools_models",    "Comparing.","2026-09-10T10:02:00+00:00"),
    ev("tools_models",    "Comparing.","2026-09-10T10:03:00+00:00"),
    ev("principal_architect", "Spec.", "2026-09-10T10:05:00+00:00"),
], "principal_architect")
assert [s["name"] for s in stages] == ["product_manager","tools_models","principal_architect"]
assert stages[0]["duration_seconds"] == 120.0 and stages[0]["status"] == "completed"
assert stages[1]["retry_count"] == 1
assert stages[-1]["status"] == "running"
assert _derive_stages([], None) == []
print("OK")
PY
```

### Step M-1b — Stream what the agent is doing

Stream **per message, not per token**: a token stream is one Redis write, one
WebSocket frame and one React render per token, for text a human reads in
paragraphs. Publish from a LangChain **callback**, not by converting the graph to
`.stream()` - `_run_gated_agent` is the interrupt-and-resume path and a callback
observes it without changing control flow. Use the **sync** Redis client
(`redis_client.py:32`); the callback runs on a worker thread with no event loop.

#### Event types

**File:** `src/app/server/events.py`. Find:

```python
        "error",
        "complete",
    ] = Field(description="Type of the event.")
```

Replace with:

```python
        "error",
        "complete",
        # Agent activity. One event per assistant message, tool call and tool
        # result - never per token.
        "agent_message",
        "tool_call",
        "tool_result",
    ] = Field(description="Type of the event.")
```

#### The callback

**Create** `src/app/server/agent_stream.py`:

```python
"""Publishes what an agent is doing while it is doing it.

The dashboard could show which node was running and nothing else, because the
graph only reports at node boundaries: `_run_gated_agent` calls `agent.invoke`,
which returns when the whole turn is finished. On a real model that is minutes
of silence.

Everything here is best-effort. A failure to narrate must never fail the run
that was being narrated, so every publish is wrapped and nothing re-raises.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_core.callbacks.base import BaseCallbackHandler

logger = logging.getLogger(__name__)

MAX_TEXT = 2_000
"""Characters of any one message that reach the dashboard.

The full text is already in the model's context and, for tool output, in the
journal. This is a UI feed, not a record.
"""

MAX_EVENTS_PER_RUN = 5_000
"""Ceiling on agent-activity events per run.

A model in a tool-calling loop can emit thousands of messages, and without a
ceiling one pathological run makes every dashboard poll slower.
"""


def _clip(text: str) -> str:
    text = str(text or "")
    if len(text) <= MAX_TEXT:
        return text
    return text[:MAX_TEXT] + f"\n\n[+{len(text) - MAX_TEXT:,} more characters]"


class AgentActivityStream(BaseCallbackHandler):
    """Publish an agent's messages and tool calls to a run's event stream."""

    def __init__(self, run_id: str, stage: str) -> None:
        self.run_id = run_id
        self.stage = stage
        self._published = 0

    def _publish(self, event_type: str, message: str, metadata: dict[str, Any] | None = None) -> None:
        if self._published >= MAX_EVENTS_PER_RUN:
            return
        try:
            from app.server.events import EventBus, redact_metadata
            from app.server.redis_client import get_redis_client

            client = get_redis_client()
            key = f"run:{self.run_id}:history"
            sequence = client.incr(f"run:{self.run_id}:seq")
            body = json.dumps({
                "run_id": self.run_id,
                "event_id": str(uuid.uuid4()),
                "sequence": sequence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": self.stage,
                "event_type": event_type,
                "message": message,
                "files_modified": 0,
                "tests_passed": 0,
                "tests_failed": 0,
                "metadata": redact_metadata(metadata or {}),
            })
            # The same pipeline `EventBus.publish` uses. A bare rpush would
            # bypass the history cap, and agent activity is by far the
            # highest-volume event type - exactly what the cap exists to bound.
            pipe = client.pipeline()
            pipe.rpush(key, body)
            pipe.ltrim(key, -EventBus.MAX_HISTORY, -1)
            pipe.expire(key, EventBus.HISTORY_TTL_SECONDS)
            pipe.expire(f"run:{self.run_id}:seq", EventBus.HISTORY_TTL_SECONDS)
            pipe.publish(f"run:{self.run_id}:events", body)
            pipe.execute()
            self._published += 1
        except Exception:  # noqa: BLE001 - narration is never load-bearing
            logger.debug("Could not publish agent activity for %s", self.run_id, exc_info=True)

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:  # noqa: ARG002
        try:
            for generations in getattr(response, "generations", []) or []:
                for generation in generations or []:
                    text = getattr(generation, "text", "") or ""
                    if text.strip():
                        self._publish("agent_message", _clip(text))
        except Exception:  # noqa: BLE001
            logger.debug("Could not read an LLM response", exc_info=True)

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:  # noqa: ARG002
        name = (serialized or {}).get("name") or "tool"
        self._publish("tool_call", f"{name}: {_clip(input_str)}", {"tool": name})

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:  # noqa: ARG002
        self._publish("tool_result", _clip(output))

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:  # noqa: ARG002
        self._publish("tool_result", f"Failed: {_clip(str(error))}", {"failed": True})


def activity_stream_enabled() -> bool:
    """Opt-out switch, on by default. Set STREAM_AGENT_ACTIVITY=false to silence."""
    return os.environ.get("STREAM_AGENT_ACTIVITY", "true").strip().lower() in {"1", "true", "yes", "on"}


def build_activity_callbacks(run_id: str | None, stage: str) -> list[BaseCallbackHandler]:
    """The callbacks to attach to one agent invocation; empty when unavailable."""
    if not run_id or not activity_stream_enabled():
        return []
    return [AgentActivityStream(run_id, stage)]


__all__ = ["AgentActivityStream", "activity_stream_enabled", "build_activity_callbacks"]
```

The Redis key names are confirmed against `EventBus` (`events.py:104-114`):
history list `run:{id}:history`, counter `run:{id}:seq`, channel
`run:{id}:events`. Copy them exactly - a mismatch is a silent no-op, not an
error.

#### Carry the run id into the graph

**File:** `src/app/graph/workflow.py`. Find:

```python
def _run_config(thread_id: str, recursion_limit: int, metadata: dict | None = None) -> RunnableConfig:
    """Build the per-invoke config every entry point below shares."""
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}, "recursion_limit": recursion_limit}
```

Replace with:

```python
def _run_config(
    thread_id: str,
    recursion_limit: int,
    metadata: dict | None = None,
    run_id: str | None = None,
) -> RunnableConfig:
    """Build the per-invoke config every entry point below shares.

    `run_id` rides in `configurable` rather than `metadata` because metadata is
    only populated when LangSmith tracing is enabled, and the activity stream
    must work whether or not anyone is tracing.
    """
    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id, "run_id": run_id},
        "recursion_limit": recursion_limit,
    }
```

Add a keyword-only `run_id: str | None = None` to `start_workflow`,
`resume_pending_approval`, `resume_pending_review` and `resume_failed_run`, and
forward it to their `_run_config(...)` call - each already forwards `metadata`
the same way.

#### Attach the callbacks

Still in `workflow.py`, in `_run_gated_agent`. Find:

```python
    outer_thread_id = config["configurable"]["thread_id"]
```

Replace with:

```python
    outer_thread_id = config["configurable"]["thread_id"]
    # Narration only. Returns [] when the run id is unknown or the feature is
    # switched off, and the handler never raises.
    from app.server.agent_stream import build_activity_callbacks

    activity = build_activity_callbacks(config["configurable"].get("run_id"), stage_name)
```

Find:

```python
            result = resume_with_decision(agent, inner_thread_id, pending_decision)
```

Replace with:

```python
            result = resume_with_decision(
                agent, inner_thread_id, pending_decision, callbacks=activity
            )
```

If `resume_with_decision` does not accept `callbacks`, add it as a keyword-only
parameter defaulting to `None` and forward it into the config it builds. Do not
change its positional signature.

Find:

```python
            result = agent.invoke(initial_request, config={"configurable": {"thread_id": inner_thread_id}})
```

Replace with:

```python
            result = agent.invoke(
                initial_request,
                config={"configurable": {"thread_id": inner_thread_id}, "callbacks": activity},
            )
```

#### Pass the run id from the runner

**File:** `src/app/server/runner.py`. Every call to `start_workflow`,
`resume_pending_approval`, `resume_pending_review` and `resume_failed_run` gains
`run_id=run_id`. There are four in `_run_loop` and one in `_handle_state`'s
auto-approve branch. For example:

```python
                state = await asyncio.to_thread(
                    start_workflow, graph, document, repository, record.thread_id,
                    review_policy=record.review_policy, reviewer=record.reviewer,
                    metadata=trace_meta, run_id=run_id,
                )
```

#### Register the setting

`.env.example`, after the `CTX_SPECIFICATION_BUDGET` block:

```
# Live agent activity in the dashboard: one event per assistant message, tool
# call and tool result. Never per token. Set to false to silence it.
STREAM_AGENT_ACTIVITY=true
```

`docker-compose.yml`, in the shared `app-env` block:

```yaml
  STREAM_AGENT_ACTIVITY: ${STREAM_AGENT_ACTIVITY:-true}
```

**Verify:**

```bash
PYTHONPATH=src ENV=development .venv/bin/python - <<'PY'
from types import SimpleNamespace
from app.server.agent_stream import AgentActivityStream, MAX_TEXT, build_activity_callbacks
published = []
s = AgentActivityStream("run-test", "product_manager")
s._publish = lambda t, m, meta=None: published.append((t, m, meta))
s.on_llm_end(SimpleNamespace(generations=[[SimpleNamespace(text="I will read the brief.")]]))
s.on_tool_start({"name": "write_artifact"}, '{"relative_path": "docs/x.md"}')
s.on_tool_end("wrote 4kb")
s.on_tool_error(RuntimeError("nope"))
assert [p[0] for p in published] == ["agent_message","tool_call","tool_result","tool_result"]
assert "write_artifact" in published[1][1] and published[3][2] == {"failed": True}
s.on_llm_end(SimpleNamespace(generations=[[SimpleNamespace(text="x"*10_000)]]))
assert len(published[-1][1]) < MAX_TEXT + 200
s.on_llm_end(SimpleNamespace())          # malformed must not raise
assert build_activity_callbacks(None, "s") == []
print("OK")
PY
```

Then end to end, with the stack up and a run started:

```bash
docker compose exec -T redis redis-cli LRANGE "run:<your-run-id>:history" 0 -1 | grep -c agent_message
```

Must exceed zero within a minute. Zero means the Redis key names do not match.

### Step M-1c — The three-column layout

#### Equal panel heights

**File:** `langchain-ui/src/components/LogViewer.tsx`. Find:

```tsx
    <div className="glass-card rounded-2xl overflow-hidden">
```

Replace with:

```tsx
    <div className={`glass-card rounded-2xl overflow-hidden flex flex-col ${isExpanded ? 'h-full' : ''}`}>
```

Find:

```tsx
          className="p-4 max-h-[400px] overflow-y-auto bg-[#0a0f1a] font-mono text-xs leading-relaxed"
```

Replace with:

```tsx
          className="p-4 flex-1 min-h-0 overflow-y-auto bg-[#0a0f1a] font-mono text-xs leading-relaxed"
```

`min-h-0` is not optional: a flex child's default `min-height: auto` refuses to
shrink below its content, so without it the panel grows to fit every log line
and never scrolls. `h-full` only when expanded, so a collapsed panel stays a
header bar.

**File:** `langchain-ui/src/components/ArtifactList.tsx`. Find:

```tsx
    <div className="glass-card rounded-2xl overflow-hidden">
```

Replace with:

```tsx
    <div className="glass-card rounded-2xl overflow-hidden flex flex-col h-full">
```

Find:

```tsx
      <div className="divide-y divide-border/30">
```

Replace with:

```tsx
      <div className="divide-y divide-border/30 flex-1 min-h-0 overflow-y-auto">
```

Find:

```tsx
      <div className="glass-card rounded-2xl p-8 text-center">
```

Replace with:

```tsx
      <div className="glass-card rounded-2xl p-8 text-center h-full flex flex-col items-center justify-center">
```

#### The execution-flow rail

**Create** `langchain-ui/src/components/ExecutionFlow.tsx`:

```tsx
import React from 'react';
import type { RunStage } from '../types';
import { CheckCircle2, XCircle, AlertCircle, Loader2, Circle, GitCommitHorizontal } from 'lucide-react';

interface ExecutionFlowProps {
  stages: RunStage[];
  currentStage: string | null;
  isTerminal: boolean;
}

/**
 * The run's execution order as a top-down spine, one node per stage in the
 * order they first ran, newest at the bottom.
 *
 * Colour is the point: a glance must answer "is anything wrong, and is anything
 * waiting for me". Each status gets its own hue, and the hues mean the same
 * thing everywhere else in the app.
 */
const STATUS_STYLES: Record<string, { icon: React.ElementType; ring: string; dot: string; label: string }> = {
  completed:            { icon: CheckCircle2, ring: 'border-success/40 bg-success/10', dot: 'text-success', label: 'Passed' },
  running:              { icon: Loader2,      ring: 'border-primary/50 bg-primary/10', dot: 'text-primary animate-spin', label: 'Running' },
  waiting_for_approval: { icon: AlertCircle,  ring: 'border-warning/50 bg-warning/10', dot: 'text-warning', label: 'Sent for approval' },
  waiting_for_review:   { icon: AlertCircle,  ring: 'border-warning/50 bg-warning/10', dot: 'text-warning', label: 'Sent for review' },
  approved:             { icon: CheckCircle2, ring: 'border-success/40 bg-success/10', dot: 'text-success', label: 'Approved' },
  approved_with_notes:  { icon: CheckCircle2, ring: 'border-primary/40 bg-primary/10', dot: 'text-primary', label: 'Approved with comments' },
  rejected:             { icon: XCircle,      ring: 'border-danger/50 bg-danger/10',   dot: 'text-danger',  label: 'Rejected' },
  failed:               { icon: XCircle,      ring: 'border-danger/50 bg-danger/10',   dot: 'text-danger',  label: 'Failed' },
  cancelled:            { icon: Circle,       ring: 'border-border/50 bg-surface/40',  dot: 'text-text-muted', label: 'Cancelled' },
};

const FALLBACK = { icon: Circle, ring: 'border-border/50 bg-surface/40', dot: 'text-text-muted', label: 'Pending' };

const humanise = (name: string) =>
  name.replace(/^awaiting_(approval|user_review):/, '').replace(/_/g, ' ');

export const ExecutionFlow: React.FC<ExecutionFlowProps> = ({ stages, currentStage, isTerminal }) => {
  if (stages.length === 0) {
    return (
      <div className="glass-card rounded-2xl p-6 text-center text-sm text-text-muted">
        Waiting for the first stage to start.
      </div>
    );
  }

  return (
    <div className="glass-card rounded-2xl p-5 h-full flex flex-col">
      <h3 className="text-sm font-semibold text-white mb-5 uppercase tracking-wider flex items-center gap-2">
        <GitCommitHorizontal className="w-4 h-4 text-primary" />
        Execution Flow
      </h3>

      <ol className="flex-1 min-h-0 overflow-y-auto pr-1">
        {stages.map((stage, index) => {
          const isCurrent = stage.name === currentStage && !isTerminal;
          const key = isCurrent && stage.status === 'completed' ? 'running' : stage.status;
          const style = STATUS_STYLES[key] ?? FALLBACK;
          const Icon = style.icon;
          const isLast = index === stages.length - 1;

          return (
            <li key={`${stage.name}-${index}`} className="flex gap-3 relative">
              {!isLast && <div className="absolute left-[15px] top-8 bottom-0 w-px bg-border/50" aria-hidden />}

              <div className={`flex-none w-8 h-8 rounded-full border-2 flex items-center justify-center ${style.ring} ${isCurrent ? 'ring-4 ring-primary/20' : ''}`}>
                <Icon className={`w-3.5 h-3.5 ${style.dot}`} />
              </div>

              <div className="pb-6 min-w-0 flex-1">
                <p className="text-sm font-semibold text-white capitalize truncate" title={stage.name}>
                  {humanise(stage.name)}
                </p>
                <p className={`text-xs mt-0.5 ${style.dot.split(' ')[0]}`}>{style.label}</p>
                <div className="flex gap-2 mt-1 text-[11px] text-text-muted font-mono">
                  {stage.duration_seconds !== null && <span>{stage.duration_seconds.toFixed(1)}s</span>}
                  {stage.retry_count > 0 && <span className="text-warning">x{stage.retry_count + 1}</span>}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
};
```

Check `RunStage` in `langchain-ui/src/types/index.ts` has `name`, `status`,
`duration_seconds` and `retry_count`. Widen `status` to `string` if it is a
narrow union - the new statuses must be assignable.

#### The agent-activity rail

**Create** `langchain-ui/src/components/AgentActivity.tsx`:

```tsx
import React, { useEffect, useRef } from 'react';
import type { LogEntry } from '../types';
import { Sparkles, Wrench, CornerDownRight } from 'lucide-react';

interface AgentActivityProps {
  logs: LogEntry[];
}

const ACTIVITY_TYPES = new Set(['agent_message', 'tool_call', 'tool_result']);

/**
 * What the agent is doing right now, in the order it happened.
 *
 * Deliberately not the same view as Live Logs. Live Logs is the run's control
 * plane - stage transitions, gates, errors - and stays terse. This is the
 * model's own work: prose, the tools it called, and what came back.
 */
export const AgentActivity: React.FC<AgentActivityProps> = ({ logs }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const activity = logs.filter((l) => ACTIVITY_TYPES.has(l.event_type));

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [activity.length]);

  return (
    <div className="glass-card rounded-2xl overflow-hidden flex flex-col h-full">
      <div className="px-5 py-3.5 border-b border-border/50 flex items-center gap-2.5">
        <Sparkles className="h-4 w-4 text-primary" />
        <h3 className="font-semibold text-white text-sm">Agent Activity</h3>
        {activity.length > 0 && (
          <span className="bg-primary/20 text-primary text-xs px-2 py-0.5 rounded-full font-semibold">
            {activity.length}
          </span>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
        {activity.length === 0 ? (
          <p className="text-text-muted italic text-sm text-center py-8">
            Nothing yet. The agent's reasoning and tool calls appear here as they happen.
          </p>
        ) : (
          activity.map((entry) => {
            if (entry.event_type === 'agent_message') {
              return (
                <div key={entry.sequence} className="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap break-words">
                  {entry.message}
                </div>
              );
            }
            const isCall = entry.event_type === 'tool_call';
            const failed = entry.metadata?.failed === true;
            return (
              <div
                key={entry.sequence}
                className={`rounded-lg border px-3 py-2 text-xs font-mono break-words ${
                  failed ? 'border-danger/40 bg-danger/5 text-danger'
                         : 'border-border/40 bg-surface/40 text-text-secondary'
                }`}
              >
                <div className="flex items-center gap-1.5 mb-1 text-[11px] uppercase tracking-wider opacity-70">
                  {isCall ? <Wrench className="h-3 w-3" /> : <CornerDownRight className="h-3 w-3" />}
                  {isCall ? 'Tool call' : failed ? 'Tool failed' : 'Result'}
                </div>
                <span className="whitespace-pre-wrap">{entry.message}</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
```

If `LogEntry` has no `metadata` field, add
`metadata?: Record<string, unknown>;` to it in `src/types/index.ts`.

#### Wire the columns

**File:** `langchain-ui/src/pages/RunDashboard.tsx`. Add:

```tsx
import { ExecutionFlow } from '../components/ExecutionFlow';
import { AgentActivity } from '../components/AgentActivity';
```

Find:

```tsx
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <LogViewer logs={logs} />
        </div>
        <div>
          <ArtifactList artifacts={run.artifacts} runId={runId!} />
        </div>
      </div>
```

Replace with:

```tsx
      {/* Live Logs is the control plane - stages, gates, errors. Artifacts is
          what the run produced. Matched heights so the row has no dead space. */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-stretch h-[420px]">
        <div className="lg:col-span-2 min-h-0">
          <LogViewer logs={logs} />
        </div>
        <div className="min-h-0">
          <ArtifactList artifacts={run.artifacts} runId={runId!} />
        </div>
      </div>
```

Find the outermost element of the returned JSX:

```tsx
    <div className="max-w-7xl mx-auto space-y-6 animate-fade-in">
```

Replace with:

```tsx
    <div className="max-w-[110rem] mx-auto animate-fade-in xl:grid xl:grid-cols-[16rem_minmax(0,1fr)_22rem] xl:gap-6">
      {/* Left rail: execution order. Sticky, so the spine stays visible while
          the centre column scrolls. Hidden below xl, where three columns would
          be three unreadable ones - the same information is in Live Logs. */}
      <aside className="hidden xl:block xl:sticky xl:top-6 xl:h-[calc(100vh-3rem)]">
        <ExecutionFlow stages={run.stages || []} currentStage={run.current_stage} isTerminal={isTerminal} />
      </aside>

      <div className="space-y-6 min-w-0">
```

Find the component's last two lines:

```tsx
    </div>
  );
};
```

Replace with:

```tsx
      </div>

      {/* Right rail: the model's own work, as it happens. */}
      <aside className="hidden xl:block xl:sticky xl:top-6 xl:h-[calc(100vh-3rem)] mt-6 xl:mt-0">
        <AgentActivity logs={logs} />
      </aside>
    </div>
  );
};
```

You have added one opening `<div>` and one closing `</div>`, plus two
self-contained `<aside>` elements. `npx tsc -b` catches an imbalance.

#### Readable log labels

**File:** `langchain-ui/src/components/LogViewer.tsx`. Find:

```tsx
                    <span className={`font-semibold shrink-0 w-28 truncate ${getEventColor(log.event_type)}`} title={log.stage}>
                      {log.stage}
                    </span>
```

Replace with:

```tsx
                    <span
                      className={`font-semibold shrink-0 w-28 truncate ${getEventColor(log.event_type)}`}
                      title={log.stage}
                    >
                      {/* The raw stage is an internal routing key; a watching
                          human needs the role that acted. Full value on hover. */}
                      {log.stage.replace(/^awaiting_(approval|user_review):/, '').replace(/_/g, ' ')}
                    </span>
```

Find:

```tsx
      case 'stage_change': return 'text-primary';
```

Replace with:

```tsx
      case 'stage_change': return 'text-primary';
      case 'agent_message': return 'text-slate-400';
      case 'tool_call': return 'text-primary/70';
      case 'tool_result': return 'text-text-muted';
```

### Step M-1d — Retire the dead progress fields

`files_modified`, `tests_passed` and `tests_failed` have no writer anywhere.
Delete them from `RunEvent` (`src/app/server/events.py:41-43`) and from
`LogEntry` (`langchain-ui/src/types/index.ts:120-122`). A field that is always 0
reads as "nothing has changed" rather than "not measured", which is worse than
its absence.

If you do Part B's M-2, you may instead populate them: `files_modified` from
`changed_files`, the test counts from `RemediationCycle.test_runs`, which
`build_defect_report` already walks (`sprint/__init__.py:196-198`). Pick one;
do not leave them as they are.

Note: `agent_stream.py` above writes all three as `0` explicitly. If you delete
the fields, delete those three lines from the payload too.

### Step M-1e — Verify the dashboard

There is no frontend test runner (`package.json` has `dev`, `build`, `lint`,
`preview`). Verification is the type checker, the linter, and a manual pass.

```bash
cd langchain-ui && npx tsc -b && npx oxlint && cd ..
```

| # | Check | Pass condition |
|---|---|---|
| 1 | Left rail | More than one node once the run passes its first stage |
| 2 | Colours | Completed green, running spinning primary, gate amber, failure red |
| 3 | Order | Newest at the bottom; the line joins every node but the last |
| 4 | Repeats | A stage that runs twice shows `x2`, not two nodes |
| 5 | Right rail | Assistant text appears while the model works, not only at boundaries |
| 6 | Right rail | Tool calls are bordered blocks; a failed tool is red |
| 7 | Heights | Live Logs and Artifacts have identical edges; both scroll internally |
| 8 | Collapse | Collapsing Live Logs leaves a header bar, not a tall empty box |
| 9 | Narrow | Below 1280px the rails disappear; nothing overflows sideways |
| 10 | Unattended | No approval modal; the chip never reads WAITING FOR APPROVAL |

### Step M-1f — Tests for M-1

Six tests. `tests/test_events.py` is the natural home for both groups - it
already owns the event schema and the event bus.

Append to `tests/test_events.py`:

```python
# ---------------------------------------------------------------------------
# The execution timeline
# ---------------------------------------------------------------------------
#
# `RunStatusResponse.stages` was a hardcoded empty list, so the dashboard's flow
# chart fell through to a fallback that fabricates one node from `current_stage`.
# A run that had finished three stages showed one.


def _stage_event(stage: str, message: str, timestamp: str, status: str = "running"):
    from types import SimpleNamespace

    return SimpleNamespace(
        event_type="stage_change", stage=stage, message=message,
        timestamp=timestamp, metadata={"status": status},
    )


def test_the_timeline_has_one_node_per_stage_in_execution_order():
    from app.server.runs import _derive_stages

    stages = _derive_stages([
        _stage_event("product_manager", "Reading.", "2026-09-10T10:00:00+00:00"),
        _stage_event("tools_models", "Comparing.", "2026-09-10T10:02:00+00:00"),
        _stage_event("principal_architect", "Spec.", "2026-09-10T10:05:00+00:00"),
    ], "principal_architect")

    assert [s["name"] for s in stages] == [
        "product_manager", "tools_models", "principal_architect",
    ]
    assert stages[0]["duration_seconds"] == 120.0
    assert stages[0]["status"] == "completed"
    assert stages[-1]["status"] == "running", "the last stage is still open"


def test_a_repeated_stage_increments_rather_than_adding_a_node():
    """The specialist loop and review revisions re-enter the same node; a row
    per iteration would make the chart unreadable."""
    from app.server.runs import _derive_stages

    stages = _derive_stages([
        _stage_event("specialist_dispatch", "Working.", "2026-09-10T10:00:00+00:00"),
        _stage_event("specialist_dispatch", "Working.", "2026-09-10T10:01:00+00:00"),
        _stage_event("specialist_dispatch", "Working.", "2026-09-10T10:02:00+00:00"),
    ], "specialist_dispatch")

    assert len(stages) == 1
    assert stages[0]["retry_count"] == 2


def test_an_empty_history_yields_an_empty_timeline():
    from app.server.runs import _derive_stages

    assert _derive_stages([], None) == []


# ---------------------------------------------------------------------------
# Agent activity
# ---------------------------------------------------------------------------
#
# The graph only reported at node boundaries, so a real model turn was minutes
# of silence.


def _captured_stream():
    from app.server.agent_stream import AgentActivityStream

    published: list = []
    stream = AgentActivityStream("run-test", "product_manager")
    stream._publish = lambda kind, message, metadata=None: published.append(
        (kind, message, metadata)
    )
    return stream, published


def test_each_message_and_tool_call_becomes_one_event():
    from types import SimpleNamespace

    stream, published = _captured_stream()
    stream.on_llm_end(SimpleNamespace(generations=[[SimpleNamespace(text="I will read the brief.")]]))
    stream.on_tool_start({"name": "write_artifact"}, '{"relative_path": "docs/x.md"}')
    stream.on_tool_end("wrote 4kb")
    stream.on_tool_error(RuntimeError("nope"))

    assert [p[0] for p in published] == [
        "agent_message", "tool_call", "tool_result", "tool_result",
    ]
    assert "write_artifact" in published[1][1]
    assert published[3][2] == {"failed": True}


def test_a_long_message_is_clipped_before_it_reaches_the_dashboard():
    """This is a UI feed, not a record: the full text is already in the model's
    context and, for tool output, in the journal."""
    from types import SimpleNamespace

    from app.server.agent_stream import MAX_TEXT

    stream, published = _captured_stream()
    stream.on_llm_end(SimpleNamespace(generations=[[SimpleNamespace(text="x" * 10_000)]]))

    assert len(published[-1][1]) < MAX_TEXT + 200


def test_a_malformed_response_does_not_raise_into_the_agents_turn():
    """Narration must never fail the run it was narrating."""
    from types import SimpleNamespace

    from app.server.agent_stream import build_activity_callbacks

    stream, published = _captured_stream()
    stream.on_llm_end(SimpleNamespace())      # no `generations` at all

    assert published == []
    assert build_activity_callbacks(None, "any_stage") == []
```

**Verify:**

```bash
PATH="$SHIM:$PATH" PYTHONPATH=src ENV=development .venv/bin/python -m pytest \
  tests/test_events.py -q --no-cov
```

---

## B.2 — Steps for M-2

### Step M-2a — Record every command that runs

**File:** `src/app/tools/sandbox.py`. Insert above `class SandboxExecutor`:

```python
def _ledger_path(repo_root: str) -> "Path | None":
    """Where this run's execution ledger lives, or None if it cannot be placed.

    Keyed by the workspace directory name, which is per-run
    (`<product>-run-<uuid>`), so no run id has to be plumbed through the tool
    layer to reach here.

    Under DATA_DIR rather than in the workspace: the workspace is product
    output, listed as run artifacts and archived, and an execution log is
    neither.
    """
    try:
        name = Path(repo_root).resolve().name
        if not name:
            return None
        directory = Path(os.environ.get("DATA_DIR", ".")) / "ledger"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{re.sub(r'[^A-Za-z0-9_.-]+', '-', name)}.jsonl"
    except Exception:  # noqa: BLE001 - a missing ledger is not a failed command
        return None


def _record_execution(repo_root: str, role_name: str, argv: list[str], result: dict) -> None:
    """Append one command's outcome to the run's ledger. Never raises.

    Verification is currently self-reported: a specialist writes
    `tests: ["ran pytest, all green"]` and nothing establishes whether anything
    ran. The executor knows the truth - it has the argv and the exit code - and
    used to discard it the moment the tool result was consumed.
    """
    path = _ledger_path(repo_root)
    if path is None:
        return
    try:
        entry = {
            "at": datetime.now(timezone.utc).isoformat(),
            "role": role_name,
            "command": argv,
            "returncode": result.get("returncode"),
            "error": result.get("error"),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        logger.debug("Could not append to the execution ledger", exc_info=True)


def read_execution_ledger(repo_root: str, limit: int = 200) -> list[dict]:
    """Every command this run actually ran, oldest first. Never raises."""
    path = _ledger_path(repo_root)
    if path is None or not path.is_file():
        return []
    entries: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        return []
    return entries


def summarise_executions(repo_root: str) -> str:
    """A short digest of what actually ran, for a reviewer or a model."""
    entries = read_execution_ledger(repo_root)
    if not entries:
        return "No commands were executed in this workspace."
    lines = []
    for entry in entries[-40:]:
        argv = " ".join(str(part) for part in entry.get("command") or [])
        code = entry.get("returncode")
        outcome = "OK" if code == 0 else (f"exit {code}" if code is not None else "refused")
        lines.append(f"- [{entry.get('role', '?')}] {argv} -> {outcome}")
    passed = sum(1 for e in entries if e.get("returncode") == 0)
    return f"{len(entries)} command(s) executed, {passed} succeeded:\n" + "\n".join(lines)
```

Add the imports this needs at the top of `sandbox.py` if absent: `json`, `re`,
`from datetime import datetime, timezone`. Confirm `Path`, `os` and `logger`
are already there.

Then call `_record_execution` at every point `execute` returns. There are three
result paths (the timeout path near `:385`, the container path near `:393`, the
in-container path near `:468`). Build the dict into a local first:

```python
            outcome = {
                "returncode": result.returncode,
                "stdout": _truncate(result.stdout, f"{role_name}-{argv[0]}-stdout"),
                "stderr": _truncate(result.stderr, f"{role_name}-{argv[0]}-stderr"),
            }
            _record_execution(repo_root, role_name, argv, outcome)
            return outcome
```

**Also record refusals** - the `ALLOW_COMMAND_EXECUTION` path near `:408` and the
`CommandNotAllowed` path. A specialist that tried to run a test and was refused
is materially different from one that never tried, and only the ledger can tell
them apart.

### Step M-2b — Make the specialist state its evidence structurally

**File:** `src/app/agents/specialists.py`. Insert above `class SpecialistOutput`:

```python
class VerificationRun(BaseModel):
    """One command a specialist ran to prove its work, and what happened.

    Free-text `tests` was the only evidence, so `["ran pytest, all green"]` was
    indistinguishable from having run it. This is checkable:
    `app.tools.sandbox.read_execution_ledger` holds what actually executed in
    this workspace, and a claim here that is absent there is one the model
    invented.
    """

    model_config = ConfigDict(extra="forbid")

    command: list[str] = Field(description='The argv you ran, e.g. ["pytest", "-q"].')
    exit_code: int = Field(description="The `returncode` the tool returned. 0 means success.")
    summary: str = Field(default="", description="One line on what it proved, or how it failed.")
```

Find:

```python
    tests: list[str] = Field(default_factory=list, description="Tests added, updated, or run for this task.")
```

Replace with:

```python
    tests: list[str] = Field(default_factory=list, description="Tests added, updated, or run for this task.")
    verification: list[VerificationRun] = Field(
        default_factory=list,
        description=(
            "Commands you actually executed to prove this task works, with their exit codes. "
            "Leave empty only if you executed nothing. Do not describe commands here that you "
            "did not run - the workspace keeps its own record of every execution and the two "
            "are compared."
        ),
    )
```

Then find, in the shared specialist system prompt:

```
- If you cannot verify something (a test, a security property), say so as a
```

Insert immediately **above** it:

```
- Prove your work by running it. Write the code, then use `run_terminal_command`
  (or `run_validation`) to build it, start it, or test it, and record every
  command you ran in `verification` with its exit code. A task reported complete
  with an empty `verification` list is a task nobody checked.
- If a command's output was truncated, call `read_command_output` with the
  reference in the truncation pointer to see the part that was cut. The real
  error is usually there.
```

### Step M-2c — Compare the claim against the record

**File:** `src/app/agents/milestone_reviewer.py`. Add above
`build_milestone_review_request`:

```python
def _execution_evidence(repository_root: str) -> str:
    """What actually ran, from the executor's own record. Never raises.

    The reviewer was given the specialists' account of their work and no way to
    check it. This is the record of every command in this workspace, so "the
    tests pass" can be compared against whether a test command ran at all.
    """
    try:
        from app.tools.sandbox import summarise_executions

        return summarise_executions(repository_root)
    except Exception:  # noqa: BLE001 - a reviewer without evidence still reviews
        return "The execution record could not be read for this workspace."
```

In `build_milestone_review_request`, add as the last interpolated section of the
`brief`:

```python
        f"--- Commands actually executed in this workspace ---\n"
        f"{_execution_evidence(repository_root)}\n\n"
```

And add to the milestone reviewer's system-prompt constraints:

```
- Treat the executed-command record as authoritative over any specialist's
  description of its own testing. A milestone whose specialists report passing
  tests, but whose record shows no test command ran, is not verified - raise it
  as a blocking finding.
```

### Step M-2d — Widen the allowlist to what a real build needs

**File:** `src/app/tools/sandbox.py`. Find:

```python
ROLE_EXECUTABLES: dict[str, frozenset[str]] = {
    "ui_specialist": frozenset({"npm", "npx", "node", "yarn", "pnpm"}),
    "backend_specialist": frozenset({"python", "python3", "pip", "pip3", "pytest", "cargo", "go", "uv"}),
    "database_specialist": frozenset({"prisma", "psql", "alembic"}),
    "testing_specialist": frozenset({"pytest", "python", "python3", "npm", "yarn", "pnpm", "go", "cargo"}),
    "principal_architect": frozenset({"npx", "npm", "django-admin"}),
}
```

Replace with:

```python
ROLE_EXECUTABLES: dict[str, frozenset[str]] = {
    # `make` is added across build-capable roles: a Makefile is the entry point
    # for a large share of real projects, and without it those cannot be built
    # at all. It executes only what the repository's own Makefile contains,
    # which the agent wrote through the gated write tool.
    "ui_specialist": frozenset({"npm", "npx", "node", "yarn", "pnpm", "make", "python3"}),
    "backend_specialist": frozenset({
        "python", "python3", "pip", "pip3", "pytest", "cargo", "go", "uv", "make", "npm", "npx",
    }),
    # A migration is a script, and the role that writes one has to run it.
    "database_specialist": frozenset({"prisma", "psql", "alembic", "python", "python3", "make"}),
    "testing_specialist": frozenset({
        "pytest", "python", "python3", "npm", "npx", "yarn", "pnpm", "go", "cargo", "make",
    }),
    "principal_architect": frozenset({"npx", "npm", "django-admin"}),
}
```

Find:

```python
    "git": frozenset({"-c", "--exec-path", "--upload-pack", "--receive-pack"}),
}
```

Replace with:

```python
    "git": frozenset({"-c", "--exec-path", "--upload-pack", "--receive-pack"}),
    # -f/--file would run a makefile from anywhere; --eval injects rules on the
    # command line. Both turn `make` into a general interpreter pointed at
    # something the workspace does not contain.
    "make": frozenset({"-f", "--file", "--makefile", "--eval", "-e"}),
}
```

Deliberately **not** added: `rm`/`mv`/`cp` (the gated write tool is the only
sanctioned mutation path); `docker` (in `in-container` mode the socket is the
host's, which is root on the host); `curl`/`wget` (only the `install` category
has networking, and package managers are the sanctioned way to use it).

### Step M-2e — Tests for M-2

Append to `tests/test_sandbox_in_container.py`:

```python
# ---------------------------------------------------------------------------
# The execution ledger
# ---------------------------------------------------------------------------


@needs_python
def test_a_command_that_runs_is_recorded(workspace, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "in-container")
    from app.tools.sandbox import SandboxExecutor, read_execution_ledger

    SandboxExecutor.execute(command=["echo", "hello"], repo_root=workspace,
                            role_name="backend_specialist", category="default")

    entries = read_execution_ledger(workspace)
    assert len(entries) == 1
    assert entries[0]["command"] == ["echo", "hello"]
    assert entries[0]["returncode"] == 0


def test_a_refused_command_is_recorded_too(workspace, monkeypatch, tmp_path):
    """"Tried and was refused" and "never tried" are different failures."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "in-container")
    from app.tools.sandbox import SandboxExecutor, read_execution_ledger

    SandboxExecutor.execute(command=["curl", "http://example.com"], repo_root=workspace,
                            role_name="backend_specialist", category="default")

    assert read_execution_ledger(workspace), "a refusal must still be recorded"


def test_the_ledger_summary_is_readable_by_a_reviewer(workspace, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.tools.sandbox import summarise_executions

    assert "No commands were executed" in summarise_executions(workspace)


def test_two_runs_do_not_share_a_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.tools.sandbox import _ledger_path

    assert _ledger_path(str(tmp_path / "app-run-aaaa")) != _ledger_path(str(tmp_path / "app-run-bbbb"))


def test_make_cannot_be_pointed_at_another_makefile():
    from app.tools.sandbox import CommandNotAllowed, validate_command

    validate_command(["make", "build"], "backend_specialist")
    with pytest.raises(CommandNotAllowed):
        validate_command(["make", "-f", "/tmp/evil.mk"], "backend_specialist")


def test_a_role_can_run_the_migration_it_writes():
    from app.tools.sandbox import validate_command

    validate_command(["python3", "migrate.py"], "database_specialist")


def test_destructive_verbs_are_still_refused_for_every_role():
    from app.tools.sandbox import CommandNotAllowed, validate_command

    for role in ("ui_specialist", "backend_specialist", "testing_specialist",
                 "database_specialist", "principal_architect"):
        for verb in ("rm", "docker", "curl", "wget"):
            with pytest.raises(CommandNotAllowed):
                validate_command([verb, "anything"], role)
```

The first test is marked `@needs_python` only if it resolves a bare `python`;
`echo` does not, so **drop the marker** if your `_execute_here` resolves `echo`
from PATH without needing `python`. Check which by running the test both with
and without the shim.

Append to `tests/test_run_recovery.py`:

```python
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

This is the test removed in phase 2 as orphaned. Adding it back is correct *only
once Step M-2b exists*; do not add it before.

---

## Final verification

```bash
export SHIM=/tmp/pyshim && mkdir -p "$SHIM" && ln -sf "$(pwd)/.venv/bin/python" "$SHIM/python"

# 1. Suite.
PATH="$SHIM:$PATH" PYTHONPATH=src ENV=development .venv/bin/python -m pytest tests/ -q --no-cov
# expect after Part A: 651 passed, 1 skipped
# expect after Part B: 665 passed, 1 skipped

# 2. Coverage.
PATH="$SHIM:$PATH" PYTHONPATH=src ENV=development .venv/bin/python -m pytest tests/ -q
# expect >= 83%

# 3. Security (read the *severity* section, not confidence).
.venv/bin/python -m bandit -r src/app -ll

# 4. Frontend.
cd langchain-ui && npx tsc -b && npx oxlint && cd ..

# 5. No node restarts a run from intake (phase-2 invariant, re-checked).
PYTHONPATH=src ENV=development .venv/bin/python - <<'PY'
from types import SimpleNamespace
from app.graph.workflow import resume_failed_run, _NODE_NAMES, _UNREWINDABLE_NODES
def snap(n): return SimpleNamespace(next=n, values={})
class G:
    def __init__(s,h): s._h=h; s.updates=[]
    def get_state(s,c): return SimpleNamespace(values={"stage":"failed"})
    def get_state_history(s,c): return iter(s._h)
    def update_state(s,c,v,as_node=None): s.updates.append((v,as_node))
    def invoke(s,i,config=None): return {}
for node in sorted(_NODE_NAMES - _UNREWINDABLE_NODES):
    g=G([snap(()),snap(("failed",)),snap((node,))]); resume_failed_run(g,"t")
    assert not (g.updates[0][0]["stage"]=="product_manager" and node!="product_manager"), node
print("OK")
PY

# 6. reconcile-runs no longer un-repairs anything.
PYTHONPATH=src ENV=development .venv/bin/python -m app.server.manage reconcile-runs --dry-run

# 7. Commit.
git add -A && git commit -m "fix: clone settings, reconcile safety, resume guard; feat: dashboard rails and execution ledger"
```

## The verification that actually matters

Everything above is unit-level. The system has never produced a line of source
code: every workspace holds only `docs/*.md`, and `DATA_DIR/journal/` does not
exist, so no command has ever run. F-0 and F-1 were why runs kept dying before
the specialist stage, and both are fixed.

So **start a run and watch it reach `specialist_dispatch`.** Then:

```bash
docker compose exec -T worker sh -c 'cat /app/data/ledger/*.jsonl | head -20'
docker compose exec -T worker sh -c 'find /app/data/workspaces -name "*.py" -o -name "*.ts" | head'
```

The first must show real build and test commands with exit codes. The second
must show source files. Until both do, M-2 is unproven - and so is the claim
that this system writes working software.

## What none of this gives you

Even fully implemented, `verification` is the model's own account cross-checked
against a ledger. The ledger proves a command ran and what it exited with; it
does not prove the command was the *right* one. A specialist can run
`pytest tests/test_nothing.py`, get exit 0, and report a verified milestone.

Closing that needs a check the model does not author - a coverage threshold, or a
workflow-owned test command derived from the sprint's acceptance criteria rather
than chosen by the specialist. That is a larger design change and is deliberately
out of scope.
