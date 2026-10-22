"""A call to a tool the model call withheld is refused, not run.

A planning stage on a 1-bit model sent one withheld query 23 times; each ran.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents.settled_answer import IDENTICAL_ANSWERS_BEFORE_WITHHOLDING_THE_TOOL, build_settled_answer_middleware

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SAME = "[This `glob` returned exactly what it returned the 3 previous times you ran it in this stage.]"


class Plan(BaseModel):
    goal: str


class _Request:
    def __init__(self, messages, tools):
        self.messages, self.tools = messages, tools

    def override(self, **changes):
        return _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))


def test_a_withheld_tool_is_refused_and_an_offered_one_runs():
    messages: list = [HumanMessage(content="plan")]
    for n in range(IDENTICAL_ANSWERS_BEFORE_WITHHOLDING_THE_TOOL):
        messages.append(AIMessage(content="", id=f"a{n}", tool_calls=[{"name": "glob", "args": {"pattern": "*"}, "id": f"c{n}"}]))
        messages.append(ToolMessage(content=SAME, tool_call_id=f"c{n}"))
    tools = [SimpleNamespace(name=name) for name in ("glob", "ls", "read_file")]
    middleware = build_settled_answer_middleware(Plan, "scrum_master", 120)
    sent = []
    middleware.wrap_model_call(_Request(messages, tools), lambda r: sent.append(r))
    assert "glob" not in [tool.name for tool in sent[0].tools]

    refused = middleware.wrap_tool_call(SimpleNamespace(tool_call={"name": "glob", "args": {}, "id": "x"}), lambda r: "ran")
    assert isinstance(refused, ToolMessage) and "was not run" in refused.content
    assert not BANNED.search(refused.content)
    assert middleware.wrap_tool_call(SimpleNamespace(tool_call={"name": "ls", "args": {}, "id": "y"}), lambda r: "ran") == "ran"


def test_nothing_is_refused_when_nothing_was_withheld():
    middleware = build_settled_answer_middleware(Plan, "scrum_master", 120)
    middleware.wrap_model_call(_Request([HumanMessage(content="plan")], [SimpleNamespace(name="glob")]), lambda r: r)
    assert middleware.wrap_tool_call(SimpleNamespace(tool_call={"name": "glob", "args": {}, "id": "x"}), lambda r: "ran") == "ran"


def test_a_withheld_tool_stays_refused_when_the_agent_is_built_again_to_resume_a_pause():
    """A call that needs approval pauses the graph and the agent is built afresh to run it, with no model
    call first: a withheld write ran after its pause."""
    from app.agents import stage_memory
    from app.agents.settled_answer import _NOTHING_NEW, _REFUSED

    messages: list = [HumanMessage(content="plan")]
    for n in range(IDENTICAL_ANSWERS_BEFORE_WITHHOLDING_THE_TOOL):
        messages.append(AIMessage(content="", id=f"a{n}", tool_calls=[{"name": "glob", "args": {"pattern": "*"}, "id": f"c{n}"}]))
        messages.append(ToolMessage(content=SAME, tool_call_id=f"c{n}"))
    tools = [SimpleNamespace(name=name) for name in ("glob", "ls")]
    with stage_memory.remembering("run-x:scrum_master"):
        first = build_settled_answer_middleware(Plan, "scrum_master", 120)
        first.wrap_model_call(_Request(messages, tools), lambda r: r)
        rebuilt = build_settled_answer_middleware(Plan, "scrum_master", 120)
        refused = rebuilt.wrap_tool_call(SimpleNamespace(tool_call={"name": "glob", "args": {}, "id": "x"}), lambda r: "ran")
    assert isinstance(refused, ToolMessage), "the rebuilt agent still refuses it"
    assert _REFUSED.search(refused.content) and _NOTHING_NEW.search(refused.content), "counted as refused and as nothing new"
