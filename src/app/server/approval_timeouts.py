"""A gate that asks a person approves itself once the run's timeout has passed.

A run is either attended - every approval and review waits for a person, however
long - or unattended (`auto_approve`), with no checkpoint at all. A run started
with `approval_timeout_minutes` sits between: a person can approve the
specification or the sprint when they are there, and when nobody answers in
that time the run goes on as an unattended one would.

The API process sweeps once a minute. Several server processes may sweep at
once; `submit_approval` and `submit_review` move a run out of waiting with a
compare-and-set, so only one of them dispatches it and the rest are refused.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

logger = logging.getLogger(__name__)

SWEEP_SECONDS = 60
_WAITING = {"waiting_for_approval": "approval", "waiting_for_review": "review"}


def _when(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def minutes_for(record: Any, kind: str | None) -> int | None:
    """How long this run's gate waits: the run's own timeout, else the plan gate's default; None waits for ever.

    The plan gate always has a time (plan WS.3): it is a go asked for before the build, not a review a run is
    meant to stop at, so a run left alone at it goes on by itself.
    """
    minutes = getattr(record, "approval_timeout_minutes", None)
    if minutes:
        return int(minutes)
    from app.graph.plan_gate import PLAN_GATE_STAGE, plan_gate_minutes

    if kind == "review" and str(getattr(record, "current_stage", "") or "") == PLAN_GATE_STAGE:
        return plan_gate_minutes()
    return None


def waiting_since(record: Any) -> datetime | None:
    """Since when the run's gate has waited: its record's last update, which the gate's opening wrote."""
    return _when(getattr(record, "updated_at", None))


def due(records: Iterable[Any], now: datetime) -> list[tuple[str, str, int]]:
    """(run id, "approval" or "review", minutes) for each run whose gate has waited past its timeout."""
    found = []
    for record in records:
        kind = _WAITING.get(str(getattr(record, "status", "") or ""))
        minutes = minutes_for(record, kind)
        since = waiting_since(record)
        if kind and minutes and since and now - since >= timedelta(minutes=int(minutes)):
            found.append((record.run_id, kind, int(minutes)))
    return found


async def approve_what_is_due(runner: Any, now: datetime | None = None) -> list[str]:
    """Approve every gate past its timeout; the run ids approved."""
    from app.agents.approval import approve_write_decision
    from app.graph.workflow import approve_decision

    records = runner.run_store.list_all(limit=500, offset=0)
    stages = {record.run_id: str(getattr(record, "current_stage", "") or "") for record in records}
    approved = []
    for run_id, kind, minutes in due(records, now or datetime.now(timezone.utc)):
        why = f"Approved automatically: nobody answered within {minutes} minute(s)."
        try:
            if kind == "approval":
                await runner.submit_approval(run_id, approve_write_decision())
            else:
                await runner.submit_review(run_id, approve_decision(comment=why, by_timeout=True))
        except Exception as error:  # noqa: BLE001 - another process won, or the run moved on
            logger.info("Did not approve %s after its timeout: %s", run_id, error)
            continue
        logger.warning("%s: %s", run_id, why)
        await _say_it_went_on_by_itself(runner, run_id, stages.get(run_id, ""), kind, minutes, why)
        approved.append(run_id)
    return approved


async def _say_it_went_on_by_itself(runner: Any, run_id: str, stage: str, kind: str, minutes: int, why: str) -> None:
    """The run's transcript and its stream say the gate was answered by its time, not by a person. Never raises."""
    try:
        from app.observability.transcript import record

        record(run_id, stage, "gate", event="proceeded_on_its_own", gate=kind, minutes=minutes)
    except Exception:  # noqa: BLE001 - a record must never cost the run
        logger.debug("Could not record the gate's timeout", exc_info=True)
    bus = getattr(runner, "event_bus", None)
    if bus is None:
        return
    try:
        from app.server.events import RunEvent

        point = stage.split(":", 1)[-1] if kind == "review" else ""
        await bus.publish(run_id, RunEvent(
            run_id=run_id, sequence=await bus.next_sequence(run_id), stage=point or stage,
            event_type="review_decision" if kind == "review" else "approval_decision",
            message=why,
            metadata={"action": "approve", "decided_by": "timeout", "minutes": minutes, "review_point": point},
        ))
    except Exception:  # noqa: BLE001 - an event that cannot be sent never stops the sweep
        logger.debug("Could not publish the gate's timeout", exc_info=True)


async def sweep_for_ever(runner: Any) -> None:
    while True:
        await asyncio.sleep(SWEEP_SECONDS)
        try:
            await approve_what_is_due(runner)
        except Exception:  # noqa: BLE001 - a sweep never takes the server down
            logger.warning("The approval-timeout sweep failed", exc_info=True)
        # And stalls and long gates, told to a webhook and an email (plan OP.2).
        from app.server.stall_notices import notify_what_is_stalled

        await notify_what_is_stalled(runner)
