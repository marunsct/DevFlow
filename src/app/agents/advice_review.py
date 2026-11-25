"""Each sprint, the specialists consulted before the specification check their advice was built.

Advice the specification adopted is a promise about the product, and nothing
held a sprint to it: the work orders carried some of it, the acceptance suite
measures function, and the milestone review read the code for the sprint's
goal. So advice could fall away quietly - adopted in the specification, built
by nobody.

After each sprint's security review, every consulted specialist whose advice was
adopted is asked, in one structured answer, which of its items this sprint's
work should have built and did not. The UI/UX specialist, when its model reads
images, is also shown the page at a desktop's width and a phone's
(`app.agents.page_screenshots`) and says what a person sees that contradicts
the interface design. What they find goes to the milestone reviewer, who weighs
it with everything else - so a specialist that always finds something cannot by
itself hold a sprint back, and one that finds something real has it decided.

The testing specialist's advice is about the acceptance suite, which the QA lead
reviews before it is locked; it is not checked again here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.role_agent import create_role_agent
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE

#: The roles whose adopted advice is checked against each sprint's work.
REVIEWED_ROLES = ("ui_ux", "database", "backend", "security_reliability")

#: At most this many findings per role, so one review cannot flood the next.
MOST_FINDINGS = 8


class AdviceReview(BaseModel):
    """One specialist's check of its adopted advice against a sprint's work."""

    model_config = ConfigDict(extra="forbid")

    not_built: list[str] = Field(
        default_factory=list,
        description=(
            "One line per adopted item this sprint's work should have built and did not, "
            "starting with the item's id: what is missing, and in which file. Empty when "
            "everything due is built."
        ),
    )
    design_problems: list[str] = Field(
        default_factory=list,
        description=(
            "Only when you were shown screenshots or measured facts of the page: each thing a person "
            "sees that contradicts the interface design, and which screenshot or fact shows it."
        ),
    )


_SYSTEM_PROMPT = (
    "You are a specialist on a product team. Before the specification was written you "
    "advised the architect, and the specification adopted some of your advice. Now a "
    "sprint's work is done, and you check whether what it built follows that advice. "
    "Read the code that was built - the changed files first - before deciding. An item "
    "is due when this sprint, or an earlier one, built the part of the product it is "
    "about; an item about a part a later sprint builds is not missing yet and is not "
    "reported. Report only what you can point to in the code - a file, and what is "
    "there or is not - never a guess. When everything due is built, return empty "
    "lists: an empty answer is a good answer. You write no code and no files.\n\n"
    + STRUCTURED_RESPONSE_RULE
)


def roles_to_review(advice: dict[str, list[str]] | None, specification: Any) -> list[str]:
    """The consulted roles with advice the specification adopted, in the order they were asked.

    With `SPECIALIST_DOMAIN_REVIEW` on, every consulted role: each also reviews its own domain
    (`app.agents.specialist_domain_review`)."""
    from app.agents.specialist_advice import adopted
    from app.agents.specialist_domain_review import roles_consulted

    reviewing = set(roles_consulted(advice, REVIEWED_ROLES))
    return [role for role in REVIEWED_ROLES if role in reviewing or adopted(advice, specification, role)]


def build_advice_review_request(
    role: str,
    adopted_items: Sequence[str],
    sprint_goal: str,
    sprint_scope: str,
    changed_files: Sequence[str],
    held: Sequence[str] = (),
) -> dict[str, list[dict[str, str]]]:
    """The input asking one specialist to check its adopted advice against a sprint.

    `held`: the changed files its project memory holds, numbered (`review_files.held_for_review`, LF.1284), named
    where they are; given only for a product whose files today's memory does not hold. Measured on one medium run:
    the security-and-reliability review, told only the files' names, read 112 times and was summarised 6 times in
    19 calls.
    """
    from app.agents.specialist_advice import ROLE_TITLE

    files = "\n".join(f"- {name}" for name in changed_files) or "- (none recorded)"
    content = (
        f"The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        f"--- Your advice the specification adopted ---\n"
        + ("\n".join(f"- {item}" for item in adopted_items) or "- (none)")
        + f"\n\n--- The sprint just finished ---\n{sprint_goal}\n\n"
        f"{sprint_scope}"
        f"--- The files it changed ---\n{files}\n\n"
        + _where_the_files_are(held)
        + f"As the {ROLE_TITLE.get(role, role)}, check each item due by now against the code "
        "and report the ones not built."
    )
    return {"messages": [{"role": "user", "content": content}]}


def _where_the_files_are(held: Sequence[str]) -> str:
    if not held:
        return ""
    from app.agents.review_files import held_section

    return held_section(held) + "Read with your tools only a changed file not held there.\n\n"


def create_advice_reviewer_agent(
    role: str,
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
    allow_subdirectories: bool = True,
) -> Any:
    """The agent that checks one role's adopted advice - and its own domain, behind `SPECIALIST_DOMAIN_REVIEW`.

    It reads; it writes nothing."""
    from app.agents import specialist_domain_review

    return create_role_agent(
        name=f"{role}_advice_reviewer",
        stage="advice_review",
        system_prompt=_SYSTEM_PROMPT + specialist_domain_review.system_rule(),
        response_format=specialist_domain_review.response_format(),
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root,
        allow_subdirectories=allow_subdirectories,
        can_write=False,
    )


def findings_from(role: str, answer: Any) -> list[str]:
    """A review's findings as lines naming the specialist, at most `MOST_FINDINGS`; then its own-domain defects."""
    from app.agents.specialist_advice import ROLE_TITLE
    from app.agents.specialist_domain_review import lines_of

    title = ROLE_TITLE.get(role, role)
    lines = [
        *(f"[{title}] not built: {' '.join(str(item).split())}" for item in getattr(answer, "not_built", None) or []),
        *(f"[{title}] design: {' '.join(str(item).split())}" for item in getattr(answer, "design_problems", None) or []),
    ]
    return [line for line in lines if line.split(": ", 1)[-1].strip()][:MOST_FINDINGS] + lines_of(role, answer)


def as_sprint_findings(lines: Sequence[str], round_number: int) -> list[dict[str, Any]]:
    """One specialist's findings as one record of the Sprint Record: minor, never gating.

    Kept with the sprint's other findings so they are not lost when the
    milestone reviewer passes over them. Measured on one run: the UI/UX and
    database specialists reported thirteen adopted items not built, the review
    accepted the sprint without a word about any, and the next two sprints
    closed with nothing to build - so the feedback after each action, the empty
    list's message and the desktop layout the specification adopted were never
    built. A finding that does not gate is carried to the next sprint's lead,
    who takes or declines it (`app.sprint.record.carried_from`).

    One record per specialist, not per item: the lead records a decision per
    carried record, and one run's lead, carried fifteen, was sent back twice
    a plan for recording six, then ten, then fourteen.
    """
    kept = [" ".join(str(line).split()) for line in lines if str(line).strip()]
    if not kept:
        return []
    title = kept[0][1:].split("]", 1)[0] if kept[0].startswith("[") else "specialist"
    items = []
    for line in kept:
        said = line.split("] ", 1)[1] if line.startswith("[") and "] " in line else line
        items.append(said[len("not built: "):] if said.startswith("not built: ") else said)
    return [{
        "round": round_number,
        "source": "advice",
        "severity": "minor",
        "description": f"[{title}] {len(items)} adopted item(s) the code does not follow: " + "; ".join(items),
        "remediation": (
            "take each item that still holds into a work order for its role and decline the "
            "rest with the reason - one decision line for the whole list"
        ),
        "gating": False,
    }]


def findings_block(findings: dict[str, list[str]] | None) -> str:
    """The specialists' findings for the milestone reviewer, or "" when there are none."""
    from app.agents.specialist_domain_review import block, is_defect_line

    lines = [line for role in REVIEWED_ROLES for line in (findings or {}).get(role) or [] if not is_defect_line(line)]
    domain = block(findings, REVIEWED_ROLES)
    if not lines:
        return domain
    return (
        "--- What the specialists found of their adopted advice not built ---\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\nEach was advice the specification adopted. Check each against the code: one that "
        "holds is a finding of yours - blocking or major when this sprint's work goes against "
        "what the specification adopted, minor when it is polish; one the code shows built is "
        "not.\n\n"
        + domain
    )


__all__ = [
    "AdviceReview",
    "REVIEWED_ROLES",
    "as_sprint_findings",
    "build_advice_review_request",
    "create_advice_reviewer_agent",
    "findings_block",
    "findings_from",
    "roles_to_review",
]
