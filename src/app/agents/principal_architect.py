"""Principal Architect Deep Agent (Step 4.2).

This role worker consumes the approved product intake and the approved
tools-and-models comparison, then produces a technical specification plus
architecture decision records (ADRs). It defines component boundaries, data
flows, and acceptance criteria, and records the rationale behind every
material decision so a later reviewer or specialist does not have to guess why
a choice was made.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.role_agent import create_role_agent
from app.state import RepositoryContext

logger = logging.getLogger(__name__)

_STAGE = "architecture"
_NAME = "principal_architect"


class ArchitectureDecisionRecord(BaseModel):
    """One durable architecture decision, in the classic ADR shape.

    Capturing alternatives and trade-offs (not just the final decision) is
    what makes an ADR useful later: a reviewer or future maintainer can see
    why the road not taken was rejected, instead of only seeing the outcome.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., description="Short, specific name for the decision.")
    context: str = Field(..., description="The situation and constraints that made a decision necessary.")
    alternatives: list[str] = Field(default_factory=list, description="Other options that were considered.")
    decision: str = Field(..., description="The option that was chosen.")
    rationale: str = Field(..., description="Why this option was chosen over the alternatives.")
    trade_offs: list[str] = Field(default_factory=list, description="Known downsides accepted with this decision.")
    consequences: list[str] = Field(
        default_factory=list, description="Follow-on effects this decision has on other parts of the system."
    )
    validation_evidence: str = Field(
        default="", description="Evidence (tests, benchmarks, prior art) supporting this decision, if any."
    )


class TechnicalSpecificationOutput(BaseModel):
    """Structured technical specification produced by the Principal Architect.

    Field names mirror the sections the workflow plan requires so a reviewer
    can check completeness mechanically before reading for quality.
    """

    model_config = ConfigDict(extra="forbid")

    product_scope: str = Field(..., description="What this release covers and explicitly defers.")
    component_boundaries: list[str] = Field(default_factory=list)
    domain_model: list[str] = Field(default_factory=list)
    api_and_event_contracts: list[str] = Field(default_factory=list)
    data_flows: list[str] = Field(default_factory=list)
    security_and_privacy: list[str] = Field(default_factory=list)
    reliability_and_observability: list[str] = Field(default_factory=list)
    testing: list[str] = Field(default_factory=list)
    deployment: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    decisions: list[ArchitectureDecisionRecord] = Field(
        default_factory=list, description="Every material decision made while producing this specification."
    )


from app.documents import DocumentContent

REVISION_DOCUMENT_BUDGET = 80_000
"""Characters of the original upload to carry into a *revision* request.

A revision is a targeted edit, not a fresh reading of the brief. It already
carries the previous specification, the approved intake (which is the product
manager's distillation of these very documents) and the reviewer's findings, so
re-sending the whole corpus mostly displaces the parts the architect needs.

Measured on a real run: the uploaded documents were 96% of a ~35k-token first
request and 90% of a ~38k-token revision. The architect responded with a
structured specification whose sections were empty even though it had written a
complete 215-line document to disk - the signature of a structured output
generated with almost no room left.

Reduced from 20,000 because revisions are iterative refinements — the architect
already has the full spec and knows what to change. The intake document is the
authoritative source of truth; the raw uploaded docs are only needed for edge
cases the PM distillation might have missed.
"""

def _initial_document_budget() -> int:
    """Parse CTX_ARCHITECT_DOCUMENT_BUDGET without ever crashing the import.

    A malformed value (e.g. "40k") must degrade to the default, not take the
    whole app down at startup - the same never-raise convention as
    `ContextPolicy.from_environment`.
    """
    raw = os.environ.get("CTX_ARCHITECT_DOCUMENT_BUDGET", "150000")
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Malformed CTX_ARCHITECT_DOCUMENT_BUDGET=%r; using default 8000", raw
        )
        return 8_000


INITIAL_DOCUMENT_BUDGET = _initial_document_budget()
"""Characters of the original upload to carry into the *first* request.

Measured on a real run: seven documents totalling 135,821 characters made the
architect's first request ~35,200 tokens, of which 96% was those documents -
sitting beside `product_intake`, which is the product manager's distillation of
the same material. The structured response came back with required sections
empty, the signature of a model with almost no room left to answer in.

Reduced from 40,000 to 8,000 because:
- The product intake is already the distilled version of these documents.
- A small budget forces the architect to rely on the intake rather than trying
  to re-read raw docs it doesn't have room for.
- The architect can request specific document excerpts if needed (via tool call).

Set to 0 to send everything (not recommended for large inputs).
"""


def _document_excerpt(document: DocumentContent, budget: int) -> str:
    """The document text, trimmed to a budget with the trim made visible."""
    text = document.text
    if len(text) <= budget:
        return text
    return (
        text[:budget]
        + f"\n\n[Excerpt: {len(text):,} characters of source documents were trimmed to "
        f"{budget:,} for this revision. The approved product intake above is the "
        "complete distillation of them; ask for a specific document if you need more.]"
    )


def build_architecture_request(
    product_intake_text: str,
    tools_and_models_text: str,
    stack_selection_text: str,
    repository: RepositoryContext,
    document: DocumentContent,
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input from the approved intake, tools/models plan, and repo context."""
    brief = (
        f"Repository root: {repository.root_path} "
        f"(branch: {repository.branch}, commit: {repository.commit})\n\n"
        f"--- Approved product intake ---\n{product_intake_text}\n\n"
        f"--- Approved tools and models plan ---\n{tools_and_models_text}\n\n"
        f"--- Approved stack selection ---\n{stack_selection_text}\n\n"
        f"--- Original uploaded documents ---\n"
        f"{_document_excerpt(document, INITIAL_DOCUMENT_BUDGET) if INITIAL_DOCUMENT_BUDGET else document.text}\n\n"
        f"**CRITICAL INSTRUCTION**: When scaffolding or creating projects (using terminal commands), ensure you place it strictly inside a directory named after the app (e.g. `thehub/` for 'The Hub'). Do NOT use generic names like 'nest-app' and do NOT scaffold directly in the repository root without a named folder. Place all documentation in the `docs/` directory.\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


def build_architecture_revision_request(
    previous_specification_text: str,
    required_changes: list[str],
    product_intake_text: str,
    tools_and_models_text: str,
    stack_selection_text: str,
    repository: RepositoryContext,
    document: DocumentContent,
) -> dict[str, list[dict[str, str]]]:
    """Build the input that sends a rejected specification back for a new revision.

    Step 4.3 requires the controller to route rejected architecture back to the
    Principal Architect. Routing alone is not enough: re-sending the *original*
    brief would make the architect redo the same work with no idea what was
    wrong, and it would very likely reproduce the same rejected specification.
    This request instead carries the previous specification plus the concrete
    required changes, so the architect can make a targeted revision.

    Args:
        previous_specification_text: the rejected specification, serialized.
        required_changes: one line per thing that must change. Sources are the
            Senior Architect Reviewer's findings (severity, description, and
            required remediation) and, when optional user review is enabled,
            the human reviewer's comments.

    Returns:
        A Deep Agent input dict in the same `{"messages": [...]}` shape as
        `build_architecture_request`, so the caller invokes it identically.
    """
    changes_text = "\n".join(f"- {change}" for change in required_changes)
    brief = (
        f"Repository root: {repository.root_path} "
        f"(branch: {repository.branch}, commit: {repository.commit})\n\n"
        f"--- Approved product intake ---\n{product_intake_text}\n\n"
        f"--- Approved tools and models plan ---\n{tools_and_models_text}\n\n"
        f"--- Approved stack selection ---\n{stack_selection_text}\n\n"
        f"--- Original uploaded documents (excerpt) ---\n"
        f"{_document_excerpt(document, REVISION_DOCUMENT_BUDGET)}\n\n"
        "Your previous technical specification was NOT accepted. Produce a new "
        "revision that resolves every required change listed below.\n\n"
        f"--- Your previous specification ---\n{previous_specification_text}\n\n"
        f"--- Required changes ---\n{changes_text}\n\n"
        "Address every item explicitly. Do not silently drop specification "
        "content or ADRs that were not flagged.\n\n"
        f"**CRITICAL INSTRUCTION**: When scaffolding or creating projects (using terminal commands), ensure you place it strictly inside a directory named after the app (e.g. `thehub/` for 'The Hub'). Do NOT use generic names like 'nest-app' and do NOT scaffold directly in the repository root without a named folder. Place all documentation in the `docs/` directory.\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


_SYSTEM_PROMPT = """You are the Principal Architect for this workflow.

Your role is to turn an approved product intake and an approved tools-and-models
plan into a complete technical specification, recording every material decision
as an architecture decision record (ADR).

Responsibilities:
- Define product scope: what this release covers and what it explicitly defers.
- Define component boundaries, the domain model, API and event contracts, and
  data flows.
- Cover security and privacy, reliability and observability, testing, and
  deployment.
- Record every material decision as an ADR with context, alternatives,
  decision, rationale, trade-offs, consequences, and validation evidence.
- List open questions instead of guessing when evidence is missing.
- Define acceptance criteria specific enough for an independent reviewer to
  check without asking you follow-up questions.

Constraints:
- Only write your technical specification artifact inside the `docs/` folder (e.g., `docs/technical_specification.md`).
- Every write_artifact call pauses for a human decision before anything is
  saved; never claim the artifact is saved until a tool result confirms it.
- **Write the complete specification in ONE single write_artifact call.** Do NOT
  make follow-up edit calls to refine, fix typos, or improve the document after
  the initial write. The document must be complete and correct before you write
  it. Once the write is confirmed, immediately return your structured response.
- Keep the output structured and concise.

Return the response in the required output schema only.
"""


def create_principal_architect_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
        allow_subdirectories: bool = True,
) -> Any:
    resolved_repo_root = str(Path(repo_root).resolve()) if repo_root else str(Path.cwd())

    return create_role_agent(
        name=_NAME,
        stage=_STAGE,
        system_prompt=_SYSTEM_PROMPT,
        response_format=TechnicalSpecificationOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root, allow_subdirectories=allow_subdirectories,
    )


__all__ = [
    "ArchitectureDecisionRecord",
    "TechnicalSpecificationOutput",
    "build_architecture_request",
    "build_architecture_revision_request",
    "create_principal_architect_agent",
]
