"""A long run stops at a stage boundary before its task's limit and is resumed in a new task, within a budget.

Measured: two healthy runs were killed by the twelve-hour task limit mid-stage, recorded cancelled and then failed,
and nothing resumed them; one was in sprint 2 of 3 and still making progress.
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest import mock


def _tasks():
    from app.server import tasks

    return tasks


class _Redis:
    def __init__(self, start=0):
        self.n = start

    def incr(self, key):
        self.n += 1
        return self.n

    def expire(self, key, seconds):
        return True


def _runner(status):
    async def resume_run(run_id):
        runner.resumed.append(run_id)

    runner = SimpleNamespace(resumed=[], run_store=SimpleNamespace(load=lambda run_id: SimpleNamespace(status=status)),
                             resume_run=resume_run)
    return runner


def test_a_run_paused_at_its_segment_s_limit_is_resumed_until_its_budget_is_spent():
    tasks = _tasks()
    runner = _runner("paused")
    assert tasks.carry_to_a_new_segment(runner, "run-x", client=_Redis(0)) is True
    assert runner.resumed == ["run-x"]
    spent = _runner("paused")
    assert tasks.carry_to_a_new_segment(spent, "run-x", client=_Redis(tasks.MOST_SEGMENTS)) is False
    assert spent.resumed == []


def test_a_run_that_did_not_stop_is_not_resumed_again():
    tasks = _tasks()
    for status in ("running", "completed", "failed"):
        runner = _runner(status)
        assert tasks.carry_to_a_new_segment(runner, "run-x", client=_Redis()) is False
        assert runner.resumed == []


def test_the_clock_asks_for_a_stop_at_a_boundary_before_the_task_s_limit():
    tasks = _tasks()
    asked = []
    store = SimpleNamespace(request_pause=lambda run_id, at: asked.append(run_id) or True)
    with tasks._SegmentClock(SimpleNamespace(run_store=store), "run-x", 0.05) as clock:
        time.sleep(0.3)
    assert asked == ["run-x"] and clock.rang
    assert tasks.SEGMENT_PAUSE_AT_SECONDS < tasks.celery_app.conf.task_soft_time_limit
    with tasks._SegmentClock(SimpleNamespace(run_store=store), "run-y", 30) as quiet:
        pass
    assert not quiet.rang and asked == ["run-x"]
