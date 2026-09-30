"""Checkpointer construction with an explicit deserialization allowlist.

Why this module exists
----------------------
LangGraph checkpoints the workflow state so a paused run can resume. That state
holds our own Pydantic models (`ProductManagerOutput`, `RemediationCycle`,
`ReviewStatus`, ...), and by default LangGraph will happily reconstruct *any*
type it finds in a checkpoint, warning each time that this will be blocked in a
future version.

Two reasons to pin it down now rather than later:

1. **Security.** LangGraph's own serializer documentation warns that anyone able
   to write to the checkpoint store may be able to trigger code execution when
   the data is deserialized. An allowlist means a tampered checkpoint can only
   rebuild the handful of types this workflow actually stores, not arbitrary
   importable classes. That matters more, not less, once Step 8.1 moves
   checkpoints out of memory into a shared database.
2. **Forward compatibility.** The permissive default is deprecated. Declaring
   the allowlist explicitly means a LangGraph upgrade tightening this cannot
   silently break resume.

If you add a new Pydantic model to `WorkflowGraphState`, add it to
`CHECKPOINTED_TYPES` too, or resuming a run that contains it will fail.
"""

from __future__ import annotations

import os
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
import psycopg
from psycopg_pool import ConnectionPool
import sqlite3
from app.config import load_settings
from app.server.process_local import PerProcess

from app.agents.architecture_reviewer import ArchitectureReviewFinding, ArchitectureReviewOutput
from app.agents.milestone_reviewer import MilestoneReviewFinding, MilestoneReviewOutput
from app.agents.principal_architect import ArchitectureDecisionRecord, TechnicalSpecificationOutput
from app.agents.product_manager import ProductManagerOutput
from app.agents.scrum_master import SprintDefinition, SprintPlanOutput
from app.agents.stack_selector import StackSelectorOutput
from app.agents.security_reviewer import SecurityFinding, SecurityReviewOutput
from app.agents.specialists import ReportedDefect, SpecialistOutput, VerificationRun
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.agents.tools_models import TechnologyChoice, TechnologyStack, ToolsAndModelsOutput
from app.documents import DocumentContent
from app.sprint import Defect, RemediationCycle, TestRunRecord
from app.state import (
    ApprovalDecision,
    HumanApprovalRequest,
    RepositoryContext,
    ReviewRequestStatus,
    ReviewStatus,
    WorkflowStage,
)

CHECKPOINTED_TYPES = (
    # Product input and repository boundary
    DocumentContent,
    RepositoryContext,
    # Role outputs stored in graph state
    ProductManagerOutput,
    ToolsAndModelsOutput,
    TechnologyChoice,
    StackSelectorOutput,
    TechnologyStack,
    TechnicalSpecificationOutput,
    ArchitectureDecisionRecord,
    SecurityReviewOutput,
    SecurityFinding,
    ArchitectureReviewOutput,
    ArchitectureReviewFinding,
    MilestoneReviewOutput,
    MilestoneReviewFinding,
    SprintPlanOutput,
    SprintDefinition,
    MilestonePlanOutput,
    SpecialistTask,
    SpecialistOutput,
    VerificationRun,
    ReportedDefect,
    # Sprint remediation bookkeeping
    RemediationCycle,
    Defect,
    TestRunRecord,
    # Approval and review contracts, including their enums
    HumanApprovalRequest,
    ApprovalDecision,
    ReviewStatus,
    ReviewRequestStatus,
    WorkflowStage,
)
"""Every type this workflow may store in a LangGraph checkpoint."""


from app.server.schema_lock import (
    lock_schema_for_the_session,
    unlock_schema,
)


def build_serializer() -> JsonPlusSerializer:
    """Build the checkpoint serializer restricted to this workflow's own types."""
    return JsonPlusSerializer(allowed_msgpack_modules=list(CHECKPOINTED_TYPES))


# One connection pool per process. Per process, not per module: a pool built in
# the Celery parent is inherited by every worker it forks later, and two
# processes on one socket is a dropped connection. See `app.server.process_local`.
_pool: PerProcess[ConnectionPool] = PerProcess()

def get_connection_pool() -> ConnectionPool:
    db_url = os.environ.get("DB_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
    return _pool.get(lambda: ConnectionPool(conninfo=db_url, max_size=20, kwargs={"autocommit": True}))

def build_checkpointer():
    """Build the checkpointer based on configuration with the allowlist applied."""
    settings = load_settings()
    serde = build_serializer()
    
    if settings.checkpointer_type == "sqlite":
        data_dir = os.environ.get("DATA_DIR", ".")
        sqlite_path = os.path.join(data_dir, "checkpoints.sqlite")
        conn = sqlite3.connect(sqlite_path, check_same_thread=False)
        saver = SqliteSaver(conn, serde=serde)
        saver.setup()
        return saver
    elif settings.checkpointer_type == "postgres":
        pool = get_connection_pool()
        saver = PostgresSaver(pool, serde=serde)
        # `PostgresSaver.setup()` creates LangGraph's own checkpoint tables and
        # inserts into `checkpoint_migrations`. It has the same defect as our
        # schema creation did, in a library we do not own: the API process and
        # the worker both call it, and against a fresh database both run the
        # same migration. Observed on 2026-09-21 in `worker` on a cold start:
        #
        #   psycopg.errors.UniqueViolation: duplicate key value violates unique
        #   constraint "checkpoint_migrations_pkey"
        #   DETAIL:  Key (v)=(3) already exists.
        #
        # It raises out of `build_checkpointer`, so the loser gets no
        # checkpointer at all. The same advisory lock serialises it; the lock is
        # taken on a connection of our own and held across `setup()`, which is
        # what makes the two processes take turns.
        #
        # A SESSION-scoped lock, not a transaction-scoped one, and the
        # difference is the whole of this comment.
        #
        # `setup()` issues three `CREATE INDEX CONCURRENTLY` statements. That
        # statement cannot run inside a transaction block, so it runs on
        # another connection, and before it can finish it waits for every
        # transaction overlapping it to end. Holding `pg_advisory_xact_lock`
        # here made this connection exactly such a transaction - one that is
        # waiting for `setup()` to return. Neither side could move.
        #
        # Observed on 2026-09-23, a suite stopped for thirty minutes at
        # `tests/test_api_contract.py`:
        #
        #   pid 77 | idle in transaction | SELECT pg_advisory_xact_lock($1)
        #   pid 78 | active | Lock | virtualxid | CREATE INDEX CONCURRENTLY
        #
        # It fires only when the indexes do not exist yet - a fresh database
        # always, an established one never - which is why it looked like an
        # occasional slow start rather than a deadlock.
        #
        # The pool is built with `autocommit=True`, so `pg_advisory_lock`
        # holds at session level with no transaction open: two processes
        # still take turns and nothing blocks the index build. It is not
        # released for us, hence the `finally`.
        with pool.connection() as guard:
            cursor = guard.cursor()
            lock_schema_for_the_session(cursor)
            try:
                saver.setup()
            finally:
                unlock_schema(cursor)
        return saver
    else:
        # Default to memory
        return MemorySaver(serde=serde)


__all__ = ["CHECKPOINTED_TYPES", "build_checkpointer", "build_serializer"]
