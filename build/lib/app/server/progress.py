"""Configurable live progress endpoints: SSE streaming, polling, and spinner.

Step 6.3 of the workflow plan.  Three progress modes, one canonical event
format.  The client chooses its mode; the server supports all three
simultaneously.  All three consume the same ``EventBus`` and ``RunEvent``
schema from ``app.server.events``.

- **SSE** (``GET /events/stream``): real-time Server-Sent Events with
  ``Last-Event-ID`` reconnect support and keepalive comments.
- **Polling** (``GET /events``): returns a batch of events since a cursor.
- **Spinner** (``GET /status``): minimal payload for a loading indicator.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Query, Request
from sse_starlette.sse import EventSourceResponse

from app.server.events import EventBus, RunEvent
from app.server.runner import RunRecord, WorkflowRunner, _stage_meaning

router = APIRouter()

KEEPALIVE_INTERVAL_SECONDS = 15
"""Send an SSE comment every 15 seconds to prevent proxy timeouts."""


def _event_to_sse_data(event: RunEvent) -> dict[str, str]:
    """Format a RunEvent as an SSE data dict for sse-starlette."""
    return {
        "id": str(event.sequence),
        "event": event.event_type,
        "data": event.model_dump_json(),
    }


async def _sse_generator(
    request: Request,
    event_bus: EventBus,
    run_id: str,
    last_event_id: int,
) -> Any:
    """Async generator that yields SSE events.

    Sends missed events (for reconnect), then streams live events.
    Sends keepalive comments to prevent proxy/CDN timeouts.
    """
    # Replay missed events on reconnect.
    if last_event_id > 0:
        missed = await event_bus.history(run_id, since_sequence=last_event_id)
        for event in missed:
            if await request.is_disconnected():
                return
            yield _event_to_sse_data(event)

    # Stream live events.
    async with event_bus.subscribe(run_id) as stream:
        try:
            async for event in stream:
                if await request.is_disconnected():
                    return
                yield _event_to_sse_data(event)
        except asyncio.CancelledError:
            return


def create_progress_router(runner: WorkflowRunner, event_bus: EventBus) -> APIRouter:
    """Build the progress router with the shared runner and event bus.

    This is a factory because the router needs access to the runner and
    event bus instances, which are created at app startup, not at import
    time.
    """
    progress = APIRouter()

    @progress.get("/{run_id}/events/stream")
    async def stream_events(
        request: Request,
        run_id: str,
    ) -> EventSourceResponse:
        """Server-Sent Events endpoint for live run progress.

        Supports ``Last-Event-ID`` header for automatic reconnect: the
        client will receive all events it missed since disconnecting,
        then resume the live stream.
        """
        record = runner.runs.get(run_id)
        if record is None:
            # Return a 404 as a stream that immediately closes with an error event.
            async def error_gen() -> Any:
                yield {"event": "error", "data": json.dumps({"error": f"Run {run_id} not found"})}

            return EventSourceResponse(error_gen(), status_code=404)

        # Parse Last-Event-ID for reconnect support.
        last_event_id_header = request.headers.get("Last-Event-ID", "0")
        try:
            last_event_id = int(last_event_id_header)
        except ValueError:
            last_event_id = 0

        return EventSourceResponse(
            _sse_generator(request, event_bus, run_id, last_event_id),
            ping=KEEPALIVE_INTERVAL_SECONDS,
        )

    @progress.get("/{run_id}/events")
    async def poll_events(
        run_id: str,
        since: int = Query(0, ge=0, description="Return events after this sequence number."),
    ) -> dict[str, Any]:
        """Polling endpoint: returns events since a cursor.

        The client calls this periodically when SSE is unavailable.
        Response includes a ``cursor`` for the next poll.
        """
        record = runner.runs.get(run_id)
        if record is None:
            return {"error": f"Run {run_id} not found", "events": [], "cursor": 0}

        events = await event_bus.history(run_id, since_sequence=since)
        cursor = events[-1].sequence if events else since
        return {
            "events": [event.model_dump() for event in events],
            "cursor": cursor,
        }

    @progress.get("/{run_id}/status")
    async def spinner_status(run_id: str) -> dict[str, Any]:
        """Minimal status for a spinner UI.

        Returns only the current stage, its human-readable meaning, the
        last update time, and whether the run has terminated.  No event
        history, no log entries — just enough for a loading indicator.
        """
        record = runner.runs.get(run_id)
        if record is None:
            return {"error": f"Run {run_id} not found"}

        is_terminal = record.status in ("completed", "failed", "cancelled")
        return {
            "stage": record.current_stage,
            "stage_meaning": record.stage_meaning or _stage_meaning(record.current_stage),
            "last_updated": record.updated_at,
            "is_terminal": is_terminal,
            "status": record.status,
        }

    return progress


__all__ = ["create_progress_router"]
