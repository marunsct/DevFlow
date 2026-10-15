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


def due(records: Iterable[Any], now: datetime) -> list[tuple[str, str, int]]:
    """(run id, "approval" or "review", minutes) for each run whose gate has waited past its timeout."""
    found = []
    for record in records:
        kind = _WAITING.get(str(getattr(record, "status", "") or ""))
        minutes = getattr(record, "approval_timeout_minutes", None)
        since = _when(getattr(record, "updated_at", None))
        if kind and minutes and since and now - since >= timedelta(minutes=int(minutes)):
            found.append((record.run_id, kind, int(minutes)))
    return found


async def approve_what_is_due(runner: Any, now: datetime | None = None) -> list[str]:
    """Approve every gate past its timeout; the run ids approved."""
    from app.agents.approval import approve_write_decision
    from app.graph.workflow import approve_decision

    records = runner.run_store.list_all(limit=500, offset=0)
    approved = []
    for run_id, kind, minutes in due(records, now or datetime.now(timezone.utc)):
        why = f"Approved automatically: nobody answered within {minutes} minute(s)."
        try:
            if kind == "approval":
                await runner.submit_approval(run_id, approve_write_decision())
            else:
                await runner.submit_review(run_id, approve_decision(comment=why))
        except Exception as error:  # noqa: BLE001 - another process won, or the run moved on
            logger.info("Did not approve %s after its timeout: %s", run_id, error)
            continue
        logger.warning("%s: %s", run_id, why)
        approved.append(run_id)
    return approved


async def sweep_for_ever(runner: Any) -> None:
    while True:
        await asyncio.sleep(SWEEP_SECONDS)
        try:
            await approve_what_is_due(runner)
        except Exception:  # noqa: BLE001 - a sweep never takes the server down
            logger.warning("The approval-timeout sweep failed", exc_info=True)
