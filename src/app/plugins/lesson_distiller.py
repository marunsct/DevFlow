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

A lesson rests on facts: each quotes what the transcripts recorded and counts
the runs that recorded it, and a rule says only what the harness does. One rule
here said any change breaking a test is reverted, while `net_gain` and
`unit_tests_disagree` keep some, and it reached prompts on every stack approved.
`check_the_evidence` holds the lessons on record to the same standard.
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
#: How a revert names a test it broke. A product that stopped building or a language-service finding names none.
_A_BROKEN_TEST = re.compile(r"\b(?:unit|acceptance): ")


def enabled() -> bool:
    return is_on("LESSON_DISTILLER", ON_BY_DEFAULT)


def proposals(records: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """The lessons a run's transcript records argue for, as {trigger, rule, evidence}; one per kind. Never raises."""
    found: dict[str, dict[str, str]] = {}
    attempts: dict[str, int] = {}
    for record in records:
        if not isinstance(record, dict) or record.get("kind") != "defect":
            continue
        event, detail = str(record.get("event") or ""), str(record.get("detail") or "")
        description = str(record.get("description") or "")
        if event == "reverted" and _A_BROKEN_TEST.search(detail):
            found.setdefault("reverted", {
                "trigger": "a fix reverted for breaking tests that passed before it",
                "rule": "Before answering, run the unit and acceptance suites, not only the failing test: "
                        "the harness runs both after a change and weighs what it broke against what it gained.",
                "evidence": detail,
            })
        if "no manifest declares" in description:
            # The rule is the stack's, so it names no one product's packages.
            found.setdefault("undeclared", {
                "trigger": "code imports a package no manifest declares",
                "rule": "Add every package the code imports to the project's manifest in the same change.",
                "evidence": description,
            })
        if event in ("left open", "reverted", "fixed"):
            # One defect is fixed across rounds under the same description, not the same (round, index).
            key = description or str(record.get("index"))
            attempts[key] = attempts.get(key, 0) + 1
    most = max(attempts, key=lambda key: attempts[key], default="")
    if most and attempts[most] > ATTEMPTS_WORTH_A_LESSON:
        found.setdefault("attempts", {
            "trigger": f"a defect that needed more than {ATTEMPTS_WORTH_A_LESSON} fix attempts",
            "rule": "Read the failing test's assertion and the code path it reaches before the first edit; "
                    "change what the evidence names, and run that test again before answering.",
            "evidence": f"{attempts[most]} fix attempts on: {most}",
        })
    return list(found.values())


def _records(transcript: str | Path) -> list[Any]:
    records = []
    for line in Path(transcript).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records


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
        done = []
        for proposal in proposals(_records(transcript)):
            lesson = lessons.propose(
                stack, proposal["trigger"], proposal["rule"], 1, source="harness",
                run_id=Path(transcript).stem, evidence=proposal["evidence"], path=path,
            )
            if lesson.get("status") == "approved":
                # Once per run: the distiller runs with every `loop.sh kpi`.
                lesson = lessons.recurred(lesson["id"], run_id=Path(transcript).stem, path=path)
            done.append(lesson)
        return done
    except Exception:  # noqa: BLE001 - a lesson is never worth a failed run
        logger.warning("Could not distil this run's lessons", exc_info=True)
        return []


def check_the_evidence(
    runs: Iterable[tuple[str | Path, str | Path]], *, path: Path | None = None,
) -> list[dict[str, Any]]:
    """Add what these (transcript, workspace) pairs recorded to the lessons on record; those left with no evidence.

    Proposes nothing and decides nothing: a lesson with none is named for the owner. A rejected one is not named.
    """
    from app.plugins import lessons

    for transcript, root in runs:
        stack = the_stack(root)
        if not stack:
            continue
        for proposal in proposals(_records(transcript)):
            lessons.add_evidence(
                stack, proposal["trigger"], run_id=Path(transcript).stem, evidence=proposal["evidence"], path=path,
            )
    return [
        lesson for lesson in lessons.load(path)
        if lesson.get("status") != "rejected" and not lesson.get("evidence_in")
    ]


__all__ = ["ATTEMPTS_WORTH_A_LESSON", "ON_BY_DEFAULT", "check_the_evidence", "distil", "enabled", "proposals", "the_stack"]
