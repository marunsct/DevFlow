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

#: The tools that change a file, and the argument naming it.
_WRITING_TOOLS = frozenset({
    "write_artifact", "edit_artifact", "replace_lines", "replace_approved_lines",
    "move_artifact", "delete_artifact",
})
_PATH_ARGUMENTS = ("relative_path", "path", "file_path")

MOST_FILES_NAMED = 40

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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Set while one summary is made, read when its message is built: the
        # two run in turn within one model call.
        self._kept: tuple[str, list[str]] | None = None

    def _prepare(self, messages: list[AnyMessage]) -> list[AnyMessage]:
        """What the summariser is handed; records the request and the files for the message."""
        self._kept = None
        request, files, earlier, rest = "", [], "", list(messages)
        if rest and getattr(rest[0], "type", None) == "human" and self._is_summary_message(rest[0]):
            kwargs = rest[0].additional_kwargs or {}
            request = str(kwargs.get(KEPT_REQUEST) or "")
            files = list(kwargs.get(FILES_WRITTEN) or [])
            earlier = str(kwargs.get(SUMMARY) or "")
            rest = rest[1:]
        else:
            # The stage's whole opening turn, every message of it before the
            # model's first reply: measured live, a stage opens with the files
            # as they stood, then the defect it is to fix - and keeping only
            # the first message kept the files and lost the defect.
            turn = 0
            while turn < len(rest) and getattr(rest[turn], "type", None) in ("human", "system"):
                turn += 1
            request = "\n\n".join(
                _without_memory(message) for message in rest[:turn] if getattr(message, "type", None) == "human"
            )
            rest = rest[turn:]
        for path in _files_written(rest):
            if path not in files:
                files.append(path)
        self._kept = (request, files[-MOST_FILES_NAMED:])

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

    def _create_summary(self, messages_to_summarize: list[AnyMessage]) -> str:
        return super()._create_summary(self._prepare(messages_to_summarize))

    async def _acreate_summary(self, messages_to_summarize: list[AnyMessage]) -> str:
        return await super()._acreate_summary(self._prepare(messages_to_summarize))

    def _build_new_messages_with_path(self, summary: str, file_path: str | None) -> list[AnyMessage]:
        built = super()._build_new_messages_with_path(summary, file_path)
        kept, self._kept = self._kept, None
        if not kept or not built:
            return built
        request, files = kept
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
            },
        )]


__all__ = ["RequestKeepingSummarization", "KEPT_REQUEST", "FILES_WRITTEN"]
