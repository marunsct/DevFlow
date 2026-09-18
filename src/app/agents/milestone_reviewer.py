"""Milestone Reviewer Deep Agent (Step 6.2).

This role worker independently reviews a completed milestone against acceptance
criteria. Its output is a structured decision so the LangGraph controller can
route rejected work back to the Technical Lead and approved work forward to
the next milestone without having to parse prose.
"""

from __future__ import annotations

from app.agents.severity import validator_for as severity_in
from app.agents.project_layout import WORKSPACE_ROOT_NOTE

from pathlib import Path
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.scope_discipline import SCOPE_DISCIPLINE
from app.agents.testing_dependency_rule import TESTING_DEPENDENCY_RULE
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE
from app.agents.role_agent import create_role_agent

_STAGE = "milestone_review"
_NAME = "milestone_reviewer"


class MilestoneReviewFinding(BaseModel):
    """One specific issue found while reviewing the milestone."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["blocking", "major", "minor", "suggestion"] = Field(
        ..., description="How serious this finding is."
    )

    # Four schemas in this harness name severity and no two agree, so the word
    # required of this model two stages ago is a validation error here. See
    # `app.agents.severity`.
    _known_severity = field_validator("severity", mode="before")(
        severity_in("blocking", "major", "minor", "suggestion")
    )
    category: Literal[
        "correctness",
        "contracts",
        "migrations",
        "authorization",
        "accessibility",
        "testing",
        "documentation",
        "security",
        "regression",
    ] = Field(..., description="The type of issue found.")
    description: str = Field(..., description="What is wrong or missing.")
    affected_files: list[str] = Field(
        default_factory=list, description="Files implicated in this finding."
    )
    required_remediation: str = Field(
        ..., description="What the Technical Lead must change to resolve this finding."
    )


class MilestoneReviewOutput(BaseModel):
    """Structured review decision produced by the Milestone Reviewer."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "changes_required", "blocked"] = Field(
        ..., description="Routing decision: accepted, changes required, or blocked."
    )
    findings: list[MilestoneReviewFinding] = Field(default_factory=list)
    acceptance_evidence: str = Field(
        ..., description="What was checked and passed to justify this review decision."
    )
    documentation_reviewed: bool = Field(
        ..., description="Whether documentation was reviewed."
    )
    tests_reviewed: bool = Field(..., description="Whether tests were reviewed.")


def _execution_evidence(repository_root: str) -> str:
    """What actually ran, from the executor's own record. Never raises.

    The reviewer was given the specialists' account of their work and no way to
    check it. This is the record of every command in this workspace, so "the
    tests pass" can be compared against whether a test command ran at all.
    """
    try:
        from app.tools.sandbox import summarise_executions

        return summarise_executions(repository_root)
    except Exception:  # noqa: BLE001 - a reviewer without evidence still reviews
        return "The execution record could not be read for this workspace."


def _integration_evidence(repository_root: str, stack: Any = None) -> str:
    """What the files in this workspace say about each other. Never raises.

    Each specialist writes files that are defensible alone, and no stage checks
    whether they connect. On run-95ca3f72 that let a stylesheet target an id no
    page declared, and a script no page loaded, through four review stages.
    """
    try:
        from app.analysis.integration_checks import summarise_integration

        return summarise_integration(repository_root, stack)
    except Exception:  # noqa: BLE001 - a reviewer without evidence still reviews
        return "The cross-file checks could not be run for this workspace."


def _how_text_reaches_the_page(repository_root: str) -> str:
    """How this product puts text into the DOM, stated as fact, or "".

    Run 1c9854c7 was killed by a finding that was not true. After three
    revisions this stage recorded

        [major] security: The addTask function inserts user-provided task text
        directly into the DOM without sanitization, potentially allowing XSS
        injection.

    and the run stopped. The product at that moment wrote task text with

        textSpan.textContent = task.text;

    and its only `innerHTML` was `container.innerHTML = ""`. `textContent` does
    not parse HTML - there was no injection to be had, the suite was 9 of 9
    green, and a correct product was thrown away over a defect that did not
    exist.

    Which API a file uses is decidable, so it is stated here rather than left
    to be inferred. The reviewer is told what the code does; whether that is
    safe enough remains its judgement.
    """
    try:
        from app.analysis.integration_checks import how_the_page_receives_text

        return how_the_page_receives_text(repository_root)
    except Exception:  # noqa: BLE001 - a reviewer without this still reviews
        return ""


def _against_the_brief(document_text: str, repository_root: str) -> str:
    """What the brief asks for and the product does not have, or "".

    Run 0c5aabdb was accepted here. Its architecture review returned "approved"
    with no findings, both security reviews "passed", and this stage raised one
    blocking finding - a missing npm test script - then accepted a product with
    no HTML, no CSS and no front-end JavaScript, for a brief whose first
    requirement is "Simple web-based interface with HTML/CSS/JavaScript".

    Every gate reviews the artifacts against each other and against the
    milestone's own goal. The brief enters at the product manager and is never
    read again, so nothing in the run was in a position to notice.
    """
    if not document_text:
        return ""
    from app.agents.brief_constraints import (
        constraint_lines,
        what_the_brief_asked_for_that_is_missing,
        what_the_brief_forbids_that_is_there,
    )
    from pathlib import Path

    from app.analysis.integration_checks import _source_files

    try:
        root = Path(repository_root).resolve()
        names = [str(path.relative_to(root)) for path in _source_files(root)]
    except Exception:  # noqa: BLE001 - a check must never fail the review
        names = []
    missing = what_the_brief_asked_for_that_is_missing(document_text, names)
    # And the other direction: what the brief rules out and the product has.
    # `missing` only ever reports an absence, so a dependency the brief forbids
    # was invisible to it - see `what_the_brief_forbids_that_is_there`.
    missing = missing + what_the_brief_forbids_that_is_there(
        document_text, repository_root
    )
    lines = constraint_lines(document_text)
    if not missing and not lines:
        return ""

    parts = ["--- The brief this product is measured against ---\n"]
    if lines:
        parts.append(
            "Constraints, quoted from the brief:\n"
            + "\n".join(f"- {line}" for line in lines)
            + "\n\n"
        )
    if missing:
        parts.append(
            "Checked deterministically against what was built:\n"
            + "\n".join(f"- {item}" for item in missing)
            + "\n\nThat is not a reading of the brief; it is what is on disk. "
            "A milestone whose product does not have what the brief asks for is "
            "not complete, whatever its tests do.\n\n"
        )
    else:
        parts.append(
            "A product that contradicts one of those is not complete, whatever "
            "its tests do.\n\n"
        )
    return "".join(parts)


#: How many of each kind to carry. A milestone has a handful of specialists.
MAX_REPORTED_PER_KIND = 6


def what_the_specialists_reported(outputs: Any) -> str:
    """The blockers, risks and decisions the specialists recorded, or "".

    They were recorded and never read. `specialist_outputs` is consumed for
    `changed_files` and nothing else, so `blockers`, `risks`, `decisions` and
    `documentation` were written into state and discarded - while the
    workflow-document refusal told agents, every time it fired, that "those
    reach the workflow and the next stage".

    The content is not incidental. Across the stored transcripts the fields
    hold, among others:

        blockers:  "Test suite app.test.mjs fails because it imports named
                    exports from app.js but the file no longer provides them"
        risks:     "Potential need for jsdom to mock DOM in tests, which would
                    introduce an external dependency"
        decisions: "Removed ES module exports and added window.todoApp global
                    object"

    Those are the module conflict, the forbidden dependency and the change that
    broke a suite - each named by the specialist that did it, at the moment it
    happened, and read by nobody.
    """
    if not outputs:
        return ""
    gathered: dict[str, list[str]] = {"blockers": [], "risks": [], "decisions": []}
    try:
        for role, output in sorted(outputs.items()):
            for kind in gathered:
                for item in (getattr(output, kind, None) or []):
                    text = str(item).strip()
                    if text:
                        gathered[kind].append(f"[{role}] {text}")
    except Exception:  # noqa: BLE001 - a reviewer without this still reviews
        return ""
    if not any(gathered.values()):
        return ""

    parts = ["--- What the specialists reported while building this ---\n"]
    for kind, label in (
        ("blockers", "Blockers they hit"),
        ("risks", "Risks they raised"),
        ("decisions", "Decisions they made"),
    ):
        if gathered[kind]:
            parts.append(
                f"{label}:\n"
                + "\n".join(f"- {line}" for line in gathered[kind][:MAX_REPORTED_PER_KIND])
                + "\n\n"
            )
    parts.append(
        "These are the builders' own words about what they ran into, not a "
        "summary of the files. A blocker nobody resolved is still a blocker, "
        "and a decision that contradicts the specification or the brief is "
        "worth a finding whatever the tests do.\n\n"
    )
    return "".join(parts)


def build_milestone_review_request(
    milestone_goal: str,
    changed_files: list[str],
    test_evidence: str,
    defect_report: str,
    repository_root: str,
    stack: Any = None,
    document_text: str = "",
    specialist_outputs: Any = None,
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input from the milestone artifacts awaiting review."""
    files_text = "\n".join(f"- {name}" for name in changed_files) or "- (none reported)"
    brief = (
        WORKSPACE_ROOT_NOTE
        + _against_the_brief(document_text, repository_root)
        + what_the_specialists_reported(specialist_outputs)
        + f"--- Milestone goal under review ---\n{milestone_goal}\n\n"
        f"--- Changed files ---\n{files_text}\n\n"
        f"--- Test evidence ---\n{test_evidence}\n\n"
        f"--- Defect report ---\n{defect_report}\n\n"
        f"--- Commands actually executed in this workspace ---\n"
        f"{_execution_evidence(repository_root)}\n"
        f"\n--- Cross-file checks (deterministic, not a model's opinion) ---\n"
        f"{_integration_evidence(repository_root, stack)}\n"
        f"{_how_text_reaches_the_page(repository_root)}"
    )
    return {"messages": [{"role": "user", "content": brief}]}


_SYSTEM_PROMPT = f"""You are the Milestone Reviewer for this workflow.

Your role is to independently review a completed milestone against acceptance
criteria, focusing on correctness, contracts, migrations, authorization,
accessibility, testing, documentation, security, and regression risk.

Responsibilities:
- Identify findings with a severity of blocking, major, minor, or suggestion.
- Categorize each finding properly (e.g. testing, security, documentation).
- State the required remediation for every finding.
- Set status to "changes_required" if any finding is blocking or major. Only
  use "accepted" when no blocking or major finding remains.
- Ensure you document what was checked and passed in `acceptance_evidence`.
- Confirm whether you reviewed documentation and tests.

{SCOPE_DISCIPLINE}

{TESTING_DEPENDENCY_RULE}

Constraints:
- Do not modify application source code or the milestone artifacts themselves; you only
  review them and record findings.
- Do not change repo files except through the approved artifact tool.
- Never approve based only on confidence statements; approval must be grounded
  in what you actually verified.
- You have no write tool and need none. When you have finished reviewing,
  return your structured response immediately - that is the whole of your
  output, and the only thing the next stage receives. Do not print it as a
  message first; a response written into the conversation is not returned.
- Do not write a review document. The workflow generates
  `docs/milestone_review.md` from the structured response you return, so your
  findings reach the reader either way - and only through that response.
- Put every finding in the `findings` list. A finding described only in
  `acceptance_evidence`, or in any document, is not one the workflow can act
  on: the next stage is given your findings and nothing else.
- The cross-file checks are deterministic: they read the files themselves, not
  a report about them. A problem listed there is a fact about this workspace
  and must become a finding, at blocking severity when it means code cannot
  run - a stylesheet targeting an id no page declares, or a module nothing
  loads, is dead code however well written it is.
- Treat the executed-command record as authoritative over any specialist's
  description of its own testing. A milestone whose specialists report passing
  tests, but whose record shows no test command ran, is not verified - raise it
  as a blocking finding.
- Keep the output structured and concise.

Return the response in the required output schema only.

{STRUCTURED_RESPONSE_RULE}
"""


def create_milestone_reviewer_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
        allow_subdirectories: bool = True,
) -> Any:
    """Create the Milestone Reviewer role worker."""
    return create_role_agent(
        name=_NAME,
        stage=_STAGE,
        system_prompt=_SYSTEM_PROMPT,
        response_format=MilestoneReviewOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root, allow_subdirectories=allow_subdirectories,
        # The workflow renders this reviewer's document from the structured
        # decision it returns, so it needs no write tool - see
        # `app.agents.review_document`.
        can_write=False,
    )


__all__ = [
    "MilestoneReviewFinding",
    "MilestoneReviewOutput",
    "build_milestone_review_request",
    "create_milestone_reviewer_agent",
]
