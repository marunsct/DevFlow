"""End a stage once the model has answered and stopped making progress.

Measured on one run. `milestone_review` produced a complete verdict -
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
import re
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

    Measured on one run: `specialist_testing` wrote its complete answer to
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
    makes one more call per gate. Measured on one run's `test_round_3`:
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


def _without_repeats(payload: Any) -> Any:
    """`payload` with every list's repeated entries dropped, at any depth.

    For an answer read out of the conversation, which is where a runaway reply
    ends up. Measured on one run's `defect_fix_1_0`: its final reply opened a
    correct response object and then wrote the same eleven lines of its `tests`
    list over and over for 100,189 characters, until the 25,000-token reply
    ceiling cut it off. The truncated object was closed, it validated, and it
    was taken as the answer - with the repetition in it, for every later stage
    that reads a specialist's `tests` to see.

    An entry equal to an earlier one in the same list says nothing the first
    did not, in any field of any schema, so dropping it cannot lose an answer.
    """
    if isinstance(payload, dict):
        return {key: _without_repeats(value) for key, value in payload.items()}
    if isinstance(payload, list):
        kept: list[Any] = []
        seen: set[str] = set()
        for item in payload:
            item = _without_repeats(item)
            try:
                marker = json.dumps(item, sort_keys=True, default=str)
            except (TypeError, ValueError):
                kept.append(item)
                continue
            if marker in seen:
                continue
            seen.add(marker)
            kept.append(item)
        return kept
    return payload


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
        return schema.model_validate(unwrapped(_without_repeats(payload), schema))
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

    Three runs died exactly here - one run on `final_response.json`,
    one run on `final_output.json`, one run on `docs/summary.json`,
    each stopped by the run-level repeat guard after five identical requests.
    One run had already completed four milestones.

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

    Measured on one run's `defect_fix_2_0`. The model wrote a complete,
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

#: Calls at the end of a stage's budget where every tool is taken away and the
#: only thing the model can still do is return its structured response.
#:
#: The warning alone does not work, and that is measured. Across the twelve
#: stored transcripts the "you have NOT written a structured response yet"
#: correction was sent on 276 model calls; 13 of those calls returned the
#: answer and 263 went back to work - 132 `read_file`, 68
#: `run_terminal_command`, 29 `edit_artifact`. On one run the last
#: request of `specialist_testing_1` said "You have made about 39 of the 40
#: model calls this stage is allowed ... Return your structured response now"
#: and the model replied with an `edit_artifact` call. It did that on three
#: consecutive fresh conversations and the run failed.
#:
#: Two, not one, because a model that has just lost its tools may spend a call
#: saying so. Two calls out of forty is the whole cost, and it is only ever
#: paid by a stage that would otherwise be killed on the next call and
#: restarted from an empty conversation - so there is nothing left to lose.
#:
#: Not at the warning threshold, which was the tempting version and is wrong:
#: 23 of the 28 stages that were ever warned went on to answer, some after 36
#: or 40 further calls of real work. Taking their tools away at 70% would have
#: cut off the recoveries to save the failures.
CALLS_RESERVED_FOR_THE_ANSWER = 2


#: Redundant reads refused in one stage before the read tool itself is taken
#: away for the rest of it.
#:
#: Measured on one run's `specialist_ui_ux_1`. It made 73 tool calls, 64
#: of them reads. The read ladder worked exactly as designed - note, withhold,
#: then refuse - and the stage read 30 more times after its first refusal, of
#: which:
#:
#:     16  refused as redundant
#:     13  withheld as redundant
#:      1  returned content it had not seen
#:
#: So once a stage has been refused a redundant read, almost everything it
#: reads afterwards is redundant too, and every rung of a per-file ladder can
#: only redirect it: measured across the earlier runs, a withheld read sent it
#: to a *different* file 61.5% of the time, and the refusal that replaced that
#: rung raised it to 81.2% while cutting same-file retries from 30.0% to 6.2%.
#: The loop ended when the model-call budget withheld every tool and the stage
#: answered.
#:
#: Three, because a refusal already requires twelve repeated reads behind it -
#: the stage has proved the point three times over by then. At three, that run
#: keeps its one useful read and loses about twenty-six wasted model calls.
#:
#: `grep` and the listings are deliberately left: the refusal's own words are
#: "a range you have NOT read still works, and so does `grep`", and a harness
#: that says that and then removes `grep` is the contradiction this file keeps
#: finding elsewhere.
READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL = 3

#: The tools withheld at that point - the two that return a file's contents,
#: and nothing else.
_READ_TOOLS = frozenset({"read_file", "read_repository_file"})

#: Identical refusals of one tool before it is taken away, rather than described
#: again. The repeat note starts at `REPEATS_BEFORE_SAYING_SO` (2), so a stage is
#: told twice before this, which is proportionate: the arguments that fail are
#: sometimes nearly right, and the note is what lets a stage correct them itself.
#: Higher than the read threshold of 3 for the same reason - a refused write is
#: work the stage still has to land, where a refused read is work already done.
IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL = 4

#: A tool result that is a refusal rather than an answer. Every guard in this
#: harness opens one of these ways, and the bracketed group is the repeat note
#: some of them prepend - an anchored match without it stopped counting a call
#: exactly when it started repeating, which is how the audit script came to
#: report 15 failures on a run that had 29.
_REFUSED = re.compile(
    r'^\s*(?:\[[^\]]*\]\s*)?(?:\{"error"|Error:|Refusing|Not running|Not looking|No journalled)',
)

#: How far back to look for an answer the stage already wrote. Bounded so an
#: answer from the very start of a long stage, superseded by the work since,
#: does not stop it.
ANSWER_LOOKBACK_MESSAGES = 30

#: At most this many field errors in one correction. A model that got every
#: field wrong needs the first few and a fresh look, not a wall of text.
MAX_REPORTED_ERRORS = 6

#: The field paths from the most recent diagnosis, for the log line only.
#: Without them the log says a stage "sent an answer that does not satisfy its
#: schema" and nothing about which part - which on one run meant watching
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
#: Measured live on one run at 07:38, where each such call cost three and
#: a half minutes on a 35B model and the log could not say what to change.
_LAST_FAILURE_KIND: str = ""


def _it_is_not_json_at_all(text: str) -> str:
    """What to say when a message holds no JSON object the schema can read.

    A model that answers in prose or Markdown gets no correction from the
    refusal it triggers, because the tool it called to write that prose refuses
    for a different reason - "a structured response is returned, not written to
    a file". So it writes the document again. Measured on one run's
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

    Measured on one run's `principal_architect`: twenty-one minutes,
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
        # answer as a Markdown document instead - measured on one run's
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
    answered and then kept talking - which is the shape that cost one run
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
#: Measured across two runs: the median stage costs 3 to 8
#: calls, the ninetieth percentile 16 to 27, and the worst healthy stage seen is
#: 37. A stage past forty is not working, it is circling.
MODEL_CALLS_PER_STAGE = 40
"""Model calls a stage may spend before it is stopped and retried.

Measured across 71 stage executions in four runs, counting `model_request` records per stage from the transcripts:

    stages that finished under the ceiling   61
      most calls any of them needed          36  (specialist_backend_1)
      next                                   33  (milestone_review)
      median                                  5
      90th percentile                        26

    stages that reached the ceiling          10

So 40 sits four calls above the largest stage that has ever finished, and the
gap between the 90th percentile and the ceiling is where the warnings live.
Lowering it to 30 - which the spinning stages make tempting - would have cut off
`specialist_backend_1` and `milestone_review` mid-answer, and a stage killed with
work in hand is worse than one that wastes a dozen calls before the retry.

Raising it is worse still: the stages that reach 40 do not finish at 50 either.
Every one of the ten above had been told to return what it had from 70% onward,
had content withheld from repeated reads, and had the exit named for it - on
one run's `specialist_testing_1`, seventeen reads withheld and the exit named
96 times across the run. They are not short of room; they are not using it.
"""


def _model_calls_used(messages: list[Any]) -> int:
    """How many model calls this stage has cost, counted from its own thread.

    This used to read `langgraph_step` from the running config and compare it
    to `recursion_limit`, on the reasoning that LangGraph publishes the real
    number so there is no need to convert. Both halves of that were wrong in
    the same direction, and the error is visible in one run.

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

    Measured on one run: `specialist_testing_2` spent all three of its
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


def _nothing_left_but_the_answer(messages: list[Any], limit: int, schema: Any) -> bool:
    """True on the last calls of the budget with no answer written yet.

    Deliberately narrow. An answer already written means `_decide` ends the
    stage gracefully at the limit, so there is nothing to force; and under the
    reserve the stage is doing ordinary work and keeps every tool.
    """
    if limit <= 0 or schema is None:
        return False
    if _model_calls_used(messages) < limit - CALLS_RESERVED_FOR_THE_ANSWER:
        return False
    return _most_recent_answer(messages, schema) is None


def _the_last_reply_was_all_reasoning(messages: list[Any]) -> bool:
    """True when the previous reply spent the whole output budget on nothing.

    `finish_reason: length` with no content and no tool call means the model
    reasoned until its reply was truncated. Measured on one run: 7 of 543
    responses did this, each burning the full 30,000-token budget, and the run
    died when `test_round_2` ended that way three times over.

    It is not an input problem, so trimming context does not address it and a
    larger budget only makes the same spiral more expensive: those seven replies
    had inputs of 34k-66k tokens, while the largest input of the run, 77k,
    answered in 361 tokens.

    What it is, is a reply with no room left to think in. So the next call gets
    the tools taken away and is asked for the answer - the same remedy this
    module already applies at the end of the call budget, for the same reason.
    One spiral then costs one call instead of the stage.
    """
    for message in reversed(messages):
        if getattr(message, "type", None) != "ai":
            continue
        truncated = any(
            isinstance(holder, dict)
            and str(holder.get("finish_reason") or "") == "length"
            for holder in (
                getattr(message, "response_metadata", None),
                getattr(message, "additional_kwargs", None),
            )
        )
        if not truncated:
            return False
        if str(getattr(message, "content", "") or "").strip():
            return False
        return not (getattr(message, "tool_calls", None) or ())
    return False


#: Sent when the previous reply reasoned past its own output budget. Separate
#: from `TOOLS_WITHHELD_NOTICE`, which is about the call budget: this stage has
#: calls left and the last reply simply had nowhere to land.
_REASONED_PAST_THE_BUDGET_NOTICE = (
    "Your previous reply was cut off at its output limit while you were still "
    "reasoning, so nothing of it survived - no text, no tool call. Reasoning "
    "further will hit the same limit again: the limit is per reply, and the one "
    "you just spent was the whole of it.\n"
    "Your tools are withheld for this call. Answer now from what you already "
    "know, briefly, and return your structured response. A short answer that "
    "exists is worth more than a thorough one that is truncated. If you genuinely "
    "cannot answer, say what is missing in `blockers` - that is a complete answer "
    "too."
)


#: Sent on the calls where the tools are withheld. It says what was done rather
#: than asking again, because asking is what the previous 263 calls did.
TOOLS_WITHHELD_NOTICE = (
    "Your tools have been withheld for this call. You are at the end of this "
    "stage's model-call budget with no structured response written, and the "
    "next thing that happens is this conversation being discarded and the "
    "stage started again from nothing. There is no file left to read and no "
    "command left to run: return your structured response now, from what you "
    "already know. An answer that is complete but imperfect is worth far more "
    "than none."
)


#: Where the withholding is remembered for this stage, so a tool that would
#: otherwise recommend `read_file` can know it is gone. See
#: `app.tools.agent_toolkit._and_a_path_is_read_with_read_file`.
READ_TOOL_WITHHELD = "read tool withheld"


def _remember_the_read_tool_is_withheld() -> None:
    try:
        from app.agents.stage_memory import store

        store(READ_TOOL_WITHHELD, {})["withheld"] = True
    except Exception:  # noqa: BLE001 - a memo must never fail a model call
        pass


def the_read_tool_is_withheld() -> bool:
    """Whether this stage has had its read tool withheld."""
    try:
        from app.agents.stage_memory import store

        return bool(store(READ_TOOL_WITHHELD, {}).get("withheld"))
    except Exception:  # noqa: BLE001
        return False


def _refused_reads(messages: list[Any]) -> int:
    """How many redundant reads this stage has been refused.

    Counted from the conversation rather than from shared state, so the two
    modules need agree on nothing but the marker the backend writes.

    The ordinal the refusal quotes - "it is the 34th time this stage has asked
    for content it already has" - is deliberately NOT used, though it looks like
    exactly the tally this wants. It does not count the stage. Measured on
    one run: `specialist_testing_5` made 11 read calls in total and was told
    it was on its 34th, `specialist_ui_ux_1` made 14 and was told 29, and
    `specialist_ui_ux_0` was refused once and told 33.

    The cause is `workspace_backend._the_repeated_read_tally`, which keeps the
    count in `stage_memory.store("repeated_reads", own)`. `store` returns the
    per-instance fallback whenever `current_stage_key()` cannot resolve a thread,
    and that instance outlives the stage - so the number is the run's, not the
    stage's, and the sentence carrying it is wrong about whose it is.

    Trusting it would withhold a stage's read tool on its first refusal, once any
    earlier stage in the run had pushed the shared count past three. Until that
    tally is really per stage, counting the refusals in front of us understates
    a stage that paused and resumed, and understating is the safe direction.
    """
    from app.agents.workspace_backend import READ_REFUSED_MARKER

    refused = 0
    for message in messages:
        if getattr(message, "type", None) != "tool":
            continue
        if READ_REFUSED_MARKER in str(getattr(message, "content", "") or ""):
            refused += 1
    return refused


def _a_tool_refused_identically(messages: list[Any]) -> tuple[str, int] | None:
    """The tool this stage keeps calling to the same failure, and how often.

    Telling a stage it is repeating a dead call is not enough on its own. The
    note already says "It will fail this way again. Change the arguments, create
    what is missing, or carry on without it", and measured across two runs a
    stage read that and carried straight on:

      One run  `specialist_backend_0`  15 identical `edit_artifact` calls,
                    every one refused because the file would not parse
      one run  `specialist_backend_3`   7 identical `replace_lines` calls,
                    the same refusal each time

    The first was the largest single class of failed calls in its run. Reads
    already escalate from a note to withholding the tool; a mutation that cannot
    succeed had no such step, so the only thing bounding it was the stage's
    model-call budget.

    Counted by pairing each refusal with the call that earned it, through
    `tool_call_id`, and tallying identical `(name, arguments)`. Nothing here reads
    the wording of a guard, which matters twice over.

    The first version matched one phrase, "failed the same way", which is
    `repeated_queries`' wording. Measured on one run: `specialist_testing_2`
    called `read_command_output` seven times with a workspace path where a journal
    reference belongs. Its guard answered perfectly - "looks like a path rather
    than a journal reference ... read it with `read_file`", then refused outright
    - in its own words, which that phrase does not match, so nothing escalated. A
    loop is a loop whoever describes it.

    The second version read the number a note quotes, and that number counts the
    run rather than the stage: `specialist_ui_ux_0` made one `edit_artifact` call
    on one run and was told it had failed the same way the 3 previous times.
    Believing it would disarm a stage on its first call. `_refused_reads` below
    still carries that trap, deliberately, with the measurement in its docstring.

    Across a stage that pauses for approval and resumes this undercounts, because
    the conversation is shorter than the stage. Undercounting costs a few more
    refused calls; overcounting takes a tool away from a stage that has done
    nothing wrong.
    """
    asked: dict[str, tuple[str, str]] = {}
    failures: dict[tuple[str, str], int] = {}
    for message in messages:
        for call in getattr(message, "tool_calls", None) or ():
            name = str((call or {}).get("name") or "")
            if not name:
                continue
            identity = json.dumps((call or {}).get("args") or {}, sort_keys=True, default=str)
            called = str((call or {}).get("id") or "")
            if called:
                asked[called] = (name, identity)
        if getattr(message, "type", None) != "tool":
            continue
        pair = asked.get(str(getattr(message, "tool_call_id", "") or ""))
        if pair is None:
            continue
        if not _REFUSED.match(str(getattr(message, "content", "") or "")):
            continue
        failures[pair] = failures.get(pair, 0) + 1
    if not failures:
        return None
    (name, _identity), count = max(failures.items(), key=lambda item: item[1])
    if count < IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL:
        return None
    return name, count


def _named(tool: Any) -> str:
    """A tool's name, whether it is an object or a mapping."""
    return str(
        getattr(tool, "name", "")
        or (tool.get("name") if isinstance(tool, dict) else "")
    )


def _without_that_tool_in(tools: list[Any], name: str) -> list[Any] | None:
    """`tools` without the one named, or None if that changes nothing.

    None when it is not there or when removing it would leave nothing, so a list
    already narrowed is not narrowed into something the model cannot act with.
    """
    kept = [tool for tool in tools if _named(tool) != name]
    if len(kept) == len(tools) or not kept:
        return None
    return kept


def _without_the_read_tools_in(tools: list[Any]) -> list[Any] | None:
    """`tools` without the file readers, or None if that changes nothing."""
    kept = [tool for tool in tools if _named(tool) not in _READ_TOOLS]
    if len(kept) == len(tools) or not kept:
        return None
    return kept


def _a_tool_withheld_notice(name: str, refusals: int) -> str:
    """Why that one tool is gone, and what is left to do the work with.

    Only the repeated tool is taken, never the whole set: the same edit usually
    goes through as a whole-file `write_artifact`, and a stage left with no way
    to change a file at all could only give up.
    """
    return (
        f"`{name}` has been withheld for the rest of this stage. You have called "
        f"it {refusals} times with the same arguments and it has been refused "
        "the same way every time, so the next identical call would be refused "
        "too. Nothing about the file has changed in between.\n"
        "Everything else still works. If the change is still needed, reach it "
        "another way - write the whole file with `write_artifact`, or fix "
        "whatever the refusal named first. If it is not needed, or something is "
        "genuinely in the way, say so in `blockers` and return your structured "
        "response."
    )


#: Sent on the call the read tool is taken away, because a tool that vanishes
#: with no explanation is a tool the model will keep trying to call.
_READ_TOOL_WITHHELD_NOTICE = (
    "Your file-reading tool has been withheld for the rest of this stage. You "
    "have been refused several reads that returned nothing you had not already "
    "been given, and on the runs this was measured on, almost every read after "
    "that point was redundant too. `grep` and the directory listings still "
    "work, and so does everything that changes a file or runs a command. Use "
    "what you have: make the change, run the check, or return your structured "
    "response. If something is genuinely missing, say so in `blockers`."
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
                # The tools go last, after whatever correction was already
                # due. A schema failure still needs its validation errors -
                # the model is being asked to answer, and it should know why
                # its last attempt was refused.
                reading_nothing_new = _refused_reads(messages)
                # Checked before the call-budget rung and folded into the same
                # `answer_only` path, because the remedy is identical - no tools,
                # answer now - and a stage can be in both states at once.
                spiralled = _the_last_reply_was_all_reasoning(messages)
                if spiralled:
                    correction = (
                        f"{correction}\n\n{_REASONED_PAST_THE_BUDGET_NOTICE}"
                        if correction
                        else _REASONED_PAST_THE_BUDGET_NOTICE
                    )
                    logger.warning(
                        "Stage %s spent a whole reply's output budget on "
                        "reasoning; withholding its tools for one call so it can "
                        "answer from what it has",
                        stage_name or "?",
                    )
                answer_only = spiralled or _nothing_left_but_the_answer(
                    messages, step_limit, schema
                )
                if answer_only and not spiralled:
                    correction = (
                        f"{correction}\n\n{TOOLS_WITHHELD_NOTICE}"
                        if correction
                        else TOOLS_WITHHELD_NOTICE
                    )
                    logger.warning(
                        "Stage %s is %d calls from its budget with nothing "
                        "written; withholding its tools so the only move left "
                        "is the answer",
                        stage_name or "?",
                        step_limit - _model_calls_used(messages),
                    )
                # The two withholding rungs are independent. `repeated` used to
                # be computed only when nothing else had produced a correction,
                # and the read rung above produces one constantly - 114 times in
                # one run - so it starved this one completely: a stage that
                # loops on `edit_artifact` loops on reads too, and the reads
                # always won. Measured on one run, which held an
                # `edit_artifact` repeated past the threshold and never withheld
                # it once. Both can apply on one call, and the tool list below is
                # narrowed by each in turn.
                repeated = None
                if not correction:
                    if reading_nothing_new >= READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL:
                        correction = _READ_TOOL_WITHHELD_NOTICE
                    repeated = _a_tool_refused_identically(messages)
                    if repeated is not None:
                        notice = _a_tool_withheld_notice(*repeated)
                        correction = f"{correction}\n\n{notice}" if correction else notice
                if not correction:
                    return handler(request)
                overrides: dict[str, Any] = {}
                if answer_only:
                    # Empty here, not empty at the model. `_get_bound_model`
                    # appends the structured-output tools to whatever this
                    # list holds, so the model is left bound to exactly one
                    # tool: the one that ends the stage.
                    overrides["tools"] = []
                    if spiralled:
                        # Without tools the model can still spend the reply
                        # reasoning, and did. See `answering_without_reasoning`.
                        from app.agents.thinking import answering_without_reasoning

                        quiet = answering_without_reasoning(getattr(request, "model", None))
                        if quiet:
                            overrides["model_settings"] = {
                                **(getattr(request, "model_settings", None) or {}),
                                **quiet,
                            }
                            logger.warning(
                                "Stage %s: thinking switched off for this one call "
                                "so the reply can be the answer",
                                stage_name or "?",
                            )
                else:
                    kept = list(getattr(request, "tools", None) or [])
                    narrowed = False
                    if reading_nothing_new >= READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL:
                        without_reads = _without_the_read_tools_in(kept)
                        if without_reads is not None:
                            kept, narrowed = without_reads, True
                            _remember_the_read_tool_is_withheld()
                            logger.warning(
                                "Stage %s has been refused %d redundant reads; "
                                "withholding the read tool for the rest of it",
                                stage_name or "?", reading_nothing_new,
                            )
                    if repeated is not None:
                        without_it = _without_that_tool_in(kept, repeated[0])
                        if without_it is not None:
                            kept, narrowed = without_it, True
                            logger.warning(
                                "Stage %s has called `%s` %d times to the same "
                                "refusal; withholding that one tool for the rest "
                                "of it",
                                stage_name or "?", repeated[0], repeated[1],
                            )
                    if narrowed:
                        overrides["tools"] = kept
                    elif repeated is not None and not correction.strip():
                        # Nothing was removed, so a notice would describe a tool
                        # the model can still see and call.
                        return handler(request)
                request = request.override(
                    messages=[*messages, {"role": "user", "content": correction}],
                    **overrides,
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
            # The answer need not be in the LAST message. One run's
            # `scrum_master` wrote a valid sprint plan at 15:23:30 and then
            # spent eleven minutes writing prose about creating files it has
            # no tools to create, so by the time it was circling, the last
            # message held no answer and this check was blind to it.
            # Past the budget, with an answer already written: end. The
            # warning has said so from 70% onward, and on one run's
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
                # on one run, where `specialist_testing` was told 71 times
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
            # all. Measured on one run's `specialist_testing_1`: the model
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
    "CALLS_RESERVED_FOR_THE_ANSWER",
    "READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL",
    "BUDGET_STOP_MARKER",
    "MODEL_CALLS_PER_STAGE",
    "MAX_REPORTED_ERRORS",
    "MUTATING_TOOLS",
    "TOOLS_WITHHELD_NOTICE",
    "build_settled_answer_middleware",
    "was_stopped_by_the_budget",
]
