"""A stage's prose answer is asked again with only its schema allowed, and older refusals reach the model as a line each.

On llama.cpp an answer tool cannot be forced - a named `tool_choice` reads as
`auto`, and one model answered "Hi! How can I help you?" three times of three
with `required` and one tool - so a model that writes its answer as text was
reminded and wrote text again. `response_format` with the answer's schema and
no tools is enforced. And a fixer with a dozen refused shell lines in its
conversation sent a thirteenth: a model continues the mistakes its context
holds (Sinha et al., 2025).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field

from app.agents import refusal_folding, structured_extraction


class Answer(BaseModel):
    changed_files: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)


class _Server:
    def __init__(self, content):
        self.content, self.sent = content, []

    def create(self, **payload):
        self.sent.append(payload)
        return {"choices": [{"finish_reason": "stop", "message": {"content": self.content}}]}


def _request(server):
    model = SimpleNamespace(
        root_client=SimpleNamespace(chat=SimpleNamespace(completions=server)),
        _get_request_payload=lambda messages, **kw: {"model": "m", "messages": [
            {"role": getattr(m, "type", "user"), "content": m.content} for m in messages],
            "tools": [{"type": "function"}], "tool_choice": "auto"},
    )
    return SimpleNamespace(model=model, system_message=SystemMessage(content="You fix defects."),
                           messages=[HumanMessage(content="Fix it."), AIMessage(content="I changed routes.py.")])


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("STRUCTURED_EXTRACTION", "on")
    monkeypatch.setenv("REFUSALS_FOLDED", "on")


def test_a_prose_answer_is_asked_again_with_no_tools_and_its_schema_as_the_format():
    server = _Server('<think>it was routes.py</think>{"changed_files": ["app/routes.py"], "decisions": ["201"]}')

    response = structured_extraction.answered_in_its_schema(_request(server), Answer, "defect_fix_1")

    sent = server.sent[0]
    assert "tools" not in sent and "tool_choice" not in sent
    assert sent["response_format"]["json_schema"]["schema"] == Answer.model_json_schema()
    assert sent["messages"][-1]["content"] == structured_extraction.ASK
    call = response.result[0].tool_calls[0]
    assert call["name"] == "Answer" and call["args"]["changed_files"] == ["app/routes.py"]


def test_no_object_back_leaves_the_stage_to_its_reminder():
    assert structured_extraction.answered_in_its_schema(_request(_Server("I cannot.")), Answer) is None


def test_a_refused_schema_leaves_the_stage_to_its_reminder():
    class _Refuses:
        def create(self, **payload):
            raise RuntimeError("400 - unsupported schema keyword")

    assert structured_extraction.answered_in_its_schema(_request(_Refuses()), Answer) is None


def test_nothing_is_asked_again_with_the_switch_off(monkeypatch):
    monkeypatch.setenv("STRUCTURED_EXTRACTION", "off")
    server = _Server('{"changed_files": []}')
    assert structured_extraction.answered_in_its_schema(_request(server), Answer) is None and server.sent == []


def _refusals(n):
    messages = []
    for i in range(n):
        messages.append(AIMessage(content="", tool_calls=[{"id": f"c{i}", "name": "run_terminal_command",
                                                            "args": {"command": [f"cd a && cat f{i}"]}}]))
        messages.append(ToolMessage(tool_call_id=f"c{i}", content=json.dumps({"error": (
            f"'cd a && cat f{i}' is a whole command line in one string. There is no shell here. " + "Detail. " * 60)})))
    return messages


def test_every_refusal_but_the_latest_is_a_line_each():
    messages = _refusals(4)
    sent, count = refusal_folding.folded(messages)

    assert count == 3
    tools = [m for m in sent if m.type == "tool"]
    assert all(m.content.startswith(refusal_folding.FOLDED) and len(m.content) < 220 for m in tools[:-1])
    assert tools[-1].content == messages[-1].content  # the one it is answering stays whole
    assert messages[1].content.startswith('{"error"')  # the stored conversation is untouched


def test_the_guards_still_count_the_refusals_as_stored():
    from app.agents.settled_answer import IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL, _a_tool_refused_identically

    messages = _refusals(IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL)
    refusal_folding.folded(messages)
    assert _a_tool_refused_identically(messages) is not None


def test_one_refusal_is_left_as_it_is():
    messages = _refusals(1)
    assert refusal_folding.folded(messages) == (messages, 0)
