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

import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.agents.architecture_reviewer import ArchitectureReviewFinding, ArchitectureReviewOutput
from app.agents.milestone_reviewer import MilestoneReviewFinding, MilestoneReviewOutput
from app.agents.principal_architect import ArchitectureDecisionRecord, TechnicalSpecificationOutput
from app.agents.product_manager import ProductManagerOutput
from app.agents.scrum_master import SprintDefinition, SprintPlanOutput
from app.agents.security_reviewer import SecurityFinding, SecurityReviewOutput
from app.agents.specialists import ReportedDefect, SpecialistOutput
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.agents.tools_models import TechnologyChoice, ToolsAndModelsOutput
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


# Create a global connection for the app lifecycle
_DB_PATH = "checkpoints.sqlite"
_conn = None

def get_connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    return _conn


def build_checkpointer() -> SqliteSaver:
    """Build the durable SQLite checkpointer with the allowlist applied.

    The state is saved to `checkpoints.sqlite` so workflow runs survive server restarts.
    """
    saver = SqliteSaver(get_connection(), serde=build_serializer())
    saver.setup()
    return saver


__all__ = ["CHECKPOINTED_TYPES", "build_checkpointer", "build_serializer"]
