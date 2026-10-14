"""A checkpoint write holding an integer msgpack cannot store does not fail the run.

Measured on one run: 15 hours in, a stage's reply held such an integer in the
message the agent was writing, and the write raised "Type is not msgpack
serializable: AIMessage" - the run failed.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage

from app.agents.technical_lead import MilestonePlanOutput
from app.graph.checkpointing import build_serializer


def test_a_message_holding_a_huge_integer_is_stored_and_read_back_as_a_message():
    serializer = build_serializer()
    message = AIMessage(
        content="", tool_calls=[{"name": "t", "args": {"id": 2**70, "ok": 3}, "id": "1"}],
        response_metadata={"seed": -(2**80)},
    )

    restored = serializer.loads_typed(serializer.dumps_typed({"messages": [message]}))

    back = restored["messages"][0]
    assert isinstance(back, AIMessage)
    assert back.tool_calls[0]["args"] == {"id": str(2**70), "ok": 3}
    assert back.response_metadata["seed"] == str(-(2**80))


def test_what_msgpack_holds_is_stored_as_it_is():
    serializer = build_serializer()
    plan = MilestonePlanOutput(selected_sprint_goal="g", milestone_scope=[], delegated_tasks=[], blockers=["none yet"])
    value = {"plan": plan, "n": 2**63 - 1, "flag": True}

    assert serializer.loads_typed(serializer.dumps_typed(value)) == value
