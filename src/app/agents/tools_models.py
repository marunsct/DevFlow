"""Tools and Models Architect Deep Agent (Step 4.1).

This role worker consumes the approved product intake (from the Product
Manager) plus repository evidence, and produces an evidence-based comparison
of the frameworks, model providers, storage, and other technology choices the
project might use. The plan's gate for this step is explicit: "No
implementation dependency is added solely because the agent named it. The
choice must be approved and recorded." This agent only proposes and compares
options in a structured artifact; it never edits source code or installs
dependencies itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.role_agent import create_role_agent
from app.state import RepositoryContext

_STAGE = "tools_models"
_NAME = "tools_models_architect"


class TechnologyStack(BaseModel):
    """The unified technology stack for scaffolding the project."""

    model_config = ConfigDict(extra="forbid")

    language: str = Field(..., description="Primary programming language (e.g., TypeScript, Python).")
    framework: str = Field(..., description="Primary framework (e.g., React, NestJS, FastAPI).")
    database: str = Field(..., description="Database technology (e.g., PostgreSQL, MongoDB).")
    testing_framework: str = Field(..., description="Testing framework (e.g., Jest, Pytest).")
    additional_tools: list[str] = Field(default_factory=list, description="Other notable tools to scaffold.")


class TechnologyChoice(BaseModel):
    """One compared option for a technology category.

    Every field the plan requires for an evidence-based choice is captured
    explicitly, rather than leaving the comparison as free-form prose that a
    human would need to re-derive structure from.
    """

    model_config = ConfigDict(extra="forbid")

    category: str = Field(..., description="Technology category, e.g. 'framework' or 'model_provider'.")
    name: str = Field(..., description="The specific tool, framework, service, or model being evaluated.")
    capability: str = Field(..., description="What this option can actually do for the project.")
    compatibility: str = Field(..., description="How well it fits the existing repository and stack.")
    quality: str = Field(..., description="Known reliability, maturity, or output quality signals.")
    latency: str = Field(..., description="Expected responsiveness or throughput characteristics.")
    cost: str = Field(..., description="Pricing model and expected cost at relevant scale.")
    privacy: str = Field(..., description="Data handling, residency, or retention considerations.")
    licensing: str = Field(..., description="License terms and any usage restrictions.")
    operational_burden: str = Field(..., description="Ongoing maintenance, ops, or on-call cost.")
    alternative: str = Field(..., description="The next-best alternative considered.")
    replacement_criteria: str = Field(
        ..., description="What would need to change for this choice to be replaced later."
    )


class ToolsAndModelsOutput(BaseModel):
    """Structured technology comparison produced by the Tools and Models Architect.

    Each list covers one category named in the workflow plan. Leaving a list
    empty is valid when a category genuinely does not apply yet; the agent
    should not invent choices to fill every field.
    """

    model_config = ConfigDict(extra="forbid")

    frameworks: list[TechnologyChoice] = Field(default_factory=list)
    model_providers: list[TechnologyChoice] = Field(default_factory=list)
    storage_options: list[TechnologyChoice] = Field(default_factory=list)
    queue_and_job_systems: list[TechnologyChoice] = Field(default_factory=list)
    authentication: list[TechnologyChoice] = Field(default_factory=list)
    observability: list[TechnologyChoice] = Field(default_factory=list)
    testing_tools: list[TechnologyChoice] = Field(default_factory=list)
    deployment_options: list[TechnologyChoice] = Field(default_factory=list)
    technology_stack: TechnologyStack | None = Field(default=None, description="The chosen integrated stack.")
    open_questions: list[str] = Field(default_factory=list)


def build_tools_models_request(
    product_intake_text: str, repository: RepositoryContext
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input from the approved product intake and repo context.

    `product_intake_text` is expected to be the already-approved product
    intake artifact (e.g. the content behind `docs/generated/product-intake.md`),
    not a raw, unreviewed document — this role only starts after Step 3's
    intake artifact is approved.
    """
    brief = (
        f"Repository root: {repository.root_path} "
        f"(branch: {repository.branch}, commit: {repository.commit})\n\n"
        f"--- Approved product intake ---\n{product_intake_text}\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


_SYSTEM_PROMPT = """You are the Tools and Models Architect for this workflow.

Your role is to turn an approved product intake and repository evidence into an
evidence-based comparison of the technology choices this project might use.

Responsibilities:
- Compare frameworks, model providers and model roles, databases and storage,
  queue and job systems, authentication, observability, testing tools, and
  deployment options.
- For every choice, record capability, compatibility, quality, latency, cost,
  privacy, licensing, operational burden, an alternative, and replacement
  criteria — do not skip fields with vague filler text.
- Ground comparisons in the product intake and repository evidence (existing
  dependencies, language, and constraints); do not recommend a technology the
  repository evidence contradicts without explaining the trade-off.
- List open questions that block a confident choice instead of guessing.

Constraints:
- Do not modify application source code and do not install dependencies.
- Do not change repo files except through the approved artifact tool.
- No implementation dependency should be treated as decided just because you
  named it here; this artifact is a proposal for human approval.
- Only write your artifact inside the `docs/` folder.\n- Every write_artifact call pauses for a human decision before anything is
  saved; never claim the artifact is saved until a tool result confirms it.
- Keep the output structured and concise.

Return the response in the required output schema only.
"""


def create_tools_models_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
        allow_subdirectories: bool = True,
) -> Any:
    """Create the Tools and Models Architect role worker.

    Thin wrapper around `create_role_agent`, matching the pattern established
    by `create_product_manager_agent`.
    """
    return create_role_agent(
        name=_NAME,
        stage=_STAGE,
        system_prompt=_SYSTEM_PROMPT,
        response_format=ToolsAndModelsOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root, allow_subdirectories=allow_subdirectories,
    )


__all__ = [
    "TechnologyChoice",
    "TechnologyStack",
    "ToolsAndModelsOutput",
    "build_tools_models_request",
    "create_tools_models_agent",
]
