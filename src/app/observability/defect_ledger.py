"""Each defect's life, in the run's transcript: raised, closed, fixed, left open, reverted.

What became of a defect was spread over the worker's log ("already fixed ...
closed without a fixer", "Reverted defect_fix_1_3"), the Sprint Record's
final status and the fixer's own transcript, and an audit stitched them
together by time. One `defect` record per event, keyed by round and index,
puts it in one place - `scripts/loop/defects.py` reads it back.
"""

from __future__ import annotations

from typing import Any


def note(event: str, stage: str, *, defect: Any = None, round_: int | None = None,
         index: int | None = None, detail: str = "", sprint: int | None = None) -> None:
    """Record one event in this run's transcript. Never raises."""
    try:
        from app.observability.transcript import _run_id_from_config, record

        record(
            _run_id_from_config(), stage, "defect",
            event=event,
            sprint=sprint,
            round=round_,
            index=index,
            source=str(getattr(defect, "source", "") or ""),
            owner=str(getattr(defect, "owner", "") or ""),
            description=" ".join(str(getattr(defect, "description", "") or "").split())[:300],
            detail=" ".join(str(detail or "").split())[:500],
        )
    except Exception:  # noqa: BLE001 - a ledger must never fail the stage it records
        pass


__all__ = ["note"]
