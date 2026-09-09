"""Scrum Master Deep Agent (Step 5.1).

This role worker consumes the approved technical specification and turns it
into an implementation plan made of independently verifiable sprints. Per the
plan: "Do not plan all implementation details before architecture approval" —
this agent should only be invoked after the Senior Architect Reviewer has
returned `status == "approved"`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.role_agent import create_role_agent

_STAGE = "sprint_planning"
_NAME = "scrum_master"


class SprintDefinition(BaseModel):
    """One independently verifiable sprint in the implementation plan."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(..., description="The user-facing outcome this sprint delivers.")
    user_value: str = Field(..., description="Why this outcome matters to a real user or stakeholder.")
    in_scope: list[str] = Field(default_factory=list, description="Work explicitly included in this sprint.")
    out_of_scope: list[str] = Field(default_factory=list, description="Work explicitly deferred to a later sprint.")
    dependencies: list[str] = Field(default_factory=list, description="Other sprints or external work this depends on.")
    acceptance_criteria: list[str] = Field(default_factory=list)
    test_strategy: list[str] = Field(default_factory=list, description="How this sprint's work will be verified.")
    security_checks: list[str] = Field(default_factory=list)
    documentation_work: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    rollback_notes: str = Field(default="", description="How to recover if this sprint's work needs to be reverted.")


class SprintPlanOutput(BaseModel):
    """Structured implementation plan produced by the Scrum Master."""

    model_config = ConfigDict(extra="forbid")

    sprints: list[SprintDefinition] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


def build_sprint_planning_request(
    technical_specification_text: str, repository_root: str
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input from the approved technical specification."""
    brief = (
        f"Repository root: {repository_root}\n\n"
        f"--- Approved technical specification ---\n{technical_specification_text}\n\n"
        f"**CRITICAL INSTRUCTION**: Ensure all tasks and specialists are aware that projects must be scaffolded strictly inside a directory named after the app (e.g. `thehub/` for 'The Hub') and not in generic directories like 'nest-app' or directly in the repository root. All documentation must be created in the `docs/` directory.\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


_SYSTEM_PROMPT = """You are the Scrum Master for this workflow.

Your role is to turn an approved technical specification into an implementation
plan made of independently verifiable sprints.

Responsibilities:
- Break the approved specification into sprints that each deliver real user
  value on their own, rather than one sprint per technical layer.
- For every sprint, define goal, user value, in-scope and out-of-scope work,
  dependencies on other sprints, acceptance criteria, test strategy, security
  checks, documentation work, risks, and rollback or recovery notes.
- Sequence sprints so each one is verifiable before the next begins.
- List open questions instead of guessing when the specification is silent.

Constraints:
- Do not modify application source code.
- Do not change repo files except through the approved artifact tool.
- Only plan against the already-approved specification; do not introduce new
  architecture decisions here.
- Only write your artifact inside the `docs/` folder.\n- Every write_artifact call pauses for a human decision before anything is
  saved; never claim the artifact is saved until a tool result confirms it.
- Keep the output structured and concise.

Return the response in the required output schema only.
"""


def create_scrum_master_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
        allow_subdirectories: bool = True,
) -> Any:
    """Create the Scrum Master role worker."""
    return create_role_agent(
        name=_NAME,
        stage=_STAGE,
        system_prompt=_SYSTEM_PROMPT,
        response_format=SprintPlanOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root, allow_subdirectories=allow_subdirectories,
    )


__all__ = [
    "SprintDefinition",
    "SprintPlanOutput",
    "build_sprint_planning_request",
    "create_scrum_master_agent",
]
