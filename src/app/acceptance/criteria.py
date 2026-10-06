"""The numbered acceptance criteria: what "done" means for this product.

Taken from the brief, the customer's own words, wherever it states them: an
acceptance-criteria section, and the features its requirements list. The intake's
success measures are the fallback for a brief that states neither; they are the
product manager's restatement and include measures no test can check ("user
feedback indicates ease of use"), so they are not mixed in when the brief speaks
for itself.

An interface section is criteria too, line by line: what the product shows,
what each control is called, what it refuses. It is what the customer checks, and
it was not numbered: one run's brief said "A task cannot be added without a
title" there, QA's test of it was refused as naming no criterion, the product
disabled its add control instead, and the customer's check timed out on it.

Constraints - the stack, the storage, a line budget, "no authentication" - are not
criteria: they are checked by the cross-file checks and the reviews, not by a test
that drives the product.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

#: Headings whose bullets are things the product must do.
_CRITERIA_HEADING = re.compile(
    r"acceptance criteria|definition of done|features?|functional requirements|"
    r"user stories|capabilities|must[- ]haves?|requirements|scope|what it (?:must )?do|"
    r"interface",
    re.I,
)
#: Headings whose bullets are not, even when the words above also appear.
_NOT_CRITERIA_HEADING = re.compile(
    r"constraint|non[- ]functional|technical|out of scope|deferred|future|later|"
    r"nice[- ]to[- ]have|assumption|risk|question|background|overview|context",
    re.I,
)
#: Under a broad heading ("Requirements"), a labelled item is a group of
#: criteria only when its label says so; "**Data Storage**: local storage" is a
#: constraint, "**Features**:" a list of things to do.
_A_FEATURE_LABEL = re.compile(r"feature|function|capabilit|user stor|behaviou?r|workflow|must", re.I)
_STRONG_HEADING = re.compile(
    r"acceptance criteria|definition of done|features?|user stories|capabilities|interface", re.I
)

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_BULLET = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")
_LABEL = re.compile(r"^\*\*([^*]+)\*\*\s*:?\s*(.*)$")
_ANNOTATION = re.compile(r"\s*\((?:a success measure|an MVP feature)[^)]*\)\s*$", re.I)


@dataclass(frozen=True)
class Criterion:
    id: str
    text: str
    source: str  # "brief" | "intake"


def _plain(text: str) -> str:
    text = _ANNOTATION.sub("", text)
    text = re.sub(r"\*\*|__|`", "", text)
    return re.sub(r"\s+", " ", text).strip(" .;")


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def from_brief(brief: str) -> list[str]:
    """The behaviours the brief lists, in its own words and order."""
    found: list[str] = []
    heading = ""
    # The open labelled item under a broad heading, and whether it is a group of
    # features: (indent, is_features).
    group: tuple[int, bool] | None = None
    for line in brief.splitlines():
        match = _HEADING.match(line)
        if match:
            heading = match.group(2)
            group = None
            continue
        bullet = _BULLET.match(line)
        if not bullet or not heading:
            continue
        if _NOT_CRITERIA_HEADING.search(heading) or not _CRITERIA_HEADING.search(heading):
            continue
        indent = len(bullet.group(1).expandtabs(4))
        body = bullet.group(2)
        label = _LABEL.match(body)
        if group is not None and indent > group[0]:
            if group[1]:
                found.append(_plain(body))
            continue
        group = None
        if _STRONG_HEADING.search(heading) and not _NOT_CRITERIA_HEADING.search(heading):
            if (label and not label.group(2)) or body.rstrip().endswith(":"):
                # "**Features**:" under "Features", or "The service's JSON
                # interface:" over its endpoints - a group header.
                group = (indent, True)
                continue
            found.append(_plain(body))
            continue
        # A broad heading such as "Requirements".
        if label:
            name, rest = label.group(1), label.group(2)
            if _A_FEATURE_LABEL.search(name):
                if rest:
                    found.append(_plain(rest))
                group = (indent, True)
            else:
                group = (indent, False)
            continue
        found.append(_plain(body))
    return [item for item in found if item]


def number(brief: str, intake: Any = None) -> list[Criterion]:
    """AC-1..n from the brief, or from the intake's success measures when the
    brief lists fewer than two behaviours."""
    texts = from_brief(brief or "")
    source = "brief"
    if len(texts) < 2:
        measures: Iterable[Any] = getattr(intake, "success_measures", None) or []
        texts = [_plain(str(item)) for item in measures if str(item).strip()]
        source = "intake"
    seen: set[str] = set()
    criteria: list[Criterion] = []
    for text in texts:
        key = _key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        criteria.append(Criterion(id=f"AC-{len(criteria) + 1}", text=text, source=source))
    return criteria


def render(criteria: list[Criterion], deferred: dict[str, str] | None = None) -> str:
    """`docs/acceptance_criteria.md`: the list every stage reads."""
    deferred = deferred or {}
    lines = [
        "# Acceptance criteria",
        "",
        "What \"done\" means for this product. Each criterion is proven by the tests in the "
        "acceptance suite whose names carry its id; the harness runs that suite and a sprint is "
        "accepted only when the criteria it delivers pass.",
        "",
    ]
    for criterion in criteria:
        line = f"- **{criterion.id}** {criterion.text}"
        if criterion.id in deferred:
            line += f" - *deferred: {deferred[criterion.id]}*"
        lines.append(line)
    return "\n".join(lines) + "\n"


def as_records(criteria: list[Criterion]) -> list[dict[str, str]]:
    return [{"id": c.id, "text": c.text, "source": c.source} for c in criteria]


def from_records(records: Any) -> list[Criterion]:
    out: list[Criterion] = []
    for record in records or []:
        if isinstance(record, Criterion):
            out.append(record)
        elif isinstance(record, dict) and record.get("id"):
            out.append(Criterion(id=str(record["id"]), text=str(record.get("text", "")), source=str(record.get("source", ""))))
    return out
