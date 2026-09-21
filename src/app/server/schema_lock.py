"""One advisory lock, taken before any `CREATE TABLE IF NOT EXISTS`.

`IF NOT EXISTS` is not the protection it reads as. In PostgreSQL it is not
atomic against a concurrent session: two sessions both check for the table, both
find it absent, and both proceed to create it. The loser fails on
`pg_type_typname_nsp_index` - the unique index over the rowtype PostgreSQL
creates alongside every table - with `duplicate key value violates unique
constraint`, which names an internal index and does not mention the table the
caller was creating.

This system arranges for that collision in three separate places:

- `auth.init_db` runs in every gunicorn worker's lifespan, and `WEB_CONCURRENCY`
  defaults to 4, so four sessions create the schema simultaneously on first boot.
- `run_store.RunStore._ensure_schema` runs when a store is constructed, in both
  the API and the worker.
- `runtime_settings` creates its two tables lazily on six different read and
  write paths, so two concurrent *requests* can race - not just two processes at
  startup.

Measured on 2026-09-21 against a fresh `devflow_pgdata` volume: three of four
`app` workers failed to boot on two of three cold starts, and gunicorn halted
with `HaltServer 'Worker failed to boot.' 3`.

What kept it invisible is that it heals. Docker restarts the container, the
winner's schema is committed, every `IF NOT EXISTS` is now satisfied, and the
second boot works - so the symptom is a service that took two goes to start,
which reads as a slow database rather than a failure. It fires only against an
empty database, so the only people who meet it are the ones setting the project
up for the first time, who have the least context for diagnosing it.

The lock is transaction-scoped deliberately. `pg_advisory_lock` is held until it
is explicitly released or the session ends, so a process that dies mid-migration
leaves every other process blocked on a lock nothing will release.
`pg_advisory_xact_lock` is released when the transaction commits *or* rolls
back, including on the raise, so the failure mode is one worker erroring rather
than all of them hanging.
"""

from __future__ import annotations

SCHEMA_INIT_LOCK_KEY = 8_014_651_003_271_004_001
"""Advisory-lock key serialising schema creation across processes.

An arbitrary constant. It only has to be stable across releases and distinct
from any other advisory lock in this database; nothing reads it as a number.
One key covers all three schemas rather than one key each, because the cost of
over-serialising is that a second process waits a few milliseconds at startup,
and the cost of getting per-key allocation wrong is this bug again.
"""


def lock_schema(cursor) -> None:
    """Block until this transaction may create schema objects.

    Call before the first `CREATE`, on the same transaction that does the
    creating: the lock lifetime is the transaction's, so taking it on a
    different connection protects nothing.

    Callers that reach a database which does not implement advisory locks - the
    SQLite checkpointer path - should not call this at all rather than expect it
    to degrade; it is PostgreSQL-specific by construction.
    """
    cursor.execute("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_INIT_LOCK_KEY,))


def ensure_table(cursor, table: str, create_sql: str) -> None:
    """Create `table` if it is missing, without serialising the common case.

    `lock_schema` is the right tool for a migration that runs once at startup.
    It is the wrong tool for `runtime_settings`, which issues its
    `CREATE TABLE IF NOT EXISTS` on six *request* paths: taking a global
    advisory lock on every settings read would make concurrent reads queue
    behind each other for a table that has existed since the first boot.

    Measured while building this: with the lock taken unconditionally, 24
    concurrent readers exhausted the 20-connection pool, because each one sat on
    a pooled connection while waiting its turn. `PoolError: connection pool
    exhausted` on a read-only path is a worse bug than the one being fixed.

    So: check first, and only pay for the lock when there is something to do.
    The check is `to_regclass`, a catalogue lookup with no lock of its own. The
    re-check after acquiring is what makes it correct rather than merely fast -
    between the first check and the lock, another session may have created the
    table and committed, and creating it twice is the original bug.
    """
    cursor.execute("SELECT to_regclass(%s)", (table,))
    row = cursor.fetchone()
    if row and row[0] is not None:
        return

    lock_schema(cursor)
    # Re-check under the lock: the winner may have finished while we queued.
    cursor.execute("SELECT to_regclass(%s)", (table,))
    row = cursor.fetchone()
    if row and row[0] is not None:
        return
    cursor.execute(create_sql)


__all__ = ["SCHEMA_INIT_LOCK_KEY", "ensure_table", "lock_schema"]
