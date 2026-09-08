"""Product Manager Deep Agent.

This module implements the first role worker in the workflow. Its job is not to
build code or change the app directly. Instead, it reads product documents and
repository context, identifies the product problem space, and returns a
structured intake artifact suitable for review by later workflow stages.

The big idea is easy to understand: each role agent is narrow and deliberate.
The Product Manager stays in discovery mode, while the runtime graph remains the
piece that decides when a write is allowed and when a human should review it.
Safety wiring (tools, approval gate, checkpointer) lives in `app.agents.role_agent`
and `app.agents.approval` so every future role agent shares it instead of
re-implementing it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.approval import (
    approve_write_decision as approve_write_decision,
)
from app.agents.approval import (
    edit_write_decision as edit_write_decision,
)
from app.agents.approval import (
    extract_pending_approval as _extract_pending_approval,
)
from app.agents.approval import (
    reject_write_decision as reject_write_decision,
)
from app.agents.approval import (
    resume_with_decision as resume_with_decision,
)
from app.agents.role_agent import create_role_agent, default_repo_root
from app.documents import DocumentContent
from app.state import HumanApprovalRequest, RepositoryContext

_STAGE = "intake"
_NAME = "product_manager"


class ProductManagerOutput(BaseModel):
    """Structured product-intake output returned by the Product Manager agent.

    The schema deliberately mirrors the product discovery fields named in the
    workflow plan. Every field is intended to be reviewable by a human and
    machine-readable by the later pipeline stages.
    """

    model_config = ConfigDict(extra="forbid")

    product_name: str = Field(..., description="Human-readable product identifier.")
    users_and_stakeholders: list[str] = Field(default_factory=list)
    problems_and_desired_outcomes: list[str] = Field(default_factory=list)
    core_workflows: list[str] = Field(default_factory=list)
    mvp_candidates: list[str] = Field(default_factory=list)
    deferred_scope: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    evidence_vs_assumptions: list[str] = Field(default_factory=list)
    success_measures: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


def build_intake_request(
    document: DocumentContent, repository: RepositoryContext
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input from a read product document and repo context.

    `create_product_manager_agent` only builds the graph; something still has to
    turn a `DocumentContent` (from `app.documents.read_document`) and a
    `RepositoryContext` (from `app.state`) into the first message the agent sees.
    Callers should pass this function's return value straight to `agent.invoke`.
    """
    brief = (
        f"Product document source: {document.source_path} ({document.source_type})\n"
        f"Repository root: {repository.root_path} "
        f"(branch: {repository.branch}, commit: {repository.commit})\n\n"
        f"--- Product document text ---\n{document.text}\n"
    )
    if document.truncated and document.truncation_note:
        brief += f"\nNote: {document.truncation_note}\n"
    return {"messages": [{"role": "user", "content": brief}]}


def extract_pending_approval(
    result: dict[str, Any],
    repo_root: str | Path,
    *,
    requested_by: str = _NAME,
) -> HumanApprovalRequest | None:
    """Product-Manager-flavored wrapper around the generic approval extractor.

    Kept here (instead of requiring callers to pass `stage="intake"` every
    time) so existing call sites and tests keep working unchanged.
    """
    return _extract_pending_approval(result, repo_root, requested_by=requested_by, stage=_STAGE)


_SYSTEM_PROMPT = """You are the Product Manager and UX discovery partner for this workflow.

Your role is to turn a supplied product brief and repository evidence into a clear product intake artifact.

Ground every conclusion in the product document and repository evidence. If evidence is missing, state it as an assumption instead of inventing certainty.

Responsibilities:
- Identify the product name and who the users or stakeholders are.
- Summarize problems, pain points, desired outcomes, and the value the product should create.
- Describe the main workflows and the likely MVP candidates.
- Call out deferred scope, constraints, evidence-vs-assumptions, success measures, and open product questions.
- Prioritize decision-worthy product clarity over speculative future features.

Constraints:
- Do not modify application source code.
- Do not change repo files except through the approved artifact tool.
- Only write an intake artifact inside the generated docs area.
- Do not claim a requirement is fact without evidence from the supplied brief or repository context.
- Every write_artifact call pauses for a human decision before anything is saved; never tell the user the artifact is saved until you see a tool result confirming a completed write.
- Keep the output structured and concise.

Return the response in the required output schema only.
"""


def create_product_manager_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
        allow_subdirectories: bool = True,
) -> Any:
    """Create the Product Manager role worker using the Deep Agents runtime.

    This is a thin wrapper around `create_role_agent`: it supplies the
    Product-Manager-specific system prompt and output schema, and lets the
    shared factory handle tools, the approval gate, and checkpointing.
    """
    return create_role_agent(
        name=_NAME,
        stage=_STAGE,
        system_prompt=_SYSTEM_PROMPT,
        response_format=ProductManagerOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root, allow_subdirectories=allow_subdirectories,
    )


def _repo_root() -> Path:
    """Backward-compatible alias kept for any external callers of the old name."""
    return default_repo_root()


__all__ = [
    "ProductManagerOutput",
    "approve_write_decision",
    "build_intake_request",
    "create_product_manager_agent",
    "edit_write_decision",
    "extract_pending_approval",
    "reject_write_decision",
    "resume_with_decision",
]
