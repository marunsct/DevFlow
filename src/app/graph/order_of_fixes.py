"""The order a fix round takes its open defects in: the latest test round's first; with `FIX_ORDER_CRITERIA_FIRST` on,
failing criteria and release findings next.

Always: what the latest test round raised (or raised again) goes before what was carried over from earlier rounds.
Measured on one run: a round raised "the router is mounted with a double prefix, causing every endpoint under it to
return 404" first and eight of its symptoms after it, but the ledger listed two defects carried over from earlier
rounds ahead of them; the fixers took those first, judged on a product that no longer existed, and 25 minutes later the
double prefix had not been worked and no fix on a route under it could be measured. The latest measurement is what
the product is now: a cause it names is fixed before older findings whose failures it may well explain. Each group
keeps the order raised, so a round's own first finding - where its tester puts the shared cause - leads.

The switch: measured on one run, a sprint's second attempt raised thirteen defects in this order: the unit tests
fail, six regressions of single unit tests, an unstyled page, an install and a build that fail, then the three failing
acceptance criteria. Fixers were sent in the order raised, two side by side on a slow model, so the criteria - what
the sprint is judged by - waited more than 35 minutes behind unit-test fixes that left most of them open.

With the switch on, a fix round takes each of those two groups' open defects in three groups, each in the order
raised:

1. a product that does not build or start - `start_first` still holds every other defect back while one is open;
2. a failing acceptance criterion, and what a probe the release asks again finds (`probes_at_release`): what blocks
   the release;
3. everything else - failing and regressed unit tests, style, mutation findings.

Only the order changes: no defect is dropped or put off to a later round, and a regression is still fixed in the same
round. Each round in which the order changed is recorded once in the transcript (`RECORD_KIND`), naming what moved
ahead, so the switch's firing and the minutes to the first criterion's fixer can be measured. Off, defects are fixed
in the order raised within the latest round's and the carried-over groups. The latest round going first is recorded
once a round too (`LATEST_FIRST_SAID`, no switch).
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

#: What the record of a round whose order the latest round's defects changed opens with (`loop.sh effects`).
LATEST_FIRST_SAID = "Defects the latest test round raised fixed ahead of those carried over from earlier rounds"

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


def raised_by_the_latest_round(defects: Sequence[Any]) -> set[int]:
    """The indices of `defects` the latest test round raised or raised again; empty when no round is recorded.

    The latest round is the highest `found_in_round` among all of them: only a test round sets it, so it stays the
    same through a fix round, whatever the fixes close or add. Never raises.
    """
    rounds: dict[int, int] = {}
    for index, defect in enumerate(defects):
        found = getattr(defect, "found_in_round", None)
        if isinstance(found, int) and not isinstance(found, bool):
            rounds[index] = found
    if not rounds:
        return set()
    latest = max(rounds.values())
    return {index for index, found in rounds.items() if found == latest}


def latest_round_first(defects: Sequence[Any], indices: Iterable[int]) -> list[int]:
    """`indices` into `defects` with those the latest test round raised first, each group in the order given."""
    indices = list(indices)
    latest = raised_by_the_latest_round(defects)
    return [*(index for index in indices if index in latest), *(index for index in indices if index not in latest)]


def ordered(defects: Sequence[Any], indices: Iterable[int]) -> list[int]:
    """`indices` into `defects` in the order they are fixed: the latest test round's first; with the switch on, within
    each of those two groups those that block the release first. Every group keeps the order given."""
    indices = latest_round_first(defects, indices)
    if not enabled():
        return indices
    latest = raised_by_the_latest_round(defects)
    # Stable: equal keys keep the order given.
    return sorted(indices, key=lambda index: (index not in latest, not blocks_the_release(defects[index])))


def moved_ahead(given: Sequence[int], now: Sequence[int]) -> list[int]:
    """The indices `now` puts ahead of one that came before them in `given`, in `now`'s order; [] for none."""
    position = {index: at for at, index in enumerate(given)}
    moved: list[int] = []
    for at, index in enumerate(now):
        if any(position.get(later, -1) < position.get(index, -1) for later in now[at + 1:]):
            moved.append(index)
    return moved


def note_the_order(state: Any, cycle: Any, given: Sequence[int], now: Sequence[int], stage: str) -> None:
    """Record once per round, in this run's transcript, what each rule put ahead; nothing for a rule that changed
    nothing: the latest round's defects ahead of those carried over (no switch), then failing criteria and release
    findings (`FIX_ORDER_CRITERIA_FIRST`).

    Never raises.
    """
    try:
        by_round = latest_round_first(cycle.defects, given)
        _note(state, cycle, given, by_round, stage, rule="latest round", said=LATEST_FIRST_SAID, switch="")
        _note(state, cycle, by_round, now, stage, rule=NAME, said=SAID, switch=NAME)
    except Exception:  # noqa: BLE001 - a record never fails the round
        logger.debug("Could not record the fix order", exc_info=True)


def _note(state: Any, cycle: Any, given: Sequence[int], now: Sequence[int], stage: str, *, rule: str, said: str,
          switch: str) -> None:
    moved = moved_ahead(given, now)
    if not moved:
        return
    from app.observability.transcript import _run_id_from_config, record, transcript_path

    run = _run_id_from_config()
    if not run:
        return
    round_ = state.get("test_round", 0)
    sprint = state.get("current_sprint_index", 0)
    key = (str(transcript_path(run)), sprint, state.get("sprint_replan_count", 0), round_, rule)
    with _LOCK:
        if key in _NOTED:
            return
        _NOTED.add(key)
    behind = [index for index in given if index not in set(moved)]
    record(
        run, stage, RECORD_KIND, **({"switch": switch} if switch else {}), sprint=sprint, round=round_,
        moved_ahead=[{"index": index, "description": " ".join(str(cycle.defects[index].description).split())[:160]}
                     for index in moved],
        behind=len(behind),
        message=f"{said}: {len(moved)} moved ahead, {len(behind)} after them",
    )
    logger.info("Fix order (%s): %d defect(s) ahead of %d other(s)", rule, len(moved), len(behind))


__all__ = ["LATEST_FIRST_SAID", "NAME", "ON_BY_DEFAULT", "RECORD_KIND", "SAID", "blocks_the_release", "enabled",
           "latest_round_first", "moved_ahead", "note_the_order", "ordered", "raised_by_the_latest_round"]
