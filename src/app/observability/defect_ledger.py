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


def shown(stage: str, defect: Any, request: Any, *, round_: int | None = None, index: int | None = None,
          sprint: int | None = None) -> None:
    """Record what one fixer was shown: a fingerprint of its request, its size and its sections. Never raises.

    Deep review F9: the ledger held a defect's one-line description and outcome, not the request each fixer was
    given, so "why did the second try succeed" could not be answered from data.
    """
    try:
        import hashlib

        text = request if isinstance(request, str) else "\n".join(
            str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in (request or []))
        fingerprint = hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:12]
        sections = [line.strip("- ").strip() for line in text.splitlines() if line.startswith(("---", "## "))]
        note("shown", stage, defect=defect, round_=round_, index=index, sprint=sprint,
             detail=f"fingerprint {fingerprint}; {len(text)} characters; sections: "
                    + ("; ".join(dict.fromkeys(sections)) or "none")[:300])
    except Exception:  # noqa: BLE001 - a ledger must never fail the stage it records
        pass


__all__ = ["note", "shown"]
