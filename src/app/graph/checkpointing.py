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

from app.agents.architecture_reviewer import ArchitectureReviewFinding, ArchitectureReviewOutput
from app.agents.milestone_reviewer import MilestoneReviewFinding, MilestoneReviewOutput
from app.agents.principal_architect import ArchitectureDecisionRecord, TechnicalSpecificationOutput
from app.agents.product_manager import ProductManagerOutput
from app.agents.scrum_master import SprintDefinition, SprintPlanOutput
from app.agents.stack_selector import StackSelectorOutput
from app.agents.security_reviewer import SecurityFinding, SecurityReviewOutput
from app.agents.specialists import ReportedDefect, SpecialistOutput
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


def build_serializer() -> JsonPlusSerializer:
    """Build the checkpoint serializer restricted to this workflow's own types."""
    return JsonPlusSerializer(allowed_msgpack_modules=list(CHECKPOINTED_TYPES))


# Create a global connection pool for the app lifecycle
_pool = None

def get_connection_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        db_url = os.environ.get("DB_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
        _pool = ConnectionPool(conninfo=db_url, max_size=20, kwargs={"autocommit": True})
    return _pool

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
        saver = PostgresSaver(get_connection_pool(), serde=serde)
        saver.setup()
        return saver
    else:
        # Default to memory
        return MemorySaver(serde=serde)


__all__ = ["CHECKPOINTED_TYPES", "build_checkpointer", "build_serializer"]
