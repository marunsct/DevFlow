"""A worker that answers one of the sweep's questions and not another has not said its task is gone (LR.1).

Measured: under a load spike the recurring orphan sweep's question about active tasks timed out while its question
about reserved tasks was answered (empty). The sweep took that for "a worker answered and runs nothing", marked a run
whose task was still running as abandoned and resumed it, and two tasks wrote the one run at once; the second also
held the worker's last slot, so a newly started run waited with no stage for twelve minutes.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.server import manage


def _inspector(active, reserved, scheduled):
    return SimpleNamespace(active=lambda: active, reserved=lambda: reserved, scheduled=lambda: scheduled)


def _asking(monkeypatch, inspector):
    from app.server import tasks

    monkeypatch.setattr(tasks.celery_app.control, "inspect", lambda timeout=5: inspector)


def test_an_active_list_that_never_came_is_cannot_tell(monkeypatch):
    _asking(monkeypatch, _inspector(None, {"worker@a": []}, {"worker@a": []}))
    assert manage._live_task_ids() is None


def test_a_worker_missing_from_one_answer_is_cannot_tell(monkeypatch):
    _asking(monkeypatch, _inspector({"worker@a": []}, {"worker@a": [], "worker@b": []}, {"worker@a": [], "worker@b": []}))
    assert manage._live_task_ids() is None


def test_every_answer_from_every_worker_is_the_live_set(monkeypatch):
    _asking(monkeypatch, _inspector({"worker@a": [{"id": "t1"}]}, {"worker@a": [{"id": "t2"}]},
                                    {"worker@a": [{"request": {"id": "t3"}}]}))
    assert manage._live_task_ids() == {"t1", "t2", "t3"}


def test_no_worker_at_all_is_cannot_tell(monkeypatch):
    _asking(monkeypatch, _inspector(None, None, None))
    assert manage._live_task_ids() is None
