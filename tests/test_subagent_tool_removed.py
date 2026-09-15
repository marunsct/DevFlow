"""No role agent gets a general-purpose subagent spawner.

`create_deep_agent` installs a `task` tool by default. No stage here needs
one: each is a single stage with one structured answer, its filesystem tools
are narrowed to `ls`, `read_file`, `glob` and `grep`, and every mutating call
is gated. `task` arrived with none of that.

Measured on run-d6369866's `scrum_master`. The stage produced a valid sprint
plan at 15:23:30, then in the same turn called `task`, and the subagent it
spawned ran `glob {'pattern': '**/*'}` 835 times over eleven and a half
minutes - 802 tool calls in one stage against 21 assistant messages, with zero
globs before the first `task` call.

Nothing bounded it. The parent's `recursion_limit` does not reach inside a
subagent, so no GraphRecursionError was ever raised; and the settled-answer
middleware reads the LAST message, which by then was prose about creating
files the stage has no tools to create.
"""

from __future__ import annotations

import pytest


def _tool_names(agent) -> set[str]:
    names: set[str] = set()
    for node in getattr(agent, "nodes", {}).values():
        for attribute in ("tools_by_name", "_tools_by_name"):
            registry = getattr(getattr(node, "bound", node), attribute, None)
            if isinstance(registry, dict):
                names |= set(registry)
    return names


@pytest.fixture
def model():
    from app.models import CompatibleChatOpenAI

    # No call is made; the profile lookup only needs the provider and name.
    return CompatibleChatOpenAI(
        model="Qwen3.5-9B-GGUF", api_key="unused", base_url="http://localhost:9/v1"
    )


def test_a_role_agent_has_no_task_tool(model) -> None:
    from deepagents import create_deep_agent

    from app.agents.role_agent import _disable_the_general_purpose_subagent

    _disable_the_general_purpose_subagent()
    agent = create_deep_agent(model=model, tools=[], system_prompt="s")

    assert "task" not in _tool_names(agent)


def test_the_tools_a_stage_does_need_are_untouched(model) -> None:
    """A guard that removed the filesystem tools would cost far more than the
    subagent ever did."""
    from deepagents import create_deep_agent

    from app.agents.role_agent import _disable_the_general_purpose_subagent

    _disable_the_general_purpose_subagent()
    names = _tool_names(create_deep_agent(model=model, tools=[], system_prompt="s"))

    assert {"ls", "read_file", "glob", "grep"} <= names


def test_registering_twice_is_harmless() -> None:
    """It runs before every agent build."""
    from app.agents.role_agent import _disable_the_general_purpose_subagent

    _disable_the_general_purpose_subagent()
    _disable_the_general_purpose_subagent()


def test_every_role_agent_build_disables_it_first() -> None:
    """Reaching twelve of thirteen builders is the mistake this codebase has
    made four times, so this asserts the call site rather than one agent."""
    import inspect

    from app.agents.role_agent import create_role_agent

    source = inspect.getsource(create_role_agent)
    assert "_disable_the_general_purpose_subagent()" in source
    assert source.index("_disable_the_general_purpose_subagent()") < source.index(
        "create_deep_agent("
    )
