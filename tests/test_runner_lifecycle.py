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


async def test_a_stage_transition_does_not_crash_the_loop(runner):
    """A transition between two stages is the moment the previous stage's
    duration is recorded.

    That call used to name a function that did not exist, so the very first
    transition raised `NameError: name '_record_stage_duration' is not defined`
    and every run died on it - silently, because the graph had already done its
    work by then and the failure looked like a flaky model error. A graph that
    moves through more than one stage reaches that line; a single-stage one
    never does, which is why the other tests never caught it.
    """
    record = _register(runner, status="running")
    graph = _FakeGraph([{"stage": "complete"}])

    await runner._handle_state(record, graph, {"stage": "product_manager"}, {})

    stored = runner.run_store.load("run-1")
    assert stored.status == "completed"
    assert stored.error is None


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
    # Alternating stages: the graph never settles, but it *is* running something
    # each round. A graph returning one unchanging stage is the idle-spin case,
    # which is caught sooner and reported differently.
    graph = _FakeGraph([
        {"stage": "product_manager" if index % 2 else "tools_models"} for index in range(10)
    ])

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


def test_an_unattended_run_that_raises_on_a_gate_stays_resumable(runner):
    """The mirror-image deadlock, for a run with nobody to ask.

    Deriving the status from the stage opens the approval route, which is the
    right call for a supervised run. An unattended run has no approval route:
    `submit_approval` refuses it outright because it answers its own gates. So
    reporting `waiting_for_approval` closed /approve *and* /resume at once, and
    a real run lost 25 minutes of work with no way back in except cloning it.
    """
    record = RunRecord(
        run_id="run-z", thread_id="thread-z", document_names=[], document_paths=[],
        current_stage="awaiting_approval:principal_architect", auto_approve=True,
    )

    assert runner._status_after_failure(record) == "failed"


def test_an_unattended_run_resumes_by_answering_its_own_gate(runner):
    """The other half of the deadlock, on the way back in.

    Reporting `failed` opens /resume, but resume alone re-enters the paused gate
    and `resume_failed_run` rightly refuses it: a parked run needs a decision,
    not a retry. For an unattended run there is no one to give that decision, so
    it has to supply its own - which is what it does at every other gate.
    """
    record = RunRecord(
        run_id="run-gate", thread_id="thread-gate", document_names=[], document_paths=[],
        current_stage="awaiting_approval:principal_architect", auto_approve=True,
    )

    assert runner._resume_means_answering_own_gate(record) is True


@pytest.mark.parametrize(
    ("stage", "auto_approve"),
    [
        # A supervised run has a person who can answer; asking them is correct.
        ("awaiting_approval:principal_architect", False),
        # A review needs a human whether or not writes are auto-approved.
        ("awaiting_user_review:specification", True),
        # Not parked at all: this is a genuine retry.
        ("principal_architect", True),
        ("", True),
    ],
)
def test_other_runs_resume_as_a_retry(runner, stage, auto_approve):
    record = RunRecord(
        run_id="run-other", thread_id="thread-other", document_names=[], document_paths=[],
        current_stage=stage, auto_approve=auto_approve,
    )

    assert runner._resume_means_answering_own_gate(record) is False


def test_an_unattended_run_still_defers_to_a_human_review_gate(runner):
    """Auto-approve covers artifact writes, not review sessions.

    A review point genuinely needs a person whether or not writes are gated, so
    the review status must survive the unattended special case.
    """
    record = RunRecord(
        run_id="run-w", thread_id="thread-w", document_names=[], document_paths=[],
        current_stage="awaiting_user_review:specification", auto_approve=True,
    )

    assert runner._status_after_failure(record) == "waiting_for_review"


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
    """Read through `_max_gates()` rather than by reloading the module.

    `importlib.reload` re-executes `runner.py` into the same module namespace,
    which rebinds every class in it. This file imports `RunConflict` at the top,
    so after a reload that name pointed at a class the runner no longer raises -
    and every `except RunConflict` below this line silently stopped matching.
    """
    from app.server.runner import _max_gates

    monkeypatch.setenv("WORKFLOW_MAX_GATES", "42")

    assert _max_gates() == 42


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

    # Stages that are neither terminal nor a pause, and that *change* each
    # round - so the loop keeps going and genuinely exhausts its rounds. A graph
    # returning one unchanging stage is a different failure, caught sooner by
    # the idle check and tested separately below.
    class _EndlessGraph:
        def __init__(self):
            self.calls = 0

        def invoke(self, _input, config=None):
            self.calls += 1
            return {"stage": "product_manager" if self.calls % 2 else "tools_models"}

    await runner._handle_state(record, _EndlessGraph(), {"stage": "product_manager"}, {})

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

    try:
        await runner.resume_run("run-damaged")
    except RunConflict:
        pass
    else:
        pytest.fail("Expected RunConflict to be raised")

    assert runner.run_store.load("run-damaged").error.startswith("Interrupted:")


@pytest.mark.asyncio
async def test_an_ordinary_failed_run_still_resumes(runner, dispatched):
    record = _register(runner, run_id="run-ordinary")
    record.status = "failed"
    record.error = "OpenAIModelNotFoundError: the model was not found"
    runner.run_store.save(record)

    await runner.resume_run("run-ordinary")

    assert [c["run_id"] for c in dispatched] == ["run-ordinary"]


def test_no_single_stage_can_consume_the_whole_run():
    """One real unattended run spent all 1000 of its gates on one stage.

    They were all `awaiting_approval:product_manager`, all auto-approved, none
    making progress, because the only ceiling was the whole-run one.
    """
    from app.server.runner import MAX_GATES, MAX_GATES_PER_STAGE

    assert MAX_GATES_PER_STAGE < MAX_GATES / 3

    # And it must clear the work a real stage does. A specialist writing code,
    # running the suite and fixing what broke used 26 gates of genuine progress
    # and was killed by a ceiling of 25.
    assert MAX_GATES_PER_STAGE > 40, "a code-writing specialist needs room to iterate"


def test_a_stage_repeating_one_request_is_caught_long_before_the_ceiling():
    """Looping is detected by repetition, not by volume.

    The ceiling is a blunt backstop. What identifies a stuck agent is asking for
    the same write again and again, and that must fail fast - well before a
    busy-but-productive stage would trip anything.
    """
    from app.server.runner import MAX_GATES_PER_STAGE, MAX_IDENTICAL_GATES

    assert MAX_IDENTICAL_GATES < MAX_GATES_PER_STAGE / 10


def test_approval_signatures_distinguish_work_from_repetition():
    from app.server.runner import _approval_signature

    class _A:
        def __init__(self, path, notes):
            self.artifact_path, self.notes = path, notes

    first = _approval_signature(_A("docs/spec.md", "# Spec"))
    again = _approval_signature(_A("docs/spec.md", "# Spec"))
    other = _approval_signature(_A("docs/plan.md", "# Spec"))
    edited = _approval_signature(_A("docs/spec.md", "# Spec, revised"))

    assert first == again
    assert first != other
    assert first != edited
    assert _approval_signature(None) == ("", "")


def test_the_per_stage_ceiling_is_configurable(monkeypatch):
    from app.server.runner import _max_gates_per_stage

    monkeypatch.setenv("WORKFLOW_MAX_GATES_PER_STAGE", "7")

    assert _max_gates_per_stage() == 7


def test_a_malformed_per_stage_ceiling_falls_back(monkeypatch):
    from app.server.runner import _max_gates_per_stage

    monkeypatch.setenv("WORKFLOW_MAX_GATES_PER_STAGE", "lots")
    fallback = _max_gates_per_stage()

    monkeypatch.delenv("WORKFLOW_MAX_GATES_PER_STAGE")
    assert fallback == _max_gates_per_stage()


# ---------------------------------------------------------------------------
# What a failed run tells the person who has to fix it
# ---------------------------------------------------------------------------


def test_a_backend_with_no_model_loaded_is_explained_not_dumped() -> None:
    """The reader needs the instruction, not the provider's nested JSON.

    Observed live: a run stopped mid-stage because LM Studio had unloaded its
    model, and the dashboard showed
    `OpenAIInvalidRequestError: Error code: 400 - {'error': {'message': 'No
    model loaded. Call POST /inference/load first...'}}`. Nothing was wrong with
    the run - both artifacts and the pending gate survived, and it continued
    once a model was loaded - but finding that out meant reading a dict.
    """
    from app.server.runner import _explain_failure

    class OpenAIInvalidRequestError(Exception):
        pass

    message = _explain_failure(
        OpenAIInvalidRequestError(
            "Error code: 400 - {'error': {'message': 'No model loaded. Call POST "
            "/inference/load first. Or enable Model auto-switch (Settings > API) "
            "to load a requested model automatically.', 'type': 'invalid_request_error'}}"
        )
    )

    assert message.startswith("The model server would not serve the model this run asked for")
    assert "resume" in message
    # The provider's own words are kept, after the instruction.
    assert "No model loaded" in message


def test_an_unreachable_backend_says_so() -> None:
    from app.server.runner import _explain_failure

    message = _explain_failure(ConnectionError("Connection refused by host"))
    assert "could not be reached" in message


def test_an_unrecognised_failure_is_shown_verbatim() -> None:
    """A failure we cannot name must not be paraphrased into a guess."""
    from app.server.runner import _explain_failure

    message = _explain_failure(ValueError("structured response was empty"))
    assert message == "ValueError: structured response was empty"


def test_the_error_stays_short_enough_to_render() -> None:
    from app.server.runner import RUN_ERROR_MAX_CHARS, _explain_failure

    noisy = _explain_failure(RuntimeError("no model loaded. " + "x" * 5_000))
    plain = _explain_failure(RuntimeError("y" * 5_000))
    assert len(noisy) <= RUN_ERROR_MAX_CHARS
    assert len(plain) <= RUN_ERROR_MAX_CHARS
    # The instruction is what survives the cap, not the noise.
    assert noisy.startswith("The model server would not serve the model this run asked for")


def test_a_task_time_limit_says_the_run_was_still_working() -> None:
    """`SoftTimeLimitExceeded: SoftTimeLimitExceeded()` tells the reader nothing.

    Observed on one run: 54.3 minutes of healthy progress, from
    stack_selector through two architecture-review rounds to technical_lead,
    ended by a 3300-second ceiling. Nothing was wrong with the run and nothing
    was lost - but the message named a Celery class, not a clock, so the obvious
    reading was that the workflow had broken.
    """
    from app.server.runner import _explain_failure

    class SoftTimeLimitExceeded(Exception):
        pass

    message = _explain_failure(SoftTimeLimitExceeded())

    assert "task time limit" in message
    assert "still making progress" in message
    assert "CELERY_TASK_SOFT_TIME_LIMIT" in message


def test_the_task_time_limit_is_sized_for_a_whole_run() -> None:
    """A dispatch runs every stage of an unattended run, not one model call."""
    import os

    from app.server.tasks import celery_app

    soft = celery_app.conf.task_soft_time_limit
    hard = celery_app.conf.task_time_limit
    assert soft >= 6 * 3600, "a full local-model run does not fit in an hour"
    assert hard > soft, "the hard limit must leave room for the soft one to fire first"
    assert os.environ.get("CELERY_TASK_SOFT_TIME_LIMIT") is None or soft > 0


def test_a_loaded_but_different_model_is_explained_too() -> None:
    """The server may hold a model and still refuse the one that was asked for.

    Observed on one run: settings named `unsloth/Qwen3.8-27B-GGUF` while
    the server had `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` loaded with
    'Switch model by request' off. Saying "no model loaded" would have sent the
    reader looking for a problem that was not there.
    """
    from app.server.runner import _explain_failure

    class OpenAIModelNotFoundError(Exception):
        pass

    message = _explain_failure(
        OpenAIModelNotFoundError(
            "Error code: 404 - {'error': {'message': \"The model "
            "'unsloth/Qwen3.8-27B-GGUF' is downloaded but not loaded, and 'Switch "
            "model by request' is off, so this server can only serve the loaded model.\"}}"
        )
    )

    assert "would not serve the model this run asked for" in message
    assert "already" in message and "loaded" in message


# ---------------------------------------------------------------------------
# Re-running a command is not a loop
#
# `MAX_IDENTICAL_GATES` catches an agent that re-requests an identical *write*:
# nothing changed between attempts, and `write_approved_artifact` says so by
# reporting `unchanged`. Applying the same rule to a command inverts it.
#
# On one run `specialist_backend_1` ran `npm test`, read `app.js`, ran it
# again, read four more files, ran it again - real diagnosis between every run,
# with the tests passing - and was stopped after five as "asking to write the
# same thing 5 times in a row". It had written nothing at all.
# ---------------------------------------------------------------------------


def _approval(kind: str, path: str = "", notes: str = ""):
    from types import SimpleNamespace

    return SimpleNamespace(action_kind=kind, artifact_path=path, notes=notes)


def test_an_identical_write_still_counts_as_a_loop() -> None:
    from app.server.runner import _repeat_is_a_loop

    assert _repeat_is_a_loop(_approval("write", "docs/spec.md", "Write docs/spec.md: ..."))


def test_an_identical_command_is_not_a_loop() -> None:
    from app.server.runner import _repeat_is_a_loop

    assert not _repeat_is_a_loop(_approval("command", "", "Run npm test"))


def test_an_approval_of_unknown_kind_is_treated_as_a_write() -> None:
    """Old checkpoints carry no kind; the stricter reading is the safe default."""
    from app.server.runner import _repeat_is_a_loop

    assert _repeat_is_a_loop(_approval("unknown"))
    assert _repeat_is_a_loop(None)


def test_the_approval_records_what_the_pause_would_do() -> None:
    from types import SimpleNamespace

    from app.agents.approval import extract_pending_approval

    def paused(args):
        return {"__interrupt__": [SimpleNamespace(id="i1", value={"action_requests": [{"args": args}]})]}

    write = extract_pending_approval(
        paused({"relative_path": "docs/a.md", "content": "x"}), "/w",
        requested_by="s", stage="s",
    )
    command = extract_pending_approval(
        paused({"command": ["npm", "test"], "category": "test"}), "/w",
        requested_by="s", stage="s",
    )

    assert write.action_kind == "write"
    assert command.action_kind == "command"


def test_a_loop_is_answered_before_the_run_is_ended() -> None:
    """Ending the run was the harshest available response, and the only one.

    One run's `specialist_backend_8` wrote `docs/blocker.md` five times - a
    perfectly reasonable document, from a model that had correctly worked out it
    was blocked and had no other move - and that killed a run which had already
    completed a full sprint, a test round, a security review and a milestone
    review. A gate is a decision point, and a decision has two answers.
    """
    from app.server.runner import MAX_IDENTICAL_GATES, MAX_LOOPS_ANSWERED_BY_DENIAL

    assert MAX_LOOPS_ANSWERED_BY_DENIAL >= 1
    # And the run still ends if denial does not stop it, so a loop cannot spin
    # forever: each answered loop costs MAX_IDENTICAL_GATES + 1 gates.
    assert MAX_LOOPS_ANSWERED_BY_DENIAL * (MAX_IDENTICAL_GATES + 1) < 40


def test_the_denial_tells_the_agent_what_to_do_instead() -> None:
    from app.agents.approval import reject_write_decision

    decision = reject_write_decision("Denied. Return your structured response now.")

    assert decision["type"] == "reject"
    assert "structured response" in decision["message"]


def test_what_was_asked_for_prefers_the_half_that_says_something() -> None:
    from app.server.runner import _what_was_asked_for

    assert _what_was_asked_for(("docs/blocker.md", "Write docs/...")) == "docs/blocker.md"
    assert _what_was_asked_for(("<unknown path>", "Run npm test")) == "Run npm test"
    assert _what_was_asked_for(("", "")) == "an artifact write"


def test_a_repeated_command_reports_the_command_not_an_unknown_path() -> None:
    """`The repeated request was: <unknown path>` names nothing a reader can act on."""
    from app.server.runner import _approval_signature

    signature = _approval_signature(_approval("command", "<unknown path>", "Run npm test"))
    shown = signature[0] if signature[0] and "unknown" not in signature[0] else signature[1]

    assert shown == "Run npm test"


# ---------------------------------------------------------------------------
# A graph with nothing to resume must be caught, not spun on
#
# `graph.invoke(None, ...)` runs something only when the thread has a task
# pending. A checkpoint written with values but no scheduled node - which
# `update_state` produces unless told `as_node` - has none, so the runner's
# "re-invoke to make progress" fallback returns identical state forever.
#
# Bounded only by MAX_GATES, that spun 1000 times in five seconds on
# one run and reported "Stopped after 1000 automatic approvals" when not
# one approval had happened.
# ---------------------------------------------------------------------------


def test_the_idle_reinvoke_ceiling_is_small() -> None:
    """A graph with work to do makes progress on the first re-invoke."""
    from app.server.runner import MAX_GATES, MAX_IDLE_REINVOKES

    assert 1 <= MAX_IDLE_REINVOKES <= 5
    assert MAX_IDLE_REINVOKES < MAX_GATES / 100, (
        "the idle check must fire long before the gate ceiling, or the run still "
        "spins and still reports the wrong reason"
    )


@pytest.mark.asyncio
async def test_a_graph_with_nothing_to_resume_is_caught_quickly(runner, monkeypatch):
    """The spin, and the message that sent a reader looking for the wrong thing."""
    import app.server.runner as runner_module

    monkeypatch.setattr(runner_module, "MAX_GATES", 500)

    record = _register(runner, "run-stalled")
    record.auto_approve = True
    published = []
    closed = []

    async def _capture(run_id, event):
        published.append(event)

    async def _close(run_id):
        closed.append(run_id)

    monkeypatch.setattr(runner.event_bus, "publish", _capture)
    monkeypatch.setattr(runner.event_bus, "close", _close)

    class _NothingToResume:
        """`invoke(None)` on a thread with no pending task returns it unchanged."""

        def __init__(self):
            self.calls = 0

        def invoke(self, _input, config=None):
            self.calls += 1
            return {"stage": "milestone_review"}

    graph = _NothingToResume()
    await runner._handle_state(record, graph, {"stage": "milestone_review"}, {})

    assert record.status == "failed"
    assert "without running anything" in record.error
    assert "no pending work to resume" in record.error
    # Caught in a handful of rounds, not five hundred.
    assert graph.calls <= runner_module.MAX_IDLE_REINVOKES + 2, (
        f"spun {graph.calls} times before noticing"
    )
    assert "automatic approvals" not in record.error, "reported as the wrong failure"
    assert closed == ["run-stalled"], "the event stream was never closed"


def test_gate_exhaustion_reports_what_the_stage_kept_doing():
    """"Raise the ceiling" was the whole message, and it is often wrong advice.

    Measured on one run: `defect_fix_1_0` spent all 120 approvals running
    `node test.js` against a test whose assertion could not be satisfied - the
    defect was "test.js AC-BE-1 regex was too strict, expected literal
    'todo_tasks' but code uses a constant". A larger budget would have bought
    more non-convergence, not a fix.

    The repeat guard does not catch this by design: identical *commands* are
    the build-and-fix cycle working, and only identical *writes* count as a
    loop. So the ceiling is the right catch - it just has to say what it caught.
    """
    import inspect

    from app.server import runner

    source = " ".join(inspect.getsource(runner).split())

    assert "Its most repeated request was" in source
    assert "is not converging" in source
    assert "a larger budget only helps the first case" in source


def test_the_repeat_guard_still_distinguishes_writes_from_commands():
    """Re-running a command is diagnosis; re-writing a file is a loop."""
    from app.server.runner import _repeat_is_a_loop

    class _Approval:
        def __init__(self, kind):
            self.action_kind = kind

    assert _repeat_is_a_loop(_Approval("write"))
    assert not _repeat_is_a_loop(_Approval("command"))


async def test_a_run_keeps_the_delivery_mode_it_was_started_with(runner, dispatched, tmp_path, monkeypatch):
    """Chosen per run, not a setting beside the models: a later change of the
    deployment's default does not move a run already going."""
    from app import delivery
    from app.state import RepositoryContext

    monkeypatch.setenv("DELIVERY_MODE", "fast")
    _register(runner)
    repository = RepositoryContext(root_path=str(tmp_path), branch="main", commit="abc", status="clean")

    await runner.start_run("run-1", document=None, repository=repository, delivery_mode="thorough")

    record = runner.run_store.load("run-1")
    assert record.delivery_mode == "thorough"
    with delivery.for_the_run(record.delivery_mode):
        assert delivery.mode() == "thorough" and not delivery.fast()
    assert delivery.mode() == "fast", "outside the run, the deployment's default"


async def test_a_run_started_without_a_choice_takes_the_deployment_s(runner, dispatched, tmp_path, monkeypatch):
    from app.state import RepositoryContext

    monkeypatch.setenv("DELIVERY_MODE", "fast")
    _register(runner)
    repository = RepositoryContext(root_path=str(tmp_path), branch="main", commit="abc", status="clean")

    await runner.start_run("run-1", document=None, repository=repository)

    assert runner.run_store.load("run-1").delivery_mode == "fast"


async def test_a_run_started_without_the_frontier_model_keeps_every_stage_on_the_build_model(runner, dispatched, tmp_path, monkeypatch):
    """Owner, 2026-10-15: a choice on the run - unchecked, all the work happens on the local model."""
    from app.models.roles import build_judgement_model, on_the_build_model_only
    from app.state import RepositoryContext

    _register(runner)
    repository = RepositoryContext(root_path=str(tmp_path), branch="main", commit="abc", status="clean")

    await runner.start_run("run-1", document=None, repository=repository, use_frontier_model=False)

    record = runner.run_store.load("run-1")
    assert record.local_only is True
    local = object()
    frontier_settings = {
        "LLM_PROVIDER": "local", "OPENAI_MODEL": "local-y", "OPENAI_BASE_URL": "http://localhost:1/v1",
        "OPENAI_API_KEY": "k", "JUDGEMENT_MODEL": "frontier-x",
    }
    assert getattr(build_judgement_model(local, frontier_settings), "model_name", None) == "frontier-x"
    with on_the_build_model_only(record.local_only):
        assert build_judgement_model(local, frontier_settings) is local


async def test_a_run_started_without_saying_uses_the_frontier_model(runner, dispatched, tmp_path):
    from app.state import RepositoryContext

    _register(runner)
    repository = RepositoryContext(root_path=str(tmp_path), branch="main", commit="abc", status="clean")

    await runner.start_run("run-1", document=None, repository=repository)

    assert runner.run_store.load("run-1").local_only is False


def test_the_worker_works_a_run_on_the_models_it_was_started_with():
    from pathlib import Path

    source = Path("src/app/server/tasks.py").read_text()
    assert 'on_the_build_model_only(bool(getattr(record, "local_only", False)))' in source
    store = Path("src/app/server/run_store.py").read_text()
    assert "ADD COLUMN IF NOT EXISTS local_only" in store and store.count("delivery_mode, local_only, approval_timeout_minutes FROM runs") == 3
