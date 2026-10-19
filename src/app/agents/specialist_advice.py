"""What the specialists advise before the technical specification is written.

The architect wrote the specification alone, and nothing in it described the
interface: its sections are scope, components, data, contracts, security,
testing and deployment. The UI/UX specialist then built from work orders drawn
against functional acceptance tests. Measured over the last 26 stored products:
20 still shipped the scaffold's 11-line stylesheet, untouched by any stage - a
page with the browser's own defaults and nothing designed.

So the specialists a product needs are asked first, each in one structured
answer: the UI/UX specialist when the product has an interface, the database
specialist when it keeps data of its own, the backend specialist when it serves
requests, the security and reliability specialist when it serves requests or its
brief is about sign-in, people's data, money or files, and the testing specialist
- per acceptance criterion, on how each can be proven - whenever it has criteria.
The specification then takes up or declines each item, by id, and a
product with an interface gets an `interface_design` section built from the
UI/UX advice - which the lead's work orders and the UI/UX specialist's brief
carry from there.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.role_agent import create_role_agent
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE

logger = logging.getLogger(__name__)

#: The roles consulted, in the order they are asked.
ADVICE_ROLES = ("ui_ux", "database", "backend", "security_reliability", "testing")

#: Each role's prefix for the ids the specification answers by.
ID_PREFIX = {
    "ui_ux": "UX", "database": "DB", "backend": "BE", "security_reliability": "SR", "testing": "TS",
}

#: How a role is named to the architect.
ROLE_TITLE = {
    "ui_ux": "UI/UX specialist",
    "database": "database specialist",
    "backend": "backend specialist",
    "security_reliability": "security and reliability specialist",
    "testing": "testing specialist",
}

#: At most this many items per role: enough to design from, few enough that
#: each one is a decision rather than a list to skim.
MOST_RECOMMENDATIONS = 10

#: A product kind that has an interface a person uses. A program run from a
#: terminal has one too - its commands, options, output and messages.
_HAS_AN_INTERFACE = frozenset({"browser_app", "fullstack", "cli"})

#: A product kind that serves requests.
_SERVES_REQUESTS = frozenset({"http_api", "fullstack"})

#: A `database` value that names no store of the product's own.
_NO_STORE = re.compile(r"^(?:|-|n/?a\b.*|none\b.*|no\b.*|not (?:applicable|needed|required)\b.*)$", re.I)

#: What in a brief needs a security and reliability specialist: people signing
#: in, data about them or their money, files they send, or an API open to
#: callers. Matched in the brief's own words, and not where the brief rules it
#: out - "No authentication required" asks for none.
_SENSITIVE = re.compile(
    r"\b(?:sign(?:[- ])?(?:in|up|on)|log(?:[- ])?in|logout|passwords?|accounts?|authenticat\w*|"
    r"authori[sz]\w*|sessions?|personal (?:data|information|details)|e-?mail address\w*|"
    r"payments?|credit cards?|billing|checkout|uploads?|attachments?|public api|api keys?|tokens?)\b",
    re.I,
)
_RULED_OUT = re.compile(r"\b(?:no|not|without|none|never|n't)\b[^.;:\n]*$", re.I)


def _asks_for_something_sensitive(text: str) -> bool:
    """Whether the brief asks for something a security specialist must see, not ruled out."""
    for match in _SENSITIVE.finditer(text or ""):
        before = text[max(0, text.rfind("\n", 0, match.start()) + 1):match.start()]
        if not _RULED_OUT.search(before):
            return True
    return False


class SpecialistAdvice(BaseModel):
    """One specialist's advice for the technical specification."""

    model_config = ConfigDict(extra="forbid")

    recommendations: list[str] = Field(
        ...,
        min_length=1,
        max_length=MOST_RECOMMENDATIONS,
        description=(
            "Each one concrete sentence the architect can adopt or decline and a "
            "reviewer can check against the product - never a general aim."
        ),
    )


def roles_to_consult(stack: Any, brief_text: str = "") -> list[str]:
    """The specialists this product needs to hear from, by what it is.

    UI/UX when it has an interface, database when its stack keeps data of its
    own, backend when it serves requests. Never raises: with nothing to judge
    by, nobody is consulted and the architect works as before.
    """
    try:
        from app.stacks import product_kind

        kind = product_kind(stack, brief_text)
        database = str(getattr(stack, "database", "") or "").strip()
    except Exception:  # noqa: BLE001
        return []
    roles = []
    if kind in _HAS_AN_INTERFACE:
        roles.append("ui_ux")
    if stack is not None and not _NO_STORE.match(database):
        roles.append("database")
    if kind in _SERVES_REQUESTS:
        roles.append("backend")
    # An API anyone can call, or a brief about people's sign-in, data, money
    # or files.
    if kind in _SERVES_REQUESTS or _asks_for_something_sensitive(brief_text):
        roles.append("security_reliability")
    # Every product with acceptance criteria: each is proven by an automated
    # test, and most locked suites that could not pass were criteria hard to
    # test as written - a test needing data it never made, a control that left
    # the page as it was confirmed, a test written inside another.
    if stack is not None and _criteria_of(brief_text):
        roles.append("testing")
    return roles


def _criteria_of(brief_text: str) -> list[Any]:
    """The brief's acceptance criteria as the suite will number them, or []."""
    try:
        from app.acceptance.criteria import number

        return list(number(brief_text or ""))
    except Exception:  # noqa: BLE001
        return []


_WHAT_TO_COVER = {
    "ui_ux": (
        "how a person meets the product. The layout at a phone's width and at a "
        "desktop's, and what changes between them; the visual hierarchy - what is "
        "seen first and what is secondary; every control and every item shown, with "
        "each of its states - empty, focused, hovered, disabled, invalid, finished - "
        "and how each looks; the feedback after each action; what is shown when there "
        "is nothing yet; accessibility - a label for every control, use by keyboard "
        "alone, focus that can be seen, enough contrast; and a small visual style the "
        "whole interface keeps to: a spacing scale, type sizes, a few colours with "
        "their uses. For a program run from a terminal the interface is its commands, "
        "options, output and messages: how each reads, and how an error says what to "
        "do next."
    ),
    "database": (
        "the data the product keeps. Each kind of record, its fields and their types, "
        "how a record is identified, which fields are required and how each is "
        "validated, how the data is stored, loaded and saved, what happens when "
        "stored data is missing, malformed or written by an older version, and what "
        "must stay consistent between records."
    ),
    "backend": (
        "the service. Each operation, what it accepts and what it returns, how input "
        "is validated, the error responses and status codes, what happens when two "
        "requests change the same thing at once, configuration, and limits."
    ),
    "security_reliability": (
        "what must be protected and how it fails safely. Who may do what, and how that "
        "is checked on every operation; how people sign in and how a session ends; how "
        "every input is validated and every output encoded; where secrets live and that "
        "none is written to a log or sent to the client; how files sent in are checked "
        "and stored; limits on how often and how much; and what happens on a timeout, a "
        "crash or a write cut off half way, so no data is lost or left half changed."
    ),
    "testing": (
        "how each acceptance criterion below can be proven by an automated test through "
        "the product's real interface. Start each recommendation with the id of the "
        "criterion it is for. Say the exact name a test finds each control or field by - "
        "the one the brief gives; the data a test must create for itself first, since "
        "every test starts from an empty product; anything that changes with time or "
        "chance and how it is held still; what must be reset between tests; what result "
        "a person would see that the test asserts on; and where an action takes its own "
        "control off the page - assert on what remains, rather than confirm the control."
    ),
}

_SYSTEM_PROMPT = (
    "You are a specialist on a product team, asked for your advice before the "
    "architect writes the technical specification. You advise; you write no code "
    "and no files. Keep within the brief: the names it gives controls, fields and "
    "messages are fixed, its required behaviour is fixed, and its constraints - "
    "what may be depended on, how large the product may be - hold. Advice that "
    "would break any of them is wrong. Nor may advice add a rule the brief does not "
    "state that refuses or limits what a person may do - one value unique among "
    "records, a longest or shortest length, a field the brief leaves optional made "
    "required: such a rule makes a different product, and the customer's own checks "
    "fail on it. And every control the brief names stays usable: an action that cannot "
    "go ahead is refused when it is tried, with a message saying why, never by "
    "disabling the control. Each recommendation is one concrete sentence "
    "the architect can adopt or decline and a reviewer can check against the "
    "product: name what, where and how - never a general aim such as 'make it "
    "intuitive' or 'follow best practices'. Give the few that matter most, at most "
    f"{MOST_RECOMMENDATIONS}.\n\n" + STRUCTURED_RESPONSE_RULE
)


def build_advice_request(role: str, brief_text: str, intake_text: str, stack_text: str) -> dict[str, list[dict[str, str]]]:
    """The input asking one specialist for its advice."""
    criteria = ""
    if role == "testing":
        numbered = _criteria_of(brief_text)
        if numbered:
            criteria = (
                "--- The acceptance criteria, as the suite will number them ---\n"
                + "\n".join(f"- {c.id}: {c.text}" for c in numbered) + "\n\n"
            )
    content = (
        f"--- The brief ---\n{brief_text}\n\n"
        f"--- The product intake ---\n{intake_text}\n\n"
        f"--- The technology stack chosen ---\n{stack_text}\n\n"
        f"{criteria}"
        f"As the {ROLE_TITLE[role]}, advise the architect on {_WHAT_TO_COVER[role]}"
    )
    return {"messages": [{"role": "user", "content": content}]}


def create_specialist_advice_agent(
    role: str,
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
    allow_subdirectories: bool = True,
) -> Any:
    """The agent that gives one role's advice. It writes nothing."""
    return create_role_agent(
        name=f"{role}_advisor",
        stage="specialist_consultation",
        system_prompt=_SYSTEM_PROMPT,
        response_format=SpecialistAdvice,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root,
        allow_subdirectories=allow_subdirectories,
        can_write=False,
    )


def advice_from(answer: Any) -> list[str]:
    """The recommendations an answer gave, cleaned of blanks and repeats.

    Without one that disables a control until something is done, which the
    advisor is told never to give. Measured on two runs: the advice was given
    anyway and adopted, the page check then demanded the opposite, and in the
    second - the specification's own text clean - the sprint's advice check
    carried "not disabled until the title holds text" forward as owed work.
    """
    kept: list[str] = []
    for item in getattr(answer, "recommendations", None) or []:
        text = " ".join(str(item).split())
        if not text or text in kept:
            continue
        if disables_on_a_condition(text):
            logger.info("Advice left out, it disables a control until something is done: %s", text[:160])
            continue
        kept.append(text)
    return kept[:MOST_RECOMMENDATIONS]


def _numbered(advice: dict[str, list[str]]) -> list[tuple[str, str, str]]:
    """(role, id, recommendation) for every item, in the order the roles were asked."""
    return [
        (role, f"{ID_PREFIX[role]}-{number}", item)
        for role in ADVICE_ROLES
        for number, item in enumerate(advice.get(role) or [], start=1)
    ]


def advice_block(advice: dict[str, list[str]] | None) -> str:
    """The advice, numbered, with what the architect must do with it; "" when there is none."""
    items = _numbered(advice or {})
    if not items:
        return ""
    lines = ["--- What the specialists advise, before you write the specification ---"]
    for role in ADVICE_ROLES:
        mine = [(ident, text) for owner, ident, text in items if owner == role]
        if mine:
            lines.append(f"The {ROLE_TITLE[role]}:")
            lines.extend(f"- {ident}: {text}" for ident, text in mine)
    lines.append(
        "Decide on each item: adopt it into the section it belongs to, or decline it "
        "with the reason - the brief or the stack rules it out, it adds a rule the brief "
        "does not state that refuses or limits what a person may do, or it costs more than "
        "it gives. Record one line per item in `specialist_advice_decisions`, starting with "
        "its id: \"UX-1: adopted - interface_design\", or \"DB-2: declined - <why>\"."
    )
    if advice and advice.get("ui_ux"):
        lines.append(
            "The adopted UI/UX advice is the `interface_design` section: the layout at a "
            "phone's width and a desktop's, each control's states, the feedback after "
            "each action, accessibility, and the visual style - concrete enough that the "
            "specialist who builds the interface and a reviewer who looks at it can check "
            "one against the other."
        )
    return "\n".join(lines) + "\n\n"


def unanswered(specification: Any, advice: dict[str, list[str]] | None) -> list[str]:
    """The advice ids the specification neither adopts nor declines."""
    said = " ".join(str(line) for line in getattr(specification, "specialist_advice_decisions", None) or [])
    return [
        ident for _, ident, _ in _numbered(advice or {})
        if not re.search(rf"(?<![A-Za-z0-9]){re.escape(ident)}(?![0-9])", said)
    ]


def adopted(advice: dict[str, list[str]] | None, specification: Any, role: str) -> list[str]:
    """One role's advice the specification adopted, as "ID: item" lines.

    An item counts as adopted unless its line in `specialist_advice_decisions`
    says it was declined; an item with no line at all is the architect's to
    answer (`unanswered`), and is passed on rather than lost.
    """
    lines = [str(line) for line in getattr(specification, "specialist_advice_decisions", None) or []]
    kept = []
    for owner, ident, text in _numbered(advice or {}):
        if owner != role:
            continue
        said = [
            line for line in lines
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(ident)}(?![0-9])", line)
        ]
        if any(re.search(r"\bdeclin", line, re.I) for line in said):
            continue
        # Advice the harness rules out is never owed, even where it was
        # adopted before `advice_from` left it out. See `advice_from`.
        if disables_on_a_condition(text):
            continue
        kept.append(f"{ident}: {text}")
    return kept


#: A control disabled on a condition: "disabled until the title holds text".
#: A control disabled on a condition: "disabled until the title holds text",
#: "if invalid, the form disables the add control", "enabled only once ...".
#: Two parts on one line, in either order: one run's specification said "If
#: invalid, the form disables" - a verb form and an order the first pattern
#: did not know - and its product shipped the control disabled on load.
_DISABLES = re.compile(
    r"\bdisabl(?:e|es|ed|ing)\b|\baria-disabled\b"
    r"|\benabled?\b[^.;\n]{0,60}?\bonly (?:when|once|if|after)\b"
    r"|\b(?:becomes|is|are|stays?) (?:only )?(?:enabled|active|clickable) (?:only )?(?:when|once|after|if)\b",
    re.I,
)
_ON_A_CONDITION = re.compile(
    r"\b(?:until|unless|while|whenever|when|if|once|invalid|empty|blank|missing)\b", re.I
)


#: How the disabled state looks, not a rule that disables anything: "a light gray
#: background when disabled", "the disabled state", "disabled inputs are dimmed".
#: Measured on one run: input styling advice - "a red border when invalid, and a
#: light gray background when disabled" - was left out as if it disabled a control
#: until the input was valid.
_THE_DISABLED_STATE = re.compile(
    r"\b(?:when|while|if)\s+(?:it\s+is\s+|they\s+are\s+)?disabled\b"
    r"|\bdisabled\s+(?:state|styles?|styling|appearance|look|inputs?|fields?|controls?)\b",
    re.I,
)


def disables_on_a_condition(text: str) -> bool:
    """Whether any line of `text` disables a control on a condition; how a disabled control looks is not one."""
    return any(
        _DISABLES.search(cleaned) and _ON_A_CONDITION.search(cleaned)
        for line in re.split(r"(?<=[.;])\s+|\n", str(text or ""))
        for cleaned in [_THE_DISABLED_STATE.sub(" ", line)]
    )


def controls_disabled_until_something(specification: Any) -> list[str]:
    """The specification's lines that disable a control until a condition holds.

    Measured on one run: the UI/UX advice, told never to disable a control the
    brief names, advised that "Add task" be disabled until its title held text;
    the architect adopted it, code review then demanded it, the harness's page
    check demanded the opposite, and the sprint's fixers undid each other until
    its attempts ran out.
    """
    lines: list[str] = []
    try:
        fields = specification.model_dump() if hasattr(specification, "model_dump") else dict(specification or {})
    except Exception:  # noqa: BLE001 - nothing readable, nothing found
        return []
    for value in fields.values():
        for item in value if isinstance(value, list) else [value]:
            for line in str(item or "").splitlines():
                if disables_on_a_condition(line):
                    lines.append(" ".join(line.split()))
    return lines


def what_the_specification_owes(specification: Any, advice: dict[str, list[str]] | None) -> list[str]:
    """Why the specification has not answered the specialists, or [] when it has."""
    problems = []
    missing = unanswered(specification, advice)
    if missing:
        problems.append(
            "`specialist_advice_decisions` does not answer "
            + ", ".join(missing)
            + ": give each one line, starting with its id, saying it is adopted and where, "
            "or declined and why."
        )
    disabling = controls_disabled_until_something(specification)
    if disabling:
        problems.append(
            "It disables a control until something is done: "
            + "; ".join(f"\"{line[:160]}\"" for line in disabling[:3])
            + ". Every control the brief names stays usable: an action that cannot go ahead is "
            "refused when it is tried, with a message saying why. Write it so, wherever it says this."
        )
    if advice and advice.get("ui_ux") and not [
        line for line in getattr(specification, "interface_design", None) or [] if str(line).strip()
    ]:
        problems.append(
            "`interface_design` is empty, and this product has an interface: write it from "
            "the UI/UX advice you adopted - layout at a phone's width and a desktop's, each "
            "control's states, feedback, accessibility and the visual style."
        )
    return problems


__all__ = [
    "ADVICE_ROLES",
    "adopted",
    "SpecialistAdvice",
    "advice_block",
    "advice_from",
    "build_advice_request",
    "create_specialist_advice_agent",
    "roles_to_consult",
    "unanswered",
    "what_the_specification_owes",
]
