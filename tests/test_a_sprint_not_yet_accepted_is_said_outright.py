"""A sprint not yet accepted is said to be so, and asking about one sprint after another stalls.

One run's planning stage, before any sprint was accepted, asked what had
changed since sprints 1, 2, 3, 4 and 5 in turn, over and over, each answered
"Nothing has changed since sprint N was accepted, or sprint N has not been
accepted yet". Each call had different arguments, so the identical-call rung
never saw it, and the stall rule counted one tool as no stall at all.
"""

from __future__ import annotations

import re

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents.settled_answer import NOTHING_NEW_BEFORE_THE_ANSWER, build_settled_answer_middleware
from app.tools.agent_toolkit import build_sprint_history_tool
from app.tools.version_control import accepted_sprints, commit_milestone, initialise_repository

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_before_any_sprint_is_accepted_the_tool_says_so_outright(tmp_path):
    (tmp_path / "a.txt").write_text("a\n")
    assert initialise_repository(tmp_path)
    tool = build_sprint_history_tool(str(tmp_path))

    answer = tool.invoke({"sprint": 3})
    assert answer["changed"] == []
    assert "Accepted so far: none" in answer["note"] and "nothing to compare against" in answer["note"]
    assert not BANNED.search(answer["note"])
    assert accepted_sprints(tmp_path) == []


def test_after_a_sprint_is_accepted_it_is_compared_against(tmp_path):
    (tmp_path / "a.txt").write_text("a\n")
    assert initialise_repository(tmp_path)
    commit_milestone(tmp_path, sprint=1, goal="sprint 1")
    assert accepted_sprints(tmp_path) == [1]
    (tmp_path / "b.txt").write_text("b\n")
    tool = build_sprint_history_tool(str(tmp_path))

    assert "b.txt" in tool.invoke({"sprint": 1})["changed"]
    assert "Accepted so far: 1" in tool.invoke({"sprint": 2})["note"]


class Plan(BaseModel):
    goal: str


class _Request:
    def __init__(self, messages):
        self.messages, self.tools, self.captured = messages, ["ls", "changed_since_sprint"], {}

    def override(self, **changes):
        self.captured.update(changes)
        return self


def test_one_tool_asked_one_thing_after_another_with_nothing_new_leaves_the_answer():
    note = "Sprint {n} has not been accepted in this run. Accepted so far: none. There is nothing to compare against."
    messages: list = [HumanMessage(content="plan the sprint")]
    for n in range(1, NOTHING_NEW_BEFORE_THE_ANSWER + 1):
        messages.append(AIMessage(content="", id=f"a{n}",
                                  tool_calls=[{"name": "changed_since_sprint", "args": {"sprint": n}, "id": f"c{n}"}]))
        messages.append(ToolMessage(content=note.format(n=n), tool_call_id=f"c{n}"))
    request = _Request(messages)

    build_settled_answer_middleware(Plan, "scrum_master", 120).wrap_model_call(request, lambda r: r)

    assert request.captured.get("tools") == []
