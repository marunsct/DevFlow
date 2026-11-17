"""One decision at the end of a sprint's attempt, from one measurement (LR.26).

Four fixes in one day changed the decisions at a sprint's end (`docs/reviews/sprint-ending-2026-11-14.md`): the
settle rule read the measurement before the best attempt came back, then again after it; the stall rule read a third;
and the settle rule required the whole suite green, so a sprint whose only failing tests waited on later sprints was
never settled. Each rule was right alone and wrong in its place in the sequence.

Now, in one order: put the best attempt back if the product is worse (which measures it again), then ask of that one
measurement - is the locked suite green for this sprint (later sprints' tests and deferred criteria aside) with only
unit tests or findings read from files open? Then settle. Have the last attempts stopped beating the best? Then stop.
Otherwise plan the sprint again.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SETTLE, STOP, REPLAN = "settle", "stop", "replan"


@dataclass(frozen=True)
class Decision:
    outcome: str
    why: str = ""
    best_history: list[int] = field(default_factory=list)
    put_back: str = ""


def decide(root: str, defects: Any, *, replans: int, best_history: Any, budget: Any = None) -> Decision:
    """What ends this attempt: settle, stop, or plan again; with the reason added and the record of the best.

    `budget` is the sprint's measured time (`sprint_time_budget.Budget`), or None when it is not measured.
    """
    from app.graph import best_attempt, settle_when_green, stalled_sprint

    # Even one test fewer than the best is worse here: a run released at 17 of 18 criteria, with AC-14 deferred,
    # after an earlier attempt had passed all 18.
    put_back = best_attempt.restore_if_worse(root, margin=1)
    still_open = settle_when_green.open_after_the_put_back(root, defects) if put_back else list(defects or ())
    if settle_when_green.applies(root, still_open, replans):
        said = ("with the best attempt put back every acceptance test due passes and only the unit tests fail" if put_back
                else "every acceptance test due passes and only the unit tests fail")
        return Decision(SETTLE, said, list(best_history or ()), put_back)
    history = stalled_sprint.record(root, best_history)
    # Planned again once already and still near green (LR.53, `NEAR_GREEN_REPLANNED_ONCE`): measured, later re-plans
    # of a near-green sprint beat the best in 4 of 27 cases, at about 34 minutes each.
    from app.graph import near_green_once

    if near_green_once.applies(root, replans):
        return Decision(STOP, f"{near_green_once.SAID}: it was planned again once and is still near green",
                        history, put_back)
    if stalled_sprint.stalled(history):
        return Decision(STOP, f"the last {stalled_sprint.AFTER_FLAT_ATTEMPTS} attempts did not beat the best product",
                        history, put_back)
    # Past the sprint's time budget (LR.42, `SPRINT_TIME_BUDGET`): stopped with the criteria still failing, not planned
    # again. Last, so it decides only an attempt nothing else would have stopped.
    if budget is not None and budget.past():
        return Decision(STOP, budget.why(root), history, put_back)
    return Decision(REPLAN, "", history, put_back)


__all__ = ["Decision", "REPLAN", "SETTLE", "STOP", "decide"]
