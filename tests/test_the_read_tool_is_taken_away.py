"""Per-file guards redirect a reading loop. Taking the tool away ends it.

Measured on one run's `specialist_ui_ux_1`: 73 tool calls, 64 of them
reads. The ladder worked exactly as designed - note, withhold, then refuse -
and the stage read 30 more times after its first refusal:

    16  refused as redundant
    13  withheld as redundant
     1  returned content it had not seen

Across the earlier runs a withheld read sent the stage to a *different* file
61.5% of the time; the refusal that replaced that rung raised it to 81.2%
while cutting same-file retries from 30.0% to 6.2%. Neither stopped the loop.
What stopped it was the model-call budget withholding every tool, after which
the stage answered.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents.settled_answer import (
    READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL,
    build_settled_answer_middleware,
)
from app.agents.workspace_backend import READ_REFUSED_MARKER


class Verdict(BaseModel):
    status: str
    reason: str


class _Tool:
    def __init__(self, name: str) -> None:
        self.name = name


TOOLS = [
    _Tool("read_file"),
    _Tool("read_repository_file"),
    _Tool("grep"),
    _Tool("ls"),
    _Tool("edit_artifact"),
    _Tool("run_terminal_command"),
]


class _Request:
    def __init__(self, messages, tools=None):
        self.messages = messages
        self.tools = list(TOOLS if tools is None else tools)
        self.captured: dict = {}

    def override(self, **changes):
        self.captured.update(changes)
        other = _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))
        other.captured = self.captured
        return other


def _conversation(refusals: int) -> list:
    messages: list = [HumanMessage(content="build it")]
    for i in range(refusals):
        messages.append(AIMessage(content="", id=f"a{i}"))
        messages.append(
            ToolMessage(
                content=f"{READ_REFUSED_MARKER} 'app.js' again: this returns nothing you "
                "have not already been given.",
                tool_call_id=f"c{i}",
            )
        )
    messages.append(AIMessage(content="still reading", id="last"))
    return messages


def _call(messages, tools=None):
    request = _Request(messages, tools)
    build_settled_answer_middleware(Verdict, "specialist_ui_ux_1", 40).wrap_model_call(
        request, lambda r: r
    )
    return request.captured


def _names(captured):
    return {getattr(t, "name", "") for t in captured.get("tools", [])}


def test_the_read_tools_go_once_the_stage_is_refused_enough(  ) -> None:
    captured = _call(_conversation(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL))

    assert "read_file" not in _names(captured)
    assert "read_repository_file" not in _names(captured)


def test_grep_and_the_listings_stay() -> None:
    """The refusal's own words are "a range you have NOT read still works, and
    so does `grep`". A harness that says that and removes `grep` is the
    contradiction this file keeps finding elsewhere."""
    kept = _names(_call(_conversation(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL)))

    assert "grep" in kept
    assert "ls" in kept


def test_the_tools_that_change_things_stay() -> None:
    kept = _names(_call(_conversation(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL)))

    assert "edit_artifact" in kept
    assert "run_terminal_command" in kept


def test_a_stage_below_the_threshold_keeps_everything() -> None:
    captured = _call(_conversation(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL - 1))

    assert "tools" not in captured


def test_a_stage_that_was_never_refused_keeps_everything() -> None:
    assert "tools" not in _call(_conversation(0))


def test_the_model_is_told_the_tool_is_gone() -> None:
    """A tool that vanishes with no explanation is a tool the model keeps
    trying to call."""
    captured = _call(_conversation(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL))
    said = str(captured["messages"][-1])

    assert "withheld for the rest of this stage" in said
    assert "grep" in said
    assert "`blockers`" in said


def test_it_does_not_narrow_a_request_that_has_no_read_tool() -> None:
    """A request already narrowed - by the budget rung, say - is not narrowed
    again into something the model cannot act with at all."""
    captured = _call(
        _conversation(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL),
        tools=[_Tool("grep"), _Tool("edit_artifact")],
    )

    assert "tools" not in captured


def test_the_budget_rung_still_wins() -> None:
    """At the end of the budget every tool goes, not just the readers."""
    messages = _conversation(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL)
    messages += [AIMessage(content="x", id=f"b{i}") for i in range(40)]

    assert _call(messages).get("tools") == []


def test_the_marker_is_the_one_the_backend_writes() -> None:
    """Counting a message by a phrase written somewhere else is how a marker
    goes stale silently."""
    import inspect

    from app.agents.workspace_backend import WorkspaceBackend

    source = inspect.getsource(WorkspaceBackend._refuse_a_read_that_returns_nothing_new)

    assert "READ_REFUSED_MARKER" in source
