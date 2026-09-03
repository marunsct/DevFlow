"""Tests for human-approval gating on the Product Manager's artifact writes.

Step 3.2 adds a mandatory pause-before-write safety gate: `write_artifact` calls
must be approved, edited, or rejected by a human before anything is saved. These
tests use a scripted fake chat model instead of the slow real local model, so we
can exercise approve, edit, reject, and resume-with-the-same-thread-id
deterministically and in well under a second. The fake model only decides
whether and how to call `write_artifact`; the actual pausing, checkpointing, and
resume mechanics come from the real `deepagents`/`langgraph` code, so this still
proves our own wiring (`interrupt_on`, checkpointer, decision helpers) is wired
correctly without waiting on live inference.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.messages.tool import ToolCall
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agents.product_manager import (
    approve_write_decision,
    edit_write_decision,
    extract_pending_approval,
    reject_write_decision,
    resume_with_decision,
)
from app.state import ApprovalDecision
from app.tools.agent_toolkit import build_artifact_write_tool


class _ScriptedToolCallingModel(FakeMessagesListChatModel):
    """Fake chat model that replays scripted messages and ignores tool schemas.

    The real Deep Agents harness calls `model.bind_tools(...)` before every
    turn. The base `FakeMessagesListChatModel` does not implement `bind_tools`,
    so it raises `NotImplementedError`. Overriding it to return `self` lets the
    fake model act as a drop-in replacement for testing tool-calling flows
    without needing a real, slow model.
    """

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_ScriptedToolCallingModel":  # noqa: ARG002
        return self


def _write_call(relative_path: str, content: str, call_id: str = "call_1") -> AIMessage:
    """Build a scripted AIMessage that calls write_artifact with fixed arguments."""
    return AIMessage(
        content="",
        tool_calls=[
            ToolCall(
                name="write_artifact",
                args={"relative_path": relative_path, "content": content},
                id=call_id,
                type="tool_call",
            )
        ],
    )


def _build_write_agent(
    tmp_path: Path,
    responses: list[AIMessage] | None = None,
    checkpointer: InMemorySaver | None = None,
    model: _ScriptedToolCallingModel | None = None,
):
    """Build a minimal deep agent sharing the exact write_artifact + interrupt_on
    wiring used by the real Product Manager agent, with a scripted fake model
    swapped in so the test runs instantly instead of waiting on live inference.
    """
    return create_deep_agent(
        model=model or _ScriptedToolCallingModel(responses=responses or []),
        tools=[build_artifact_write_tool(str(tmp_path))],
        interrupt_on={
            "write_artifact": {"allowed_decisions": ["approve", "edit", "reject"]},
        },
        checkpointer=checkpointer or InMemorySaver(),
    )


def _artifact(tmp_path: Path, relative_path: str) -> Path:
    return tmp_path / "docs" / "generated" / relative_path


def test_approve_decision_writes_the_artifact(tmp_path: Path) -> None:
    agent = _build_write_agent(
        tmp_path,
        responses=[_write_call("brief.md", "hello"), AIMessage(content="Saved.")],
    )
    config = {"configurable": {"thread_id": "thread-approve"}}

    paused = agent.invoke({"messages": [{"role": "user", "content": "please save"}]}, config)
    assert "__interrupt__" in paused

    result = resume_with_decision(agent, "thread-approve", approve_write_decision())

    assert not result.get("__interrupt__")
    assert _artifact(tmp_path, "brief.md").read_text() == "hello"


def test_reject_decision_skips_the_write(tmp_path: Path) -> None:
    agent = _build_write_agent(
        tmp_path,
        responses=[_write_call("brief.md", "hello"), AIMessage(content="Understood, not saving.")],
    )
    config = {"configurable": {"thread_id": "thread-reject"}}

    agent.invoke({"messages": [{"role": "user", "content": "please save"}]}, config)
    resume_with_decision(agent, "thread-reject", reject_write_decision("not ready yet"))

    assert not _artifact(tmp_path, "brief.md").exists()


def test_edit_decision_changes_the_write_target(tmp_path: Path) -> None:
    agent = _build_write_agent(
        tmp_path,
        responses=[_write_call("wrong.md", "draft"), AIMessage(content="Saved with edits.")],
    )
    config = {"configurable": {"thread_id": "thread-edit"}}

    agent.invoke({"messages": [{"role": "user", "content": "please save"}]}, config)
    resume_with_decision(agent, "thread-edit", edit_write_decision("final.md", "polished content"))

    assert _artifact(tmp_path, "final.md").read_text() == "polished content"
    assert not _artifact(tmp_path, "wrong.md").exists()


def test_resume_after_new_agent_instance_with_same_thread_id(tmp_path: Path) -> None:
    """Simulates a process restart: a brand new compiled graph, sharing only the
    checkpointer, thread_id, and (like a real external model service) the model,
    must resume the paused run instead of losing it or redoing completed steps.
    """
    checkpointer = InMemorySaver()
    fake_model = _ScriptedToolCallingModel(
        responses=[_write_call("brief.md", "hello"), AIMessage(content="Saved.")]
    )

    first_agent = _build_write_agent(tmp_path, checkpointer=checkpointer, model=fake_model)
    config = {"configurable": {"thread_id": "thread-restart"}}
    paused = first_agent.invoke({"messages": [{"role": "user", "content": "please save"}]}, config)
    assert "__interrupt__" in paused

    # A brand-new graph object, as if the process had restarted, but backed by
    # the same checkpointer, thread_id, and model as the original run.
    second_agent = _build_write_agent(tmp_path, checkpointer=checkpointer, model=fake_model)
    result = second_agent.invoke(Command(resume={"decisions": [approve_write_decision()]}), config)

    assert not result.get("__interrupt__")
    assert _artifact(tmp_path, "brief.md").read_text() == "hello"


def test_extract_pending_approval_describes_the_paused_write(tmp_path: Path) -> None:
    agent = _build_write_agent(
        tmp_path,
        responses=[_write_call("brief.md", "hello world"), AIMessage(content="done")],
    )
    config = {"configurable": {"thread_id": "thread-extract"}}

    paused = agent.invoke({"messages": [{"role": "user", "content": "please save"}]}, config)
    approval = extract_pending_approval(paused, tmp_path)

    assert approval is not None
    assert approval.artifact_path == "docs/generated/brief.md"
    assert approval.risk_level == "low"
    assert approval.decision == ApprovalDecision.PENDING
    assert approval.notes == "hello world"
