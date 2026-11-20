"""A fix round takes failing criteria and release findings before the other open defects (behind `FIX_ORDER_CRITERIA_FIRST`).

Measured on one run, a sprint's second attempt raised thirteen defects in this order: the unit tests fail, six
regressions of single unit tests, an unstyled page, an install and a build that fail, then the three failing
acceptance criteria. Fixers were sent in the order raised, two side by side on a slow model, so the criteria - what
the sprint is judged by - waited more than 35 minutes behind unit-test fixes that left most of them open.

With the switch on, a fix round takes its open defects in three groups, each in the order raised:

1. a product that does not build or start - `start_first` still holds every other defect back while one is open;
2. a failing acceptance criterion, and what a probe the release asks again finds (`probes_at_release`): what blocks
   the release;
3. everything else - failing and regressed unit tests, style, mutation findings.

Only the order changes: no defect is dropped or put off to a later round, and a regression is still fixed in the same
round. Each round in which the order changed is recorded once in the transcript (`RECORD_KIND`), naming what moved
ahead, so the switch's firing and the minutes to the first criterion's fixer can be measured. Off, defects are fixed
in the order raised.
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any, Iterable, Sequence

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `FIX_ORDER_CRITERIA_FIRST` set to on or off overrides this.
ON_BY_DEFAULT = False
NAME = "FIX_ORDER_CRITERIA_FIRST"
#: The transcript record of a round whose order changed; the switch-firing check reads its `message`.
RECORD_KIND = "fix_order"
#: What that record's message opens with (`switch_firing.SIGNALS`).
SAID = "Failing criteria and release findings fixed ahead of the other defects"

#: How a criterion's defect opens: its id in brackets (`acceptance_nodes`, `last_try_on_deferred`).
_OPENS_WITH_A_CRITERION = re.compile(r"^\s*\[[A-Za-z][\w.-]{0,30}\]")
_LOCK = threading.Lock()
_NOTED: set[tuple] = set()


def enabled() -> bool:
    return is_on(NAME, ON_BY_DEFAULT)


def blocks_the_release(defect: Any) -> bool:
    """Whether `defect` is a failing acceptance criterion or carries what a release probe found. Never raises."""
    try:
        if _OPENS_WITH_A_CRITERION.match(str(getattr(defect, "description", "") or "")):
            return True
        if any(isinstance(record, dict) and str(record.get("criterion") or "").strip()
               for record in getattr(defect, "evidence", None) or ()):
            return True
        from app.acceptance import probes_at_release

        return probes_at_release.carries_a_finding(defect)
    except Exception:  # noqa: BLE001 - a defect that cannot be read keeps its place
        logger.debug("Could not read whether a defect blocks the release", exc_info=True)
        return False


def ordered(defects: Sequence[Any], indices: Iterable[int]) -> list[int]:
    """`indices` into `defects` in the order they are fixed: as given when off; else those that block the release
    first, each group in the order given."""
    indices = list(indices)
    if not enabled():
        return indices
    ahead = [index for index in indices if blocks_the_release(defects[index])]
    return [*ahead, *(index for index in indices if index not in set(ahead))]


def moved_ahead(given: Sequence[int], now: Sequence[int]) -> list[int]:
    """The indices `now` puts ahead of one that came before them in `given`, in `now`'s order; [] for none."""
    position = {index: at for at, index in enumerate(given)}
    moved: list[int] = []
    for at, index in enumerate(now):
        if any(position.get(later, -1) < position.get(index, -1) for later in now[at + 1:]):
            moved.append(index)
    return moved


def note_the_order(state: Any, cycle: Any, given: Sequence[int], now: Sequence[int], stage: str) -> None:
    """Record once per round, in this run's transcript, what the order put ahead; nothing when it changed nothing.

    Never raises.
    """
    try:
        moved = moved_ahead(given, now)
        if not moved:
            return
        from app.observability.transcript import _run_id_from_config, record, transcript_path

        run = _run_id_from_config()
        if not run:
            return
        round_ = state.get("test_round", 0)
        sprint = state.get("current_sprint_index", 0)
        key = (str(transcript_path(run)), sprint, state.get("sprint_replan_count", 0), round_)
        with _LOCK:
            if key in _NOTED:
                return
            _NOTED.add(key)
        behind = [index for index in given if index not in set(moved)]
        record(
            run, stage, RECORD_KIND, switch=NAME, sprint=sprint, round=round_,
            moved_ahead=[{"index": index, "description": " ".join(str(cycle.defects[index].description).split())[:160]}
                         for index in moved],
            behind=len(behind),
            message=f"{SAID}: {len(moved)} moved ahead, {len(behind)} after them",
        )
        logger.info("Fix order: %d failing criteria or release findings ahead of %d other defects",
                    len(moved), len(behind))
    except Exception:  # noqa: BLE001 - a record never fails the round
        logger.debug("Could not record the fix order", exc_info=True)


__all__ = ["NAME", "ON_BY_DEFAULT", "RECORD_KIND", "SAID", "blocks_the_release", "enabled", "moved_ahead",
           "note_the_order", "ordered"]
