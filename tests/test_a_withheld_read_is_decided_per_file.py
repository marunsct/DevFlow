"""Once its reads stop teaching it anything, a stage's reads are decided file by file, not the read tool withheld whole.

Measured over 26 runs (tool review TR.2, LF.1517): 85 reads were refused with "Use what this conversation already
holds", and 51 of them asked for a file the request no longer held - read before a summary, or never read. The live
case is the conversation here, captured from a fixer's request after two summaries: it had been pointed at the project
memory nine times for three files it held, and then asked for those three and for the test file its defect names,
read once before both summaries. All four were refused; it wrote the product files without the test in front of it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents import project_memory, stage_memory
from app.agents.settled_answer import build_settled_answer_middleware

CAPTURED = json.loads((Path(__file__).parent / "captured" / "fixer-reads-withheld-after-two-summaries.json")
                      .read_text(encoding="utf-8"))
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
#: The three files the fixer's project memory held whole.
HELD = ("tasks-api/tasks_api/routes.py", "tasks-api/tasks_api/database.py", "tasks-api/tasks_api/models.py")
FROM_DISK = "read from disk"


class Answer(BaseModel):
    changed_files: list[str]


class _Request(SimpleNamespace):
    def override(self, **changes):
        return _Request(**{**self.__dict__, **changes})


def _message(m: dict):
    if m["type"] == "ai":
        return AIMessage(content=m["content"], tool_calls=m["tool_calls"])
    return ToolMessage(content=m["content"], tool_call_id=m["tool_call_id"], name=m["name"])


@pytest.fixture
def the_fixer(tmp_path, monkeypatch):
    """The fixer's memory holding its three files, and its answer guard, both in one stage, as its agent has them."""
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("STABLE_TOOLS", "on")
    monkeypatch.setenv("FIRST_REREAD_ANSWERED", "off")
    monkeypatch.setenv("FIX_STAGE_CALL_CAP", "off")
    (tmp_path / "tasks-api" / "tasks_api").mkdir(parents=True)
    for path in HELD:
        (tmp_path / path).write_text(f'"""{Path(path).stem}"""\n')
    memory = project_memory.build_project_memory_middleware(str(tmp_path))
    guard = build_settled_answer_middleware(Answer, "specialist_database", 40)
    with stage_memory.remembering("the-fixer-thread"):
        memory.wrap_model_call(_Request(messages=[HumanMessage(content="Fix the failing unit tests")], model=None),
                               lambda request: None)
        conversation = [HumanMessage(content="Fix the failing unit tests"),
                        *(_message(m) for m in CAPTURED["conversation"])]
        tools = [SimpleNamespace(name=name) for name in CAPTURED["offered"]]
        guard.wrap_model_call(_Request(messages=conversation, tools=tools, model=None, model_settings={}),
                              lambda request: None)
        yield memory, guard
    stage_memory.forget_everything()


def _read(memory, guard, path: str) -> str:
    """One read through both, the memory outside the guard as the agent orders them."""
    call = SimpleNamespace(tool_call={"name": "read_file", "id": "r1", "args": {"file_path": path}})

    def from_disk(request):
        return ToolMessage(content=FROM_DISK, tool_call_id="r1")

    return str(memory.wrap_tool_call(call, lambda request: guard.wrap_tool_call(request, from_disk)).content)


def test_the_test_file_read_before_both_summaries_is_read(the_fixer):
    memory, guard = the_fixer

    assert _read(memory, guard, "tasks-api/tests/test_models.py") == FROM_DISK


@pytest.mark.parametrize("path", HELD)
def test_a_file_the_memory_holds_is_refused_by_name_and_where_it_is(the_fixer, path):
    memory, guard = the_fixer

    said = _read(memory, guard, path)

    assert said != FROM_DISK
    assert f"'{path}'" in said and project_memory.HELD_POINTER in said
    assert not BANNED.search(said.replace(path, "")), "the harness's own words (the product's path aside)"


def test_a_file_read_since_the_last_summary_is_refused_by_name_and_where_it_is(the_fixer):
    """`auth.py` was read in the conversation the request still sends (its result is the file's numbered lines)."""
    memory, guard = the_fixer

    said = _read(memory, guard, "tasks-api/tasks_api/auth.py")

    assert said != FROM_DISK
    assert "'tasks-api/tasks_api/auth.py'" in said and "read earlier in this conversation" in said
    assert not BANNED.search(said.replace("tasks-api/tasks_api/auth.py", ""))


def test_the_stage_is_told_how_reads_are_decided(tmp_path, monkeypatch):
    """The notice is prompt text: it says the rule, and carries no product word."""
    monkeypatch.setenv("STABLE_TOOLS", "on")
    monkeypatch.setenv("FIX_STAGE_CALL_CAP", "off")
    conversation = [HumanMessage(content="Fix the failing unit tests"), *(_message(m) for m in CAPTURED["conversation"])]
    sent: list = []
    request = _Request(messages=conversation, tools=[SimpleNamespace(name=name) for name in CAPTURED["offered"]],
                       model=None, model_settings={})

    build_settled_answer_middleware(Answer, "specialist_database", 40).wrap_model_call(request, sent.append)

    said = str(sent[0].messages[-1]["content"])
    assert "file by file" in said and "can still be read" in said
    assert "refused if called" not in said, "the read tool is not listed as refused: each read is decided"
    assert not BANNED.search(said)
