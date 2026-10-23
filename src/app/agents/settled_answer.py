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


#: Set beside `BUDGET_STOP_MARKER` on the message a no-progress stop leaves
#: behind: the stage ended because its conversation shows it circling the same
#: calls, not because it ran out of budget. Recovery treats the two alike - no
#: nudge, straight to the fresh conversation - and the marker tells the log and
#: the routing of a defect stage which of the two happened.
NO_PROGRESS_MARKER = "settled_answer_no_progress_stop"

#: How many identical calls that returned nothing new end a stage. Every
#: softer rung has fired by then: the second repeat gets a note, the read
#: refusal escalates to withholding, a withheld tool called again takes the
#: exploring tools away - and measured on one run the repeated-read tally
#: still climbed, 9 to 16, while the withholding did its work, and a sprint
#: planner's `changed_since_sprint` went from 3 to 27 calls in an evening.
#: Budget-exhaustion warnings ran 47 in a day, concentrated in the defect-fix
#: stages: the soft landing still costs most of the stage's calls. Twelve
#: matches the top of the existing rung ladder; the stop is the rung after it.
SAME_CALLS_BEFORE_ENDING_THE_STAGE = 12


def was_stopped_for_no_progress(result: Any) -> bool:
    """Did `settled_answer` end this thread for circling identical calls?"""
    if not isinstance(result, dict):
        return False
    for message in reversed(result.get("messages") or []):
        kwargs = getattr(message, "additional_kwargs", None)
        if isinstance(kwargs, dict) and kwargs.get(NO_PROGRESS_MARKER):
            return True
        if getattr(message, "type", None) == "ai":
            break
    return False


def _identical_calls_so_far(messages: list[Any]) -> int:
    """The largest count of one identical, nothing-new call this conversation shows.

    Counted from the conversation rather than the shared stage tally, for the
    reason `_refused_reads` gives: the shared `repeated_reads` counter was
    measured counting the run, not the stage. Three guards write the markers
    counted here - the read refusal, the same-answer note on a listing or
    search, and the identical-failure pairing - so a loop ends whichever
    guard is describing it. Across a pause and resume this undercounts; the
    safe direction, as everywhere in this ladder.
    """
    from app.agents.repeated_queries import SAME_ANSWER_MARKER

    same_answers = 0
    for message in messages:
        if getattr(message, "type", None) != "tool":
            continue
        if SAME_ANSWER_MARKER in str(getattr(message, "content", "") or ""):
            same_answers += 1
    identically = _a_tool_refused_identically(messages)
    return max(_refused_reads(messages), same_answers, identically[1] if identically else 0)


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



def validated_leniently(schema: Any, payload: Any) -> Any:
    """`payload` as the schema's instance; on a miss, once more with its shapes repaired; raises as validation does.

    An answer written as text never went through the repair a tool call's
    arguments get (`tool_arguments.with_structure_decoded`): prose where a list
    is wanted, a list where a line is, a field the schema has no place for. One
    run's sprint planner wrote a plan with exactly those misses six times, was
    told each time which fields were wrong, and the run failed with the plan
    written every time.
    """
    try:
        return schema.model_validate(payload)
    except Exception:
        from app.models.tool_arguments import with_structure_decoded

        # Only an answer to this schema is repaired: most of its top-level keys
        # are the schema's own. Any other object - a `package.json` written as a
        # file - would lose every key it has and pass as an empty answer.
        fields = set(getattr(schema, "model_fields", {}) or {})
        keys = set(payload) if isinstance(payload, dict) else set()
        if not keys or len(keys & fields) * 2 < len(keys):
            raise
        repaired = with_structure_decoded(payload, schema.model_json_schema())
        if repaired == payload:
            raise
        return schema.model_validate(repaired)

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
        return validated_leniently(schema, unwrapped(_without_repeats(payload), schema))
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

#: Reads of a file the project memory already holds, answered with a pointer to
#: it, before the read tool goes too. The pointer is the same answer as a
#: refusal in kinder words and was not counted: measured on one run, a testing
#: stage made 70 model calls of which 64 tool results were pointers - a batch of
#: reads, a stall that withheld them for one call, one write, and the batch
#: again, around 35 calls of it. Higher than the refusal count because the memory
#: holds only whole files, and a stage may still need a file it does not.
POINTED_READS_BEFORE_WITHHOLDING_THE_TOOL = 8

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

#: How many times a query may be answered with the note that nothing changed
#: before the tool is withheld. The note first appears on the third identical
#: call, so this is the sixth.
IDENTICAL_ANSWERS_BEFORE_WITHHOLDING_THE_TOOL = 4

#: A tool result that is a refusal rather than an answer. Every guard in this
#: harness opens one of these ways, and the bracketed group is the repeat note
#: some of them prepend - an anchored match without it stopped counting a call
#: exactly when it started repeating, which is how the audit script came to
#: report 15 failures on a run that had 29.
#: An edit's result saying the change is already in the file.
_ALREADY_APPLIED = re.compile(r'"status":\s*"already_applied"')

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
    # And the calls a compaction summarised away, carried on its summary:
    # measured on one gate run, a fix stage made 41 calls against a budget of
    # 40 and went on - the count had restarted from the summary.
    from app.agents.compaction import CALLS_BEFORE

    before = max(
        (int((getattr(message, "additional_kwargs", None) or {}).get(CALLS_BEFORE) or 0) for message in messages),
        default=0,
    )
    return before + sum(1 for message in messages if getattr(message, "type", None) == "ai")


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


#: Tool results in a row that gave the stage nothing new before its tools are
#: withheld and the answer is the only move left.
NOTHING_NEW_BEFORE_THE_ANSWER = 5

#: Pointer answers in a row - reads of files the project memory already holds -
#: before the stall fires. The files are in the conversation, so the second such
#: read is the stall the five-result rule waited three more full prefills and
#: replies to see; one run's stages were answered with 774 pointers (Initiative BC).
POINTERS_BEFORE_THE_ANSWER = 2

#: How a tool result says it gave nothing new: a repeat refused or answered
#: with a pointer, the same bytes or listing again.
_NOTHING_NEW = re.compile(
    r"returned exactly what it returned|the same bytes|Refusing to read .{0,200}? again|"
    r"You have already read|nothing you did not already have|nothing you have not already been given|"
    r"is in the project memory at the start of this conversation|has had its share of|"
    r"There is nothing to compare against|"
    # A write refused for changing nothing: measured on one gate run, an
    # acceptance author wrote the same files again and again, each refused
    # with this, and none counted - it ran on toward its whole budget.
    r"already contain(?:s|ed) exactly this content|"
    r"is withheld at this point of the stage and was not run|"
    r"is not a valid tool",
    re.S,
)



#: Told to a stage that writes when its reads stopped teaching it anything:
#: the looking tools go, the writing tools stay.
_STALLED_WITH_WRITERS_NOTICE = (
    "Your last calls only showed you what you already have - the files are in the project memory "
    "at the start of this conversation. Reading is done for this stage: the tools that look are "
    "withheld, and the ones that change files are still yours. Make the change now, then return "
    "your structured response saying what you changed."
)


def _pointed_lately(messages: list[Any]) -> bool:
    """True when the stage's last `POINTERS_BEFORE_THE_ANSWER` tool results were all pointers to the memory."""
    from app.agents.project_memory import HELD_POINTER

    seen = 0
    for message in reversed(messages):
        if getattr(message, "type", None) != "tool":
            continue
        if HELD_POINTER not in str(getattr(message, "content", "") or ""):
            return False
        seen += 1
        if seen >= POINTERS_BEFORE_THE_ANSWER:
            return True
    return False


def _nothing_new_lately(messages: list[Any], count: int = NOTHING_NEW_BEFORE_THE_ANSWER) -> bool:
    """True when the stage's last `count` tool results all gave it nothing new.

    One run's architect on a local model began twenty replies with "I have
    everything I need; I'll write the specification now" and each time called
    `glob` or `ls` for a file it had already read, for 20 minutes. Each result
    said so; the read and listing tools were withheld one by one and it found
    another. With nothing new coming back, the answer is the only move left.
    """
    # Distinct calls, not tool names: one tool asked about one thing after
    # another, each answered with nothing new, is as stuck as several tools.
    called = {
        str(call.get("id") or ""): (
            str(call.get("name") or ""), json.dumps(call.get("args") or {}, sort_keys=True, default=str)
        )
        for message in messages if getattr(message, "type", None) == "ai"
        for call in getattr(message, "tool_calls", None) or []
    }
    seen = 0
    tools: set[tuple[str, str]] = set()
    for message in reversed(messages):
        if getattr(message, "type", None) != "tool":
            continue
        if not _NOTHING_NEW.search(str(getattr(message, "content", "") or "")):
            return False
        seen += 1
        tools.add(called.get(str(getattr(message, "tool_call_id", "") or ""), (str(getattr(message, "name", "") or ""), "")))
        if seen >= count:
            # One call repeating is the repeat rung's: it withholds that tool
            # and leaves the rest. Several, and withholding one did not help.
            return len(tools - {("", "")}) >= 2
    return False


#: Times a fix stage is told its defect's own tests pass before only its
#: answer is left to it (plan AY step 3).
FIXED_NOTICES_BEFORE_THE_ANSWER = 2


def _told_its_defect_is_fixed(messages: list[Any]) -> bool:
    """Whether the harness has measured this stage's defect fixed after its writes at least twice, the last time too.

    The measurement after each write (`app.graph.verify_after_write`) tells a
    fixer its defect's tests pass and to answer, and a model can carry on
    regardless. Measured on an all-on run: a fixer whose unit-test defect was
    fixed was told so seven times and went on diagnosing another defect's
    500s with one throwaway script after another, its own budget running out
    on work another fixer is given. Counted from the conversation, so it
    survives a pause and a rebuilt agent; the last measurement must still be
    a pass, so a later write that broke the tests again keeps its tools.
    """
    from app.graph.verify_after_write import FAILING, PASSED

    passed, last = 0, None
    for message in messages:
        if getattr(message, "type", None) != "tool":
            continue
        said = str(getattr(message, "content", "") or "")
        if PASSED in said:
            passed, last = passed + 1, True
        elif FAILING in said:
            last = False
    return passed >= FIXED_NOTICES_BEFORE_THE_ANSWER and last is True


#: Sent with the tools withheld once `_told_its_defect_is_fixed`.
_FIXED_ANSWER_NOW_NOTICE = (
    "The harness has measured your defect's own tests passing after your changes, and has told you so "
    "more than once. Your tools are withheld: return your structured answer now, saying what you changed. "
    "Other failing tests are other defects, each with its own fixer."
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


def _is_lost_reasoning_message(message: Any) -> bool:
    if getattr(message, "type", None) != "ai":
        return False
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
    if getattr(message, "invalid_tool_calls", None):
        return False
    return not (getattr(message, "tool_calls", None) or ())


def _consecutive_lost_reasoning_replies(messages: list[Any]) -> int:
    """How many trailing AI messages in a row were truncated with nothing surviving."""
    count = 0
    for message in reversed(messages):
        if getattr(message, "type", None) != "ai":
            break
        if not _is_lost_reasoning_message(message):
            break
        count += 1
    return count


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
        return _is_lost_reasoning_message(message)
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


#: Sent instead when thinking can be switched off for the next call and this is
#: the stage's first lost reply. The tools stay: a stage whose work is writing
#: files cannot do it by answering. Measured on one run: QA reasoned through its
#: whole 25,000-token reply before writing a test, the tools were withheld, and
#: the only answer left to it was an empty suite marking two criteria "not
#: automatable" - one of them adding a task - which cost the stage a second
#: visit. Switching thinking off is what stops the spiral; the tools were the
#: remedy from before it could be switched off.
_REASONED_PAST_THE_BUDGET_THINKING_OFF_NOTICE = (
    "Your previous reply was cut off at its output limit while you were still "
    "reasoning, so nothing of it survived - no text, no tool call. Thinking is "
    "switched off for this reply, so it goes straight to action: take your next "
    "step now - the tool call your work needs next, or your structured response "
    "if the work is done. Do not plan all of it again; do the next part of it. "
    "Thinking is back on the reply after: keep it short and about that one step."
)

#: Sent on a second lost reply in one visit: thinking stays off from here on.
_REASONED_PAST_THE_BUDGET_AGAIN_NOTICE = (
    "Your previous reply was cut off at its output limit while you were still "
    "reasoning, for the second time in this stage, so nothing of it survived. "
    "Thinking is switched off for the rest of this stage, so each reply goes "
    "straight to action: take your next step now - the tool call your work needs "
    "next, or your structured response if the work is done. Do not plan all of it "
    "again; do the next part of it."
)


def _replies_that_were_all_reasoning(messages: list[Any]) -> int:
    """How many replies in this visit spent their whole output budget on reasoning.

    With those a compaction summarised away, carried on its summary: measured
    on one gate run, a stage lost a reply, was compacted, lost another, and was
    treated as losing its first - thinking came back on for the reply after.
    """
    from app.agents.compaction import LOST_BEFORE

    count = max(
        (int((getattr(message, "additional_kwargs", None) or {}).get(LOST_BEFORE) or 0) for message in messages),
        default=0,
    )
    for message in messages:
        if getattr(message, "type", None) != "ai":
            continue
        truncated = any(
            isinstance(holder, dict) and str(holder.get("finish_reason") or "") == "length"
            for holder in (
                getattr(message, "response_metadata", None),
                getattr(message, "additional_kwargs", None),
            )
        )
        if (
            truncated
            and not str(getattr(message, "content", "") or "").strip()
            and not (getattr(message, "tool_calls", None) or ())
            and not (getattr(message, "invalid_tool_calls", None) or ())
        ):
            count += 1
    return count


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
    from app.agents.workspace_backend import READ_REFUSED_MARKER, READ_WITHHELD_MARKER

    # A read whose content is held back as a repeat counts too. Measured live:
    # a fixer read one file fourteen times with the same arguments, the last
    # eleven held back, none of them a refusal by these words - so the read
    # tool stayed, and the stage spent its budget on it.
    refused = 0
    for message in messages:
        if getattr(message, "type", None) != "tool":
            continue
        said = str(getattr(message, "content", "") or "")
        if READ_REFUSED_MARKER in said or READ_WITHHELD_MARKER in said:
            refused += 1
    return refused


def _pointed_reads(messages: list[Any]) -> int:
    """How many reads this stage was answered with a pointer to the project memory."""
    from app.agents.project_memory import HELD_POINTER

    return sum(
        1 for message in messages
        if getattr(message, "type", None) == "tool" and HELD_POINTER in str(getattr(message, "content", "") or "")
    )


#: How much of a refusal's opening is its kind, once what it quotes and counts are taken out.
_KIND_CHARACTERS = 80
_QUOTED = re.compile(r"'[^']*'|`[^`]*`")


#: The tools a refusal of the same kind does not make a loop of (see `_a_tool_refused_identically`).
_WRITES_A_FILE = frozenset({"write_artifact", "edit_artifact", "replace_lines", "replace_approved_lines",
                            "delete_artifact", "move_artifact"})


def _the_kind_of(refusal: str) -> str:
    """A refusal's opening with what it quotes and every number taken out: what kind of refusal it is."""
    text = refusal
    try:
        found = json.loads(refusal[refusal.index("{"):]) if "{" in refusal else None
        if isinstance(found, dict) and isinstance(found.get("error"), str):
            text = found["error"]
    except ValueError:
        pass
    plain = _QUOTED.sub("X", text)
    plain = re.sub(r"\d+", "N", plain)
    return " ".join(plain.split())[:_KIND_CHARACTERS]


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
        content = str(getattr(message, "content", "") or "")
        if not _REFUSED.match(content):
            continue
        key = (pair[0], "invalid_tool") if "is not a valid tool" in content else pair
        failures[key] = failures.get(key, 0) + 1
        # And by the kind of refusal: a stage that changes its call a little
        # each time - a different shell line, refused the same way - was never
        # the same call twice. Measured on one run: a fixer sent ten shell
        # lines in a minute, each refused as a whole command line in one
        # string, and nothing escalated. The kind is the refusal's opening
        # with whatever it quotes and counts taken out, so no guard's wording
        # is matched.
        # Not for a tool that writes: a stage editing a file that does not yet
        # parse is refused the same way edit after edit while it fixes it.
        if pair[0] not in _WRITES_A_FILE:
            kind = (pair[0], "kind:" + _the_kind_of(content))
            failures[kind] = failures.get(kind, 0) + 1
    if not failures:
        return None
    (name, _identity), count = max(failures.items(), key=lambda item: item[1])

    if count < IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL:
        return None
    return name, count


def _a_query_answered_identically(messages: list[Any]) -> tuple[str, int] | None:
    """The query tool this stage keeps asking the same thing, and how often.

    The refusal rung above counts calls that fail. A query that succeeds and
    changes nothing had no rung at all: `repeated_queries` notes it, and the
    note is all. One run's technical lead called `ls {"path": "./"}` about
    twenty times in three minutes, every one answered with the same listing
    and, from the third, "[This `ls` returned exactly what it returned the N
    previous times ...]". None of them was a failed call, so nothing escalated.

    Counted like the refusals - each result paired with its call through
    `tool_call_id`, identical `(name, arguments)` tallied - on the marker
    `repeated_queries` writes, not on this module's reading of the listing.

    An edit answered `already_applied` is the same loop: it changes nothing and
    says so. One run's backend specialist wrote its module, then sent the one
    edit already in it eight times running, each answered "This edit is
    already in ...", until its call budget was gone and its tools were taken -
    with nothing above to stop it, because none of those calls failed.
    """
    from app.agents.repeated_queries import SAME_ANSWER_MARKER

    asked: dict[str, tuple[str, str]] = {}
    repeats: dict[tuple[str, str], int] = {}
    for message in messages:
        for call in getattr(message, "tool_calls", None) or ():
            name = str((call or {}).get("name") or "")
            called = str((call or {}).get("id") or "")
            if name and called:
                asked[called] = (
                    name, json.dumps((call or {}).get("args") or {}, sort_keys=True, default=str)
                )
        if getattr(message, "type", None) != "tool":
            continue
        pair = asked.get(str(getattr(message, "tool_call_id", "") or ""))
        content = str(getattr(message, "content", "") or "")
        if pair is None or not (SAME_ANSWER_MARKER in content or _ALREADY_APPLIED.search(content)):
            continue
        repeats[pair] = repeats.get(pair, 0) + 1
    if not repeats:
        return None
    (name, _identity), count = max(repeats.items(), key=lambda item: item[1])
    if count < IDENTICAL_ANSWERS_BEFORE_WITHHOLDING_THE_TOOL:
        return None
    return name, count


#: Identical failing test runs, with edits between them, before the stage is told
#: its edits are not moving the result, and before it is left only its answer.
SAME_FAILURE_BEFORE_SAYING_SO = 3
SAME_FAILURE_BEFORE_THE_ANSWER = 5
_A_TEST_COMMAND = re.compile(r"test|spec|pytest|jest|vitest|playwright|mocha", re.I)
_A_FAILURE_LINE = re.compile(r"fail|✖|not ok|error|assert", re.I)
_TIMINGS = re.compile(r"\d+(?:\.\d+)?\s*(?:ms|s|m)\b|\(\d+(?:\.\d+)?ms\)")


def _failure_signature(argv: Any, content: str) -> str | None:
    """A failing test run reduced to what failed, timings aside; None if it is not a failing test run."""
    command = " ".join(str(part) for part in argv) if isinstance(argv, list) else str(argv or "")
    if not _A_TEST_COMMAND.search(command):
        return None
    try:
        result = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(result, dict) or str(result.get("returncode", "0")) in ("0", "None", ""):
        return None
    output = f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}"
    lines = sorted({_TIMINGS.sub("", line).strip() for line in output.splitlines() if _A_FAILURE_LINE.search(line)})
    return f"{command}|{result.get('returncode')}|" + "\n".join(lines[:40])


def _the_same_failure_running(messages: list[Any]) -> tuple[str, int] | None:
    """The test command whose last runs failed identically with edits between them, and how many runs.

    The stuck-loop shape a step count misses: a stage edits, runs the tests,
    gets the same failure, and edits again - every call new, every result new
    to a repeat check, and nothing moving. The measure that should move is the
    failure itself.
    """
    from app.agents.repeated_queries import MUTATING_TOOLS

    asked: dict[str, tuple[str, Any]] = {}
    runs: list[tuple[str, str, bool]] = []
    edited = False
    for message in messages:
        for call in getattr(message, "tool_calls", None) or ():
            asked[str(call.get("id") or "")] = (str(call.get("name") or ""), (call.get("args") or {}).get("command"))
        if getattr(message, "type", None) != "tool":
            continue
        name, argv = asked.get(str(getattr(message, "tool_call_id", "") or ""), ("", None))
        if name in MUTATING_TOOLS or name in ("write_file", "edit_file", "replace_lines"):
            edited = True
            continue
        if argv is None:
            continue
        signature = _failure_signature(argv, str(getattr(message, "content", "") or ""))
        if signature is None:
            continue
        command = " ".join(str(part) for part in argv) if isinstance(argv, list) else str(argv)
        runs.append((command, signature, edited))
        edited = False
    if not runs:
        return None
    command, last, _ = runs[-1]
    count = 1
    for _command, signature, edited_before in reversed(runs[:-1]):
        if signature != last:
            break
        count += 1
    # Edits between them: the same failure run twice in a row with nothing
    # changed is the repeat rung's, not this one's.
    if count < 2 or not any(edited_before for _c, _s, edited_before in runs[-count + 1:]):
        return None
    return command, count


def _the_same_failure_notice(command: str, count: int) -> str:
    return (
        f"Your last {count} runs of `{command}` failed in exactly the same way, and the edits between them "
        "did not change the result. Stop editing on the same idea: read the first failure in full, decide "
        "what it says is actually wrong, and change your approach. If it cannot be fixed from here, return "
        "your structured response saying what still fails and why."
    )


#: Calls of a withheld tool after which the stage is left only its answer.
#: Withholding a tool takes it off the list the model is offered; a weak model
#: calls it anyway, and the call still runs. Measured on one run: a planning
#: stage on a 1-bit build model sent one identical `changed_since_sprint` 27
#: times, 23 of them after the tool was withheld, each answered the same.
WITHHELD_CALLS_BEFORE_THE_ANSWER = 2


def _a_withheld_tool_still_called(messages: list[Any]) -> bool:
    """Whether a tool withheld for repeating itself has been called again since, more than once."""
    for repeated, threshold in (
        (_a_tool_refused_identically(messages), IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL),
        (_a_query_answered_identically(messages), IDENTICAL_ANSWERS_BEFORE_WITHHOLDING_THE_TOOL),
    ):
        if repeated is not None and repeated[1] >= threshold + WITHHELD_CALLS_BEFORE_THE_ANSWER:
            return True
    return False


#: With thinking off, the same call this many times running is a loop. The
#: rungs above were measured on stages that think, and wait for a refusal or a
#: "nothing changed" note to repeat: a stage that lost a reply to reasoning and
#: carries on without it reads those notes and sends the call again. Measured
#: on one run: 35% of the tool calls made without thinking repeated the call
#: before them exactly, against 3% with thinking on; one fix stage sent one
#: refused edit 6 times and one refused `replace_lines` 13 times, and two
#: stages read one file 14 times, every repeat after its reply was lost.
SAME_CALL_RUNNING_WITHOUT_THINKING = 3


#: The same structured answer refused this many times running ends the visit.
#: The schema's refusal says what is missing; a stage that sends the identical
#: object back after reading it three times will not read it a fourth.
SAME_REFUSED_ANSWERS_BEFORE_ENDING = 3


def _the_same_refused_answer_running(messages: list[Any], schema: Any) -> int:
    """How many replies running ended with the identical structured answer refused by its schema.

    0 unless the conversation ends with such a refusal. A refused answer
    leaves the schema's error as a tool message after the reply, so the last
    message is not the reply.
    """
    name = str(getattr(schema, "__name__", "") or "")
    if not name or not messages:
        return 0
    results = {
        str(getattr(m, "tool_call_id", "") or ""): str(getattr(m, "content", "") or "")
        for m in messages if getattr(m, "type", None) == "tool"
    }
    last = messages[-1]
    if getattr(last, "type", None) != "tool" or not str(getattr(last, "content", "") or "").lstrip().startswith("Error"):
        return 0
    running, previous = 0, None
    for message in reversed(messages):
        if getattr(message, "type", None) != "ai":
            continue
        calls = list(getattr(message, "tool_calls", None) or [])
        if len(calls) != 1 or (calls[0] or {}).get("name") != name:
            break
        if not results.get(str((calls[0] or {}).get("id") or ""), "").lstrip().startswith("Error"):
            break
        signature = json.dumps((calls[0] or {}).get("args") or {}, sort_keys=True, default=str)
        if previous is not None and signature != previous:
            break
        previous = signature
        running += 1
    return running


#: Replies lost to reasoning in one visit after which thinking stays off for
#: the rest of it. After the first, only the next reply goes without thinking -
#: the one that lands the next step - and thinking is back on the reply after.
#: Measured on two runs: with thinking kept off for the rest of a visit after
#: one loss, and for the rest of the run after losses on two visits, 52% and
#: 29% of replies went without it, and 35% and 22% of the calls they made
#: repeated the call before exactly, against 3% and 0.4% with thinking on.
LOST_REPLIES_BEFORE_THINKING_STAYS_OFF = 2


def _thinking_is_off_here(messages: list[Any], stage_name: str = "", lost_before: int = 0) -> bool:
    """Whether this call goes without thinking: the reply right after one lost
    to reasoning, or any reply once a visit has lost
    `LOST_REPLIES_BEFORE_THINKING_STAYS_OFF`.

    `lost_before` is the visit's own count, kept by the middleware: counted
    from the history alone, compaction took the lost replies out of it and
    the count never reached two. Measured on one run: a lead lost five
    20,000-token replies to reasoning in 23 minutes of one visit, thinking
    coming back on after each.
    """
    return _the_last_reply_was_all_reasoning(messages) or (
        max(lost_before, _replies_that_were_all_reasoning(messages)) >= LOST_REPLIES_BEFORE_THINKING_STAYS_OFF
    )


def _the_same_call_running(messages: list[Any]) -> tuple[str, int] | None:
    """The tool of the last call and how many calls running had exactly its arguments, or None below the threshold."""
    calls: list[tuple[str, str]] = []
    for message in messages:
        for call in getattr(message, "tool_calls", None) or ():
            name = str((call or {}).get("name") or "")
            if name:
                calls.append((name, json.dumps((call or {}).get("args") or {}, sort_keys=True, default=str)))
    if not calls:
        return None
    running = 0
    for call in reversed(calls):
        if call != calls[-1]:
            break
        running += 1
    if running < SAME_CALL_RUNNING_WITHOUT_THINKING:
        return None
    return calls[-1][0], running


#: The same call answered the same this many times running is a loop, with
#: thinking on or off. Measured on one run: a builder sent one install command
#: twelve times in a row, about every eight seconds, each answered "Requirement
#: already satisfied" - a command, so no query rung counted it, and thinking was
#: on, so the rung above did not either.
SAME_CALL_SAME_ANSWER_RUNNING = 4


def _the_same_call_answered_the_same(messages: list[Any]) -> tuple[str, int] | None:
    """The tool of the last call and how many calls running had its arguments and its answer, or None below the threshold.

    Timings aside: a command that reports how long it took answers the same
    with a different number.
    """
    answers = {
        str(getattr(m, "tool_call_id", "") or ""): _TIMINGS.sub("", str(getattr(m, "content", "") or ""))
        for m in messages if getattr(m, "type", None) == "tool"
    }
    calls: list[tuple[str, str, str]] = []
    for message in messages:
        for call in getattr(message, "tool_calls", None) or ():
            name = str((call or {}).get("name") or "")
            called = str((call or {}).get("id") or "")
            if name and called in answers:
                calls.append((name, json.dumps((call or {}).get("args") or {}, sort_keys=True, default=str), answers[called]))
    if not calls:
        return None
    running = 0
    for call in reversed(calls):
        if call != calls[-1]:
            break
        running += 1
    if running < SAME_CALL_SAME_ANSWER_RUNNING:
        return None
    return calls[-1][0], running


def stable_tools_notice(withheld: set[str]) -> str:
    """What a call is told when its tools stay listed but some are refused (plan PX.2)."""
    names = ", ".join(f"`{name}`" for name in sorted(withheld)[:12])
    return (f"\n\nStill listed, but refused if called on this call: {names}. A call to one returns "
            "a refusal and is not run.")


def _the_same_call_running_notice(name: str, times: int) -> str:
    """Why a tool is gone for this call: the stage sent it the same arguments again and again."""
    return (
        f"`{name}` is withheld for this call. You have sent it the same arguments {times} "
        "times in a row, and the same call returns the same thing: what it returned is "
        "already in this conversation above. Take the next step instead - change "
        "something, run a different check, or return your structured response."
    )


def _a_query_withheld_notice(name: str, repeats: int) -> str:
    """Why a query tool is gone: it kept answering the same question the same way."""
    return (
        f"`{name}` has been withheld for the rest of this stage. You have asked it "
        f"the same thing {repeats + 2} times or more and it has answered identically "
        "every time, because nothing it reports on has changed. The answer is "
        "already in this conversation above.\n"
        "Everything else still works. Act on what you have: make the change, run "
        "the check, or return your structured response."
    )


def _named(tool: Any) -> str:
    """A tool's name, whether it is an object, a mapping or the name itself."""
    if isinstance(tool, str):
        return tool
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


#: Model calls a fix stage may make before it has changed a file, after which its tools that only
#: look are withheld and it must write. Measured live: one fix stage made 123 model calls and one edit
#: over 47 minutes, saying "I have all the information I need" before each further read; another made 118
#: tool calls and none. The attempt is measured and reverted if it is wrong, so a best attempt costs
#: less than a seventh reading of the same files.
CALLS_BEFORE_A_FIX_MUST_WRITE = 12

#: The tools whose success is a change to a file.
_THE_WRITING_TOOLS = frozenset({"write_artifact", "edit_artifact", "replace_lines", "delete_artifact", "move_artifact"})

_WRITE_NOW_NOTICE = (
    "You have made {calls} calls and changed nothing. Reading is done for this stage: the tools that look are "
    "withheld, and the ones that change files are still yours. Change the files now, from what you have read - "
    "your change is measured after you return, and a wrong attempt is undone. Then return your structured "
    "response saying what you changed."
)


def _the_graph_stage(role_name: str = "") -> str:
    """The graph stage making this call (`defect_fix_2_14`), not the role the agent was built with."""
    try:
        from app.observability.transcript import _stage_from_config

        return str(_stage_from_config(role_name or "") or "")
    except Exception:  # noqa: BLE001
        return str(role_name or "")


def _model_calls_without_a_write(messages: list[Any]) -> int:
    """How many model calls the conversation has made since a file last changed (or since it began)."""
    names: dict[str, str] = {}
    calls = 0
    for message in messages:
        kind = getattr(message, "type", None)
        if kind == "ai":
            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                calls += 1
            for call in tool_calls:
                names[str(call.get("id") if isinstance(call, dict) else getattr(call, "id", ""))] = str(
                    call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
                )
        elif kind == "tool":
            name = names.get(str(getattr(message, "tool_call_id", "") or ""), "")
            body = str(getattr(message, "content", "") or "").lstrip()
            if name in _THE_WRITING_TOOLS and not body.startswith(("Error", '{"error"', "Refusing", "Not running")):
                calls = 0
    return calls


def _without_the_looking_tools_in(tools: list[Any]) -> list[Any]:
    """`tools` without any that only read, list, search or look something up."""
    from app.agents.repeated_queries import QUERY_TOOLS

    return [tool for tool in tools if _named(tool) not in QUERY_TOOLS | _READ_TOOLS]


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


#: Replies lost to reasoning, by (run, graph stage), across the stage's visits.
#: A retry or a resume starts a new conversation and a new middleware, and the
#: count started again with thinking back on: one run lost 37 replies of 20,000
#: tokens each, two or more per defect in eleven defects' fix stages - eight in
#: one planning stage across its visits.
_LOST_ACROSS_VISITS: dict[tuple[str, str], int] = {}


def _the_stage_across_visits() -> tuple[str, str] | None:
    """(run, graph stage) of the running call, the same for every visit of a stage; None outside a run."""
    try:
        from app.observability.log_context import _from_the_graph

        run, stage = _from_the_graph()
    except Exception:  # noqa: BLE001
        return None
    if not run or not stage:
        return None
    if len(_LOST_ACROSS_VISITS) > 2000:
        _LOST_ACROSS_VISITS.clear()
    return str(run), str(stage)


def _without_reasoning_after_a_lost_reply(request: Any, stage_name: str, lost_before: int = 0) -> Any:
    """`request` with thinking switched off on the reply after one lost to
    reasoning, and for the rest of a visit that has lost
    `LOST_REPLIES_BEFORE_THINKING_STAYS_OFF`; otherwise `request` unchanged.

    The tools stay: this is the stage's ordinary work, done without the
    reasoning that has just produced nothing. Off for one reply first, not for
    the rest of the visit: a stage asked on without thinking repeated its own
    calls ten times as often as one thinking (see
    `LOST_REPLIES_BEFORE_THINKING_STAYS_OFF`). A second loss in the visit - what
    once failed a run, when thinking came straight back - keeps it off from
    then on, still with the tools.
    """
    try:
        from app.agents.thinking import answering_without_reasoning

        if not _thinking_is_off_here(list(getattr(request, "messages", None) or []), stage_name, lost_before):
            return request
        quiet = answering_without_reasoning(getattr(request, "model", None))
        if not quiet:
            return request
        return request.override(
            model_settings={**(getattr(request, "model_settings", None) or {}), **quiet}
        )
    except Exception:  # noqa: BLE001 - never fail the call over a saving
        return request



#: Characters of a reply cut at its length limit that the next call is shown.
CUT_REPLY_KEPT = 4_000
#: Below this a cut reply is carried as it is: it costs the window little.
CUT_REPLY_CARRIED_WHOLE = 8_000


def _repeats_itself(text: str) -> bool:
    """Whether the end of `text` is one stretch said over and over: its last 8,000 characters compress past 12 to 1."""
    import zlib

    tail = text[-8_000:].encode("utf-8", errors="replace")
    return len(tail) >= 2_000 and len(zlib.compress(tail)) * 12 < len(tail)


def _the_cut_reply_shortened(message: Any) -> Any:
    """`message`, when its reply was cut at the length limit with a long text, cut to its head and a note; else itself."""
    truncated = any(
        isinstance(holder, dict) and str(holder.get("finish_reason") or "") == "length"
        for holder in (getattr(message, "response_metadata", None), getattr(message, "additional_kwargs", None))
    )
    content = getattr(message, "content", "")
    if (getattr(message, "type", None) != "ai" or not truncated or not isinstance(content, str)
            or len(content) <= CUT_REPLY_CARRIED_WHOLE or getattr(message, "tool_calls", None)):
        return message
    why = ("it repeated the same text over and over until the limit stopped it"
           if _repeats_itself(content) else "it ran past the reply's length limit")
    note = (f"\n\n[This reply was cut off: {why}. The {len(content) - CUT_REPLY_KEPT:,} characters after "
            "this point are not shown. Nothing in it was accepted. Write the answer again, once, "
            "complete and short enough to finish.]")
    return message.model_copy(update={"content": content[:CUT_REPLY_KEPT] + note})


def _with_cut_replies_shortened(request: Any) -> Any:
    """`request` with every long reply cut at the length limit shortened; `request` itself when there is none.

    A reply cut at its limit is never an answer, and carried whole it cost the
    next call its window and taught it the loop it was cut in: one stage's
    first reply repeated a three-character string until 107,596 tokens were
    spent, the next call was handed all 205,682 characters of it, and its own
    reply repeated one block 102 times. The empty case - a reply all reasoning
    - is `_the_last_reply_was_all_reasoning`'s.
    """
    try:
        messages = list(getattr(request, "messages", None) or [])
        shortened = [_the_cut_reply_shortened(m) for m in messages]
        if all(a is b for a, b in zip(messages, shortened)):
            return request
        return request.override(messages=shortened)
    except Exception:  # noqa: BLE001 - never fail the call over a saving
        return request

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
            # The same call without the reasoning-effort field, for a server
            # that refuses the request because of it. Set only when thinking is
            # switched off below.
            refused_fallback = None
            # For `_decide`, which runs after this call and sees no model.
            self._model = getattr(request, "model", None)
            # Tools this call withholds, refused if called anyway (`wrap_tool_call`).
            self._set_withheld(set())
            # Each lost reply, counted once by its message, so compaction
            # cannot take the count with the history.
            seen = list(getattr(request, "messages", None) or [])
            visit_stage = _the_stage_across_visits()
            if _the_last_reply_was_all_reasoning(seen):
                last_ai = next((m for m in reversed(seen) if getattr(m, "type", None) == "ai"), None)
                lost_id = str(getattr(last_ai, "id", "") or id(last_ai))
                if lost_id not in getattr(self, "_lost_replies", set()):
                    self._lost_replies = getattr(self, "_lost_replies", set()) | {lost_id}
                    if visit_stage:
                        _LOST_ACROSS_VISITS[visit_stage] = _LOST_ACROSS_VISITS.get(visit_stage, 0) + 1
            lost = max(
                len(getattr(self, "_lost_replies", set())),
                _replies_that_were_all_reasoning(seen),
                _LOST_ACROSS_VISITS.get(visit_stage, 0) if visit_stage else 0,
            )
            request = _without_reasoning_after_a_lost_reply(request, stage_name, lost)
            request = _with_cut_replies_shortened(request)
            # Older refusals as a line each in what the model reads; the
            # guards below still count the conversation as it is stored.
            from app.agents.refusal_folding import with_old_refusals_folded

            counted = request
            request = with_old_refusals_folded(request)
            try:
                # Counted as stored - folded refusals would read as none - and
                # sent as folded (`refusal_folding`).
                messages = getattr(counted, "messages", None)
                sent_messages = getattr(request, "messages", None) or messages
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
                    # Asked again with only its schema allowed, where the
                    # server enforces that (`structured_extraction`); the
                    # reminder below when it cannot be had.
                    from app.agents.structured_extraction import answered_in_its_schema

                    extracted = answered_in_its_schema(request, schema, stage_name)
                    if extracted is not None:
                        return extracted
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
                read_tool_due = (
                    reading_nothing_new >= READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL
                    or _pointed_reads(messages) >= POINTED_READS_BEFORE_WITHHOLDING_THE_TOOL
                )
                # Checked before the call-budget rung and folded into the same
                # `answer_only` path, because the remedy is identical - no tools,
                # answer now - and a stage can be in both states at once.
                spiralled = _the_last_reply_was_all_reasoning(messages)
                # Thinking off with the tools kept, where it can be switched
                # off: for the next reply after a first lost one, and for the
                # rest of the visit after a second (`_without_reasoning_after_a_lost_reply`);
                # the tools withheld where it cannot. See the notices for why.
                spiral_quiet: dict = {}
                spiral_plainer = None
                if spiralled:
                    from app.agents.thinking import answering_without_reasoning

                    spiral_quiet = answering_without_reasoning(getattr(request, "model", None)) or {}
                    for_the_rest = _replies_that_were_all_reasoning(messages) >= LOST_REPLIES_BEFORE_THINKING_STAYS_OFF
                    notice = (
                        (_REASONED_PAST_THE_BUDGET_AGAIN_NOTICE if for_the_rest else _REASONED_PAST_THE_BUDGET_THINKING_OFF_NOTICE)
                        if spiral_quiet
                        else _REASONED_PAST_THE_BUDGET_NOTICE
                    )
                    correction = f"{correction}\n\n{notice}" if correction else notice
                    if spiral_quiet:
                        logger.warning(
                            "Stage %s spent a whole reply's output budget on "
                            "reasoning; thinking switched off %s, tools kept",
                            stage_name or "?",
                            "for the rest of this visit" if for_the_rest else "for the next reply",
                        )
                    else:
                        logger.warning(
                            "Stage %s spent a whole reply's output budget on "
                            "reasoning; withholding its tools for one call so it can "
                            "answer from what it has",
                            stage_name or "?",
                        )
                stalled = schema is not None and (_nothing_new_lately(messages) or _pointed_lately(messages))
                # A fix stage that has read for many calls and changed nothing is
                # made to write - only when it has the tools to (a stage with no
                # writers would be left with only its answer).
                unwritten = (
                    schema is not None and _the_graph_stage(stage_name).startswith("defect_fix_")
                    and bool(_without_the_looking_tools_in(list(getattr(request, "tools", None) or [])))
                    and _model_calls_without_a_write(messages) >= CALLS_BEFORE_A_FIX_MUST_WRITE
                )
                stalled = stalled or unwritten
                ignored = schema is not None and _a_withheld_tool_still_called(messages)
                same_failure = _the_same_failure_running(messages)
                if same_failure is not None and same_failure[1] >= SAME_FAILURE_BEFORE_SAYING_SO:
                    notice = _the_same_failure_notice(*same_failure)
                    correction = f"{correction}\n\n{notice}" if correction else notice
                    logger.warning(
                        "Stage %s: %d runs of `%s` failed the same way with edits between them",
                        stage_name or "?", same_failure[1], same_failure[0],
                    )
                stuck_on_a_failure = (
                    schema is not None and same_failure is not None
                    and same_failure[1] >= SAME_FAILURE_BEFORE_THE_ANSWER
                )
                # Every tool that only looks goes; a stage that also writes
                # keeps its writers, and one that only looks has its answer left.
                # The same for a stall: measured on one run, fix stages that
                # read files the project memory already held were stalled at
                # five such reads with every tool withheld - their writers
                # too - and could only answer, which each did by claiming
                # changes it never made, defect after defect.
                writers = (
                    _without_the_looking_tools_in(list(getattr(request, "tools", None) or []))
                    if ignored or stalled else []
                )
                fixed_already = schema is not None and _told_its_defect_is_fixed(messages)
                if fixed_already:
                    correction = f"{correction}\n\n{_FIXED_ANSWER_NOW_NOTICE}" if correction else _FIXED_ANSWER_NOW_NOTICE
                    logger.warning("Stage %s was told its defect is fixed and carried on; only its answer is left", stage_name or "?")
                answer_only = (spiralled and not spiral_quiet) or _nothing_left_but_the_answer(
                    messages, step_limit, schema
                ) or (stalled and not writers) or (ignored and not writers) or stuck_on_a_failure or fixed_already
                if ignored:
                    # Named as well: the model is told which call it kept
                    # sending, not only that its tools are gone.
                    refused = _a_tool_refused_identically(messages)
                    named = (_a_tool_withheld_notice(*refused) if refused is not None
                             else _a_query_withheld_notice(*_a_query_answered_identically(messages)))
                    if not writers:
                        # With writers kept, the repeat rung below names it.
                        correction = f"{correction}\n\n{named}" if correction else named
                    logger.warning(
                        "Stage %s kept calling a tool after it was withheld; withholding %s",
                        stage_name or "?", "every tool that only looks" if writers else "its tools so the only move left is the answer",
                    )
                if stalled:
                    if writers:
                        notice = (
                            _WRITE_NOW_NOTICE.format(calls=_model_calls_without_a_write(messages))
                            if unwritten else _STALLED_WITH_WRITERS_NOTICE
                        )
                        correction = f"{correction}\n\n{notice}" if correction else notice
                        # Reading is withheld from here: what refuses a write
                        # as unseen shows the file instead (`repository`).
                        _remember_the_read_tool_is_withheld()
                    logger.warning(
                        "Stage %s had nothing new from its last %d tool calls; withholding %s",
                        stage_name or "?", NOTHING_NEW_BEFORE_THE_ANSWER,
                        "every tool that only looks, keeping its writers" if writers
                        else "its tools so the only move left is the answer",
                    )
                if answer_only and not (spiralled and not spiral_quiet):
                    correction = (
                        f"{correction}\n\n{TOOLS_WITHHELD_NOTICE}"
                        if correction
                        else TOOLS_WITHHELD_NOTICE
                    )
                    if not stalled:
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
                #
                # And neither waits for the other corrections. Gated on "no
                # correction yet", both were starved by the call-budget warning,
                # which is due on every call from 70% of the budget on - the
                # stretch where a looping stage is. Measured on one run: a fix
                # stage sent one identical `read_command_output` eight times
                # running under that warning and was never stopped.
                repeated = None
                if not answer_only:
                    notices = []
                    if read_tool_due:
                        notices.append(_READ_TOOL_WITHHELD_NOTICE)
                    repeated = _a_tool_refused_identically(messages)
                    notice = _a_tool_withheld_notice(*repeated) if repeated is not None else ""
                    if repeated is None:
                        repeated = _a_query_answered_identically(messages)
                        notice = _a_query_withheld_notice(*repeated) if repeated is not None else ""
                    if repeated is None:
                        repeated = _the_same_call_answered_the_same(messages)
                        notice = _the_same_call_running_notice(*repeated) if repeated is not None else ""
                    if repeated is None and _thinking_is_off_here(messages, stage_name):
                        repeated = _the_same_call_running(messages)
                        notice = _the_same_call_running_notice(*repeated) if repeated is not None else ""
                    if notice:
                        notices.append(notice)
                    if notices:
                        correction = "\n\n".join([correction, *notices] if correction else notices)
                if not correction:
                    return handler(request)
                overrides: dict[str, Any] = {}
                if spiral_quiet:
                    from app.agents.thinking import without_the_effort_field

                    overrides["model_settings"] = {
                        **(getattr(request, "model_settings", None) or {}),
                        **spiral_quiet,
                    }
                    spiral_plainer = without_the_effort_field(overrides["model_settings"])
                from app.agents import stable_tools

                stable = stable_tools.enabled()
                withheld_here: set[str] | None = None
                if answer_only:
                    # Empty here, not empty at the model. `_get_bound_model`
                    # appends the structured-output tools to whatever this
                    # list holds, so the model is left bound to exactly one
                    # tool: the one that ends the stage. With the list held
                    # stable (plan PX.2) every one of them is refused instead.
                    if stable:
                        withheld_here = {_named(tool) for tool in getattr(request, "tools", None) or []} - {""}
                    else:
                        overrides["tools"] = []
                    if spiralled:
                        # Without tools the model can still spend the reply
                        # reasoning, and did. See `answering_without_reasoning`.
                        from app.agents.thinking import (
                            answering_without_reasoning,
                            without_the_effort_field,
                        )

                        quiet = answering_without_reasoning(getattr(request, "model", None))
                        if quiet:
                            overrides["model_settings"] = {
                                **(getattr(request, "model_settings", None) or {}),
                                **quiet,
                            }
                            plainer = without_the_effort_field(overrides["model_settings"])
                            if plainer is not None:
                                refused_fallback = {**overrides, "model_settings": plainer}
                            logger.warning(
                                "Stage %s: thinking switched off for this one call "
                                "so the reply can be the answer",
                                stage_name or "?",
                            )
                else:
                    kept = list(getattr(request, "tools", None) or [])
                    narrowed = False
                    if read_tool_due:
                        without_reads = _without_the_read_tools_in(kept)
                        if without_reads is not None:
                            kept, narrowed = without_reads, True
                            _remember_the_read_tool_is_withheld()
                            logger.warning(
                                "Stage %s has been refused %d redundant reads and pointed to the "
                                "project memory for %d; withholding the read tool for the rest of it",
                                stage_name or "?", reading_nothing_new, _pointed_reads(messages),
                            )
                    if repeated is not None:
                        without_it = _without_that_tool_in(kept, repeated[0])
                        if without_it is not None:
                            kept, narrowed = without_it, True
                            logger.warning(
                                "Stage %s has called `%s` %d times to the same "
                                "result; withholding that one tool for the rest "
                                "of it",
                                stage_name or "?", repeated[0], repeated[1],
                            )
                    if ignored or (stalled and writers):
                        kept, narrowed = _without_the_looking_tools_in(kept), True
                    if narrowed and stable:
                        withheld_here = ({_named(tool) for tool in getattr(request, "tools", None) or []}
                                         - {_named(tool) for tool in kept} - {""})
                    elif narrowed:
                        overrides["tools"] = kept
                    elif repeated is not None and not correction.strip():
                        # Nothing was removed, so a notice would describe a tool
                        # the model can still see and call.
                        return handler(request)
                if spiral_quiet and spiral_plainer is not None:
                    # Built last, so it carries whatever tool narrowing the
                    # call above settled on.
                    refused_fallback = {**overrides, "model_settings": spiral_plainer}
                if withheld_here:
                    correction += stable_tools_notice(withheld_here)
                corrected = [*sent_messages, {"role": "user", "content": correction}]
                if refused_fallback is not None:
                    refused_fallback = request.override(messages=corrected, **refused_fallback)
                if "tools" in overrides:
                    sent = {_named(tool) for tool in overrides["tools"]}
                    self._set_withheld({_named(tool) for tool in getattr(request, "tools", None) or []} - sent - {""})
                elif withheld_here is not None:
                    self._set_withheld(withheld_here)
                request = request.override(messages=corrected, **overrides)
            except Exception:  # noqa: BLE001 - never fail the call over a hint
                return handler(request)
            if refused_fallback is None:
                return handler(request)
            try:
                return handler(request)
            except Exception as error:
                from app.agents.thinking import the_server_refused_the_request

                if not the_server_refused_the_request(error):
                    raise
                logger.warning(
                    "Stage %s: the model server refused the request with "
                    "`reasoning_effort` in it (%s: %s); asking again with the "
                    "chat-template switch alone",
                    # What the server said, because a 400 is not always about
                    # the field: one arrived five minutes into a generation.
                    stage_name or "?", type(error).__name__, " ".join(str(error).split())[:300],
                )
                return handler(refused_fallback)

        def _set_withheld(self, names: Any) -> None:
            """The tools this call withholds, on the instance and in the stage's memory.

            A call that needs approval pauses the graph, and the node builds the
            agent afresh to resume it, running the paused call with no model call
            first: on the instance alone the new middleware knew of nothing
            withheld, and a withheld write or command ran after its pause.
            """
            from app.agents.stage_memory import store

            self._withheld = set(names)
            store("withheld tools", {})["names"] = sorted(self._withheld)

        def _withheld_now(self) -> set[str]:
            if "_withheld" in self.__dict__:
                return set(self._withheld)
            from app.agents.stage_memory import store

            return set(store("withheld tools", {}).get("names") or ())

        def wrap_tool_call(self, request: Any, handler: Any) -> Any:
            """A call to a tool this call withheld is refused, not run.

            Withholding takes a tool off the list the model is offered; a weak
            model calls it anyway, and the call still ran. Measured on one run:
            a planning stage on a 1-bit model sent one withheld query 23 times,
            each answered as if it had been offered.
            """
            call = getattr(request, "tool_call", None) or {}
            name = str(call.get("name") or "")
            if name and name in self._withheld_now():
                from langchain_core.messages import ToolMessage

                # Opens as a refusal, so the guards that count refused and
                # nothing-new results count it: unopened, a stalled stage's
                # check was reset by each refused call and never escalated.
                return ToolMessage(
                    content=(
                        f"Refusing: `{name}` is withheld at this point of the stage and was not run. Use what this "
                        "conversation already holds, and the tools you were offered on this call."
                    ),
                    tool_call_id=str(call.get("id") or ""),
                    name=name,
                    status="error",
                )
            return handler(request)

        @hook_config(can_jump_to=["end", "model"])
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
                # A structured answer its schema refused: the error follows the
                # reply, so the budget check below never saw it. Measured on one
                # run: a fix stage sent the same empty answer about fifty times
                # after reading the refusal, 51 calls past its budget, until the
                # run's own guard restarted it.
                refused = _the_same_refused_answer_running(messages, schema)
                over = bool(step_limit) and _model_calls_used(messages) >= step_limit
                if refused and (over or refused >= SAME_REFUSED_ANSWERS_BEFORE_ENDING):
                    logger.warning(
                        "Stage %s sent the same refused answer %d time(s) running%s; ending it so "
                        "the run can retry on a fresh conversation",
                        stage_name or "?", refused, " past its model-call budget" if over else "",
                    )
                    return {
                        "messages": [AIMessage(content="", additional_kwargs={BUDGET_STOP_MARKER: True})],
                        "jump_to": "end",
                    }
                return None
            pending = list(getattr(last, "tool_calls", None) or [])
            # The deterministic no-progress stop (Initiative L.5): the
            # conversation shows the stage circling the same calls, every one
            # answered that nothing changed, and no answer was ever written.
            # Notes, refusals and withheld tools have all fired and been
            # ignored; what is left to fire is the budget, and spending it on
            # pointer-answer turns is exactly the waste this removes. Ending
            # here hands the stage to the run's recovery - a fresh
            # conversation, then the routing a failed stage gets - instead of
            # another refusal turn.
            tally = _identical_calls_so_far(messages)
            if tally >= SAME_CALLS_BEFORE_ENDING_THE_STAGE and _most_recent_answer(messages, schema) is None:
                logger.warning(
                    "Stage %s made %d identical calls with nothing new coming back and no "
                    "answer written; ending it so the run can retry on a fresh conversation",
                    stage_name or "?", tally,
                )
                return {
                    "messages": [
                        AIMessage(
                            content=getattr(last, "content", "") or "",
                            id=getattr(last, "id", None),
                            additional_kwargs={BUDGET_STOP_MARKER: True, NO_PROGRESS_MARKER: True},
                        )
                    ],
                    "jump_to": "end",
                }
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

            # A reply lost to reasoning ends nothing: the model is asked again at
            # once, and the call that asks (`wrap_model_call`) switches thinking
            # off - for one reply after a first loss, for the rest of the visit
            # after a second. A lost reply has no tool call, so it used to end
            # the stage, and the graph's one nudge carried the first loss; the
            # second ended it for good with thinking never switched off for the
            # rest of the visit, and the run failed. Measured on one run: the
            # sprint planner lost a reply, did real work with thinking off, lost
            # the next one with thinking back on, and the run failed at 54
            # minutes. Only where thinking can be switched off - elsewhere the
            # reply would be lost again, and the stage ends as before.
            if not pending and _the_last_reply_was_all_reasoning(messages):
                losses = _consecutive_lost_reasoning_replies(messages)
                if losses > 2:
                    logger.warning(
                        "Stage %s lost %d replies in a row to the output limit; ending the jump loop so "
                        "recovery can proceed on a fresh conversation",
                        stage_name or "?",
                        losses,
                    )
                    return {
                        "messages": [
                            AIMessage(
                                content="",
                                id=getattr(last, "id", None),
                                additional_kwargs={BUDGET_STOP_MARKER: True},
                            )
                        ],
                        "jump_to": "end",
                    }
                from app.agents.thinking import answering_without_reasoning

                if answering_without_reasoning(getattr(self, "_model", None)):
                    logger.warning(
                        "Stage %s lost a reply to reasoning (%d in a row); asking again at once with "
                        "thinking off rather than ending the stage",
                        stage_name or "?",
                        losses,
                    )
                    return {"jump_to": "model"}

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
    "NO_PROGRESS_MARKER",
    "SAME_CALLS_BEFORE_ENDING_THE_STAGE",
    "was_stopped_by_the_budget",
    "was_stopped_for_no_progress",
]
