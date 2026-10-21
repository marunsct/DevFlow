"""The owner's rating of a delivered run, kept beside its KPIs (plan EV.1).

Hidden tests score whether a product works, and only on the benchmarks that
have them; nothing recorded whether the owner found it any good. A rating is one
JSON file per run under `DATA_DIR/ratings/`, where `loop.sh kpi` reads it into
the run's KPI row (`scripts/loop/kpi.py owner_rating`) and `bench-report` shows
it beside the hidden score. Rating again replaces the earlier one.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _path(run_id: str) -> Path:
    return Path(os.environ.get("DATA_DIR") or "data") / "ratings" / f"{Path(run_id).name}.json"


def read(run_id: str) -> dict[str, Any] | None:
    """The run's rating, or None when it has none."""
    try:
        rating = json.loads(_path(run_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return rating if isinstance(rating, dict) else None


def save(run_id: str, score: int, note: str, by: str) -> dict[str, Any]:
    """Keep the rating, replacing any earlier one; the rating as kept."""
    rating = {"score": int(score), "note": " ".join(str(note or "").split())[:500], "rated_by": by,
              "rated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path = _path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(rating), encoding="utf-8")
    temporary.replace(path)
    return rating


__all__ = ["read", "save"]
