"""The complete record of what a run said, was told, and did.

The event stream is a UI feed. It clips every message at 2,000 characters, it
carries tool output as the tool produced it rather than as the model received
it, and it has never recorded the prompts at all. Those three gaps cost real
diagnosis time in one session:

- a repeat notice appended after 3,847 characters of file content sat past the
  clip, so every audit of run-3c0c31d2 read "no note fired" when the notice had
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

**Kinds.** `model_request` (every message sent, and the tools bound),
`model_response` (content, tool calls, token usage, finish reason),
`tool_call` and `tool_result` (post-middleware, so the notices are in the
record), and `note` for anything a stage wants to leave behind.

**Never raises.** A transcript that can fail a run is worth less than no
transcript. Every entry point swallows and logs.
"""

from __future__ import annotations

import json
import logging
import os
import re
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

    Measured on run-d3965815. `defect_fix_2_1` was briefed with "Syntax error
    in createElementFallback causing renderTasks failure ... Observe stderr
    showing Unexpected token '}'". By then the suite was failing with
    `ReferenceError: mockList is not defined` at `app.test.mjs:50:20`, and
    there was no syntax error anywhere in the file. The fixer spent its stage
    looking for one, and the run went through three remediation rounds without
    the defect moving.

    The machine's own words were on disk the whole time - the transcript
    records every `run_terminal_command` result verbatim. This hands them back.
    The prose stays: it carries the specialist's judgement about *which*
    failure matters, which the raw output does not.
    """
    if not run_id:
        return None
    calls: dict[str, dict] = {}
    found: dict[str, str] | None = None
    for entry in read_transcript(run_id, {"tool_call", "tool_result"}):
        call_id = str(entry.get("call_id") or "")
        if not call_id:
            continue
        if entry.get("kind") == "tool_call":
            calls[call_id] = entry
            continue
        call = calls.get(call_id)
        if call is None or call.get("tool") != "run_terminal_command":
            continue
        content = str(entry.get("content") or "")
        if not _reports_a_failure(content):
            continue
        argv = (call.get("args") or {}).get("command")
        found = {
            "command": (
                " ".join(str(part) for part in argv)
                if isinstance(argv, list)
                else str(argv or "")
            ),
            "output": _last_lines(content, OBSERVED_OUTPUT_LINES),
            "at": str(entry.get("at") or ""),
            "stage": str(call.get("stage") or entry.get("stage") or ""),
        }
    return found


def _reports_a_failure(content: str) -> bool:
    """Whether this `run_terminal_command` result is a failure.

    The tool returns a JSON object carrying `returncode`. A refused command has
    an `error` and no exit code; that is the harness declining, not the project
    failing, and briefing a fixer with it would send it after the wrong thing.

    The quotes around the number are optional because the tool really does send
    it both ways - `{"returncode": "0"}` in the transcripts on disk. Matching
    the bare-integer form alone found nothing at all, silently.
    """
    match = re.search(r'"returncode"\s*:\s*"?(-?\d+)"?', content)
    return bool(match) and match.group(1) != "0"


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
        rendered.append(entry)
    return rendered


def build_transcript_callback(run_id: str | None, stage: str) -> Any:
    """A callback that records every prompt and every reply, in full."""
    from langchain_core.callbacks import BaseCallbackHandler

    class TranscriptCallback(BaseCallbackHandler):
        """The half of the record that the tool middleware cannot see."""

        def on_chat_model_start(
            self, serialized: dict[str, Any], messages: Any, **kwargs: Any
        ) -> None:  # noqa: ARG002
            try:
                for conversation in messages or []:
                    record(
                        run_id,
                        stage,
                        "model_request",
                        messages=_messages_of(conversation),
                        model=(serialized or {}).get("name"),
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
                            usage=getattr(message, "usage_metadata", None),
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
            record(
                run_id,
                stage,
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
                    stage,
                    "tool_result",
                    tool=call.get("name"),
                    call_id=call.get("id"),
                    raised=f"{type(failure).__name__}: {failure}",
                )
                raise
            record(
                run_id,
                stage,
                "tool_result",
                tool=call.get("name"),
                call_id=call.get("id"),
                content=getattr(result, "content", None),
                status=getattr(result, "status", None),
            )
            return result

    return TranscriptMiddleware()


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
            lines.append(f"[{clock}] --> model ({len(messages)} messages)")
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
