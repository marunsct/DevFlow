"""What the brief's requirement and constraint lines ask the product to have, accounted for by a criterion (plan PQ.1).

The criteria are the brief's acceptance criteria, its features and its interface section
(`app.acceptance.criteria`). Its other requirement lines and its constraints were not read: "the stack, the storage,
a line budget" are choices of how the product is built, held by the reviews. Some of those lines name something the
product must have, though. Measured on a medium brief: "User Interface: Modern web application with responsive
design", "Frontend: React or Vue.js", "Database migrations required" and "Docker containerization" became no
criterion, the sprint plan put the interface out of scope in every sprint, and the product shipped with no interface
at all - nothing the run measured said anything was missing.

So each line is read for the kinds of thing a product can be asked to have (`KINDS`): an interface a person uses,
database migrations, a container definition, API documentation, a CI pipeline. A kind a line asks for that no
criterion carries yet becomes one criterion, in the brief's own words (the first line asking for it); a kind an
existing criterion carries adds nothing, so a brief that already numbers what it asks for - an interface section,
"Responsive design for mobile and desktop" - keeps its criteria as they were. A line that rules a kind out ("No
Docker", "migrations not required") asks for nothing. A line naming none of the kinds is a choice of how the
product is built and stays a constraint. Deterministic: no model reads the brief here.

What was added, and what already carried each line, is recorded as a decision (`decision`); an added criterion the
release cannot prove ships named as a scope cut, like any other (`app.graph.delivery`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Kind:
    """A kind of thing a product can be asked to have."""

    name: str
    #: A requirement line asking for it.
    asks: re.Pattern[str]
    #: A criterion already carrying it (a line asking for it carries it too).
    carries: re.Pattern[str] | None = None
    #: A line that names it but is about something else ("User Interface: a command-line program").
    other_thing: re.Pattern[str] | None = None

    def asked_by(self, line: str) -> bool:
        text = str(line or "")
        return bool(self.asks.search(text)) and not (self.other_thing and self.other_thing.search(text)) \
            and not _RULED_OUT.search(text)

    def carried_by(self, criterion: str) -> bool:
        text = str(criterion or "")
        if self.other_thing and self.other_thing.search(text):
            return False
        return bool(self.asks.search(text) or (self.carries and self.carries.search(text)))


_I = re.I
KINDS: tuple[Kind, ...] = (
    Kind(
        "an interface a person uses",
        re.compile(r"\buser interface\b|\bweb[- ](?:app|application|interface|page|ui|front[- ]?end)s?\b|"
                   r"\bweb[- ]based\b|\bfront[- ]?end\b|(?-i:\bUI\b)|\bresponsive\b|\bsingle[- ]page\b|"
                   r"\bbrowsers?\b", _I),
        re.compile(r"\bpages?\b|\bscreens?\b|\blabell?ed\b|\btext (?:field|area|box)\b|\bforms?\b|\bmobile\b|"
                   r"\bdesktop\b|\bwindows?\b", _I),
        re.compile(r"\bcommand[- ]line\b|(?-i:\bCLI\b)|\bterminal\b|\bconsole\b", _I),
    ),
    Kind("database migrations", re.compile(r"\bmigrations?\b", _I)),
    Kind("a container definition", re.compile(r"\bdocker\w*|\bcontaineri[sz]\w*|\bcontainers?\b|\bkubernetes\b", _I)),
    Kind("API documentation",
         re.compile(r"\b(?:api|interface|endpoints?)\s+(?:documentation|docs|reference)\b|\bswagger\b|"
                    r"\bopen\s?api\b", _I)),
    Kind("a CI pipeline", re.compile(r"(?-i:\bCI\b)|\bcontinuous (?:integration|delivery|deployment)\b", _I)),
)

#: A line that rules out what it names: "No Docker", "Database migrations not required", "without a container".
_RULED_OUT = re.compile(r"\b(?:no|not|without|never|none)\b|n't\b", re.I)


@dataclass(frozen=True)
class Requirement:
    """One requirement or constraint line of the brief and how it is accounted for."""

    text: str
    #: The kinds it asks for; () for a choice of how the product is built.
    kinds: tuple[str, ...]
    #: The criterion carrying it, "" for a constraint.
    criterion: str = ""


def _asked(line: str) -> tuple[Kind, ...]:
    return tuple(kind for kind in KINDS if kind.asked_by(line))


def to_add(brief: str, criteria: list[str]) -> list[str]:
    """The brief's lines to add as criteria after `criteria`: one per kind asked for that no criterion carries."""
    from app.acceptance.criteria import requirement_lines

    lines = requirement_lines(brief or "")
    held = [str(text) for text in criteria or []]
    added: list[str] = []
    for kind in KINDS:
        if any(kind.carried_by(text) for text in held):
            continue
        line = next((line for line in lines if kind.asked_by(line)), None)
        if line is None or line in added:
            continue
        added.append(line)
        held.append(line)
    return added


def accounted_for(brief: str, criteria: Any) -> list[Requirement]:
    """Each requirement or constraint line of the brief, with the criterion carrying what it asks for."""
    from app.acceptance.criteria import requirement_lines

    numbered = [(str(getattr(c, "id", "")), str(getattr(c, "text", ""))) for c in criteria or []]
    out: list[Requirement] = []
    for line in requirement_lines(brief or ""):
        kinds = _asked(line)
        if not kinds:
            out.append(Requirement(line, ()))
            continue
        exact = next((ident for ident, text in numbered if text == line), "")
        carrier = exact or next(
            (ident for ident, text in numbered if any(kind.carried_by(text) for kind in kinds)), "")
        out.append(Requirement(line, tuple(kind.name for kind in kinds), carrier))
    return out


def decision(brief: str, criteria: Any) -> dict[str, Any] | None:
    """The decision record's fields when lines of the brief's requirements or constraints were added as criteria, else
    None: what was added, what already carried each other line asking for something, and what stays a constraint."""
    numbered = list(criteria or [])
    rows = accounted_for(brief, numbered)
    texts = {str(getattr(c, "text", "")): str(getattr(c, "id", "")) for c in numbered}
    added = [row for row in rows if row.kinds and texts.get(row.text) == row.criterion and row.criterion]
    if not added:
        return None
    lines = []
    for row in rows:
        if not row.kinds:
            lines.append(f"- \"{row.text}\": a choice of how the product is built, held by the reviews.")
        elif row in added:
            lines.append(f"- \"{row.text}\": added as {row.criterion} ({', '.join(row.kinds)}).")
        elif row.criterion:
            lines.append(f"- \"{row.text}\": carried by {row.criterion}.")
        else:
            lines.append(f"- \"{row.text}\": asks for {', '.join(row.kinds)}, and no criterion carries it.")
    ids = ", ".join(row.criterion for row in added)
    return {
        "point": "acceptance_tests",
        "question": "Which of the brief's requirement and constraint lines are acceptance criteria?",
        "decision": f"{ids} added from the brief's requirements and constraints",
        "options": [f"{ids} added from the brief's requirements and constraints",
                    "the owner says one is not built in this release"],
        "rationale": (
            "Each line of the brief that names something the product must have is a criterion, so every sprint plan "
            "places it and the suite proves it; one the release cannot prove ships named as a scope cut, not built "
            "in this release.\n" + "\n".join(lines)
        ),
    }


__all__ = ["KINDS", "Kind", "Requirement", "accounted_for", "decision", "to_add"]
