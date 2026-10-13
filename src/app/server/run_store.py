"""Postgres-backed persistence for run metadata.

Run records carry everything the API needs to answer status queries and to
authorise access: identity, ownership, status, stage, documents, timestamps and
the workspace path. The graph *state* (specialist outputs, remediation cycles)
lives in the LangGraph checkpointer keyed by ``thread_id`` and is read from
there, never duplicated here - two copies of the same state drift, and the
metadata copy was previously never written at all, so every API read saw an
empty dict.

Two things this module is careful about:

- **Connections are pooled and always returned**, with a rollback on the error
  path so a failed transaction is never handed to the next borrower.
- **Status transitions are atomic.** ``compare_and_set_status`` performs the
  check and the write in one statement, because the read-then-write pattern it
  replaces allowed two concurrent approvals to both pass the guard.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from typing import Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from app.server.runner import RunRecord

from app.server.process_local import owned_here
from app.server.schema_lock import lock_schema

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,
    thread_id       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'created',
    current_stage   TEXT NOT NULL DEFAULT '',
    stage_meaning   TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    error           TEXT,
    review_policy   TEXT NOT NULL DEFAULT '{}',
    reviewer        TEXT NOT NULL DEFAULT 'unassigned',
    auto_approve    BOOLEAN NOT NULL DEFAULT FALSE,
    document_names  TEXT NOT NULL DEFAULT '[]',
    document_paths  TEXT NOT NULL DEFAULT '[]',
    repo_root       TEXT,
    owner           TEXT NOT NULL DEFAULT 'unknown',
    tenant_id       TEXT NOT NULL DEFAULT 'default',
    task_id         TEXT,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    model_overrides TEXT NOT NULL DEFAULT '{}'
);
"""

_MIGRATIONS = (
    "ALTER TABLE runs ADD COLUMN IF NOT EXISTS repo_root TEXT",
    "ALTER TABLE runs ADD COLUMN IF NOT EXISTS owner TEXT NOT NULL DEFAULT 'unknown'",
    "ALTER TABLE runs ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default'",
    "ALTER TABLE runs ADD COLUMN IF NOT EXISTS task_id TEXT",
    "ALTER TABLE runs ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE runs ADD COLUMN IF NOT EXISTS model_overrides TEXT NOT NULL DEFAULT '{}'",
    # Why the stop flag was raised: 'cancel' (the default) or 'pause'. The
    # worker stops the same way for both, at a stage boundary; only the status
    # it records differs, and a paused run is resumed, not ended.
    "ALTER TABLE runs ADD COLUMN IF NOT EXISTS stop_reason TEXT",
    "CREATE INDEX IF NOT EXISTS runs_tenant_created_idx ON runs (tenant_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS runs_owner_idx ON runs (owner)",
)

# Statements are literal constants - no SQL is assembled from any runtime value.
# Every value that reaches the process is passed as a bound parameter.
#
# Written out in full rather than interpolated from a shared constant so that no
# SQL string in this module is an f-string at all: that keeps the "is any of this
# built from input?" question answerable by reading, not by tracing a variable.
#
# Statements are assembled once, at import, from module constants only. Nothing
# here is built from a value that reaches the process at runtime; every such
# value is passed as a bound parameter.
_INSERT_SQL = """
    INSERT INTO runs (run_id, thread_id, status, current_stage, stage_meaning, created_at, updated_at, error, review_policy, reviewer, auto_approve, document_names, document_paths, repo_root, owner, tenant_id, task_id, cancel_requested, model_overrides)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (run_id) DO UPDATE SET
        thread_id        = EXCLUDED.thread_id,
        status           = EXCLUDED.status,
        current_stage    = EXCLUDED.current_stage,
        stage_meaning    = EXCLUDED.stage_meaning,
        updated_at       = EXCLUDED.updated_at,
        error            = EXCLUDED.error,
        review_policy    = EXCLUDED.review_policy,
        reviewer         = EXCLUDED.reviewer,
        auto_approve     = EXCLUDED.auto_approve,
        document_names   = EXCLUDED.document_names,
        document_paths   = EXCLUDED.document_paths,
        repo_root        = EXCLUDED.repo_root,
        owner            = EXCLUDED.owner,
        tenant_id        = EXCLUDED.tenant_id,
        task_id          = COALESCE(runs.task_id, EXCLUDED.task_id),
        model_overrides  = EXCLUDED.model_overrides
"""

_SELECT_ONE_SQL = "SELECT run_id, thread_id, status, current_stage, stage_meaning, created_at, updated_at, error, review_policy, reviewer, auto_approve, document_names, document_paths, repo_root, owner, tenant_id, task_id, cancel_requested, model_overrides FROM runs WHERE run_id = %s"
_LIST_ALL_SQL = "SELECT run_id, thread_id, status, current_stage, stage_meaning, created_at, updated_at, error, review_policy, reviewer, auto_approve, document_names, document_paths, repo_root, owner, tenant_id, task_id, cancel_requested, model_overrides FROM runs ORDER BY created_at DESC LIMIT %s OFFSET %s"
_LIST_TENANT_SQL = (
    "SELECT run_id, thread_id, status, current_stage, stage_meaning, created_at, updated_at, error, review_policy, reviewer, auto_approve, document_names, document_paths, repo_root, owner, tenant_id, task_id, cancel_requested, model_overrides FROM runs WHERE tenant_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s"
)
_COUNT_ALL_SQL = "SELECT COUNT(*) FROM runs"
_COUNT_TENANT_SQL = "SELECT COUNT(*) FROM runs WHERE tenant_id = %s"
#: Runs holding a worker slot right now. `running` is the only status that
#: occupies one: every pause - approval, review, budget - has released the
#: worker and is waiting on a human.
_COUNT_IN_FLIGHT_SQL = "SELECT COUNT(*) FROM runs WHERE status = 'running'"


def database_url() -> str:
    """Resolved at call time so tests and late-loading secrets are honoured."""
    return os.environ.get("DB_URL", "postgresql://postgres:postgres@localhost:5432/postgres")


class RunStore:
    """Durable store for ``RunRecord`` metadata."""

    _shared: Optional["RunStore"] = None
    _shared_owner: Optional[int] = None
    _shared_lock = threading.Lock()

    def __init__(self, db_url: str | None = None) -> None:
        self._pool = ThreadedConnectionPool(1, 20, db_url or database_url())
        self._ensure_schema()

    @classmethod
    def shared(cls) -> "RunStore":
        """One store per process.

        Celery previously constructed a RunStore per task, each opening a pool of
        up to 20 connections and never closing it, which exhausted Postgres after
        a few dozen tasks.
        """
        # Per process, not per class: a store built in the Celery parent is
        # inherited by every worker it forks later, and two processes on one
        # connection is a dropped connection. See `app.server.process_local`.
        with cls._shared_lock:
            if cls._shared is None or not owned_here(cls._shared_owner):
                cls._shared = cls()
                cls._shared_owner = os.getpid()
            return cls._shared

    @classmethod
    def reset_shared(cls) -> None:
        with cls._shared_lock:
            # An inherited store is dropped, never closed: closing it here
            # closes the parent's connections.
            if cls._shared is not None and owned_here(cls._shared_owner):
                cls._shared.close()
            cls._shared = None
            cls._shared_owner = None

    def _ensure_schema(self) -> None:
        """Create the runs table and apply the additive migrations.

        Runs when a store is constructed, which happens in the API and in the
        worker, so two processes starting together race on the `CREATE TABLE IF
        NOT EXISTS` unless they are serialised. See `app.server.schema_lock`.
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                lock_schema(cur)
                cur.execute(_CREATE_TABLE)
                for statement in _MIGRATIONS:
                    cur.execute(statement)
            conn.commit()

    @contextmanager
    def get_connection(self):
        conn = self._pool.getconn()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            try:
                conn.rollback()
            except Exception:
                pass
            self._pool.putconn(conn)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def save(self, record: RunRecord) -> None:
        """Persist a record.

        ``cancel_requested`` is deliberately absent from the UPDATE set: it is
        owned solely by ``request_cancel``. Writing it from an in-memory record
        would let a worker's routine persist reset a cancellation that arrived
        while it was mid-step - which is precisely how the previous
        implementation made cancel a no-op.

        ``task_id`` is the same kind of field: ``set_task_id`` owns it, and a
        save keeps the stored one. A worker's record was loaded before the API
        recorded the task that worker was running, so its routine persist wrote
        the previous task's id back - and a pause revoked a task that no longer
        existed, leaving the run going until its next stage boundary.
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _INSERT_SQL,
                    (
                        record.run_id,
                        record.thread_id,
                        record.status,
                        record.current_stage,
                        record.stage_meaning,
                        record.created_at,
                        record.updated_at,
                        record.error,
                        json.dumps(record.review_policy),
                        record.reviewer,
                        bool(record.auto_approve),
                        json.dumps(record.document_names),
                        json.dumps(record.document_paths),
                        record.repo_root,
                        record.owner,
                        record.tenant_id,
                        record.task_id,
                        bool(record.cancel_requested),
                        json.dumps(record.model_overrides or {}),
                    ),
                )
            conn.commit()

    def compare_and_set_status(
        self,
        run_id: str,
        expected: str | tuple[str, ...],
        new_status: str,
        *,
        updated_at: str,
        error: str | None = None,
        task_id: str | None = None,
        clear_error: bool = False,
    ) -> bool:
        """Atomically move a run from one status to another.

        Returns False if the run was not in the expected status, which the API
        turns into a 409. Doing the check inside the UPDATE is what makes
        double-submitted approvals and double-clicked start buttons safe.
        """
        expected_tuple = (expected,) if isinstance(expected, str) else tuple(expected)
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE runs
                       SET status = %s,
                           updated_at = %s,
                           error = CASE WHEN %s THEN NULL ELSE COALESCE(%s, error) END,
                           task_id = COALESCE(%s, task_id)
                     WHERE run_id = %s AND status = ANY(%s)
                    """,
                    (new_status, updated_at, clear_error, error, task_id, run_id, list(expected_tuple)),
                )
                changed = cur.rowcount
            conn.commit()
        return changed == 1

    def request_cancel(self, run_id: str, updated_at: str) -> bool:
        """Flag a run for cancellation without clobbering the worker's status.

        The worker checks this between supersteps and stops. Setting the status
        directly (as the previous implementation did) was pointless: the worker's
        next persist overwrote it.
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE runs SET cancel_requested = TRUE, stop_reason = 'cancel', updated_at = %s "
                    "WHERE run_id = %s AND status NOT IN ('completed','failed','cancelled')",
                    (updated_at, run_id),
                )
                changed = cur.rowcount
            conn.commit()
        return changed == 1

    def request_pause(self, run_id: str, updated_at: str) -> bool:
        """Flag a running run to stop at its next stage boundary and wait to be resumed.

        The same flag a cancel raises, so the worker stops the same way; the
        reason makes it record `paused` and keep everything (see
        `WorkflowRunner._finish_stopped`). Only a running run can be paused: a
        run parked on a person is already waiting.
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE runs SET cancel_requested = TRUE, stop_reason = 'pause', updated_at = %s "
                    "WHERE run_id = %s AND status = 'running'",
                    (updated_at, run_id),
                )
                changed = cur.rowcount
            conn.commit()
        return changed == 1

    def stop_reason(self, run_id: str) -> str:
        """Why the run's stop flag was raised: 'pause', or 'cancel' for anything else."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT stop_reason FROM runs WHERE run_id = %s", (run_id,))
                row = cur.fetchone()
        return "pause" if row and row[0] == "pause" else "cancel"

    def clear_stop(self, run_id: str) -> None:
        """Lower the stop flag, for a run being resumed."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE runs SET cancel_requested = FALSE, stop_reason = NULL WHERE run_id = %s",
                    (run_id,),
                )
            conn.commit()

    def is_cancel_requested(self, run_id: str) -> bool:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT cancel_requested FROM runs WHERE run_id = %s", (run_id,))
                row = cur.fetchone()
        return bool(row[0]) if row else False

    def set_task_id(self, run_id: str, task_id: str) -> None:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE runs SET task_id = %s WHERE run_id = %s", (task_id, run_id))
            conn.commit()

    def delete(self, run_id: str) -> None:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
            conn.commit()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def load(self, run_id: str) -> RunRecord | None:
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(_SELECT_ONE_SQL, (run_id,))
                row = cur.fetchone()
        return self._row_to_record(row) if row else None

    def list_all(
        self,
        *,
        tenant_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RunRecord]:
        """Return runs newest first, scoped to a tenant and always bounded."""
        bounded_limit = max(1, min(limit, 500))
        bounded_offset = max(0, offset)
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if tenant_id:
                    cur.execute(_LIST_TENANT_SQL, (tenant_id, bounded_limit, bounded_offset))
                else:
                    cur.execute(_LIST_ALL_SQL, (bounded_limit, bounded_offset))
                rows = cur.fetchall()
        return [self._row_to_record(r) for r in rows]

    def document_in_use(self, path: str, *, exclude_run_id: str) -> bool:
        """Whether any other run still references this uploaded file.

        Clones share document paths, so deleting one run must not remove files a
        sibling still needs.
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM runs WHERE run_id <> %s AND document_paths LIKE %s LIMIT 1",
                    (exclude_run_id, f"%{path}%"),
                )
                return cur.fetchone() is not None

    def count(self, tenant_id: str | None = None) -> int:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if tenant_id:
                    cur.execute(_COUNT_TENANT_SQL, (tenant_id,))
                else:
                    cur.execute(_COUNT_ALL_SQL)
                return int(cur.fetchone()[0])

    def count_in_flight(self) -> int:
        """How many runs are executing right now, across every tenant.

        Counted in the database rather than from Celery, because the question
        is asked at dispatch by whichever API worker took the request and
        Celery's own inspection is a broadcast with a timeout. The status is
        written before the task is dispatched and cleared by the worker, so
        this is the same fact one join earlier.
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(_COUNT_IN_FLIGHT_SQL)
                return int(cur.fetchone()[0])

    @staticmethod
    def _row_to_record(row: dict) -> RunRecord:
        def _json(value: Any, default: Any) -> Any:
            if not value:
                return default
            try:
                return json.loads(value)
            except (TypeError, ValueError):
                logger.warning("Could not decode stored JSON column; using default")
                return default

        return RunRecord(
            run_id=row["run_id"],
            thread_id=row["thread_id"],
            status=row["status"],
            current_stage=row["current_stage"],
            stage_meaning=row["stage_meaning"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error=row["error"],
            repo_root=row["repo_root"],
            review_policy=_json(row["review_policy"], {}),
            reviewer=row["reviewer"],
            auto_approve=bool(row["auto_approve"]),
            document_names=_json(row["document_names"], []),
            document_paths=_json(row["document_paths"], []),
            owner=row.get("owner") or "unknown",
            tenant_id=row.get("tenant_id") or "default",
            task_id=row.get("task_id"),
            cancel_requested=bool(row.get("cancel_requested")),
            model_overrides=_json(row.get("model_overrides"), {}),
        )

    def close(self) -> None:
        try:
            self._pool.closeall()
        except Exception:  # noqa: BLE001
            logger.debug("Ignoring error closing run store pool", exc_info=True)


__all__ = ["RunStore", "database_url"]
