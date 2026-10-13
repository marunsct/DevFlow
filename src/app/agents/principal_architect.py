"""Principal Architect Deep Agent (Step 4.2).

This role worker consumes the approved product intake and the approved
tools-and-models comparison, then produces a technical specification plus
architecture decision records (ADRs). It defines component boundaries, data
flows, and acceptance criteria, and records the rationale behind every
material decision so a later reviewer or specialist does not have to guess why
a choice was made.
"""

from __future__ import annotations

import re

import logging
import os
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.scope_discipline import SCOPE_DISCIPLINE
from app.agents.project_layout import PROJECT_LAYOUT
from app.agents.testability import TESTABILITY_RULE
from app.agents.testing_dependency_rule import TESTING_DEPENDENCY_RULE
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE
from app.agents.role_agent import create_role_agent
from app.tools.package_registry import lookup_tools
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


#: A testing entry that needs a person, or a check that cannot fail.
_NEEDS_A_PERSON = re.compile(
    r"\bmanual(?:ly)?\b[^.;]*\b(?:test|verif|check|inspect|review)"
    r"|\bvisual(?:ly)?\s+(?:inspect|check|verif)"
    r"|\bby hand\b|\beyeball"
    r"|console\.assert|\bconsole\s+assert",
    re.I,
)
#: The entry rules such checks out - before naming them ("no manual steps") or
#: after ("manual testing is refused", "manual and visual checks are excluded").
#: Only the first was recognised once: on one run an entry reading "Manual
#: testing alone is refused - no human runs tests here" was sent back as a
#: plan for manual testing, twice, and the third answer came back with two
#: required sections empty.
_NEGATED = re.compile(
    r"\b(?:no|not|never|without|instead of|rather than|replac\w*|avoid\w*|eliminat\w*)\b"
    r"[^.;]{0,20}\b(?:manual|visual|by hand|console)"
    r"|\b(?:manual|visual|by hand|console)\w*\b[^.;]{0,60}?\b(?:is|are|be|been|get|gets)\s+"
    r"(?:\w+\s+)?(?:refus\w*|exclud\w*|forbid\w*|prohibit\w*|disallow\w*|reject\w*|ruled out|"
    r"banned|not\s+(?:used|allowed|permitted|valid|possible|planned|relied))"
    r"|\b(?:manual|visual|by hand|console)\w*\b[^.;]{0,60}?\b(?:never|not)\s+"
    r"(?:used|allowed|permitted|valid|possible|planned|relied|happen\w*|run)\b",
    re.I,
)


def testing_nobody_can_run(specification: Any) -> list[str]:
    """The specification's testing entries that nothing here can carry out.

    There is no person watching the workspace and no display, so a manual or
    visual check never happens, and a `console.assert` exits 0 whatever it finds.
    One run's specification read "No test framework dependencies - use
    console.assert and manual verification"; every test written from it would
    have passed. An entry that rules these out ("no manual steps") is kept.
    """
    found: list[str] = []
    for entry in getattr(specification, "testing", None) or []:
        text = " ".join(str(entry).split())
        if _NEEDS_A_PERSON.search(text) and not _NEGATED.search(text):
            found.append(text)
    return found


def the_sections_a_specification_has(*, reader: str) -> str:
    """The specification's fixed sections, said to whoever is about to ask for,
    or be asked for, one it does not have.

    The specification is a schema, and its sections are that schema's fields.
    Neither side was told. Measured on one run: the reviewer required a
    "ui_design" section, then "code_size_governance", "testing_infrastructure"
    and "deployment_artifacts"; the architect, who cannot add a field, wrote
    what it could into the sections that exist; the reviewer found the named
    sections still missing; and after six revisions of the same four findings
    the run ended without a line of code.

    Read off `TechnicalSpecificationOutput`, so it cannot drift from it.
    """
    names = ", ".join(
        f"`{name}`" for name in TechnicalSpecificationOutput.model_fields
    )
    fixed = (
        "The specification has a fixed set of sections, and no revision can add "
        f"one: {names}.\n"
    )
    if reader == "reviewing":
        return (
            fixed
            + "So do not require a new section by name - it cannot be created, "
            "and the finding would come back unresolved however good the revision "
            "is. Say what is missing and which of those sections it belongs in, "
            "and judge the next revision by whether the content is there, "
            "wherever it was put.\n\n"
        )
    return (
        fixed
        + "Where a required change asks for a new section, put what it asks for "
        "in the existing section it belongs to, in full - the review reads for "
        "the content, not for the heading.\n\n"
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
    # Optional, like every section here, so a specification written before
    # these existed still loads. Required by `specialist_advice` when advice was
    # given: an interface design for a product with an interface, and one line
    # per advice item.
    interface_design: list[str] = Field(
        default_factory=list,
        description=(
            "For a product a person uses: the layout at a phone's width and a "
            "desktop's, each control's states, the feedback after each action, "
            "accessibility, and the visual style - from the UI/UX advice adopted."
        ),
    )
    specialist_advice_decisions: list[str] = Field(
        default_factory=list,
        description=(
            "One line per specialist advice item, starting with its id: adopted and "
            "where, or declined and why."
        ),
    )
    decisions: list[ArchitectureDecisionRecord] = Field(
        default_factory=list, description="Every material decision made while producing this specification."
    )


from app.documents import DocumentContent

def _revision_budget() -> int:
    """Characters of the document carried into a revision request.

    Half the initial budget: a revision carries the document *and* the findings
    raised against it, and the findings are the part that must fit beside it.
    """
    from app.agents.context_budget import ContextBudget

    raw = os.environ.get("CTX_REVISION_DOCUMENT_BUDGET", "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            logger.warning("Malformed CTX_REVISION_DOCUMENT_BUDGET=%r; deriving it", raw)
    return ContextBudget.resolve().revision_budget_chars


REVISION_DOCUMENT_BUDGET = _revision_budget()
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
    from app.agents.context_budget import ContextBudget

    raw = os.environ.get(
        "CTX_ARCHITECT_DOCUMENT_BUDGET",
        str(ContextBudget.resolve().document_budget_chars),
    )
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


def _the_briefs_own_constraints(document: Any) -> str:
    """The brief's constraints as a block, or "". Never raises.

    `app.agents.brief_constraints` already does this for the stage that picks
    the stack and the one that reviews the specification. The stage that
    *writes* the specification had the whole document and not the constraints
    pulled out of it, and wrote a forbidden dependency into the design three
    times across the stored runs.
    """
    try:
        from app.agents.brief_constraints import constraints_note

        return constraints_note(getattr(document, "text", "") or "", reader="choosing")
    except Exception:  # noqa: BLE001 - an architect without this still writes
        return ""


def _the_specialists_advice(advice: dict[str, list[str]] | None) -> str:
    """The specialists' numbered advice and what to do with it, or "". See `app.agents.specialist_advice`."""
    from app.agents.specialist_advice import advice_block

    return advice_block(advice)


def build_architecture_request(
    product_intake_text: str,
    tools_and_models_text: str,
    stack_selection_text: str,
    repository: RepositoryContext,
    document: DocumentContent,
    advice: dict[str, list[str]] | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input from the approved intake, tools/models plan, and repo context."""
    brief = (
        # Deliberately not the repository's absolute path. That is the HOST's
        # path; inside the agent the workspace is rooted at "/". Quoting it here
        # and then telling the agent never to use it does not work - measured on
        # one run, agents retried `ls` against that exact string four times
        # in a row, and fed it to shell commands, every attempt failing with
        # path_not_found. The reliable fix is not to show it.
        f"Repository: branch {repository.branch}, commit {repository.commit}\n"
        f"The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        # The brief's own constraints, quoted, before anything derived from
        # them. The whole document appears below and that was not enough: one
        # run's specification said "Backend: Express server" with the
        # brief in front of it, and two runs wrote "Use
        # Node's built-in test runner with jsdom for DOM simulation" into a
        # specification for a brief reading "No external dependencies beyond
        # basic HTML/CSS/JS". The specialists that installed jsdom were
        # building to spec; this is where that choice is made.
        + _the_briefs_own_constraints(document)
        + f"--- Approved product intake (/docs/product_intake.md) ---\n{product_intake_text}\n\n"
        f"--- Approved tools and models plan (/docs/tools_and_models.md) ---\n{tools_and_models_text}\n\n"
        f"--- Approved stack selection (/docs/technology_stack.md) ---\n{stack_selection_text}\n\n"
        + _the_specialists_advice(advice)
        + f"--- Original uploaded documents ---\n"
        f"{_document_excerpt(document, INITIAL_DOCUMENT_BUDGET) if INITIAL_DOCUMENT_BUDGET else document.text}\n\n"
        f"**CRITICAL INSTRUCTION**: All application code lives in ONE project directory at the workspace root. Run `ls` FIRST: if a project directory already exists, write into that exact directory, spelled exactly as it already is. Only create one if none exists, naming it after this product in lowercase-with-hyphens. Never scaffold directly in the workspace root, never use a generic name like 'nest-app', and never create a second project directory. Documentation that ships with the product goes inside that project directory beside the code it describes. `docs/` is the workflow's own directory and writing anything into it is refused.\n"
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
    advice: dict[str, list[str]] | None = None,
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
        # Deliberately not the repository's absolute path. That is the HOST's
        # path; inside the agent the workspace is rooted at "/". Quoting it here
        # and then telling the agent never to use it does not work - measured on
        # one run, agents retried `ls` against that exact string four times
        # in a row, and fed it to shell commands, every attempt failing with
        # path_not_found. The reliable fix is not to show it.
        f"Repository: branch {repository.branch}, commit {repository.commit}\n"
        f"The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        # The brief's own constraints, quoted, before anything derived from
        # them. The whole document appears below and that was not enough: one
        # run's specification said "Backend: Express server" with the
        # brief in front of it, and two runs wrote "Use
        # Node's built-in test runner with jsdom for DOM simulation" into a
        # specification for a brief reading "No external dependencies beyond
        # basic HTML/CSS/JS". The specialists that installed jsdom were
        # building to spec; this is where that choice is made.
        + _the_briefs_own_constraints(document)
        + f"--- Approved product intake (/docs/product_intake.md) ---\n{product_intake_text}\n\n"
        f"--- Approved tools and models plan (/docs/tools_and_models.md) ---\n{tools_and_models_text}\n\n"
        f"--- Approved stack selection (/docs/technology_stack.md) ---\n{stack_selection_text}\n\n"
        + _the_specialists_advice(advice)
        + f"--- Original uploaded documents (excerpt) ---\n"
        f"{_document_excerpt(document, REVISION_DOCUMENT_BUDGET)}\n\n"
        "Your previous technical specification was NOT accepted. Produce a new "
        "revision that resolves every required change listed below.\n\n"
        f"--- Your previous specification ---\n{previous_specification_text}\n\n"
        f"--- Required changes ---\n{changes_text}\n\n"
        + the_sections_a_specification_has(reader="revising")
        + "Address every item explicitly. Do not silently drop specification "
        "content or ADRs that were not flagged, and do not add scope that was "
        "not asked for: a revision resolves the listed findings and changes "
        "nothing else. New sections, new features and new behaviours added "
        "here arrive unreviewed and under-specified, and the next review finds "
        "them. Four consecutive reviews of one specification returned "
        "changes_required with 5, then 4, then 6, then 8 findings, escalating "
        "from minor to blocking, each round raising subjects the round before "
        "had not mentioned.\n\n"
        f"**CRITICAL INSTRUCTION**: All application code lives in ONE project directory at the workspace root. Run `ls` FIRST: if a project directory already exists, write into that exact directory, spelled exactly as it already is. Only create one if none exists, naming it after this product in lowercase-with-hyphens. Never scaffold directly in the workspace root, never use a generic name like 'nest-app', and never create a second project directory. Documentation that ships with the product goes inside that project directory beside the code it describes. `docs/` is the workflow's own directory and writing anything into it is refused.\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


_SYSTEM_PROMPT = f"""You are the Principal Architect for this workflow.

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

{SCOPE_DISCIPLINE}

{TESTABILITY_RULE}

{TESTING_DEPENDENCY_RULE}

{PROJECT_LAYOUT}

Constraints:
- Do not write a specification document. The workflow renders
  `docs/technical_specification.md` from the structured response you return,
  so your specification reaches its readers either way - and only through that
  response. Writing it yourself produces the whole document twice from one
  understanding, and the two copies then disagree.
- Put the specification in the response fields. Each field is a section of the
  document: `product_scope`, `component_boundaries`, `domain_model`,
  `api_and_event_contracts`, `data_flows`, `security_and_privacy`,
  `reliability_and_observability`, `testing`, `deployment`,
  `acceptance_criteria`, `open_questions`, and `decisions` for the ADRs. A
  section you leave empty is a section the document says nothing about.
- Keep the output structured and concise.

Return the response in the required output schema only.

{STRUCTURED_RESPONSE_RULE}
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
        # Its document is rendered from the structured response, so it needs no
        # write tool - see `app.agents.artifact_document`.
        can_write=False,
        # Versions move faster than any model's training: see `app.tools.package_registry`.
        extra_tools=lookup_tools(),
    )


__all__ = [
    "ArchitectureDecisionRecord",
    "TechnicalSpecificationOutput",
    "build_architecture_request",
    "build_architecture_revision_request",
    "create_principal_architect_agent",
]
