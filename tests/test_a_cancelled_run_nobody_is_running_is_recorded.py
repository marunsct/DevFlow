"""A cancelled run that only a resumed task ever sees again is recorded cancelled.

Measured on one run: the worker was killed mid-command and the run was
cancelled while nothing was executing it. The recovery sweep resumed it, the
resumed task found the cancel flag and returned - recording nothing. The row
read `running` with no task behind it, and stayed that way.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.server import tasks


class _Store:
    def __init__(self, status: str, cancel_requested: bool = True):
        self.record = SimpleNamespace(status=status, document_paths=[], pending_decision_payload=None)
        self.cancel_requested = cancel_requested
        self.moves: list[tuple] = []

    def load(self, run_id):
        return self.record

    def is_cancel_requested(self, run_id):
        return self.cancel_requested

    def compare_and_set_status(self, run_id, expected, new_status, *, updated_at, **_):
        self.moves.append((run_id, expected, new_status))
        self.record.status = new_status
        return True


def _run_task(monkeypatch, store) -> None:
    monkeypatch.setattr(tasks, "_get_runner", lambda: SimpleNamespace(run_store=store))
    tasks.execute_workflow_run.run("run-x", True)


def test_a_running_row_with_a_cancel_request_becomes_cancelled(monkeypatch) -> None:
    store = _Store("running")

    _run_task(monkeypatch, store)

    assert store.moves == [("run-x", "running", "cancelled")]
    assert store.record.status == "cancelled"


@pytest.mark.parametrize("status", ["cancelled", "failed", "completed"])
def test_a_run_that_already_ended_is_left_as_it_ended(monkeypatch, status) -> None:
    store = _Store(status)

    _run_task(monkeypatch, store)

    assert store.moves == []
    assert store.record.status == status


def test_a_store_that_cannot_record_it_does_not_run_the_graph(monkeypatch) -> None:
    store = _Store("running")

    def broken(*args, **kwargs):
        raise RuntimeError("database gone")

    store.compare_and_set_status = broken

    _run_task(monkeypatch, store)  # returns without raising and without executing
