"""An auxiliary reply that is all reasoning is asked again with room to reason.

The framework list and a framework's notes are asked for in a small reply with
reasoning off. A model that reasons on every reply whatever it is asked spent
the whole 2,048-token cap thinking and wrote nothing (`finish_reason: length`,
no text), so the frameworks came back empty.
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.plugins import middleware


class AlwaysReasons:
    """Writes its answer only when the cap leaves room after its reasoning."""

    def __init__(self, max_tokens: int = middleware._AUXILIARY_REPLY_TOKENS, calls: list | None = None):
        self.max_tokens, self.extra_body, self.calls = max_tokens, None, calls if calls is not None else []

    def model_copy(self, update: dict[str, Any]) -> "AlwaysReasons":
        return AlwaysReasons(update.get("max_tokens", self.max_tokens), self.calls)

    def invoke(self, messages: Any, **kwargs: Any) -> AIMessage:
        self.calls.append(self.max_tokens)
        if self.max_tokens <= 3_000:
            return AIMessage(content="", response_metadata={"finish_reason": "length"})
        return AIMessage(content="fastapi, python, sqlite", response_metadata={"finish_reason": "stop"})


class Answers(AlwaysReasons):
    def invoke(self, messages: Any, **kwargs: Any) -> AIMessage:
        self.calls.append(self.max_tokens)
        return AIMessage(content="react, typescript", response_metadata={"finish_reason": "stop"})


def test_an_all_reasoning_reply_is_asked_once_more_with_room_and_answers():
    model = AlwaysReasons()

    reply = middleware._ask(model, [HumanMessage(content="the stack")])

    assert middleware._framework_names(middleware._text_of(reply)) == ["fastapi", "python", "sqlite"]
    assert model.calls == [middleware._AUXILIARY_REPLY_TOKENS, middleware._AUXILIARY_REPLY_TOKENS_WITH_REASONING]


def test_a_model_that_answers_is_asked_once():
    model = Answers()

    assert middleware._text_of(middleware._ask(model, [HumanMessage(content="the stack")])) == "react, typescript"
    assert model.calls == [middleware._AUXILIARY_REPLY_TOKENS]


def test_an_empty_reply_that_was_not_cut_is_not_asked_again():
    class SaysNothing(AlwaysReasons):
        def invoke(self, messages: Any, **kwargs: Any) -> AIMessage:
            self.calls.append(self.max_tokens)
            return AIMessage(content="", response_metadata={"finish_reason": "stop"})

    model = SaysNothing()
    middleware._ask(model, [HumanMessage(content="not a framework")])

    assert model.calls == [middleware._AUXILIARY_REPLY_TOKENS]
