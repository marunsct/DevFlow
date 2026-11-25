"""Each sprint, the consulted specialists also review this sprint's changed files in their own domain (plan SP.3).

The advice review (`app.agents.advice_review`) asked each specialist one question: which of your adopted items due
this sprint were not built. Nothing asked them to review their domain beyond their own advice. Measured on one medium
run (a service and a page): a lookup by name through a primary-key fetch (a server error on a reused name), another
user's record refused with an exception that became a server error instead of "forbidden", a filter accepted and
ignored, a rate limiter that never recorded an attempt, every origin allowed together with credentials, no index on
the fields looked up and no migrations - each passed every specialist, because none was asked.

Behind `SPECIALIST_DOMAIN_REVIEW` (off until measured: it lengthens each specialist's call), in the same call and so
with no stage of its own, each specialist also reports defects in its own domain in this sprint's changed files: each
with a severity in the milestone review's words, the file and line, and the failure a person or a client of the
product meets. At most `MOST_DEFECTS` a role are kept, the most severe first. A blocking or major one is a gating
finding of the sprint, recorded and shown to the milestone reviewer like the security review's; the rest are one
note per specialist, carried to the next sprint's lead.

Each specialist's checklist is generic: it names no language, framework or kind of product. Stack-specific review
advice belongs in `app.plugins.seed` or a stack pack.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.advice_review import AdviceReview
from app.agents.severity import validator_for
from app.switches import is_on

#: Off in code like every switch; the compose file and each run's own setting decide.
ON_BY_DEFAULT = False

#: What the admin page says this switch does.
explanation = ("After each sprint, every consulted specialist (UI/UX, database, backend, security) also reviews the "
               "sprint's changed files in its own domain, in the same call as its advice check: at most five "
               "defects each, with file, line and the failure a user meets. Blocking and major ones are gating "
               "findings the milestone review weighs; the rest are carried to the next sprint as notes.")

#: At most this many defects a role are kept, the most severe first.
MOST_DEFECTS = 5

#: The milestone review's severity words, most severe first (`app.agents.severity` reads any other word into these).
SEVERITIES = ("blocking", "major", "minor", "suggestion")

#: The severities that gate, as the sprint record's `GATING` reads them.
GATING = ("blocking", "major")

#: The heading of the request's section; only this switch puts it in a request (`observability.switch_firing`).
SECTION_HEADING = "--- Your own domain: defects in this sprint's changed files ---"

#: The heading of the milestone reviewer's block.
BLOCK_HEADING = "--- Defects the specialists found in their own domains this sprint ---"

#: Characters of the specification's own sections shown with a role's checklist.
MOST_SPECIFICATION_CHARACTERS = 2_000

#: What each specialist checks in the changed files, whatever the stack.
CHECKLISTS: dict[str, tuple[str, ...]] = {
    "database": (
        "the schema against the specification's data model: every entity, field, type, required field and relation "
        "it names, and nothing it does not",
        "constraints the data needs - unique, not null, references to a parent - and what the code does on a "
        "duplicate or a missing parent",
        "each lookup by a field other than the primary key: the code uses a lookup by that field (a fetch by "
        "primary key given a name fails), and the field has an index",
        "migrations present when the brief or the specification asks for them, and the schema created the way the "
        "specification says",
        "writes that must succeed or fail together run in one transaction",
    ),
    "backend": (
        "each error mapped to the status code the specification gives - not found, conflict, forbidden, invalid "
        "input - and no exception left unhandled to become a server error",
        "every input the interface accepts is used: a filter, sort, page size or field that is accepted and then "
        "ignored is a defect",
        "request and response shapes, field names and status codes against the specification's interface "
        "contract",
        "inputs validated where they enter, with the error the specification gives",
    ),
    "security_reliability": (
        "credentials: passwords stored with a slow one-way hash, never logged or sent back",
        "cookies and tokens: HttpOnly, Secure and SameSite where they apply, and an expiry",
        "cross-origin settings: never every origin together with credentials",
        "secrets read from configuration, never written in the code",
        "authorisation on each owned resource: reading, changing or deleting another user's record is refused "
        "(forbidden or not found), never a server error and never allowed",
        "every limit the specification gives - attempts, sizes, rates - is enforced: a limiter that never records an "
        "attempt limits nothing",
    ),
    "ui_ux": (
        "every state of each view: loading, empty, error and success, each with a message a person understands",
        "every form field with a visible label, and each error shown next to the field it is about",
        "text contrast at least WCAG AA (4.5:1, 3:1 for large text) and a keyboard focus that can be seen",
        "the layout at a phone's width and a desktop's: nothing cut off and nothing wider than the screen",
        "the interface design in the specification: the layout, names and controls it gives",
    ),
}

#: The specification's sections each specialist's domain is checked against.
_SPECIFICATION_SECTIONS: dict[str, tuple[str, ...]] = {
    "database": ("domain_model",),
    "backend": ("api_and_event_contracts", "interface_contract"),
    "security_reliability": ("security_and_privacy",),
    "ui_ux": ("interface_design",),
}

#: Told to every advice reviewer when the switch is on, after its own rules.
DOMAIN_RULE = (
    "\n\nYou also review this sprint's changed files in your own domain, as a specialist on the team would, beyond "
    "your own advice: the request lists what to check. Report a defect in `domain_defects` only where you can name "
    "the file and line and say what a person or a client of the product meets because of it - the observable "
    "failure, such as a server error on a reused name or another user's record shown - never a preference of style "
    "and never a guess. Severity: blocking when the product cannot do what the brief asks; major when a feature "
    "works wrongly or unsafely for some input; minor for polish; suggestion for an idea. At most five, the most "
    "severe first. Nothing found is a good answer."
)


class DomainDefect(BaseModel):
    """One defect a specialist found in its own domain in a sprint's changed files."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["blocking", "major", "minor", "suggestion"] = Field(
        description="blocking, major, minor or suggestion, as the milestone review uses them.",
    )
    file: str = Field(description="The file the defect is in, relative to the workspace root.")
    line: int | None = Field(default=None, description="The line it is at, when one line shows it.")
    defect: str = Field(description="What the code does wrong there, in one sentence.")
    failure: str = Field(
        description="What a person or a client of the product meets because of it: the request and its wrong answer, "
        "or what the page does wrong.",
    )

    _known_severity = field_validator("severity", mode="before")(validator_for(*SEVERITIES))


class AdviceAndDomainReview(AdviceReview):
    """The advice review's answer with the specialist's own-domain defects."""

    domain_defects: list[DomainDefect] = Field(
        default_factory=list,
        description=(
            "Defects in your own domain in this sprint's changed files, at most five, the most severe first: each "
            "with its file, line and the observable failure. Empty when you found none."
        ),
    )


def enabled() -> bool:
    return is_on("SPECIALIST_DOMAIN_REVIEW", ON_BY_DEFAULT)


def response_format() -> type[AdviceReview]:
    """The advice reviewer's schema: with the domain defects when the switch is on."""
    return AdviceAndDomainReview if enabled() else AdviceReview


def system_rule() -> str:
    """What the advice reviewer is told of its domain review, or "" when the switch is off."""
    return DOMAIN_RULE if enabled() else ""


def roles_consulted(advice: Mapping[str, Any] | None, roles: Sequence[str]) -> list[str]:
    """With the switch on, each of `roles` consulted before the specification, adopted advice or not; else []."""
    if not enabled():
        return []
    return [role for role in roles if role in (advice or {})]


def _flat(text: Any) -> str:
    return " ".join(str(text or "").split())


def _the_specification_s(role: str, specification: Any) -> str:
    lines = [
        _flat(line)
        for section in _SPECIFICATION_SECTIONS.get(role, ())
        for line in getattr(specification, section, None) or []
        if _flat(line)
    ]
    text = "\n".join(f"- {line}" for line in lines)
    if len(text) > MOST_SPECIFICATION_CHARACTERS:
        text = text[:MOST_SPECIFICATION_CHARACTERS].rsplit("\n", 1)[0] + "\n- (the rest is in docs/technical_specification.md)"
    return text


def section(role: str, specification: Any = None) -> str:
    """The request's own-domain section for `role`: its checklist and the specification's lines it checks against."""
    checklist = CHECKLISTS.get(role)
    if not checklist:
        return ""
    from app.agents.specialist_advice import ROLE_TITLE

    said = _the_specification_s(role, specification)
    return (
        f"\n\n{SECTION_HEADING}\n"
        f"Then, as the {ROLE_TITLE.get(role, role)}, read this sprint's changed files for defects in your own "
        "domain, whether or not your advice named them. Check:\n"
        + "\n".join(f"- {item}" for item in checklist)
        + (f"\nWhat the specification says of it:\n{said}" if said else "")
        + "\nReport each in `domain_defects` with its severity, file, line and the observable failure."
    )


def with_the_domain_review(request: dict[str, Any], role: str, specification: Any = None) -> dict[str, Any]:
    """`request` with `role`'s own-domain section after its text, when the switch is on; else `request`. Never raises."""
    try:
        if not enabled():
            return request
        added = section(role, specification)
        messages = list(request.get("messages") or [])
        if not added or not messages or not isinstance(messages[-1].get("content"), str):
            return request
        last = {**messages[-1], "content": messages[-1]["content"] + added}
        return {**request, "messages": [*messages[:-1], last]}
    except Exception:  # noqa: BLE001 - the advice review as it was
        return request


#: `[Title] defect (severity) at file:line: what - fails: failure`, as `lines_of` writes one.
_LINE = re.compile(r"^\[(?P<title>[^\]]+)\] defect \((?P<severity>[a-z]+)\) at (?P<where>\S+): (?P<said>.+)$")


def lines_of(role: str, answer: Any) -> list[str]:
    """The answer's own-domain defects as lines naming the specialist, at most `MOST_DEFECTS`, the most severe first.

    A defect naming no file or saying nothing is left out: it cannot be checked. Never raises.
    """
    try:
        from app.agents.specialist_advice import ROLE_TITLE

        title = ROLE_TITLE.get(role, role)
        found = []
        for defect in getattr(answer, "domain_defects", None) or []:
            where, said = _flat(getattr(defect, "file", "")), _flat(getattr(defect, "defect", ""))
            severity = _flat(getattr(defect, "severity", "")).lower()
            if not where or not said or severity not in SEVERITIES:
                continue
            line = getattr(defect, "line", None)
            if isinstance(line, int) and line > 0:
                where = f"{where}:{line}"
            failure = _flat(getattr(defect, "failure", ""))
            found.append((SEVERITIES.index(severity),
                          f"[{title}] defect ({severity}) at {where}: {said}" + (f" - fails: {failure}" if failure else "")))
        return [text for _, text in sorted(found, key=lambda pair: pair[0])][:MOST_DEFECTS]
    except Exception:  # noqa: BLE001 - nothing found rather than a lost review
        return []


def is_defect_line(line: Any) -> bool:
    """Whether a specialist's finding line is an own-domain defect, not advice not built."""
    return bool(_LINE.match(_flat(line)))


def sprint_findings(lines: Sequence[str], round_number: int) -> list[dict[str, Any]]:
    """A specialist's findings as Sprint Record findings: its advice as the advice review records it, and each
    blocking or major own-domain defect as a gating finding of its own; the lesser ones as one note."""
    from app.agents.advice_review import as_sprint_findings

    advice = [line for line in lines or () if not is_defect_line(line)]
    out = as_sprint_findings(advice, round_number)
    notes: list[str] = []
    title = "specialist"
    for line in lines or ():
        match = _LINE.match(_flat(line))
        if not match:
            continue
        title, severity = match["title"], match["severity"]
        said = f"{match['where']}: {match['said']}"
        if severity in GATING:
            out.append({
                "round": round_number,
                "source": "specialist",
                "severity": severity,
                "description": f"[{title}] {said}",
                "remediation": f"change {match['where']} so the failure it names no longer happens",
                "gating": True,
            })
        else:
            notes.append(f"({severity}) {said}")
    if notes:
        out.append({
            "round": round_number,
            "source": "specialist",
            "severity": "minor",
            "description": f"[{title}] {len(notes)} lesser defect(s) in its domain: " + "; ".join(notes),
            "remediation": "take each that still holds into a work order for its role and decline the rest with the "
                           "reason - one decision line for the whole list",
            "gating": False,
        })
    return out


def block(findings: Mapping[str, Sequence[str]] | None, roles: Sequence[str]) -> str:
    """The own-domain defects for the milestone reviewer, or "" when there are none."""
    lines = [line for role in roles for line in (findings or {}).get(role) or [] if is_defect_line(line)]
    if not lines:
        return ""
    return (
        f"{BLOCK_HEADING}\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\nEach names a file, a line and the failure a person or a client of the product meets. Check each "
        "against the code: one the code shows is a finding of yours at the severity given, or higher when the "
        "failure is worse than it says; one the code does not show is not.\n\n"
    )


__all__ = [
    "AdviceAndDomainReview",
    "BLOCK_HEADING",
    "CHECKLISTS",
    "DOMAIN_RULE",
    "DomainDefect",
    "MOST_DEFECTS",
    "SECTION_HEADING",
    "block",
    "enabled",
    "is_defect_line",
    "lines_of",
    "response_format",
    "roles_consulted",
    "section",
    "sprint_findings",
    "system_rule",
    "with_the_domain_review",
]
