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
#: calls later; a request too large for the window is still compacted at once
#: (the summariser's own overflow fallback).
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
MOST_AIM_CHARACTERS = 1_500
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


def aim_of(request: str) -> str:
    """The opening of a stage's request, as its aim is said there, within `MOST_AIM_CHARACTERS`; "" for none."""
    text = _THE_WORKSPACE_ROOT.sub("", str(request or "").strip()).strip()
    if len(text) <= MOST_AIM_CHARACTERS:
        return text
    return text[:MOST_AIM_CHARACTERS].rsplit("\n", 1)[0].rstrip() + "\n..."


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


def files_read_line(files_read: dict[str, list[list[int]]]) -> str:
    """The summary's line naming what the stage had read before it; "" when it read nothing."""
    if not files_read:
        return ""
    named = list(files_read.items())[-MOST_FILES_READ_NAMED:]
    shown = ", ".join(f"`{path}` (lines " + ", ".join(f"{a}-{b}" if a != b else str(a) for a, b in ranges) + ")"
                      for path, ranges in named)
    return ("Files this stage has read so far, whose text is no longer in this conversation: " + shown + ".")


class RequestKeepingSummarization(SummarizationMiddleware):
    """`SummarizationMiddleware` whose summary keeps the request and is never empty."""

    @property
    def name(self) -> str:
        # `create_deep_agent` replaces its own summariser with one of the same
        # name and appends any other: under a name of its own this would be a
        # second summariser beside the default one.
        return "SummarizationMiddleware"

    def __init__(self, *args: Any, most_kept_tokens: int | None = None, usual_trigger_tokens: int | None = None,
                 reply_room: tuple[str, int, int] | None = None, role: str = "", **kwargs: Any) -> None:
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
        # Set while one summary is made, read when its message is built: the
        # two run in turn within one model call.
        self._kept: tuple[str, list[str], int, int, dict[str, list[list[int]]], int, list[list[Any]]] | None = None

    def _prepare(self, messages: list[AnyMessage]) -> list[AnyMessage]:
        """What the summariser is handed; records the request and the files for the message."""
        self._kept = None
        request, files, earlier, rest = "", [], "", list(messages)
        calls = lost = summaries = 0
        read: dict[str, list[list[int]]] = {}
        reads: list[list[Any]] = []
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
        for path in _files_written(rest):
            if path not in files:
                files.append(path)
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
        if not cap or cutoff <= 0:
            return cutoff
        while len(messages) - cutoff > MOST_KEPT_FEWEST and self.token_counter(messages[cutoff:]) > cap:
            moved = cutoff + 1
            while moved < len(messages) and getattr(messages[moved], "type", None) == "tool":
                moved += 1
            if len(messages) - moved < MOST_KEPT_FEWEST:
                break
            cutoff = moved
        return cutoff

    def _truncate_args(self, messages: list[AnyMessage], total_tokens: int) -> tuple[list[AnyMessage], bool]:
        """Old calls' long arguments shortened, and - with `OBSERVATION_FOLDING` - old long results folded.

        Both only once the conversation reaches the argument trigger, so a small
        stage is sent as it is. Behind a boundary that moves `FOLD_STEP`
        messages at a time (`observation_folding.boundary`), so what is
        shortened stays the same, and cached, between steps.
        """
        from app.agents import observation_folding

        if not self._should_truncate_args(messages, total_tokens):
            return messages, False
        cutoff = observation_folding.boundary(min(self._determine_truncate_cutoff_index(messages), len(messages)))
        if cutoff <= 0:
            return messages, False
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
        if observation_folding.enabled():
            shortened, folded = observation_folding.fold(shortened, cutoff)
            if folded:
                modified = True
                observation_folding.a_read_was_folded(sum(
                    1 for m in shortened[:cutoff] if observation_folding.FOLDED in str(getattr(m, "content", ""))
                ))
        return (shortened, True) if modified else (messages, False)

    def _should_summarize(self, messages: list[AnyMessage], total_tokens: int) -> bool:
        if self._reply_room:
            from app.agents import reply_room
            from app.observability.transcript import _stage_from_config

            reply_room.note(_stage_from_config(""), *self._reply_room)
        if not super()._should_summarize(messages, total_tokens):
            usual = self._usual_trigger
            trigger = getattr(self._lc_helper, "trigger", None)
            if usual and isinstance(trigger, tuple) and len(trigger) == 2 and trigger[1] > usual <= total_tokens:
                from app.agents import summarise_later
                from app.observability.transcript import _stage_from_config

                summarise_later.note_kept_whole(_stage_from_config(""), total_tokens, usual, int(trigger[1]))
            return False
        if messages and getattr(messages[0], "type", None) == "human" and self._is_summary_message(messages[0]):
            keep = getattr(self._lc_helper, "keep", None)
            kept = keep[1] if isinstance(keep, tuple) and len(keep) == 2 and keep[0] == "messages" else 0
            if len(messages) - 1 < int(kept) + NEW_MESSAGES_BEFORE_COMPACTING_AGAIN:
                return False
        return True

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
        built = super()._build_new_messages_with_path(summary, file_path)
        kept, self._kept = self._kept, None
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
            },
        )]


__all__ = ["CALLS_BEFORE", "FILES_READ", "READS", "LOST_BEFORE", "SUMMARIES", "files_read_line", "KEPT_TAIL_SHARE",
           "RequestKeepingSummarization", "KEPT_REQUEST", "FILES_WRITTEN", "WORK_NOTE", "WORK_NOTE_PROMPT", "aim_of",
           "role_of"]
