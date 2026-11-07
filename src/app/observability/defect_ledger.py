"""Each defect's life, in the run's transcript: raised, closed, fixed, left open, reverted.

What became of a defect was spread over the worker's log ("already fixed ...
closed without a fixer", "Reverted defect_fix_1_3"), the Sprint Record's
final status and the fixer's own transcript, and an audit stitched them
together by time. One `defect` record per event, keyed by round and index,
puts it in one place - `scripts/loop/defects.py` reads it back.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

#: What changes between two rounds' copies of one defect: numbers, quoted values, paths' line numbers.
_VARYING = re.compile(r"`[^`]*`|\"[^\"]*\"|'[^']*'|\d+")
_A_CRITERION = re.compile(r"\b(?:AC|CR)-\d+\b")


def defect_id(defect: Any) -> str:
    """One defect's id across rounds (harness review F8): its source, owner, criteria and wording without the values
    that change from round to round. Measured: the ledger keyed defects by round and index, so a defect raised again
    in the next round was a new row, and no outcome KPI could follow one defect to its end."""
    description = str(getattr(defect, "description", "") or "")
    criteria = ",".join(sorted(set(_A_CRITERION.findall(description))))
    wording = " ".join(_VARYING.sub("_", _A_CRITERION.sub("", description)).split()).lower()[:200]
    key = "|".join((str(getattr(defect, "source", "") or ""), str(getattr(defect, "owner", "") or ""), criteria,
                    wording))
    return hashlib.sha1(key.encode("utf-8", errors="replace")).hexdigest()[:10]


def note(event: str, stage: str, *, defect: Any = None, round_: int | None = None,
         index: int | None = None, detail: str = "", sprint: int | None = None) -> None:
    """Record one event in this run's transcript. Never raises."""
    try:
        from app.observability.transcript import _run_id_from_config, record

        record(
            _run_id_from_config(), stage, "defect",
            event=event,
            defect_id=defect_id(defect) if defect is not None else "",
            sprint=sprint,
            round=round_,
            index=index,
            source=str(getattr(defect, "source", "") or ""),
            owner=str(getattr(defect, "owner", "") or ""),
            description=" ".join(str(getattr(defect, "description", "") or "").split())[:300],
            detail=" ".join(str(detail or "").split())[:900],
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
        text = request if isinstance(request, str) else "\n".join(
            str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in (request or []))
        fingerprint = hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:12]
        sections = [line.strip("- ").strip() for line in text.splitlines() if line.startswith(("---", "## "))]
        note("shown", stage, defect=defect, round_=round_, index=index, sprint=sprint,
             detail=f"fingerprint {fingerprint}; {len(text)} characters; sections: "
                    + ("; ".join(dict.fromkeys(sections)) or "none")[:300])
    except Exception:  # noqa: BLE001 - a ledger must never fail the stage it records
        pass


__all__ = ["defect_id", "note", "shown"]
