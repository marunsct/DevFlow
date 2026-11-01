"""Which switches acted in a run, read from what they leave in its transcript (plan item 22).

`switches_on` in a KPI row says a switch was deployed, not that it did anything: of 66 switches on in the last measured
run, a handful ever reach their condition. A switch that was on and never acted cannot have moved a KPI, so the gate
(`scripts/loop/switch_gate.py`) must tell "never acted" from "acted and changed nothing". Only a switch with text of
its own in a request or a tool's answer can be told apart; any other is reported as having no signal, never as idle.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

#: Switch -> text only that switch puts in a model request or a tool's answer.
SIGNALS: dict[str, str] = {
    "LESSON_DISTILLER": "LESSONS FROM EARLIER RUNS",
    "ASSUMPTIONS_GATE": "Open questions, answered",
    "SHARED_FACTS": "The facts this work is built and judged under",
    "WHERE_THINGS_STAND": "Where things stand",
    "LOCALISE_FIRST": "You find where in a codebase a failure is caused",
    "VERIFY_AFTER_WRITE": "Your defect is fixed",
    "STABLE_TOOLS": "is withheld at this point of the stage",
    "AGENT_LOOP_FIX_LIMITS": "and no file has changed since the first",
    "MUTANT_CHECK_IN_THE_FIX_STAGE": "The harness made the deliberate change described above",
    "SPEC_DRY_RUN": "the dry run of the suite",
    "IDS_READ_WITHOUT_A_CREATE": "an id the test never created",
    "SETTLE_SPEC_CONTRADICTIONS": "The design review of this specification ended with these findings open",
    "BRIEF_OVER_SPEC_ADDITIONS": "What the specification adds beyond the brief",
}


@dataclass(frozen=True)
class Chance:
    """When a switch should have acted: what held, and how the run's decision log shows that it did."""

    condition: str
    in_the_decisions: re.Pattern[str]


#: Switch -> its chance to act. A switch joins with one row here and its own text in `SIGNALS`.
CHANCES: dict[str, Chance] = {
    # Decided by the harness, with findings named: a person's approval asks for no ruling, by design.
    "SETTLE_SPEC_CONTRADICTIONS": Chance(
        "the design review ended with findings open",
        re.compile(r"\*\*Decision:\*\* build from the latest specification, recording the open points as known risks\n"
                   r"- \*\*Decided by:\*\* auto\b.*\n(?:- \*\*Options:\*\*.*\n)?- \*\*Why:\*\*[^\n]* Open: "),
    ),
}


def _text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str)


def fired(records: Iterable[Any]) -> list[str]:
    """The switches in `SIGNALS` whose text appears in these transcript records, sorted."""
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        kind = record.get("kind")
        if kind == "model_request":
            text = _text(record.get("messages"))
        elif kind == "tool_result":
            text = _text(record.get("content") or record.get("result") or record.get("output"))
        else:
            continue
        seen.update(name for name, needle in SIGNALS.items() if name not in seen and needle in text)
    return sorted(seen)


def on_throughout(records: Iterable[Any]) -> list[str]:
    """The switches every provenance record of the run lists; [] with none. On for part of a run says nothing of the rest."""
    segments = [set(r.get("switches_on") or ()) for r in records if isinstance(r, dict) and r.get("kind") == "provenance"]
    return sorted(set.intersection(*segments)) if segments else []


def silent(on: Iterable[str], records: Iterable[Any], decisions: str) -> list[tuple[str, str]]:
    """(switch, condition) for each of `on` whose chance came in this run and that left no sign of acting."""
    acted = set(fired(records))
    return [(name, CHANCES[name].condition) for name in on
            if name in CHANCES and name not in acted and CHANCES[name].in_the_decisions.search(decisions or "")]


def chance_lines(records: Iterable[Any], decisions: str) -> list[str]:
    """One report line per switch in `CHANCES` that was on throughout: acted, never acted though it could, or no chance."""
    records = list(records)
    on = [name for name in on_throughout(records) if name in CHANCES]
    never = dict(silent(on, records, decisions))
    acted = set(fired(records))
    lines = []
    for name in on:
        if name in never:
            lines.append(f"    !!  {name}: NEVER ACTED, though it was on throughout and {never[name]}: look for a bug")
        elif name in acted:
            lines.append(f"  acted  {name}")
        else:
            lines.append(f"     -  {name}: on, its condition did not arise ({CHANCES[name].condition})")
    return lines


__all__ = ["CHANCES", "Chance", "SIGNALS", "chance_lines", "fired", "on_throughout", "silent"]
