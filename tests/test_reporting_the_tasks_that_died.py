"""A failure written to a queue nobody reads was not reported to anybody.

`tasks.handle_task_failure` has written every permanently failed Celery task to
the Redis list `celery_dlq` since it was added, and trimmed it to 1,000 entries
so it cannot fill Redis. Two writes, and no reader anywhere in the product: no
endpoint, no command, no log line. A worker crash was recorded and then not told
to anybody.

Nine entries were sitting in it when this was written, going back thirteen days,
and every one is something an operator would have wanted the same day:

    x2  'WorkflowRunner' object has no attribute '_run_loop'
    x2  unexpected character after line continuation character (sandbox.py, line 384)
    x2  Worker exited prematurely: signal 9 (SIGKILL) Job: 0.
    x1  SoftTimeLimitExceeded()
    x1  connection already closed
    x1  -241

The two `SyntaxError`s name this harness's own module, so two runs died because
`sandbox.py` was briefly unparseable, and the only record of it was in a list
with no reader.

Reports by default and changes nothing, like `workspaces`, `checkpoints` and
`recover-orphans`. `--clear` is how a report stops repeating what has been dealt
with, and it is the operator's decision, not this command's.
"""

from __future__ import annotations

import json

import pytest

from app.server.manage import DEAD_LETTER_KEY, MAX_FAILURES_LISTED, failed_tasks


class FakeRedis:
    """Enough of the client for a list, plus a record of what was asked."""

    def __init__(self, entries: list[str] | None = None, *, fail: bool = False):
        self.entries = list(entries or [])
        self.fail = fail
        self.deleted: list[str] = []

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        if self.fail:
            raise RuntimeError("Connection refused")
        assert key == DEAD_LETTER_KEY
        return self.entries if end == -1 else self.entries[start : end + 1]

    def delete(self, key: str) -> int:
        self.deleted.append(key)
        self.entries = []
        return 1


def _entry(exception: str, run_id: str = "run-abc12345", when: str = "2026-09-18T07:31:00+00:00",
           resume: bool = False) -> str:
    return json.dumps({
        "task_id": "t-1",
        "task_name": "execute_workflow_run",
        "exception": exception,
        "kwargs": {"run_id": run_id, "resume": resume, "decision_payload": None},
        "failed_at": when,
    })


@pytest.fixture
def a_queue(monkeypatch):
    def _install(entries=None, *, fail=False):
        client = FakeRedis(entries, fail=fail)
        monkeypatch.setattr(
            "app.server.redis_client.get_redis_client", lambda: client
        )
        return client

    return _install


class TestReportingWhatIsThere:
    def test_the_nine_that_were_waiting(self, a_queue, capsys):
        a_queue([
            _entry("connection already closed", "run-a0000004", resume=True),
            _entry("-241", "run-a000000e"),
            _entry("'WorkflowRunner' object has no attribute '_run_loop'", "run-a000000d"),
            _entry("'WorkflowRunner' object has no attribute '_run_loop'", "run-a000000a"),
            _entry("unexpected character after line continuation character", "run-a0000007"),
            _entry("unexpected character after line continuation character", "run-a0000001"),
            _entry("Worker exited prematurely: signal 9 (SIGKILL) Job: 0.", "run-a000000c"),
            _entry("Worker exited prematurely: signal 9 (SIGKILL) Job: 0.", "run-a000000c"),
            _entry("SoftTimeLimitExceeded()", "run-a0000002", resume=True),
        ])

        assert failed_tasks() == 0
        printed = capsys.readouterr().out

        assert "9 permanently failed task(s)" in printed
        assert "x2" in printed, "the count is what says one-off or pattern"
        assert "run-a000000c" in printed

    def test_an_empty_queue_says_so(self, a_queue, capsys):
        a_queue([])

        assert failed_tasks() == 0
        assert "No permanently failed tasks recorded." in capsys.readouterr().out

    def test_the_run_is_named_so_a_failure_can_be_investigated(self, a_queue, capsys):
        a_queue([_entry("boom", "run-deadbeef")])
        failed_tasks()

        assert "run-deadbeef" in capsys.readouterr().out

    def test_whether_it_was_a_resume_is_shown(self, a_queue, capsys):
        """A failure on resume and a failure on start are different faults."""
        a_queue([_entry("boom", "run-deadbeef", resume=True)])
        failed_tasks()

        assert "True" in capsys.readouterr().out

    def test_identical_exceptions_are_counted_together(self, a_queue, capsys):
        a_queue([_entry("the same thing") for _ in range(4)])
        failed_tasks()

        assert "x4" in capsys.readouterr().out


class TestNotDrowningTheReader:
    def test_the_list_is_capped_and_says_how_many_are_left(self, a_queue, capsys):
        a_queue([_entry(f"failure {index}") for index in range(MAX_FAILURES_LISTED + 7)])

        failed_tasks()
        printed = capsys.readouterr().out

        assert "and 7 more" in printed
        assert "--limit" in printed

    def test_the_limit_can_be_raised(self, a_queue, capsys):
        a_queue([_entry(f"failure {index}") for index in range(30)])

        failed_tasks(limit=30)

        assert "more; pass --limit" not in capsys.readouterr().out

    def test_the_grouping_is_never_truncated(self, a_queue, capsys):
        """The counts are the summary, so they are always complete."""
        a_queue(
            [_entry("common") for _ in range(MAX_FAILURES_LISTED + 5)]
            + [_entry("rare once")]
        )

        failed_tasks()

        assert "rare once" in capsys.readouterr().out


class TestChangingNothingUnlessAsked:
    def test_reporting_leaves_the_queue_alone(self, a_queue, capsys):
        client = a_queue([_entry("boom")])

        failed_tasks()

        assert client.deleted == []
        assert "Nothing was changed" in capsys.readouterr().out

    def test_clear_empties_it(self, a_queue, capsys):
        client = a_queue([_entry("boom"), _entry("boom")])

        assert failed_tasks(clear=True) == 0

        assert client.deleted == [DEAD_LETTER_KEY]
        assert "Cleared 2" in capsys.readouterr().out


class TestSurvivingBadInput:
    def test_an_unreachable_redis_is_reported_not_raised(self, a_queue, capsys):
        """A diagnostic command that crashes is one more thing to diagnose."""
        a_queue(fail=True)

        assert failed_tasks() == 1
        assert "Could not read the dead-letter list" in capsys.readouterr().out

    def test_an_entry_that_is_not_json_is_counted_not_dropped_silently(
        self, a_queue, capsys
    ):
        a_queue(["{not json at all", _entry("boom")])

        assert failed_tasks() == 0
        printed = capsys.readouterr().out

        assert "could not be parsed" in printed
        assert "boom" in printed

    def test_bytes_from_redis_are_decoded(self, a_queue, capsys):
        """`decode_responses` is not guaranteed by every client configuration."""
        a_queue([_entry("boom").encode("utf-8")])

        failed_tasks()

        assert "boom" in capsys.readouterr().out

    def test_an_entry_with_no_kwargs_still_prints(self, a_queue, capsys):
        a_queue([json.dumps({"exception": "boom", "failed_at": "2026-09-18T07:31:00"})])

        assert failed_tasks() == 0
        assert "boom" in capsys.readouterr().out

    def test_an_entry_with_no_exception_is_still_a_failure(self, a_queue, capsys):
        a_queue([json.dumps({"kwargs": {"run_id": "run-1"}, "failed_at": "2026-09-18"})])

        failed_tasks()

        assert "no exception recorded" in capsys.readouterr().out


class TestItIsReachableFromTheCommandLine:
    def test_the_subcommand_is_registered(self, a_queue, monkeypatch, capsys):
        """A command the parser does not know is a function nobody can call."""
        from app.server import manage

        a_queue([_entry("boom")])
        monkeypatch.setattr(manage, "init_db_pool", lambda: None)

        assert manage.main(["failed-tasks"]) == 0
        assert "boom" in capsys.readouterr().out

    def test_clear_is_wired_through(self, a_queue, monkeypatch, capsys):
        from app.server import manage

        client = a_queue([_entry("boom")])
        monkeypatch.setattr(manage, "init_db_pool", lambda: None)

        manage.main(["failed-tasks", "--clear"])

        assert client.deleted == [DEAD_LETTER_KEY]

    def test_the_key_matches_the_one_the_writer_uses(self):
        """Two constants for one list is how a reader stops finding the writes."""
        import inspect

        from app.server import tasks

        assert DEAD_LETTER_KEY in inspect.getsource(tasks.handle_task_failure)
