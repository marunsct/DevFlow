"""A reply of several calls sent again and again, each answered the same, is noticed as a single call is.

Measured on one run: a stage sent the same two searches seven times in a row; compared call by call, the pair
(A, B, A, B, ...) never ran past one, and nothing withheld them.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.settled_answer import SAME_CALL_SAME_ANSWER_RUNNING, _the_same_call_answered_the_same


def _reply(n: int, pattern_b: str = "^class TestShutdown") -> list[object]:
    return [
        AIMessage(content="", tool_calls=[
            {"name": "grep", "args": {"pattern": "signal.signal"}, "id": f"a{n}"},
            {"name": "grep", "args": {"pattern": pattern_b}, "id": f"b{n}"},
        ]),
        ToolMessage(content="tests/test_main.py:12: signal.signal(...)", tool_call_id=f"a{n}"),
        ToolMessage(content="tests/test_main.py:880: class TestShutdown:", tool_call_id=f"b{n}"),
    ]


def test_the_same_pair_answered_the_same_is_noticed():
    messages = [HumanMessage(content="write the tests")]
    for n in range(SAME_CALL_SAME_ANSWER_RUNNING):
        messages += _reply(n)
    assert _the_same_call_answered_the_same(messages) == ("grep", SAME_CALL_SAME_ANSWER_RUNNING)


def test_fewer_repeats_or_a_changed_pair_is_not():
    short = [HumanMessage(content="x")] + [m for n in range(SAME_CALL_SAME_ANSWER_RUNNING - 1) for m in _reply(n)]
    assert _the_same_call_answered_the_same(short) is None
    changed = [HumanMessage(content="x")] + [m for n in range(SAME_CALL_SAME_ANSWER_RUNNING) for m in _reply(n, f"p{n}")]
    assert _the_same_call_answered_the_same(changed) is None
