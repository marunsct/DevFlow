"""What the graph checkpoints cost, and what it takes to reclaim any of them.

Nothing prunes these. There is no `DELETE FROM checkpoint...` anywhere in
`src/app` and no thread-deletion call, so every superstep of every run ever
executed is still on disk. Measured on the development deployment: 144 MB of
database for fourteen runs of a to-do list app, 136 MB of it checkpoints -
about 10 MB a run, spread across 522 threads.

Deleting them is not like deleting a workspace. A workspace is what a run
built; its checkpoints are how it got there, and they are the only thing that
lets an unfinished run resume. So a run that has not reached a terminal state
is never offered, however old it is.
"""

from __future__ import annotations

import types
from datetime import datetime, timedelta, timezone

import pytest

from app.server import manage


class _Cursor:
    def __init__(self, counts: dict[str, int], deleted: list[tuple[str, tuple]]):
        self._counts = counts
        self._deleted = deleted
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql: str, args: tuple = ()):  # noqa: ANN001
        if "pg_database_size" in sql:
            self._row = ("144 MB",)
        elif sql.startswith("SELECT count(*) FROM checkpoints"):
            self._row = (self._counts.get(args[0], 0),)
        elif sql.startswith("DELETE FROM"):
            self._deleted.append((sql.split()[2], args))
            self._row = None

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self, counts, deleted):
        self._counts = counts
        self._deleted = deleted
        self.commits = 0

    def cursor(self):
        return _Cursor(self._counts, self._deleted)

    def commit(self):
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _record(run_id: str, thread_id: str, status: str, age_days: float):
    return types.SimpleNamespace(
        run_id=run_id,
        thread_id=thread_id,
        status=status,
        created_at=datetime.now(timezone.utc) - timedelta(days=age_days),
    )


@pytest.fixture
def store(monkeypatch):
    records = [
        _record("run-aaaa", "thread-aaaa", "completed", 30),
        _record("run-bbbb", "thread-bbbb", "running", 30),
        _record("run-cccc", "thread-cccc", "completed", 0.5),
    ]
    counts = {"thread-aaaa": 400, "thread-bbbb": 120, "thread-cccc": 40}
    deleted: list[tuple[str, tuple]] = []
    connection = _Connection(counts, deleted)

    shared = types.SimpleNamespace(
        list_all=lambda **kw: records if kw.get("offset", 0) == 0 else [],
        get_connection=lambda: connection,
    )
    monkeypatch.setattr("app.server.run_store.RunStore.shared", staticmethod(lambda: shared))
    return types.SimpleNamespace(deleted=deleted, connection=connection)


def test_it_reports_every_run_with_its_checkpoint_count(store, capsys) -> None:
    manage.checkpoints()
    out = capsys.readouterr().out

    assert "400 checkpoints" in out
    assert "run-aaaa" in out
    assert "across 3 run(s)" in out
    assert "144 MB" in out


def test_nothing_is_offered_without_an_age(store, capsys) -> None:
    manage.checkpoints()

    assert "Would delete" not in capsys.readouterr().out
    assert store.deleted == []


def test_an_age_reports_what_could_go_and_removes_nothing(store, capsys) -> None:
    manage.checkpoints(older_than_days=7)
    out = capsys.readouterr().out

    assert "Would delete 400 checkpoints for run-aaaa" in out
    assert "Re-run with --delete" in out
    assert store.deleted == []


def test_it_says_what_deleting_them_costs(store, capsys) -> None:
    """A workspace is what a run built; these are how it got there."""
    manage.checkpoints(older_than_days=7)
    out = capsys.readouterr().out

    assert "no longer be resumed or replayed" in out
    assert "transcripts and the workspaces are not touched" in out


def test_an_unfinished_run_keeps_its_checkpoints(store, capsys) -> None:
    manage.checkpoints(older_than_days=7, delete=True)
    out = capsys.readouterr().out

    assert "Kept run-bbbb" in out
    assert "how it would resume" in out
    assert all("thread-bbbb" not in str(args) for _table, args in store.deleted)


def test_a_young_run_is_left_alone(store) -> None:
    manage.checkpoints(older_than_days=7, delete=True)

    assert all("thread-cccc" not in str(args) for _table, args in store.deleted)


def test_delete_clears_all_three_tables(store, capsys) -> None:
    manage.checkpoints(older_than_days=7, delete=True)

    assert [table for table, _ in store.deleted] == list(manage.CHECKPOINT_TABLES)
    assert "Reclaimed the graph state of 1 run(s)" in capsys.readouterr().out


def test_the_inner_threads_go_with_the_outer_one(store) -> None:
    """Every gated stage runs its agent under
    `f"{outer_thread_id}:{stage_name}:{uuid}"`, which is why one deployment
    has 522 threads for 14 runs. Deleting only the exact thread would leave
    almost all of a run's rows behind."""
    manage.checkpoints(older_than_days=7, delete=True)

    for _table, args in store.deleted:
        assert args == ("thread-aaaa", "thread-aaaa:%")


def test_the_delete_order_leaves_no_checkpoint_without_its_contents(store) -> None:
    """No foreign keys tie these together, so the order is chosen. Writes and
    blobs reference a checkpoint, so the checkpoint goes last."""
    assert manage.CHECKPOINT_TABLES[-1] == "checkpoints"


def test_the_cli_reaches_it(monkeypatch) -> None:
    seen: dict = {}
    monkeypatch.setattr(manage, "init_db_pool", lambda: None)
    monkeypatch.setattr(
        manage,
        "checkpoints",
        lambda older_than_days=None, delete=False: seen.update(
            older=older_than_days, delete=delete
        )
        or 0,
    )

    assert manage.main(["checkpoints", "--older-than-days", "30", "--delete"]) == 0
    assert seen == {"older": 30.0, "delete": True}


def test_the_cli_defaults_to_reporting(monkeypatch) -> None:
    seen: dict = {}
    monkeypatch.setattr(manage, "init_db_pool", lambda: None)
    monkeypatch.setattr(
        manage,
        "checkpoints",
        lambda older_than_days=None, delete=False: seen.update(
            older=older_than_days, delete=delete
        )
        or 0,
    )

    assert manage.main(["checkpoints"]) == 0
    assert seen == {"older": None, "delete": False}
