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

import logging
import os
from typing import Any

from pydantic import BaseModel
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


#: The integers msgpack can store: signed and unsigned 64-bit.
_SMALLEST_STORABLE, _LARGEST_STORABLE = -(2**63), 2**64 - 1


def _storable(value: Any, path: str, changed: list[str]) -> Any:
    """`value` with every integer msgpack cannot hold written as text, the paths in `changed`.

    Inside a message or a model, a copy of it with the field changed, so it
    is still read back as a message or a model.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not _SMALLEST_STORABLE <= value <= _LARGEST_STORABLE:
        changed.append(path)
        return str(value)
    if isinstance(value, dict):
        return {k: _storable(v, f"{path}.{k}", changed) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        items = [_storable(v, f"{path}[{i}]", changed) for i, v in enumerate(value)]
        return items if isinstance(value, list) else type(value)(items) if not hasattr(value, "_fields") else type(value)(*items)
    if isinstance(value, BaseModel):
        before = len(changed)
        update = {
            name: _storable(getattr(value, name, None), f"{path}.{name}", changed)
            for name in type(value).model_fields
        }
        return value.model_copy(update=update) if len(changed) > before else value
    return value


def _unusual(value: Any, path: str) -> list[str]:
    """Where `value` holds something other than text, numbers, lists, maps and models, for the log."""
    if isinstance(value, (str, int, float, bool, type(None), bytes)):
        return []
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in _unusual(v, f"{path}.{k}")]
    if isinstance(value, (list, tuple)):
        return [p for i, v in enumerate(value) for p in _unusual(v, f"{path}[{i}]")]
    if isinstance(value, BaseModel):
        return [p for name in type(value).model_fields for p in _unusual(getattr(value, name, None), f"{path}.{name}")]
    return [f"{path} ({type(value).__name__})"]


class _StorableSerializer(JsonPlusSerializer):
    """The serializer, which stores an integer msgpack cannot hold as text rather than failing the run.

    Measured on one run: 15 hours in, a stage's reply held such an integer
    somewhere in the message the agent was writing, and the write raised
    "Type is not msgpack serializable: AIMessage" - the run failed. Where it
    was is logged, so the cause can be found.
    """

    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        try:
            return super().dumps_typed(obj)
        except TypeError as error:
            changed: list[str] = []
            fixed = _storable(obj, "value", changed)
            if not changed:
                logger.error("A checkpoint write cannot be stored (%s); unusual values in it: %s",
                             error, ", ".join(_unusual(obj, "value")[:10]) or "none found")
                raise
            logger.warning(
                "A checkpoint write held integers msgpack cannot store (%s); stored as text at: %s",
                error, ", ".join(changed[:10]),
            )
            return super().dumps_typed(fixed)


def build_serializer() -> JsonPlusSerializer:
    """Build the checkpoint serializer restricted to this workflow's own types."""
    return _StorableSerializer(allowed_msgpack_modules=list(CHECKPOINTED_TYPES))


logger = logging.getLogger(__name__)

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
