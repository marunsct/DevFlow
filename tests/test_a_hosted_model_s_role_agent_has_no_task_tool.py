"""A role agent on a hosted model's own client is not offered `task` either.

The general-purpose subagent was switched off for the `openai` provider key alone. A role agent on Anthropic's or
Google's own client reports another provider, so it was still offered `task` - the tool that once spent eleven and a
half minutes and 802 tool calls in one stage, unbounded by the stage's recursion limit.
"""
from __future__ import annotations

import pytest
from deepagents import create_deep_agent

from app.agents.role_agent import _disable_the_general_purpose_subagent


def _tool_names(agent) -> set[str]:
    names: set[str] = set()
    for node in getattr(agent, "nodes", {}).values():
        for attribute in ("tools_by_name", "_tools_by_name"):
            registry = getattr(getattr(node, "bound", node), attribute, None)
            if isinstance(registry, dict):
                names |= set(registry)
    return names


def _claude():
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(model="claude-opus-5-5", api_key="unused")


def _gemini():
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(model="gemini-x", google_api_key="unused")


@pytest.mark.parametrize("hosted", [_claude, _gemini], ids=["anthropic", "google"])
def test_a_role_agent_on_a_hosted_client_has_no_task_tool(hosted):
    _disable_the_general_purpose_subagent()
    names = _tool_names(create_deep_agent(model=hosted(), tools=[], system_prompt="s"))
    assert "task" not in names
    assert {"ls", "read_file", "glob", "grep"} <= names
