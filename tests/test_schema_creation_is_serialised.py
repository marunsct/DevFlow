"""Concurrent schema creation does not collide.

`CREATE TABLE IF NOT EXISTS` reads as a safe idempotent statement and is not one
under concurrency: in PostgreSQL two sessions both find the table absent and
both create it, and the loser fails on `pg_type_typname_nsp_index` with
`duplicate key value violates unique constraint`.

Found on 2026-09-21 bringing the stack up on a new machine against an empty
`devflow_pgdata` volume. Three of the four gunicorn workers failed to boot on
two of three cold starts, and gunicorn halted the container with
`HaltServer 'Worker failed to boot.' 3`.

It was invisible because it heals itself: Docker restarts the container, the
winner's schema is committed, and the second boot finds everything present. The
only symptom is a service that took two attempts to start.

These tests drive the real functions against the real test Postgres from several
threads at once. Without `lock_schema` they fail the same way production did;
with it every thread returns cleanly.
"""

from __future__ import annotations

import threading

import pytest

from app.server.schema_lock import SCHEMA_INIT_LOCK_KEY, lock_schema


def _run_concurrently(work, threads: int = 8) -> list[BaseException]:
    """Run `work` on `threads` threads at once; return whatever it raised.

    A barrier rather than a plain thread start: the race needs the sessions to
    arrive at the `CREATE` together, and threads started in a loop otherwise
    tend to run one after another and never collide.
    """
    ready = threading.Barrier(threads)
    failures: list[BaseException] = []
    lock = threading.Lock()

    def target() -> None:
        try:
            ready.wait(timeout=30)
            work()
        except BaseException as exc:  # noqa: BLE001 - the point is to collect it
            with lock:
                failures.append(exc)

    workers = [threading.Thread(target=target) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=120)
    return failures


class TestTheLockItself:
    def test_the_key_is_stable(self):
        """Changing it between releases would stop it serialising anything."""
        assert SCHEMA_INIT_LOCK_KEY == 8_014_651_003_271_004_001

    def test_it_is_transaction_scoped(self, setup_db):
        """`pg_advisory_lock` would outlive a crashed migration and wedge every
        other process behind a lock nothing releases."""
        import inspect

        assert "pg_advisory_xact_lock" in inspect.getsource(lock_schema)

    def test_it_is_released_when_the_transaction_ends(self, setup_db):
        from app.server.auth import get_db_connection

        for _ in range(2):
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    lock_schema(cur)
                conn.commit()

        # A third taker must not block: if the first two had leaked the lock,
        # this would hang rather than fail.
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'"
                )
                held = cur.fetchone()[0]
            conn.commit()
        assert held == 0, "an advisory lock outlived its transaction"


def _drop(*tables: str) -> None:
    """Remove these tables so the next `CREATE` is a real create.

    Without this the tests prove nothing. `setup_db` builds the schema once per
    session, so by the time a test runs every `CREATE TABLE IF NOT EXISTS` is a
    no-op and no two sessions can collide - which is exactly the state that made
    the first version of this file pass with the lock deliberately disabled. The
    race only exists against an absent table, so the table has to be absent.
    """
    from app.server.auth import get_db_connection

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for table in tables:
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        conn.commit()


@pytest.fixture
def schema_restored(setup_db):
    """Put the schema back however the test leaves it.

    These tests drop real tables. Whether they pass or fail, the session's other
    tests need the schema back.
    """
    yield
    from app.server.auth import init_db
    from app.server.run_store import RunStore

    init_db()
    RunStore()._ensure_schema()


class TestConcurrentCreationSucceeds:
    """Each test drops its tables first, so the `CREATE` genuinely races.

    Verified to fail without the fix: with `lock_schema` stubbed out, the three
    tests below that drop `users` or `runs` raise
    `UniqueViolation: duplicate key value violates unique constraint
    "pg_type_typname_nsp_index"` with `DETAIL: Key (typname, typnamespace)=(users,
    2200) already exists` - the same error, on the same index, that three of four
    gunicorn workers hit on a cold start.

    The two `runtime_settings` tests at the end are weaker and say so where they
    stand; their tables create too quickly to lose the race dependably.
    """

    def test_init_db_from_many_workers_at_once(self, schema_restored):
        """The exact production failure: every gunicorn worker runs this."""
        from app.server.auth import init_db

        _drop("users", "audit_log")
        failures = _run_concurrently(init_db)
        assert not failures, f"init_db raced: {failures[:3]}"

    def test_the_admin_seed_does_not_double_insert(self, schema_restored):
        """The second race in `init_db`: SELECT for admin, then INSERT.

        Two workers that both read "no admin" both insert one, and the loser
        fails on the primary key. The lock covers this because it is held for
        the whole transaction, not just the DDL.
        """
        from app.server.auth import get_db_connection, init_db

        _drop("users", "audit_log")
        failures = _run_concurrently(init_db)
        assert not failures, f"the admin seed raced: {failures[:3]}"

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM users WHERE username = 'admin'")
                admins = cur.fetchone()[0]
            conn.commit()
        assert admins == 1

    def test_run_store_schema_from_two_processes(self, schema_restored):
        """`_ensure_schema` runs in the API and in the worker."""
        from app.server.run_store import RunStore

        store = RunStore()
        _drop("runs")
        failures = _run_concurrently(store._ensure_schema)
        assert not failures, f"_ensure_schema raced: {failures[:3]}"

    def test_runtime_settings_creates_its_tables_under_load(self, schema_restored):
        """These run on request paths, so the race is between two requests.

        `_read_overrides_from_db` rather than the cached `overrides()`, because
        the cache would let all but the first thread return without ever
        reaching the `CREATE` - which is the statement under test.
        """
        from app.server.runtime_settings import _read_overrides_from_db

        _drop("runtime_settings")
        # 16 rather than the default 8, and no higher: the pool holds 20
        # connections and every barrier-released thread takes one, so 24 here
        # raises `PoolError: connection pool exhausted` before the race can
        # even be reached.
        #
        # Honest limitation: these two tables create fast enough that this
        # test does *not* reliably fail with the guard removed, unlike the
        # three above, which fail every time. It is a smoke test that the
        # path works under concurrency; the guarantee that this path is
        # guarded at all comes from `TestEverySchemaCreatorTakesTheLock`.
        failures = _run_concurrently(_read_overrides_from_db, threads=16)
        assert not failures, f"_read_overrides_from_db raced: {failures[:3]}"

    def test_the_secrets_table_too(self, schema_restored):
        """`runtime_secrets` is created on its own set of paths."""
        from app.server.runtime_settings import _read_secrets_from_db

        _drop("runtime_secrets")
        failures = _run_concurrently(_read_secrets_from_db, threads=16)
        assert not failures, f"_read_secrets_from_db raced: {failures[:3]}"


class TestEverySchemaCreatorTakesTheLock:
    """The §1-B rule: a rule defined over part of the set it governs.

    Three modules create tables. Fixing two of them and leaving the third is how
    this bug comes back, in the one place nobody thought to look, so the set is
    asserted rather than trusted.
    """

    def test_no_create_table_is_left_unguarded(self):
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[1] / "src" / "app"
        offenders = []
        for path in root.rglob("*.py"):
            text = path.read_text()
            if "CREATE TABLE IF NOT EXISTS" not in text:
                continue
            if path.name == "schema_lock.py":
                continue  # its docstring names the statement it guards
            # Either guard is acceptable: `lock_schema` for a migration that
            # runs once at startup, `ensure_table` for a path that runs per
            # request and must not serialise on the common case.
            if "lock_schema" not in text and "ensure_table" not in text:
                offenders.append(str(path.relative_to(root)))
        assert not offenders, (
            f"these create tables without taking the schema lock: {offenders}"
        )


class TestTheCheckpointerMigrationIsGuardedToo:
    """LangGraph creates its own tables, and races on them the same way.

    Found on 2026-09-21 in the `worker` log during a live run, on a cold start:

        psycopg.errors.UniqueViolation: duplicate key value violates unique
        constraint "checkpoint_migrations_pkey"
        DETAIL:  Key (v)=(3) already exists.

    raised out of `PostgresSaver.setup()` inside Celery's
    `worker_process_init` handler. The API process and the worker both build a
    checkpointer at startup and both run the same migration.

    This one is in a library, so `test_no_create_table_is_left_unguarded` cannot
    see it: there is no `CREATE TABLE IF NOT EXISTS` in our source to find. The
    call site is ours, though, and that is what is asserted here.
    """

    def test_build_checkpointer_locks_around_setup(self):
        import inspect

        from app.graph.checkpointing import build_checkpointer

        source = inspect.getsource(build_checkpointer)
        assert "lock_schema" in source, "setup() is called without the schema lock"

    def test_the_lock_is_held_across_setup_not_merely_taken(self):
        """Taking the lock and then calling setup outside it does nothing.

        The lock has to still be held while the migration runs, or the two
        processes serialise on the lock and then race on the migration anyway.
        Still true; what changed is which lock. See the class below.
        """
        import inspect

        from app.graph.checkpointing import build_checkpointer

        lines = [
            line.strip()
            for line in inspect.getsource(build_checkpointer).splitlines()
            if "lock_schema_for_the_session(" in line or "saver.setup()" in line
        ]
        assert lines[-2].startswith("lock_schema_for_the_session"), lines
        assert lines[-1] == "saver.setup()", lines

    def test_no_transaction_is_opened_around_setup(self):
        """The opposite of what this file asserted until 2026-09-23.

        An explicit transaction was used here deliberately, because the pool
        is built with `autocommit=True` and a transaction-scoped advisory lock
        taken outside one is released instantly, serialising nothing.

        The reasoning was right and the lock was wrong. `setup()` issues three
        `CREATE INDEX CONCURRENTLY` statements; that statement cannot run
        inside a transaction block, so it runs on another connection and waits
        for every overlapping transaction to end - including the one holding
        the lock, which is waiting for `setup()` to return.

        Caught in `pg_stat_activity` with the suite stopped for thirty
        minutes:

            pid 77 | idle in transaction | SELECT pg_advisory_xact_lock($1)
            pid 78 | active | Lock | virtualxid | CREATE INDEX CONCURRENTLY

        A session-scoped lock serialises the two processes without holding a
        transaction, which is what both properties need at once.
        """
        import inspect

        from app.graph.checkpointing import build_checkpointer

        source = inspect.getsource(build_checkpointer)
        setup = source.rindex("saver.setup()")
        # Comments stripped: the explanation above this code quotes the old
        # statement, and an assertion that reads its own rationale as the
        # thing it forbids is the "reached twelve of thirteen" mistake in
        # miniature.
        window = "\n".join(
            line for line in source[max(0, setup - 1400):setup].splitlines()
            if not line.strip().startswith("#")
        )

        assert ".transaction()" not in window, (
            "an open transaction here deadlocks against CREATE INDEX CONCURRENTLY"
        )
        assert "pg_advisory_xact_lock" not in window
        assert "lock_schema_for_the_session" in window
