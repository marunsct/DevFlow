"""Security Reviewer Deep Agent.

This role worker independently reviews changes for security and reliability
issues. It can be invoked by the milestone reviewer or used standalone.
"""

from __future__ import annotations

from app.agents.severity import validator_for as severity_in
from app.agents.finding_category import validator_for as category_in
from app.agents.project_layout import WORKSPACE_ROOT_NOTE

from pathlib import Path
from typing import Any, Literal, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.scope_discipline import SCOPE_DISCIPLINE
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE
from app.agents.role_agent import create_role_agent

_STAGE = "security_review"
_NAME = "security_reviewer"


#: The security review's categories, in the order the schema lists them.
SECURITY_CATEGORIES = (
    "isolation", "permissions", "data_leakage", "secrets", "external_integration", "filesystem", "command_execution",
    "timeouts", "checkpoint_recovery", "audit_trail", "retention", "code_note", "other",
)


class SecurityFinding(BaseModel):
    """One specific security or reliability issue found."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["critical", "high", "medium", "low", "info"] = Field(
        ..., description="How serious this finding is."
    )

    # See `app.agents.severity`. This vocabulary is the CVSS one and the other
    # three are not, so a model that reviewed a milestone first arrives here
    # saying "blocking".
    _known_severity = field_validator("severity", mode="before")(
        severity_in("critical", "high", "medium", "low", "info")
    )
    category: Literal[
        "isolation",
        "permissions",
        "data_leakage",
        "secrets",
        "external_integration",
        "filesystem",
        "command_execution",
        "timeouts",
        "checkpoint_recovery",
        "audit_trail",
        "retention",
        # A finding that names no security or reliability harm (PA.17): a note about the code, kept and capped.
        "code_note",
        # So an unrecognised word is kept rather than rejecting the whole review (`app.agents.finding_category`).
        "other",
    ] = Field(..., description="The category of security or reliability issue.")
    _known_category = field_validator("category", mode="before")(category_in(*SECURITY_CATEGORIES))
    description: str = Field(..., description="What is wrong or missing.")
    harm: str = Field(
        default="",
        description=(
            "The harm, in one sentence: who could do what to which data or service because of this. Empty when "
            "there is none: the finding is then a note about the code, never critical or high."
        ),
    )
    affected_files: list[str] = Field(
        default_factory=list, description="Files implicated in this finding."
    )
    remediation: str = Field(
        ..., description="What must be changed to resolve this finding."
    )


class SecurityReviewOutput(BaseModel):
    """Structured review decision produced by the Security Reviewer."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["passed", "findings"] = Field(
        ..., description="Routing decision: passed or findings exist."
    )
    findings: list[SecurityFinding] = Field(default_factory=list)
    local_only_exceptions: list[str] = Field(
        default_factory=list, description="Documented exceptions for local-only features."
    )


#: Characters of source to carry into one security review. Enough for a small
#: product's whole application, and bounded so a large one still starts.
SOURCE_BUDGET = 24_000

def _the_source_under_review(changed_files: list[str], repository_root: str, held: Sequence[str] = ()) -> str:
    """The contents of the changed files, or a note saying why there are none.

    The reviewer was given a list of names and asked to review them. It has
    read tools and could open each one, but it answers in two to four model
    calls, so in practice it never did: across every transcript on disk, 33
    security reviews returned `status: passed` and `findings: []`, every single
    one. Not one finding has ever been recorded by this stage.

    A reviewer that cannot see the code cannot review it, and the fix is the
    same one every other reviewer here already has - the milestone reviewer is
    handed test evidence, the execution ledger and the cross-file checks; the
    architecture reviewer is handed the specification. This one was handed
    filenames.

    Bounded by `SOURCE_BUDGET`, so a large product's files may not all fit. A
    file that does not fit is named, every one of them - this used to stop at
    the first and drop the rest without a word - and the reviewer is told to
    open those itself. The workflow records the same list in the review
    document (`source_coverage`), so a pass over part of the source says so.

    Which files are shown is the language table's (`review_files.under_review`): the fixed list of suffixes it
    replaced knew JavaScript, Python, HTML and JSON only, and a Go, Rust or Java product's request said none of its
    files could be read. `held`: the files the project memory holds for this review, numbered
    (`review_files.held_for_review`, LF.1284); named as held, not repeated here and not to be opened. Only for a
    product whose files today's request and memory do not show; otherwise this is as it was.
    """
    shown, not_shown = _select(changed_files, repository_root, held)
    # The files the budget leaves out given as their changed definitions and what uses them (KG.8, off until measured).
    from app.agents.reviews_hold_the_change import for_files_not_shown

    the_change, not_shown = for_files_not_shown(repository_root, not_shown)
    if held:
        return _with_the_files_held(held, shown, not_shown) + the_change
    if not shown and not not_shown and not the_change:
        return (
            "None of the changed files could be read for this request. Open "
            "them with your read tools before deciding anything.\n"
        )
    parts = [f"\n--- {name} ---\n{body}" for name, body in shown]
    parts += [f"\n--- {name} (not shown: the budget for this request is full) ---" for name in not_shown]
    request = (
        "--- The source under review, in full ---"
        + "".join(parts)
        + "\n\nThis is the code itself, not a summary. Judge it on what is "
        "here; use your read tools only for something this does not show.\n"
    )
    if not_shown:
        request += (
            f"\n{len(not_shown)} file(s) above are not shown. Open each of them with your "
            "read tools before deciding: a review that passes code it never read is "
            "recorded as covering only what it read.\n"
        )
    return request + the_change


def _with_the_files_held(held: Sequence[str], shown: list[tuple[str, str]], not_shown: list[str]) -> str:
    """The source part of a request whose memory holds `held`: those named, the rest shown or named as before."""
    from app.agents.review_files import held_section

    request = held_section(held)
    if shown or not_shown:
        request += (
            "\n--- The rest of the source under review, in full ---"
            + "".join(f"\n--- {name} ---\n{body}" for name, body in shown)
            + "".join(f"\n--- {name} (not shown: the budget for this request is full) ---" for name in not_shown)
            + "\n"
        )
    request += "\nThis is the code itself, not a summary. Judge it on what is here.\n"
    if not_shown:
        request += (
            f"\n{len(not_shown)} file(s) above are neither held nor shown. Open each of them with your "
            "read tools before deciding: a review that passes code it never read is "
            "recorded as covering only what it read.\n"
        )
    return request


def _select(changed_files: list[str], repository_root: str,
            held: Sequence[str] = ()) -> tuple[list[tuple[str, str]], list[str]]:
    """The reviewable changed files that fit the budget, with their text, and those that do not; none of `held`."""
    from app.agents.review_files import under_review

    shown: list[tuple[str, str]] = []
    not_shown: list[str] = []
    used = 0
    for name, body in under_review(repository_root, changed_files):
        if name in held:
            continue
        if used + len(body) > SOURCE_BUDGET:
            not_shown.append(name)
            continue
        used += len(body)
        shown.append((name, body))
    return shown, not_shown


def source_coverage(changed_files: list[str], repository_root: str,
                    held: Sequence[str] = ()) -> tuple[list[str], list[str]]:
    """(files shown to the reviewer in full - in its memory or its request -, reviewable files the budget left out)."""
    shown, not_shown = _select(changed_files, repository_root, held)
    return [*held, *(name for name, _ in shown)], not_shown


def _how_text_reaches_the_page(repository_root: str) -> str:
    """What the product uses to write to the DOM, stated rather than inferred.

    `how_the_page_receives_text` was built for the milestone reviewer, which
    recorded a major XSS finding in one run against a product whose only
    text write was `textContent`. The security reviewer is the stage whose job
    this is, and it was never given the fact: one run's security review
    reported "renders task names using innerHTML without sanitization" against
    a product with no `innerHTML` assignment of any content at all - only
    `textContent`, three times over.

    The same wrong finding, from the second of the two stages that can make
    it, with the answer already computed and routed to the other one.
    """
    try:
        from app.analysis.integration_checks import how_the_page_receives_text

        return how_the_page_receives_text(repository_root)
    except Exception:  # noqa: BLE001 - evidence that cannot be gathered says nothing
        return ""


def _advisories_of_what_ships(repository_root: str) -> str:
    """The known advisories and support dates of what the installs resolved (HK.6, `app.stacks.advisories`)."""
    try:
        from app.stacks.advisories import for_the_security_reviewer

        return for_the_security_reviewer(repository_root)
    except Exception:  # noqa: BLE001 - the request as it was
        return ""


def build_security_review_request(
    changed_files: list[str],
    tool_permissions: str,
    repository_root: str,
    held: Sequence[str] = (),
    recorded: Sequence[str] = (),
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input for a security review; `held` as `_the_source_under_review` takes it.

    `recorded`: the findings the sprint has already recorded (`repeated_findings.recorded_by`), which are not raised
    again unless they still do harm (PA.17)."""
    files_text = "\n".join(f"- {name}" for name in changed_files) or "- (none reported)"
    brief = (
        WORKSPACE_ROOT_NOTE
        + f"--- Changed files under review ---\n{files_text}\n\n"
        + _the_source_under_review(changed_files, repository_root, held)
        + _how_text_reaches_the_page(repository_root)
        + _advisories_of_what_ships(repository_root)
        + _already_recorded(recorded)
        + f"\n--- Tool permissions context ---\n{tool_permissions}\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


#: Recorded findings one request lists, at most.
MOST_RECORDED_SHOWN = 12


def _already_recorded(recorded: Sequence[str]) -> str:
    lines = [" ".join(str(item).split())[:300] for item in recorded if str(item).strip()][:MOST_RECORDED_SHOWN]
    if not lines:
        return ""
    return ("\n--- Already recorded for this sprint ---\n" + "\n".join(f"- {line}" for line in lines)
            + "\nThese stay on the sprint's record. Raise one again only when the code still does the harm it names.\n")


#: What a harm that names nothing is written as.
_NO_HARM = frozenset({
    "", "none", "na", "n a", "nothing", "no harm", "no direct harm", "no security harm", "no security impact",
    "no impact", "not applicable", "none identified", "no risk", "minimal", "low",
})
#: The severities a finding with no harm may not have, and the one it is capped to.
_HARM_ONLY = frozenset({"critical", "high", "medium"})
CODE_NOTE_SEVERITY = "low"
#: The severities that hold the sprint (`workflow._SECURITY_GRADES_THAT_GATE`): a repeat of one is never dropped.
_GATES = frozenset({"critical", "high"})


def names_a_harm(harm: str) -> bool:
    """Whether a finding's harm says who could do what to which data or service, rather than nothing."""
    text = " ".join("".join(ch if ch.isalnum() else " " for ch in str(harm or "").lower()).split())
    return text not in _NO_HARM and len(text.split()) >= 3


def as_recorded(review: SecurityReviewOutput, recorded: Sequence[str] = ()) -> SecurityReviewOutput:
    """`review` with each finding that names no harm made a code note, and each repeat that does not gate left out.

    PA.17, measured on one run's reviews (2026-11-25 per-agent audit, role 18): its critical finding was a missing type
    import, its info findings an unused model class and comments in a test file - five of six findings were not about
    security - and the second review of the same sprint raised three of them again. A finding with no harm is kept as
    a note about the code (`code_note`, at most low), so it can no longer hold a sprint as critical or high; one the
    sprint already recorded (`recorded`) is not raised again unless it still holds the sprint. Never raises.
    """
    try:
        from app.agents.repeated_findings import already_recorded

        findings: list[SecurityFinding] = []
        for finding in review.findings:
            if not names_a_harm(finding.harm):
                finding = finding.model_copy(update={
                    "category": "code_note",
                    "severity": CODE_NOTE_SEVERITY if finding.severity in _HARM_ONLY else finding.severity,
                })
            if finding.severity not in _GATES and already_recorded(finding.description, recorded):
                continue
            findings.append(finding)
        if findings == list(review.findings):
            return review
        status = "findings" if findings else "passed"
        return review.model_copy(update={"findings": findings, "status": status})
    except Exception:  # noqa: BLE001 - the review as it was answered stands
        return review


#: Measured on one run: a browser-only product with no accounts kept its
#: records in the browser's own storage; this review rated "stored without
#: encryption, readable via devtools or extensions" medium, the milestone
#: review made it major, and the last sprint spent two attempts base64-encoding
#: the records - which protects nothing - instead of finishing its work.
BROWSER_KEPT_DATA = """Data a product keeps in its own user's browser belongs to that user. Reading
it with the browser's own tools is not a leak, and encrypting it with a key the
same page holds protects nothing - neither is a finding. What is one: such data
sent somewhere the user did not ask, or read back in a way that runs it as code.
And the harness's own test setup - the files the project contract names as
kept - is not the product: a finding about one of them is not this review's."""


#: Measured on one run: this review asked for `SECRET_KEY` to be moved to the
#: environment, the work order made the product refuse to start without it,
#: and every acceptance test failed - the suite starts the product with only
#: `PORT` and `DATA_DIR` set, as the environment contract tells every stage.
SECRETS_HERE = """A secret is read from the environment with a development default, or generated
at first start and kept under `DATA_DIR`: the tests start the product with
only `PORT` and `DATA_DIR` set. A production secret in the code is a finding;
a remediation keeps the product starting when the variable is unset."""


#: PA.17: measured on one run, five of six findings were not about security (a missing import rated critical, an
#: unused class, comments in a test file), and the next review of the same sprint raised three of them again.
NAME_THE_HARM = """Each finding names its harm in `harm`: who could do what to which data or service.
A finding that names none - an unused name, a comment, a missing import, a style - is
a note about the code: leave `harm` empty, and it is recorded as one, at most low. A
finding listed as already recorded for this sprint is not raised again unless the code
still does the harm it names."""


_SYSTEM_PROMPT = f"""You are the Security Reviewer for this workflow.

Your role is to independently review changed files and tool permissions for
security and reliability issues.

Responsibilities:
- Identify findings with a severity of critical, high, medium, low, or info.
  Here critical and high are blocking and major findings, and a suggestion is info.
- Categorize each finding properly (e.g. isolation, secrets, command_execution).
- State the remediation for every finding.
- Set status to "findings" if any issues are identified, else "passed".
- Document any valid exceptions for local-only features in `local_only_exceptions`.

{SCOPE_DISCIPLINE}

{BROWSER_KEPT_DATA}

{SECRETS_HERE}

{NAME_THE_HARM}

Constraints:
- Do not modify application source code; you only review and record findings.
- Keep the output structured and concise.

Return the response in the required output schema only.

{STRUCTURED_RESPONSE_RULE}
"""


def create_security_reviewer_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
        allow_subdirectories: bool = True,
) -> Any:
    """Create the Security Reviewer role worker."""
    return create_role_agent(
        name=_NAME,
        stage=_STAGE,
        system_prompt=_SYSTEM_PROMPT,
        response_format=SecurityReviewOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root, allow_subdirectories=allow_subdirectories,
        # The workflow renders `docs/security_review.md` from the decision.
        # A reviewer holding a write tool it is not asked to use is the shape
        # that cost three runs a stage each.
        can_write=False,
    )


__all__ = [
    "NAME_THE_HARM",
    "SECURITY_CATEGORIES",
    "as_recorded",
    "names_a_harm",
    "SecurityFinding",
    "SecurityReviewOutput",
    "build_security_review_request",
    "create_security_reviewer_agent",
    "source_coverage",
]
