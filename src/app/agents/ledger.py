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
BLOCKER = "blocker"
DECISION = "decision"

#: A file name shorter than this is too common a word to route a report by.
SHORTEST_NAME = 5

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
    mine = {str(f).strip().removeprefix("./").lstrip("/") for f in files if str(f).strip()}
    return [
        entry for entry in entries
        if (not entry.roles or role in entry.roles)
        and (not entry.files or bool(mine & set(entry.files)))
    ]


CONTRACT_HEADING = (
    "--- The interface contract: the acceptance suite and the release check these lines ---\n"
    "Each line is a route and its status, a page control and its accessible name, or a command and "
    "its exit code, exactly as the product must offer it. Build to them word for word.\n"
)

REPORTS_HEADING = (
    "--- What earlier work orders reported about your files ---\n"
    "Recorded by the harness from their structured answers. A blocker is for you to clear in these "
    "files; a decision is one to build on, not to undo.\n"
)


def rendered(entries: list[Entry], budget: int = SLICE_CHARACTERS, heading: str = CONTRACT_HEADING) -> str:
    """The slice as a block within `budget` characters, the entries left out named; "" when empty."""
    if not entries:
        return ""
    kept: list[str] = []
    used = len(heading)
    left_out: list[str] = []
    for entry in entries:
        line = f"- {entry.text}\n" if entry.kind == INTERFACE_CONTRACT else f"- {entry.kind} ({entry.source}): {entry.text}\n"
        if used + len(line) > budget:
            left_out.append(entry.id)
            continue
        kept.append(line)
        used += len(line)
    tail = (
        f"({len(left_out)} more line(s) left out for room: {', '.join(left_out[:12])}"
        f"{' ...' if len(left_out) > 12 else ''}"
        f"{'; all are in /docs/technical_specification.md' if heading == CONTRACT_HEADING else ''})\n"
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


def from_the_builders(outputs: Any, known_files: Iterable[str], leave_out: str = "") -> list[Entry]:
    """A blocker or decision each finished work order reported, routed by the planned files it names (plan CM.3).

    A builder's `blockers` and `decisions` reached only the milestone review
    (`milestone_reviewer.what_the_specialists_reported`), after every work
    order had run: a later work order building on a file an earlier one had
    changed, or was blocked on, learnt of it a whole review later. One naming
    no planned file has nothing to route by and stays the review's.
    """
    known = sorted({str(f).strip().removeprefix("./").lstrip("/") for f in known_files if str(f).strip()})
    entries = []
    for key, output in sorted((outputs or {}).items()):
        if key == leave_out:
            continue
        for kind, name in ((BLOCKER, "blockers"), (DECISION, "decisions")):
            for at, item in enumerate(getattr(output, name, None) or []):
                text = " ".join(str(item).split())
                named = tuple(
                    path for path in known
                    if path in text or (len(path.rsplit("/", 1)[-1]) >= SHORTEST_NAME and path.rsplit("/", 1)[-1] in text)
                )
                if text and named:
                    entries.append(Entry(kind, f"{key}:{kind}{at + 1}", text, f"{key}", files=named))
    return entries


def with_the_reports(request: dict[str, Any], outputs: Any, work_order: Any, plan: Iterable[Any], leave_out: str = "") -> dict[str, Any]:
    """`request` with what earlier work orders reported about this one's files; as it was when off or nothing applies."""
    if not enabled():
        return request
    try:
        known = [f for order in plan for f in (getattr(order, "files", None) or [])]
        entries = the_slice(from_the_builders(outputs, known, leave_out), "", getattr(work_order, "files", None) or ())
        block = rendered(entries, heading=REPORTS_HEADING)
        if block and request.get("messages") and isinstance(request["messages"][-1].get("content"), str):
            request["messages"][-1]["content"] += "\n\n" + block
    except Exception:  # noqa: BLE001 - the request stands as it was
        pass
    return request


ATTEMPTS_HEADING = (
    "--- Earlier attempts at this defect, as the harness measured them ---\n"
    "Each ended as it says. Do not make a change one of them made and was measured making; "
    "build on what held, and change what did not.\n"
)

#: The most attempts listed; the newest are kept.
MOST_ATTEMPTS_LISTED = 6


def attempt_record(stage: str, fix_result: Any, outcome: str) -> dict[str, Any]:
    """One fix attempt as the ledger keeps it: the stage, the files it changed, what it did, how it ended (plan PH.2)."""
    decisions = [" ".join(str(d).split()) for d in (getattr(fix_result, "decisions", None) or []) if str(d).strip()]
    return {
        "stage": str(stage),
        "files": [str(f) for f in (getattr(fix_result, "changed_files", None) or [])][:8],
        "did": decisions[0][:240] if decisions else "",
        "outcome": " ".join(str(outcome).split())[:300],
    }


def earlier_attempts(defect: Any, defects: Iterable[Any] = ()) -> str:
    """What the fixer of `defect` reads of the attempts before it - its own and the defect it recurs from; "" when none or off.

    A fixer saw an earlier attempt only as a revert sentence appended to the
    defect's actual behaviour, so the next attempt could redo the change that
    had been reverted - measured on earlier runs (the LF.80/82 class).
    """
    if not enabled():
        return ""
    from app.sprint import recurrence_of

    before = list(defects or ())
    try:
        earlier = recurrence_of(defect, [d for d in before if d is not defect])
    except Exception:  # noqa: BLE001 - its own attempts alone
        earlier = None
    attempts = [*(getattr(earlier, "attempts", None) or []), *(getattr(defect, "attempts", None) or [])]
    if not attempts:
        return ""
    lines = []
    for item in attempts[-MOST_ATTEMPTS_LISTED:]:
        files = ", ".join(f"`{f}`" for f in item.get("files") or []) or "no file"
        did = f"; {item['did']}" if item.get("did") else ""
        lines.append(f"- {item.get('stage', '?')}: changed {files}{did} -> {item.get('outcome', '?')}")
    return "\n" + ATTEMPTS_HEADING + "\n".join(lines) + "\n"
