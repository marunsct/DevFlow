"""The decision-and-contract ledger: typed records the harness writes and each stage reads its slice of (plan CM.2).

Agents never talk to each other here. What one stage decided reaches another
only as a record the harness wrote from a structured output that already
exists - never reasoning, prose notes or model-written memory, which drift and
mislead a weaker model (Pillar 9). Each stage reads the entries meant for its
role and files, under a hard character budget; an entry left out is named, so
a stage knows the slice is a slice.

The first entry type is the interface contract (EF.11). The architect writes
one strict line per route, page control or command, and the acceptance suite
and the release check are made from those lines - while the builders were
given only their work order's criteria as prose, so a label, route or exit
code the suite looks for was a guess. Measured on one run: the page kept 1 of
its 10 contract lines at release.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

#: Group 2 of the plan is measured before and after (ADR-0010): built while a
#: gate run measures the code without it, so it stays off until that run ends.
#: `DECISION_LEDGER` set to on or off overrides this.
ON_BY_DEFAULT = False

#: The most a stage's slice takes (CM.2: 4k characters per stage under BJ).
SLICE_CHARACTERS = 4_000

INTERFACE_CONTRACT = "interface_contract"

_CRITERION = re.compile(r"^\s*((?:AC|CR)-\d+)\b")


def enabled() -> bool:
    """Whether stages read the ledger (plan CM.2)."""
    value = str(os.environ.get("DECISION_LEDGER") or "").strip().lower()
    if value in ("1", "on", "true", "yes"):
        return True
    if value in ("0", "off", "false", "no"):
        return False
    return ON_BY_DEFAULT


@dataclass(frozen=True)
class Entry:
    """One record: its type, a stable id, the line itself and where it came from."""

    kind: str
    id: str
    text: str
    source: str
    #: The roles it is for; empty means every role.
    roles: tuple[str, ...] = ()
    #: The files it is about; empty means it is not about one file.
    files: tuple[str, ...] = field(default=())


def from_the_specification(specification: Any) -> list[Entry]:
    """The entries the specification gives: one per interface contract line."""
    entries = []
    for at, line in enumerate(getattr(specification, "interface_contract", None) or []):
        text = " ".join(str(line).split())
        if not text:
            continue
        criterion = _CRITERION.match(text)
        entries.append(Entry(
            kind=INTERFACE_CONTRACT,
            id=f"{criterion.group(1) if criterion else 'IC'}#{at + 1}",
            text=text,
            source="the specification's interface contract",
        ))
    return entries


def the_slice(entries: Iterable[Entry], role: str = "", files: Iterable[str] = ()) -> list[Entry]:
    """The entries for this role and these files, in ledger order: everyone's, the role's, and those about its files."""
    mine = {str(f).strip().lstrip("./") for f in files if str(f).strip()}
    return [
        entry for entry in entries
        if (not entry.roles or role in entry.roles)
        and (not entry.files or bool(mine & set(entry.files)))
    ]


def rendered(entries: list[Entry], budget: int = SLICE_CHARACTERS) -> str:
    """The slice as a block within `budget` characters, the entries left out named; "" when empty."""
    if not entries:
        return ""
    heading = (
        "--- The interface contract: the acceptance suite and the release check these lines ---\n"
        "Each line is a route and its status, a page control and its accessible name, or a command and "
        "its exit code, exactly as the product must offer it. Build to them word for word.\n"
    )
    kept: list[str] = []
    used = len(heading)
    left_out: list[str] = []
    for entry in entries:
        line = f"- {entry.text}\n"
        if used + len(line) > budget:
            left_out.append(entry.id)
            continue
        kept.append(line)
        used += len(line)
    tail = (
        f"({len(left_out)} more line(s) left out for room: {', '.join(left_out[:12])}"
        f"{' ...' if len(left_out) > 12 else ''}; all are in /docs/technical_specification.md)\n"
        if left_out else ""
    )
    return heading + "".join(kept) + tail


def for_a_work_order(specification: Any, work_order: Any, role: str = "") -> str:
    """What a builder or fixer of this work order reads from the ledger; "" when off or empty."""
    if not enabled() or specification is None:
        return ""
    entries = the_slice(
        from_the_specification(specification), role, getattr(work_order, "files", None) or (),
    )
    block = rendered(entries)
    return block + "\n" if block else ""
