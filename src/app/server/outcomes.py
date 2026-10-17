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
#: Completed runs a forecast needs before it says anything.
FEWEST_FOR_A_FORECAST = 2


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
            "score": _score(record.run_id),
        })
    return rows


def forecast(rows: list[dict[str, Any]], delivery_mode: str) -> dict[str, Any] | None:
    """The typical time of a completed run in this delivery mode, or None with too few to say."""
    hours = [row["hours"] for row in rows
             if row["status"] == "completed" and row["delivery_mode"] == delivery_mode and row["hours"]]
    if len(hours) < FEWEST_FOR_A_FORECAST:
        return None
    return {
        "delivery_mode": delivery_mode,
        "typical_hours": round(statistics.median(hours), 1),
        "shortest_hours": round(min(hours), 1),
        "longest_hours": round(max(hours), 1),
        "runs": len(hours),
    }
