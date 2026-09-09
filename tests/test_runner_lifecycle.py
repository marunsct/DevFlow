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
    assert "gates" in stored.error
