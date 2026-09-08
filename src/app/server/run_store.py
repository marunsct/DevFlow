"""SQLite-backed persistence for run metadata.

Run records track everything the API needs to answer status queries: run ID,
thread ID, status, current stage, document names, timestamps, settings, and
error messages.  The full graph *state* (specialist outputs, remediation
cycles, etc.) lives in ``checkpoints.sqlite`` via LangGraph's own
``SqliteSaver``; this store only persists the lightweight metadata envelope.

Why a separate database?
    The LangGraph checkpointer owns graph state and is keyed by thread_id.
    Run metadata (which documents were uploaded, what review policy was chosen,
    when the run was created) is orthogonal to graph state and has a different
    lifecycle: it must survive server restarts even for runs that never started,
    and it must support listing all runs regardless of their thread.
"""

from __future__ import annotations

import json
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from typing import Any

from app.server.runner import RunRecord


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
    auto_approve    INTEGER NOT NULL DEFAULT 0,
    document_names  TEXT NOT NULL DEFAULT '[]',
    document_paths  TEXT NOT NULL DEFAULT '[]',
    repo_root       TEXT
);
"""


class RunStore:
    """Durable store for ``RunRecord`` metadata using Postgres."""

    def __init__(self, db_url: str | None = None) -> None:
        if db_url is None:
            db_url = os.environ.get("DB_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
        self._conn = psycopg2.connect(db_url)
        self._conn.autocommit = True
        
        with self._conn.cursor() as cur:
            cur.execute(_CREATE_TABLE)
            
            # Add repo_root column if it doesn't exist (migration for existing DBs)
            try:
                cur.execute("ALTER TABLE runs ADD COLUMN repo_root TEXT")
            except psycopg2.Error:
                pass  # Column already exists


    def save(self, record: RunRecord) -> None:
        """Insert or replace a run record."""
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO runs
                    (run_id, thread_id, status, current_stage, stage_meaning,
                     created_at, updated_at, error, review_policy, reviewer,
                     auto_approve, document_names, document_paths, repo_root)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    thread_id = EXCLUDED.thread_id,
                    status = EXCLUDED.status,
                    current_stage = EXCLUDED.current_stage,
                    stage_meaning = EXCLUDED.stage_meaning,
                    updated_at = EXCLUDED.updated_at,
                    error = EXCLUDED.error,
                    review_policy = EXCLUDED.review_policy,
                    reviewer = EXCLUDED.reviewer,
                    auto_approve = EXCLUDED.auto_approve,
                    document_names = EXCLUDED.document_names,
                    document_paths = EXCLUDED.document_paths,
                    repo_root = EXCLUDED.repo_root
                """,
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
                    int(record.auto_approve),
                    json.dumps(record.document_names),
                    json.dumps(record.document_paths),
                    record.repo_root,
                ),
            )

    def load(self, run_id: str) -> RunRecord | None:
        """Load a single run record, or None if it doesn't exist."""
        with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM runs WHERE run_id = %s", (run_id,))
            row = cur.fetchone()
            if row is None:
                return None
            return self._row_to_record(row)

    def list_all(self) -> list[RunRecord]:
        """Return all run records ordered by creation time (newest first)."""
        with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM runs ORDER BY created_at DESC")
            rows = cur.fetchall()
            return [self._row_to_record(r) for r in rows]

    def delete(self, run_id: str) -> None:
        """Delete a run record."""
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))

    @staticmethod
    def _row_to_record(row: dict) -> RunRecord:
        """Deserialize a database row back into a RunRecord.

        The resulting record has no background task or decision event
        attached — those are ephemeral and only exist while the server
        process is running.
        """
        return RunRecord(
            run_id=row["run_id"],
            thread_id=row["thread_id"],
            status=row["status"],
            current_stage=row["current_stage"],
            stage_meaning=row["stage_meaning"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error=row["error"],
            repo_root=row["repo_root"] if "repo_root" in row.keys() else None,
            review_policy=json.loads(row["review_policy"]),
            reviewer=row["reviewer"],
            auto_approve=bool(row["auto_approve"]),
            document_names=json.loads(row["document_names"]),
            document_paths=json.loads(row["document_paths"]),
        )

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()


__all__ = ["RunStore"]
