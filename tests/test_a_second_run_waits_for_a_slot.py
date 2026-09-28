"""Runs are bounded at dispatch, so two do not contend for one model server.

Item 6 of `docs/harness-hardening-plan-part3.md`, and the gate on Part I's
item 2. Nothing bounded this: `_dispatch` handed every run to Celery, which
accepted the message and held it, so a second run looked started and was in
fact competing.

Observed on 2026-09-20: orphan recovery resumed one run at the moment another
run was started, and both executed against a model server that answers one
request at a time. Throughput halved and the 524 rate rose.

Part I's item 2 derives a request timeout from a measured generation rate. A
probe run on a contended server measures a rate the run will not see, so that
item cannot land until this one has.
"""

from __future__ import annotations

import pytest

from app.server.runner import RunConflict, RunQueueFull, _max_concurrent_runs


class TestTheSetting:
    def test_it_is_off_by_default(self, monkeypatch):
        monkeypatch.delenv("MAX_CONCURRENT_RUNS", raising=False)
        assert _max_concurrent_runs() == 0

    def test_blank_is_off(self, monkeypatch):
        monkeypatch.setenv("MAX_CONCURRENT_RUNS", "   ")
        assert _max_concurrent_runs() == 0

    def test_a_number_is_read(self, monkeypatch):
        monkeypatch.setenv("MAX_CONCURRENT_RUNS", "2")
        assert _max_concurrent_runs() == 2

    def test_nonsense_is_ignored_rather_than_fatal(self, monkeypatch):
        """A malformed limit must not be the reason no run can start."""
        monkeypatch.setenv("MAX_CONCURRENT_RUNS", "two")
        assert _max_concurrent_runs() == 0

    def test_it_is_read_on_every_call_not_captured_at_import(self, monkeypatch):
        """Raising it is the answer to a full queue; that must not need a restart."""
        monkeypatch.setenv("MAX_CONCURRENT_RUNS", "1")
        assert _max_concurrent_runs() == 1
        monkeypatch.setenv("MAX_CONCURRENT_RUNS", "4")
        assert _max_concurrent_runs() == 4


class _Store:
    def __init__(self, in_flight):
        self._in_flight = in_flight
        self.task_ids = []

    def count_in_flight(self):
        if isinstance(self._in_flight, Exception):
            raise self._in_flight
        return self._in_flight

    def set_task_id(self, run_id, task_id):
        self.task_ids.append((run_id, task_id))


class _Runner:
    """Just the dispatch seam, with its real implementation."""

    from app.server.runner import WorkflowRunner

    _dispatch = WorkflowRunner._dispatch

    def __init__(self, store):
        self.run_store = store


@pytest.fixture
def dispatched(monkeypatch):
    sent = []

    class _Result:
        id = "task-1"

    class _Task:
        @staticmethod
        def delay(**kwargs):
            sent.append(kwargs)
            return _Result()

    import app.server.tasks as tasks

    monkeypatch.setattr(tasks, "execute_workflow_run", _Task)
    return sent


def test_a_run_dispatches_when_a_slot_is_free(monkeypatch, dispatched):
    monkeypatch.setenv("MAX_CONCURRENT_RUNS", "2")
    runner = _Runner(_Store(in_flight=1))

    runner._dispatch("run-a", resume=False, decision_payload=None)

    assert len(dispatched) == 1


def test_a_run_is_refused_when_every_slot_is_taken(monkeypatch, dispatched):
    monkeypatch.setenv("MAX_CONCURRENT_RUNS", "2")
    runner = _Runner(_Store(in_flight=2))

    with pytest.raises(RunQueueFull) as raised:
        runner._dispatch("run-b", resume=False, decision_payload=None)

    assert dispatched == [], "the message must not reach Celery"
    # The message has to say what to do about it.
    assert "2 of 2 run slots" in str(raised.value)
    assert "MAX_CONCURRENT_RUNS" in str(raised.value)


def test_the_refusal_is_a_conflict_so_existing_handlers_still_answer_409():
    assert issubclass(RunQueueFull, RunConflict)


def test_no_limit_means_no_check(monkeypatch, dispatched):
    monkeypatch.delenv("MAX_CONCURRENT_RUNS", raising=False)
    store = _Store(in_flight=99)
    runner = _Runner(store)

    runner._dispatch("run-c", resume=False, decision_payload=None)

    assert len(dispatched) == 1


def test_a_store_that_cannot_count_still_dispatches(monkeypatch, dispatched):
    """A limit must never be the reason a run cannot start."""
    monkeypatch.setenv("MAX_CONCURRENT_RUNS", "1")
    runner = _Runner(_Store(in_flight=RuntimeError("database is away")))

    runner._dispatch("run-d", resume=False, decision_payload=None)

    assert len(dispatched) == 1


def test_only_running_occupies_a_slot():
    """A paused run has released its worker and is waiting on a human."""
    from app.server.run_store import _COUNT_IN_FLIGHT_SQL

    assert "status = 'running'" in _COUNT_IN_FLIGHT_SQL


def test_readiness_reports_the_count():
    import inspect

    from app.server import api

    source = inspect.getsource(api)
    assert '"in_flight"' in source
    # Reported, never judged: a full pool is a healthy pool doing its job.
    assert 'k not in ("status", "runs")' in source
