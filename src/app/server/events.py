from __future__ import annotations

import asyncio
import copy
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal

import os

from pydantic import BaseModel, ConfigDict, Field, ValidationError


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
    files_modified: int = Field(default=0, description="Count of files modified so far.")
    tests_passed: int = Field(default=0, description="Count of tests passed so far.")
    tests_failed: int = Field(default=0, description="Count of tests failed so far.")
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
    """Redis-backed event history and live fan-out for run progress.

    History is a capped list rather than an unbounded one, and it is read by
    range rather than in full. The previous implementation `RPUSH`ed forever with
    no TTL and answered every poll with `LRANGE 0 -1`, parsing the entire history
    into Pydantic models on each request - cost that grew linearly with run
    length on a path the dashboard polls continuously.
    """

    MAX_HISTORY = int(os.environ.get("RUN_EVENT_HISTORY_MAX", "5000"))
    HISTORY_TTL_SECONDS = int(os.environ.get("RUN_EVENT_TTL_SECONDS", str(30 * 24 * 3600)))

    def __init__(self, redis_client: Any | None = None) -> None:
        self._redis_override = redis_client

    @property
    def _redis(self):
        if self._redis_override is not None:
            return self._redis_override
        from app.server.redis_client import get_async_redis_client

        return get_async_redis_client()

    @staticmethod
    def _history_key(run_id: str) -> str:
        return f"run:{run_id}:history"

    @staticmethod
    def _channel(run_id: str) -> str:
        return f"run:{run_id}:events"

    @staticmethod
    def _sequence_key(run_id: str) -> str:
        return f"run:{run_id}:seq"

    async def next_sequence(self, run_id: str) -> int:
        return int(await self._redis.incr(self._sequence_key(run_id)))

    async def publish(self, run_id: str, event: RunEvent) -> None:
        payload = event.model_dump_json()
        key = self._history_key(run_id)
        pipe = self._redis.pipeline()
        pipe.rpush(key, payload)
        # Cap the list and give it a TTL so a long-lived deployment cannot fill
        # Redis with the history of runs nobody will ever look at again.
        pipe.ltrim(key, -self.MAX_HISTORY, -1)
        pipe.expire(key, self.HISTORY_TTL_SECONDS)
        pipe.expire(self._sequence_key(run_id), self.HISTORY_TTL_SECONDS)
        pipe.publish(self._channel(run_id), payload)
        await pipe.execute()

    @asynccontextmanager
    async def subscribe(self, run_id: str) -> AsyncIterator[AsyncIterator[RunEvent]]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._channel(run_id))

        async def event_generator() -> AsyncIterator[RunEvent]:
            try:
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    data = message["data"]
                    if data == "CLOSE":
                        break
                    try:
                        yield RunEvent.model_validate_json(data)
                    except ValidationError:
                        # A malformed payload must not tear down a live stream.
                        continue
            finally:
                await pubsub.unsubscribe(self._channel(run_id))
                await pubsub.aclose()

        try:
            yield event_generator()
        finally:
            pass

    async def get_history(
        self, run_id: str, *, offset: int = 0, limit: int | None = None, since_sequence: int | None = None
    ) -> list[RunEvent]:
        """Return a page of history, or everything after a sequence number."""
        key = self._history_key(run_id)
        if since_sequence is not None:
            # Replay is bounded by MAX_HISTORY, so scanning the retained window
            # is cheap and avoids a second index.
            raw = await self._redis.lrange(key, 0, -1)
            events = [RunEvent.model_validate_json(item) for item in raw]
            return [e for e in events if e.sequence > since_sequence]

        stop = -1 if limit is None else offset + limit - 1
        raw = await self._redis.lrange(key, offset, stop)
        return [RunEvent.model_validate_json(item) for item in raw]

    async def history_length(self, run_id: str) -> int:
        return int(await self._redis.llen(self._history_key(run_id)))

    async def close(self, run_id: str) -> None:
        """Tell live subscribers the run is finished."""
        await self._redis.publish(self._channel(run_id), "CLOSE")

    async def purge(self, run_id: str) -> None:
        """Delete a run's event history and sequence counter."""
        await self._redis.delete(self._history_key(run_id), self._sequence_key(run_id))


async def publish_stage_event(
    bus: EventBus,
    run_id: str,
    stage: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Publish one stage-change event with a real sequence number."""
    event = RunEvent(
        run_id=run_id,
        # This was hardcoded to 0, which collided every event published through
        # this helper and broke both the polling cursor and reconnect replay.
        sequence=await bus.next_sequence(run_id),
        stage=stage,
        event_type="stage_change",
        message=message,
        metadata=redact_metadata(metadata) if metadata else {},
    )
    await bus.publish(run_id, event)


__all__ = ["EventBus", "RunEvent", "publish_stage_event", "redact_metadata"]
