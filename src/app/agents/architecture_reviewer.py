"""Senior Architect Reviewer Deep Agent (Step 4.3).

This role worker independently reviews the Principal Architect's technical
specification and ADRs for completeness, feasibility, security, operability,
and unjustified assumptions. Its output is a structured decision, never free
text, so the LangGraph controller can route rejected work back to the
Principal Architect and approved work forward to sprint planning without
having to parse prose. The plan's gate is explicit: "Free-form text cannot
bypass the review gate."
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.role_agent import create_role_agent

_STAGE = "architecture_review"
_NAME = "senior_architect_reviewer"


class ArchitectureReviewFinding(BaseModel):
    """One specific issue found while reviewing the technical specification."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["blocking", "major", "minor", "informational"] = Field(
        ..., description="How serious this finding is for release readiness."
    )
    description: str = Field(..., description="What is wrong or missing.")
    evidence: str = Field(..., description="The specific spec section, ADR, or repository fact supporting this finding.")
    required_remediation: str = Field(
        ..., description="What the Principal Architect must change to resolve this finding."
    )


class ArchitectureReviewOutput(BaseModel):
    """Structured review decision produced by the Senior Architect Reviewer.

    `status` is the single field the workflow controller should route on.
    Approval with only minor/informational findings is allowed; any
    `blocking` or `major` finding must force `changes_required`, which the
    system prompt below states explicitly so the model cannot approve around
    its own findings.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["approved", "changes_required"] = Field(
        ..., description="Routing decision: forward to sprint planning, or back to the Principal Architect."
    )
    findings: list[ArchitectureReviewFinding] = Field(default_factory=list)
    approval_conditions: list[str] = Field(
        default_factory=list, description="Conditions that must hold for this approval to remain valid."
    )
    accepted_risks: list[str] = Field(
        default_factory=list, description="Risks knowingly accepted rather than blocking approval on."
    )


def build_architecture_review_request(
    technical_specification_text: str, repository_root: str
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input from the specification text awaiting review.

    The specification is budgeted. It is the largest artifact in the pipeline
    and it arrives in the *first* user message, which is the one case
    compaction cannot rescue: with nothing older in the conversation, the
    summariser has nothing to evict and the call simply overflows.
    """
    from app.agents.text_budget import excerpt, specification_budget

    specification = excerpt(
        technical_specification_text,
        specification_budget(),
        what="technical specification",
    )
    brief = (
        f"Repository root: {repository_root}\n\n"
        f"--- Technical specification and ADRs under review ---\n{specification}\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


_SYSTEM_PROMPT = """You are the Senior Architect Reviewer for this workflow.

Your role is to independently review the Principal Architect's technical
specification and ADRs for completeness, feasibility, security, operability,
and unjustified assumptions.

Responsibilities:
- Identify findings with a severity of blocking, major, minor, or informational.
- Cite the specific spec section, ADR, or repository evidence for each finding.
- State the required remediation for every finding.
- Set status to "changes_required" if any finding is blocking or major. Only
  use "approved" when no blocking or major finding remains.
- Record any risk you are knowingly accepting rather than blocking on, and any
  condition that must remain true for your approval to stand.

Constraints:
- Do not modify application source code or the specification itself; you only
  review it and record findings.
- Do not change repo files except through the approved artifact tool.
- Never approve based only on the Principal Architect's own confidence
  statements; approval must be grounded in what you actually verified.
- Every write_artifact call pauses for a human decision before anything is
  saved; never claim the artifact is saved until a tool result confirms it.
- Keep the output structured and concise.

Return the response in the required output schema only.
"""


def create_architecture_reviewer_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
        allow_subdirectories: bool = True,
) -> Any:
    """Create the Senior Architect Reviewer role worker."""
    return create_role_agent(
        name=_NAME,
        stage=_STAGE,
        system_prompt=_SYSTEM_PROMPT,
        response_format=ArchitectureReviewOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root, allow_subdirectories=allow_subdirectories,
    )


__all__ = [
    "ArchitectureReviewFinding",
    "ArchitectureReviewOutput",
    "build_architecture_review_request",
    "create_architecture_reviewer_agent",
]
