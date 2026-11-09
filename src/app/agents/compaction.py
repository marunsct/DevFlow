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


class RequestKeepingSummarization(SummarizationMiddleware):
    """`SummarizationMiddleware` whose summary keeps the request and is never empty."""

    @property
    def name(self) -> str:
        # `create_deep_agent` replaces its own summariser with one of the same
        # name and appends any other: under a name of its own this would be a
        # second summariser beside the default one.
        return "SummarizationMiddleware"

    def __init__(self, *args: Any, most_kept_tokens: int | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # The most of the conversation a compaction leaves whole (see
        # `_determine_cutoff_index`); None keeps the message count alone.
        self._most_kept_tokens = most_kept_tokens
        # Set while one summary is made, read when its message is built: the
        # two run in turn within one model call.
        self._kept: tuple[str, list[str], int, int] | None = None

    def _prepare(self, messages: list[AnyMessage]) -> list[AnyMessage]:
        """What the summariser is handed; records the request and the files for the message."""
        self._kept = None
        request, files, earlier, rest = "", [], "", list(messages)
        calls = lost = 0
        if rest and getattr(rest[0], "type", None) == "human" and self._is_summary_message(rest[0]):
            kwargs = rest[0].additional_kwargs or {}
            request = str(kwargs.get(KEPT_REQUEST) or "")
            files = list(kwargs.get(FILES_WRITTEN) or [])
            earlier = str(kwargs.get(SUMMARY) or "")
            calls = int(kwargs.get(CALLS_BEFORE) or 0)
            lost = int(kwargs.get(LOST_BEFORE) or 0)
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
        self._kept = (request, files[-MOST_FILES_NAMED:], calls, lost)

        opening = HumanMessage(
            content=_THE_WORK_SO_FAR + (f"\n\nThe summary of the work before it:\n{earlier}" if earlier else "")
        )
        budget = getattr(self._lc_helper, "trim_tokens_to_summarize", None)
        if budget is None:
            return [opening, *rest]
        room = budget - self.token_counter([opening])
        if room <= 0:
            return [opening]
        latest = trim_messages(
            rest, max_tokens=room, token_counter=self.token_counter, strategy="last", allow_partial=True,
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
        if not super()._should_summarize(messages, total_tokens):
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
        request, files, calls, lost = kept
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
        return [HumanMessage(
            content="\n\n".join(parts),
            additional_kwargs={
                **(message.additional_kwargs or {}),
                KEPT_REQUEST: request,
                FILES_WRITTEN: files,
                SUMMARY: summary,
                CALLS_BEFORE: calls,
                LOST_BEFORE: lost,
            },
        )]


__all__ = ["CALLS_BEFORE", "LOST_BEFORE", "KEPT_TAIL_SHARE", "RequestKeepingSummarization", "KEPT_REQUEST", "FILES_WRITTEN"]
