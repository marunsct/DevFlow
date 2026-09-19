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


def _repair_json(text: str) -> str | None:
    """Close the brackets and quotes a model left open, or None if hopeless.

    Measured on run-91a18470: `specialist_testing` wrote its complete answer to
    `docs/structured_response.json` fifty-nine times, and every copy was
    truncated one character short - `defects` missing its closing `]`, so the
    object is 3068 bytes long and fails at character 3067. The answer was
    there, complete in everything but punctuation, and nothing in this module
    could accept it. So the stage could neither return the answer nor write it,
    and circled until the run's repeat guard killed it.

    A model that emits near-valid JSON is common, and a harness that accepts
    only perfect JSON will spend a stage's whole budget on a one-character
    omission. This is the narrowest repair that recovers it: append the closers
    implied by what is still open, then let schema validation decide.
    Validation is the real test - a repair that produces something the schema
    rejects is discarded, so this can never turn a wrong answer into an accepted
    one. It can only promote an answer that was already right apart from its
    punctuation.
    """
    if "{" not in text:
        return None
    # Walk the candidate tracking every container we opened, so the closers can
    # be emitted in the reverse of the order they were opened. Appending them as
    # a plain count gets the nesting wrong whenever an array and an object are
    # open at once: `{"a": [1} ` would become `{"a": [1} ]}` when it needs
    # `{"a": [1]}`.
    #
    # A closer that matches nothing open is dropped rather than counted. A
    # truncated object usually loses a closer somewhere in the middle, not at
    # the end - the array's `]` goes missing while the object's `}` is still
    # emitted, so the text ends in a `}` that closes nothing. Keeping it would
    # leave the repair one level too deep forever.
    stack: list[str] = []
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            out.append(ch)
            continue
        out.append(ch)
        if in_string:
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in ("}", "]"):
            if stack and stack[-1] == ch:
                stack.pop()
            else:
                # A closer with nothing to close: the truncation lost its
                # opener, and this character is what makes the text unparseable.
                out[-1] = ""
    if not stack and not in_string:
        return None
    # An unterminated string needs its quote before any closer can count.
    if in_string:
        out.append('"')
    out.extend(reversed(stack))
    return "".join(out)


#: Set on the message a budget hard stop leaves behind. The graph's own
#: recovery (`_nudge_for_the_structured_response`) re-invokes the inner thread
#: to ask for the answer again, and on a thread this middleware already had to
#: stop that is a guaranteed extra model call for an answer the model has
#: shown it cannot produce. See `was_stopped_by_the_budget`.
BUDGET_STOP_MARKER = "settled_answer_budget_stop"


def was_stopped_by_the_budget(result: Any) -> bool:
    """Did `settled_answer` end this thread because it ran out of model calls?

    The hard stop itself works: the inner graph ends. What costs the extra
    calls is the recovery that runs afterwards. `_nudge_for_the_structured_
    response` re-invokes the same inner thread, which re-enters at `__start__`
    and runs another `before_agent -> model -> after_model` cycle, so the model
    makes one more call per gate. Measured on run-91a18470's `test_round_3`:
    eighteen `__start__` writes and thirty-four `jump_to=end` writes on one
    inner thread, the model-call count climbing every gate until the run's
    repeat guard killed it.

    A thread that reached its budget has already been told it is out of room -
    the warning fires from 70% of the budget onward - and kept going. Asking it
    again cannot produce a different answer, so the caller should go straight to
    the fresh-conversation retry instead of nudging.
    """
    if not isinstance(result, dict):
        return False
    for message in reversed(result.get("messages") or []):
        kwargs = getattr(message, "additional_kwargs", None)
        if isinstance(kwargs, dict) and kwargs.get(BUDGET_STOP_MARKER):
            return True
        # Only the trailing AI messages matter; anything older than the last
        # answer attempt is not evidence about how this invoke ended.
        if getattr(message, "type", None) == "ai":
            break
    return False


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
    from app.agents.model_output import strip_reasoning
    from app.graph.workflow import _first_json_object

    # Reasoning first: a model that thinks about the schema before emitting it
    # leaves an example object inside `<think>`, and the first JSON object in
    # the raw text is then the example rather than the answer.
    candidate = _first_json_object(strip_reasoning(text))
    if not candidate:
        return None
    try:
        payload = json.loads(candidate)
    except ValueError:
        # A truncated object is not a wrong answer, it is an unfinished one.
        # Try to close it before giving up; the schema still has to accept it.
        repaired = _repair_json(candidate)
        if not repaired:
            return None
        try:
            payload = json.loads(repaired)
        except ValueError:
            return None
    if not isinstance(payload, dict):
        return None
    from app.agents.wrapped_answer import unwrapped

    try:
        return schema.model_validate(unwrapped(payload, schema))
    except Exception:  # noqa: BLE001 - a near-miss is not the answer
        return None


#: Tool arguments that carry a whole file's content, which is where a model
#: that will not use the response channel puts its answer.
_CONTENT_ARGUMENTS = ("content", "replace")


def _first_content(pending: list[Any]) -> str:
    """The content argument of the first write among `pending`."""
    for call in pending:
        arguments = call.get("args") if isinstance(call, dict) else getattr(call, "args", None)
        if isinstance(arguments, dict):
            for key in _CONTENT_ARGUMENTS:
                text = arguments.get(key)
                if isinstance(text, str) and "{" in text:
                    return text
    return ""


def _answer_in_a_pending_write(pending: list[Any], schema: Any) -> Any | None:
    """A valid answer sitting in the arguments of a write this turn requested.

    Some models never put the structured response anywhere but a file. They
    call `write_artifact` with the complete, valid answer as `content`, the
    tool refuses - a structured response reaches the workflow through the
    schema, and a copy on disk is read by nothing - and they call it again.

    `settled_answer` could not help, because it looks for the answer in the
    message *content* and these turns have none: the model emits a tool call
    and no text at all. So the answer was on the screen, valid, five times
    over, and the stage had no way to accept it.

    Three runs died exactly here - run-0deeb8bf on `final_response.json`,
    run-130deeef on `final_output.json`, run-01f03ed9 on `docs/summary.json`,
    each stopped by the run-level repeat guard after five identical requests.
    run-01f03ed9 had already completed four milestones.

    Safe because of what the schema is: an artifact whose entire content
    validates as this stage's response model IS the structured response. That
    is the same judgement `repository._is_json_document` makes when it refuses
    the write, arrived at from the other side.
    """
    if schema is None:
        return None
    for call in pending:
        name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
        if name not in {"write_artifact", "edit_artifact"}:
            continue
        arguments = call.get("args") if isinstance(call, dict) else getattr(call, "args", None)
        if not isinstance(arguments, dict):
            continue
        for key in _CONTENT_ARGUMENTS:
            text = arguments.get(key)
            if not isinstance(text, str) or "{" not in text:
                continue
            found = _answer_in(AIMessageStub(text), schema)
            if found is not None:
                return found
    return None


class AIMessageStub:
    """Just enough of a message for `_answer_in` to read one string."""

    type = "ai"

    def __init__(self, content: str) -> None:
        self.content = content


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


#: Write tools that say so plainly when they wrote nothing. A refusal from one
#: of these means the filesystem is exactly as it was, so the call cannot have
#: changed what a later read returns. `run_terminal_command` is deliberately
#: absent: a command that exits non-zero may still have installed packages,
#: created a lockfile or half-written a build, so a failure there is no promise
#: that nothing moved.
_TOOLS_THAT_REPORT_WRITING_NOTHING = frozenset(
    {"write_artifact", "edit_artifact", "delete_artifact", "move_artifact"}
)


def _results_by_call_id(history: list[Any]) -> dict[str, str]:
    """Each tool result in this thread, keyed by the call it answered."""
    results: dict[str, str] = {}
    for message in history:
        if getattr(message, "type", None) != "tool":
            continue
        call_id = getattr(message, "tool_call_id", None)
        if call_id:
            results[str(call_id)] = str(getattr(message, "content", "") or "")
    return results


def _actually_changed_something(call: Any, results: dict[str, str]) -> bool:
    """Whether this mutating call altered anything a later read would see.

    Measured on run-0deeb8bf's `defect_fix_2_0`. The model wrote a complete,
    valid answer as message content and, in the same turn, called
    `write_artifact('final_response.json', <that same answer>)`. The tool
    refuses that by design - a structured response reaches the workflow through
    the response schema and a copy on disk is read by nothing - so the write
    was rejected and the filesystem did not move. The model then did it again,
    identically, and again, until the repeat guard stopped the stage and the
    run failed with its answer sitting in the transcript.

    Counting every `write_artifact` as a change is what kept that alive: each
    refusal wiped the record of what had already been asked, so a byte-identical
    repeat never looked like one and the settle never fired. Three runs died
    this way (`final_response.json`, `final_output.json`,
    `docs/structured_response.json`), always with the answer already written.

    Unknown results stay a change. A call whose result is not in the thread
    yet is assumed to have done something, because letting a stage run on is
    far cheaper than ending one that was still working.
    """
    name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
    if name not in _TOOLS_THAT_REPORT_WRITING_NOTHING:
        return True
    call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
    content = results.get(str(call_id)) if call_id else None
    if content is None:
        return True
    from app.agents.repeated_queries import _changed_nothing, _looks_like_a_failure

    return not (_looks_like_a_failure(content) or _changed_nothing(content))


def _asks_only_for_what_cannot_have_changed(pending: list[Any], history: list[Any]) -> bool:
    """Whether every pending call repeats one made since the last change.

    Two conditions, not one. A call this thread has issued before is only a
    circle if nothing has happened since that could alter the answer: a
    specialist that writes a file and reads it back issues a byte-identical
    request and gets different content, which is the ordinary shape of work and
    must not be mistaken for a spin.

    A write that was refused is not a change - see
    `_actually_changed_something`.
    """
    if not pending:
        return False
    results = _results_by_call_id(history)
    seen_since_last_change: set[str] = set()
    for message in history:
        for call in getattr(message, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
            if name in MUTATING_TOOLS and _actually_changed_something(call, results):
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

#: What kind of answer problem the last diagnosis found: "schema" when
#: pydantic rejected the fields, "no-json" when the message held no object at
#: all, "" when nothing was wrong.
#:
#: Without this the log said "sent an answer that does not satisfy its schema
#: (unknown)" for a stage that had answered in prose - a different fault, the
#: same words, and a field list left over from whatever diagnosed last.
#: Measured live on run-ed05e20e at 07:38, where each such call cost three and
#: a half minutes on a 35B model and the log could not say what to change.
_LAST_FAILURE_KIND: str = ""


def _it_is_not_json_at_all(text: str) -> str:
    """What to say when a message holds no JSON object the schema can read.

    A model that answers in prose or Markdown gets no correction from the
    refusal it triggers, because the tool it called to write that prose refuses
    for a different reason - "a structured response is returned, not written to
    a file". So it writes the document again. Measured on run-519a9d8a's
    `specialist_testing_1`: twenty auto-approvals, each a write of the same
    Markdown to the same path.

    The correction names the one thing that is actually wrong - the answer's
    shape, not its content.
    """
    stripped = (text or "").strip()
    if not stripped:
        return ""
    looks_like_markdown = any(
        stripped.startswith(mark) for mark in ("#", "-", "*", "|", ">")
    ) or "```" in stripped
    if not looks_like_markdown:
        return ""
    return (
        "Your last message was a Markdown document, not the structured response "
        "this stage needs. Nothing has been recorded, and writing it to a file "
        "does not record it either - the response is RETURNED, as a JSON object, "
        "and the workflow reads it from your message.\n\n"
        "Send the same content as a single JSON object that satisfies this "
        "stage's response schema. Do not write it to a file, do not wrap it in "
        "a code block for a person to read, and do not call any more tools - "
        "the work is done, only its shape is wrong."
    )


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
    global _LAST_FAILURE_KIND

    # Cleared first, in every path. A module-level diagnosis that survives its
    # own call reports an earlier stage's fields against this one's failure.
    _LAST_FAILING_FIELDS.clear()
    _LAST_FAILURE_KIND = ""
    if schema is None:
        return ""
    text = str(getattr(message, "content", "") or "")
    if "{" not in text:
        # Prose with no object in it at all. The model may have written its
        # answer as a Markdown document instead - measured on run-519a9d8a's
        # `specialist_testing_1`, which wrote `## changed_files` to
        # `docs/structured_response.md` twenty times and was refused each time
        # by a message that never says what shape a right answer has.
        _LAST_FAILURE_KIND = "no-json"
        return _it_is_not_json_at_all(text)
    from app.agents.model_output import strip_reasoning
    from app.graph.workflow import _first_json_object

    # Reasoning first: a model that thinks about the schema before emitting it
    # leaves an example object inside ``, and the first JSON object in
    # the raw text is then the example rather than the answer.
    candidate = _first_json_object(strip_reasoning(text))
    if not candidate:
        _LAST_FAILURE_KIND = "no-json"
        return _it_is_not_json_at_all(text)
    try:
        payload = json.loads(candidate)
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    from app.agents.wrapped_answer import unwrapped

    try:
        schema.model_validate(unwrapped(payload, schema))
    except Exception as exc:  # noqa: BLE001 - any validation failure is the point
        _LAST_FAILING_FIELDS[:] = failing_fields(exc)
        _LAST_FAILURE_KIND = "schema"
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


#: Model calls a stage may make before the workflow's own guards would stop it.
#: Measured across run-0deeb8bf and run-d3965815: the median stage costs 3 to 8
#: calls, the ninetieth percentile 16 to 27, and the worst healthy stage seen is
#: 37. A stage past forty is not working, it is circling.
MODEL_CALLS_PER_STAGE = 40


def _model_calls_used(messages: list[Any]) -> int:
    """How many model calls this stage has cost, counted from its own thread.

    This used to read `langgraph_step` from the running config and compare it
    to `recursion_limit`, on the reasoning that LangGraph publishes the real
    number so there is no need to convert. Both halves of that were wrong in
    the same direction, and the error is visible in run-d3965815.

    `recursion_limit` bounds supersteps *per invoke*, and with `auto_approve`
    every gated tool interrupts and resumes through a fresh
    `agent.invoke(Command(resume=...))`. So the ceiling is re-armed on each
    resume while `langgraph_step` keeps climbing from the checkpoint. The two
    numbers stopped describing the same thing the moment a stage wrote a file.

    Measured directly: `specialist_ui_ux_0` was warned at 42, 46, 50, 54, 58
    and 62 "of the 60 steps this stage is allowed", sailed past the ceiling it
    was being warned about, and finished normally. `specialist_backend_2`
    reached 66. Neither raised `GraphRecursionError`, because neither single
    invoke came close to sixty supersteps.

    The cost of that was not a wrong number in a log. The warning says "stop
    exploring and return your structured response now", and it was reaching
    healthy stages from their eleventh call onward - six of `specialist_ui_ux_0`'s
    seventeen calls carried it. A guard against circling was pushing working
    stages to cut their work short.

    Model calls are the unit the warning's own text is about, they survive an
    approval resume because the messages do, and they need no agreement with
    LangGraph's internals.
    """
    return sum(1 for message in messages if getattr(message, "type", None) == "ai")


def _running_out_of_room(messages: list[Any], limit: int, schema: Any = None) -> str:
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

    What it says depends on whether an answer exists, because what happens
    next does. At the limit `_decide` ends the stage *only if* it finds an
    answer already written; with none, nothing stops the stage there and it
    runs on to the graph's step ceiling, is stopped, and - when there is
    nothing to salvage - is restarted from an empty conversation by
    `_restart_on_a_fresh_conversation`.

    The single message this replaced asserted the graceful ending in both
    cases: "At {limit} this stage ends with whatever answer you have already
    written". For a stage with no answer that is not true, and it is the case
    that matters - the stage reading it has nothing written, and is being told
    its position is safer than it is. Measured across runs 60-67, eleven stages
    reached the warning and made 61 further model calls between them; one ran
    to 57 against a limit of 40, having been told twice over that 40 was where
    it ended.
    """
    used = _model_calls_used(messages)
    if limit <= 0 or used < int(limit * BUDGET_WARNING_FRACTION):
        return ""
    opening = (
        f"You have made about {used} of the {limit} model calls this stage is allowed. "
    )
    if schema is not None and _most_recent_answer(messages, schema) is not None:
        return opening + (
            f"You have already written an answer, so at {limit} this stage ends with "
            "that one and anything you have learned since is lost. Return it now, "
            "with whatever you have added, rather than letting the older version "
            "stand."
        )
    return opening + (
        "You have NOT written a structured response yet. Nothing ends this stage "
        "gracefully without one: it runs on until the step ceiling stops it, and "
        "then it is started again from an empty conversation - every file you have "
        "read, every command you have run and every result you have seen is gone, "
        "and the work begins from nothing. Return your structured response now. An "
        "answer that is complete but imperfect is worth far more than none."
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
                if correction and _LAST_FAILURE_KIND == "no-json":
                    logger.info(
                        "Stage %s answered with no JSON object at all - prose or "
                        "Markdown where the schema was expected; telling it what "
                        "shape an answer has",
                        stage_name or "?",
                    )
                elif correction:
                    logger.info(
                        "Stage %s sent an answer that does not satisfy its schema "
                        "(%s); returning the validation errors",
                        stage_name or "?",
                        ", ".join(_LAST_FAILING_FIELDS[:MAX_REPORTED_ERRORS])
                        or "no field named",
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
                    correction = _running_out_of_room(messages, step_limit, schema)
                    if correction:
                        logger.info(
                            "Stage %s is close to its model-call budget; telling "
                            "it to return what it has",
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
            # The answer need not be in the LAST message. run-d6369866's
            # `scrum_master` wrote a valid sprint plan at 15:23:30 and then
            # spent eleven minutes writing prose about creating files it has
            # no tools to create, so by the time it was circling, the last
            # message held no answer and this check was blind to it.
            # Past the budget, with an answer already written: end. The
            # warning has said so from 70% onward, and on run-08acb1ee's
            # `specialist_ui_ux_0` it said so on twelve consecutive calls -
            # 28, 29, 30 ... 39 - and the stage ignored every one and ended on
            # a `run_terminal_command` at 40.
            #
            # Until now that warning threatened something that does not
            # happen. `MODEL_CALLS_PER_STAGE` was read only to decide when to
            # nag; nothing stopped a stage at it, so "when they run out the
            # stage is stopped" was untrue - the same fault as an allowlist
            # naming programs that are not installed, in a sentence the model
            # is being asked to act on.
            #
            # Ending here is safe in the one way that matters: it only happens
            # when a valid answer exists, and ending with a valid answer is
            # never worse than continuing without one. Under the budget,
            # repetition is still required.
            if step_limit and _model_calls_used(messages) >= step_limit:
                spent = _most_recent_answer(messages, schema)
                if spent is not None:
                    logger.info(
                        "Stage %s reached its model-call budget with an answer "
                        "written; ending it rather than nagging again",
                        stage_name or "?",
                    )
                    return {
                        "messages": [
                            AIMessage(
                                content=getattr(last, "content", "") or "",
                                id=getattr(last, "id", None),
                            )
                        ],
                        "jump_to": "end",
                    }
                # Past the budget with nothing written. The warning has said so
                # on every call since 70% and been ignored each time - measured
                # on run-1a7a62c2, where `specialist_testing` was told 71 times
                # and kept running `npm test` for over an hour and a half.
                #
                # Nothing else here can stop it. `_decide` only ends a stage it
                # can see an answer in, and the graph's own recovery
                # (`_restart_on_a_fresh_conversation`) is reached only when the
                # stage *ends* - so a stage that neither answers nor ends is
                # outside every guard the run has. Ending it now hands it to
                # that recovery, which clears the conversation and retries, and
                # fails the run only after the retry budget is spent.
                logger.warning(
                    "Stage %s is past its model-call budget (%d calls) with no "
                    "structured response written; ending it so the run can "
                    "retry on a fresh conversation",
                    stage_name or "?", _model_calls_used(messages),
                )
                return {
                    "messages": [
                        AIMessage(
                            content=getattr(last, "content", "") or "",
                            id=getattr(last, "id", None),
                            additional_kwargs={BUDGET_STOP_MARKER: True},
                        )
                    ],
                    "jump_to": "end",
                }

            # An answer the model put in a file rather than in the response
            # channel is still an answer, and this turn is about to be refused
            # for it. See `_answer_in_a_pending_write`.
            written = _answer_in_a_pending_write(pending, schema)
            if written is not None:
                logger.info(
                    "Stage %s put its structured response in a write_artifact "
                    "call; taking it as the answer rather than refusing it again",
                    stage_name or "?",
                )
                return {
                    "messages": [
                        AIMessage(
                            content=_first_content(pending),
                            id=getattr(last, "id", None),
                        )
                    ],
                    "jump_to": "end",
                }

            # The model answered in prose in THIS turn, with no tool call at
            # all. Measured on run-519a9d8a's `specialist_testing_1`: the model
            # emitted `{"SpecialistOutput": {...}}` as an `agent_message` and
            # stopped calling tools, twenty times in a row. The answer was
            # complete and valid once unwrapped, but this middleware returned
            # None at the `if not pending` guard above, so nothing ended the
            # stage and the model was asked again for something it had already
            # given.
            #
            # Repetition is not required here, because there is nothing pending
            # to repeat: a turn that makes no tool call cannot be circling. The
            # answer is validated against the schema, which is the real test.
            if not pending:
                in_this_turn = _answer_in(last, schema)
                if in_this_turn is not None:
                    logger.info(
                        "Stage %s returned its structured response as a message "
                        "with no tool call; taking it as the answer",
                        stage_name or "?",
                    )
                    return {
                        "messages": [
                            AIMessage(
                                content=getattr(last, "content", "") or "",
                                id=getattr(last, "id", None),
                            )
                        ],
                        "jump_to": "end",
                    }
                # No answer and nothing pending: the model is thinking out loud
                # or asking a question. Leave it alone, as before.
                return None

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
    "BUDGET_STOP_MARKER",
    "MODEL_CALLS_PER_STAGE",
    "MAX_REPORTED_ERRORS",
    "MUTATING_TOOLS",
    "build_settled_answer_middleware",
    "was_stopped_by_the_budget",
]
