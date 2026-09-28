"""After a reply that reasoned until it was cut off, the next reply answers.

Measured on one run's `test_round_1`, with the reply ceiling at 25,000 tokens
and the thinking mode at `default` - the server launched with thinking on:

    15:59:07  reply 1: 25,000 output tokens, no text, no tool call
              -> tools withheld, "answer now from what you know"
              -> the workflow's nudge, which opened "Stop. You wrote your
                 answer into the conversation as text"
    16:02:25  reply 2: 25,000 output tokens, no text, no tool call
              -> run failed

Two things were wrong with that second call. Taking the tools away does not
stop a model reasoning, so it did the same again; and the nudge described a
failure that had not happened, to a model that had written nothing at all. The
failure message then said both attempts "hit the same ceiling each time",
when the first had ended on its model-call budget.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from app.agents.thinking import answering_without_reasoning


class _Answer(BaseModel):
    summary: str


def _local_model(**extra: Any):
    from app.models import CompatibleChatOpenAI

    return CompatibleChatOpenAI(
        base_url="http://model-server:8888/v1", api_key="k", model="m", max_tokens=10, **extra
    )


class TestHowThinkingIsSwitchedOff:
    def test_a_local_server_gets_the_template_flag(self) -> None:
        settings = answering_without_reasoning(_local_model())

        assert settings == {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}

    def test_what_the_client_already_sends_is_kept(self) -> None:
        """`extra_body` is replaced as a whole, so it must carry everything else."""
        model = _local_model(
            extra_body={"chat_template_kwargs": {"enable_thinking": True, "x": 1}, "top_k": 20}
        )

        settings = answering_without_reasoning(model)

        assert settings["extra_body"] == {
            "chat_template_kwargs": {"enable_thinking": False, "x": 1},
            "top_k": 20,
        }

    def test_the_setting_reaches_the_request_payload(self) -> None:
        """The whole mechanism rests on a per-call `extra_body` overriding the
        client's own - checked against the installed client, not assumed."""
        model = _local_model(extra_body={"chat_template_kwargs": {"enable_thinking": True}})

        payload = model._get_request_payload(
            [HumanMessage(content="hi")], **answering_without_reasoning(model)
        )

        assert payload["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False

    def test_a_hosted_openai_model_gets_nothing(self) -> None:
        """No base URL: not a llama.cpp template, and the field could be refused."""
        from app.models import CompatibleChatOpenAI

        hosted = CompatibleChatOpenAI(api_key="k", model="m", max_tokens=10)

        assert answering_without_reasoning(hosted) == {}

    def test_anthropic_gets_nothing(self) -> None:
        """Its thinking budget is always below the reply ceiling already."""
        from langchain_anthropic import ChatAnthropic

        model = ChatAnthropic(api_key="k", model="claude-haiku-4-5-20251001", max_tokens=4000)

        assert answering_without_reasoning(model) == {}

    def test_no_model_gets_nothing(self) -> None:
        assert answering_without_reasoning(None) == {}


class _Request:
    def __init__(self, messages: list, model: Any, tools: list | None = None, settings=None):
        self.messages = messages
        self.model = model
        self.tools = tools if tools is not None else [SimpleNamespace(name="read_file")]
        self.model_settings = settings or {}

    def override(self, **changes: Any) -> "_Request":
        return _Request(
            changes.get("messages", self.messages),
            changes.get("model", self.model),
            changes.get("tools", self.tools),
            changes.get("model_settings", self.model_settings),
        )


def _sent(messages: list, model: Any, settings: dict | None = None) -> _Request:
    from app.agents.settled_answer import build_settled_answer_middleware

    seen: dict[str, _Request] = {}

    def handler(request: _Request) -> Any:
        seen["request"] = request
        return SimpleNamespace(result=[])

    middleware = build_settled_answer_middleware(_Answer, "test_round_1", step_limit=40)
    middleware.wrap_model_call(_Request(messages, model, settings=settings), handler)
    return seen["request"]


def _spiral() -> AIMessage:
    return AIMessage(content="", response_metadata={"finish_reason": "length"})


class TestTheCallAfterASpiral:
    def test_thinking_is_off_for_it(self) -> None:
        """The regression: tools withheld, thinking left on, 25,000 tokens again."""
        sent = _sent([HumanMessage(content="Run the tests."), _spiral()], _local_model())

        assert sent.model_settings["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False

    def test_its_tools_are_still_withheld(self) -> None:
        sent = _sent([HumanMessage(content="Run the tests."), _spiral()], _local_model())

        assert sent.tools == []

    def test_other_model_settings_survive(self) -> None:
        sent = _sent(
            [HumanMessage(content="Run the tests."), _spiral()],
            _local_model(),
            settings={"parallel_tool_calls": False},
        )

        assert sent.model_settings["parallel_tool_calls"] is False

    def test_an_ordinary_call_is_left_alone(self) -> None:
        """Only the spiral switches thinking off. Every other call keeps the
        deployment's own setting."""
        answered = AIMessage(content="Running them now.", response_metadata={"finish_reason": "stop"})

        sent = _sent([HumanMessage(content="Run the tests."), answered], _local_model())

        assert "extra_body" not in sent.model_settings

    def test_a_reply_cut_off_after_writing_something_is_left_alone(self) -> None:
        """That reply landed near the ceiling, not in a spiral."""
        cut = AIMessage(content="The failures are", response_metadata={"finish_reason": "length"})

        sent = _sent([HumanMessage(content="Run the tests."), cut], _local_model())

        assert "extra_body" not in sent.model_settings


class TestWhatTheModelIsTold:
    def test_it_is_not_told_it_answered_in_prose(self) -> None:
        from app.graph.workflow import _nudge_text

        text = _nudge_text({"messages": [HumanMessage(content="x"), _spiral()]}, _Answer)

        assert "You wrote your answer into the conversation" not in text
        assert "You already have the answer above" not in text

    def test_it_is_told_what_did_happen(self) -> None:
        from app.graph.workflow import _nudge_text

        text = _nudge_text({"messages": [HumanMessage(content="x"), _spiral()]}, _Answer)

        assert "cut off" in text and "reasoning" in text
        assert "structured response" in text

    def test_a_prose_answer_still_gets_the_prose_nudge(self) -> None:
        from app.graph.workflow import _STRUCTURED_RESPONSE_NUDGE, _nudge_text

        prose = AIMessage(content="All tests pass.", response_metadata={"finish_reason": "stop"})

        assert _nudge_text({"messages": [prose]}, None) == _STRUCTURED_RESPONSE_NUDGE
