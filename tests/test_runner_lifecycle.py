"""Runner lifecycle: dispatch, atomic transitions, cancellation and the run loop.

The run loop is where several of the worst defects lived, and it was the least
covered module in the project. The graph is faked here so the loop's own control
flow is what gets exercised, not an LLM.
"""

from datetime import datetime, timezone

import pytest

from app.server.events import EventBus
from app.server.runner import (
    RunConflict,
    RunRecord,
    WorkflowRunner,
    _api_status,
    _public_model_overrides,
    _stage_meaning,
)


@pytest.fixture
def runner(run_store, redis_container, monkeypatch):
    from app.server.redis_client import reset_clients

    reset_clients()
    monkeypatch.setenv("CHECKPOINTER_TYPE", "memory")
    return WorkflowRunner(EventBus(), run_store=run_store)


@pytest.fixture
def dispatched(monkeypatch):
    """Capture Celery dispatches instead of enqueuing them."""
    calls = []

    class _AsyncResult:
        id = "task-1"

    def _delay(**kwargs):
        calls.append(kwargs)
        return _AsyncResult()

    import app.server.tasks as tasks_module

    monkeypatch.setattr(tasks_module.execute_workflow_run, "delay", _delay)
    return calls


def _register(runner, run_id="run-1", **overrides):
    record = runner.register_run(
        run_id=run_id,
        thread_id=f"thread-{run_id}",
        document_names=["brief.md"],
        document_paths=["/tmp/brief.md"],
        owner="alice",
        tenant_id="acme",
    )
    if overrides:
        for key, value in overrides.items():
            setattr(record, key, value)
        runner.run_store.save(record)
    return record


# ---------------------------------------------------------------------------
# Stage mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        ("complete", "completed"),
        ("failed", "failed"),
        ("awaiting_approval:product_manager", "waiting_for_approval"),
        ("awaiting_user_review:sprint", "waiting_for_review"),
        ("product_manager", "running"),
    ],
)
def test_stage_maps_to_api_status(stage, expected):
    assert _api_status(stage) == expected


def test_a_paused_stage_gets_a_readable_meaning():
    assert "approval" in _stage_meaning("awaiting_approval:principal_architect").lower()
    assert "review" in _stage_meaning("awaiting_user_review:sprint").lower()


def test_an_unknown_stage_falls_back_to_its_own_name():
    assert _stage_meaning("something_new") == "something_new"


# ---------------------------------------------------------------------------
# Model overrides
# ---------------------------------------------------------------------------


def test_secrets_are_stripped_from_persisted_overrides():
    """Keys must not reach the metadata table or the Celery broker."""
    cleaned = _public_model_overrides(
        {
            "model_name": "gpt-4o",
            "openai_api_key": "sk-secret",
            "anthropic_api_key": "sk-ant",
            "google_api_key": "goog",
            "llm_provider": "openai",
        }
    )
    assert cleaned == {"model_name": "gpt-4o", "llm_provider": "openai"}


def test_empty_overrides_collapse_to_nothing():
    assert _public_model_overrides({"model_name": None}) == {}
    assert _public_model_overrides(None) == {}


# ---------------------------------------------------------------------------
# Registration and dispatch
# ---------------------------------------------------------------------------


def test_registering_persists_ownership(runner):
    record = _register(runner)
    loaded = runner.run_store.load(record.run_id)
    assert loaded.owner == "alice"
    assert loaded.tenant_id == "acme"
    assert loaded.status == "created"


async def test_starting_dispatches_and_records_the_task_id(runner, dispatched, tmp_path):
    from app.state import RepositoryContext

    _register(runner)
    repository = RepositoryContext(
        root_path=str(tmp_path), branch="main", commit="abc", status="clean"
    )

    await runner.start_run(
        "run-1", document=None, repository=repository, model_overrides={"model_name": "gpt-4o"}
    )

    assert dispatched[0]["run_id"] == "run-1"
    assert dispatched[0]["resume"] is False
    record = runner.run_store.load("run-1")
    assert record.status == "running"
    assert record.task_id == "task-1"
    # Overrides are persisted now; they used to be built and silently dropped.
    assert record.model_overrides == {"model_name": "gpt-4o"}


async def test_starting_twice_conflicts(runner, dispatched, tmp_path):
    from app.state import RepositoryContext

    _register(runner)
    repository = RepositoryContext(
        root_path=str(tmp_path), branch="main", commit="abc", status="clean"
    )
    await runner.start_run("run-1", document=None, repository=repository)

    with pytest.raises(RunConflict):
        await runner.start_run("run-1", document=None, repository=repository)


async def test_only_a_failed_run_can_be_resumed(runner, dispatched):
    _register(runner, status="running")
    with pytest.raises(RunConflict):
        await runner.resume_run("run-1")

    _register(runner, run_id="run-2", status="failed", error="boom")
    await runner.resume_run("run-2")
    assert runner.run_store.load("run-2").status == "running"
    assert runner.run_store.load("run-2").error is None


async def test_an_approval_is_only_accepted_while_waiting(runner, dispatched):
    _register(runner, status="running")
    with pytest.raises(RunConflict):
        await runner.submit_approval("run-1", {"type": "approve"})

    _register(runner, run_id="run-2", status="waiting_for_approval")
    await runner.submit_approval("run-2", {"type": "approve"})
    assert dispatched[-1]["decision_payload"]["type"] == "approval"


async def test_a_double_submitted_approval_is_refused(runner, dispatched):
    """Both submissions used to pass the read-then-write guard and dispatch."""
    _register(runner, status="waiting_for_approval")
    await runner.submit_approval("run-1", {"type": "approve"})

    with pytest.raises(RunConflict):
        await runner.submit_approval("run-1", {"type": "approve"})
    assert len(dispatched) == 1


async def test_a_review_is_only_accepted_while_waiting(runner, dispatched):
    _register(runner, status="waiting_for_review")
    await runner.submit_review("run-1", {"type": "approve"})
    assert dispatched[-1]["decision_payload"]["type"] == "review"


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


async def test_cancelling_a_paused_run_marks_it_terminal(runner, monkeypatch):
    _register(runner, status="waiting_for_approval", task_id="task-9")

    revoked = []
    import app.server.tasks as tasks_module

    monkeypatch.setattr(
        tasks_module.celery_app.control,
        "revoke",
        lambda task_id, **kw: revoked.append(task_id),
    )

    await runner.cancel_run("run-1")

    record = runner.run_store.load("run-1")
    assert record.status == "cancelled"
    assert record.cancel_requested is True
    # The task is actually revoked; cancel used to be advisory only.
    assert revoked == ["task-9"]


async def test_cancelling_a_running_run_flags_it_for_the_worker(runner, monkeypatch):
    """A running worker stops at its next checkpoint rather than being killed
    mid-write, so the status stays 'running' until it acknowledges."""
    _register(runner, status="running", task_id="task-8")

    import app.server.tasks as tasks_module

    monkeypatch.setattr(tasks_module.celery_app.control, "revoke", lambda *a, **k: None)

    await runner.cancel_run("run-1")
    assert runner.run_store.is_cancel_requested("run-1")


async def test_cancelling_a_terminal_run_is_a_no_op(runner):
    _register(runner, status="completed")
    await runner.cancel_run("run-1")
    assert runner.run_store.load("run-1").status == "completed"


# ---------------------------------------------------------------------------
# The run loop
# ---------------------------------------------------------------------------


class _FakeGraph:
    """Returns a scripted sequence of states, one per invoke."""

    def __init__(self, states):
        self._states = list(states)
        self.invocations = 0

    def invoke(self, _input, _config=None):
        self.invocations += 1
        return self._states.pop(0) if self._states else {"stage": "complete"}


async def test_a_terminal_state_completes_the_run(runner, monkeypatch):
    record = _register(runner, status="running")
    graph = _FakeGraph([])

    await runner._handle_state(record, graph, {"stage": "complete"}, {})

    assert runner.run_store.load("run-1").status == "completed"


async def test_a_failed_state_records_the_error(runner):
    record = _register(runner, status="running")

    await runner._handle_state(record, _FakeGraph([]), {"stage": "failed", "error": "nope"}, {})

    stored = runner.run_store.load("run-1")
    assert stored.status == "failed"
    assert stored.error == "nope"


async def test_an_approval_pause_stops_and_waits(runner):
    record = _register(runner, status="running")

    await runner._handle_state(
        record, _FakeGraph([]), {"stage": "awaiting_approval:product_manager"}, {}
    )

    assert runner.run_store.load("run-1").status == "waiting_for_approval"


async def test_a_review_pause_stops_and_waits(runner):
    record = _register(runner, status="running")

    await runner._handle_state(
        record, _FakeGraph([]), {"stage": "awaiting_user_review:sprint"}, {}
    )

    assert runner.run_store.load("run-1").status == "waiting_for_review"


async def test_a_mid_flight_state_re_invokes_rather_than_spinning(runner):
    """The loop used to `continue` without re-invoking, republishing the same
    event MAX_GATES times and then reporting a gate-limit failure that had not
    occurred."""
    record = _register(runner, status="running")
    graph = _FakeGraph([{"stage": "tools_models"}, {"stage": "complete"}])

    await runner._handle_state(record, graph, {"stage": "product_manager"}, {})

    assert graph.invocations == 2
    assert runner.run_store.load("run-1").status == "completed"


async def test_a_cancellation_request_stops_the_loop(runner):
    record = _register(runner, status="running")
    runner.run_store.request_cancel("run-1", datetime.now(timezone.utc).isoformat())

    await runner._handle_state(record, _FakeGraph([]), {"stage": "product_manager"}, {})

    assert runner.run_store.load("run-1").status == "cancelled"


async def test_the_gate_ceiling_is_enforced(runner, monkeypatch):
    """A graph that never settles must stop, not loop forever."""
    import app.server.runner as runner_module

    monkeypatch.setattr(runner_module, "MAX_GATES", 3)
    record = _register(runner, status="running")
    graph = _FakeGraph([{"stage": "product_manager"} for _ in range(10)])

    await runner._handle_state(record, graph, {"stage": "product_manager"}, {})

    stored = runner.run_store.load("run-1")
    assert stored.status == "failed"
    assert "automatic approvals" in stored.error


# ---------------------------------------------------------------------------
# The status recorded when an invoke raises
# ---------------------------------------------------------------------------
#
# A node that raises is never checkpointed, so the graph is still parked exactly
# where it was before the attempt. Recording a flat "failed" desynchronised the
# row from the graph and made the run unreachable: the UI offers Resume for a
# failed run, but Resume cannot clear an approval gate, and /approve refuses
# anything whose status is not `waiting_for_approval`.


@pytest.mark.parametrize(
    "stage, expected",
    [
        ("awaiting_approval:principal_architect", "waiting_for_approval"),
        ("awaiting_user_review:specification", "waiting_for_review"),
        ("principal_architect", "failed"),
        ("", "failed"),
    ],
)
def test_failure_status_follows_the_stage_the_graph_is_parked_on(runner, stage, expected):
    record = RunRecord(
        run_id="run-x", thread_id="thread-x", document_names=[], document_paths=[],
        current_stage=stage,
    )

    assert runner._status_after_failure(record) == expected


def test_a_failure_on_a_gate_leaves_exactly_one_usable_route(runner):
    """The deadlock: status said `failed`, current_stage said waiting."""
    record = RunRecord(
        run_id="run-y", thread_id="thread-y", document_names=[], document_paths=[],
        current_stage="awaiting_approval:principal_architect",
    )

    status = runner._status_after_failure(record)

    assert status == _api_status(record.current_stage)


# ---------------------------------------------------------------------------
# What a run pins, and what it must not
# ---------------------------------------------------------------------------
#
# `llm_provider` and `model_name` are experiment choices: re-running later
# should use the same model. A base URL is not - it is where the model happens
# to be hosted, and the host moves. Pinning it meant that relocating the model
# server permanently broke every run that already existed: the stored URL beat
# the corrected setting on every resume, so there was no way to repoint them.


def test_the_model_and_provider_are_pinned_to_the_run():
    from app.server.runner import _public_model_overrides

    kept = _public_model_overrides({"llm_provider": "local", "model_name": "qwen-30b"})

    assert kept == {"llm_provider": "local", "model_name": "qwen-30b"}


def test_the_base_url_is_not_pinned_to_the_run():
    from app.server.runner import _public_model_overrides

    kept = _public_model_overrides(
        {"llm_provider": "local", "model_name": "qwen-30b",
         "openai_base_url": "http://old-host:1234/v1"}
    )

    assert "openai_base_url" not in kept


def test_a_run_stored_before_the_fix_stops_using_its_stale_url():
    """Rows written earlier still carry a base URL; it must not be applied."""
    from app.server.runner import _applicable_overrides

    applied = _applicable_overrides(
        {"llm_provider": "local", "model_name": "qwen-30b",
         "openai_base_url": "http://host-that-moved:1234/v1"}
    )

    assert applied == {"llm_provider": "local", "model_name": "qwen-30b"}


def test_credentials_are_still_stripped_from_applied_overrides():
    from app.server.runner import _applicable_overrides

    applied = _applicable_overrides({"model_name": "m", "openai_api_key": "sk-secret"})

    assert applied == {"model_name": "m"}


# ---------------------------------------------------------------------------
# The auto-approval ceiling
# ---------------------------------------------------------------------------
#
# Only an unattended run gets near this. A supervised run returns to the human
# at each gate, ending the segment; an unattended one answers every gate itself
# and does the whole build in one segment, so every artifact write by every
# specialist across every sprint is one round.


def test_the_gate_ceiling_is_high_enough_for_a_real_unattended_build():
    """200 was sized for a supervised run and stopped real builds part-way."""
    from app.server.runner import MAX_GATES

    assert MAX_GATES >= 1000


def test_the_gate_ceiling_is_configurable(monkeypatch):
    import importlib

    monkeypatch.setenv("WORKFLOW_MAX_GATES", "42")
    import app.server.runner as runner_module

    reloaded = importlib.reload(runner_module)
    try:
        assert reloaded.MAX_GATES == 42
    finally:
        monkeypatch.delenv("WORKFLOW_MAX_GATES", raising=False)
        importlib.reload(runner_module)


@pytest.mark.asyncio
async def test_exhausting_the_gate_ceiling_is_reported(runner, monkeypatch):
    """The failure an unattended run is most likely to hit.

    It used to be recorded silently - the row said "failed" while no event was
    published and the stream was never closed - so a UI watching the run waited
    forever for something that had already stopped.
    """
    import app.server.runner as runner_module

    monkeypatch.setattr(runner_module, "MAX_GATES", 2)

    record = _register(runner, "run-gates")
    record.auto_approve = True
    published = []

    async def _capture(run_id, event):
        published.append(event)

    closed = []

    async def _close(run_id):
        closed.append(run_id)

    monkeypatch.setattr(runner.event_bus, "publish", _capture)
    monkeypatch.setattr(runner.event_bus, "close", _close)

    # A stage that is neither terminal nor a pause, so the loop keeps going.
    class _StuckGraph:
        def invoke(self, _input, config=None):
            return {"stage": "product_manager"}

    await runner._handle_state(record, _StuckGraph(), {"stage": "product_manager"}, {})

    assert record.status == "failed"
    assert "automatic approvals" in record.error
    assert any(e.event_type == "error" for e in published), "no error event was published"
    assert closed == ["run-gates"], "the event stream was never closed"


# ---------------------------------------------------------------------------
# An unattended run is not waiting for anyone (Part 4d)
# ---------------------------------------------------------------------------
#
# The bug: `_update_record` persisted `_api_status(stage)` at the top of
# `_handle_state`'s loop, before the auto-approve branch ran. The row said
# "waiting_for_approval" for as long as the resumed agent took, which showed the
# user an approval modal for a gate that was clearing itself - and, worse,
# satisfied `submit_approval`'s compare-and-set guard, dispatching a second
# Celery task onto a thread the first was still driving.


def test_an_unattended_run_is_never_persisted_as_waiting_for_approval():
    from app.server.runner import _stage_narration

    _, status = _stage_narration("awaiting_approval:product_manager", auto_approve=True)

    assert status == "running"


def test_an_attended_run_still_reports_the_gate():
    from app.server.runner import _stage_narration

    message, status = _stage_narration("awaiting_approval:tools_models", auto_approve=False)

    assert status == "waiting_for_approval"
    assert "Waiting for approval" in message


def test_auto_approve_does_not_swallow_a_review_gate():
    """auto_approve answers artifact writes; review points are `review_policy`."""
    from app.server.runner import _stage_narration

    _, status = _stage_narration("awaiting_user_review:sprint", auto_approve=True)

    assert status == "waiting_for_review"


@pytest.mark.parametrize(
    "stage, expected",
    [("complete", "completed"), ("failed", "failed"), ("scrum_master", "running")],
)
def test_terminal_and_working_stages_are_unaffected_by_auto_approve(stage, expected):
    from app.server.runner import _stage_narration

    assert _stage_narration(stage, auto_approve=True)[1] == expected
