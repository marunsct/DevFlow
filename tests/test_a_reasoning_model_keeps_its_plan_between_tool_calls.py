"""A reasoning model's plan survives from one tool call to the next.

On one run 82% of every token the model produced was reasoning, and all of it
was dropped before the next call: `ChatOpenAI` discarded the server's
`reasoning_content`, and the LM Studio server ignores reasoning in every
input field. Measured with a codeword planted in a plan: sent as
`reasoning_content`, `reasoning` or `thinking` the model answered NONE; sent as
the tool-calling message's `content` it answered with the codeword.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.models import (
    REASONING_CARRIED_CHARS,
    REASONING_FIELD,
    CompatibleChatOpenAI,
)


def _model() -> CompatibleChatOpenAI:
    return CompatibleChatOpenAI(base_url="http://local:1234/v1", api_key="k", model="m")


def _response(reasoning: str | None, *, field: str = "reasoning_content") -> dict:
    message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}],
    }
    if reasoning is not None:
        message[field] = reasoning
    return {"id": "r", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls"}]}


class TestKeepingIt:
    def test_the_server_s_reasoning_is_kept_on_the_message(self) -> None:
        result = _model()._create_chat_result(_response("Read app.js next, then fix the filter."))
        assert result.generations[0].message.additional_kwargs[REASONING_FIELD] == "Read app.js next, then fix the filter."

    def test_the_other_field_name_is_read_too(self) -> None:
        result = _model()._create_chat_result(_response("plan", field="reasoning"))
        assert result.generations[0].message.additional_kwargs[REASONING_FIELD] == "plan"

    def test_its_end_is_kept_when_it_is_long(self) -> None:
        long = "x" * (REASONING_CARRIED_CHARS + 500) + "DECISION"
        kept = _model()._create_chat_result(_response(long)).generations[0].message.additional_kwargs[REASONING_FIELD]
        assert len(kept) == REASONING_CARRIED_CHARS and kept.endswith("DECISION")

    def test_a_reply_without_reasoning_carries_none(self) -> None:
        result = _model()._create_chat_result(_response(None))
        assert REASONING_FIELD not in result.generations[0].message.additional_kwargs


def _turn(n: int, reasoning: str | None = None, content: str = "") -> list:
    kwargs = {REASONING_FIELD: reasoning} if reasoning else {}
    return [
        AIMessage(content=content, tool_calls=[{"name": "read_file", "args": {"n": n}, "id": f"c{n}"}], additional_kwargs=kwargs),
        ToolMessage(content=f"result {n}", tool_call_id=f"c{n}"),
    ]


class TestSendingItBack:
    def test_it_goes_where_the_template_renders_it(self) -> None:
        conversation = [HumanMessage(content="Fix the bug."), *_turn(1, "PLAN: read app.js, then edit line 12.")]
        payload = _model()._get_request_payload(conversation)
        assistant = [m for m in payload["messages"] if m["role"] == "assistant"][0]
        assert assistant["content"] == "PLAN: read app.js, then edit line 12."

    def test_every_reply_since_the_last_answer_carries_it(self) -> None:
        conversation = [HumanMessage(content="Go.")]
        for n in range(7):
            conversation += _turn(n, f"plan {n}")
        payload = _model()._get_request_payload(conversation)
        carried = [m["content"] for m in payload["messages"] if m["role"] == "assistant"]
        assert carried == [f"plan {n}" for n in range(7)]

    def test_an_answer_ends_the_stretch_its_reasoning_belongs_to(self) -> None:
        conversation = [HumanMessage(content="Go."), *_turn(1, "old plan"),
                        AIMessage(content="Done with that."), HumanMessage(content="Next."), *_turn(2, "new plan")]
        payload = _model()._get_request_payload(conversation)
        carried = [m["content"] for m in payload["messages"] if m["role"] == "assistant"]
        assert carried == [None, "Done with that.", "new plan"]

    def test_a_message_once_sent_is_sent_the_same_way_every_time(self) -> None:
        """The first version carried the last four replies only, so the oldest
        lost its reasoning on every call and the server re-read the prompt from
        there: 6,390 tokens a request against 1,068 before it."""
        model, conversation, sent = _model(), [HumanMessage(content="Go.")], []
        for n in range(8):
            conversation += _turn(n, f"plan {n}")
            sent.append(model._get_request_payload(conversation)["messages"])
        for earlier, later in zip(sent, sent[1:]):
            assert later[: len(earlier)] == earlier

    def test_each_reply_carries_the_end_of_its_reasoning(self) -> None:
        long = "x" * (REASONING_CARRIED_CHARS * 3) + "NEXT: edit line 12"
        payload = _model()._get_request_payload([HumanMessage(content="Go."), *_turn(1, long)])
        carried = [m["content"] for m in payload["messages"] if m["role"] == "assistant"][0]
        assert len(carried) == REASONING_CARRIED_CHARS and carried.endswith("NEXT: edit line 12")

    def test_a_reply_that_said_something_keeps_its_own_words(self) -> None:
        conversation = [HumanMessage(content="Go."), *_turn(1, "hidden plan", content="Reading the file now.")]
        payload = _model()._get_request_payload(conversation)
        assert [m["content"] for m in payload["messages"] if m["role"] == "assistant"] == ["Reading the file now."]

    def test_the_stored_conversation_is_not_changed(self) -> None:
        conversation = [HumanMessage(content="Go."), *_turn(1, "plan")]
        _model()._get_request_payload(conversation)
        assert conversation[1].content == ""
