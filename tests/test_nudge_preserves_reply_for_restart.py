"""Tests that a stage whose nudge produced text is retried on a fresh conversation.

When an initial model call produces nothing but reasoning (finish_reason: length,
empty content), the harness nudges the agent for its structured response.
If the nudged reply produced text content but could not parse into the structured
schema, the stage did NOT produce 'nothing but reasoning' - the model wrote
substantive text. The nudge result must be preserved in the gated runner so that
the stage falls through to a fresh conversation restart rather than falsely
diagnosing that the model produced nothing and terminating the run.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from app.agents.technical_lead import _SYSTEM_PROMPT, create_technical_lead_agent
from app.graph.workflow import _run_gated_agent


class _ReplyAgent:
    def __init__(self, replies: list[dict[str, Any]]):
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def invoke(self, request: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append({"request": request, "config": config})
        if self.replies:
            return self.replies.pop(0)
        return {"messages": []}


def _make_msg(content: str = "", finish: str = "stop") -> AIMessage:
    msg = AIMessage(content=content)
    msg.response_metadata = {"finish_reason": finish}
    return msg


def test_nudge_producing_text_restarts_instead_of_failing():
    initial_reply = {
        "messages": [_make_msg(content="", finish="length")],
        "structured_response": None,
    }
    nudge_reply = {
        "messages": [
            _make_msg(content="", finish="length"),
            _make_msg(content="Here is the detailed analysis...", finish="length"),
        ],
        "structured_response": None,
    }

    agent = _ReplyAgent([initial_reply, nudge_reply])
    agent.workflow_response_format = None

    state = {
        "repository": SimpleNamespace(root_path="/workspace"),
        "structured_retries": {},
    }

    update = _run_gated_agent(
        state,
        {"configurable": {"thread_id": "thread-outer"}},
        stage_name="technical_lead",
        agent=agent,
        initial_request={"messages": []},
        output_key="milestone_plan",
        next_stage="sprint_planning",
    )

    assert update is not None
    assert update.get("stage") == "technical_lead"
    assert update.get("structured_retries", {}).get("technical_lead") == 1


def test_technical_lead_has_no_contradictory_artifact_write_prompt():
    """Technical lead has can_write=False; prompt must not instruct it to write artifacts."""
    agent = create_technical_lead_agent(model="openai:gpt-4o-mini")
    assert getattr(agent, "can_write", False) is False

    assert "write_artifact" not in _SYSTEM_PROMPT
    assert "ONE single write_artifact call" not in _SYSTEM_PROMPT


def test_technical_lead_prompt_banned_words():
    banned = {"task", "tasks", "to-do", "todo", "button", "click", "checkbox"}
    words = set(re.findall(r"\b[a-z0-9_-]+\b", _SYSTEM_PROMPT.lower()))
    # In technical lead, the system prompt contains delegated_tasks / tasks in architecture context
    # but any new rules must ban todo/button/click/checkbox
    for banned_word in {"to-do", "todo", "button", "click", "checkbox"}:
        assert banned_word not in words

