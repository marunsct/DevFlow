from __future__ import annotations

import asyncio
import copy
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal

import os

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


class RunEvent(BaseModel):
    """Canonical event model for run updates.

    `extra="ignore"`, not `"forbid"`. This model is not only constructed in
    process - it is parsed back out of a Redis history that outlives any single
    deployment (30-day TTL). Forbidding extras meant that *removing* a field
    made every event already on disk unparseable: dropping the unused
    `files_modified` / `tests_passed` / `tests_failed` counters took out the log
    stream for every existing run at once, because `get_history` validates the
    whole page and one bad record fails all of them.

    Ignoring extras makes a field removal backward-compatible. A field
    *addition* was always safe. Input still cannot invent fields the model
    exposes, because unknown keys are dropped rather than kept.
    """

    model_config = ConfigDict(extra="ignore")

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
        # A gate answered with a denial rather than an approval, because the
        # stage asked for the same thing over and over. Added with the runner
        # code that emits it - and not, the first time, at the same moment:
        # One run reached its third sprint and then died on
        # `ValidationError: Input should be 'stage_change', 'log', ... [type=
        # literal_error, input_value='approval_denied']`. The whole test suite
        # passed, because no test ran the runner's denial path against this
        # model. See `test_event_types_are_registered`.
        "approval_denied",
        # A run parked at its `MAX_RUN_COST_USD` ceiling, naming the spend. Not
        # `error`: the run is intact and the operator may simply raise the
        # ceiling and resume. Registered here in the same change as the runner
        # code that emits it, which is the lesson of `approval_denied` above.
        "budget_pause",
        "error",
        "complete",
        # Agent activity. One event per assistant message, tool call and tool
        # result - never per token: a token stream is one Redis write, one
        # WebSocket frame and one React render per token, for text a human reads
        # in paragraphs.
        "agent_message",
        "tool_call",
        "tool_result",
        # A human's answer to a gate, recorded when it is submitted. Before
        # these existed, a decision was not a fact anywhere: the only trace of
        # it was *which stage ran next*, so every consumer (the timeline and
        # each dashboard) re-derived "was this review approved or sent back"
        # from the stages that followed it, and could be wrong. The event
        # carries the answer itself; the following stage is now only a cross-
        # check. Old runs predate these events and their history cannot be
        # rewritten, so readers still keep the stage-inference fallback for
        # them.
        "review_decision",
        "approval_decision",
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

    @staticmethod
    def _parse_page(raw: list) -> list[RunEvent]:
        """Parse a page of stored events, skipping any that no longer validate.

        The live stream has always skipped a malformed payload rather than
        tearing itself down; history did not, so one unparseable record failed
        the entire page. That is how a field removed from `RunEvent` took the
        log view out for every existing run at once - the history in Redis
        outlives the schema that wrote it, by up to `HISTORY_TTL_SECONDS`.

        Skipping is the right trade for a display feed: a reader would rather
        see 57 of 58 events than an error.
        """
        events: list[RunEvent] = []
        skipped = 0
        for item in raw:
            try:
                events.append(RunEvent.model_validate_json(item))
            except ValidationError:
                skipped += 1
        if skipped:
            logger.warning(
                "Skipped %d stored event(s) that no longer match the RunEvent schema", skipped
            )
        return events

    async def get_history(
        self, run_id: str, *, offset: int = 0, limit: int | None = None, since_sequence: int | None = None
    ) -> list[RunEvent]:
        """Return a page of history, or everything after a sequence number."""
        key = self._history_key(run_id)
        if since_sequence is not None:
            # Replay is bounded by MAX_HISTORY, so scanning the retained window
            # is cheap and avoids a second index.
            raw = await self._redis.lrange(key, 0, -1)
            return [e for e in self._parse_page(raw) if e.sequence > since_sequence]

        stop = -1 if limit is None else offset + limit - 1
        raw = await self._redis.lrange(key, offset, stop)
        return self._parse_page(raw)

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
