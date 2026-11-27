"""Compaction that keeps the request a stage was given, and summarises what it did.

deepagents' `SummarizationMiddleware` replaces everything before its cutoff with
one summary message - the stage's opening request included - and makes that
summary with langchain's summariser, which trims what it summarises to its last
`trim_tokens_to_summarize` tokens and requires the slice to start on a human
message. A stage has one human message, its opening request, and it is far
larger than that budget, so the slice was always empty and the summary always
read "Previous conversation was too long to summarize."

Measured live: seven of a run's eight compactions were that empty summary, six
of them in fix stages, and all six fixes failed. One fixer, compacted twelve
minutes in, lost which defect it was fixing, its failing tests and the warning
that the served page was the scaffold's stub, and went on to edit the copy
nothing serves.

So the request is carried whole into the summary message - through every later
compaction too, from the message's own record of it - with the files the stage
has written, and the summariser is handed the latest work it can summarise.
"""

from __future__ import annotations

import re
from typing import Any

from deepagents.middleware.summarization import SummarizationMiddleware
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.messages.utils import trim_messages

#: What a summary message records of the request it replaced, and of the files written.
KEPT_REQUEST = "harness_kept_request"
FILES_WRITTEN = "harness_files_written"
SUMMARY = "harness_summary"
#: How many model calls the messages a summary replaced had made, so a stage's
#: call budget counts across a compaction (`settled_answer._model_calls_used`).
CALLS_BEFORE = "harness_calls_before"
#: How many of those replies were lost to reasoning, so the rule that keeps
#: thinking off after a second loss counts across a compaction too.
LOST_BEFORE = "harness_lost_before"
#: The files the replaced messages had read, by path, as the line ranges their results showed (LF.1285).
FILES_READ = "harness_files_read"
#: How many summaries this stage has had, this one included (LF.1285).
SUMMARIES = "harness_summaries"
#: The files the replaced messages read, each with how often, the latest read last (LF.1288): what the project memory
#: holds whole after this summary is chosen from it (`review_files.chosen_again`).
READS = "harness_reads"
#: The ledger the harness keeps of the stage's work from its tool calls (`work_note_ledger`, LF.1466): each refusal
#: the tools gave, and each command run with how it ended.
REFUSALS = "harness_refusals"
COMMANDS = "harness_commands"
#: How many messages the compaction left whole behind the summary (LF.1499): what "new since the summary" counts from.
KEPT_TAIL = "harness_kept_tail"

#: The tools that change a file, and the argument naming it.
_WRITING_TOOLS = frozenset({
    "write_artifact", "edit_artifact", "replace_lines", "replace_approved_lines",
    "move_artifact", "delete_artifact",
})
_PATH_ARGUMENTS = ("relative_path", "path", "file_path")
#: The calls whose long arguments are shortened behind the kept tail. deepagents
#: shortens only its own `write_file` and `edit_file`, which no stage here has:
#: they write through `write_artifact` and `edit_artifact`, so a written file's
#: whole content stayed in every later request of the stage, and the relief
#: `role_agent` configures for exactly that never fired.
_ARGUMENTS_SHORTENED = frozenset({"write_file", "edit_file", *_WRITING_TOOLS})

MOST_FILES_NAMED = 40

#: The most of the opening turn carried, in characters: its last message - the
#: request - always whole, the ones before it only while they fit. Measured
#: live: carrying a 27,000-character snapshot of the files at the stage's start
#: as well as the request left a compacted conversation so near the trigger
#: that one fix stage was compacted 10 times in 28 calls. The project memory
#: hands every call the files as they are now.
MOST_CARRIED_CHARACTERS = 48_000

#: Messages a compacted conversation must gain past its kept tail before it is
#: compacted again. Its kept tail sits near the trigger, so it fired again two
#: calls later. Counted past the tail the compaction really kept (LF.1499), and
#: never holding back a request that would not fit the slot (`request_fit`).
NEW_MESSAGES_BEFORE_COMPACTING_AGAIN = 8

#: The kept tail's ceiling, as a share of the compaction trigger (`role_agent`).
KEPT_TAIL_SHARE = 0.15
#: Messages a compaction always leaves whole.
MOST_KEPT_FEWEST = 2

_THE_WORK_SO_FAR = "What follows is the latest of this stage's work, to be summarised."

#: What the summariser is asked for: the stage's work note, not a description of what it read (PA.2, LF.1360).
#: Measured on one medium run: the acceptance suite's writer was summarised 74 times in 462 calls by langchain's
#: general prompt, which saw only the latest file reads and no word of the stage's aim. Every one of its summaries
#: opened "Establish the foundational backend architecture for a FastAPI application", described the product's
#: models, schemas and routes, and ended "Implement remaining FastAPI routers" - nothing of what the stage had found,
#: decided or had left - so after each the stage read the same files again (764 reads of 43 files in one run). The
#: files are in the workspace and the project memory; what a summary loses is what the stage learnt from them.
#: `{messages}` is the one placeholder the summariser fills.
WORK_NOTE_PROMPT = """You keep the work note of one stage of a software build. The stage's conversation below is about to be replaced by your note. The stage goes on from the note, its request and the project's files, which stay in the workspace and which it can read again by line range. A note that describes what the files contain is no use to it. What is lost unless you write it down is what the stage learnt from them, what it chose and what it still has to do.

The first message below names the stage's role and what it was asked to do. Write the note for that aim alone: never work out the aim from the files it read.

Write these four sections, each a short list, with "None" under one that has nothing:

## Found
Each fact the stage's work depends on, with the file and line it came from as `path:line`: a name and its signature, a field and its type, a route and what it answers, a value, the result of a command it ran, an error and where it points.

## Decided
What the stage chose to do and why, and what it ruled out.

## Changed
Each file the stage wrote or changed, and what that file now does.

## Left
What is left of the request, the next step first, each concrete enough to start without reading again. Name a file to read only where the next step needs a line of it that is not under Found.

Do not restate, describe or copy the text of a file that was read. Answer with the note alone.

<messages>
Messages to summarize:
{messages}
</messages>"""

#: The most of the stage's role (its system prompt's opening) and of its request's opening the summariser is shown.
MOST_ROLE_CHARACTERS = 600
MOST_AIM_CHARACTERS = 2_000
#: A tool result or a call's argument longer than this is shown to the summariser as its start and its end: what a
#: command ended with is at its end, and a read file's text is the workspace's, not the note's.
MOST_RESULT_CHARACTERS = 1_200
_RESULT_START = 400
_RESULT_END = 600
MOST_ARGUMENT_CHARACTERS = 300

#: The note a stage's last summary made, kept for a restart of the stage to start from (`carry_over`).
WORK_NOTE = "work_note"
_A_PARAGRAPH = re.compile(r"\n\s*\n")
_THE_WORKSPACE_ROOT = re.compile(r"^The workspace is rooted at [^\n]*\n*")


def role_of(system_prompt: str) -> str:
    """A stage's role as its system prompt opens: its first paragraph, cut at a sentence within
    `MOST_ROLE_CHARACTERS`. "" for none."""
    text = " ".join(_A_PARAGRAPH.split(str(system_prompt or "").strip(), 1)[0].split())
    if len(text) <= MOST_ROLE_CHARACTERS:
        return text
    cut = text[:MOST_ROLE_CHARACTERS]
    end = cut.rfind(". ")
    return cut[:end + 1] if end > MOST_ROLE_CHARACTERS // 3 else cut.rstrip() + " ..."


#: The headings under which a request says what its stage is to do (LF.1466): the work order's ask and the files it
#: owns, the milestone a test round checks and what it changed, a review's work orders, a fixer's defect. Measured on
#: one medium run: the summariser of 6 of 9 stage families was shown the opening of the request as its aim - the
#: builders' "where things stand" and the stack, a test round's stack, a review's brief - and the ask itself, 6,000
#: characters in, never.
_ASK_HEADING = re.compile(
    r"^--- (?:Delegated\b|Files you own\b|Milestone under test\b|Files changed in this milestone\b"
    r"|Work orders in this batch\b|Defect ---)[^\n]*$", re.M)
#: Text before a request's first heading that is this long says the ask itself (a suite writer's "Write its suite").
_AN_OPENING_ASK = 200


def _within(text: str, most: int) -> str:
    text = text.strip()
    if len(text) <= most:
        return text
    return text[:most].rsplit("\n", 1)[0].rstrip() + "\n..."


def aim_of(request: str) -> str:
    """What a stage's request asks of it, within `MOST_AIM_CHARACTERS`; "" for none.

    The sections the request says its ask under (`_ASK_HEADING`), else the text before its first heading when that
    is an ask of its own, else its opening as before."""
    from app.agents.request_budget import sections

    text = _THE_WORKSPACE_ROOT.sub("", str(request or "").strip()).strip()
    parts = sections(text)
    asks = [part.strip() for part in parts if _ASK_HEADING.match(part.strip())]
    if asks:
        shown: list[str] = []
        room = MOST_AIM_CHARACTERS
        for ask in asks:
            if room <= 200:
                break
            shown.append(_within(ask, room))
            room -= len(shown[-1]) + 2
        return "\n\n".join(shown)
    before = parts[0].strip() if parts and not parts[0].lstrip().startswith("--- ") else ""
    if len(before) >= _AN_OPENING_ASK:
        return _within(before, MOST_AIM_CHARACTERS)
    return _within(text, MOST_AIM_CHARACTERS)


def _shortened(text: str) -> str:
    if len(text) <= MOST_RESULT_CHARACTERS:
        return text
    hidden = text[_RESULT_START:-_RESULT_END].count("\n")
    return (text[:_RESULT_START] + f"\n[... {hidden} lines not shown here: what a file holds stays in the "
            "workspace ...]\n" + text[-_RESULT_END:])


def _as_the_summariser_sees_it(message: AnyMessage) -> AnyMessage:
    """`message` with a long tool result shown as its start and end, and a call's long arguments cut: the summariser
    sees the span of the stage's work - what it called, what each call answered - rather than the last few files."""
    if getattr(message, "type", None) == "tool":
        text = _text(message.content)
        return message.model_copy(update={"content": _shortened(text)}) if len(text) > MOST_RESULT_CHARACTERS else message
    if isinstance(message, AIMessage) and message.tool_calls:
        calls = []
        for call in message.tool_calls:
            args = {key: (value[:MOST_ARGUMENT_CHARACTERS] + " ..." if isinstance(value, str)
                          and len(value) > MOST_ARGUMENT_CHARACTERS else value)
                    for key, value in (call.get("args") or {}).items()}
            calls.append({**call, "args": args})
        if calls != message.tool_calls:
            copied = message.model_copy()
            copied.tool_calls = calls
            return copied
    return message


def _keep_the_note(note: str) -> None:
    """The stage's latest work note, for a restart of it (`carry_over.carry_over_note`); nothing outside a graph run."""
    try:
        from app.agents.stage_memory import current_stage_key, store

        if current_stage_key() is not None and note.strip():
            store(WORK_NOTE, {})["note"] = note.strip()
    except Exception:  # noqa: BLE001 - the summary is made either way
        pass


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(block.get("text") or "") if isinstance(block, dict) else str(block) for block in content
        )
    return str(content or "")


def _without_memory(message: AnyMessage) -> str:
    """The message's own words: the project memory, when a call put it in front, is handed over afresh."""
    from app.observability.transcript import MEMORY_CHARS

    text = _text(message.content)
    memory = (getattr(message, "additional_kwargs", None) or {}).get(MEMORY_CHARS)
    return text[memory:] if isinstance(memory, int) and 0 < memory <= len(text) else text


def _files_written(messages: list[AnyMessage]) -> list[str]:
    found: list[str] = []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls or []:
            if call.get("name") not in _WRITING_TOOLS:
                continue
            args = call.get("args") or {}
            path = next((str(args[k]) for k in _PATH_ARGUMENTS if args.get(k)), "")
            if path and path not in found:
                found.append(path)
    return found


#: A line of a read's result as `read_file` numbers it: `    12  ...`, a long line's continuation `    12.1  ...`; the
#: tab of the older `cat -n` gutter too. Measured on one medium run (LF.1399): the read tool had moved to the two
#: spaces, this read the tab alone, and every summary of every stage counted no read - the memory chosen again at a
#: summary held what the stage wrote and what its opening named, never the files it read 6-14 times.
_NUMBERED_LINE = re.compile(r"^[ \t]*(\d+)(?:\.\d+)?(?:\t|  )", re.M)
MOST_FILES_READ_NAMED = 40


def _files_read(messages: list[AnyMessage]) -> dict[str, list[list[int]]]:
    """Each file the messages read, with the line ranges the reads' results showed; a read that returned no numbered
    line (a pointer to the memory, an error) read nothing and is not named."""
    found: dict[str, list[list[int]]] = {}
    for path, ranges in _each_read(messages):
        found.setdefault(path, []).extend(ranges)
    return found


def _reads_in_order(messages: list[AnyMessage]) -> list[list[Any]]:
    """[path, reads] for each file the messages read (a read that returned numbered lines), the latest read last."""
    found: dict[str, int] = {}
    for path, ranges in _each_read(messages):
        found[path] = found.pop(path, 0) + len(ranges)
    return [[path, count] for path, count in found.items()]


def _each_read(messages: list[AnyMessage]) -> list[tuple[str, list[list[int]]]]:
    results = {str(getattr(m, "tool_call_id", "")): _text(m.content) for m in messages
               if getattr(m, "type", None) == "tool"}
    found: list[tuple[str, list[list[int]]]] = []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls or []:
            if call.get("name") != "read_file":
                continue
            args = call.get("args") or {}
            path = str(args.get("file_path") or args.get("path") or "").strip().lstrip("/")
            numbers = [int(n) for n in _NUMBERED_LINE.findall(results.get(str(call.get("id") or ""), ""))]
            if path and numbers:
                found.append((path, [[min(numbers), max(numbers)]]))
    return found


def _merged_reads(earlier: list[list[Any]], later: list[list[Any]]) -> list[list[Any]]:
    counts: dict[str, int] = {}
    for path, count in [*(earlier or []), *(later or [])]:
        counts[str(path)] = counts.pop(str(path), 0) + int(count)
    return [[path, count] for path, count in counts.items()]


def _merged_ranges(*groups: dict[str, list[list[int]]]) -> dict[str, list[list[int]]]:
    merged: dict[str, list[list[int]]] = {}
    for group in groups:
        for path, ranges in (group or {}).items():
            merged.setdefault(str(path), []).extend([int(a), int(b)] for a, b in ranges)
    for path, ranges in merged.items():
        joined: list[list[int]] = []
        for start, end in sorted(ranges):
            if joined and start <= joined[-1][1] + 1:
                joined[-1][1] = max(joined[-1][1], end)
            else:
                joined.append([start, end])
        merged[path] = joined
    return merged


#: How the summary names the files it read that the project memory holds whole (LF.1424).
HELD_READS = ("Of the files this stage has read, the project memory at the start of this conversation holds these "
              "whole and current, so work from there and do not read them again: ")


def files_read_line(files_read: dict[str, list[list[int]]], held: Any = ()) -> str:
    """The summary's line naming what the stage had read before it; "" when it read nothing.

    A file the project memory holds whole (`held`) is named as held, not as gone (LF.1424). Measured on one medium
    run: the line called a fixer's database module "no longer in this conversation" while the memory held it whole,
    the note's next step read "Read database.py", and the fixer asked for it six times running, each answered with a
    pointer to the memory."""
    if not files_read:
        return ""
    kept = {str(path) for path in held or ()}
    named = list(files_read.items())[-MOST_FILES_READ_NAMED:]
    gone = [(path, ranges) for path, ranges in named if path not in kept]
    parts = []
    if gone:
        shown = ", ".join(f"`{path}` (lines " + ", ".join(f"{a}-{b}" if a != b else str(a) for a, b in ranges) + ")"
                          for path, ranges in gone)
        parts.append("Files this stage has read so far, whose text is no longer in this conversation: " + shown + ".")
    whole = [path for path, _ in named if path in kept]
    if whole:
        parts.append(HELD_READS + ", ".join(f"`{path}`" for path in whole) + ".")
    return " ".join(parts)


def with_held_reads_named(messages: list[Any], held: Any) -> list[Any]:
    """`messages` with a summary's line of the files it read naming those the project memory holds whole (`held`) as
    held (LF.1424); `messages` itself when there is no such line or nothing changes. Called by the project memory,
    which knows what it holds on this call."""
    changed = False
    out: list[Any] = []
    for message in messages:
        kwargs = getattr(message, "additional_kwargs", None) or {}
        read = kwargs.get(FILES_READ)
        content = getattr(message, "content", None)
        if getattr(message, "type", None) == "human" and read and isinstance(content, str):
            before, after = files_read_line(read), files_read_line(read, held)
            if before and after != before and before in content:
                message = message.model_copy(update={"content": content.replace(before, after, 1)})
                changed = True
        out.append(message)
    return out if changed else messages


class RequestKeepingSummarization(SummarizationMiddleware):
    """`SummarizationMiddleware` whose summary keeps the request and is never empty."""

    @property
    def name(self) -> str:
        # `create_deep_agent` replaces its own summariser with one of the same
        # name and appends any other: under a name of its own this would be a
        # second summariser beside the default one.
        return "SummarizationMiddleware"

    def __init__(self, *args: Any, most_kept_tokens: int | None = None, usual_trigger_tokens: int | None = None,
                 reply_room: tuple[str, int, int] | None = None, role: str = "", repo_root: str | None = None,
                 fix_stage_trigger_tokens: int | None = None, reply_reserve_tokens: int | None = None,
                 window_tokens: int | None = None, soft_trigger_ratio: float | None = None, **kwargs: Any) -> None:
        # The summary is the stage's work note (PA.2): asked for what was found, decided, changed and is left.
        kwargs.setdefault("summary_prompt", WORK_NOTE_PROMPT)
        super().__init__(*args, **kwargs)
        # The stage's role, as its system prompt opens (`role_of`): the summariser is told whose note it keeps.
        self._role = str(role or "")
        # The trigger without `SUMMARISE_LATER_WITH_HEADROOM`; a request past it and short of the real one is noted.
        self._usual_trigger = usual_trigger_tokens
        # (role, tokens held back for a reply, what they were) when `REPLY_ROOM_SIZED_PER_ROLE` resized them.
        self._reply_room = reply_room
        # The most of the conversation a compaction leaves whole (see
        # `_determine_cutoff_index`); None keeps the message count alone.
        self._most_kept_tokens = most_kept_tokens
        # The workspace, for whether a read's lines are still the file's, and a fix stage's own trigger, both for
        # `FIX_STAGES_STUB_OLD_READS` (`old_reads_stubbed`, LF.1420).
        self._repo_root = repo_root
        self._fix_stage_trigger = fix_stage_trigger_tokens
        # Set while one summary is made, read when its message is built: the
        # two run in turn within one model call.
        self._kept: tuple[str, list[str], int, int, dict[str, list[list[int]]], int, list[list[Any]]] | None = None
        # (refusals, commands) of the whole stage so far, set with `_kept` (`work_note_ledger`, LF.1466).
        self._ledger: tuple[list[str], list[str]] = ([], [])
        # The reply's reserve and the stage's window, for the room a whole request has (`request_fit`, LF.1500).
        self._reply_reserve = reply_reserve_tokens
        self._window = window_tokens
        # The share of the room beside the measured opening a request may fill before it is summarised (LF.1606).
        if soft_trigger_ratio is None:
            from app.agents.context_budget import SOFT_TRIGGER_RATIO

            soft_trigger_ratio = SOFT_TRIGGER_RATIO
        self._soft_ratio = float(soft_trigger_ratio)
        # How many messages the last cutoff left whole, set where it is chosen and kept on its summary (LF.1499).
        self._kept_tail: int | None = None

    def _prepare(self, messages: list[AnyMessage]) -> list[AnyMessage]:
        """What the summariser is handed; records the request and the files for the message."""
        self._kept = None
        request, files, earlier, rest = "", [], "", list(messages)
        calls = lost = summaries = 0
        read: dict[str, list[list[int]]] = {}
        reads: list[list[Any]] = []
        refused: list[str] = []
        ran: list[str] = []
        if rest and getattr(rest[0], "type", None) == "human" and self._is_summary_message(rest[0]):
            kwargs = rest[0].additional_kwargs or {}
            request = str(kwargs.get(KEPT_REQUEST) or "")
            files = list(kwargs.get(FILES_WRITTEN) or [])
            earlier = str(kwargs.get(SUMMARY) or "")
            calls = int(kwargs.get(CALLS_BEFORE) or 0)
            lost = int(kwargs.get(LOST_BEFORE) or 0)
            summaries = int(kwargs.get(SUMMARIES) or 0)
            read = dict(kwargs.get(FILES_READ) or {})
            reads = list(kwargs.get(READS) or [])
            refused = list(kwargs.get(REFUSALS) or [])
            ran = list(kwargs.get(COMMANDS) or [])
            rest = rest[1:]
        else:
            # The stage's whole opening turn, every message of it before the
            # model's first reply: measured live, a stage opens with the files
            # as they stood, then the defect it is to fix - and keeping only
            # the first message kept the files and lost the defect.
            turn = 0
            while turn < len(rest) and getattr(rest[turn], "type", None) in ("human", "system"):
                turn += 1
            opening = [_without_memory(m) for m in rest[:turn] if getattr(m, "type", None) == "human"]
            carried: list[str] = []
            for text in reversed(opening):
                if carried and sum(map(len, carried)) + len(text) > MOST_CARRIED_CHARACTERS:
                    continue
                carried.insert(0, text)
            request = "\n\n".join(carried)
            rest = rest[turn:]
        written_now = _files_written(rest)
        for path in written_now:
            if path not in files:
                files.append(path)
        from app.agents import work_note_ledger

        refused = work_note_ledger.merged(work_note_ledger.settled(refused, written_now), work_note_ledger.refusals(rest),
                                          work_note_ledger.MOST_REFUSALS)
        ran = work_note_ledger.merged(ran, work_note_ledger.commands(rest), work_note_ledger.MOST_COMMANDS)
        self._ledger = (refused, ran)
        calls += sum(1 for message in rest if getattr(message, "type", None) == "ai")
        from app.agents.settled_answer import _replies_that_were_all_reasoning

        lost += _replies_that_were_all_reasoning(rest)
        self._kept = (request, files[-MOST_FILES_NAMED:], calls, lost, _merged_ranges(read, _files_read(rest)),
                      summaries + 1, _merged_reads(reads, _reads_in_order(rest)))

        # Whose note it is and what the stage is for (PA.2): without them the summariser guessed the aim from the
        # files the stage had read.
        said = []
        if self._role:
            said.append(f"The stage's role: {self._role}")
        aim = aim_of(request)
        if aim:
            said.append("What the stage was asked to do (the opening of its request, which stays in front of it):\n"
                        + aim)
        if earlier:
            said.append(f"The stage's work note before this part of its work:\n{earlier}")
        # What the harness knows from the tool calls (LF.1466): the note names every file written and keeps what the
        # tools refused, whatever this part of the conversation shows.
        ledger = work_note_ledger.for_the_summariser(files[-MOST_FILES_NAMED:], written_now, refused, ran)
        if ledger:
            said.append(ledger)
        said.append(_THE_WORK_SO_FAR)
        opening = HumanMessage(content="\n\n".join(said))
        shown = [_as_the_summariser_sees_it(message) for message in rest]
        budget = getattr(self._lc_helper, "trim_tokens_to_summarize", None)
        if budget is None:
            return [opening, *shown]
        room = budget - self.token_counter([opening])
        if room <= 0:
            return [opening]
        latest = trim_messages(
            shown, max_tokens=room, token_counter=self.token_counter, strategy="last", allow_partial=True,
        )
        return [opening, *latest]

    def _determine_cutoff_index(self, messages: list[AnyMessage]) -> int:
        """Where the summarised part ends: the kept tail as configured, cut to `most_kept_tokens`.

        The tail is kept by count, and a count of messages is no measure of
        their size. Measured live: a fix stage's last fifteen messages held three
        file reads, the request after each compaction was still at or above the
        trigger - the project memory and the request are re-sent whole and only
        the conversation can shrink - and it compacted eight times in 26
        minutes, re-reading the same files after each. Cut only before a model
        message, so no tool call is parted from its result, and keep at least
        `MOST_KEPT_FEWEST` messages.
        """
        cutoff = super()._determine_cutoff_index(messages)
        cap = self._most_kept_tokens
        summarised = bool(messages) and getattr(messages[0], "type", None) == "human" \
            and self._is_summary_message(messages[0])
        if cap and cutoff <= 0 and summarised and len(messages) > MOST_KEPT_FEWEST + 1:
            # A summarised conversation no longer than the kept count (LF.1499): by count alone nothing could be
            # summarised again until 15 messages followed the summary's own short tail, however large they were.
            cutoff = 1
        if cap and cutoff > 0:
            while len(messages) - cutoff > MOST_KEPT_FEWEST and self.token_counter(messages[cutoff:]) > cap:
                moved = cutoff + 1
                while moved < len(messages) and getattr(messages[moved], "type", None) == "tool":
                    moved += 1
                if len(messages) - moved < MOST_KEPT_FEWEST:
                    break
                cutoff = moved
        if summarised and cutoff == 1:
            cutoff = 0  # nothing but the summary itself before the tail
        self._kept_tail = len(messages) - cutoff if cutoff > 0 else None
        return cutoff

    def _truncate_args(self, messages: list[AnyMessage], total_tokens: int) -> tuple[list[AnyMessage], bool]:
        """Old calls' long arguments shortened, and - with `OBSERVATION_FOLDING` - old long results folded.

        Both only once the conversation reaches the argument trigger, so a small
        stage is sent as it is. Behind a boundary that moves `FOLD_STEP`
        messages at a time (`observation_folding.boundary`), so what is
        shortened stays the same, and cached, between steps.
        """
        from app.agents import observation_folding, old_reads_stubbed

        stubbing = old_reads_stubbed.applies_here()
        stubbed = False
        if stubbing:
            # A fix stage's old reads as one-line notes, in place of folding every long result (LF.1420).
            messages, stubbed = self._with_old_reads_stubbed(messages, total_tokens)
        if not self._should_truncate_args(messages, total_tokens):
            return messages, stubbed
        # deepagents' "every message is recent, shorten nothing" (LF.1465): a conversation of at most its kept count
        # gets `len(messages)` back, and the boundary of that is not a cutoff. Measured on one medium run: from 10 to
        # 15 messages - where every stage sits after a summary on a 93K slot - the first ten were folded, and 294
        # reads in four runs reached the model as their first six lines before it had seen them once.
        kept_from = self._determine_truncate_cutoff_index(messages)
        if kept_from >= len(messages):
            return messages, stubbed
        cutoff = observation_folding.boundary(kept_from)
        if cutoff <= 0:
            return messages, stubbed
        shortened: list[AnyMessage] = []
        modified = False
        for index, message in enumerate(messages):
            if index < cutoff and isinstance(message, AIMessage) and message.tool_calls:
                calls = [self._truncate_tool_call(call) if call.get("name") in _ARGUMENTS_SHORTENED else call
                         for call in message.tool_calls]
                if calls != message.tool_calls:
                    message = message.model_copy()
                    message.tool_calls = calls
                    modified = True
            shortened.append(message)
        modified = modified or stubbed
        if observation_folding.enabled() and not stubbing:
            # Never a result no model reply follows: the model has not seen it yet (LF.1465).
            last_reply = max((i for i, m in enumerate(shortened) if isinstance(m, AIMessage)), default=0)
            shortened, folded = observation_folding.fold(shortened, min(cutoff, last_reply))
            if folded:
                modified = True
                observation_folding.a_read_was_folded(sum(
                    1 for m in shortened[:cutoff] if observation_folding.FOLDED in str(getattr(m, "content", ""))
                ))
        return (shortened, True) if modified else (messages, False)

    def _the_trigger(self) -> int | None:
        """The token trigger for this call: a fix stage's own under `FIX_STAGES_STUB_OLD_READS`, else the configured."""
        from app.agents import old_reads_stubbed

        trigger = getattr(self._lc_helper, "trigger", None)
        usual = int(trigger[1]) if isinstance(trigger, tuple) and len(trigger) == 2 and trigger[0] == "tokens" else None
        return old_reads_stubbed.trigger_here(usual, self._fix_stage_trigger)

    def _with_old_reads_stubbed(self, messages: list[AnyMessage], total_tokens: int) -> tuple[list[AnyMessage], bool]:
        """A fix stage's reads shown again later made one-line notes, and at its trigger every read before the kept
        tail too (`old_reads_stubbed`, LF.1420)."""
        from app.agents import observation_folding, old_reads_stubbed

        trigger = self._the_trigger()
        before = 0
        if trigger and total_tokens >= trigger:
            before = observation_folding.boundary(min(self._determine_cutoff_index(messages), len(messages)))
        out, repeated, masked = old_reads_stubbed.stubbed(messages, self._repo_root, before)
        old_reads_stubbed.note(repeated, masked)
        return (out, True) if repeated or masked else (messages, False)

    def _should_summarize(self, messages: list[AnyMessage], total_tokens: int) -> bool:
        if self._reply_room:
            from app.agents import reply_room
            from app.observability.transcript import _stage_from_config

            reply_room.note(_stage_from_config(""), *self._reply_room)
        if self._past_the_room(messages):
            # The next request would not fit the slot (LF.1500): compacted now, whatever the triggers below say.
            return True
        trigger = getattr(self._lc_helper, "trigger", None)
        configured = int(trigger[1]) if isinstance(trigger, tuple) and len(trigger) == 2 else None
        own = self._the_trigger()
        later = self._past_the_opening(messages, own if own is not None else configured)
        if later is not None:
            # Past the stage's measured opening, within the room its request has (LF.1606).
            if later.upcoming < later.trigger:
                from app.agents import summary_trigger
                from app.observability.transcript import _stage_from_config

                if configured and later.upcoming >= configured:
                    summary_trigger.note_kept_whole(_stage_from_config(""), later, configured)
                return False
        elif own is not None and own != configured:
            # A fix stage's own trigger (LF.1420): past it only when its old reads, already notes, left it there.
            if total_tokens < own:
                return False
        elif not super()._should_summarize(messages, total_tokens):
            usual = self._usual_trigger
            trigger = getattr(self._lc_helper, "trigger", None)
            if usual and isinstance(trigger, tuple) and len(trigger) == 2 and trigger[1] > usual <= total_tokens:
                from app.agents import summarise_later
                from app.observability.transcript import _stage_from_config

                summarise_later.note_kept_whole(_stage_from_config(""), total_tokens, usual, int(trigger[1]))
            return False
        if messages and getattr(messages[0], "type", None) == "human" and self._is_summary_message(messages[0]):
            # Past the tail this summary really kept (LF.1499). Measured on one fast run: the tail was cut to its
            # token share, three messages, but the count stood at the 15 configured, so 23 messages - ten calls -
            # had to follow before another summary; the stage went from 54,263 to 81,370 reported tokens unsummarised
            # and its next request was refused by a 93,184-token slot.
            kept = (messages[0].additional_kwargs or {}).get(KEPT_TAIL)
            if not isinstance(kept, int):
                keep = getattr(self._lc_helper, "keep", None)
                kept = keep[1] if isinstance(keep, tuple) and len(keep) == 2 and keep[0] == "messages" else 0
            if len(messages) - 1 < int(kept) + NEW_MESSAGES_BEFORE_COMPACTING_AGAIN:
                return False
        return True

    def _reserve(self) -> int | None:
        """The tokens held back for this call's reply: a fix stage's smaller cap where its own trigger counts on it."""
        if self._fix_stage_trigger and self._the_trigger() == self._fix_stage_trigger:
            # A fix stage's replies are capped smaller, and its own trigger already counts on that (LF.1420).
            from app.models import FIX_STAGE_REPLY_TOKENS

            return FIX_STAGE_REPLY_TOKENS
        return self._reply_reserve

    def _past_the_opening(self, messages: list[AnyMessage], usual: int | None) -> Any:
        """The trigger past this conversation's measured opening (`summary_trigger`, LF.1606) when it is later than
        `usual`, else None: the configured trigger, measured against a framing of 6,000 tokens, sits inside an opening
        of 35,000-40,000 and left a stage about 8,000 tokens of conversation between summaries."""
        if not usual:
            return None
        from app.agents import summary_trigger

        found = summary_trigger.measured(messages, reserve=self._reserve(), window=self._window,
                                         ratio=self._soft_ratio)
        return found if found is not None and found.trigger > usual else None

    def _past_the_room(self, messages: list[AnyMessage]) -> bool:
        """Whether the next request - the last reply's server-reported tokens and the messages since - would pass
        the room the slot leaves once the reply's reserve is held back (`request_fit`, LF.1500), and summarising
        what lies before the kept tail could bring it back: when the framing alone fills the room, a summary on every
        call would gain nothing, and the client's guard cuts the results instead."""
        from app.models import request_fit

        try:
            room = request_fit.room_tokens(self._reserve(), window=self._window)
            upcoming = request_fit.next_request_tokens(messages)
            if not room or not upcoming or upcoming <= room * request_fit.MARGIN:
                return False
            cutoff = self._determine_cutoff_index(messages)
            first = 1 if messages and self._is_summary_message(messages[0]) else 0
            older = sum(request_fit.message_chars(m) for m in messages[first:max(cutoff, first)])
            return older / request_fit.chars_per_token() >= upcoming - room * request_fit.MARGIN
        except Exception:  # noqa: BLE001 - the triggers as configured
            return False

    def _create_summary(self, messages_to_summarize: list[AnyMessage]) -> str:
        return super()._create_summary(self._prepare(messages_to_summarize))

    async def _acreate_summary(self, messages_to_summarize: list[AnyMessage]) -> str:
        return await super()._acreate_summary(self._prepare(messages_to_summarize))

    def _build_new_messages_with_path(self, summary: str, file_path: str | None) -> list[AnyMessage]:
        # The tool results the stage read are summarised away, so a read of the
        # same lines after this is not a repeat. Measured on one gate run: 40 of
        # 57 reads counted as redundant came after a compaction, each told "this
        # returned nothing you did not already have" about text it no longer had.
        try:
            from app.agents.stage_memory import forget
            from app.agents.workspace_backend import WHAT_THE_CONVERSATION_WAS_GIVEN

            forget(*WHAT_THE_CONVERSATION_WAS_GIVEN)
        except Exception:  # noqa: BLE001 - the summary is made either way
            pass
        if self._kept:
            # The note checked against the tool calls and the workspace before it is kept (LF.1466).
            from app.agents import work_note_ledger

            summary = work_note_ledger.checked(work_note_ledger.with_every_file_written(summary, self._kept[1]),
                                               self._repo_root)
        built = super()._build_new_messages_with_path(summary, file_path)
        kept, self._kept = self._kept, None
        kept_tail, self._kept_tail = self._kept_tail, None
        refused, ran = self._ledger
        if not kept or not built:
            return built
        request, files, calls, lost, read, summaries, reads = kept
        # The note is what a restart of the stage starts from too (PA.2, `carry_over`).
        _keep_the_note(summary)
        # What the stage was reading and writing, for its project memory to hold whole from the next call (LF.1288).
        try:
            from app.agents.project_memory import a_summary_was_made

            a_summary_was_made(files, reads)
        except Exception:  # noqa: BLE001 - the summary is made either way
            pass
        message = built[0]
        parts = []
        if request:
            parts.append(
                "The request this stage was given, which still stands (the conversation after it is "
                "summarised below):\n\n" + request.rstrip() + "\n\n---\n"
            )
        parts.append(_text(message.content))
        if files:
            parts.append("Files this stage has written or changed so far: " + ", ".join(f"`{p}`" for p in files) + ".")
        if read:
            # What it covered, so a stage that still reads past its room is told so (LF.1285).
            parts.append(files_read_line(read))
        from app.agents import work_note_ledger

        ledger = work_note_ledger.for_the_stage(refused, ran)
        if ledger:
            parts.append(ledger)
        return [HumanMessage(
            content="\n\n".join(parts),
            additional_kwargs={
                **(message.additional_kwargs or {}),
                KEPT_REQUEST: request,
                FILES_WRITTEN: files,
                SUMMARY: summary,
                CALLS_BEFORE: calls,
                LOST_BEFORE: lost,
                FILES_READ: read,
                SUMMARIES: summaries,
                READS: reads,
                REFUSALS: refused,
                COMMANDS: ran,
                **({KEPT_TAIL: kept_tail} if isinstance(kept_tail, int) else {}),
            },
        )]


__all__ = ["CALLS_BEFORE", "COMMANDS", "KEPT_TAIL", "FILES_READ", "READS", "REFUSALS", "LOST_BEFORE", "SUMMARIES", "files_read_line", "KEPT_TAIL_SHARE",
           "HELD_READS", "with_held_reads_named",
           "RequestKeepingSummarization", "KEPT_REQUEST", "FILES_WRITTEN", "WORK_NOTE", "WORK_NOTE_PROMPT", "aim_of",
           "role_of"]
