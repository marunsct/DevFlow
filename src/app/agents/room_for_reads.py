"""A whole-file read is given whole only while the request has room for it (`READS_SIZED_TO_THE_ROOM`, LF.1289).

Measured on a medium run (`reports/audits/2026-11-24-reading-stages-past-their-room.md`, section 1.2): a technical
lead's request with a full project memory was 51,000-64,000 tokens before its first read, against a 59,776-token
room, and the lead reads about eight files a reply - 55,000-65,000 characters, which does not fit by itself. 23% of
all model calls of that run were past the room. A whole file read into a conversation that has no room for it is
summarised away within a call or two and read again: the loop the reading stages were caught in.

So, with the switch on, a read that names no `offset` and no `limit` of a file longer than a narrow range, whose
numbered text is larger than the room the request has left, is answered with the file's outline - each definition
with the lines it spans - and its length, and the stage reads the lines it needs by range. A range read is never
changed. The room left is known exactly: the last reply's reported `input_tokens` against the stage's input ceiling
(`context_budget`), less what the tool results after that reply have returned. A product whose files fit never meets
it, and with the switch off nothing changes.

The outline is `app.analysis.outline.entries` when that module is present; without it, the file's top-level
definition lines (`project_memory._DEFINES`) with the lines each spans. Either is a callable
`(path, text) -> [(first line, last line, text)]`, so this module works whichever lands first.
"""
from __future__ import annotations

import contextvars
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

NAME = "READS_SIZED_TO_THE_ROOM"
#: Off until measured (owner policy: a change to what a tool returns is doubtful until a run shows it costs nothing).
ON_BY_DEFAULT = False

#: What the stage's room is kept under in `stage_memory`.
ROOM_RECORD = "room_for_reads"
#: The most characters of one outline line.
MOST_ENTRY_CHARACTERS = 110
#: The most outline lines given in one answer; the rest are counted.
MOST_ENTRIES = 200

#: (first line, last line, the line's text) of one thing a file defines.
Entry = tuple[int, int, str]
Outline = Callable[[str, str], list[Entry]]

#: Said once in every answer, which `switch_firing` reads as the switch having acted.
SAID = "more than this request has room left for"


class _ReadsSizedToTheRoom:
    """`READS_SIZED_TO_THE_ROOM` as the switch registry reads one: off in code until measured."""

    ON_BY_DEFAULT = ON_BY_DEFAULT
    #: What the admin page says this switch does.
    explanation = ("A read of a whole file whose numbered text is larger than the room the stage's request has left "
                   "(the last reply's reported input tokens against the input ceiling, less what was read since) is "
                   "answered with the file's outline - each definition and the lines it spans - so the stage reads "
                   "the lines it needs by range. A range read is never changed. Measured on a medium run: 23% of "
                   "calls were past the room, and whole files read into them were summarised away and read again.")

    @staticmethod
    def enabled() -> bool:
        from app.switches import is_on

        return is_on(NAME, ON_BY_DEFAULT)


reads_sized_switch = _ReadsSizedToTheRoom()


# --- the outline --------------------------------------------------------------------------------------------------


def top_level_definitions(path: str, text: str) -> list[Entry]:
    """The file's least-indented definition lines, each with the lines up to the next: the outline without one."""
    from app.agents.project_memory import _DEFINES

    lines = text.splitlines()
    found = [(n, line) for n, line in enumerate(lines, 1) if _DEFINES.match(line)]
    if not found:
        return []
    least = min(len(line) - len(line.lstrip()) for _, line in found)
    top = [(n, line) for n, line in found if len(line) - len(line.lstrip()) == least]
    ends = [n - 1 for n, _ in top[1:]] + [len(lines)]
    return [(n, end, line.strip()[:MOST_ENTRY_CHARACTERS]) for (n, line), end in zip(top, ends)]


def the_outline() -> Outline:
    """`app.analysis.outline.entries` when it is there, else `top_level_definitions`."""
    try:
        from app.analysis.outline import entries
    except ImportError:
        return top_level_definitions
    return entries


# --- the room -----------------------------------------------------------------------------------------------------


def _ceiling_of(model: Any) -> int:
    from app.agents.context_budget import ContextBudget

    try:
        from app.models import environment_of

        return ContextBudget.resolve(environment_of(model)).input_ceiling_tokens
    except Exception:  # noqa: BLE001 - the deployment's own window
        return ContextBudget.resolve().input_ceiling_tokens


def _input_tokens(response: Any) -> int | None:
    """The input tokens the server reported for the reply in `response` (a model response or a message), or None."""
    messages = getattr(response, "result", None)
    messages = messages if isinstance(messages, list) else [response]
    for message in reversed(messages):
        usage = getattr(message, "usage_metadata", None)
        if isinstance(usage, dict) and int(usage.get("input_tokens") or 0) > 0:
            return int(usage["input_tokens"])
    return None


def note_the_reply(response: Any, model: Any) -> None:
    """Keep the room the stage's next request has, from the reply's reported input tokens. Never raises."""
    try:
        from app.agents.stage_memory import store

        tokens = _input_tokens(response)
        if tokens is None:
            return
        record = store(ROOM_RECORD, {})
        record.clear()
        record.update(input_tokens=tokens, ceiling=_ceiling_of(model), returned=0)
    except Exception:  # noqa: BLE001 - the room is then unknown, and reads are as before
        logger.debug("Could not keep the room left for reads", exc_info=True)


def note_what_was_returned(characters: int) -> None:
    """Count a tool result's characters against the room the next request has."""
    from app.agents.stage_memory import store

    record = store(ROOM_RECORD, {})
    if "input_tokens" in record:
        record["returned"] = int(record.get("returned") or 0) + max(0, int(characters))


def room_left() -> int | None:
    """Characters the stage's next request still has room for (negative past it), or None when not known."""
    from app.agents.context_budget import CHARS_PER_TOKEN
    from app.agents.stage_memory import store

    record = store(ROOM_RECORD, {})
    if "input_tokens" not in record:
        return None
    return (int(record["ceiling"]) - int(record["input_tokens"])) * CHARS_PER_TOKEN - int(record.get("returned") or 0)


# --- a whole read -------------------------------------------------------------------------------------------------

#: Set around one `read_file` call that named no range: a dict the backend writes its answer into.
_A_WHOLE_READ: contextvars.ContextVar[dict | None] = contextvars.ContextVar("a_whole_read", default=None)


def asks_for_the_whole_file(arguments: Any) -> bool:
    """Whether `read_file` arguments, as the model wrote them, name no range."""
    if not isinstance(arguments, dict):
        return False
    return arguments.get("offset") in (None, "", 0, "0") and arguments.get("limit") in (None, "")


def numbered_length(text: str) -> int:
    """The characters `text` takes once numbered as a read returns it."""
    from deepagents.backends.utils import format_content_with_line_numbers

    return len(format_content_with_line_numbers(text, start_line=1))


def answer(path: str, text: str, room: int, outline: Outline | None = None) -> str:
    """What a whole read of `path` (its whole `text`) is answered with when its numbered text is past `room`."""
    from app.agents.project_memory import MOST_WINDOW_LINES

    lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
    numbered = numbered_length(text)
    entries = (outline or the_outline())(path, text)
    first, last = (entries[0][0], entries[0][1]) if entries else (1, min(lines, MOST_WINDOW_LINES))
    head = (f"{path} has {lines:,} lines ({numbered:,} characters numbered), {SAID} "
            f"(about {max(room, 0):,} characters), so its outline is given in place of its text. Read the lines you "
            f"need by range: `offset` counts from 0 and `limit` is how many lines, so lines {first}-{last} are "
            f"offset {first - 1}, limit {last - first + 1}.")
    if not entries:
        fits = max(room, 0) * lines // max(numbered, 1)
        return head + (f"\n\nIt defines nothing an outline can show; read it a part at a time, about "
                       f"{max(MOST_WINDOW_LINES, min(fits, 400)):,} lines a read.")
    shown = [f"  {start}-{end}  {line[:MOST_ENTRY_CHARACTERS]}" for start, end, line in entries[:MOST_ENTRIES]]
    more = len(entries) - len(shown)
    tail = [f"  ... and {more} more, after line {entries[MOST_ENTRIES - 1][1]}"] if more > 0 else []
    return "\n".join([head, "", f"Outline of {path} (first-last line, then the line):", *shown, *tail])


def an_answer_in_place_of_the_whole(path: str, returned: str, total_lines: int,
                                    whole_text: Callable[[], str], root: str | None = None) -> str | None:
    """With the switch on, inside a read that named no range: the outline answer when `returned` is past the room.

    `returned` is what the read would give and `whole_text` reads the whole file. None (the read as it is) when the
    switch is off, the read named a range, the room is not known, the file is no longer than a narrow range, or what
    the read gives fits. `root`: the workspace, whose code graph adds what uses each definition (KG.6, its own switch).
    """
    slot = _A_WHOLE_READ.get()
    if slot is None or not reads_sized_switch.enabled():
        return None
    from app.agents.project_memory import MOST_WINDOW_LINES

    room = room_left()
    if room is None or total_lines <= MOST_WINDOW_LINES or numbered_length(returned) <= room:
        return None
    from app.agents.graph_in_search_answers import for_an_outline

    said = answer(path, whole_text(), room) + for_an_outline(root, path)
    slot["answer"] = said
    return said


def build_room_for_reads_middleware() -> Any:
    """Middleware that keeps the room each request has left and marks a `read_file` that names no range.

    Outside the path rewrite, so it sees the arguments as the model wrote them (the rewrite fills in a `limit`); and
    it gives the outline answer as it is, not numbered as file text.
    """
    from langchain.agents.middleware import AgentMiddleware

    class RoomForReadsMiddleware(AgentMiddleware):
        name = "RoomForReadsMiddleware"

        def wrap_model_call(self, request: Any, handler: Any) -> Any:
            response = handler(request)
            if reads_sized_switch.enabled():
                note_the_reply(response, getattr(request, "model", None))
            return response

        def wrap_tool_call(self, request: Any, handler: Any) -> Any:
            if not reads_sized_switch.enabled():
                return handler(request)
            call = getattr(request, "tool_call", None) or {}
            whole = call.get("name") == "read_file" and asks_for_the_whole_file(call.get("args"))
            slot: dict = {}
            token = _A_WHOLE_READ.set(slot if whole else None)
            try:
                result = handler(request)
            finally:
                _A_WHOLE_READ.reset(token)
            if slot.get("answer"):
                try:
                    result = result.model_copy(update={"content": slot["answer"]})
                except Exception:  # noqa: BLE001 - a Command, or some other shape: as the tool gave it
                    pass
            try:
                content = getattr(result, "content", None)
                note_what_was_returned(len(content) if isinstance(content, str) else 0)
            except Exception:  # noqa: BLE001 - the count is then low, never a failed call
                pass
            return result

    return RoomForReadsMiddleware()


__all__ = [
    "NAME",
    "ROOM_RECORD",
    "SAID",
    "an_answer_in_place_of_the_whole",
    "answer",
    "asks_for_the_whole_file",
    "build_room_for_reads_middleware",
    "note_the_reply",
    "note_what_was_returned",
    "numbered_length",
    "reads_sized_switch",
    "room_left",
    "the_outline",
    "top_level_definitions",
]
