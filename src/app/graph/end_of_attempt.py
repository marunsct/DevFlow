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


def decide(root: str, defects: Any, *, replans: int, best_history: Any) -> Decision:
    """What ends this attempt: settle, stop, or plan again; with the reason added and the record of the best."""
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
    if stalled_sprint.stalled(history):
        return Decision(STOP, f"the last {stalled_sprint.AFTER_FLAT_ATTEMPTS} attempts did not beat the best product",
                        history, put_back)
    return Decision(REPLAN, "", history, put_back)


__all__ = ["Decision", "REPLAN", "SETTLE", "STOP", "decide"]
