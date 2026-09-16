"""A tool call the model wrote as text, recovered into a real one.

Some OpenAI-compatible servers do not parse a model's tool-call syntax into the
`tool_calls` field. Measured on run 40, Qwen2.5-Coder-7B-Instruct-128K through
LM Studio, asked for the weather with a tool bound:

    tool_calls: None
    content   : '<tools>\\n{"name": "get_weather", "arguments": {...}}\\n</tools>'

The call is right in every respect except the envelope. That run reached
`stack_selector` on answer recovery alone and never wrote a file, because no
tool it asked for ever ran.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from app.agents.text_tool_calls import tool_calls_in_text

KNOWN = {"get_weather", "ls"}


def test_the_exact_shape_run_40_returned() -> None:
    calls = tool_calls_in_text(
        '<tools>\n{"name": "get_weather", "arguments": {"location": "Paris"}}\n</tools>',
        KNOWN,
    )

    assert [(c["name"], c["args"]) for c in calls] == [("get_weather", {"location": "Paris"})]


@pytest.mark.parametrize(
    "content",
    [
        '<tool_call>{"name":"ls","arguments":{"path":"/"}}</tool_call>',
        '```json\n{"name":"ls","arguments":{"path":"/"}}\n```',
        '{"name":"ls","arguments":{"path":"/"}}',
        '<tools>{"name":"ls","parameters":{"path":"/"}}</tools>',
        '<tools>{"name":"ls","arguments":"{\\"path\\": \\"/\\"}"}</tools>',
    ],
)
def test_the_wrappers_and_spellings_seen_in_the_wild(content: str) -> None:
    calls = tool_calls_in_text(content, KNOWN)

    assert len(calls) == 1 and calls[0]["name"] == "ls"


@pytest.mark.parametrize(
    "content",
    [
        "I will use the get_weather tool for Paris.",
        '<tools>{"name":"not_a_real_tool","arguments":{}}</tools>',
        'Here is some JSON: {"name":"ls"} in a sentence.',
        "The ls command lists files.",
        "",
    ],
)
def test_prose_and_unknown_names_are_not_calls(content: str) -> None:
    """Requiring a name the agent actually has is what keeps discussion of a
    tool from becoming a call to it."""
    assert tool_calls_in_text(content, KNOWN) == []


def test_two_calls_in_one_message_are_both_recovered() -> None:
    calls = tool_calls_in_text(
        '<tools>{"name":"ls","arguments":{"path":"/a"}}</tools>\n'
        '<tools>{"name":"ls","arguments":{"path":"/b"}}</tools>',
        KNOWN,
    )

    assert [c["args"]["path"] for c in calls] == ["/a", "/b"]


def test_each_recovered_call_gets_its_own_id() -> None:
    """Two calls sharing an id pair both results to one, and the second is lost."""
    calls = tool_calls_in_text(
        '<tools>{"name":"ls","arguments":{"path":"/a"}}\n'
        '{"name":"ls","arguments":{"path":"/b"}}</tools>',
        KNOWN,
    )

    assert len({c["id"] for c in calls}) == len(calls) == 2


# --- the integration, which is where the last regression of this kind hid ---


@tool
def get_weather(location: str) -> str:
    """Get the weather for a location."""
    return f"sunny in {location}"


class _TextToolCallModel(GenericFakeChatModel):
    """A server that fails to parse tool calls, then answers normally."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:  # noqa: ARG002
        return self


def test_a_real_agent_runs_a_tool_the_server_failed_to_parse() -> None:
    """Component tests passed for the streaming default that broke every run.

    The agent path is the one that matters: this asserts the tool actually
    executed and its result came back, not merely that a string parsed.
    """
    from langchain.agents import create_agent

    from app.agents.text_tool_calls import build_text_tool_call_middleware

    model = _TextToolCallModel(
        messages=iter(
            [
                AIMessage(
                    content='<tools>\n{"name": "get_weather", '
                    '"arguments": {"location": "Paris"}}\n</tools>'
                ),
                AIMessage(content="It is sunny in Paris."),
            ]
        )
    )
    agent = create_agent(
        model=model,
        tools=[get_weather],
        middleware=[build_text_tool_call_middleware()],
    )

    result = agent.invoke({"messages": [{"role": "user", "content": "weather in Paris?"}]})

    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_messages, "the tool never ran"
    assert "sunny in Paris" in tool_messages[0].content


def test_a_correctly_parsed_call_is_left_untouched() -> None:
    """On a working server this must be dead weight, not a second parser."""
    from langchain.agents import create_agent

    from app.agents.text_tool_calls import build_text_tool_call_middleware

    model = _TextToolCallModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_weather",
                            "args": {"location": "Oslo"},
                            "id": "call_1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="It is sunny in Oslo."),
            ]
        )
    )
    agent = create_agent(
        model=model,
        tools=[get_weather],
        middleware=[build_text_tool_call_middleware()],
    )

    result = agent.invoke({"messages": [{"role": "user", "content": "weather in Oslo?"}]})

    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_messages[0].tool_call_id == "call_1"
    assert "sunny in Oslo" in tool_messages[0].content


def test_every_role_agent_gets_it() -> None:
    import inspect

    from app.agents.role_agent import create_role_agent

    assert "build_text_tool_call_middleware()" in inspect.getsource(create_role_agent)
