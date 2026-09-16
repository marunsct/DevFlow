"""Scrum Master Deep Agent (Step 5.1).

This role worker consumes the approved technical specification and turns it
into an implementation plan made of independently verifiable sprints. Per the
plan: "Do not plan all implementation details before architecture approval" —
this agent should only be invoked after the Senior Architect Reviewer has
returned `status == "approved"`.
"""

from __future__ import annotations

from app.agents.project_layout import WORKSPACE_ROOT_NOTE

from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.scope_discipline import SCOPE_DISCIPLINE
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE
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
    """Build the Deep Agent input from the approved technical specification.

    Budgeted for the same reason as the architecture review request: this is a
    first message, so compaction cannot save it if the specification alone
    exceeds the window.
    """
    from app.agents.text_budget import excerpt, specification_budget

    specification = excerpt(
        technical_specification_text,
        specification_budget(),
        what="approved technical specification",
    )
    brief = (
        WORKSPACE_ROOT_NOTE
        + f"--- Approved technical specification (/docs/technical_specification.md) ---\n{specification}\n\n"
        f"**CRITICAL INSTRUCTION**: All application code lives in ONE project directory at the workspace root. Run `ls` FIRST: if a project directory already exists, write into that exact directory, spelled exactly as it already is. Only create one if none exists, naming it after this product in lowercase-with-hyphens. Never scaffold directly in the workspace root, never use a generic name like 'nest-app', and never create a second project directory. All documentation goes in the `docs/` directory.\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


_SYSTEM_PROMPT = f"""You are the Scrum Master for this workflow.

Your role is to turn an approved technical specification into an implementation
plan made of independently verifiable sprints.

Responsibilities:
- Break the approved specification into sprints that each deliver real user
  value on their own, rather than one sprint per technical layer.
- Never make setup a sprint of its own. The workspace, its project directory
  and the `docs/` folder already exist and the workflow maintains them, so
  "create the project directory", "copy the documentation" and "initialise the
  manifest" deliver nothing a user could use. Measured on run-84e05d4b, whose
  first sprint was "Create project directory and basic documentation": the run
  spent a full milestone, a test round, a security review, a milestone review
  and two remediation rounds on it, and the product had no application code at
  the end. The first sprint must ship working behaviour; any manifest or
  directory it needs is part of that sprint, not instead of it.
- For every sprint, define goal, user value, in-scope and out-of-scope work,
  dependencies on other sprints, acceptance criteria, test strategy, security
  checks, documentation work, risks, and rollback or recovery notes.
- Sequence sprints so each one is verifiable before the next begins.
- List open questions instead of guessing when the specification is silent.

{SCOPE_DISCIPLINE}

Constraints:
- Do not modify application source code.
- Do not change repo files except through the approved artifact tool.
- Only plan against the already-approved specification; do not introduce new
  architecture decisions here.
- Do not write a document. The workflow renders `docs/sprint_plan.md` from the
  structured response you return, so your sprint plan reaches its readers
  either way - and only through that response. Writing it yourself
  produces the same work twice from one understanding, and the two
  copies then disagree.
- Every write_artifact call pauses for a human decision before anything is
  saved; never claim the artifact is saved until a tool result confirms it.
- **Write the complete artifact in ONE single write_artifact call.** Do NOT
  make follow-up edit calls to refine, fix typos, or improve the document after
  the initial write. The document must be complete and correct before you write
  it. Once the write is confirmed, immediately return your structured response.
- Keep the output structured and concise.

Return the response in the required output schema only.

{STRUCTURED_RESPONSE_RULE}
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
        # Its document is rendered from the structured response, so it needs no
        # write tool - see `app.agents.artifact_document`.
        can_write=False,
    )


__all__ = [
    "SprintDefinition",
    "SprintPlanOutput",
    "build_sprint_planning_request",
    "create_scrum_master_agent",
]
