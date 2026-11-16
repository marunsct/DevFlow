"""A sprint whose locked suite is near green is planned again once, not twice (LR.53, behind `NEAR_GREEN_REPLANNED_ONCE`).

Measured over 175 re-plans in 109 runs (2026-11-04 to 11-17): after a near-green suite - one or two locked tests
failing, or nine in ten passing - the first re-plan beat the best attempt in 41 of 57 cases; the second and third in 4
of 27 (the third in none of 9), at about 34 active minutes each (931 in all), and 21 of the 22 runs that had them
scored every hidden test. So once a near-green sprint has been planned again, the attempt's end goes to the escalation
- which accepts the sprint with its open failures stated, or stops it - instead of a second plan.

An efficiency change, so a switch (Efficiency group), kept only if measured runs lose no hidden test by it.
"""
from __future__ import annotations

from pathlib import Path

from app.switches import is_on

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False

#: The words its decision gives, which the audit's switch-firing check reads.
SAID = "a near-green suite is not planned again a second time"


def enabled() -> bool:
    return is_on("NEAR_GREEN_REPLANNED_ONCE", ON_BY_DEFAULT)


def near_green(passed: int, failed: int) -> bool:
    """One or two locked tests failing, or nine in ten passing; a green suite is the settle rule's, not this one's."""
    total = passed + failed
    return total > 0 and failed > 0 and (failed <= 2 or passed >= 0.9 * total)


def applies(root: str | Path, replans: int) -> bool:
    """Whether this attempt ends the sprint's re-plans: on, re-planned at least once, the last measurement near green."""
    if not enabled() or replans < 1:
        return False
    from app.acceptance import suite

    result = suite.last_result(root) or {}
    try:
        return near_green(int(result.get("passed") or 0), int(result.get("failed") or 0))
    except (TypeError, ValueError):
        return False


__all__ = ["ON_BY_DEFAULT", "SAID", "applies", "enabled", "near_green"]
