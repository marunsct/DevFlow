"""Specialist Deep Agents (Step 5.3).

The Technical Lead (Step 5.2) delegates scoped tasks to one of six specialist
roles: UI/UX, database, backend, testing and quality engineering,
documentation, and security/reliability. Every specialist returns the same
shape — changed files, decisions, tests, documentation, risks, and blockers —
so the Technical Lead and Milestone Reviewer can process any specialist's
output the same way. Each specialist receives only the task and context it
needs; none of them can edit files outside the approved artifact directory
without a human approval (see `app.agents.role_agent`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.role_agent import create_role_agent, default_repo_root
from app.agents.technical_lead import SpecialistRole
from app.tools.agent_toolkit import build_validation_tool

_STAGE = "implementation"

_ROLE_DESCRIPTIONS: dict[SpecialistRole, str] = {
    "ui_ux": (
        "You are the UI and UX specialist. You design and describe user-facing "
        "workflows, accessibility, and responsive states for the delegated task."
    ),
    "database": (
        "You are the Database specialist. You design schemas, migrations, "
        "indexes, and ownership/tenant isolation for the delegated task."
    ),
    "backend": (
        "You are the Backend specialist. You design services, APIs, "
        "authorization, and domain state transitions for the delegated task."
    ),
    "testing": (
        "You are the Testing and Quality Engineering specialist. You define and "
        "run unit, integration, contract, end-to-end, accessibility, and "
        "security regression tests for the delegated task. Use the validation "
        "tool to actually run tests rather than only describing them. Report "
        "every failure as a structured defect in the `defects` field, naming "
        "the specialist role that must fix it, so the workflow can track and "
        "route it."
    ),
    "documentation": (
        "You are the Documentation specialist. You write beginner-readable "
        "explanations, ADR usage docs, and operational runbooks for the "
        "delegated task."
    ),
    "security_reliability": (
        "You are the Security and Reliability specialist. You review "
        "authorization, data isolation, secrets handling, retries, and "
        "observability for the delegated task."
    ),
}


class ReportedDefect(BaseModel):
    """One test failure, as reported by the Testing specialist (Step 5.4).

    This is the *agent-facing* defect shape, deliberately separate from
    `app.sprint.Defect`, which is the controller's tracking record. The
    difference matters: `Defect` also carries lifecycle fields (`status`,
    `regression_test`, `accepted_risk_reason`) that only the workflow may set.
    Exposing those to the model would let it declare its own defects fixed.

    `owner` is typed as `SpecialistRole` rather than a free string so the model
    must name one of the six real specialists. The plan's gate forbids
    accepting a sprint with unowned defects, and a defect owned by "the team"
    or "backend service" is exactly that - unroutable.
    """

    model_config = ConfigDict(extra="forbid")

    description: str = Field(..., description="Short summary of what is wrong.")
    severity: Literal["blocking", "major", "minor"] = Field(..., description="Impact level of this failure.")
    reproduction_steps: str = Field(..., description="How to reliably reproduce the failure.")
    expected_behavior: str = Field(..., description="What should have happened.")
    actual_behavior: str = Field(..., description="What actually happened.")
    affected_files: list[str] = Field(default_factory=list, description="Files implicated in this failure.")
    owner: SpecialistRole = Field(..., description="Which specialist role must fix this defect.")
    regression_test_required: bool = Field(
        default=True,
        description="Whether closing this defect requires a new or updated regression test. Normally true.",
    )


class SpecialistOutput(BaseModel):
    """Structured result every specialist returns, regardless of role.

    One shared shape lets the Technical Lead and Milestone Reviewer integrate
    results from any specialist without role-specific parsing logic.
    """

    model_config = ConfigDict(extra="forbid")

    changed_files: list[str] = Field(
        default_factory=list,
        description="Files this specialist changed or proposes to change (paths only; actual edits go through review).",
    )
    decisions: list[str] = Field(default_factory=list, description="Notable decisions made while doing this task.")
    tests: list[str] = Field(default_factory=list, description="Tests added, updated, or run for this task.")
    documentation: list[str] = Field(default_factory=list, description="Documentation added or updated for this task.")
    risks: list[str] = Field(default_factory=list, description="Risks introduced or discovered by this task.")
    blockers: list[str] = Field(default_factory=list, description="Anything preventing this task from being completed.")
    defects: list[ReportedDefect] = Field(
        default_factory=list,
        description=(
            "Test failures found during this task. Only the testing specialist normally fills this in; "
            "every other role should leave it empty and use `blockers` instead."
        ),
    )


def build_specialist_task_request(
    task_description: str, acceptance_criteria: list[str], repository_root: str
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input for one delegated specialist task."""
    criteria_text = "\n".join(f"- {criterion}" for criterion in acceptance_criteria)
    brief = (
        f"Repository root: {repository_root}\n\n"
        f"--- Delegated task ---\n{task_description}\n\n"
        f"--- Acceptance criteria ---\n{criteria_text}\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


def build_test_run_request(
    milestone_goal: str, changed_files: list[str], repository_root: str
) -> dict[str, list[dict[str, str]]]:
    """Build the Testing specialist's input for one verification round (Step 5.4).

    This is the loop's step 2, "the Test Engineer runs the tests applicable to
    that increment", and it is a separate invocation from the testing task the
    Technical Lead may have delegated during implementation. Every failure it
    finds must come back as a structured `ReportedDefect` so the controller can
    track and route it, rather than as prose in `blockers` that nothing can act
    on.
    """
    files_text = "\n".join(f"- {name}" for name in changed_files) or "- (none reported)"
    brief = (
        f"Repository root: {repository_root}\n\n"
        f"--- Milestone under test ---\n{milestone_goal}\n\n"
        f"--- Files changed in this milestone ---\n{files_text}\n\n"
        "Run the unit, integration, contract, end-to-end, accessibility, and security "
        "tests that apply to this increment. Use the run_validation tool to actually "
        "execute them.\n\n"
        "Report EVERY failure in the `defects` field, each with a severity, reproduction "
        "steps, expected behavior, actual behavior, affected files, and the specialist "
        "role that must fix it. If everything passes, return an empty `defects` list."
    )
    return {"messages": [{"role": "user", "content": brief}]}


def build_defect_fix_request(
    description: str,
    reproduction_steps: str,
    expected_behavior: str,
    actual_behavior: str,
    affected_files: list[str],
    regression_test_required: bool,
    repository_root: str,
) -> dict[str, list[dict[str, str]]]:
    """Build the input that routes one tracked defect to the specialist who owns it.

    This is the loop's steps 4 and 5: the Technical Lead routes the defect, and
    the owning specialist fixes it *and* adds a regression test. The regression
    test is not optional politeness - the plan's gate refuses to accept a sprint
    with missing regression coverage, so the request states that requirement
    explicitly and the specialist must name the test in its `tests` field.
    """
    files_text = "\n".join(f"- {name}" for name in affected_files) or "- (none identified)"
    regression_clause = (
        "You MUST also add or update a regression test that fails before your fix and "
        "passes after it, and name that test in your `tests` field. A fix with no named "
        "regression test cannot be accepted."
        if regression_test_required
        else "A regression test is not required for this defect, but name any test you did run."
    )
    brief = (
        f"Repository root: {repository_root}\n\n"
        "A test failure has been assigned to you to fix.\n\n"
        f"--- Defect ---\n{description}\n\n"
        f"--- Reproduction steps ---\n{reproduction_steps}\n\n"
        f"--- Expected behavior ---\n{expected_behavior}\n\n"
        f"--- Actual behavior ---\n{actual_behavior}\n\n"
        f"--- Affected files ---\n{files_text}\n\n"
        f"{regression_clause}\n\n"
        "Fix only this defect. If you cannot fix it, say why in `blockers` rather than "
        "claiming it is resolved."
    )
    return {"messages": [{"role": "user", "content": brief}]}


def _system_prompt(role: SpecialistRole) -> str:
    """Build the full system prompt for one specialist role."""
    role_description = _ROLE_DESCRIPTIONS[role]
    return f"""{role_description}

Responsibilities:
- Complete only the delegated task and its stated acceptance criteria; do not
  expand scope on your own initiative.
- Report every changed file, notable decision, added or updated test, added or
  updated documentation, risk, and blocker.
- If you cannot verify something (a test, a security property), say so as a
  risk or blocker instead of asserting it is fine.

Beginner documentation requirement:
- Any non-obvious code or configuration you describe must explain purpose,
  inputs, outputs, control flow, failure behavior, and security assumptions in
  your `documentation` field or inline comments you propose.

Constraints:
- Do not change repo files except through the approved artifact tool.
- Every write_artifact call pauses for a human decision before anything is
  saved; never claim the artifact is saved until a tool result confirms it.
- Keep the output structured and concise.

Return the response in the required output schema only.
"""


def create_specialist_agent(
    role: SpecialistRole,
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
) -> Any:
    """Create one specialist role worker.

    The `testing` specialist gets one extra tool (`run_validation`) so it can
    actually execute an allowlisted test command instead of only describing
    what should be tested; every other specialist gets the same narrow
    read/write tools as any other role agent.
    """
    resolved_repo_root = str(repo_root) if repo_root is not None else str(default_repo_root())
    extra_tools = [build_validation_tool(resolved_repo_root)] if role == "testing" else None

    return create_role_agent(
        name=f"specialist_{role}",
        stage=_STAGE,
        system_prompt=_system_prompt(role),
        response_format=SpecialistOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root,
        extra_tools=extra_tools,
    )


__all__ = [
    "ReportedDefect",
    "SpecialistOutput",
    "build_defect_fix_request",
    "build_specialist_task_request",
    "build_test_run_request",
    "create_specialist_agent",
]
