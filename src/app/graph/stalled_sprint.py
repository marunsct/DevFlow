"""A sprint whose attempts stop improving the product is not planned again and again (behind `STALL_RULE`).

Measured on three runs: a browser app and two services sat at the same number of acceptance criteria passing for 30 to
60 minutes while the sprint was drafted, fixed and planned again; the best product was already kept (`best_attempt`)
and no later attempt beat it. Each time a sprint is about to be planned again, the best number of acceptance tests
passing so far is written down. When the last `AFTER_FLAT_ATTEMPTS` attempts each failed to beat the best before them,
the sprint goes where the re-plan limit sends it: the escalation, which accepts it with the open problems recorded or
stops it.

Needs the best-attempt record (`KEEP_THE_BEST_ATTEMPT`); without one nothing is recorded and the rule never applies.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file turns it on.
ON_BY_DEFAULT = False

#: How many attempts in a row may fail to beat the best before the sprint goes to the escalation.
AFTER_FLAT_ATTEMPTS = 2


def enabled() -> bool:
    return is_on("STALL_RULE", ON_BY_DEFAULT)


def record(root: str | Path, history: Any) -> list[int]:
    """`history` with the best acceptance-test count so far added; unchanged when there is none."""
    past = [int(n) for n in (history or ()) if isinstance(n, (int, float))]
    if not enabled():
        return past
    try:
        from app.graph import best_attempt

        best = int(best_attempt._read(Path(root)).get("passed") or 0)
    except Exception:  # noqa: BLE001 - no record, no rule
        logger.debug("Could not read the best attempt", exc_info=True)
        return past
    return [*past, best] if best > 0 else past


def stalled(history: Any) -> bool:
    """Whether the last `AFTER_FLAT_ATTEMPTS` re-plans each left the best count where it was."""
    if not enabled():
        return False
    counts = [int(n) for n in (history or ()) if isinstance(n, (int, float))]
    need = AFTER_FLAT_ATTEMPTS + 1
    if len(counts) < need:
        return False
    recent = counts[-need:]
    return all(later <= earlier for earlier, later in zip(recent, recent[1:])) and recent[0] > 0


__all__ = ["AFTER_FLAT_ATTEMPTS", "ON_BY_DEFAULT", "enabled", "record", "stalled"]
