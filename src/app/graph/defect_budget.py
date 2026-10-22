"""A hard ceiling on the model calls one defect may cost across all its fix attempts (plan AY step 4, behind `DEFECT_CALL_CAP`).

Each fix stage has its own call budget, and it was re-armed at every attempt:
a defect fixed in three rounds could cost three full budgets and more, and the
last attempts are the ones least likely to work (repair gains come in the first
two or three tries). With the switch on, each attempt's model calls are kept on
its attempt record (PH.2's `attempts`), counted from the transcript, and a
defect - with the one it recurs from - that has spent `most_calls()` is not
dispatched again: it is left open with what its attempts did as its
diagnosis.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from app.switches import is_on

#: `DEFECT_CALL_CAP` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Model calls one defect may cost across its attempts; `DEFECT_CALLS_AT_MOST` overrides it.
MOST_CALLS = 60


def enabled() -> bool:
    return is_on("DEFECT_CALL_CAP", ON_BY_DEFAULT)


def most_calls() -> int:
    try:
        return max(1, int(os.environ.get("DEFECT_CALLS_AT_MOST") or MOST_CALLS))
    except ValueError:
        return MOST_CALLS


def now() -> str:
    """The moment an attempt starts, as the transcript writes moments."""
    return datetime.now(timezone.utc).isoformat()


def calls_in(run_id: str | None, stage: str, since: str) -> int | None:
    """The model calls `stage` made since `since`, from the transcript; None when off, unreadable or with no start.

    With no start every call ever made under the stage's name would count,
    and a name recurs across a sprint's attempts.
    """
    if not enabled() or not run_id or not since:
        return None
    try:
        from app.observability.transcript import read_transcript

        return sum(1 for r in read_transcript(run_id, {"model_request"})
                   if r.get("stage") == stage and str(r.get("at") or "") >= since)
    except Exception:  # noqa: BLE001
        return None


def spent(cycle: Any, index: int) -> int:
    """The calls defect `index` and the defect it recurs from have cost, by their attempt records."""
    from app.sprint import recurrence_of

    defect = cycle.defects[index]
    chain = [defect, *([earlier] if (earlier := recurrence_of(defect, cycle.defects[:index])) is not None else [])]
    return sum(int((a or {}).get("calls") or 0) for d in chain for a in (getattr(d, "attempts", None) or []))


def spent_out(cycle: Any, index: int) -> str:
    """Why defect `index` is not fixed again, or "" when it may be. "" when off."""
    if not enabled():
        return ""
    used = spent(cycle, index)
    if used < most_calls():
        return ""
    did = [f"{a.get('stage')}: {a.get('did') or 'no decision recorded'} ({a.get('outcome')})"
           for a in getattr(cycle.defects[index], "attempts", None) or [] if isinstance(a, dict)]
    return (f"left open after {used} model calls across its attempts (at most {most_calls()}); what they did: "
            + ("; ".join(did[-3:]) or "nothing recorded"))


__all__ = ["MOST_CALLS", "ON_BY_DEFAULT", "calls_in", "enabled", "most_calls", "now", "spent", "spent_out"]
