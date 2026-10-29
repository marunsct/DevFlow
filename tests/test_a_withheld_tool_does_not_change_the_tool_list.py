"""With `STABLE_TOOLS` on, a withheld tool stays on the list and is refused when called (plan PX.2).

Tools are rendered into the system prompt, so a list that changes inside a
stage makes the server prefill the conversation again: the first break behind
30-31% of uncached input on two gate runs (PX.1). Off, the list narrows as before.
"""
from __future__ import annotations

import os
import re
from types import SimpleNamespace
from unittest import mock

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


def _repeated_glob():
    messages: list = [HumanMessage(content="plan")]
    for n in range(IDENTICAL_ANSWERS_BEFORE_WITHHOLDING_THE_TOOL):
        messages.append(AIMessage(content="", id=f"a{n}", tool_calls=[{"name": "glob", "args": {"pattern": "*"}, "id": f"c{n}"}]))
        messages.append(ToolMessage(content=SAME, tool_call_id=f"c{n}"))
    return messages


def _sent(switch):
    tools = [SimpleNamespace(name=name) for name in ("glob", "ls", "read_file")]
    middleware = build_settled_answer_middleware(Plan, "scrum_master", 120)
    sent = []
    with mock.patch.dict(os.environ, {"STABLE_TOOLS": switch}):
        middleware.wrap_model_call(_Request(_repeated_glob(), tools), lambda r: sent.append(r))
    return middleware, sent[0]


def test_on_the_list_is_unchanged_the_call_is_told_and_the_tool_is_refused():
    middleware, sent = _sent("on")
    assert [tool.name for tool in sent.tools] == ["glob", "ls", "read_file"]
    told = sent.messages[-1]["content"]
    assert "`glob`" in told and "refused if called" in told and not BANNED.search(told)
    refused = middleware.wrap_tool_call(SimpleNamespace(tool_call={"name": "glob", "args": {}, "id": "x"}), lambda r: "ran")
    assert isinstance(refused, ToolMessage) and "was not run" in refused.content
    assert middleware.wrap_tool_call(SimpleNamespace(tool_call={"name": "ls", "args": {}, "id": "y"}), lambda r: "ran") == "ran"


def test_off_the_list_narrows_as_before():
    _, sent = _sent("off")
    assert "glob" not in [tool.name for tool in sent.tools]


def test_on_a_spent_research_share_leaves_its_tools_listed(monkeypatch):
    from app.tools import research

    monkeypatch.setattr(research, "spent", lambda kind: True)
    tools = [SimpleNamespace(name=name) for tools in research._TOOL_OF.values() for name in tools] + [SimpleNamespace(name="ls")]
    middleware = research.build_research_share_middleware()
    for switch, kept in (("on", len(tools)), ("off", 1)):
        sent = []
        with mock.patch.dict(os.environ, {"STABLE_TOOLS": switch}):
            middleware.wrap_model_call(_Request([HumanMessage(content="x")], tools), lambda r: sent.append(r))
        assert len(sent[0].tools) == kept


def test_a_stage_whose_reading_was_done_for_it_is_refused_a_lookup_its_tools_stay_listed_for():
    """Held listed under the switch, the research tools of an architect whose research was done ran up to
    their whole shares; they had not been offered at all."""
    from app.tools import research

    with research.researched(True):
        refusal = research.over_its_share("documentation")
    assert refusal and "done for it" in refusal
    assert not re.search(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", refusal, re.I)
