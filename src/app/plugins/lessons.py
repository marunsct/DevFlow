"""Lessons learned across runs: structured, provenance-tagged, and used only once the owner approves them.

Plan item AI (owner decision 2026-10-18). Cross-run memory was once dropped over
prompt-injection risk: text an agent wrote could steer every later run. Here a
lesson is a record, not prose - the stack it is about, the failure it answers
(the tool and the message shape `scripts/loop/lessons.py` found recurring), a
rule of at most two lines, how many runs showed it, and who wrote it - and it
reaches a prompt only after the owner approves it, from the list the loop
shows after each run. A proposal is never injected.

Approved lessons for the run's stack are appended to the stack's instructions
(`app.plugins.registry`), a few per call and in a fixed order, so the prompt
prefix stays the same from call to call.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

#: Lessons appended to one call's instructions at most.
MOST_LESSONS_PER_CALL = 5
#: A rule's limits: two lines, and short enough to read at a glance.
MOST_RULE_LINES = 2
MOST_RULE_CHARS = 300

#: Words no rule in a prompt may use (the repository's rule for every prompt rule).
_BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

STATUSES = ("proposed", "approved", "rejected")
_LOCK = threading.Lock()


class LessonError(ValueError):
    """A lesson that cannot be kept as given."""


def store_path() -> Path:
    """Where the lessons are kept: beside the run data, which survives a deploy."""
    return Path(os.environ.get("DATA_DIR") or "data") / "lessons.json"


def load(path: Path | None = None) -> list[dict[str, Any]]:
    """Every lesson on record, or [] when there is none or the file cannot be read."""
    try:
        data = json.loads((path or store_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _save(lessons: list[dict[str, Any]], path: Path | None = None) -> None:
    target = path or store_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(lessons, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(target)


def _checked_rule(rule: str) -> str:
    text = "\n".join(line.strip() for line in str(rule or "").strip().splitlines() if line.strip())
    if not text:
        raise LessonError("A lesson needs a rule.")
    if len(text.splitlines()) > MOST_RULE_LINES or len(text) > MOST_RULE_CHARS:
        raise LessonError(f"A rule is at most {MOST_RULE_LINES} lines and {MOST_RULE_CHARS} characters.")
    if _BANNED.search(text):
        raise LessonError("A rule may not use the words the prompts never use (task, button, click, ...).")
    return text


def propose(
    stack: str, trigger: str, rule: str, evidence_runs: int, *,
    role: str = "all", source: str = "harness", path: Path | None = None,
) -> dict[str, Any]:
    """Record a proposed lesson, or refresh the one already proposed for this stack and failure."""
    stack = str(stack or "").strip().lower()
    trigger = " ".join(str(trigger or "").split())
    if not stack or not trigger:
        raise LessonError("A lesson needs the stack it is about and the failure it answers.")
    if source not in ("harness", "operator"):
        raise LessonError("A lesson's source is 'harness' or 'operator'.")
    text = _checked_rule(rule)
    with _LOCK:
        lessons = load(path)
        for lesson in lessons:
            if lesson.get("stack") == stack and lesson.get("trigger") == trigger and lesson.get("role") == role:
                lesson["evidence_runs"] = max(int(lesson.get("evidence_runs") or 0), int(evidence_runs))
                if lesson.get("status") == "proposed":
                    lesson["rule"] = text
                _save(lessons, path)
                return lesson
        number = 1 + max((int(str(item.get("id", "L-0")).split("-")[-1]) for item in lessons), default=0)
        lesson = {
            "id": f"L-{number}", "stack": stack, "role": role, "trigger": trigger, "rule": text,
            "evidence_runs": int(evidence_runs), "source": source, "status": "proposed",
            "proposed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        lessons.append(lesson)
        _save(lessons, path)
        return lesson


def decide(lesson_id: str, approved: bool, *, by: str = "owner", path: Path | None = None) -> dict[str, Any]:
    """Record the owner's answer on one lesson."""
    with _LOCK:
        lessons = load(path)
        for lesson in lessons:
            if lesson.get("id") == lesson_id:
                lesson["status"] = "approved" if approved else "rejected"
                lesson["decided_by"] = by
                lesson["decided_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                _save(lessons, path)
                return lesson
    raise LessonError(f"No lesson {lesson_id}.")


def approved_for(keywords: Iterable[str], path: Path | None = None) -> list[dict[str, Any]]:
    """The approved lessons about any of these stacks, in a fixed order, a call's worth at most."""
    wanted = {str(k).strip().lower() for k in keywords or () if str(k).strip()}
    chosen = [
        lesson for lesson in load(path)
        if lesson.get("status") == "approved" and lesson.get("stack") in wanted
    ]
    chosen.sort(key=lambda lesson: int(str(lesson.get("id", "L-0")).split("-")[-1]))
    return chosen[:MOST_LESSONS_PER_CALL]


def as_instructions(keywords: Iterable[str], path: Path | None = None) -> str:
    """The approved lessons as a block of the stack's instructions, or ""."""
    chosen = approved_for(keywords, path)
    if not chosen:
        return ""
    return "\n\n=== LESSONS FROM EARLIER RUNS ===\n" + "\n".join(
        f"- [{lesson['stack']}] {lesson['rule']}" for lesson in chosen
    )
