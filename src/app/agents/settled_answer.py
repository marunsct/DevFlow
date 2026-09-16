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


#: Warn a stage once it has used this share of its step budget. Below it the
#: warning is noise; above it the stage is about to lose everything it has.
BUDGET_WARNING_FRACTION = 0.7

#: How far back to look for an answer the stage already wrote. Bounded so an
#: answer from the very start of a long stage, superseded by the work since,
#: does not stop it.
ANSWER_LOOKBACK_MESSAGES = 30

#: At most this many field errors in one correction. A model that got every
#: field wrong needs the first few and a fresh look, not a wall of text.
MAX_REPORTED_ERRORS = 6

#: The field paths from the most recent diagnosis, for the log line only.
#: Without them the log says a stage "sent an answer that does not satisfy its
#: schema" and nothing about which part - which on run-44e9fc83 meant watching
#: `product_scope` get fixed and the stage keep failing, with no way to see
#: what else was wrong. Diagnosing what you cannot see is finding 47 again.
_LAST_FAILING_FIELDS: list[str] = []


def _why_it_was_not_accepted(message: Any, schema: Any) -> str:
    """Why the JSON in this message is not a valid answer, or "" if it is.

    Measured on run-5c7d7d8d's `principal_architect`: twenty-one minutes,
    fifteen answers, eight identical `ls {'path': '/'}` between them, no
    progress. The schema declares `product_scope: str` and the model emitted
    `"product_scope": {"covers": [...], "defers": [...]}` every time. Pydantic
    says exactly what is wrong - "Input should be a valid string" - and the
    model never saw it, because an answer written into the conversation goes
    through no validation at all. Only the structured-output channel validates,
    and the model was not using it.

    The recovery that already exists reads such an answer back when the stage
    ends, which helps only when the answer is CORRECT. A near miss is discarded
    and the stage spins to the recursion limit with nothing to correct.
    """
    if schema is None:
        return ""
    text = str(getattr(message, "content", "") or "")
    if "{" not in text:
        return ""
    from app.graph.workflow import _first_json_object

    candidate = _first_json_object(text)
    if not candidate:
        return ""
    try:
        payload = json.loads(candidate)
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    try:
        schema.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 - any validation failure is the point
        _LAST_FAILING_FIELDS[:] = failing_fields(exc)
        return _render_errors(exc)
    return ""


def failing_fields(exc: Exception) -> list[str]:
    """Just the field paths, for a log line that has to be read by a person."""
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return []
    try:
        return [
            ".".join(str(part) for part in error.get("loc", ())) or "(root)"
            for error in errors()
        ]
    except Exception:  # noqa: BLE001
        return []


def _render_errors(exc: Exception) -> str:
    """The validation failure as a short list of fields to fix."""
    lines: list[str] = []
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            for error in list(errors())[:MAX_REPORTED_ERRORS]:
                where = ".".join(str(part) for part in error.get("loc", ())) or "(root)"
                lines.append(f"  {where}: {error.get('msg', 'is not valid')}")
        except Exception:  # noqa: BLE001
            lines = []
    if not lines:
        lines = [f"  {str(exc)[:300]}"]
    return (
        "Your last message contained a JSON object, and it is not a valid "
        "response for this stage, so the workflow did not receive it. Nothing "
        "has been recorded. These fields are wrong:\n"
        + "\n".join(lines)
        + "\n\nFix exactly those fields and send the object again. Do not "
        "start the work over and do not call any more tools - everything else "
        "you wrote was fine."
    )


def _most_recent_answer(messages: list[Any], schema: Any) -> Any | None:
    """The newest assistant message that holds a valid answer, if any.

    Reading only the last message was the first version. It misses a stage that
    answered and then kept talking - which is the shape that cost run-d6369866
    eleven and a half minutes, because the answer was several turns back by the
    time the repetition began.

    Bounded to the recent tail: an answer from the very start of a long stage
    has usually been superseded by the work since, and stopping on it would
    discard that work.
    """
    for message in reversed(messages[-ANSWER_LOOKBACK_MESSAGES:]):
        if getattr(message, "type", None) != "ai":
            continue
        found = _answer_in(message, schema)
        if found is not None:
            return found
    return None


def _running_out_of_room(messages: list[Any], limit: int) -> str:
    """Tell a stage it is close to its step ceiling, or "" when it is not.

    A stage that reaches the ceiling is stopped and, if nothing can be
    salvaged, restarted from an empty conversation - losing every file it
    reasoned about and every result it has seen.

    Measured on run-37476645: `specialist_testing_2` spent all three of its
    attempts in an edit-run-edit-run loop on a failing suite, using 170 tool
    calls, and never returned its answer. `specialist_ui_ux_0` used 175 and
    needed a restart of its own. The limit's own docstring says "60 is roughly
    twice the longest healthy stage observed across fourteen runs, so a working
    stage never meets it" - which was measured against a different model and is
    no longer true. On this one the median stage takes 3 to 12 tool calls and
    the tail reaches 175.

    Raising the ceiling would let a genuine runaway burn the larger number
    before anything stopped it. Telling the stage instead costs nothing and
    asks for the one thing that actually helps: return what you have.
    """
    used = sum(1 for m in messages if getattr(m, "type", None) == "ai")
    if limit <= 0 or used < int(limit * BUDGET_WARNING_FRACTION):
        return ""
    return (
        f"You have used about {used} of the {limit} steps this stage is allowed. "
        "When they run out the stage is stopped and started again from an empty "
        "conversation, losing everything you have read and worked out. Stop "
        "exploring and return your structured response now, with what you have. "
        "An answer that is complete but imperfect is worth far more than none."
    )


def build_settled_answer_middleware(
    schema: Any, stage_name: str = "", step_limit: int = 0
) -> Any:
    """Middleware that stops a stage circling once its answer is written."""
    from langchain.agents.middleware import AgentMiddleware
    from langchain.agents.middleware.types import hook_config
    from langchain_core.messages import AIMessage

    class SettledAnswerMiddleware(AgentMiddleware):
        def wrap_model_call(self, request: Any, handler: Any) -> Any:
            """Tell the model why its last answer was not a valid one.

            Appended to the request rather than written to history, for the
            same reason the workspace digest is: it is a correction the model
            needs on this call, and appending to history after an assistant
            message that has pending tool calls would break their pairing.
            """
            try:
                messages = getattr(request, "messages", None)
                if not isinstance(messages, list) or not messages:
                    return handler(request)
                last_ai = next(
                    (m for m in reversed(messages) if getattr(m, "type", None) == "ai"),
                    None,
                )
                if last_ai is None:
                    return handler(request)
                correction = _why_it_was_not_accepted(last_ai, schema)
                if correction:
                    logger.info(
                        "Stage %s sent an answer that does not satisfy its schema "
                        "(%s); returning the validation errors",
                        stage_name or "?",
                        ", ".join(_LAST_FAILING_FIELDS[:MAX_REPORTED_ERRORS]) or "unknown",
                    )
                else:
                    # Logged apart from the schema case, and never using
                    # `_LAST_FAILING_FIELDS`. Both corrections shared one log
                    # line, so a budget warning was reported as "sent an answer
                    # that does not satisfy its schema" and named whatever
                    # fields some earlier, unrelated diagnosis had left in that
                    # module-level list - possibly from a different stage.
                    #
                    # The cost was not cosmetic. It made the two impossible to
                    # tell apart in a log, so "did the budget warning fire?"
                    # could not be answered from the record at all, and the
                    # schema-failure count silently absorbed every warning.
                    # Diagnosing what you cannot see is finding 47 again.
                    correction = _running_out_of_room(messages, step_limit)
                    if correction:
                        logger.info(
                            "Stage %s is close to its step ceiling; telling it to "
                            "return what it has",
                            stage_name or "?",
                        )
                if not correction:
                    return handler(request)
                request = request.override(
                    messages=[*messages, {"role": "user", "content": correction}]
                )
            except Exception:  # noqa: BLE001 - never fail the call over a hint
                return handler(request)
            return handler(request)

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
            # The answer need not be in the LAST message. run-d6369866's
            # `scrum_master` wrote a valid sprint plan at 15:23:30 and then
            # spent eleven minutes writing prose about creating files it has
            # no tools to create, so by the time it was circling, the last
            # message held no answer and this check was blind to it.
            answer = _most_recent_answer(messages, schema)
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


__all__ = [
    "ANSWER_LOOKBACK_MESSAGES",
    "BUDGET_WARNING_FRACTION",
    "MAX_REPORTED_ERRORS",
    "MUTATING_TOOLS",
    "build_settled_answer_middleware",
]
