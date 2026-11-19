"""A stage that starts over on a fresh conversation is not refused a read as "already read in this stage".

Measured on one C# technical lead: nine fresh conversations in 33 calls, and a conversation carrying a single message
was refused reads of the acceptance file as already given - text that conversation had never been given. The record
of what a stage's reads gave is forgotten when a conversation of the stage begins, as a compaction forgets it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents import stage_memory
from app.agents.workspace_backend import WHAT_THE_CONVERSATION_WAS_GIVEN, build_fresh_conversation_middleware


@dataclass
class _Request:
    messages: list[Any] = field(default_factory=list)


def _given() -> dict:
    return stage_memory.store(WHAT_THE_CONVERSATION_WAS_GIVEN[0], {})


def _called_with(messages: list[Any]) -> None:
    build_fresh_conversation_middleware().wrap_model_call(_Request(messages=messages), lambda request: None)


def test_a_fresh_conversation_forgets_what_the_stage_read():
    with stage_memory.remembering("stage-under-test-fresh"):
        _given()["spec.js"] = [(1, 100)]

        _called_with([SystemMessage(content="rules"), HumanMessage(content="plan the sprint")])

        assert _given() == {}


def test_a_conversation_under_way_keeps_it():
    with stage_memory.remembering("stage-under-test-ongoing"):
        _given()["spec.js"] = [(1, 100)]

        _called_with([HumanMessage(content="plan"), AIMessage(content="", tool_calls=[
            {"name": "read_file", "args": {"file_path": "spec.js"}, "id": "c1"}]),
            ToolMessage(content="1 | import", tool_call_id="c1")])

        assert _given() == {"spec.js": [(1, 100)]}


def test_the_role_agent_carries_it():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "src" / "app" / "agents" / "role_agent.py").read_text()
    assert "_fresh_conversation_middleware()," in source
