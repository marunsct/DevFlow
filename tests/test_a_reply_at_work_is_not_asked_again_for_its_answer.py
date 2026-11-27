"""A reply that called a tool which ran is the stage at work, not an answer in prose (LF.1624).

Measured on a C# run: fixers' replies that quoted a code fence of the product before reading a file or running the
tests were read as a Markdown answer "where the schema was expected". Each was asked again of the model with no tools
and only the answer's schema allowed - a call of 40 seconds to 4 minutes that the transcript did not show, four times
in two fix stages, about eleven minutes the timing read as neither model nor tool busy - and the next request told a
stage in the middle of its work "the work is done, do not call any more tools".
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel

from app.agents.settled_answer import build_settled_answer_middleware

PROSE_WITH_A_FENCE = ("Now I understand the defect. Line 39 has:\n\n```csharp\ncatch (Exception ex) when "
                      "(ex.Message.Contains(\"lock\"))\n```\n\nLet me run the unit tests.")


class Fix(BaseModel):
    changed_files: list[str] = []
    summary: str = ""


class _Server:
    """The model server's chat completions: what was sent to it, outside the stage's own calls."""

    def __init__(self):
        self.sent = []

    def create(self, **payload):
        self.sent.append(payload)
        return {"choices": [{"message": {"content": '{"changed_files": [], "summary": "done"}'}}]}


class _Request:
    def __init__(self, messages, server):
        self.messages, self.server = messages, server
        self.tools = [SimpleNamespace(name=n) for n in ("read_file", "run_terminal_command", "write_artifact")]
        self.system_message = SystemMessage(content="You fix defects.")
        self.model = SimpleNamespace(
            root_client=SimpleNamespace(chat=SimpleNamespace(completions=server)),
            _get_request_payload=lambda messages, **kw: {"model": "m", "messages": [
                {"role": getattr(m, "type", "user"), "content": m.content} for m in messages]})

    def override(self, **changes):
        changed = _Request(changes.get("messages", self.messages), self.server)
        changed.tools = changes.get("tools", self.tools)
        return changed


@pytest.fixture(autouse=True)
def _extraction_on(monkeypatch):
    monkeypatch.setenv("STRUCTURED_EXTRACTION", "on")


def _next_call_after(call, result):
    server, sent = _Server(), []
    messages = [HumanMessage(content="Fix the defect."),
                AIMessage(content=PROSE_WITH_A_FENCE, id="a1", tool_calls=[{**call, "id": "c1"}]),
                ToolMessage(content=result, tool_call_id="c1")]
    middleware = build_settled_answer_middleware(Fix, "defect_fix_1_0", 40)
    middleware.wrap_model_call(_Request(messages, server), lambda request: sent.append(request))
    return server, sent


def _told(request):
    return " ".join(str(getattr(m, "content", "") or "") for m in request.messages)


def test_a_reply_whose_command_ran_goes_on_with_its_tools_and_is_not_asked_for_its_answer():
    server, sent = _next_call_after(
        {"name": "run_terminal_command", "args": {"command": ["dotnet", "test"]}},
        '{"stdout": "Passed!  - Failed: 0, Passed: 17", "returncode": "0"}')

    assert server.sent == [], "no call outside the stage's own"
    assert len(sent) == 1 and "not the structured response" not in _told(sent[0])


def test_a_markdown_answer_whose_write_was_refused_is_still_asked_again_in_its_schema():
    server, sent = _next_call_after(
        {"name": "write_artifact", "args": {"relative_path": "docs/structured_response.md", "content": "## Fix"}},
        "Refusing to write 'docs/structured_response.md': your structured response is returned, not written.")

    assert len(server.sent) == 1 and server.sent[0]["response_format"]["json_schema"]["name"] == "Fix"
    assert sent == []
