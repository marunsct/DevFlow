"""What each suite dispute decided, recorded as one decision (harness review HR2.Q.4).

The QA lead's dispute can end several ways, and until now each of them was only a log warning: the ruling called a
test wrong, the harness then found it passes alone, its service stopped by itself, it was past the run's
reclassification cap, or the ruling quoted a standard the specification does not hold. None of that reached the audit,
so dispute precision could not be judged. The dispute node now writes one decision at `point="acceptance_dispute"`
and one line of `.harness/dispute-outcomes.jsonl` with every count, read by `loop.sh disputes`.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

OUTCOMES_FILE = ".harness/dispute-outcomes.jsonl"
_LEADING_NAME = re.compile(r"^`([^`]+)`")


def names_in(lines: Iterable[str]) -> list[str]:
    """The test each repair line is about: its leading backticked name, or the whole line when it has none."""
    out = []
    for line in lines:
        text = str(line)
        found = _LEADING_NAME.match(text)
        out.append(found.group(1) if found else text[:200])
    return out


def outcome(
    *,
    shown: Iterable[str],
    called_wrong: Iterable[str],
    refused: Iterable[tuple[str, str]] = (),
    passed_alone: Iterable[str] = (),
    service_stopped: Iterable[str] = (),
    past_the_cap: Iterable[str] = (),
    missing: Iterable[str] = (),
    reopened: bool = False,
) -> dict[str, Any]:
    """One dispute's decision: what the QA lead was shown, what its ruling named, and what the harness kept locked."""
    refused = [(str(name), str(why)) for name, why in refused]
    record = {
        "shown": list(map(str, shown)),
        "called_wrong": names_in(called_wrong),
        "refused": [name for name, _ in refused],
        "refused_why": [why for _, why in refused],
        "passed_alone": names_in(passed_alone),
        "service_stopped": names_in(service_stopped),
        "past_the_cap": names_in(past_the_cap),
        "missing": names_in(missing),
    }
    kept = {*record["passed_alone"], *record["service_stopped"], *record["past_the_cap"]}
    record["reopened"] = bool(reopened)
    record["reopened_tests"] = (
        [name for name in record["called_wrong"] if name not in kept] + record["missing"] if reopened else []
    )
    return record


def summary(record: dict[str, Any]) -> str:
    """The decision's one line: what was decided, counted."""
    if record.get("reopened"):
        head = f"reopened the suite for {len(record['reopened_tests'])} test(s)"
    elif not record.get("called_wrong") and not record.get("refused"):
        head = "no locked test called wrong; the suite stays as it is"
    else:
        head = "the suite stays locked"
    counts = ", ".join(
        f"{len(record[key])} {label}"
        for key, label in (
            ("shown", "shown"), ("called_wrong", "called wrong"), ("refused", "refused for the quote"),
            ("passed_alone", "passed alone"), ("service_stopped", "service stopped"), ("past_the_cap", "past the cap"),
            ("missing", "missing from the suite"),
        )
        if record.get(key)
    )
    return f"{head} ({counts})" if counts else head


def write(root: Any, record: dict[str, Any], sprint: str = "") -> None:
    """Append the record to the run's outcomes file; a write that fails changes nothing about the dispute."""
    try:
        path = Path(root) / OUTCOMES_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {"at": datetime.now(timezone.utc).isoformat(), "sprint": sprint, **record}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
    except OSError:
        pass


__all__ = ["OUTCOMES_FILE", "names_in", "outcome", "summary", "write"]
