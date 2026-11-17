"""Cancellation reaches the graph between supersteps, not only between invokes.

Item 7 of Part III of the hardening plan (`docs/improvement-plan.md §E1`). `cancel_run` does two things
- sets `cancel_requested`, and revokes the Celery task with SIGTERM - and the
flag was read only between graph *invokes*. Within one invoke the graph runs
every stage it can reach, so a cancellation arriving at the start of a
specialist was not seen until that specialist finished. The SIGTERM that would
have stopped it sooner kills the turn wherever it is, and the run then resumes
from the last checkpoint, which for a specialist stage can be a whole stage of
work back.

Checked at a stage boundary, where the graph has just checkpointed and nothing
is in flight, so stopping costs nothing that was not already saved.
"""

from __future__ import annotations

import pytest

from app.graph import workflow
from app.graph.workflow import RunCancelled, _stop_if_cancelled


@pytest.fixture(autouse=True)
def forget_cancellations():
    workflow._CANCELLED_RUNS.clear()
    yield
    workflow._CANCELLED_RUNS.clear()


class _Store:
    def __init__(self, requested, on_call=None):
        self.requested = requested
        self.calls = 0
        self._on_call = on_call

    def is_cancel_requested(self, run_id):
        self.calls += 1
        if self._on_call:
            self._on_call()
        return self.requested


@pytest.fixture
def store(monkeypatch):
    holder = {}

    def _install(requested, on_call=None):
        s = _Store(requested, on_call)
        holder["store"] = s

        class _RunStore:
            @classmethod
            def shared(cls):
                return s

        import app.server.run_store as run_store

        monkeypatch.setattr(run_store, "RunStore", _RunStore)
        return s

    return _install


def test_a_cancelled_run_stops(store):
    store(requested=True)
    with pytest.raises(RunCancelled) as raised:
        _stop_if_cancelled("run-1")
    assert "run-1" in str(raised.value)


def test_a_live_run_continues(store):
    store(requested=False)
    _stop_if_cancelled("run-1")  # must not raise


def test_no_run_id_is_not_an_error(store):
    s = store(requested=True)
    _stop_if_cancelled(None)
    assert s.calls == 0, "nothing to ask about"


def test_a_database_that_cannot_answer_does_not_stop_a_healthy_run(store):
    """The coarser checks in the runner still hold; this is granularity."""
    def explode():
        raise RuntimeError("database is away")

    store(requested=False, on_call=explode)
    _stop_if_cancelled("run-1")  # must not raise


def test_a_cancellation_is_remembered_so_the_check_stays_cheap(store):
    s = store(requested=True)

    for _ in range(4):
        with pytest.raises(RunCancelled):
            _stop_if_cancelled("run-1")

    assert s.calls == 1, "a cancellation is never withdrawn; ask once"


def test_a_live_run_is_not_cached(store):
    """The negative must be re-read, or a cancellation would never be seen."""
    s = store(requested=False)

    _stop_if_cancelled("run-1")
    _stop_if_cancelled("run-1")

    assert s.calls == 2


class TestTheWiring:
    def test_a_stage_of_a_cancelled_run_makes_no_model_call(self, store, tmp_path):
        from types import SimpleNamespace

        store(requested=True)
        asked = []
        agent = SimpleNamespace(invoke=lambda request, config=None: asked.append(request),
                                get_state=lambda config: SimpleNamespace(values={}, next=()))

        with pytest.raises(RunCancelled):
            workflow._run_gated_agent(
                {"stage": "technical_lead", "repository": SimpleNamespace(root_path=str(tmp_path))},
                {"configurable": {"thread_id": "outer", workflow.APP_RUN_ID_KEY: "run-1"}},
                stage_name="technical_lead", agent=agent,
                initial_request={"messages": [{"role": "user", "content": "plan"}]},
                output_key="out", next_stage="next",
            )

        assert asked == []

    async def test_the_runner_treats_it_as_a_cancellation_not_a_failure(self, run_store, redis_container, monkeypatch):
        """A graph that stopped for a cancellation leaves the run cancelled, with no error recorded.

        It must be caught before the runner's generic handler, or it becomes a failed run with a traceback.
        """
        from app.server import runner as runner_module
        from app.server.events import EventBus
        from app.server.redis_client import reset_clients

        reset_clients()
        monkeypatch.setenv("CHECKPOINTER_TYPE", "memory")
        runner = runner_module.WorkflowRunner(EventBus(), run_store=run_store)
        record = runner.register_run(
            run_id="run-stopped", thread_id="thread-run-stopped", document_names=["brief.md"],
            document_paths=["/tmp/brief.md"], owner="alice", tenant_id="acme",
        )
        record.status = "running"
        run_store.save(record)

        def stopped(*args, **kwargs):
            raise RunCancelled("run-stopped")

        monkeypatch.setattr(runner_module, "build_workflow_graph", lambda **kwargs: object())
        monkeypatch.setattr(runner_module, "start_workflow", stopped)

        await runner._run_loop(record, document=None, repository=None)

        stored = run_store.load("run-stopped")
        assert stored.status == "cancelled"
        assert not stored.error
