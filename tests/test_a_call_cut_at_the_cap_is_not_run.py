"""A work call cut off at the reply cap is answered, not run, and a call read leniently keeps its text as sent.

Measured on one run's backend builder: a reply wrote 123,226 characters of analysis (a `</think>` inside its text),
then a `write_artifact` call, and ended at its 32,000-token cap 2,701 characters into the file's `content`. The
lenient reading closed the open string and object and the call ran: a truncated file, with every line break of the
source gone ("// Express application configuration.//// This module..."), was sent to the tool, and only an
ownership refusal kept it off the project's source. The fixtures are that reply's shape, shortened.
"""

from __future__ import annotations

import json
import re
import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel

from app.agents.settled_answer import build_settled_answer_middleware
from app.models.tool_arguments import decode_structured_arguments

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

#: The start of the file the builder wrote, as it meant it.
SOURCE = (
    "// Express application configuration.\n//\n"
    "// This module builds the service: the JSON interface under /api, and the page\n"
    "// from public/.  `src/index.js` starts it; unit tests call createApp() directly.\n//\n"
    "// Routes:\n//   GET    /api/health          → 200 { status: 'ok' }\n"
    "import express from 'express';\n"
    'const greeting = "say \\"hi\\"";\n\n'
    "export function createApp() {\n  const app = express();\n"
    "  // GET /api/bookmarks — list all bookmarks newest first.\n  // Calls loadBookmarks()"
)
#: The analysis the reply ran on through before its call, a closing `</think>` inside it.
ANALYSIS = (
    "Now I have a clear picture. Let me analyze what's needed:\n\n"
    + "So either Express sets the type from the body, or the helper passes the headers. I think option 1. " * 40
    + "\nOK, I'm going to stop analyzing and start implementing.\n</think>\n\nLet me implement all changes:"
)


def write_artifact(relative_path: str, content: str) -> str:
    """Write a file of the project."""
    return "written"


def _the_server_s_arguments(arguments: dict[str, str], cut_at: str) -> str:
    """The argument text as the server sent it: JSON, escapes and all, stopped where `cut_at` begins."""
    text = json.dumps(arguments)
    return text[: text.index(cut_at)]


def _reply(arguments: str, *, capped: bool, name: str = "write_artifact", call_id: str = "call_1") -> ChatResult:
    """A reply whose one call the client could not parse (an invalid call), cut at the cap or ended on its own."""
    finish = {"finish_reason": "length" if capped else "tool_calls"}
    message = AIMessage(
        content=ANALYSIS,
        response_metadata=dict(finish),
        invalid_tool_calls=[{"name": name, "args": arguments, "id": call_id, "error": "Unterminated string",
                             "type": "invalid_tool_call"}],
    )
    return ChatResult(generations=[ChatGeneration(message=message, generation_info=dict(finish))])


class SpecialistAnswer(BaseModel):
    summary: str


@dataclass
class ToolRequest:
    tool_call: dict[str, Any]
    state: Any = None
    runtime: Any = None


def _what_the_stage_is_given(result: ChatResult) -> tuple[list[dict[str, Any]], list[Any]]:
    """The reply's calls as the stage's tools are reached with them: (the calls the tool ran, what each call got)."""
    decode_structured_arguments(result, [convert_to_openai_tool(write_artifact)])
    middleware = build_settled_answer_middleware(SpecialistAnswer, "specialist_backend_0")
    ran: list[dict[str, Any]] = []

    def tool(request: Any) -> ToolMessage:
        ran.append(request.tool_call)
        return ToolMessage(content="written", tool_call_id=request.tool_call["id"], name=request.tool_call["name"])

    answers = [middleware.wrap_tool_call(ToolRequest(tool_call=call), tool)
               for call in result.generations[0].message.tool_calls]
    return ran, answers


def test_a_write_cut_off_at_the_cap_is_answered_without_being_run() -> None:
    arguments = _the_server_s_arguments({"relative_path": "bookmarks/src/app.js", "content": SOURCE},
                                        "  // GET /api/bookmarks")

    ran, (answer,) = _what_the_stage_is_given(_reply(arguments, capped=True))

    assert ran == []
    assert answer.status == "error"
    assert "`content`" in answer.content and "not run" in answer.content and "Nothing was changed" in answer.content
    assert "smaller pieces" in answer.content


def test_a_cut_off_call_keeps_the_fields_that_arrived_whole_and_not_the_one_it_stopped_in() -> None:
    """What the next request shows of the call: its path, not 2,700 characters of a file that stops mid-line."""
    arguments = _the_server_s_arguments({"relative_path": "bookmarks/src/app.js", "content": SOURCE},
                                        "  // GET /api/bookmarks")
    result = _reply(arguments, capped=True)

    decode_structured_arguments(result, [convert_to_openai_tool(write_artifact)])

    (call,) = result.generations[0].message.tool_calls
    assert call["name"] == "write_artifact"
    assert call["args"]["relative_path"] == "bookmarks/src/app.js"
    assert "content" not in call["args"]


def test_a_call_whose_last_bracket_alone_is_missing_runs_with_its_line_breaks_and_quotes() -> None:
    """Not at the cap, every value whole, only the closing brace lost: read leniently and run, its text as sent."""
    arguments = json.dumps({"relative_path": "bookmarks/src/app.js", "content": SOURCE})[:-1]

    ran, _ = _what_the_stage_is_given(_reply(arguments, capped=False))

    (call,) = ran
    assert call["args"]["content"] == SOURCE


def test_an_answer_cut_off_keeps_the_line_breaks_of_the_fields_that_arrived_whole() -> None:
    """The kept fields of a cut-off answer are joined to the rest when it comes: they must be the text that was sent."""
    class Report(BaseModel):
        notes: str
        files: list[str]

    arguments = '{"notes": ' + json.dumps("first line\nsecond \"quoted\" line\\path") + ', "files": ["a.js", "b'
    result = _reply(arguments, capped=False, name="Report")

    decode_structured_arguments(result, [convert_to_openai_tool(Report)])

    (call,) = result.generations[0].message.tool_calls
    assert call["args"]["notes"] == 'first line\nsecond "quoted" line\\path'


def test_a_later_whole_write_to_another_file_is_not_joined_to_a_cut_off_one() -> None:
    """A cut-off write's fields are never held over and merged into the stage's next call of the same tool."""
    first = _reply('{"relative_path": "src/a.js", "content": "x", "mode": ', capped=False, call_id="call_1")
    decode_structured_arguments(first, [convert_to_openai_tool(write_artifact)])
    second = AIMessage(content="", tool_calls=[{"name": "write_artifact", "id": "call_2",
                                                "args": {"relative_path": "src/b.js", "content": "y"}}])
    result = ChatResult(generations=[ChatGeneration(message=second)])

    decode_structured_arguments(result, [convert_to_openai_tool(write_artifact)])

    (call,) = result.generations[0].message.tool_calls
    assert call["args"] == {"relative_path": "src/b.js", "content": "y"}


def test_what_a_cut_off_call_is_answered_with_uses_none_of_the_banned_words() -> None:
    arguments = _the_server_s_arguments({"relative_path": "bookmarks/src/app.js", "content": SOURCE}, "import")

    _, (answer,) = _what_the_stage_is_given(_reply(arguments, capped=True))

    assert not BANNED.search(answer.content)


def test_the_effects_report_counts_a_cut_off_call_answered_unrun() -> None:
    effects = runpy.run_path(str(Path(__file__).resolve().parent.parent / "scripts" / "loop" / "effects.py"))["effects"]
    arguments = _the_server_s_arguments({"relative_path": "bookmarks/src/app.js", "content": SOURCE}, "import")
    _, (answer,) = _what_the_stage_is_given(_reply(arguments, capped=True))

    lines = "\n".join(effects([{"kind": "tool_result", "content": answer.content}], ""))

    assert "   1  LF.1608 a work call cut off before its arguments were whole" in lines
