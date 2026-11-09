"""A fix stage twice told its defect's own tests pass is left only its answer (plan AY step 3).

Measured on an all-on run: a fixer whose unit-test defect was fixed was told so
seven times and went on diagnosing another defect's 500s with one throwaway
script after another, on work another fixer is given.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents import settled_answer
from app.agents.settled_answer import build_settled_answer_middleware
from app.graph.verify_after_write import FAILING, PASSED

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


class Fix(BaseModel):
    summary: str


class _Request:
    def __init__(self, messages, tools):
        self.messages, self.tools = messages, tools

    def override(self, **changes):
        return _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))


def _after_writes(*outcomes):
    messages: list = [HumanMessage(content="fix the defect")]
    for n, outcome in enumerate(outcomes):
        messages.append(AIMessage(content="", id=f"a{n}", tool_calls=[{"name": "edit_artifact", "args": {}, "id": f"c{n}"}]))
        messages.append(ToolMessage(content='{"status": "edited"}\n' + outcome, tool_call_id=f"c{n}"))
    return messages


def _sent(messages):
    tools = [SimpleNamespace(name=name) for name in ("read_file", "edit_artifact", "run_terminal_command")]
    middleware = build_settled_answer_middleware(Fix, "defect_fix_1_0", 120)
    sent = []
    middleware.wrap_model_call(_Request(messages, tools), lambda r: sent.append(r))
    return sent[0]


def test_twice_told_fixed_the_stage_is_left_only_its_answer():
    request = _sent(_after_writes(PASSED, PASSED))
    assert [t.name for t in request.tools] == [], "tools withheld"
    told = " ".join(str(getattr(m, "content", "") or (m.get("content") if isinstance(m, dict) else "")) for m in request.messages)
    assert "return your structured answer now" in told
    assert not BANNED.search(settled_answer._FIXED_ANSWER_NOW_NOTICE)


def test_once_told_or_broken_again_since_it_keeps_its_tools():
    assert settled_answer._told_its_defect_is_fixed(_after_writes(PASSED)) is False
    assert settled_answer._told_its_defect_is_fixed(_after_writes(PASSED, PASSED, FAILING)) is False
    assert settled_answer._told_its_defect_is_fixed(_after_writes(PASSED, FAILING, PASSED)) is True
