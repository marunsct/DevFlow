"""A defect-fix stage stops at 16 model calls instead of the budget every stage shares.

Measured over ten runs: the median productive agent-loop fix took 12 calls; the five most expensive stages were
36-40-call loops that ended in a surrender ("we can't fix all", empty `changed_files`), 1.1-1.9M input tokens each.
"""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents.settled_answer import build_settled_answer_middleware
from app.observability import transcript

ANSWER = '{"changed_files": ["app/server.js"]}'


class Fixed(BaseModel):
    changed_files: list[str]


def _still_reading_after(calls: int) -> dict:
    """A stage that has made `calls` model calls, each reading a new file, the last one with its answer written."""
    messages: list = [HumanMessage(content="fix the defect")]
    for i in range(calls):
        read = {"name": "read_file", "args": {"file_path": f"/app/f{i}.js"}, "id": f"c{i}", "type": "tool_call"}
        messages.append(AIMessage(content=ANSWER if i == calls - 1 else "", tool_calls=[read], id=f"a{i}"))
        if i < calls - 1:
            messages.append(ToolMessage(content="x", tool_call_id=f"c{i}"))
    return {"messages": messages}


def _ended(monkeypatch, stage: str, switch: str, calls: int) -> bool:
    monkeypatch.setenv("FIX_STAGE_CALL_CAP", switch)
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: stage)  # LangGraph's runtime config
    update = build_settled_answer_middleware(Fixed, stage, 40).after_model(_still_reading_after(calls), None)
    return (update or {}).get("jump_to") == "end"


@pytest.mark.parametrize(("stage", "switch", "calls", "ended"), [
    ("defect_fix_2_4", "on", 16, True),
    ("defect_fix_2_4", "on", 15, False),
    ("specialist_backend_1", "on", 16, False),
    ("defect_fix_2_4", "off", 16, False),
])
def test_a_fix_stage_with_its_answer_written_ends_at_sixteen_calls_and_others_keep_the_shared_budget(
        monkeypatch, stage, switch, calls, ended):
    assert _ended(monkeypatch, stage, switch, calls) is ended


def test_the_switch_is_registered():
    from app.observability import provenance

    assert "FIX_STAGE_CALL_CAP" in provenance.SWITCHES
