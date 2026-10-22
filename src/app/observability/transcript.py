"""The complete record of what a run said, was told, and did.

The event stream is a UI feed. It clips every message at 2,000 characters, it
carries tool output as the tool produced it rather than as the model received
it, and it has never recorded the prompts at all. Those three gaps cost real
diagnosis time in one session:

- a repeat notice appended after 3,847 characters of file content sat past the
  clip, so every audit of one run read "no note fired" when the notice had
  fired on every call
- notices appended by `wrap_tool_call` reach the model and not the events, so
  findings 86 and 87 were mis-measured until a live agent was driven by hand
- "largest model output" measured from events came back as 2042, 2042, 2042 -
  the clip, not the model

So this is the other thing: a full, unclipped, durable transcript, written
beside the run rather than published to a dashboard. It answers "what exactly
did the model see, and what exactly did it reply" months later, which is the
question every one of those investigations actually needed.

**Shape.** One JSON object per line, appended, under
`DATA_DIR/transcripts/<run_id>.jsonl`. JSON Lines because it survives a crash
mid-write (the file is still valid up to the last complete line), needs no
schema migration, and can be read with `grep` when nothing else is available -
the same reasoning as the execution ledger beside it.

**Kinds.** `model_request` (the messages this call ADDED, plus `carried` -
how many earlier ones it resent unchanged; see `_only_what_is_new`, and note
that every message appears exactly once across a stage's entries),
`model_response` (content, tool calls, token usage, finish reason),
`tool_call` and `tool_result` (post-middleware, so the notices are in the
record), and `note` for anything a stage wants to leave behind.

**Never raises.** A transcript that can fail a run is worth less than no
transcript. Every entry point swallows and logs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Characters of any single field kept. Generous rather than tidy: a prompt is
#: the thing most often needed in full, and the point of this file is to be the
#: copy that was not cut short. A field past this is recorded truncated with its
#: original length, which is still far more than the 2,000-character event feed.
MAX_FIELD_CHARS = 256_000


def transcripts_enabled() -> bool:
    """Opt-out switch, on by default. Set RUN_TRANSCRIPT=false to silence."""
    return os.environ.get("RUN_TRANSCRIPT", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def transcript_path(run_id: str) -> Path | None:
    """Where this run's transcript lives, or None if it cannot be placed."""
    if not run_id:
        return None
    try:
        safe = "".join(c for c in str(run_id) if c.isalnum() or c in "-_")
        if not safe:
            return None
        directory = Path(os.environ.get("DATA_DIR", ".")) / "transcripts"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{safe}.jsonl"
    except OSError:
        logger.debug("Could not place a transcript file", exc_info=True)
        return None


def _shortened(value: Any) -> Any:
    """`value` with any oversized string marked rather than silently cut."""
    if isinstance(value, str) and len(value) > MAX_FIELD_CHARS:
        return value[:MAX_FIELD_CHARS] + (
            f"\n\n[transcript: {len(value) - MAX_FIELD_CHARS:,} further characters "
            f"not recorded; the field was {len(value):,} characters]"
        )
    if isinstance(value, list):
        return [_shortened(item) for item in value]
    if isinstance(value, dict):
        return {key: _shortened(item) for key, item in value.items()}
    return value


def record(run_id: str | None, stage: str, kind: str, **fields: Any) -> None:
    """Append one entry. Never raises."""
    if not run_id or not transcripts_enabled():
        return
    path = transcript_path(run_id)
    if path is None:
        return
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "run_id": str(run_id),
        "stage": stage or "",
        "kind": kind,
        **{key: _shortened(value) for key, value in fields.items()},
    }
    try:
        line = json.dumps(entry, default=str)
    except (TypeError, ValueError):
        # A field that will not serialise must not cost the whole entry.
        try:
            line = json.dumps(
                {
                    "at": entry["at"],
                    "run_id": entry["run_id"],
                    "stage": entry["stage"],
                    "kind": kind,
                    "unserialisable": repr(fields)[:MAX_FIELD_CHARS],
                }
            )
        except Exception:  # noqa: BLE001 - give up on this entry, not the run
            return
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        logger.debug("Could not append to the transcript", exc_info=True)


def read_transcript(run_id: str, kinds: set[str] | None = None) -> list[dict]:
    """Every entry for a run, oldest first. Never raises.

    A line that will not parse is skipped rather than ending the read: a run
    killed mid-write leaves one, and the entries before it are still the record
    of what happened.
    """
    path = transcript_path(run_id)
    if path is None or not path.is_file():
        return []
    entries: list[dict] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if kinds is None or entry.get("kind") in kinds:
                    entries.append(entry)
    except OSError:
        return []
    return entries


#: Lines of command output to carry into a defect-fix brief. A test runner's
#: last forty lines hold the failure and the summary; the rest is the passing
#: tests above it.
OBSERVED_OUTPUT_LINES = 40


def last_failing_command(run_id: str | None) -> dict[str, str] | None:
    """The most recent command that failed in this run, with what it printed.

    Written for `build_defect_fix_request`, which had a real problem: the
    defect handed to a fixer is the *reporting* specialist's prose reading of a
    failure, and prose drifts.

    Measured on one run. `defect_fix_2_1` was briefed with "Syntax error
    in createElementFallback causing renderTasks failure ... Observe stderr
    showing Unexpected token '}'". By then the suite was failing with
    `ReferenceError: mockList is not defined` at `app.test.mjs:50:20`, and
    there was no syntax error anywhere in the file. The fixer spent its stage
    looking for one, and the run went through three remediation rounds without
    the defect moving.

    The machine's own words were on disk the whole time - the transcript
    records every command a stage runs, with its result, verbatim. This hands
    them back. The prose stays: it carries the specialist's judgement about
    *which* failure matters, which the raw output does not.

    Every tool whose result carries an exit code counts, not one tool by name,
    and a failure the same command has passed since is no failure any more.
    Measured on one run: a fixer was briefed with a unit-suite failure of 47
    tests, one failing, as "the machine's own output" to believe over the
    report. The suite had since grown to 61 and passed three times - through
    the validation tool, which this did not read - and the fixer spent twelve
    minutes looking for a failure that was gone.
    """
    if not run_id:
        return None
    calls: dict[str, dict] = {}
    latest: dict[str, dict[str, str] | None] = {}
    for entry in read_transcript(run_id, {"tool_call", "tool_result"}):
        call_id = str(entry.get("call_id") or "")
        if not call_id:
            continue
        if entry.get("kind") == "tool_call":
            calls[call_id] = entry
            continue
        call = calls.get(call_id)
        content = str(entry.get("content") or "")
        outcome = _exit_code(content)
        if call is None or outcome is None:
            continue
        command = _the_command(call)
        if not command or _runs_a_probe(call):
            continue
        # Re-inserted so the dict's order is the order of each command's
        # latest result.
        latest.pop(_same_command(command), None)
        latest[_same_command(command)] = None if outcome == "0" else {
            "command": command,
            "output": _last_lines(content, OBSERVED_OUTPUT_LINES),
            "at": str(entry.get("at") or ""),
            "stage": str(call.get("stage") or entry.get("stage") or ""),
        }
    failing = [found for found in latest.values() if found]
    return failing[-1] if failing else None


def _runs_a_probe(call: dict) -> bool:
    """Whether the command runs a stage's throwaway probe, whose failure is the probe's, not the product's.

    Measured live: one fixer's `tmp-check-*.py` failed on its own import path,
    and two later fixes, of other defects, were briefed with that traceback
    as the product's failure.
    """
    from app.analysis.file_kinds import is_scratch

    argv = (call.get("args") or {}).get("command")
    words = argv if isinstance(argv, list) else str(argv or "").split()
    return any(is_scratch(str(word)) for word in words[:4] if "/" in str(word) or "." in str(word))


def _the_command(call: dict) -> str:
    """The command a tool call ran, as one line, or ""."""
    argv = (call.get("args") or {}).get("command")
    if isinstance(argv, list):
        return " ".join(str(part) for part in argv)
    return str(argv or "").strip()


#: A leading `cd <dir> &&` (or `;`) - the same command, spelled from elsewhere.
_CD_FIRST = re.compile(r"^\s*cd\s+\S+\s*(?:&&|;)\s*")


def _same_command(command: str) -> str:
    """`command` with what does not change which command it is taken out."""
    return " ".join(_CD_FIRST.sub("", command).split())


def _exit_code(content: str) -> str | None:
    """A command result's exit code as text, or None for no command result.

    A refused command has an `error` and no exit code; that is the harness
    declining, not the project failing, and briefing a fixer with it would send
    it after the wrong thing.

    The quotes around the number are optional because the tool really does send
    it both ways - `{"returncode": "0"}` in the transcripts on disk. Matching
    the bare-integer form alone found nothing at all, silently.
    """
    match = re.search(r'"returncode"\s*:\s*"?(-?\d+)"?', content)
    return match.group(1) if match else None


def _last_lines(content: str, limit: int) -> str:
    """The tail of a command result, with the JSON envelope's escapes undone."""
    try:
        payload = json.loads(content)
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        text = "\n".join(
            str(payload.get(stream) or "").rstrip()
            for stream in ("stdout", "stderr")
            if payload.get(stream)
        )
    else:
        text = content
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= limit:
        return "\n".join(lines)
    return "... (earlier output omitted)\n" + "\n".join(lines[-limit:])


#: The key, in a message's `additional_kwargs`, under which the project memory says
#: how many leading characters of that message it put there. The provider never
#: sends it (only `name` is read from there), so the prompt is unchanged.
MEMORY_CHARS = "project_memory_chars"

#: A request's own section header, `--- Title ---`, and a memory file's, `=== path ===`.
_A_SECTION = re.compile(r"^(?:-{3}|={3}) .+ (?:-{3}|={3})[^\n]*$", re.M)
#: The sections that carry the specification: a header naming it, and not one of
#: the advice or gap lists that only mention it.
_THE_SPECIFICATION = re.compile(r"specification", re.I)
_ONLY_MENTIONS_IT = re.compile(r"advi[cs]e|defers|already decided", re.I)


def _specification_in(text: str) -> int:
    """Characters of `text` inside sections whose header names the specification."""
    headers = list(_A_SECTION.finditer(text))
    size = 0
    for index, header in enumerate(headers):
        title = header.group(0)
        if not _THE_SPECIFICATION.search(title) or _ONLY_MENTIONS_IT.search(title):
            continue
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        size += end - header.start()
    return size


def _contract_in(text: str) -> int:
    """Characters of the environment contract inside a system prompt, or 0."""
    try:
        from app.agents.environment_contract import environment_contract_text

        contract = environment_contract_text()
    except Exception:  # noqa: BLE001 - no contract, nothing to attribute
        return 0
    return len(contract) if contract and contract in text else 0


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in content
        )
    return str(content or "")


def prompt_blocks(messages: list[dict[str, Any]], kwargs: dict[str, Any] | None = None) -> dict[str, int]:
    """What one request carried, by block, in characters (Initiative BF).

    `system` (less the `environment_contract` it ends with), `tool_schemas`,
    `project_memory`, `workspace` (the digest), `specification` (wherever it
    sits), `request` (the stage's opening ask), `notes` (the harness's
    bracketed notices later in the conversation) and `conversation` (the
    model's turns, tool results, anything else). The sizes sum to the whole
    request, so a share is a share of what the server had to read.
    """
    blocks: dict[str, int] = {}

    def add(name: str, size: int) -> None:
        if size > 0:
            blocks[name] = blocks.get(name, 0) + size

    tools = ((kwargs or {}).get("invocation_params") or {}).get("tools") or []
    if tools:
        add("tool_schemas", len(json.dumps(tools, default=str)))
    # The stage's opening turn: every human message before the model's first
    # reply. A request can arrive as several messages (the ask, the documents,
    # the research), and counting only the first as the request put the rest
    # under conversation - 60k characters of an architect's opening request.
    answered = False
    for message in messages or []:
        role = str(message.get("role") or "")
        if role in ("ai", "assistant", "tool"):
            answered = True
        text = _text_of(message.get("content"))
        calls = message.get("tool_calls")
        size = len(text) + (len(json.dumps(calls, default=str)) if calls else 0)
        if role == "system":
            contract = _contract_in(text)
            add("environment_contract", contract)
            add("system", size - contract)
            continue
        if role not in ("human", "user"):
            add("conversation", size)
            continue
        memory = min(int(message.get(MEMORY_CHARS) or 0), len(text))
        if memory:
            spec = _specification_in(text[:memory])
            add("specification", spec)
            add("project_memory", memory - spec)
            text, size = text[memory:], size - memory
        stripped = text.lstrip()
        if stripped.startswith("The workspace as it stands"):
            kind = "workspace"
        elif stripped.startswith("[Project memory"):
            kind = "project_memory"
        elif not answered:
            kind = "request"
        elif stripped.startswith("["):
            kind = "notes"
        else:
            kind = "conversation"
        spec = _specification_in(text)
        add("specification", spec)
        add(kind, size - spec)
    return blocks


def _messages_of(payload: Any) -> list[dict[str, Any]]:
    """Messages in a shape that reads the same for every provider."""
    rendered: list[dict[str, Any]] = []
    for message in payload or []:
        if isinstance(message, dict):
            rendered.append(
                {"role": message.get("role", "?"), "content": message.get("content", "")}
            )
            continue
        entry: dict[str, Any] = {
            "role": getattr(message, "type", None) or message.__class__.__name__,
            "content": getattr(message, "content", ""),
        }
        calls = getattr(message, "tool_calls", None)
        if calls:
            entry["tool_calls"] = [
                {"name": c.get("name"), "args": c.get("args"), "id": c.get("id")}
                for c in calls
                if isinstance(c, dict)
            ]
        if getattr(message, "tool_call_id", None):
            entry["tool_call_id"] = message.tool_call_id
        memory = (getattr(message, "additional_kwargs", None) or {}).get(MEMORY_CHARS)
        if memory:
            entry[MEMORY_CHARS] = memory
        rendered.append(entry)
    return rendered


def _tool_names(kwargs: dict[str, Any]) -> list[str]:
    """The tools this call offered the model, by name.

    Part of the prompt in every sense that matters, and it was not recorded.
    "Why did this stage never call `run_validation`?" cannot be answered from a
    transcript that does not say whether `run_validation` was on the table -
    which is the question this record exists to answer.

    Names rather than schemas: the schemas are large, identical across every
    call of a stage, and the name is what a reader is checking.
    """
    try:
        tools = ((kwargs or {}).get("invocation_params") or {}).get("tools") or []
        names = []
        for entry in tools:
            if isinstance(entry, dict):
                function = entry.get("function")
                name = (function or {}).get("name") if isinstance(function, dict) else entry.get("name")
                if name:
                    names.append(str(name))
        return names
    except Exception:  # noqa: BLE001 - a record must not fail a call
        return []


#: How many requests may record only what is new before one records the
#: whole conversation again. A full copy every so often means a chain broken
#: by a crash, a rotation or a bug self-heals within this many entries
#: instead of leaving the rest of the stage unreadable.
FULL_CONVERSATION_EVERY = 25

#: `(run_id, stage) -> (fingerprints of every message recorded so far, how
#: many requests since the last full copy)`. Bounded: a worker process runs
#: many stages and this must not grow with them.
_RECORDED_PREFIX: "OrderedDict[tuple[str, str], tuple[list[str], int]]" = OrderedDict()
MAX_CONVERSATIONS_TRACKED = 32


def _fingerprints(messages: list[dict[str, Any]]) -> list[str]:
    """One short hash per message, for comparing two conversations cheaply."""
    return [
        hashlib.sha1(
            json.dumps(message, sort_keys=True, default=str).encode("utf-8", "replace")
        ).hexdigest()[:16]
        for message in messages
    ]


def _only_what_is_new(
    run_id: str | None, stage: str, messages: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    """The messages this request added, and how many it carried unchanged.

    A model request carries the whole conversation, and the transcript
    recorded all of it every time - so the file grows with the square of a
    stage's length. Measured on one run mid-run: 36.6 MB, of which 279
    `model_request` entries were 33.4 MB. 91% of the record was copies of
    text already in it, and the stored transcripts came to 490 MB.

    Recording the delta keeps every message exactly once and keeps the whole
    conversation reconstructible, because `carried` says how many of the
    earlier ones this request resent and the fingerprints prove they were the
    same ones.

    Falls back to the whole conversation whenever nothing at all is shared -
    a compaction rewrites history from the first message, and a delta against
    a history that moved would be a lie.

    An injected message that is not part of history is recorded again on
    every call that carries it, which is correct: it genuinely differs per
    call, and `carried + len(messages)` is still the length the model saw.
    """
    if not run_id:
        return messages, 0
    key = (run_id, stage)
    now = _fingerprints(messages)
    seen, since_full = _RECORDED_PREFIX.get(key, ([], FULL_CONVERSATION_EVERY))

    # The longest common prefix, not "is the old list a prefix of the new
    # one". Several middlewares append to the request without persisting it -
    # the workspace digest on every call, the settled-answer correction, the
    # response reminder - so the conversation the model sees is
    # `history + injected`, and the NEXT one is `history + new turns +
    # injected`. The injected message lands at a different index each time,
    # which made a strict prefix test fail on every single call.
    #
    # Measured live after the first deploy of this code: five consecutive
    # requests, `carried=0` on all five, nothing trimmed at all.
    shared = 0
    for before, after in zip(seen, now):
        if before != after:
            break
        shared += 1

    keep_whole = since_full >= FULL_CONVERSATION_EVERY or shared == 0
    _RECORDED_PREFIX[key] = (now, 0 if keep_whole else since_full + 1)
    _RECORDED_PREFIX.move_to_end(key)
    while len(_RECORDED_PREFIX) > MAX_CONVERSATIONS_TRACKED:
        _RECORDED_PREFIX.popitem(last=False)
    if keep_whole:
        return messages, 0
    return messages[shared:], shared


def build_transcript_callback(run_id: str | None, stage: str) -> Any:
    """A callback that records every prompt and every reply, in full."""
    from langchain_core.callbacks import BaseCallbackHandler

    class TranscriptCallback(BaseCallbackHandler):
        """The half of the record that the tool middleware cannot see."""

        def on_chat_model_start(
            self, serialized: dict[str, Any], messages: Any, **kwargs: Any
        ) -> None:  # noqa: ARG002
            try:
                offered = _tool_names(kwargs)
                for conversation in messages or []:
                    whole = _messages_of(conversation)
                    added, carried = _only_what_is_new(run_id, stage, whole)
                    record(
                        run_id,
                        stage,
                        "model_request",
                        messages=added,
                        # How many earlier messages this request resent
                        # unchanged. `carried + len(messages)` is the length
                        # of the conversation the model actually saw.
                        carried=carried,
                        model=(serialized or {}).get("name"),
                        tools=offered,
                        # The whole request by block, so a run can say what
                        # its input was spent on (Initiative BF).
                        blocks=prompt_blocks(whole, kwargs),
                    )
            except Exception:  # noqa: BLE001 - a record must not fail a call
                logger.debug("Could not record a model request", exc_info=True)

        def on_llm_end(self, response: Any, **kwargs: Any) -> None:  # noqa: ARG002
            try:
                for generations in getattr(response, "generations", []) or []:
                    for generation in generations or []:
                        message = getattr(generation, "message", None)
                        record(
                            run_id,
                            stage,
                            "model_response",
                            text=getattr(generation, "text", "") or "",
                            tool_calls=[
                                {"name": c.get("name"), "args": c.get("args")}
                                for c in (getattr(message, "tool_calls", None) or [])
                                if isinstance(c, dict)
                            ],
                            # Kept whole: a call whose arguments did not parse
                            # is otherwise nowhere, and one run lost three
                            # specifications of ~20,000 tokens that way with
                            # nothing to say why.
                            invalid_tool_calls=[
                                {"name": c.get("name"), "error": c.get("error"), "args": c.get("args")}
                                for c in (getattr(message, "invalid_tool_calls", None) or [])
                                if isinstance(c, dict)
                            ],
                            usage=getattr(message, "usage_metadata", None),
                            # How long the reply's reasoning was, for a server
                            # that reports no reasoning tokens.
                            reasoning_chars=(getattr(message, "response_metadata", None) or {}).get("reasoning_chars") or 0,
                            finish_reason=(getattr(generation, "generation_info", None) or {}).get(
                                "finish_reason"
                            ),
                        )
            except Exception:  # noqa: BLE001
                logger.debug("Could not record a model response", exc_info=True)

        def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:  # noqa: ARG002
            record(run_id, stage, "model_error", error=f"{type(error).__name__}: {error}")

    return TranscriptCallback()


def build_transcript_middleware(stage: str) -> Any:
    """Middleware recording every tool call and its result, after the notices.

    At the tool boundary rather than on a callback, deliberately. `on_tool_end`
    fires when the *tool* returns, before any middleware appends to the result,
    so a callback records what the tool produced and not what the model was
    given. Everything this session added - repeat notices, structural warnings,
    budget warnings, refusals - lives in that gap.
    """
    from langchain.agents.middleware import AgentMiddleware

    class TranscriptMiddleware(AgentMiddleware):
        name = "TranscriptMiddleware"

        def wrap_tool_call(self, request: Any, handler: Any) -> Any:
            call = getattr(request, "tool_call", None) or {}
            run_id = _run_id_from_config()
            here = _stage_from_config(stage)
            record(
                run_id,
                here,
                "tool_call",
                tool=call.get("name"),
                args=call.get("args"),
                call_id=call.get("id"),
            )
            try:
                result = handler(request)
            except Exception as failure:  # noqa: BLE001 - record, then re-raise
                record(
                    run_id,
                    here,
                    "tool_result",
                    tool=call.get("name"),
                    call_id=call.get("id"),
                    raised=f"{type(failure).__name__}: {failure}",
                )
                raise
            record(
                run_id,
                here,
                "tool_result",
                tool=call.get("name"),
                call_id=call.get("id"),
                content=getattr(result, "content", None),
                status=getattr(result, "status", None),
            )
            return result

    return TranscriptMiddleware()


def _stage_from_config(fallback: str) -> str:
    """The stage now running, from the graph's config; `fallback` if absent.

    A role agent is constructed once and invoked for many stages, so the name
    this middleware was built with is the agent's phase (`implementation`),
    not the stage making the call (`specialist_testing_1`). The invoke knows;
    the constructor could not. See `app.tracing.APP_STAGE_KEY`.
    """
    try:
        from langgraph.config import get_config

        from app.tracing import APP_STAGE_KEY

        return (get_config() or {}).get("configurable", {}).get(APP_STAGE_KEY) or fallback
    except Exception:  # noqa: BLE001 - outside a run, or no config; use the fallback
        return fallback


def _run_id_from_config() -> str | None:
    """This run's id, from the running graph's config. None outside a run."""
    try:
        from langgraph.config import get_config

        from app.tracing import APP_RUN_ID_KEY

        return (get_config() or {}).get("configurable", {}).get(APP_RUN_ID_KEY)
    except Exception:  # noqa: BLE001 - outside a graph run there is nothing to key on
        return None


__all__ = [
    "MAX_FIELD_CHARS",
    "build_transcript_callback",
    "build_transcript_middleware",
    "read_transcript",
    "record",
    "transcript_path",
    "transcripts_enabled",
]


def render_transcript(run_id: str, kinds: set[str] | None = None) -> str:
    """The transcript as something a person reads top to bottom.

    The point of keeping the record is being able to open it later, so the
    reader ships with the writer rather than being rebuilt from `jq` every
    time someone needs it.
    """
    entries = read_transcript(run_id, kinds)
    if not entries:
        return f"No transcript for {run_id}. It may predate transcripts, or RUN_TRANSCRIPT may be off."

    lines = [f"Transcript for {run_id} - {len(entries):,} entries", "=" * 72]
    stage = None
    for entry in entries:
        if entry.get("stage") != stage:
            stage = entry.get("stage")
            lines += ["", f"### stage: {stage}", ""]
        clock = str(entry.get("at", ""))[11:19]
        kind = entry.get("kind")

        if kind == "model_request":
            messages = entry.get("messages") or []
            # `carried` messages were resent unchanged and were printed by an
            # earlier entry of this stage - see `_only_what_is_new`. Saying so
            # is what keeps the reading honest: the model saw all of them.
            carried = int(entry.get("carried") or 0)
            seen_before = f", {carried} carried from above" if carried else ""
            lines.append(
                f"[{clock}] --> model ({carried + len(messages)} messages"
                f"{seen_before})"
            )
            for message in messages:
                role = str(message.get("role", "?"))
                body = str(message.get("content", "")).rstrip()
                lines.append(f"    {role}:")
                lines += [f"      {ln}" for ln in body.splitlines() or [""]]
                for call in message.get("tool_calls") or []:
                    lines.append(f"      -> calls {call.get('name')}({call.get('args')})")
        elif kind == "model_response":
            lines.append(f"[{clock}] <-- model")
            text = str(entry.get("text", "")).rstrip()
            if text:
                lines += [f"      {ln}" for ln in text.splitlines()]
            for call in entry.get("tool_calls") or []:
                lines.append(f"      -> calls {call.get('name')}({call.get('args')})")
            usage = entry.get("usage")
            if usage:
                lines.append(f"      usage: {usage}  finish: {entry.get('finish_reason')}")
        elif kind == "tool_call":
            lines.append(f"[{clock}]  >> {entry.get('tool')}({entry.get('args')})")
        elif kind == "tool_result":
            body = entry.get("raised") or str(entry.get("content", ""))
            lines.append(f"[{clock}]  << {entry.get('tool')}")
            lines += [f"      {ln}" for ln in body.rstrip().splitlines()[:400]]
        else:
            lines.append(f"[{clock}] {kind}: {json.dumps({k: v for k, v in entry.items() if k not in ('at', 'run_id', 'stage', 'kind')}, default=str)[:500]}")
    return "\n".join(lines)


def _main() -> int:
    """`python -m app.observability.transcript <run-id> [kind ...]`"""
    import sys

    if len(sys.argv) < 2:
        directory = Path(os.environ.get("DATA_DIR", ".")) / "transcripts"
        known = sorted(p.stem for p in directory.glob("*.jsonl")) if directory.is_dir() else []
        print("usage: python -m app.observability.transcript <run-id> [kind ...]")
        print(f"{len(known)} transcript(s) available:")
        for name in known[-25:]:
            print(f"  {name}")
        return 0
    kinds = set(sys.argv[2:]) or None
    print(render_transcript(sys.argv[1], kinds))
    return 0


if __name__ == "__main__":  # pragma: no cover - a convenience entry point
    raise SystemExit(_main())
