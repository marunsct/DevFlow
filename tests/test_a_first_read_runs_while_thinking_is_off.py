"""With thinking off for the rest of a stage, a read of a file the stage has never opened still runs.

Thinking off offers only what acts (LF.1421) and took every read tool with it. Measured on a medium run, 17 of 19
reads refused whole came after that notice: builders and fixers that needed a file they had never opened, refused
"`read_file` is withheld at this point of the stage", call after call. A read sent anyway is now decided per file
(LF.1527): a first read runs, a read of what the conversation already holds is refused.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents import settled_answer, stage_memory
from app.agents.settled_answer import build_settled_answer_middleware

FROM_DISK = "read from disk"
OFFERED = ("read_file", "grep", "ls", "write_artifact", "edit_artifact", "run_terminal_command")


class Answer(BaseModel):
    changed_files: list[str]


class _Request(SimpleNamespace):
    def override(self, **changes):
        return _Request(**{**self.__dict__, **changes})


@pytest.fixture
def a_stage_with_thinking_off(monkeypatch):
    monkeypatch.setenv("STABLE_TOOLS", "on")
    monkeypatch.setenv("FIRST_REREAD_ANSWERED", "off")
    monkeypatch.setenv("FIX_STAGE_CALL_CAP", "off")
    monkeypatch.setattr(settled_answer, "_thinking_stays_off_for_the_stage", lambda *a, **k: True)
    guard = build_settled_answer_middleware(Answer, "specialist_database", 40)
    conversation = [
        HumanMessage(content="Build the data layer"),
        AIMessage(content="", tool_calls=[{"name": "read_file", "id": "a1",
                                           "args": {"file_path": "app/models.py"}}]),
        ToolMessage(content="     1\tclass Item:\n     2\t    pass\n", tool_call_id="a1", name="read_file"),
    ]
    with stage_memory.remembering("a-stage-thread"):
        guard.wrap_model_call(_Request(messages=conversation, tools=[SimpleNamespace(name=n) for n in OFFERED],
                                       model=None, model_settings={}), lambda request: None)
        yield guard
    stage_memory.forget_everything()


def _read(guard, path: str) -> str:
    call = SimpleNamespace(tool_call={"name": "read_file", "id": "r1", "args": {"file_path": path}})
    return str(guard.wrap_tool_call(call, lambda request: ToolMessage(content=FROM_DISK, tool_call_id="r1")).content)


def test_a_file_never_opened_is_read(a_stage_with_thinking_off):
    assert _read(a_stage_with_thinking_off, "app/routes.py") == FROM_DISK


def test_a_file_the_conversation_holds_is_not_read_again(a_stage_with_thinking_off):
    assert _read(a_stage_with_thinking_off, "app/models.py") != FROM_DISK
