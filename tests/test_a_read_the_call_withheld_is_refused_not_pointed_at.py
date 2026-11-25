"""A read of a held file on a call that withheld reading is refused, as the call said, not answered with a pointer.

Measured on one medium run (LF.1405): after a summary a fixer read a file its project memory held, was pointed at the
memory twice, and was told "reading is done for this stage ... refused if called: `read_file`". It read the same file
six times more; each read was answered with the memory's pointer, never the refusal it had been told of, so the
guards that count refused calls never saw one and the fixer spent its last calls and ended with no answer.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents import project_memory, stage_memory
from app.agents.settled_answer import build_settled_answer_middleware

HELD = "proj/app/db.py"


class Answer(BaseModel):
    changed_files: list[str]


class _Tool:
    def __init__(self, name):
        self.name = name


class _Request(SimpleNamespace):
    def override(self, **changes):
        return _Request(**{**self.__dict__, **changes})


@pytest.fixture
def a_fixer(tmp_path, monkeypatch):
    """The project memory holding one file, and the answer guard, as a fix stage's agent has them, in one stage."""
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("STABLE_TOOLS", "on")
    monkeypatch.setenv("FIRST_REREAD_ANSWERED", "off")
    (tmp_path / "proj" / "app").mkdir(parents=True)
    (tmp_path / HELD).write_text("engine = None\n")
    memory = project_memory.build_project_memory_middleware(str(tmp_path))
    guard = build_settled_answer_middleware(Answer, "specialist_backend", 40)
    with stage_memory.remembering("a-fixer-thread"):
        memory.wrap_model_call(_Request(messages=[HumanMessage(content="Fix the sign-up")], model=None),
                               lambda request: None)
        yield memory, guard
    stage_memory.forget_everything()


def _read(call_id):
    return SimpleNamespace(tool_call={"name": "read_file", "id": call_id, "args": {"file_path": HELD}})


def _a_tool_call(memory, guard, call_id):
    """A tool call through both, the memory outside the guard as the agent orders them."""
    def from_disk(request):
        return ToolMessage(content="the file", tool_call_id=call_id)

    return memory.wrap_tool_call(_read(call_id), lambda request: guard.wrap_tool_call(request, from_disk))


def test_a_read_after_reading_was_withheld_is_refused(a_fixer):
    memory, guard = a_fixer
    conversation = [HumanMessage(content="summary of the work so far")]
    for n in range(2):
        pointed = _a_tool_call(memory, guard, f"c{n}")
        conversation += [AIMessage(content="", id=f"a{n}", tool_calls=[_read(f"c{n}").tool_call]), pointed]
    tools = [_Tool(name) for name in ("read_file", "grep", "edit_artifact", "write_artifact")]
    guard.wrap_model_call(_Request(messages=conversation, tools=tools, model=None), lambda request: None)

    read_again = _a_tool_call(memory, guard, "c2")

    assert all(project_memory.HELD_POINTER in message.content for message in conversation[2::2])
    assert read_again.content.startswith("Refusing: `read_file` is withheld")
    assert project_memory.HELD_POINTER not in read_again.content


def test_a_read_no_call_withheld_is_still_answered_from_the_memory(a_fixer):
    memory, guard = a_fixer

    pointed = _a_tool_call(memory, guard, "c0")

    assert project_memory.HELD_POINTER in pointed.content
