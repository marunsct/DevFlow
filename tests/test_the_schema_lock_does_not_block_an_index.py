"""The schema lock deadlocked against LangGraph's own index build.

`7653ad7` serialised schema creation behind `pg_advisory_xact_lock`, which is
right for `CREATE TABLE` and wrong for anything that runs
`CREATE INDEX CONCURRENTLY`.

That statement cannot run inside a transaction block, so PostgreSQL executes
it on another connection, and before it can finish it waits for every
transaction overlapping it to end. A caller holding a transaction-scoped
advisory lock is exactly such a transaction - and it is waiting for the index
build to return. Neither side moves.

`PostgresSaver.setup()` issues three of them. Observed on 2026-09-23, a suite
stopped for thirty minutes at `tests/test_api_contract.py`:

    pid 77 | idle in transaction | SELECT pg_advisory_xact_lock($1)
    pid 78 | active | Lock | virtualxid |
             CREATE INDEX CONCURRENTLY IF NOT EXISTS checkpoints_thread_id_idx

It fires only when the indexes do not exist - a fresh database always, an
established one never - which is why it read as an occasional slow start
rather than a deadlock. In isolation the same test file passes in six
seconds.

The fix is a session-scoped lock: held by the connection rather than by a
transaction, so two processes still take turns and nothing this holds blocks
an index build.
"""

from __future__ import annotations

import inspect

import pytest

from app.server import schema_lock


class _Cursor:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple]] = []

    def execute(self, sql: str, args: tuple = ()) -> None:
        self.statements.append((sql, args))


def test_the_session_lock_is_not_transaction_scoped():
    cursor = _Cursor()

    schema_lock.lock_schema_for_the_session(cursor)

    sql, args = cursor.statements[0]
    assert "pg_advisory_lock" in sql
    assert "xact" not in sql, "a transaction-scoped lock is what deadlocked"
    assert args == (schema_lock.SCHEMA_INIT_LOCK_KEY,)


def test_the_transaction_lock_still_exists_for_table_creation():
    """It is the right tool there and is not being removed."""
    cursor = _Cursor()

    schema_lock.lock_schema(cursor)

    assert "pg_advisory_xact_lock" in cursor.statements[0][0]


def test_both_forms_use_one_key():
    """Two keys would let a table creation and an index build run together."""
    held, session = _Cursor(), _Cursor()

    schema_lock.lock_schema(held)
    schema_lock.lock_schema_for_the_session(session)

    assert held.statements[0][1] == session.statements[0][1]


def test_the_session_lock_can_be_released():
    cursor = _Cursor()

    schema_lock.unlock_schema(cursor)

    assert "pg_advisory_unlock" in cursor.statements[0][0]


def test_the_checkpointer_does_not_hold_a_transaction_across_setup():
    """The regression itself, asserted against the source that caused it.

    A behavioural test would need two live connections racing on a fresh
    database, which is the thirty-minute hang this exists to prevent. The
    property that matters is structural and is checkable without one: the
    lock around `saver.setup()` must be the session-scoped form, and there
    must be no transaction opened around it.
    """
    from app.graph import checkpointing

    source = inspect.getsource(checkpointing)
    # The LAST one: the SQLite branch calls `setup()` too, and it needs no
    # lock at all because SQLite has no advisory locks and one process owns
    # the file. Matching the first occurrence tested the wrong branch.
    setup = source.rindex("saver.setup()")
    window = source[max(0, setup - 900):setup]

    assert "lock_schema_for_the_session" in window
    assert "guard.transaction()" not in window, (
        "a transaction open here cannot coexist with CREATE INDEX CONCURRENTLY"
    )


def test_the_lock_is_always_released():
    """A session lock is not released for you when the transaction ends."""
    from app.graph import checkpointing

    source = inspect.getsource(checkpointing)
    setup = source.rindex("saver.setup()")
    after = source[setup:setup + 400]

    assert "finally" in after
    assert "unlock_schema" in after


@pytest.mark.parametrize("name", ["lock_schema", "lock_schema_for_the_session",
                                  "unlock_schema", "ensure_table"])
def test_every_helper_is_exported(name: str):
    assert name in schema_lock.__all__
