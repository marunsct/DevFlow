"""A fix round that closes no defect on a product it leaves unchanged ends the attempt (LR.53, behind
`FIX_STAGES_THAT_CLOSE_NOTHING`).

A fix round is every defect_fix stage between two test rounds. When one closes nothing and the product the next round
measures is the one the round before measured - the same files, `app.acceptance.unstable.fingerprint` - the next fix
round starts from exactly where the last one did, and spends its stages the same way. So the attempt ends there and
goes where an exhausted attempt goes (`app.graph.nodes.triage._replan_or_escalate`: settle, stop or plan again) instead of another round.

A round is known by its sprint attempt and its number; only two consecutive rounds of one attempt are compared. A test
round entered again after a pause gives the answer it gave the first time.

An efficiency change, so a switch (Efficiency group), kept only if measured runs lose no hidden test by it.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.observability.degraded import degraded
from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False

#: The words its decision gives, which the audit's switch-firing check reads.
SAID = "a fix round closed no defect and left the product unchanged, so the attempt ends instead of another round"

#: The last test round that sent the sprint to a fix round, as it measured the product.
RECORD = ".harness/fix-round-before.json"

#: What counts as closed: a fix, or a risk accepted with its reason. A defect folded into another is neither.
CLOSED = ("fixed", "accepted_risk")


def enabled() -> bool:
    return is_on("FIX_STAGES_THAT_CLOSE_NOTHING", ON_BY_DEFAULT)


def closed(cycle: Any) -> int:
    """How many of the attempt's defects are closed."""
    return sum(1 for defect in getattr(cycle, "defects", None) or [] if getattr(defect, "status", "") in CLOSED)


def closed_nothing(before: dict[str, Any] | None, now: dict[str, Any]) -> bool:
    """Whether the fix round between these two test rounds closed nothing on an unchanged product."""
    if not before or not now.get("fingerprint"):
        return False
    try:
        return (
            before.get("attempt") == now.get("attempt")
            and int(before.get("round", -2)) == int(now.get("round", 0)) - 1
            and before.get("fingerprint") == now["fingerprint"]
            and int(now.get("closed", 0)) <= int(before.get("closed", 0))
        )
    except (TypeError, ValueError):
        return False


def _read(root: str | Path) -> dict[str, Any] | None:
    try:
        value = json.loads((Path(root) / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def ends_the_attempt(root: str | Path, cycle: Any, *, attempt: str, test_round: int) -> bool:
    """Whether this test round, about to send open defects to a fix round, ends the attempt instead. Never raises.

    Notes this round as the one the next is compared with, either way.
    """
    if not enabled():
        return False
    try:
        from app.acceptance import unstable

        before = _read(root)
        if before and before.get("attempt") == attempt and before.get("round") == test_round:
            return bool(before.get("ended"))  # the same round entered again after a pause
        now: dict[str, Any] = {"attempt": attempt, "round": test_round, "fingerprint": unstable.fingerprint(root),
                               "closed": closed(cycle)}
        now["ended"] = closed_nothing(before, now)
        path = Path(root) / RECORD
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(now), encoding="utf-8")
        return bool(now["ended"])
    except Exception as error:  # noqa: BLE001 - another fix round, as before
        degraded("unchanged_fix_round", error)
        return False


__all__ = ["CLOSED", "ON_BY_DEFAULT", "RECORD", "SAID", "closed", "closed_nothing", "enabled", "ends_the_attempt"]
