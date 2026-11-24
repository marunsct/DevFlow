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

Read inside the attempt too (`stops_the_fix_round`): at each test round before its fix round, and before each fixer is
sent. Measured on one run: read only at an attempt's end, last in order, a sprint ran 891 active minutes against its
126, because an attempt with defects left kept sending fixers and never reached its end. Once a sprint has run
`FIX_ROUND_FACTOR` times its budget, the fix round sends no more fixers and the attempt goes to its end-of-attempt
decision (`end_of_attempt.decide`), which puts the best attempt back if this one is worse and settles or stops. The
budget is not changed, only where it is read.
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
#: Inside an attempt, how many times its budget a sprint runs before its fix round stops. Twice, not once: the budget
#: is already the ledger's 90th-percentile pace (about three times the median), and at once over it an attempt in
#: flight - perhaps a fixer from green - would be cut where its end would have settled it; the end-of-attempt check
#: keeps stopping re-plans at once over. At twice over (60 minutes plus 24 a criterion, past the 20 a criterion beyond
#: which runs scored 0.58 of their hidden tests) the time has stopped paying, and a full budget's worth of room has
#: been given to the attempt in flight; the measured sprint was seven times over.
FIX_ROUND_FACTOR = 2
#: The transcript record of a fix round it stopped; the switch-firing check reads its `message`.
RECORD_KIND = "time_budget"

#: The stage that plans a sprint's work: its first entry after the previous sprint ended starts the sprint's clock.
SPRINT_START_STAGE = "technical_lead"
#: The thorough delivery's review stages are not on the clock: the budget's pace was measured on runs with none of them,
#: and they judge the work rather than do it. Measured on one medium run: a sprint's code, security, four advice and
#: milestone reviews took about 75 active minutes, against a 66-minute budget for its three criteria.
_REVIEW_STAGE = re.compile(r"^(?:code_review|security_review|advice_review|milestone_review)")

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

    def ends_the_fix_round(self) -> bool:
        """Whether the sprint is so far past its budget that its fix round sends no more fixers."""
        return self.minutes > self.limit * FIX_ROUND_FACTOR

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


def review_minutes(path: Path, since: datetime | None) -> float:
    """The active minutes the sprint spent in its review stages: each gap (at most `PAUSE_GAP_SECONDS`) that ends on a
    review stage's entry, from the sprint's first plan on. Taken off the sprint's active minutes."""
    seconds, last, started = 0.0, None, False
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
            if last is not None and _REVIEW_STAGE.match(head.group(2)):
                gap = (moment - last).total_seconds()
                if 0 < gap <= PAUSE_GAP_SECONDS:
                    seconds += gap
            last = moment
    return seconds / 60


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
        spent = active_minutes(moments, now or datetime.now(timezone.utc)) - review_minutes(path, _the_sprint_began_after(state))
        return Budget(round(max(spent, 0.0), 1), limit_for(size), size, due)
    except Exception as error:  # noqa: BLE001 - a sprint with no measured time is planned as before
        degraded("measure.sprint_time", error)
        return None


def stops_the_fix_round(state: Any, *, stage: str) -> str:
    """Why the fix round in flight sends no more fixers, or "" while it may; recorded in the transcript when it stops.

    "" when the switch is off or the sprint's time is not measured, so the round goes on as before. Never raises.
    """
    budget = measure(state)
    if budget is None or not budget.ends_the_fix_round():
        return ""
    why = (f"{SAID} {FIX_ROUND_FACTOR} times over ({budget.minutes:.0f} active minutes against {budget.limit:.0f}): "
           "the fix round sends no more fixers and the attempt ends here")
    logger.warning("%s: %s", stage, why)
    try:
        from app.observability.transcript import _run_id_from_config, record

        record(_run_id_from_config(), stage, RECORD_KIND, message=why, minutes=budget.minutes, limit=budget.limit,
               size=budget.size, round=state.get("test_round", 0), sprint=state.get("current_sprint_index", 0))
    except Exception as error:  # noqa: BLE001 - the round stops whether or not it is recorded
        degraded("record.sprint_time", error)
    return why


__all__ = ["BASE_MINUTES", "Budget", "FIX_ROUND_FACTOR", "ON_BY_DEFAULT", "RECORD_KIND", "PAUSE_GAP_SECONDS", "PER_CRITERION_MINUTES", "SAID",
           "active_minutes", "enabled", "limit_for", "measure", "moments_since", "sprint_size", "still_failing",
           "stops_the_fix_round"]
