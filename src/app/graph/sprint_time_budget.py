"""A sprint has a budget of active minutes from its measured size; an attempt that ends past it is not planned again
(LR.42, behind `SPRINT_TIME_BUDGET`).

Measured over the KPI ledger (379 runs with accepted criteria, 2026-10 to 11-17): the median run took 4.3 active
minutes per accepted criterion, the 90th percentile 12. Runs slower than 20 minutes a criterion scored 0.58 of their
hidden tests on average (17 runs), against 0.93-0.99 for every band under it: the time a run spends past that pace
goes on re-plans that do not pay. A medium brief had no stated bound at all - only the count of re-plans.

So each sprint gets `BASE_MINUTES` plus `PER_CRITERION_MINUTES` for each criterion it delivers (or work item it plans,
whichever is more; with no criteria assigned, its share of the suite). The base covers one re-plan of a small sprint
(about 34 active minutes each, measured for `NEAR_GREEN_REPLANNED_ONCE`); 12 a criterion is the ledger's 90th
percentile pace, about three times the median. Active minutes are the run's transcript from the sprint's first plan
on, without silences longer than `PAUSE_GAP_SECONDS` (a pause or a dead worker; a slow model call is shorter).

When an attempt ends past the budget and would otherwise be planned again, `end_of_attempt.decide` stops instead,
with the reason and the criteria still failing; the escalation then accepts what works or stops the run, as it does
for a stalled sprint. An efficiency change that can cost a criterion, so a switch, kept only on measured no loss.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.observability.degraded import degraded
from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False

#: The words its decision gives, written to the sprint's record and the escalation, which the audit reads.
SAID = "the sprint ran past its time budget"

#: Active minutes every sprint has, and each criterion (or planned work item) adds.
BASE_MINUTES = 30
PER_CRITERION_MINUTES = 12
#: A silence longer than this is not work: a pause, a deploy, or a run left without a worker.
PAUSE_GAP_SECONDS = 1800
#: The stage that plans a sprint's work: its first entry after the previous sprint ended starts the sprint's clock.
SPRINT_START_STAGE = "technical_lead"

_HEAD = re.compile(r'"at":\s*"([^"]+)".*?"stage":\s*"([^"]*)"')


def enabled() -> bool:
    return is_on("SPRINT_TIME_BUDGET", ON_BY_DEFAULT)


def limit_for(size: int) -> float:
    """The active minutes a sprint of `size` criteria has."""
    return float(BASE_MINUTES + PER_CRITERION_MINUTES * max(int(size or 0), 1))


def still_failing(root: str | Path, due: Iterable[str] = ()) -> list[str]:
    """The criteria the latest measurement says fail (only those due, when named), in id order."""
    from app.acceptance import suite

    saved = suite.last_result(root) or {}
    entries = {**(saved.get("criteria") or {}), **(saved.get("change_requests") or {})}
    wanted = set(due or ())
    failing = [cid for cid, entry in entries.items()
               if isinstance(entry, dict) and entry.get("status") in {"failed", "untested"}
               and (not wanted or cid in wanted)]
    return sorted(failing, key=lambda cid: (re.sub(r"\d+", "", cid), int(re.sub(r"\D", "", cid) or 0)))


@dataclass(frozen=True)
class Budget:
    """A sprint's active minutes so far against its budget."""

    minutes: float
    limit: float
    size: int
    due: tuple[str, ...] = ()

    def past(self) -> bool:
        return self.minutes > self.limit

    def why(self, root: str | Path) -> str:
        failing = still_failing(root, self.due)
        return (f"{SAID}: {self.minutes:.0f} active minutes against {self.limit:.0f} for a sprint of {self.size} "
                f"criteria" + (f"; still failing: {', '.join(failing)}" if failing else ""))


def _when(text: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def active_minutes(moments: Iterable[datetime], now: datetime) -> float:
    """Minutes between the first moment and `now`, without the silences longer than `PAUSE_GAP_SECONDS`."""
    points = sorted([*moments, now])
    seconds = sum(gap for gap in ((b - a).total_seconds() for a, b in zip(points, points[1:]))
                  if 0 < gap <= PAUSE_GAP_SECONDS)
    return seconds / 60


def moments_since(path: Path, since: datetime | None) -> list[datetime]:
    """The times of the transcript's entries from the sprint's first plan at or after `since` on.

    Reads only the head of each line (time and stage), so a long transcript costs a pass over the file, not a parse.
    """
    found: list[datetime] = []
    started = False
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            head = _HEAD.search(line[:400])
            if head is None:
                continue
            moment = _when(head.group(1))
            if moment is None or (since is not None and moment < since):
                continue
            if not started and head.group(2) != SPRINT_START_STAGE:
                continue
            started = True
            found.append(moment)
    return found


def sprint_size(state: Any) -> tuple[int, tuple[str, ...]]:
    """The measured size of the current sprint, and the criteria it delivers (none named: all of them)."""
    from app.acceptance import suite

    sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
    index = int(state.get("current_sprint_index") or 0)
    sprint = sprints[index] if 0 <= index < len(sprints) else None
    own = [str(cid) for cid in (getattr(sprint, "criteria", None) or [])]
    scope = len(getattr(sprint, "in_scope", None) or [])
    size = len(own)
    if not size:
        total = len(suite.criteria(state["repository"].root_path))
        size = math.ceil(total / max(len(sprints), 1)) if total else 0
    return max(size, scope, 1), tuple(own)


def _the_sprint_began_after(state: Any) -> datetime | None:
    """When the previous sprint's last attempt ended, or None for the first sprint."""
    index = int(state.get("current_sprint_index") or 0)
    ends = [_when(str(entry.get("ended_at"))) for entry in state.get("sprint_attempts") or []
            if isinstance(entry, dict) and entry.get("ended_at") and int(entry.get("sprint_index") or 0) < index]
    ends = [end for end in ends if end is not None]
    return max(ends) if ends else None


def measure(state: Any, *, run_id: str | None = None, now: datetime | None = None) -> Budget | None:
    """The current sprint's budget and active minutes; None when off, outside a run, or not measurable. Never raises."""
    if not enabled():
        return None
    try:
        from app.observability.transcript import _run_id_from_config, transcript_path

        path = transcript_path(run_id or _run_id_from_config() or "")
        if path is None or not path.is_file():
            return None
        moments = moments_since(path, _the_sprint_began_after(state))
        if not moments:
            return None
        size, own = sprint_size(state)
        from app.graph.acceptance_nodes import criteria_due

        due = tuple(criteria_due(state) or own)
        return Budget(round(active_minutes(moments, now or datetime.now(timezone.utc)), 1), limit_for(size), size, due)
    except Exception as error:  # noqa: BLE001 - a sprint with no measured time is planned as before
        degraded("measure.sprint_time", error)
        return None


__all__ = ["BASE_MINUTES", "Budget", "ON_BY_DEFAULT", "PAUSE_GAP_SECONDS", "PER_CRITERION_MINUTES", "SAID",
           "active_minutes", "enabled", "limit_for", "measure", "moments_since", "sprint_size", "still_failing"]
