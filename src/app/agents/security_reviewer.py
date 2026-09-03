"""Security Reviewer Deep Agent.

This role worker independently reviews changes for security and reliability
issues. It can be invoked by the milestone reviewer or used standalone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.role_agent import create_role_agent

_STAGE = "security_review"
_NAME = "security_reviewer"


class SecurityFinding(BaseModel):
    """One specific security or reliability issue found."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["critical", "high", "medium", "low", "info"] = Field(
        ..., description="How serious this finding is."
    )
    category: Literal[
        "isolation",
        "permissions",
        "data_leakage",
        "secrets",
        "external_integration",
        "filesystem",
        "command_execution",
        "timeouts",
        "checkpoint_recovery",
        "audit_trail",
        "retention",
    ] = Field(..., description="The category of security or reliability issue.")
    description: str = Field(..., description="What is wrong or missing.")
    affected_files: list[str] = Field(
        default_factory=list, description="Files implicated in this finding."
    )
    remediation: str = Field(
        ..., description="What must be changed to resolve this finding."
    )


class SecurityReviewOutput(BaseModel):
    """Structured review decision produced by the Security Reviewer."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["passed", "findings"] = Field(
        ..., description="Routing decision: passed or findings exist."
    )
    findings: list[SecurityFinding] = Field(default_factory=list)
    local_only_exceptions: list[str] = Field(
        default_factory=list, description="Documented exceptions for local-only features."
    )


def build_security_review_request(
    changed_files: list[str],
    tool_permissions: str,
    repository_root: str,
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input for a security review."""
    files_text = "\n".join(f"- {name}" for name in changed_files) or "- (none reported)"
    brief = (
        f"Repository root: {repository_root}\n\n"
        f"--- Changed files under review ---\n{files_text}\n\n"
        f"--- Tool permissions context ---\n{tool_permissions}\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


_SYSTEM_PROMPT = """You are the Security Reviewer for this workflow.

Your role is to independently review changed files and tool permissions for
security and reliability issues.

Responsibilities:
- Identify findings with a severity of critical, high, medium, low, or info.
- Categorize each finding properly (e.g. isolation, secrets, command_execution).
- State the remediation for every finding.
- Set status to "findings" if any issues are identified, else "passed".
- Document any valid exceptions for local-only features in `local_only_exceptions`.

Constraints:
- Do not modify application source code; you only review and record findings.
- Keep the output structured and concise.

Return the response in the required output schema only.
"""


def create_security_reviewer_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
) -> Any:
    """Create the Security Reviewer role worker."""
    return create_role_agent(
        name=_NAME,
        stage=_STAGE,
        system_prompt=_SYSTEM_PROMPT,
        response_format=SecurityReviewOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root,
    )


__all__ = [
    "SecurityFinding",
    "SecurityReviewOutput",
    "build_security_review_request",
    "create_security_reviewer_agent",
]
