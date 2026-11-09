"""A stage refused writes outside its own files again and again is left only its answer.

Measured over 40 runs: 11 had a testing stage, its own tests failing against the product, try to change the
product's code; each write was refused, from the third on with "every one will be refused", and it went on - up to
15 refusals, each a full model call. The stall rule never fired: a refused write is not "nothing new", so each one
broke the streak of reads it was counting.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents import settled_answer
from app.agents.settled_answer import build_settled_answer_middleware

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


class Answer(BaseModel):
    summary: str


class _Request:
    def __init__(self, messages, tools):
        self.messages, self.tools = messages, tools

    def override(self, **changes):
        return _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))


def _refused(times: int):
    messages: list = [HumanMessage(content="write the tests")]
    for n in range(1, times + 1):
        lead = (f"This stage has now been refused {n} writes outside its own files, whatever the file, the tool or "
                "the path. Every one will be refused. ") if n >= 3 else ""
        messages.append(AIMessage(content="", id=f"a{n}", tool_calls=[
            {"name": "edit_artifact", "args": {"relative_path": f"app/main{n}.py"}, "id": f"c{n}"}]))
        messages.append(ToolMessage(content='{"error": "' + lead + "'app/main.py' is product code. Nothing was written.\"}",
                                    tool_call_id=f"c{n}"))
        # A read between refusals that taught it something: the streak the stall rule counts is broken.
        messages.append(AIMessage(content="", id=f"r{n}", tool_calls=[{"name": "read_file", "args": {"file_path": f"t{n}"}, "id": f"rc{n}"}]))
        messages.append(ToolMessage(content=f"1\tline {n}", tool_call_id=f"rc{n}"))
    return messages


def _sent(messages):
    tools = [SimpleNamespace(name=name) for name in ("read_file", "edit_artifact", "write_artifact", "run_terminal_command")]
    middleware = build_settled_answer_middleware(Answer, "specialist_testing_2", 120)
    sent = []
    middleware.wrap_model_call(_Request(messages, tools), lambda r: sent.append(r))
    return sent[0]


def test_six_writes_refused_elsewhere_leave_only_the_answer():
    request = _sent(_refused(6))
    assert [t.name for t in request.tools] == [], "tools withheld"
    told = " ".join(str(getattr(m, "content", "") or (m.get("content") if isinstance(m, dict) else "")) for m in request.messages)
    assert "return your structured response now" in told and "the role that owns that code" in told
    assert not BANNED.search(settled_answer._OUTSIDE_ANSWER_NOW_NOTICE)


def test_fewer_refusals_keep_the_tools():
    request = _sent(_refused(5))
    assert "edit_artifact" in [t.name for t in request.tools]
    assert settled_answer._refused_outside_its_own_files(_refused(5)) == 5
    assert settled_answer._refused_outside_its_own_files(_refused(2)) == 0, "counted only once the refusal says so"
