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


def _calls_in_the_run(ids: set[str]) -> list[int]:
    """The calls of each attempt the ledger holds for defects `ids` over the whole run; [] when unreadable."""
    calls = []
    for detail in _attempts_in_the_run(ids):
        try:
            calls.append(int(detail.split()[0] or 0))
        except (ValueError, IndexError):
            continue
    return calls


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


def attempt_calls(cycle: Any, index: int, root: Any = None) -> list[int]:
    """The model calls of each attempt at defect `index` so far: by its attempt records, by the run's ledger, or by the
    fix journal's record of its problem (`root`), whichever has counted the most.

    The attempt records live on the cycle, and a re-planned sprint starts a new one: measured over 30 runs, six
    defects went past the cap this way (523 calls, 288 model minutes; 132 calls on one), and five were never fixed. The
    ledger follows a defect by its id across re-plans, and the journal follows its problem when the failing tests, and
    so its id, change between attempts.
    """
    from app.observability.defect_ledger import defect_id
    from app.sprint import recurrence_chain

    defect = cycle.defects[index]
    chain = [defect, *recurrence_chain(defect, cycle.defects[:index])]
    in_the_cycle = [int(a.get("calls") or 0) for d in chain for a in (getattr(d, "attempts", None) or [])
                    if isinstance(a, dict) and a.get("calls") is not None]
    in_the_ledger = _calls_in_the_run({defect_id(d) for d in chain})
    in_the_journal: list[int] = []
    if root:
        from app.graph.cause_journal import calls_on_the_problem

        in_the_journal = calls_on_the_problem(root, defect)
    return max((in_the_cycle, in_the_ledger, in_the_journal), key=sum)


def spent(cycle: Any, index: int, root: Any = None) -> int:
    """The calls defect `index` and the defect it recurs from have cost across their attempts (`attempt_calls`)."""
    return sum(attempt_calls(cycle, index, root))


def spent_out(cycle: Any, index: int, root: Any = None) -> str:
    """Why defect `index` is not fixed again, or "" when it may be. "" when off.

    Not fixed again once its attempts have spent `most_calls()`, or once one more attempt, costing what its attempts
    have cost on average, would take it past that. Checked only before an attempt, the ceiling alone was never reached:
    attempts cost 16 to 20 calls, so a defect at 55 of 60 was given a fourth attempt and ended at 75, and no defect in 30
    runs was ever left open by it.
    """
    if not enabled():
        return ""
    calls = attempt_calls(cycle, index, root)
    used = sum(calls)
    next_one = used / len(calls) if calls else 0
    if (used < most_calls() and used + next_one <= most_calls()) or _a_cause_no_attempt_has_seen(cycle, index):
        return ""
    did = [f"{a.get('stage')}: {a.get('did') or 'no decision recorded'} ({a.get('outcome')})"
           for a in getattr(cycle.defects[index], "attempts", None) or [] if isinstance(a, dict)]
    return (f"left open after {used} model calls across its attempts (at most {most_calls()}"
            + (f"; another attempt at their average of {round(next_one)} would pass it" if used < most_calls() else "")
            + "); what they did: " + ("; ".join(did[-3:]) or "nothing recorded"))


__all__ = ["ATTEMPT_EVENT", "MOST_CALLS", "WITH_A_KNOWN_CAUSE", "ON_BY_DEFAULT", "attempt_calls", "calls_in", "enabled",
           "most_calls", "now", "record_calls", "spent", "spent_out"]
