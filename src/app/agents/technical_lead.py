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
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agents.project_layout import PROJECT_LAYOUT, WORKSPACE_ROOT_NOTE
from app.agents.scope_discipline import SCOPE_DISCIPLINE
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE
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

    @field_validator("specialist_role", mode="before")
    @classmethod
    def _role_slug(cls, value: Any) -> Any:
        """Accept the role written the way a person writes it.

        A milestone plan is rejected whole, so "Backend Engineer" in one of six
        tasks loses the other five as well. See `app.agents.specialist_roles`;
        anything it cannot place is still refused.
        """
        from app.agents.specialist_roles import role_slug

        return role_slug(value)


class MilestonePlanOutput(BaseModel):
    """Structured milestone plan produced by the Technical Lead for one sprint."""

    model_config = ConfigDict(extra="forbid")

    selected_sprint_goal: str = Field(..., description="The single sprint goal this milestone covers.")
    milestone_scope: list[str] = Field(default_factory=list, description="What this milestone will actually deliver.")
    delegated_tasks: list[SpecialistTask] = Field(default_factory=list)
    integration_notes: list[str] = Field(
        default_factory=list,
        description=(
            "How the delegated pieces fit together once complete. Context only - never "
            "work. A change recorded here and not in `delegated_tasks` belongs to nobody "
            "and will not be made."
        ),
    )
    review_task_assignments: list[str] = Field(
        default_factory=list,
        description=(
            "When revising after a review, one line per requested change naming the "
            "delegated task that will make it, e.g. 'Add jest.setup.js polyfill -> task 3 "
            "(testing)'. Empty on a first plan. Purpose: a requested change that no task "
            "owns is a change nobody makes. Producer: Technical Lead. Consumer: the "
            "workflow, which refuses a revision that assigns nothing."
        ),
    )
    blockers: list[str] = Field(
        default_factory=list, description="Anything preventing this milestone from starting or completing."
    )

    @model_validator(mode="after")
    def _a_plan_assigns_something(self) -> "MilestonePlanOutput":
        """A milestone with scope and no tasks is not a plan.

        Measured on run-a7150a6c, whose fifth plan named a full scope - "Add
        event handlers and UI rendering for add, edit, delete, toggle in
        app.js; unit tests; documentation; encrypt data before saving" - and
        delegated nothing, with no blockers. The workflow accepted it, found no
        specialists to dispatch, and ran a test round, a security review and a
        milestone review on a milestone where nothing had been built: thirteen
        model calls before the lead was asked again and produced three tasks.

        Rejecting it here costs one model call and returns the validation error,
        which is the same conversation thirteen calls earlier.

        A milestone that genuinely cannot start is still allowed - it just has
        to say so in `blockers`, which is what that field is for.
        """
        if self.delegated_tasks or self.blockers:
            return self
        if not self.milestone_scope:
            return self
        raise ValueError(
            "This plan has a milestone scope and no delegated_tasks, so nobody "
            "will build any of it. Every item of scope needs a task with an "
            "owning specialist, or - if the milestone genuinely cannot start - "
            "a reason in `blockers`."
        )


def build_milestone_revision_request(
    previous_plan_json: str, comments: list[str]
) -> dict[str, list[dict[str, str]]]:
    """The revision request for a milestone plan sent back by a review.

    The generic revision prompt asks the agent to "address every requested
    change", and for a *plan* there is a way to do that which changes nothing:
    write it down. Measured on run-0b55ad49 - a review named the exact file,
    line and fix for a test-suite failure, the lead reproduced it verbatim under
    `## Integration Notes`, no delegated task mentioned it, and eighty minutes
    later the file was byte-for-byte unchanged. The relay worked; the assignment
    never happened.

    So the instruction here is not "address" but "assign": every requested
    change becomes a task with an owner, and the plan states which task took it.
    """
    from app.review import build_revision_prompt

    return {
        "messages": [
            {
                "role": "user",
                "content": build_revision_prompt(previous_plan_json, comments)
                + "\n\n"
                "HOW TO ADDRESS A REQUESTED CHANGE IN A PLAN:\n"
                "- Every requested change must become a DELEGATED TASK with an owning "
                "specialist and acceptance criteria. A plan is a list of assignments; "
                "writing a change into `integration_notes` assigns it to nobody and it "
                "will not be made.\n"
                "- If a change names an exact file, line or code, put that detail in the "
                "task itself. The specialist doing the work sees the task, not this "
                "conversation.\n"
                "- Fill `review_task_assignments` with one line per requested change "
                "naming the task that took it. If you cannot name a task for a change, "
                "you have not assigned it yet.\n"
                "- Fixing what the review raised comes before adding new work. Do not "
                "add new tests or features while a reported failure is unfixed.",
            }
        ]
    }


def _truncate(text: str, max_chars: int | None = None) -> str:
    """Truncate long text for local LLM context limits."""
    # Derived from the configured context window, not a fixed number: a
    # budget that does not move with the model is how every overflow in
    # this pipeline's history began.
    if max_chars is None:
        from app.agents.context_budget import ContextBudget

        max_chars = ContextBudget.resolve().document_budget_chars
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
        WORKSPACE_ROOT_NOTE
        + f"--- Approved sprint plan (/docs/sprint_plan.md) ---\n{_truncate(sprint_plan_text)}\n\n"
        f"You are now planning the milestone for this sprint: '{selected_sprint_goal}'.\n"
        "Draft the specialized tasks necessary to complete this specific sprint.\n\n"
        f"**CRITICAL INSTRUCTION**: All application code lives in ONE project directory at the workspace root. Run `ls` FIRST: if a project directory already exists, write into that exact directory, spelled exactly as it already is. Only create one if none exists, naming it after this product in lowercase-with-hyphens. Never scaffold directly in the workspace root, never use a generic name like 'nest-app', and never create a second project directory. All documentation goes in the `docs/` directory.\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


_SYSTEM_PROMPT = f"""You are the Technical Lead for this workflow.

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
- Every milestone must change what the product DOES. At least one delegated
  task must add or change application code that a user or a caller would
  notice. Creating directories, copying files and writing documentation are
  not deliverable work: the workspace and its project directory already exist,
  `docs/` is written by the workflow, and a milestone spent on them ships
  nothing. Measured on run-84e05d4b, where an entire milestone was "create the
  project directory", "copy the docs folder into it" and "initialise
  package.json" - 163 model calls, a test round, a security review and a
  milestone review, and the product had no application file at the end of it.
  The tests written for that milestone asserted that README.md contained a
  heading.
- Record blockers explicitly instead of silently assuming they are resolved.

{SCOPE_DISCIPLINE}

{PROJECT_LAYOUT}

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
- Do not write a document. The workflow renders `docs/milestone_plan.md` from the
  structured response you return, so your milestone plan reaches its readers
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
        # Its document is rendered from the structured response, so it needs no
        # write tool - see `app.agents.artifact_document`.
        can_write=False,
    )


__all__ = [
    "MilestonePlanOutput",
    "SpecialistRole",
    "SpecialistTask",
    "build_milestone_planning_request",
    "create_technical_lead_agent",
]
