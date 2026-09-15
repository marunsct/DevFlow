"""Live progress endpoints: WebSocket streaming, polling, and a spinner status.

All three read the same ``RunEvent`` history, and all three are authenticated and
tenant-scoped.

Two things worth knowing about the WebSocket:

- It is authenticated with a **short-lived ticket**, not the JWT. A token in the
  query string is recorded by every reverse-proxy access log, browser history
  entry and Referer header on the way; a ticket is single-use, expires in
  seconds, and is worthless once redeemed.
- It sends periodic pings. Without them an idle connection is dropped by the
  default 60-second timeout in most ingress configurations, and the client's
  reconnect loop then runs forever.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from app.server.auth import UserInDB, get_current_active_user
from app.server.events import EventBus, RunEvent
from app.server.runner import WorkflowRunner, _stage_meaning

logger = logging.getLogger(__name__)

KEEPALIVE_INTERVAL_SECONDS = 20
TICKET_TTL_SECONDS = 30

router = APIRouter()


def _event_payload(event: RunEvent) -> dict[str, Any]:
    return {"id": str(event.sequence), "event": event.event_type, "data": event.model_dump_json()}


def _ticket_key(ticket: str) -> str:
    return f"ws_ticket:{ticket}"


async def issue_stream_ticket(run_id: str, username: str) -> str:
    """Mint a single-use ticket authorising one WebSocket connection."""
    from app.server.redis_client import get_async_redis_client

    ticket = secrets.token_urlsafe(32)
    await get_async_redis_client().set(
        _ticket_key(ticket),
        json.dumps({"run_id": run_id, "user": username}),
        ex=TICKET_TTL_SECONDS,
    )
    return ticket


async def redeem_stream_ticket(ticket: str, run_id: str) -> str | None:
    """Consume a ticket, returning the username it was issued to."""
    from app.server.redis_client import get_async_redis_client

    client = get_async_redis_client()
    key = _ticket_key(ticket)
    raw = await client.get(key)
    if raw is None:
        return None
    await client.delete(key)  # single use
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if payload.get("run_id") != run_id:
        return None
    return payload.get("user")


def create_progress_router(runner: WorkflowRunner, event_bus: EventBus) -> APIRouter:
    """Build the progress router bound to the shared runner and event bus."""
    progress = APIRouter()

    def _authorise(run_id: str, user: UserInDB):
        record = runner.run_store.load(run_id)
        if record is None:
            return None
        if user.role != "admin" and record.tenant_id != user.tenant_id:
            return None
        return record

    @progress.post("/{run_id}/events/ticket")
    async def create_ticket(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> dict[str, Any]:
        """Exchange a bearer token for a short-lived streaming ticket."""
        from fastapi import HTTPException

        if _authorise(run_id, user) is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
        return {
            "ticket": await issue_stream_ticket(run_id, user.username),
            "expires_in": TICKET_TTL_SECONDS,
        }

    @progress.websocket("/{run_id}/events/stream")
    async def stream_events(websocket: WebSocket, run_id: str) -> None:
        """Stream live run events to an authorised client."""
        ticket = websocket.query_params.get("ticket")
        username = await redeem_stream_ticket(ticket, run_id) if ticket else None
        if username is None:
            await websocket.close(code=1008)
            return

        from app.server.auth import get_user

        user = await asyncio.to_thread(get_user, username)
        if user is None or user.disabled or _authorise(run_id, user) is None:
            await websocket.close(code=1008)
            return

        await websocket.accept()

        try:
            last_event_id = int(websocket.query_params.get("last_event_id", "0"))
        except ValueError:
            last_event_id = 0

        send_lock = asyncio.Lock()

        async def send(payload: dict[str, Any]) -> None:
            async with send_lock:
                await websocket.send_text(json.dumps(payload))

        async def keepalive() -> None:
            """Ping periodically so proxies do not drop an idle connection."""
            while True:
                await asyncio.sleep(KEEPALIVE_INTERVAL_SECONDS)
                await send({"event": "ping", "data": "{}"})

        keepalive_task = asyncio.create_task(keepalive())
        try:
            # Replay whatever the client missed before joining the live feed, so
            # a reconnect does not silently lose the gap.
            for event in await event_bus.get_history(run_id, since_sequence=last_event_id):
                await send(_event_payload(event))

            async with event_bus.subscribe(run_id) as stream:
                async for event in stream:
                    await send(_event_payload(event))

            # The stream ended because the run finished; tell the client so it
            # stops reconnecting.
            await send({"event": "closed", "data": "{}"})
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception:  # noqa: BLE001
            logger.warning("Event stream for run %s ended with an error", run_id, exc_info=True)
        finally:
            keepalive_task.cancel()
            try:
                await websocket.close()
            except RuntimeError:
                pass

    @progress.get("/{run_id}/events")
    async def poll_events(
        run_id: str,
        since: int = Query(0, ge=0, description="Return events after this sequence number."),
        user: UserInDB = Depends(get_current_active_user),
    ) -> dict[str, Any]:
        """Polling fallback: events after a cursor."""
        from fastapi import HTTPException

        if _authorise(run_id, user) is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

        events = await event_bus.get_history(run_id, since_sequence=since)
        return {
            "events": [event.model_dump() for event in events],
            "cursor": events[-1].sequence if events else since,
        }

    @progress.get("/{run_id}/status")
    async def spinner_status(
        run_id: str, user: UserInDB = Depends(get_current_active_user)
    ) -> dict[str, Any]:
        """Minimal payload for a loading indicator."""
        from fastapi import HTTPException

        record = _authorise(run_id, user)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

        # The spinner shows what the run is doing now. `current_stage` is
        # written only when the gate loop turns, so a run between gates reports
        # what it last paused on - or nothing, before its first gate.
        stage = record.current_stage or ""
        if record.status not in ("completed", "failed", "cancelled"):
            try:
                history = await event_bus.get_history(run_id)
                for event in reversed(history):
                    if event.stage:
                        stage = event.stage
                        break
            except Exception:  # noqa: BLE001 - a spinner is not worth failing
                pass

        return {
            "stage": stage,
            "stage_meaning": record.stage_meaning or _stage_meaning(stage),
            "last_updated": record.updated_at,
            "is_terminal": record.status in ("completed", "failed", "cancelled"),
            "status": record.status,
        }

    return progress


__all__ = ["create_progress_router", "issue_stream_ticket", "redeem_stream_ticket"]
