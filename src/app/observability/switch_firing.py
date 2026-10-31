"""Which switches acted in a run, read from what they leave in its transcript (plan item 22).

`switches_on` in a KPI row says a switch was deployed, not that it did anything: of 66 switches on in the last measured
run, a handful ever reach their condition. A switch that was on and never acted cannot have moved a KPI, so the gate
(`scripts/loop/switch_gate.py`) must tell "never acted" from "acted and changed nothing". Only a switch with text of
its own in a request or a tool's answer can be told apart; any other is reported as having no signal, never as idle.
"""
from __future__ import annotations

import json
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


__all__ = ["SIGNALS", "fired"]
