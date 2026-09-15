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
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.structured_response import STRUCTURED_RESPONSE_RULE
from app.agents.role_agent import create_role_agent
from app.state import RepositoryContext

_STAGE = "tools_models"
_NAME = "tools_models_architect"


class TechnologyStack(BaseModel):
    """The unified technology stack for scaffolding the project."""

    model_config = ConfigDict(extra="forbid")

    language: str = Field(..., description="Primary programming language (e.g., TypeScript, Python).")
    framework: str = Field(
        ...,
        description=(
            "The framework the backend or, for a client-only product, the "
            "application itself is built on."
        ),
    )
    # Optional so a checkpoint written before this field existed still loads,
    # and so a client-only product is not made to invent a backend.
    frontend_framework: str = Field(
        default="",
        description=(
            "The framework the user interface is built on, when the product has "
            "one that is chosen separately from the backend. Leave empty only "
            "when there is genuinely no separate frontend."
        ),
    )
    database: str = Field(..., description="Database technology (e.g., PostgreSQL, MongoDB).")
    testing_framework: str = Field(..., description="Testing framework (e.g., Jest, Pytest).")
    additional_tools: list[str] = Field(default_factory=list, description="Other notable tools to scaffold.")

    @field_validator("testing_framework")
    @classmethod
    def _must_be_runnable(cls, value: str) -> str:
        """Reject a testing approach nothing in this environment can perform.

        There is no browser in the sandbox, none on any role's allowlist, and no
        human watching the workspace, so "manual browser testing" is not a
        testing approach here - it is the absence of one. Every stage that later
        asks "did the tests pass?" gets no answer, and the milestone reviewer
        treats an absent test run as a blocking finding.

        Stated in the stack selector's prompt first, including the sentence
        "'Manual browser testing' cannot be carried out here by anyone". On
        run-78804673 the selector read that and chose "Manual browser testing"
        anyway. An instruction that has failed twice is not made truer by
        repetition; this removes the option instead.

        The message names what to do, because a validation error is what the
        model sees when it retries.
        """
        text = (value or "").strip()
        lowered = text.lower()
        impossible = ("manual", "by hand", "devtools", "browser testing", "visual inspection")
        if any(marker in lowered for marker in impossible):
            raise ValueError(
                f"'{text}' cannot be carried out in this environment: there is no "
                "browser, no display, and no person watching the workspace, so "
                "nothing can perform a manual or visual check. Choose something "
                "that runs headless and reports a pass or fail. `node --test` and "
                "Python's `unittest` are built into their runtimes: they install "
                "nothing, add no dependency, and cost no lines of product code."
            )
        # "None" is the same answer wearing a shorter word, and the previous
        # version of this message licensed it outright: it ended "'none' is
        # valid only if the product genuinely needs no verification". On
        # run-2f252e4e the selector answered "None", citing the size guidance
        # that warns against *installed* runners, and shipped a human checklist
        # instead of a test suite. A built-in runner costs nothing, so there is
        # no product here that needs no verification.
        if not text or lowered in ("none", "n/a", "na", "no testing", "nothing", "-"):
            raise ValueError(
                "A testing framework is required. `node --test` and Python's "
                "`unittest` are part of their runtimes - nothing to install, no "
                "dependency, no lines of product code - so choosing none only "
                "means nothing will ever answer 'did this work?'. Name the "
                "runner the project will actually use."
            )
        return text



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


def _truncate_for_llm(text: str, max_chars: int | None = None) -> str:
    """Truncate long text for local LLM context limits.

    Local models (7B-35B params) typically have 8K-32K token windows. After
    accounting for the system prompt (~2KB), tool definitions, and output
    tokens, we need to keep input well under that ceiling. This function
    preserves the beginning and end of long documents so reviewers can still
    see the structure and conclusion even if the middle is truncated.
    """
    # Derived from the configured context window, not a fixed number: a
    # budget that does not move with the model is how every overflow in
    # this pipeline's history began.
    if max_chars is None:
        from app.agents.context_budget import ContextBudget

        max_chars = ContextBudget.resolve().document_budget_chars
    text = str(text or "")
    if len(text) <= max_chars:
        return text
    # Keep first 60% and last 40% with a visible truncation marker
    split = int(max_chars * 0.6)
    return (
        text[:split]
        + f"\n\n--- TRUNCATED ({len(text) - split} chars removed for context limits) ---\n\n"
        + text[len(text) - (max_chars - split):]
    )


def build_tools_models_request(
    product_intake_text: str, repository: RepositoryContext
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input from the approved product intake and repo context.

    `product_intake_text` is expected to be the already-approved product
    intake artifact (the content behind `docs/product_intake.md`),
    not a raw, unreviewed document — this role only starts after Step 3's
    intake artifact is approved.
    """
    # Truncate oversized inputs to prevent context overflow on local LLMs
    truncated_intake = _truncate_for_llm(product_intake_text)
    
    brief = (
        # Deliberately not the repository's absolute path. That is the HOST's
        # path; inside the agent the workspace is rooted at "/". Quoting it here
        # and then telling the agent never to use it does not work - measured on
        # run-0b55ad49, agents retried `ls` against that exact string four times
        # in a row, and fed it to shell commands, every attempt failing with
        # path_not_found. The reliable fix is not to show it.
        f"Repository: branch {repository.branch}, commit {repository.commit}\n"
        f"The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        f"--- Approved product intake (/docs/product_intake.md) ---\n{truncated_intake}\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


_SYSTEM_PROMPT = f"""You are the Tools and Models Architect for this workflow.

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
- Do not write a document. The workflow renders `docs/tools_and_models.md` from the
  structured response you return, so your comparison reaches its readers
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
        # Its document is rendered from the structured response, so it needs no
        # write tool - see `app.agents.artifact_document`.
        can_write=False,
    )


__all__ = [
    "TechnologyChoice",
    "TechnologyStack",
    "ToolsAndModelsOutput",
    "build_tools_models_request",
    "create_tools_models_agent",
]
