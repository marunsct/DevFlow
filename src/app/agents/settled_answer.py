"""End a stage once the model has answered and stopped making progress.

Measured on run-5d83e946. `milestone_review` produced a complete verdict -
`{"status": "changes_required", ...}` carrying two blocking findings, one of
them the copy-test defect that the static checks had missed - as the CONTENT of
an assistant message that also carried a `read_file` call. It did that
twenty-seven times in three and a half minutes. Every one of those calls asked
for the same twenty lines of the same file (`limit: 20, offset: 20`) and got
the same bytes back.

An agent loop cannot end a turn with a pending tool call, so it ran the read,
handed back an identical result, and the model wrote the identical verdict
again, at about six and a half seconds a cycle, until the recursion limit
stopped the stage and the answer was recovered from the wreckage. That recovery
works. It costs sixty model turns to reach.

This ends the turn at the point the evidence is unambiguous: the model has
written a valid, complete instance of the stage's response schema, and every
tool it is asking for is one it has already run with identical arguments.

Repetition is what makes it safe. A model still finding something out asks for
something it has not seen, and is left alone however much it has already
written - so this cannot cut short an investigation, only a circle. Both
conditions have to hold: an answer nobody can use yet is not a reason to stop,
and a repeated read by a model that has not answered is the ordinary cost of
re-reading a file.

Repetition is counted from the last change, not from the start of the thread.
A specialist that writes a file and reads it back issues a byte-identical
request and gets different content; that is the ordinary shape of work, and
cutting it off would be a worse failure than the spin this fixes.

The pending calls are dropped from the message before the jump. Without that
the thread ends holding a tool call with no result, which is invalid history
for any caller that re-invokes it - and `_nudge_for_the_structured_response`
does exactly that. The content is left untouched, so the answer is read back by
`_answer_written_into_the_conversation` on the normal return path, at no model
call.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _call_signature(call: Any) -> str:
    """A tool call reduced to what makes two of them the same request."""
    if isinstance(call, dict):
        name = call.get("name") or ""
        arguments = call.get("args")
    else:
        name = getattr(call, "name", "") or ""
        arguments = getattr(call, "args", None)
    try:
        rendered = json.dumps(arguments, sort_keys=True, default=str)
    except (TypeError, ValueError):
        rendered = str(arguments)
    return f"{name}({rendered})"


def _answer_in(message: Any, schema: Any) -> Any | None:
    """The message content read as an instance of the stage's response schema.

    Validated rather than pattern-matched, so a model that merely mentions JSON
    on its way to somewhere else is not mistaken for one that has finished.
    """
    if schema is None:
        return None
    text = str(getattr(message, "content", "") or "")
    if "{" not in text:
        return None
    from app.graph.workflow import _first_json_object

    candidate = _first_json_object(text)
    if not candidate:
        return None
    try:
        payload = json.loads(candidate)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return schema.model_validate(payload)
    except Exception:  # noqa: BLE001 - a near-miss is not the answer
        return None


#: Tools that change what a later read would return. A repeat that follows one
#: of these is not a repeat in any sense that matters - the same request can
#: legitimately come back with different bytes.
MUTATING_TOOLS = frozenset(
    {
        "write_artifact",
        "edit_artifact",
        "delete_artifact",
        "move_artifact",
        "run_terminal_command",
    }
)


def _asks_only_for_what_cannot_have_changed(pending: list[Any], history: list[Any]) -> bool:
    """Whether every pending call repeats one made since the last change.

    Two conditions, not one. A call this thread has issued before is only a
    circle if nothing has happened since that could alter the answer: a
    specialist that writes a file and reads it back issues a byte-identical
    request and gets different content, which is the ordinary shape of work and
    must not be mistaken for a spin.
    """
    if not pending:
        return False
    seen_since_last_change: set[str] = set()
    for message in history:
        for call in getattr(message, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
            if name in MUTATING_TOOLS:
                # Everything read before this could now read differently.
                seen_since_last_change.clear()
            seen_since_last_change.add(_call_signature(call))
    return all(_call_signature(c) in seen_since_last_change for c in pending)


def build_settled_answer_middleware(schema: Any, stage_name: str = "") -> Any:
    """Middleware that stops a stage circling once its answer is written."""
    from langchain.agents.middleware import AgentMiddleware
    from langchain.agents.middleware.types import hook_config
    from langchain_core.messages import AIMessage

    class SettledAnswerMiddleware(AgentMiddleware):
        @hook_config(can_jump_to=["end"])
        def after_model(self, state: Any, runtime: Any = None) -> dict[str, Any] | None:
            # This runs after every model call of every gated stage. An
            # exception here would end the stage, which is worse than the spin
            # it exists to prevent, so a failure means "decide nothing" and the
            # loop behaves exactly as it did before this middleware existed.
            try:
                return self._decide(state)
            except Exception:  # noqa: BLE001 - never fail the stage it guards
                logger.exception(
                    "Settled-answer check failed in stage %s; leaving the loop alone",
                    stage_name or "?",
                )
                return None

        def _decide(self, state: Any) -> dict[str, Any] | None:
            messages = list((state or {}).get("messages") or [])
            if not messages:
                return None
            last = messages[-1]
            if getattr(last, "type", None) != "ai":
                return None
            pending = list(getattr(last, "tool_calls", None) or [])
            if not pending:
                # A turn with no pending call ends on its own.
                return None
            answer = _answer_in(last, schema)
            if answer is None:
                return None
            if not _asks_only_for_what_cannot_have_changed(pending, messages[:-1]):
                return None

            logger.info(
                "Stage %s has written its answer and is repeating %d tool call(s) "
                "it already made; ending the stage instead of circling",
                stage_name or "?", len(pending),
            )
            # Same id replaces the message; same content keeps the answer where
            # the normal return path already looks for it.
            settled = AIMessage(
                content=getattr(last, "content", "") or "",
                id=getattr(last, "id", None),
            )
            return {"messages": [settled], "jump_to": "end"}

    return SettledAnswerMiddleware()


__all__ = ["MUTATING_TOOLS", "build_settled_answer_middleware"]
