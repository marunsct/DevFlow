"""A suite repaired at a re-plan's entry that leaves the sprint near green goes back to a test round, not the lead's
re-plan (LR.53, behind `NEAR_GREEN_REPAIR_TO_ROUND`).

Measured over past re-plans: of 45 near-green re-plans that beat the best attempt, 19 had got there from the dispute's
repair of the suite alone - the suite measured again within about a minute and a half of the repair - and the re-plan
then spent about 25 more minutes. A fully green suite beside passing unit tests already goes back to the round
(`acceptance_nodes.a_repair_left_the_sprint_green`); this sends a near-green one there too, where a fix round works on
the one or two failures left instead of a new plan for the whole sprint.

An efficiency change, so a switch (Efficiency group), kept only if measured runs lose no hidden test by it.
"""
from __future__ import annotations

from typing import Any

from app.switches import is_on

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False

#: The words its decision gives, which the audit's switch-firing check reads.
SAID = "the repaired suite is near green, so the sprint is measured again in a test round instead of planned again"


def enabled() -> bool:
    return is_on("NEAR_GREEN_REPAIR_TO_ROUND", ON_BY_DEFAULT)


def counts(result: Any) -> tuple[int, int]:
    """(passed, failed) of the repaired suite's run; (0, 0) when it did not run. Never raises."""
    try:
        report = getattr(result, "report", None)
        if not getattr(result, "ran", False) or report is None:
            return 0, 0
        return int(report.passed), int(report.failed)
    except Exception:  # noqa: BLE001 - planned again, as before
        return 0, 0


def applies(result: Any) -> bool:
    """Whether a suite repaired at a re-plan's entry goes back to the test round: on, and its run near green."""
    if not enabled():
        return False
    from app.graph.near_green_once import near_green

    return near_green(*counts(result))


__all__ = ["ON_BY_DEFAULT", "SAID", "applies", "counts", "enabled"]
