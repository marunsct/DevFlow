"""Senior Architect Reviewer Deep Agent (Step 4.3).

This role worker independently reviews the Principal Architect's technical
specification and ADRs for completeness, feasibility, security, operability,
and unjustified assumptions. Its output is a structured decision, never free
text, so the LangGraph controller can route rejected work back to the
Principal Architect and approved work forward to sprint planning without
having to parse prose. The plan's gate is explicit: "Free-form text cannot
bypass the review gate."
"""

from __future__ import annotations

from app.agents.severity import validator_for as severity_in
from app.agents.project_layout import WORKSPACE_ROOT_NOTE

from pathlib import Path
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agents.scope_discipline import SCOPE_DISCIPLINE
from app.agents.testing_dependency_rule import TESTING_DEPENDENCY_RULE
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE
from app.agents.role_agent import create_role_agent

_STAGE = "architecture_review"
_NAME = "senior_architect_reviewer"


class ArchitectureReviewFinding(BaseModel):
    """One specific issue found while reviewing the technical specification."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["blocking", "major", "minor", "informational"] = Field(
        ..., description="How serious this finding is for release readiness."
    )

    # See `app.agents.severity`: the same model plays every role in a run, and
    # each role's schema asks for a different word.
    _known_severity = field_validator("severity", mode="before")(
        severity_in("blocking", "major", "minor", "informational")
    )
    description: str = Field(..., description="What is wrong or missing.")
    evidence: str = Field(..., description="The specific spec section, ADR, or repository fact supporting this finding.")
    required_remediation: str = Field(
        ..., description="What the Principal Architect must change to resolve this finding."
    )


class ArchitectureReviewOutput(BaseModel):
    """Structured review decision produced by the Senior Architect Reviewer.

    `status` is the single field the workflow controller should route on.
    Approval with only minor/informational findings is allowed; any
    `blocking` or `major` finding must force `changes_required`, which the
    system prompt below states explicitly so the model cannot approve around
    its own findings.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["approved", "changes_required"] = Field(
        ..., description="Routing decision: forward to sprint planning, or back to the Principal Architect."
    )

    @model_validator(mode="before")
    @classmethod
    def _derive_status_when_omitted(cls, data: Any) -> Any:
        """Fill `status` from the findings when the model leaves it out.

        Not a guess. The rule is stated in the system prompt as mandatory -
        "Set status to 'changes_required' if any finding is blocking or major.
        Only use 'approved' when no blocking or major finding remains" - so a
        review that lists its findings has already decided; it has only failed
        to write the word down.

        Measured on one run: the reviewer answered
        `{"findings": [...]}` with no `status` four times in one stage, which
        cost two stage restarts and reached "attempt 3 of 3", the last retry
        before the stage fails outright. Across all stored runs, 8 of 74
        answers carrying findings omit the field.

        Deliberately only fills what is ABSENT. A status the model did write is
        left exactly as written: across those same runs there are zero cases of
        a verdict approving around its own blocking finding, so there is
        nothing to enforce and overriding a stated decision on no evidence
        would be the worse error.
        """
        if not isinstance(data, dict) or data.get("status"):
            return data
        findings = data.get("findings")
        if not isinstance(findings, list):
            return data
        severities = {
            str((f or {}).get("severity", "")).strip().lower()
            for f in findings
            if isinstance(f, dict)
        }
        blocking = severities & {"blocking", "major"}
        return {**data, "status": "changes_required" if blocking else "approved"}
    findings: list[ArchitectureReviewFinding] = Field(default_factory=list)
    approval_conditions: list[str] = Field(
        default_factory=list, description="Conditions that must hold for this approval to remain valid."
    )
    accepted_risks: list[str] = Field(
        default_factory=list, description="Risks knowingly accepted rather than blocking approval on."
    )


def build_architecture_review_request(
    technical_specification_text: str,
    repository_root: str,
    document_text: str = "",
    earlier: list[ArchitectureReviewFinding] | None = None,
    revision: int = 0,
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input from the specification text awaiting review.

    `earlier` is what this review asked for last time, and `revision` how many
    times the specification has been sent back. Without them each review was a
    first reading: one run's reviewer raised two new major findings on each of
    three revisions of a to-do list - a partial-update contract, then an ES
    module setting, then that a checkbox should show whether its task is done -
    and never said whether the previous ones had been answered.

    The specification is budgeted. It is the largest artifact in the pipeline
    and it arrives in the *first* user message, which is the one case
    compaction cannot rescue: with nothing older in the conversation, the
    summariser has nothing to evict and the call simply overflows.

    `document_text` is the product brief, and only its constraints are carried.
    This is the last gate before anything is built, and it could not do the one
    job that would have saved one run: the specification it approved
    proposed Express for a brief that says "No external dependencies beyond
    basic HTML/CSS/JS", and the reviewer had no way to know that, because it
    was given the specification and nothing else. See
    `app.agents.brief_constraints`.
    """
    from app.agents.brief_constraints import constraints_note
    from app.agents.text_budget import excerpt, specification_budget

    specification = excerpt(
        technical_specification_text,
        specification_budget(),
        what="technical specification",
    )
    brief = (
        WORKSPACE_ROOT_NOTE
        + constraints_note(document_text, reader="reviewing")
        + f"--- Technical specification and ADRs under review (/docs/technical_specification.md) ---\n{specification}\n"
        + _what_the_brief_requires_that_this_defers(document_text, technical_specification_text)
        + _what_you_asked_for_last_time(earlier or [], revision)
    )
    return {"messages": [{"role": "user", "content": brief}]}


def _what_the_brief_requires_that_this_defers(document_text: str, specification: str) -> str:
    """Each brief requirement the specification defers, put to the reviewer.

    The reviewer was given the brief's constraints and not its acceptance
    criteria, so it had nothing to hold a descope against. One run's
    specification redefined "edit" as toggling completion and deferred inline
    editing, for a brief that says "Users can add, edit, delete tasks"; the
    review accepted it as a trade-off, and the objection arrived three sprint-one
    test rounds later, at stages that could not change the specification. See
    `app.analysis.integration_checks.brief_actions_the_text_defers`.

    Found by matching words, so the reviewer judges each one: a line can defer a
    variant ("bulk delete") of something the specification builds elsewhere.
    """
    try:
        from app.analysis.integration_checks import brief_actions_the_text_defers

        found = brief_actions_the_text_defers(document_text, specification)
    except Exception:  # noqa: BLE001 - a hint must never stop a review
        return ""
    if not found:
        return ""
    listed = "\n".join(
        f"- `{action}`. The brief: \"{required}\". The specification: \"{line}\""
        for action, required, line in found
    )
    return (
        "\n--- Brief requirements this specification defers or redefines ---\n"
        f"{listed}\n\n"
        "Each of these is an acceptance criterion in the operator's brief. Narrowing, "
        "reinterpreting or deferring one is the operator's decision, not the run's: a "
        "specification that does it is a major finding, and the remediation is to "
        "specify how it will be built. The one exception is a line that defers only a "
        "variant of something the specification does build elsewhere - then quote "
        "where it is built. The run's final check reads the brief, so a requirement "
        "dropped here is built at the end anyway, after every sprint that could have "
        "planned for it.\n"
    )


def _what_you_asked_for_last_time(earlier: list[ArchitectureReviewFinding], revision: int) -> str:
    """The previous review's findings, and the bar a new one has to clear."""
    if not earlier or revision < 1:
        return ""
    def field(finding: Any, name: str) -> str:
        value = finding.get(name) if isinstance(finding, dict) else getattr(finding, name, "")
        return str(value or "").strip()

    listed = "\n".join(
        f"- [{field(f, 'severity')}] {field(f, 'description')} "
        f"Required remediation: {field(f, 'required_remediation')}"
        for f in earlier
    )
    return (
        f"\n--- What your review of the previous version asked for (revision {revision}) ---\n"
        f"{listed}\n\n"
        "This version is the architect's answer. Check each of these first: resolved, "
        "or still open - and if still open, quote what the specification now says.\n\n"
        "A finding you did not raise before is major only if a competent implementer "
        "who followed this specification exactly would build something that fails a "
        "requirement of the brief, or could not build it at all. Something they would "
        "get right without being told - a control that shows the state it controls, a "
        "validation error that reaches the user the way the specification already "
        "shows errors - is minor. Every new major finding costs a full revision, and "
        "the run ends when revisions run out.\n"
    )


_SYSTEM_PROMPT = f"""You are the Senior Architect Reviewer for this workflow.

Your role is to independently review the Principal Architect's technical
specification and ADRs for completeness, feasibility, security, operability,
and unjustified assumptions.

Responsibilities:
- Identify findings with a severity of blocking, major, minor, or informational.
- Cite the specific spec section or ADR for each finding. Every finding must
  point at something the specification says, or fails to say.
- State the required remediation for every finding.
- Set status to "changes_required" if any finding is blocking or major. Only
  use "approved" when no blocking or major finding remains.
- Record any risk you are knowingly accepting rather than blocking on, and any
  condition that must remain true for your approval to stand.

WHERE YOU ARE: nothing is built yet, and that is by design. You run before
sprint planning and before any specialist writes a line. The repository holds
the specification and its supporting documents and nothing else - that is the
expected state at this stage, not a defect.

So "X is missing" is never a finding here when X is something that gets built
later. Dockerfiles, CI workflows, Helm charts, migration scripts, middleware,
endpoints, tests - none of them exist yet and none of them are your concern.
Your subject is the specification document: whether it is complete,
self-consistent, and detailed enough that someone could build from it.

Ask "does the specification say how this will be done?", never "is it done?".
The architect does not write the document - the workflow renders it from the
architect's structured specification - so a remediation is always a change to a
specification *field*, never an instruction to edit a file.
If the specification fails to describe how the product will be deployed, that
is a real finding - and the remediation is a section in the specification, not
a Dockerfile. If your remediation begins "Create", "Add" or "Implement" a file,
you are reviewing the wrong artifact; rewrite it as what the specification
should say.

Observed: this review rejected an 11.7 KB specification six times and ended
the run, on five findings all of this shape - missing container images, missing
cluster deployment charts, a missing CI workflow, missing metrics middleware,
missing encryption migrations. It had run a glob for a migration tool, found
nothing, and treated an empty repository as a defect in a document.

That specification's Deployment section read:

    Kubernetes: Helm charts (helm/charts/backend, helm/charts/database,
    helm/charts/redis, helm/charts/prometheus) with RBAC, secrets, service
    definitions, and deployment manifests.

and the finding's required remediation read:

    Add Helm chart templates under /helm/charts/ with appropriate manifests,
    RBAC, secrets.

The remediation restated what the document already said. No edit to the
document could satisfy it, because what was missing was files - which is why
six revisions did not converge and could not have. If you can satisfy your own
finding by quoting the specification back, it is not a finding.

CRITICAL: When evaluating feasibility, distinguish between issues the architect
can fix in this revision versus fundamental constraints of the technology stack.
Do NOT mark items as "blocking" if they cannot be resolved by specification
changes alone (e.g., "no Passport strategy exists when OAuth2 was chosen").
These are design choices, not specification defects. Only block on issues that
indicate the specification is incomplete, contradictory, or missing critical
details.

Acceptable risks to note (do NOT block on):
- Technology stack choices that differ from industry defaults but are justified
- Trade-offs between consistency and availability in distributed systems
- Missing operational runbooks (can be created post-approval)
- Anything not yet implemented - the implementation has not started
- Infrastructure choices (cloud provider, database engine) when they serve the requirements

{SCOPE_DISCIPLINE}

{TESTING_DEPENDENCY_RULE}

Constraints:
- Do not modify application source code or the specification itself; you only
  review it and record findings.
- Do not change repo files except through the approved artifact tool.
- Never approve based only on the Principal Architect's own confidence
  statements; approval must be grounded in what you actually verified.
- You have no write tool and need none. When you have finished reviewing,
  return your structured response immediately - that is the whole of your
  output, and the only thing the next stage receives. Do not print it as a
  message first; a response written into the conversation is not returned.
- Do not write a review document. The workflow generates
  `docs/architecture_review.md` from the structured response you return, so
  your findings reach the reader either way - and only through that response.
- Put every finding in the `findings` list. A finding described only in prose
  is not one the workflow can act on: the architect is given your findings and
  nothing else.
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


def create_architecture_reviewer_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
        allow_subdirectories: bool = True,
) -> Any:
    """Create the Senior Architect Reviewer role worker."""
    return create_role_agent(
        name=_NAME,
        stage=_STAGE,
        system_prompt=_SYSTEM_PROMPT,
        response_format=ArchitectureReviewOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root, allow_subdirectories=allow_subdirectories,
        # The workflow renders this reviewer's document from the structured
        # decision it returns, so it needs no write tool - see
        # `app.agents.review_document`.
        can_write=False,
    )


__all__ = [
    "ArchitectureReviewFinding",
    "ArchitectureReviewOutput",
    "build_architecture_review_request",
    "create_architecture_reviewer_agent",
]
