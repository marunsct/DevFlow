"""What past runs took and scored: the outcome dashboard and the start form's forecast.

Each harness change was judged run by run, by reading logs; nothing showed a
run's time and score beside the runs before it, and nobody starting a run could
see what one usually takes. Scores come from `loop.sh score`, which leaves a
summary (no test names) in `<data>/outcomes/<run>.json`.
"""

from __future__ import annotations

import json
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

FINISHED = ("completed", "failed", "cancelled")
#: Completed runs a forecast needs before it says anything. Two made a
#: "typical" thorough run of 1.5 h out of one small benchmark and one small
#: brief, beside a fast median of 4.7 h from larger briefs - so thorough read as
#: the faster of the two.
FEWEST_FOR_A_FORECAST = 3
#: Only the most recent runs of a mode count: the harness changes run to run,
#: and a twelve-hour run from many versions ago says little of the next.
RECENT_RUNS = 10


def outcomes_directory() -> Path:
    return Path(os.environ.get("RUN_OUTCOMES_DIR") or "/app/data/outcomes")


def _when(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _score(run_id: str) -> dict[str, Any] | None:
    try:
        data = json.loads((outcomes_directory() / f"{run_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return {key: data.get(key) for key in ("benchmark", "passed", "total", "score")}


def _criteria_of(record: Any) -> int | None:
    """How many acceptance criteria the run's last measured suite held, or None."""
    root = getattr(record, "repo_root", None)
    if not root:
        return None
    try:
        from app.acceptance import suite

        found = (suite.last_result(root) or {}).get("criteria") or {}
    except Exception:  # noqa: BLE001 - a row without the count beats no row
        return None
    return len(found) or None


def outcomes(records: Iterable[Any]) -> list[dict[str, Any]]:
    """One row per finished run, newest first: how it ended, how long it took, what it scored."""
    rows = []
    for record in records:
        if record.status not in FINISHED:
            continue
        started, ended = _when(record.created_at), _when(record.updated_at)
        hours = round((ended - started).total_seconds() / 3600, 2) if started and ended else None
        rows.append({
            "run_id": record.run_id,
            "status": record.status,
            # What the release knew it did not prove (Initiative J.4): the
            # dashboard shows a completed run's gaps beside its score, so a
            # 1/10 that reads "completed" can be seen for what it shipped.
            "completion_gaps": [str(gap) for gap in (getattr(record, "completion_gaps", None) or [])],
            "delivery_mode": getattr(record, "delivery_mode", "") or "",
            "use_frontier_model": not bool(getattr(record, "local_only", False)),
            "started_at": started.isoformat() if started else None,
            "hours": hours,
            "criteria": _criteria_of(record),
            "score": _score(record.run_id),
        })
    return rows


def forecast(rows: list[dict[str, Any]], delivery_mode: str) -> dict[str, Any] | None:
    """What a completed run of this delivery mode has taken here, from the most recent ones.

    Briefs differ in size, so the time per acceptance criterion comes with the
    typical time: the start form multiplies it by the brief's own count, which
    compares the modes like with like. With fewer than FEWEST_FOR_A_FORECAST
    runs the times are None and `runs` says how many there were; None when there
    were none.
    """
    recent = [row for row in rows
              if row["status"] == "completed" and row["delivery_mode"] == delivery_mode and row["hours"]][:RECENT_RUNS]
    if not recent:
        return None
    hours = [row["hours"] for row in recent]
    per_criterion = [row["hours"] / row["criteria"] for row in recent if row.get("criteria")]
    counts = [row["criteria"] for row in recent if row.get("criteria")]
    enough = len(hours) >= FEWEST_FOR_A_FORECAST
    return {
        "delivery_mode": delivery_mode,
        "runs": len(hours),
        "typical_hours": round(statistics.median(hours), 1) if enough else None,
        "shortest_hours": round(min(hours), 1) if enough else None,
        "longest_hours": round(max(hours), 1) if enough else None,
        "hours_per_criterion": (
            round(statistics.median(per_criterion), 3) if len(per_criterion) >= FEWEST_FOR_A_FORECAST else None
        ),
        "fewest_criteria": min(counts) if len(counts) >= FEWEST_FOR_A_FORECAST else None,
        "most_criteria": max(counts) if len(counts) >= FEWEST_FOR_A_FORECAST else None,
    }
