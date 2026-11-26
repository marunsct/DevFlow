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


def test_once_the_stage_is_refused_enough_its_reads_are_decided_per_file(monkeypatch) -> None:
    """TR.2 (LF.1517): withholding the whole tool refused 51 of 85 reads of files whose text the request no longer
    held; the read tool now stays listed and each read is decided by what the conversation holds."""
    # STABLE_TOOLS off: this checks the bound tool list.
    monkeypatch.setenv("STABLE_TOOLS", "off")
    captured = _call(_conversation(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL))

    assert "tools" not in captured, "every tool stays listed: grep, the listings, the writers and the readers"
    assert "file by file" in str(captured["messages"][-1])


def test_a_stage_below_the_threshold_is_told_nothing_about_reading() -> None:
    captured = _call(_conversation(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL - 1))

    assert "file by file" not in str(captured.get("messages", [""])[-1])


def test_a_stage_below_the_threshold_keeps_everything() -> None:
    captured = _call(_conversation(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL - 1))

    assert "tools" not in captured


def test_a_stage_that_was_never_refused_keeps_everything() -> None:
    assert "tools" not in _call(_conversation(0))


def test_the_model_is_told_how_reads_are_decided() -> None:
    """A tool that changes how it answers with no explanation is a tool the model keeps calling as before."""
    captured = _call(_conversation(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL))
    said = str(captured["messages"][-1])

    assert "file by file" in said
    assert "can still be read" in said
    assert "still work" not in said, "what may be called is said once, by the call's own list (TR.3)"


def test_it_does_not_narrow_a_request_that_has_no_read_tool() -> None:
    """A request already narrowed - by the budget rung, say - is not narrowed
    again into something the model cannot act with at all."""
    captured = _call(
        _conversation(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL),
        tools=[_Tool("grep"), _Tool("edit_artifact")],
    )

    assert "tools" not in captured


def test_the_budget_rung_still_wins(monkeypatch) -> None:
    """At the end of the budget every tool goes, not just the readers."""
    # STABLE_TOOLS off: this checks the bound tool list, which that fix keeps whole (it refuses a withheld call).
    monkeypatch.setenv("STABLE_TOOLS", "off")
    messages = _conversation(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL)
    messages += [AIMessage(content="x", id=f"b{i}") for i in range(40)]

    assert _call(messages).get("tools") == []


def test_every_refusal_the_backend_writes_carries_the_marker_the_count_reads(tmp_path) -> None:
    """Counting a message by a phrase written somewhere else is how a marker
    goes stale silently."""
    from app.agents.workspace_backend import WorkspaceBackend

    (tmp_path / "app.js").write_text("const a = 1;\n")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)
    refused = [error for error in (backend.read("/app.js").error for _ in range(30)) if error]

    # The marker is the contract between the backend that refuses and the middleware that counts refusals.
    assert len(refused) >= READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL
    assert all(READ_REFUSED_MARKER in error for error in refused)
