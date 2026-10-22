"""Lessons proposed from what the harness recorded, never from a model (plans RL.1-RL.3, behind `LESSON_DISTILLER`).

The lessons store (`plugins.lessons`) shows only approved lessons, and lessons
were only ever written by hand. After a run, this reads its transcript for the
signals the harness itself recorded and proposes one lesson per kind for the
run's stack, each to be approved or rejected by the owner:

- a fix reverted for breaking tests that passed before it;
- a package the code imports and no manifest declares;
- a defect that needed more than `ATTEMPTS_WORTH_A_LESSON` fixes.

A proposal seen again refreshes the one already proposed instead of adding a
second; one whose lesson was already approved is counted as recurring (RL.2:
a lesson whose trigger keeps recurring is not working). Approval stays the
owner's (`GET /api/lessons`, `loop.sh lessons`).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Iterable

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `LESSON_DISTILLER` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Fix attempts on one defect past which its kind is worth a lesson.
ATTEMPTS_WORTH_A_LESSON = 2
_PACKAGES = re.compile(r"no manifest declares: (.+?)(?:\(| A clean|$)")


def enabled() -> bool:
    return is_on("LESSON_DISTILLER", ON_BY_DEFAULT)


def proposals(records: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """The lessons a run's transcript records argue for, as {trigger, rule}; one per kind. Never raises."""
    found: dict[str, dict[str, str]] = {}
    attempts: dict[str, int] = {}
    for record in records:
        if record.get("kind") != "defect":
            continue
        event, detail = str(record.get("event") or ""), str(record.get("detail") or "")
        description = str(record.get("description") or "")
        if event == "reverted" and "test" in detail:
            found.setdefault("reverted", {
                "trigger": "a fix reverted for breaking tests that passed before it",
                "rule": "Before answering, run the whole unit and acceptance suites, not only the failing test: "
                        "a change that makes one test pass by breaking another is reverted.",
            })
        if "no manifest declares" in description:
            # The rule is the stack's, so it names no one product's packages.
            found.setdefault("undeclared", {
                "trigger": "code imports a package no manifest declares",
                "rule": "Add every package the code imports to the project's manifest in the same change.",
            })
        if event in ("left open", "reverted", "fixed"):
            # One defect is fixed across rounds under the same description, not the same (round, index).
            key = description or str(record.get("index"))
            attempts[key] = attempts.get(key, 0) + 1
    if any(count > ATTEMPTS_WORTH_A_LESSON for count in attempts.values()):
        found.setdefault("attempts", {
            "trigger": f"a defect that needed more than {ATTEMPTS_WORTH_A_LESSON} fix attempts",
            "rule": "Read the failing test's assertion and the code path it reaches before the first edit; "
                    "change what the evidence names, and run that test again before answering.",
        })
    return list(found.values())


def the_stack(root: str | Path) -> str:
    """The run's stack as the lessons store keys it: the pack that scaffolded it, else ""."""
    try:
        from app.stacks import contract

        record = contract.read(root) or {}
        return str(record.get("pack") or "")
    except Exception:  # noqa: BLE001
        return ""


def distil(transcript: str | Path, root: str | Path, *, path: Path | None = None) -> list[dict[str, Any]]:
    """Propose this run's lessons; the lessons proposed or refreshed. Nothing when off. Never raises."""
    if not enabled():
        return []
    try:
        from app.plugins import lessons

        stack = the_stack(root)
        if not stack:
            return []
        records = []
        for line in Path(transcript).read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
        done = []
        for proposal in proposals(records):
            lesson = lessons.propose(stack, proposal["trigger"], proposal["rule"], 1, source="harness", path=path)
            if lesson.get("status") == "approved":
                # Once per run: the distiller runs with every `loop.sh kpi`.
                lesson = lessons.recurred(lesson["id"], run_id=Path(transcript).stem, path=path)
            done.append(lesson)
        return done
    except Exception:  # noqa: BLE001 - a lesson is never worth a failed run
        logger.warning("Could not distil this run's lessons", exc_info=True)
        return []


__all__ = ["ATTEMPTS_WORTH_A_LESSON", "ON_BY_DEFAULT", "distil", "enabled", "proposals", "the_stack"]
