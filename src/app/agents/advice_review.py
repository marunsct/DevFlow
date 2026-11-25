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
it with everything else. An adopted item found not built when it was due is
more than an opinion: the milestone sends it back to the lead once, and one
still not built after that is an open gap of the product, in the decision log
and the release's notes (`owed_and_not_built`, SP.1) - so a specialist that
keeps finding the same item cannot keep a sprint going round. What is due comes
from the sprint plan, which places every adopted item in a sprint (`items_due`,
SP.2).

The testing specialist's advice is about the acceptance suite, which the QA lead
reviews before it is locked; it is not checked again here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.role_agent import create_role_agent
from app.agents.specialist_advice import ID_PREFIX
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE

#: The roles whose adopted advice is checked against each sprint's work.
REVIEWED_ROLES = ("ui_ux", "database", "backend", "security_reliability")

#: An advice item's id as the specification records it: "UX-3", "DB-10".
ITEM_ID = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(ID_PREFIX.values()) + r")-\d+(?![0-9])")

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
    "Read the code that was built - the changed files first - before deciding. When the "
    "request says the items listed are due, every one of them is due now. Otherwise an "
    "item is due when this sprint, or an earlier one, built the part of the product it is "
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
    due_because: str = "",
) -> dict[str, list[dict[str, str]]]:
    """The input asking one specialist to check its adopted advice against a sprint.

    `due_because`: why every item listed is due now (`items_due`) - the sprint plan placed it here or earlier, or
    this is the last sprint; "" when the plan places no advice and the specialist judges what is due.

    `held`: the changed files its project memory holds, numbered (`review_files.held_for_review`, LF.1284), named
    where they are; given only for a product whose files today's memory does not hold. Measured on one medium run:
    the security-and-reliability review, told only the files' names, read 112 times and was summarised 6 times in
    19 calls.
    """
    from app.agents.specialist_advice import ROLE_TITLE

    files = "\n".join(f"- {name}" for name in changed_files) or "- (none recorded)"
    content = (
        f"The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        + (f"--- Your advice the specification adopted, due now: {due_because} ---\n" if due_because
           else "--- Your advice the specification adopted ---\n")
        + ("\n".join(f"- {item}" for item in adopted_items) or "- (none)")
        + f"\n\n--- The sprint just finished ---\n{sprint_goal}\n\n"
        f"{sprint_scope}"
        f"--- The files it changed ---\n{files}\n\n"
        + _where_the_files_are(held)
        + f"As the {ROLE_TITLE.get(role, role)}, check each item "
        + ("listed - each one is due now - " if due_because else "due by now ")
        + "against the code and report the ones not built."
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


def findings_from(role: str, answer: Any, due_ids: Iterable[str] | None = None) -> list[str]:
    """A review's findings as lines naming the specialist, at most `MOST_FINDINGS`; then its own-domain defects.

    `due_ids`: the ids of the items the review was asked about. A "not built" line naming another id - an item a
    later sprint builds, or one the specification never adopted - is left out: nobody owes it yet.
    """
    from app.agents.specialist_advice import ROLE_TITLE
    from app.agents.specialist_domain_review import lines_of

    title = ROLE_TITLE.get(role, role)
    lines = [
        *(f"[{title}] not built: {' '.join(str(item).split())}" for item in getattr(answer, "not_built", None) or []),
        *(f"[{title}] design: {' '.join(str(item).split())}" for item in getattr(answer, "design_problems", None) or []),
    ]
    kept = [line for line in lines if line.split(": ", 1)[-1].strip()]
    if due_ids is not None:
        due = set(due_ids)
        kept = [line for line in kept if not item_owed(line) or item_owed(line) in due]
    return kept[:MOST_FINDINGS] + lines_of(role, answer)


def item_owed(line: str) -> str:
    """The id of the adopted item a "not built" finding line names, or "" for any other line.

    The reviewer starts each line with the item's id; a line that names none, or a design line, owes no item.
    """
    marker = "] not built: "
    if marker not in str(line):
        return ""
    match = ITEM_ID.search(str(line).split(marker, 1)[1][:24])
    return match.group(0) if match else ""


def as_sprint_findings(lines: Sequence[str], round_number: int) -> list[dict[str, Any]]:
    """One specialist's findings as records of the Sprint Record: the items owed gate, the rest are minor.

    An adopted item found not built when it was due is a major finding that gates (SP.1): the specification adopted
    it, so the product is not what was specified without it. Measured on one medium run: sprint 2's database
    specialist found eight adopted items not built and its security specialist three, all recorded as minor; the
    milestone review accepted the sprint, the items were carried to the next lead, and the product shipped without
    them. The milestone review sends such items back once (`owed_and_not_built`); one still not built after that is
    an open gap, recorded with the specialist's line.

    A design line, or a "not built" line that names no item, does not gate: it is carried to the next sprint's lead,
    who takes or declines it (`app.sprint.record.carried_from`). One record per specialist and kind, not per item:
    the lead records a decision per carried record, and one run's lead, carried fifteen, was sent back twice a plan
    for recording six, then ten, then fourteen.
    """
    kept = [" ".join(str(line).split()) for line in lines if str(line).strip()]
    if not kept:
        return []
    title = kept[0][1:].split("]", 1)[0] if kept[0].startswith("[") else "specialist"

    def said(line: str) -> str:
        text = line.split("] ", 1)[1] if line.startswith("[") and "] " in line else line
        return text[len("not built: "):] if text.startswith("not built: ") else text

    owed = [said(line) for line in kept if item_owed(line)]
    rest = [said(line) for line in kept if not item_owed(line)]
    records: list[dict[str, Any]] = []
    if owed:
        records.append({
            "round": round_number,
            "source": "advice",
            "severity": "major",
            "description": f"[{title}] {len(owed)} adopted item(s) due and not built: " + "; ".join(owed),
            "remediation": (
                "build each item as a work order for its role, or decline it with the reason - a decline "
                "changes the specification and is recorded in the decision log"
            ),
            "gating": True,
        })
    if rest:
        records.append({
            "round": round_number,
            "source": "advice",
            "severity": "minor",
            "description": f"[{title}] {len(rest)} adopted item(s) the code does not follow: " + "; ".join(rest),
            "remediation": (
                "take each item that still holds into a work order for its role and decline the "
                "rest with the reason - one decision line for the whole list"
            ),
            "gating": False,
        })
    return records


#: A decline and what follows it on the same line.
_DECLINED = re.compile(r"\bdeclin\w*\b\W*(.*)$", re.I)


def declined_with_a_reason(lines: Iterable[str], ids: Iterable[str]) -> dict[str, str]:
    """Each of `ids` that one of `lines` declines with a reason, mapped to that line.

    "DB-4: declined - the brief keeps ids numeric" declines DB-4. A line with no reason after the decline, or whose
    reason is only that no test requires the item, declines nothing: what the specification adopted is for the
    person who uses the product (`app.analysis.work_orders.declined_because_untested`).
    """
    from app.analysis.work_orders import declined_because_untested

    wanted = set(ids)
    found: dict[str, str] = {}
    for line in lines or ():
        text = " ".join(str(line).split())
        decline = _DECLINED.search(text)
        if not decline or len(re.findall(r"[A-Za-z]{2,}", decline.group(1))) < 2:
            continue
        if declined_because_untested([text]):
            continue
        for ident in ITEM_ID.findall(text):
            if ident in wanted and ident not in found:
                found[ident] = text
    return found


def placed_in(sprint: Any) -> list[str]:
    """The advice ids one sprint of a sprint plan builds: its `advice`, and any its scope names."""
    ids: list[str] = []
    for text in [*(getattr(sprint, "advice", None) or []), *(getattr(sprint, "in_scope", None) or [])]:
        for ident in ITEM_ID.findall(str(text)):
            if ident not in ids:
                ids.append(ident)
    return ids


def adopted_to_build(
    advice: dict[str, list[str]] | None, specification: Any, declined: Iterable[str] = ()
) -> list[str]:
    """Every adopted item a sprint builds and a specialist checks, as "ID: item" lines, less those declined since."""
    from app.agents.specialist_advice import adopted

    gone = set(declined or ())
    return [
        line for role in REVIEWED_ROLES for line in adopted(advice, specification, role)
        if line.split(":", 1)[0] not in gone
    ]


def items_due(
    advice: dict[str, list[str]] | None,
    specification: Any,
    role: str,
    sprint_plan: Any,
    sprint_index: int,
    declined: Iterable[str] = (),
) -> tuple[list[str], str]:
    """(one role's adopted items due by the end of this sprint, why they are due), from the sprint plan (SP.2).

    Due: placed in this sprint or an earlier one; in the last sprint, every adopted item not declined. A plan that
    places no advice at all - one made before plans placed it - leaves the specialist to judge, as before: every
    adopted item is listed and the reason is "".
    """
    from app.agents.specialist_advice import adopted

    gone = set(declined or ())
    items = [line for line in adopted(advice, specification, role) if line.split(":", 1)[0] not in gone]
    sprints = list(getattr(sprint_plan, "sprints", None) or [])
    placed = [placed_in(sprint) for sprint in sprints]
    if not items or not any(placed):
        return items, ""
    if sprint_index >= len(sprints) - 1:
        return items, "this is the last sprint, and every adopted item is built by its end"
    due = {ident for ids in placed[: sprint_index + 1] for ident in ids}
    return (
        [line for line in items if line.split(":", 1)[0] in due],
        "the sprint plan places each in this sprint or an earlier one",
    )


def owed_and_not_built(
    found: Mapping[str, Sequence[str]] | None,
    *,
    sent_back: Iterable[str] = (),
    declined: Iterable[str] = (),
) -> tuple[list[str], list[str]]:
    """(the lines owed to send back now, the lines still not built after their one send-back).

    Each line is a specialist's "not built" finding that names an adopted item; one per item, the first kept. An
    item is sent back once in a run: found not built again after that, it is an open gap, so a specialist that
    keeps finding the same item cannot keep a sprint going round. An item the lead declined with a reason is
    neither.
    """
    sent, gone = set(sent_back or ()), set(declined or ())
    now: list[str] = []
    still: list[str] = []
    seen: set[str] = set()
    for role in REVIEWED_ROLES:
        for line in (found or {}).get(role) or []:
            ident = item_owed(line)
            if not ident or ident in seen or ident in gone:
                continue
            seen.add(ident)
            (still if ident in sent else now).append(" ".join(str(line).split()))
    return now, still


def send_back_text(lines: Sequence[str]) -> str:
    """The milestone's request to the lead for adopted items found not built when due."""
    return (
        f"{len(lines)} item(s) of specialist advice the specification adopted are due by this sprint and the "
        "code does not have them. Each specialist checked its own items against the code:\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\nGive each item to a work order for the role that owns it, naming the item's id. An item that no "
        "longer holds may be declined only with the reason, as one line in `review_task_assignments`: "
        "\"<id> -> declined: <why>\". A decline changes the specification and is recorded in the decision "
        "log; that no test checks an item is no reason. Each item is sent back once: one still not built after "
        "this revision is recorded as an open gap of the product."
    )


#: How an adopted item still not built after its one send-back reads among the release's gaps.
OPEN_GAP = "Adopted specialist advice still not built after its one send-back"


def open_gap(line: str, sprint_number: int) -> str:
    """One open gap of the product, with the specialist's own line."""
    return f"{OPEN_GAP} (sprint {sprint_number}): {' '.join(str(line).split())}"


def advice_for_the_lead(items: Sequence[str]) -> str:
    """The section telling a sprint's lead which adopted advice this sprint builds, or ""."""
    if not items:
        return ""
    return (
        "--- Specialist advice the specification adopted, which this sprint builds ---\n"
        + "\n".join(f"- {item}" for item in items)
        + "\nThe sprint plan places each item in this sprint. Give each to a work order for the role that owns "
        "it, naming the item's id in that work order. The specialist who gave it checks the code for it when "
        "the sprint ends, and an item not built is sent back.\n\n"
    )


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
    "ITEM_ID",
    "OPEN_GAP",
    "REVIEWED_ROLES",
    "adopted_to_build",
    "advice_for_the_lead",
    "as_sprint_findings",
    "build_advice_review_request",
    "create_advice_reviewer_agent",
    "declined_with_a_reason",
    "findings_block",
    "findings_from",
    "item_owed",
    "items_due",
    "open_gap",
    "owed_and_not_built",
    "placed_in",
    "roles_to_review",
    "send_back_text",
]
