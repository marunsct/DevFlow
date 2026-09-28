"""Security Reviewer Deep Agent.

This role worker independently reviews changes for security and reliability
issues. It can be invoked by the milestone reviewer or used standalone.
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
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE
from app.agents.role_agent import create_role_agent

_STAGE = "security_review"
_NAME = "security_reviewer"


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
    ] = Field(..., description="The category of security or reliability issue.")
    description: str = Field(..., description="What is wrong or missing.")
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

#: Files worth putting in front of a security reviewer. Tests and lockfiles are
#: not where a vulnerability in the product lives.
_WORTH_REVIEWING = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".py", ".html", ".json"}


def _the_source_under_review(changed_files: list[str], repository_root: str) -> str:
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
    """
    root = Path(repository_root)
    shown: list[str] = []
    used = 0
    for name in changed_files:
        path = (root / name).resolve()
        try:
            if not path.is_file() or root not in path.parents and path.parent != root:
                continue
            if path.suffix.lower() not in _WORTH_REVIEWING:
                continue
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if used + len(body) > SOURCE_BUDGET:
            shown.append(f"\n--- {name} (not shown: the budget for this request is full) ---")
            break
        used += len(body)
        shown.append(f"\n--- {name} ---\n{body}")
    if not shown:
        return (
            "None of the changed files could be read for this request. Open "
            "them with your read tools before deciding anything.\n"
        )
    return (
        "--- The source under review, in full ---"
        + "".join(shown)
        + "\n\nThis is the code itself, not a summary. Judge it on what is "
        "here; use your read tools only for something this does not show.\n"
    )


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


def build_security_review_request(
    changed_files: list[str],
    tool_permissions: str,
    repository_root: str,
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input for a security review."""
    files_text = "\n".join(f"- {name}" for name in changed_files) or "- (none reported)"
    brief = (
        WORKSPACE_ROOT_NOTE
        + f"--- Changed files under review ---\n{files_text}\n\n"
        + _the_source_under_review(changed_files, repository_root)
        + _how_text_reaches_the_page(repository_root)
        + f"\n--- Tool permissions context ---\n{tool_permissions}\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


_SYSTEM_PROMPT = f"""You are the Security Reviewer for this workflow.

Your role is to independently review changed files and tool permissions for
security and reliability issues.

Responsibilities:
- Identify findings with a severity of critical, high, medium, low, or info.
- Categorize each finding properly (e.g. isolation, secrets, command_execution).
- State the remediation for every finding.
- Set status to "findings" if any issues are identified, else "passed".
- Document any valid exceptions for local-only features in `local_only_exceptions`.

{SCOPE_DISCIPLINE}

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
    "SecurityFinding",
    "SecurityReviewOutput",
    "build_security_review_request",
    "create_security_reviewer_agent",
]
