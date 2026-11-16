"""A run's dispatch runs once, however often the broker delivers it.

Measured on one run: queued behind two long runs, its message sat reserved and unacknowledged; Redis handed it out
again every hour (the default visibility timeout), and when slots freed two copies ran the whole run at once in one
workspace, with seven more waiting.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock



def _tasks():
    # Imported inside each test, as the other tests of the task module do: importing it while the suite collects
    # fixes its broker address before the API tests' fixtures set theirs, and their dispatches then reach no broker.
    from app.server import tasks

    return tasks


class _Redis:
    def __init__(self):
        self.keys = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True


def test_a_second_delivery_of_one_dispatch_is_dropped_and_a_retry_is_not():
    tasks = _tasks()
    redis = _Redis()
    assert tasks.first_delivery("t1", 0, redis) is True
    assert tasks.first_delivery("t1", 0, redis) is False
    assert tasks.first_delivery("t1", 1, redis) is True
    assert tasks.first_delivery("t2", 0, redis) is True


def test_an_unreadable_marker_never_holds_a_run_back():
    tasks = _tasks()
    broken = SimpleNamespace(set=mock.Mock(side_effect=ConnectionError("down")))
    assert tasks.first_delivery("t1", 0, broken) is True
    assert tasks.first_delivery(None, 0, _Redis()) is True


def test_the_redelivery_wait_is_longer_than_a_task_may_run_and_one_message_is_reserved_at_a_time():
    tasks = _tasks()
    conf = tasks.celery_app.conf
    assert conf.broker_transport_options["visibility_timeout"] > conf.task_time_limit
    assert conf.worker_prefetch_multiplier == 1


def test_the_task_drops_a_redelivered_copy_before_it_touches_the_run():
    tasks = _tasks()
    with mock.patch.object(tasks, "first_delivery", return_value=False), \
            mock.patch.object(tasks, "_get_runner") as runner:
        tasks.execute_workflow_run.run("run-x")
    runner.assert_not_called()
