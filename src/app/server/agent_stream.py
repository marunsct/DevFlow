"""Publishes what an agent is doing while it is doing it.

The dashboard could show which node was running and nothing else, because the
graph only reports at node boundaries: `_run_gated_agent` calls `agent.invoke`,
which returns when the whole turn is finished. On a real model that is minutes
of silence.

This observes the same turn through LangChain's callback interface and publishes
one event per assistant message, per tool call and per tool result. It never
changes control flow, which matters because the code it observes is the
interrupt-and-resume path.

Everything here is best-effort. A failure to narrate must never fail the run
that was being narrated, so every publish is wrapped and nothing re-raises.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_core.callbacks.base import BaseCallbackHandler

logger = logging.getLogger(__name__)

MAX_TEXT = 2_000
"""Characters of any one message that reach the dashboard.

The full text is already in the model's own context and, for tool output, in the
journal. This is a UI feed, not a record.
"""

MAX_EVENTS_PER_RUN = 5_000
"""Ceiling on agent-activity events per run.

A model in a tool-calling loop can emit thousands of messages. Without a ceiling
one pathological run fills Redis and makes every dashboard poll slower.
"""


def _clip(text: str) -> str:
    text = str(text or "")
    if len(text) <= MAX_TEXT:
        return text
    return text[:MAX_TEXT] + f"\n\n[+{len(text) - MAX_TEXT:,} more characters]"


class AgentActivityStream(BaseCallbackHandler):
    """Publish an agent's messages and tool calls to a run's event stream."""

    def __init__(self, run_id: str, stage: str) -> None:
        self.run_id = run_id
        self.stage = stage
        self._published = 0

    # -- publishing ---------------------------------------------------------

    def _publish(
        self, event_type: str, message: str, metadata: dict[str, Any] | None = None
    ) -> None:
        if self._published >= MAX_EVENTS_PER_RUN:
            return
        try:
            from app.server.events import EventBus, redact_metadata
            from app.server.redis_client import get_redis_client

            client = get_redis_client()
            key = f"run:{self.run_id}:history"
            sequence = client.incr(f"run:{self.run_id}:seq")
            body = json.dumps(
                {
                    "run_id": self.run_id,
                    "event_id": str(uuid.uuid4()),
                    "sequence": sequence,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "stage": self.stage,
                    "event_type": event_type,
                    "message": message,
                    "metadata": redact_metadata(metadata or {}),
                }
            )
            # The same pipeline `EventBus.publish` uses, for the same reason: a
            # bare rpush would bypass the history cap, and agent activity is by
            # far the highest-volume event type there is - exactly what the cap
            # exists to bound.
            pipe = client.pipeline()
            pipe.rpush(key, body)
            pipe.ltrim(key, -EventBus.MAX_HISTORY, -1)
            pipe.expire(key, EventBus.HISTORY_TTL_SECONDS)
            pipe.expire(f"run:{self.run_id}:seq", EventBus.HISTORY_TTL_SECONDS)
            pipe.publish(f"run:{self.run_id}:events", body)
            pipe.execute()
            self._published += 1
        except Exception:  # noqa: BLE001 - narration is never load-bearing
            logger.debug(
                "Could not publish agent activity for %s", self.run_id, exc_info=True
            )

    def publish_outcome(self, summary: str) -> None:
        """Record what this stage decided. See `publish_stage_outcome`."""
        if summary:
            self._publish("log", _clip(summary))

    # -- callbacks ----------------------------------------------------------

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:  # noqa: ARG002
        try:
            for generations in getattr(response, "generations", []) or []:
                for generation in generations or []:
                    text = getattr(generation, "text", "") or ""
                    if text.strip():
                        self._publish("agent_message", _clip(text))
        except Exception:  # noqa: BLE001
            logger.debug("Could not read an LLM response", exc_info=True)

    def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:  # noqa: ARG002
        name = (serialized or {}).get("name") or "tool"
        self._publish("tool_call", f"{name}: {_clip(input_str)}", {"tool": name})

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:  # noqa: ARG002
        self._publish("tool_result", _clip(output))

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:  # noqa: ARG002
        self._publish("tool_result", f"Failed: {_clip(str(error))}", {"failed": True})


def activity_stream_enabled() -> bool:
    """Opt-out switch, on by default. Set STREAM_AGENT_ACTIVITY=false to silence."""
    return os.environ.get("STREAM_AGENT_ACTIVITY", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def build_activity_callbacks(run_id: str | None, stage: str) -> list[BaseCallbackHandler]:
    """The callbacks to attach to one agent invocation; empty when unavailable.

    Two handlers with different jobs. `AgentActivityStream` feeds the dashboard
    and clips at 2,000 characters; the transcript keeps the full prompt and the
    full reply for debugging a run long after it ended. They are built together
    so a run cannot end up with one and not the other.
    """
    if not run_id:
        return []
    handlers: list[BaseCallbackHandler] = []
    if activity_stream_enabled():
        handlers.append(AgentActivityStream(run_id, stage))
    try:
        from app.observability.transcript import (
            build_transcript_callback,
            transcripts_enabled,
        )

        if transcripts_enabled():
            handlers.append(build_transcript_callback(run_id, stage))
    except Exception:  # noqa: BLE001 - a record must never cost the run its agent
        logger.debug("Could not build the transcript callback", exc_info=True)
    return handlers


def publish_stage_outcome(
    callbacks: list[BaseCallbackHandler], summary: str
) -> None:
    """Record what a stage decided, as a `log` event on its own stage.

    A stage's answer reaches the run through its structured response, and the
    structured response is not a message - so nothing in the event stream
    carries it. The effect on run-5d83e946 was that sprint 2's milestone was
    rejected and the reasons appeared nowhere an operator could see: the sprint
    simply went round again. The reasons existed, in the next stage's prompt,
    which is not somewhere anyone can look.

    The property that made it worth fixing is the direction of the bias. When
    the model MISBEHAVES and writes its verdict as prose, `on_llm_end` publishes
    it and the timeline shows everything; when the model behaves correctly, the
    timeline shows nothing. Observability was inversely related to correctness.
    """
    if not summary:
        return
    for handler in callbacks:
        if isinstance(handler, AgentActivityStream):
            handler.publish_outcome(summary)
            return


__all__ = [
    "AgentActivityStream",
    "activity_stream_enabled",
    "build_activity_callbacks",
    "publish_stage_outcome",
]
