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


class _Database:
    """The one connection the checkpointer is lent, recording what reaches PostgreSQL in order."""

    def __init__(self, setup_raises: bool = False) -> None:
        self.said: list[str] = []
        self.setup_raises = setup_raises

    def connection(self):
        from contextlib import contextmanager

        database = self

        class _Connection:
            def cursor(self):
                return _Said(database.said)

            @contextmanager
            def transaction(self):
                database.said.append("BEGIN")
                yield
                database.said.append("COMMIT")

        @contextmanager
        def lent():
            yield _Connection()

        return lent()

    def saver(self, pool, serde=None):
        database = self

        class _Saver:
            def setup(self):
                database.said.append("CREATE INDEX CONCURRENTLY")
                if database.setup_raises:
                    raise RuntimeError("the index build failed")

        return _Saver()


class _Said(_Cursor):
    def __init__(self, said: list[str]) -> None:
        super().__init__()
        self.said = said

    def execute(self, sql: str, args: tuple = ()) -> None:
        self.said.append(sql.split("(")[0].strip())


def _the_checkpointer_on(monkeypatch, database: _Database):
    from types import SimpleNamespace

    from app.graph import checkpointing

    monkeypatch.setattr(checkpointing, "load_settings", lambda: SimpleNamespace(checkpointer_type="postgres"))
    monkeypatch.setattr(checkpointing, "get_connection_pool", lambda: database)
    monkeypatch.setattr(checkpointing, "PostgresSaver", database.saver)
    return checkpointing.build_checkpointer()


def test_the_checkpointer_does_not_hold_a_transaction_across_setup(monkeypatch):
    """The regression: a transaction-scoped lock held across `setup()`, whose
    `CREATE INDEX CONCURRENTLY` waits for every open transaction to end."""
    database = _Database()

    _the_checkpointer_on(monkeypatch, database)

    assert database.said == ["SELECT pg_advisory_lock", "CREATE INDEX CONCURRENTLY", "SELECT pg_advisory_unlock"]


def test_the_lock_is_always_released(monkeypatch):
    """A session lock is not released for you when the transaction ends."""
    database = _Database(setup_raises=True)

    with pytest.raises(RuntimeError):
        _the_checkpointer_on(monkeypatch, database)

    assert database.said[-1] == "SELECT pg_advisory_unlock"
