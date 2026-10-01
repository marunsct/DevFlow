"""A tool call cut off at the output limit is not sent back to the model server.

One run's technical lead was cut off inside its answer's tool call. The nudge,
the retry and the recovery call each re-sent that history, and llama-server
refused every one with 500 "Failed to parse tool call arguments as JSON" - four
in three seconds, and the run failed.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from app.models import CUT_OFF_CALL_NOTE, CompatibleChatOpenAI, without_cut_off_tool_calls


def _call(call_id: str, arguments: str) -> dict:
    return {"id": call_id, "type": "function", "function": {"name": "Plan", "arguments": arguments}}


def test_a_cut_off_call_nobody_answered_is_removed_and_said_so() -> None:
    messages = [
        {"role": "user", "content": "plan"},
        {"role": "assistant", "content": None, "tool_calls": [_call("a", '{"tasks": ["Given x, when')]},
        {"role": "user", "content": "answer now"},
    ]

    without_cut_off_tool_calls(messages)

    assert "tool_calls" not in messages[1]
    assert messages[1]["content"] == CUT_OFF_CALL_NOTE


def test_a_whole_call_beside_it_is_kept() -> None:
    messages = [
        {"role": "assistant", "content": "reading", "tool_calls": [_call("a", '{"path": "/"}'), _call("b", '{"x": "y')]},
        {"role": "tool", "tool_call_id": "a", "content": "[]"},
    ]

    without_cut_off_tool_calls(messages)

    assert [c["id"] for c in messages[0]["tool_calls"]] == ["a"]
    assert messages[0]["content"].startswith("reading") and CUT_OFF_CALL_NOTE in messages[0]["content"]


def test_a_cut_off_call_a_tool_message_answers_keeps_its_place() -> None:
    messages = [
        {"role": "assistant", "content": "", "tool_calls": [_call("a", '{"x": "y')]},
        {"role": "tool", "tool_call_id": "a", "content": "error: invalid arguments"},
    ]

    without_cut_off_tool_calls(messages)

    assert messages[0]["tool_calls"][0]["function"]["arguments"] == "{}"


def test_a_sound_history_is_untouched() -> None:
    messages = [
        {"role": "assistant", "content": "", "tool_calls": [_call("a", "{}")]},
        {"role": "tool", "tool_call_id": "a", "content": "ok"},
    ]
    before = repr(messages)

    without_cut_off_tool_calls(messages)

    assert repr(messages) == before


def test_the_request_the_client_builds_carries_no_cut_off_call() -> None:
    model = CompatibleChatOpenAI(model="m", api_key="k", base_url="http://localhost:1/v1")
    cut = AIMessage(
        content="",
        invalid_tool_calls=[{"name": "Plan", "args": '{"tasks": ["Given x', "id": "a", "error": None}],
    )

    payload = model._get_request_payload([HumanMessage("plan"), cut, HumanMessage("answer now")])

    assistant = payload["messages"][1]
    assert "tool_calls" not in assistant
    assert CUT_OFF_CALL_NOTE in assistant["content"]
