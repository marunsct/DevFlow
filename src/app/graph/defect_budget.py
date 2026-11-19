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

        # The harness's own rewrites, candidates and localisation for the defect
        # are recorded under the family's name; they run only for a defect fixed
        # alone, so since its start they are its own. Uncounted, an attempt of
        # nine candidate calls and a rewrite was recorded as none.
        mine = {stage, "defect_fix"}
        return sum(1 for r in read_transcript(run_id, {"model_request"})
                   if r.get("stage") in mine and str(r.get("at") or "") >= since)
    except Exception:  # noqa: BLE001
        return None


#: The ledger event an attempt's model calls are recorded under, so the count follows the defect across re-plans.
ATTEMPT_EVENT = "attempt calls"


#: How an attempt record says the defect it worked on carried a cause its stack pack knows.
WITH_A_KNOWN_CAUSE = "with a known cause"


def _carries_a_known_cause(defect: Any) -> bool:
    from app.stacks.known_errors import KNOWN_CAUSE

    return KNOWN_CAUSE in str(getattr(defect, "actual_behavior", "") or "")


def record_calls(stage: str, defect: Any, calls: int) -> None:
    """Note one attempt's model calls in the run's defect ledger, under the defect's id across rounds. Never raises."""
    try:
        from app.observability import defect_ledger

        detail = str(int(calls)) + (f" {WITH_A_KNOWN_CAUSE}" if _carries_a_known_cause(defect) else "")
        defect_ledger.note(ATTEMPT_EVENT, stage, defect=defect, detail=detail)
    except Exception:  # noqa: BLE001 - a count must never fail the stage it records
        pass


def _attempts_in_the_run(ids: set[str]) -> list[str]:
    """The details of the attempt records the ledger holds for defects `ids` over the whole run; [] when unreadable."""
    try:
        from app.observability.transcript import _run_id_from_config, read_live

        run_id = _run_id_from_config()
        if not run_id or not ids:
            return []
        return [str(r.get("detail") or "0") for r in read_live(run_id, {"defect"})
                if r.get("event") == ATTEMPT_EVENT and r.get("defect_id") in ids]
    except Exception:  # noqa: BLE001
        return []


def _spent_in_the_run(ids: set[str]) -> int:
    """The calls the ledger holds for defects `ids` over the whole run; 0 when unreadable."""
    total = 0
    for detail in _attempts_in_the_run(ids):
        try:
            total += int(detail.split()[0] or 0)
        except (ValueError, IndexError):
            continue
    return total


def _a_cause_no_attempt_has_seen(cycle: Any, index: int) -> bool:
    """Whether defect `index` now carries a cause its stack pack knows that none of its attempts was shown.

    Measured on one Java run: the start failure spent 76 calls over two attempts while the fixer was shown only stack
    frames; the third attempt's defect carried the pack's cause for the error - and was left open unseen, the run
    stopped. New knowledge from the harness earns one more attempt; the attempt that sees it is marked, so it is one.
    """
    from app.observability.defect_ledger import defect_id
    from app.sprint import recurrence_chain

    defect = cycle.defects[index]
    if not _carries_a_known_cause(defect):
        return False
    chain = [defect, *recurrence_chain(defect, cycle.defects[:index])]
    return not any(WITH_A_KNOWN_CAUSE in detail for detail in _attempts_in_the_run({defect_id(d) for d in chain}))


def spent(cycle: Any, index: int) -> int:
    """The calls defect `index` and the defect it recurs from have cost, by their attempt records - or over the whole
    run, by the ledger, when that is more.

    The attempt records live on the cycle, and a re-planned sprint starts a new one: measured over 30 runs, six
    defects went past the cap this way (523 calls, 288 model minutes; 132 calls on one), and five were never fixed.
    """
    from app.observability.defect_ledger import defect_id
    from app.sprint import recurrence_chain

    defect = cycle.defects[index]
    chain = [defect, *recurrence_chain(defect, cycle.defects[:index])]
    in_the_cycle = sum(int((a or {}).get("calls") or 0) for d in chain for a in (getattr(d, "attempts", None) or []))
    return max(in_the_cycle, _spent_in_the_run({defect_id(d) for d in chain}))


def spent_out(cycle: Any, index: int) -> str:
    """Why defect `index` is not fixed again, or "" when it may be. "" when off."""
    if not enabled():
        return ""
    used = spent(cycle, index)
    if used < most_calls() or _a_cause_no_attempt_has_seen(cycle, index):
        return ""
    did = [f"{a.get('stage')}: {a.get('did') or 'no decision recorded'} ({a.get('outcome')})"
           for a in getattr(cycle.defects[index], "attempts", None) or [] if isinstance(a, dict)]
    return (f"left open after {used} model calls across its attempts (at most {most_calls()}); what they did: "
            + ("; ".join(did[-3:]) or "nothing recorded"))


__all__ = ["ATTEMPT_EVENT", "MOST_CALLS", "WITH_A_KNOWN_CAUSE", "ON_BY_DEFAULT", "calls_in", "enabled", "most_calls", "now", "record_calls",
           "spent", "spent_out"]
