"""A reply cut at its length limit is shown to the next call as its head and a note, not carried whole.

One stage's first reply repeated a three-character string until 107,596 tokens
were spent; the next call was handed all 205,682 characters of it and its own
reply repeated one block 102 times. A cut reply is never an answer.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents import settled_answer
from app.agents.settled_answer import CUT_REPLY_KEPT, build_settled_answer_middleware

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
LOOPED = '{\n  "product_scope": "Notes API",\n  "notes": [' + '" - ' * 60_000
_WORDS = "store note title body change route health restart keep list fetch delete reply field value error check order newest".split()
_RANDOM = __import__("random").Random(7)
LONG_PROSE = " ".join(_RANDOM.choice(_WORDS) + str(_RANDOM.randint(0, 999)) for _ in range(3_000))


def _cut(text: str) -> AIMessage:
    return AIMessage(content=text, response_metadata={"finish_reason": "length"})


@dataclass
class Request:
    messages: list[Any]
    model: Any = None
    model_settings: dict = field(default_factory=dict)
    tools: list = field(default_factory=list)

    def override(self, **changes: Any) -> "Request":
        return replace(self, **changes)


class Answer(BaseModel):
    product_scope: str


def _sent(messages: list[Any]) -> list[Any]:
    seen: list[Any] = []

    def handler(request: Any) -> Any:
        seen.extend(request.messages)
        return AIMessage(content=json.dumps({"product_scope": "x"}))

    build_settled_answer_middleware(Answer, "principal_architect").wrap_model_call(Request(messages), handler)
    return seen


def test_a_looping_reply_reaches_the_next_call_as_its_head_and_a_note():
    sent = _sent([HumanMessage(content="write the specification"), _cut(LOOPED)])

    shown = sent[-1].content
    assert len(shown) < CUT_REPLY_KEPT + 600 and shown.startswith('{\n  "product_scope"')
    assert "repeated the same text" in shown and "Write the answer again" in shown


def test_a_long_reply_that_ran_out_of_room_is_cut_too_and_named_so():
    shown = _sent([HumanMessage(content="go"), _cut(LONG_PROSE)])[-1].content

    assert len(shown) < CUT_REPLY_KEPT + 600 and "ran past the reply's length limit" in shown


def test_a_finished_reply_and_a_short_cut_one_are_untouched():
    finished = AIMessage(content=LOOPED)
    short = _cut("{ \"product_scope\": ")

    for message in (finished, short):
        assert settled_answer._the_cut_reply_shortened(message) is message


def _cut_with_a_call(text: str) -> AIMessage:
    return AIMessage(content=text, response_metadata={"finish_reason": "length"},
                     tool_calls=[{"name": "write_artifact", "args": {"relative_path": "src/app.js"}, "id": "c1"}])


def test_a_cut_reply_that_ends_in_a_call_reaches_the_next_call_as_its_head_and_its_call():
    """Measured on one builder: 123,226 characters of analysis before a call, all of them in the next request."""
    sent = _sent([HumanMessage(content="build it"), _cut_with_a_call(LONG_PROSE),
                  ToolMessage(content="Refusing: not run", tool_call_id="c1", name="write_artifact")])

    reply = next(m for m in sent if getattr(m, "type", None) == "ai")
    assert len(reply.content) < CUT_REPLY_KEPT + 600 and "ran past the reply's length limit" in reply.content
    assert [call["id"] for call in reply.tool_calls] == ["c1"]


def test_the_note_on_a_cut_reply_with_a_call_uses_none_of_the_banned_words():
    shown = settled_answer._the_cut_reply_shortened(_cut_with_a_call(LONG_PROSE)).content

    assert not BANNED.search(shown[CUT_REPLY_KEPT:])


def test_the_note_uses_none_of_the_banned_words():
    for text in (LOOPED, LONG_PROSE):
        assert not BANNED.search(settled_answer._the_cut_reply_shortened(_cut(text)).content[CUT_REPLY_KEPT:])
