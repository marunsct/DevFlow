"""A narrow range read is widened toward the read tool's default window while the request has room (LF.1570).

Measured on a medium run: one sprint's code review, on its second visit, made 62 reads, 55 of them distinct, almost all
50-60-line windows (`read_file(routes.py, offset 50, limit 60)`) at about 40,000 tokens of conversation a call - some
3M input tokens for one review. Each window is a model call that resends the whole conversation; the read tool's
default window is 400 lines (TR.4, LF.1520), and the request had room for it.

So, behind `READ_WINDOWS_SIZED_TO_THE_ROOM` (off in code until measured): a `read_file` naming a `limit` below the
default window, of a file that holds more lines past its `offset` than that, is given more lines from the same start -
up to the default window, never past the file's end, and never past half the room the request has left (the last
reply's reported input tokens against the input ceiling, less what was returned since: `room_for_reads.room_left`), the
other half kept for the reply's other reads and the next reply. Lines whose numbered text the conversation still holds
(LF.1517: `settled_answer.reads_in_the_conversation`, and the windows this widened that are still in view) are never
added: the window stops before them. The answer says it in one line ahead of the numbered text (`SAID`). With the room
unknown (before the stage's first reply), the switch off, or the request past the room, the read is as asked.

The model's own arguments are not changed, so the refusals that read them (the project memory's, a repeated read's)
decide the read as before; only the backend's read of the file is widened, inside the one call
(`app.agents.workspace_backend.WorkspaceBackend.read`). Measured by reads and input tokens per review and per fixer
visit (`effects_lines`, `loop.sh effects`).
"""
from __future__ import annotations

import contextvars
import re
from contextlib import contextmanager
from statistics import median
from typing import Any, Iterable, Iterator

NAME = "READ_WINDOWS_SIZED_TO_THE_ROOM"
#: Off until measured (owner policy: an efficiency change is doubtful until a run shows it costs nothing).
ON_BY_DEFAULT = False

#: The share of the room left that one widened read may take.
SHARE_OF_THE_ROOM = 0.5
#: What the stage's held windows are kept under in `stage_memory`: the lines each read's text gave, by path.
HELD_RECORD = "read windows held"
#: The windows this widened, by tool call id: (path, first line, last line), 1-based and inclusive.
WIDENED_RECORD = "read windows widened"

#: Said once in every widened answer, which `switch_firing` reads as the switch having acted.
SAID = "The read was widened to lines"


class _ReadWindowsSizedToTheRoom:
    """`READ_WINDOWS_SIZED_TO_THE_ROOM` as the switch registry reads one: off in code until measured."""

    ON_BY_DEFAULT = ON_BY_DEFAULT
    #: What the admin page says this switch does.
    explanation = ("A read of a narrow range of a longer file is given more lines from the same start, up to the read "
                   "tool's 400-line default, while the request has room for them (at most half the room left) and "
                   "never into lines the conversation still holds. Measured on a medium run: one code review made 62 "
                   "reads, almost all 50-60-line windows, at about 40k tokens of conversation a call.")

    @staticmethod
    def enabled() -> bool:
        from app.switches import is_on

        return is_on(NAME, ON_BY_DEFAULT)


read_windows_switch = _ReadWindowsSizedToTheRoom()


def enabled() -> bool:
    return read_windows_switch.enabled()


# --- what the conversation holds ------------------------------------------------------------------------------------


def _a_path(value: Any) -> str:
    return str(value or "").strip().lstrip("/")


def held_windows(messages: list[Any]) -> dict[str, list[tuple[int, int]]]:
    """Per path, the (first, last) lines whose numbered text the conversation `messages` still holds.

    The reads `settled_answer.reads_in_the_conversation` finds held, each for the window it asked (the default window
    for one that named no `limit`), and the windows this widened whose answer is still in view, for the lines given.
    """
    from app.agents.settled_answer import reads_in_the_conversation
    from app.agents.stage_memory import store
    from app.agents.workspace_paths import DEFAULT_READ_LINES

    held: dict[str, list[tuple[int, int]]] = {}
    for path, offset, lines in reads_in_the_conversation(messages):
        held.setdefault(path, []).append((offset + 1, offset + (lines or DEFAULT_READ_LINES)))
    widened = store(WIDENED_RECORD, {})
    for message in messages:
        if getattr(message, "type", None) != "tool":
            continue
        given = widened.get(str(getattr(message, "tool_call_id", "") or ""))
        if given and SAID in str(getattr(message, "content", "") or ""):
            path, first, last = given
            held.setdefault(path, []).append((first, last))
    return held


#: Kept in place of the held windows when they could not be read: then no read of the reply is widened.
_NOT_KNOWN = "\0not known"


def note_the_conversation(messages: Any) -> None:
    """Keep the windows the conversation this model call sends holds, for the reads its reply makes. Never raises:
    when they cannot be read, no read of this reply is widened."""
    from app.agents.stage_memory import store

    record = store(HELD_RECORD, {})
    record.clear()
    try:
        record.update(held_windows(messages if isinstance(messages, list) else []))
    except Exception:  # noqa: BLE001 - nothing is widened into lines that may be held
        record[_NOT_KNOWN] = []


# --- the window ----------------------------------------------------------------------------------------------------


def widened_limit(offset: int, limit: int, lines: list[str], room: int | None,
                  held: Iterable[tuple[int, int]] = ()) -> int | None:
    """The `limit` a read of `lines[offset:offset + limit]` is widened to, or None to read it as asked.

    Widened only when `limit` is below the default window and the file holds more lines past `offset + limit`; up to
    the default window, the file's end, the first line past the asked window that `held` (1-based, inclusive) already
    holds, and `SHARE_OF_THE_ROOM` of `room` (characters) for the whole numbered window.
    """
    from app.agents.workspace_paths import DEFAULT_READ_LINES

    total = len(lines)
    if room is None or offset < 0 or limit <= 0 or limit >= DEFAULT_READ_LINES or offset + limit >= total:
        return None
    asked_last = offset + limit  # 1-based number of the last line asked for
    last = min(offset + DEFAULT_READ_LINES, total)
    for first_held, last_held in held:
        if last_held > asked_last and first_held <= last:
            last = min(last, max(asked_last, first_held - 1))
    budget = int(max(room, 0) * SHARE_OF_THE_ROOM)
    gutter = len(str(last)) + 3  # the line number, two spaces and the newline
    used = sum(len(line) + gutter for line in lines[offset:asked_last])
    end = asked_last
    for line in lines[asked_last:last]:
        used += len(line) + gutter
        if used > budget:
            break
        end += 1
    return end - offset if end > asked_last else None


# --- one read ------------------------------------------------------------------------------------------------------

#: Set around one `read_file` call that named a narrow `limit`: a dict the backend writes the window it gave into.
_A_NARROW_READ: contextvars.ContextVar[dict | None] = contextvars.ContextVar("a_narrow_read", default=None)


def _asked(arguments: Any) -> tuple[str, int, int] | None:
    """(path, offset, limit) of `read_file` arguments as the model wrote them, when they name a `limit`."""
    if not isinstance(arguments, dict) or arguments.get("limit") in (None, ""):
        return None
    try:
        offset, limit = int(arguments.get("offset") or 0), int(arguments.get("limit"))
    except (TypeError, ValueError):
        return None
    return _a_path(arguments.get("file_path") or arguments.get("path")), offset, limit


@contextmanager
def around_a_read(call: Any) -> Iterator[dict | None]:
    """Around one tool call: with the switch on and a `read_file` naming a narrow window, the slot the backend widens
    it through (None otherwise). The room and the held windows are read here, as the call starts."""
    from app.agents.room_for_reads import room_left
    from app.agents.stage_memory import store

    slot = None
    try:
        call = call if isinstance(call, dict) else {}
        asked = _asked(call.get("args")) if call.get("name") == "read_file" and enabled() else None
        room = room_left() if asked else None
        held = store(HELD_RECORD, {})
        if asked is not None and room is not None and room > 0 and _NOT_KNOWN not in held:
            path, offset, limit = asked
            slot = {"path": path, "offset": offset, "limit": limit, "room": room, "id": str(call.get("id") or ""),
                    "held": list(held.get(path) or ())}
    except Exception:  # noqa: BLE001 - the read as asked
        slot = None
    if slot is None:
        yield None
        return
    token = _A_NARROW_READ.set(slot)
    try:
        yield slot
    finally:
        _A_NARROW_READ.reset(token)


def the_limit_to_read(offset: Any, limit: Any, whole_text: Any) -> Any:
    """Inside the backend's read: the `limit` to read the file with - widened inside a narrow read the request has
    room for, else `limit` as given. `whole_text` reads the file. Never raises."""
    slot = _A_NARROW_READ.get()
    if slot is None or "given" in slot:
        return limit
    try:
        if int(offset or 0) != slot["offset"] or int(limit) != slot["limit"]:
            return limit
        lines = whole_text().splitlines()
        wider = widened_limit(slot["offset"], slot["limit"], lines, slot["room"], slot["held"])
    except Exception:  # noqa: BLE001 - the read as asked
        return limit
    if wider is None:
        return limit
    slot["given"] = (slot["offset"] + 1, slot["offset"] + wider, len(lines))
    return wider


def said_in(result: Any, slot: dict | None) -> Any:
    """`result`, with the one line saying its window was widened ahead of the numbered text, when it was and the
    answer holds those lines; the window kept as held for the rest of this reply's reads."""
    if not slot or "given" not in slot:
        return result
    from app.agents.stage_memory import store

    first, last, total = slot["given"]
    content = getattr(result, "content", None)
    if not isinstance(content, str) or getattr(result, "status", "") == "error" or \
            not re.search(rf"(?m)^ *{last}(?:\t| {{2}})", content):
        return result
    asked_last = slot["offset"] + slot["limit"]
    line = (f"[{SAID} {first}-{last} of {total} (you asked for {first}-{asked_last}): the request has room for "
            f"them.]")
    try:
        result = result.model_copy(update={"content": line + "\n" + content})
    except Exception:  # noqa: BLE001 - a Command, or some other shape: as the tool gave it
        return result
    store(HELD_RECORD, {}).setdefault(slot["path"], []).append((first, last))
    if slot.get("id"):
        store(WIDENED_RECORD, {})[slot["id"]] = (slot["path"], first, last)
    return result


# --- the measure ---------------------------------------------------------------------------------------------------

_REVIEW = re.compile(r"^(?:code|security|acceptance|architecture|advice|milestone)_review")
_FIXER = re.compile(r"^defect_fix_")


def effects_lines(records: Iterable[Any]) -> list[str]:
    """`loop.sh effects` (LF.1570): reads widened, and per review and per fixer visit the median `read_file` calls and
    input tokens, so a run with the switch on is read against one without."""
    reads: dict[str, int] = {}
    tokens: dict[str, int] = {}
    widened = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        stage, kind = str(record.get("stage") or ""), record.get("kind")
        if kind == "tool_call" and record.get("tool") == "read_file":
            reads[stage] = reads.get(stage, 0) + 1
        elif kind == "model_response":
            usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
            tokens[stage] = tokens.get(stage, 0) + int(usage.get("input_tokens") or 0)
        elif kind == "tool_result" and SAID in str(record.get("content") or record.get("result") or ""):
            widened += 1

    def described(pattern: re.Pattern[str]) -> str:
        visits = [s for s in set(reads) | set(tokens) if pattern.match(s)]
        if not visits:
            return "none"
        return (f"{len(visits)} visits, median {median(reads.get(s, 0) for s in visits):g} reads and "
                f"{median(tokens.get(s, 0) for s in visits):,.0f} input tokens")

    head = "LF.1570 narrow reads widened to the room"
    return [(f"  {widened:>4}  {head}" if widened else f"     -  {head}: not reached")
            + f" (reviews: {described(_REVIEW)}; fixers: {described(_FIXER)})"]


__all__ = [
    "HELD_RECORD",
    "NAME",
    "ON_BY_DEFAULT",
    "SAID",
    "SHARE_OF_THE_ROOM",
    "WIDENED_RECORD",
    "around_a_read",
    "effects_lines",
    "enabled",
    "held_windows",
    "note_the_conversation",
    "read_windows_switch",
    "said_in",
    "the_limit_to_read",
    "widened_limit",
]
