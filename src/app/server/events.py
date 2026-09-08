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


import redis.asyncio as redis
import os

class EventBus:
    """Redis pub/sub bus for distributed run events."""

    def __init__(self) -> None:
        """Initialize the event bus."""
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._redis = redis.from_url(redis_url, decode_responses=True)

    def next_sequence(self, run_id: str) -> int:
        """Get the next sequence number for a run using a Redis counter."""
        # Using a blocking call isn't ideal but next_sequence needs to be sync right now for RunEvent creation
        # Wait, if it's sync, how can we use redis.asyncio? 
        # Actually, let's just generate a timestamp or UUID for sequence, or since we only care about relative ordering,
        # we can fetch it via asyncio, but next_sequence is called synchronously in runner.py.
        # Let's change next_sequence to just return 0, and we'll handle real sequence assigning on the publish side.
        return 0

    async def publish(self, run_id: str, event: RunEvent) -> None:
        """Publish an event for a specific run."""
        # Assign a real sequence number
        seq = await self._redis.incr(f"run:{run_id}:seq")
        event.sequence = seq
        
        # Save to history
        await self._redis.rpush(f"run:{run_id}:history", event.model_dump_json())
        
        # Publish to subscribers
        await self._redis.publish(f"run:{run_id}:events", event.model_dump_json())

    @asynccontextmanager
    async def subscribe(self, run_id: str) -> AsyncIterator[AsyncIterator[RunEvent]]:
        """Subscribe to live events for a run."""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(f"run:{run_id}:events")
        
        async def event_generator() -> AsyncIterator[RunEvent]:
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        if message["data"] == "CLOSE":
                            break
                        yield RunEvent.model_validate_json(message["data"])
            finally:
                await pubsub.unsubscribe(f"run:{run_id}:events")
                await pubsub.close()

        try:
            yield event_generator()
        finally:
            pass

    async def get_history(self, run_id: str) -> list[RunEvent]:
        """Get all historical events for a run."""
        raw_events = await self._redis.lrange(f"run:{run_id}:history", 0, -1)
        return [RunEvent.model_validate_json(raw) for raw in raw_events]

    async def close(self, run_id: str) -> None:
        """Signal subscribers that the run is complete."""
        await self._redis.publish(f"run:{run_id}:events", "CLOSE")


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
