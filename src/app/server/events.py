from __future__ import annotations

import asyncio
import copy
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal

from pydantic import BaseModel, ConfigDict, Field


class RunEvent(BaseModel):
    """Canonical event model for run updates."""
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="The ID of the run.")
    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the event.",
    )
    sequence: int = Field(description="Monotonic sequence number for the run.")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp of the event.",
    )
    stage: str = Field(description="The stage in which the event occurred.")
    event_type: Literal[
        "stage_change",
        "log",
        "artifact",
        "review_request",
        "approval_request",
        "approval_auto",
        "error",
        "complete",
    ] = Field(description="Type of the event.")
    message: str = Field(description="Human-readable message.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Safe, redacted metadata associated with the event.",
    )


def redact_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive keys from a metadata dictionary."""
    redacted = copy.deepcopy(meta)
    
    # Define sensitive keywords to search for in keys (case-insensitive)
    sensitive_keywords = (
        "key",
        "secret",
        "token",
        "password",
        "credential",
        "auth",
    )
    
    def _redact_dict(d: dict[str, Any]) -> None:
        for k, v in d.items():
            k_lower = k.lower()
            if any(keyword in k_lower for keyword in sensitive_keywords):
                d[k] = "[REDACTED]"
            elif isinstance(v, dict):
                _redact_dict(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        _redact_dict(item)
                        
    _redact_dict(redacted)
    return redacted


class EventBus:
    """In-memory pub/sub bus for run events."""

    def __init__(self) -> None:
        """Initialize the event bus."""
        self._lock = asyncio.Lock()
        # dict mapping run_id to a list of events
        self._history: dict[str, list[RunEvent]] = {}
        # dict mapping run_id to a list of queues for subscribers
        self._queues: dict[str, list[asyncio.Queue[RunEvent | None]]] = {}

    def _next_sequence(self, run_id: str) -> int:
        """Get the next sequence number for a run (must be called with lock held)."""
        if run_id not in self._history:
            return 1
        return len(self._history[run_id]) + 1

    def next_sequence(self, run_id: str) -> int:
        """Get the next sequence number for a run (thread-safe, non-async).

        This is a synchronous convenience for callers that construct a
        ``RunEvent`` before passing it to ``publish()``.  It reads the
        history length without the lock, which is safe because Python's
        GIL protects dict reads and list length checks, and the only
        writer is the single event-loop thread.
        """
        events = self._history.get(run_id)
        return 1 if events is None else len(events) + 1

    async def publish(self, run_id: str, event: RunEvent) -> None:
        """Publish an event for a specific run."""
        async with self._lock:
            # Add to history
            if run_id not in self._history:
                self._history[run_id] = []
            self._history[run_id].append(event)
            
            # Put on all subscriber queues
            if run_id in self._queues:
                for q in self._queues[run_id]:
                    # We can use put_nowait as these are unbounded queues
                    q.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self, run_id: str) -> AsyncIterator[AsyncIterator[RunEvent]]:
        """Subscribe to live events for a run.
        
        Yields an AsyncIterator that produces RunEvent objects.
        The iterator terminates when the stream is closed (indicated by a None sentinel).
        """
        queue: asyncio.Queue[RunEvent | None] = asyncio.Queue()
        
        async with self._lock:
            if run_id not in self._queues:
                self._queues[run_id] = []
            self._queues[run_id].append(queue)
            
        async def event_generator() -> AsyncIterator[RunEvent]:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item

        try:
            yield event_generator()
        finally:
            async with self._lock:
                if run_id in self._queues:
                    try:
                        self._queues[run_id].remove(queue)
                    except ValueError:
                        pass
                    if not self._queues[run_id]:
                        del self._queues[run_id]

    async def history(self, run_id: str, since_sequence: int = 0) -> list[RunEvent]:
        """Get past events for a run."""
        async with self._lock:
            if run_id not in self._history:
                return []
            events = self._history[run_id]
            
            if since_sequence <= 0:
                return list(events)
                
            # Events are ordered by sequence, and sequence is 1-indexed
            # So since_sequence=1 means return events from sequence 2 onwards
            # events[i] has sequence i+1
            return [e for e in events if e.sequence > since_sequence]

    async def close(self, run_id: str) -> None:
        """Send a sentinel (None) to all subscriber queues to signal end-of-stream."""
        async with self._lock:
            if run_id in self._queues:
                for q in self._queues[run_id]:
                    q.put_nowait(None)


async def publish_stage_event(
    bus: EventBus,
    run_id: str,
    stage: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Convenience factory function for the most common event type."""
    meta = redact_metadata(metadata) if metadata else {}
    
    # We need to get the next sequence number safely
    async with bus._lock:
        sequence = bus._next_sequence(run_id)
        
    event = RunEvent(
        run_id=run_id,
        sequence=sequence,
        stage=stage,
        event_type="stage_change",
        message=message,
        metadata=meta,
    )
    
    await bus.publish(run_id, event)
