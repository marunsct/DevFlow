"""An agent-loop fix stage that sends the same action again is told what it already did, and a stage stopped at its call cap is not restarted.

Measured over ten runs: agent-loop fix stages took 26% of the time; the costliest were 36-40-call loops that ended in
a surrender. The call cap (`FIX_STAGE_CALL_CAP`, 16 calls) held per conversation, but a stage stopped at it with no
answer was restarted on a fresh conversation twice, each restart a new 16, and the guards on a repeated action
refused the call without changing what the model read next. Behind `AGENT_LOOP_FIX_LIMITS` (off until measured).
"""
from __future__ import annotations

import inspect
import re

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents import settled_answer
from app.agents.settled_answer import BUDGET_STOP_MARKER, build_settled_answer_middleware
from app.graph import agent_loop_fix_limits, workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("AGENT_LOOP_FIX_LIMITS", "on")


class Verdict(BaseModel):
    status: str
    reason: str


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


def _calls(*calls):
    """A conversation of (tool, arguments) calls, each answered with a different result."""
    messages = [HumanMessage(content="fix it")]
    for n, (name, args) in enumerate(calls):
        messages.append(AIMessage(content="", id=f"a{n}", tool_calls=[{"name": name, "args": args, "id": f"c{n}"}]))
        messages.append(ToolMessage(content=f"result number {n}", tool_call_id=f"c{n}"))
    messages.append(AIMessage(content="thinking", id="last"))
    return messages


READ = ("read_file", {"file_path": "src/store.py"})
EDIT = ("edit_artifact", {"relative_path": "src/store.py", "old": "a", "new": "b"})
LS = ("ls", {"path": "."})


def _middleware_call(messages, monkeypatch, stage="defect_fix_2_14"):
    monkeypatch.setattr(settled_answer, "_the_graph_stage", lambda role="": stage)
    request = _Request(messages)
    build_settled_answer_middleware(Verdict, "specialist_backend", 40).wrap_model_call(request, lambda r: r)
    return request.captured


def test_the_same_read_three_times_with_no_write_between_is_told_what_was_already_tried():
    said = agent_loop_fix_limits.repeat_notice(
        _calls(READ, ("read_file", {"file_path": "./src/store.py"}), ("read_file", {"file_path": "src/store.py "})),
        "defect_fix_2_14",
    )

    assert "`read_file`" in said and "3 times" in said
    assert "gave nothing" in said and "return your structured response" in said
    assert not BANNED.search(said)


def test_two_spellings_of_one_action_are_one_action():
    assert agent_loop_fix_limits.action_key({"name": "run_terminal_command", "args": {"command": "pytest   -x\n"}}) == \
        agent_loop_fix_limits.action_key({"name": "run_terminal_command", "args": {"command": "pytest -x"}})


def test_below_the_threshold_or_after_a_write_there_is_nothing_to_say():
    assert agent_loop_fix_limits.repeat_notice(_calls(READ, READ), "defect_fix_2_14") == ""
    # Three reads, but a write between the second and third: the third reads a changed file.
    assert agent_loop_fix_limits.repeat_notice(_calls(READ, READ, EDIT, READ), "defect_fix_2_14") == ""
    assert agent_loop_fix_limits.repeat_notice(_calls(READ, READ, READ, EDIT), "defect_fix_2_14") == ""


def test_the_notice_follows_the_action_just_sent_and_lists_the_others():
    said = agent_loop_fix_limits.repeat_notice(_calls(READ, LS, READ, LS, READ), "defect_fix_2_14")

    assert "`read_file`" in said and "3 times" in said
    assert "`ls`" in said and "2 time(s)" in said
    # The last action sent is an `ls`, twice: below the threshold, so nothing is said.
    assert agent_loop_fix_limits.repeat_notice(_calls(READ, READ, READ, LS), "defect_fix_2_14") == ""


def test_off_and_other_stages_are_left_alone(monkeypatch):
    messages = _calls(READ, READ, READ)
    assert agent_loop_fix_limits.repeat_notice(messages, "specialist_backend_0") == ""
    monkeypatch.setenv("AGENT_LOOP_FIX_LIMITS", "off")
    assert agent_loop_fix_limits.repeat_notice(messages, "defect_fix_2_14") == ""


def test_the_model_s_next_input_changes_it_is_not_only_refused(monkeypatch):
    captured = _middleware_call(_calls(READ, READ, READ), monkeypatch)

    said = str(captured["messages"][-1])
    assert "You have now sent `read_file`" in said and "3 times, and no file has changed" in said
    assert "tools" not in captured, "the tool stays; what the model reads next is what changes"


def test_a_fix_stage_that_does_not_repeat_reads_its_conversation_as_it_was(monkeypatch):
    assert _middleware_call(_calls(READ, LS, ("grep", {"pattern": "x"})), monkeypatch) == {}


def test_a_fix_stage_stopped_at_its_call_cap_is_not_restarted():
    stopped = {"messages": [AIMessage(content="", additional_kwargs={BUDGET_STOP_MARKER: True})]}
    ended = {"messages": [AIMessage(content="")]}

    assert agent_loop_fix_limits.ends_for_good("defect_fix_2_14", stopped) is True
    assert agent_loop_fix_limits.ends_for_good("defect_fix_2_14", ended) is False
    assert agent_loop_fix_limits.ends_for_good("specialist_backend_0", stopped) is False


def test_off_a_fix_stage_stopped_at_its_call_cap_is_restarted_as_before(monkeypatch):
    monkeypatch.setenv("AGENT_LOOP_FIX_LIMITS", "off")
    stopped = {"messages": [AIMessage(content="", additional_kwargs={BUDGET_STOP_MARKER: True})]}

    assert agent_loop_fix_limits.ends_for_good("defect_fix_2_14", stopped) is False


def test_the_stage_runner_asks_before_it_restarts_a_stage():
    source = inspect.getsource(workflow._run_gated_agent)

    assert "ends_for_good(stage_name, result)" in source
    assert source.index("ends_for_good(stage_name, result)") < source.index('"produced no structured response"')
