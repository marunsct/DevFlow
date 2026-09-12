"""Technical Lead Deep Agent (Step 5.2).

This role worker selects exactly one sprint from the approved implementation
plan, defines a small milestone for it, and delegates only the specialist work
that sprint actually needs. Per the plan, the Technical Lead must not:
execute multiple unreviewed sprints at once, hide failing tests, change
approved architecture silently, accept undocumented assumptions, or grant a
specialist unrestricted access. Those constraints are stated in the system
prompt and reflected in the structured output shape (one sprint per milestone,
explicit blockers instead of silent assumptions).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.role_agent import create_role_agent

_STAGE = "implementation"
_NAME = "technical_lead"

SpecialistRole = Literal[
    "ui_ux",
    "database",
    "backend",
    "testing",
    "documentation",
    "security_reliability",
]
"""The six specialist roles this workflow supports (Step 5.3).

Defined once here (rather than in each specialist module) so the Technical
Lead's delegated tasks and the specialists themselves always agree on the set
of valid role names.
"""


class SpecialistTask(BaseModel):
    """One unit of delegated work for a single specialist."""

    model_config = ConfigDict(extra="forbid")

    specialist_role: SpecialistRole = Field(..., description="Which specialist should perform this task.")
    task_description: str = Field(..., description="The specific, scoped piece of work being delegated.")
    acceptance_criteria: list[str] = Field(default_factory=list)


class MilestonePlanOutput(BaseModel):
    """Structured milestone plan produced by the Technical Lead for one sprint."""

    model_config = ConfigDict(extra="forbid")

    selected_sprint_goal: str = Field(..., description="The single sprint goal this milestone covers.")
    milestone_scope: list[str] = Field(default_factory=list, description="What this milestone will actually deliver.")
    delegated_tasks: list[SpecialistTask] = Field(default_factory=list)
    integration_notes: list[str] = Field(
        default_factory=list, description="How the delegated pieces fit together once complete."
    )
    blockers: list[str] = Field(
        default_factory=list, description="Anything preventing this milestone from starting or completing."
    )


def _truncate(text: str, max_chars: int = 80_000) -> str:
    """Truncate long text for local LLM context limits."""
    text = str(text or "")
    if len(text) <= max_chars:
        return text
    split = int(max_chars * 0.6)
    return (
        text[:split]
        + f"\n\n--- TRUNCATED ({len(text) - split} chars removed for context limits) ---\n\n"
        + text[len(text) - (max_chars - split):]
    )


def build_milestone_planning_request(
    sprint_plan_text: str, selected_sprint_goal: str, repository_root: str
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input for planning one milestone from the approved sprint plan."""
    brief = (
        f"Repository root: {repository_root}\n\n"
        f"--- Approved sprint plan ---\n{_truncate(sprint_plan_text)}\n\n"
        f"You are now planning the milestone for this sprint: '{selected_sprint_goal}'.\n"
        "Draft the specialized tasks necessary to complete this specific sprint.\n\n"
        f"**CRITICAL INSTRUCTION**: Ensure all tasks strictly instruct specialists to write application code inside a directory named after the app (e.g. `thehub/` for 'The Hub') and not in generic directories like 'nest-app' or directly in the repository root. All documentation must be placed in the `docs/` directory.\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


_SYSTEM_PROMPT = """You are the Technical Lead for this workflow.

Your role is to select exactly one sprint from the approved plan, define a
small milestone for it, and delegate only the specialist work that sprint
actually needs.

Responsibilities:
- Select exactly one sprint goal for this milestone; do not plan multiple
  sprints in the same milestone.
- Delegate tasks only to the specialist roles that sprint requires: ui_ux,
  database, backend, testing, documentation, security_reliability.
- Give each delegated task a highly granular, scoped description and explicit acceptance
  criteria a Milestone Reviewer can check. You MUST instruct specialists to write complete,
  executable code and explicitly mandate that they compile/verify their code using terminal commands.
- Record blockers explicitly instead of silently assuming they are resolved.

Constraints:
- Do not execute or plan more than one sprint at a time.
- Do not hide or downplay failing tests; if tests are failing, that is a
  blocker, not something to omit.
- Do not change approved architecture decisions; if the sprint reveals a
  needed architecture change, record it as a blocker for human review instead
  of changing it yourself.
- Do not grant a specialist access beyond their delegated task.
- Do not modify application source code yourself.
- Do not change repo files except through the approved artifact tool.
- Write exactly one artifact, at `docs/milestone_plan.md`. Use that path verbatim so the
  filename is the same on every run and later stages can find it.
- Every write_artifact call pauses for a human decision before anything is
  saved; never claim the artifact is saved until a tool result confirms it.
- **Write the complete artifact in ONE single write_artifact call.** Do NOT
  make follow-up edit calls to refine, fix typos, or improve the document after
  the initial write. The document must be complete and correct before you write
  it. Once the write is confirmed, immediately return your structured response.
- Keep the output structured and concise.

Return the response in the required output schema only.
"""


def create_technical_lead_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
        allow_subdirectories: bool = True,
) -> Any:
    """Create the Technical Lead role worker."""
    return create_role_agent(
        name=_NAME,
        stage=_STAGE,
        system_prompt=_SYSTEM_PROMPT,
        response_format=MilestonePlanOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root, allow_subdirectories=allow_subdirectories,
    )


__all__ = [
    "MilestonePlanOutput",
    "SpecialistRole",
    "SpecialistTask",
    "build_milestone_planning_request",
    "create_technical_lead_agent",
]
