"""An explicit plan a stage keeps: opt-in, and honestly unproven.

No measurement supports this yet, and the tests say so rather than implying
otherwise. What they do assert is that it is off unless asked for, that
turning it on cannot break a stage, and that the prompt says the things this
harness has actually been burned by - because if it is ever switched on, the
prompt is the whole of the intervention.
"""

from __future__ import annotations

import pytest

from app.agents.task_list import (
    TASK_LIST_PROMPT,
    build_task_list_middleware,
    task_list_enabled,
)


def test_it_is_off_unless_asked_for(monkeypatch):
    monkeypatch.delenv("HARNESS_TASK_LIST", raising=False)

    assert not task_list_enabled()
    assert build_task_list_middleware() == []


@pytest.mark.parametrize("setting", ["1", "true", "yes", "on", "TRUE", " On "])
def test_an_operator_can_turn_it_on(monkeypatch, setting: str):
    monkeypatch.setenv("HARNESS_TASK_LIST", setting)

    assert task_list_enabled()
    built = build_task_list_middleware()
    assert len(built) == 1
    assert type(built[0]).__name__ == "TodoListMiddleware"


@pytest.mark.parametrize("setting", ["0", "false", "no", "off", "", "maybe"])
def test_anything_else_leaves_it_off(monkeypatch, setting: str):
    monkeypatch.setenv("HARNESS_TASK_LIST", setting)

    assert not task_list_enabled()


def test_the_tool_it_adds_is_callable_in_a_synchronous_harness():
    """The reason Part II's MCP tools are unusable here, checked for this one.

    `langchain-mcp-adapters` builds a `StructuredTool` with a `coroutine` and
    no `func`, which raises `NotImplementedError: StructuredTool does not
    support sync invocation` under this harness's `agent.invoke` control
    plane. This middleware's tool must not have that shape.
    """
    from langchain.agents.middleware.todo import write_todos

    assert getattr(write_todos, "func", None) is not None, (
        "a tool with only a coroutine cannot be called by this control plane"
    )


def test_an_absent_middleware_does_not_stop_a_stage(monkeypatch):
    """The harness worked without this yesterday and must still work today."""
    monkeypatch.setenv("HARNESS_TASK_LIST", "true")
    import builtins

    real_import = builtins.__import__

    def _no_todo(name, *args, **kwargs):
        if name == "langchain.agents.middleware":
            raise ImportError("no such middleware")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_todo)

    assert build_task_list_middleware() == []


@pytest.mark.parametrize(
    "phrase",
    [
        # Evidence, not authorship. Marking "written" as "works" is how a
        # stage reports finished work that does not run.
        "when its evidence exists",
        # A plan edited to fit the outcome tells the next stage nothing.
        "do not reword it to match what",
        # The plan is the sprint's, not a new one the stage invents.
        "The sprint plan you were given is the task list",
        # Every rewrite is a model call out of a budget of forty.
        "every rewrite is a model call",
        # The list is not the deliverable.
        "structured response",
    ],
)
def test_the_prompt_says_what_this_harness_has_been_burned_by(phrase: str):
    assert phrase in TASK_LIST_PROMPT


def test_the_prompt_is_ours_and_not_the_default():
    """The default is addressed to a chat assistant, not to a gated stage."""
    from langchain.agents.middleware.todo import WRITE_TODOS_SYSTEM_PROMPT

    assert TASK_LIST_PROMPT != WRITE_TODOS_SYSTEM_PROMPT


def test_it_goes_last_in_the_chain(monkeypatch):
    """It must not displace anything the rest of the chain depends on."""
    import inspect

    from app.agents import role_agent

    source = inspect.getsource(role_agent)
    settled = source.index("build_settled_answer_middleware(response_format")
    task = source.index("*build_task_list_middleware()")

    assert task > settled
