"""A writing stage's last call is kept for a write: told one call before that its next must be the write, and not refused.

Measured on a medium run: 10 fix attempts ended at the call cap with their final edit refused - the calls reserved for
the answer withheld every tool, the writers too, and a write on the last call ended with the stage, unrun (LF.1270).
Every stage that writes since (TR.6, LF.1519).
"""
from __future__ import annotations

import re

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents import settled_answer
from app.agents.settled_answer import build_settled_answer_middleware

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
LIMIT = 16


class Fixed(BaseModel):
    changed_files: list[str]


class _Tool:
    def __init__(self, name):
        self.name = name


TOOLS = [_Tool(n) for n in ("read_file", "ls", "grep", "edit_artifact", "write_artifact", "run_terminal_command")]


class _Request:
    def __init__(self, messages, tools=None):
        self.messages = messages
        self.tools = list(TOOLS if tools is None else tools)
        self.captured: dict = {}

    def override(self, **changes):
        self.captured.update(changes)
        other = _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))
        other.captured = self.captured
        return other


def _calls(count: int, last: dict | None = None) -> list:
    """A fix stage that has made `count` model calls - one write, then reads of new files - with no answer written;
    `last`, when given, is the tool call its last reply asks for, not yet run."""
    messages: list = [HumanMessage(content="fix the defect")]
    for n in range(count):
        call = ({"name": "edit_artifact", "args": {"relative_path": "app/x.py"}, "id": f"c{n}"} if n == 0
                else {"name": "read_file", "args": {"file_path": f"app/f{n}.py"}, "id": f"c{n}"})
        if n == count - 1 and last is not None:
            messages.append(AIMessage(content="", id=f"a{n}", tool_calls=[{**last, "id": f"c{n}"}]))
            return messages
        messages.append(AIMessage(content="", id=f"a{n}", tool_calls=[call]))
        messages.append(ToolMessage(content=f"   1  contents {n}", tool_call_id=f"c{n}"))
    return messages


def _offered(count: int, monkeypatch, stage: str = "defect_fix_2_3", tools: list | None = None) -> tuple[set[str], str]:
    monkeypatch.setenv("STABLE_TOOLS", "off")
    monkeypatch.setattr(settled_answer, "_the_graph_stage", lambda role="": stage)
    request = _Request(_calls(count), tools)
    build_settled_answer_middleware(Fixed, "specialist_backend", LIMIT).wrap_model_call(request, lambda r: r)
    offered = request.captured.get("tools")
    return ({t.name for t in request.tools} if offered is None else {t.name for t in offered}), str(request.captured.get("messages", [""])[-1])


def test_one_call_before_the_last_the_writers_stay_and_the_next_call_is_named_the_write(monkeypatch):
    offered, said = _offered(LIMIT - 2, monkeypatch)

    assert offered == {"edit_artifact", "write_artifact"}
    assert "next call must be that write" in said and "kept and run" in said


def test_on_the_last_call_the_writers_stay(monkeypatch):
    offered, said = _offered(LIMIT - 1, monkeypatch)

    assert offered == {"edit_artifact", "write_artifact"}
    assert "last model call" in said


def test_after_the_last_call_only_the_answer_is_left(monkeypatch):
    offered, _ = _offered(LIMIT, monkeypatch)

    assert offered == set()


@pytest.mark.parametrize("stage", ["specialist_backend_1", "specialist_testing_0", "acceptance_author_2",
                                   "test_round_0", "custom_setup"])
def test_every_stage_that_writes_keeps_its_writers_on_its_last_calls(monkeypatch, stage):
    """TR.6: measured over 26 runs, 18 last writes refused in 15 visits of builders, suite writers, test rounds and the
    setup - only fix stages kept their writers there."""
    offered, said = _offered(LIMIT - 2, monkeypatch, stage=stage)

    assert offered == {"edit_artifact", "write_artifact"}
    assert "next call must be that write" in said


def test_a_stage_that_only_looks_has_only_its_answer_on_its_last_calls(monkeypatch):
    offered, _ = _offered(LIMIT - 2, monkeypatch, stage="code_review_1",
                          tools=[_Tool(n) for n in ("read_file", "ls", "grep")])

    assert offered == set()


@pytest.mark.parametrize("stage", ["defect_fix_2_3", "specialist_backend_1"])
@pytest.mark.parametrize(("last", "ended"), [
    ({"name": "edit_artifact", "args": {"relative_path": "app/x.py", "content": "fixed"}}, False),
    ({"name": "read_file", "args": {"file_path": "app/y.py"}}, True),
])
def test_a_write_sent_on_the_last_call_is_run_and_any_other_call_ends_the_stage(monkeypatch, last, ended, stage):
    monkeypatch.setattr(settled_answer, "_the_graph_stage", lambda role="": stage)
    state = {"messages": _calls(LIMIT, last=last)}

    update = build_settled_answer_middleware(Fixed, "specialist_backend", LIMIT).after_model(state, None)

    assert ((update or {}).get("jump_to") == "end") is ended


def test_what_the_last_calls_are_told_names_no_product_word():
    for said in (settled_answer.LAST_CALLS_KEPT_FOR_A_WRITE, settled_answer.LAST_CALL_KEPT_FOR_A_WRITE):
        assert not BANNED.search(said)
