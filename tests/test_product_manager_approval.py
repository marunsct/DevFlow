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

from app.agents.approval import decisions_for
from app.agents.product_manager import (
    approve_write_decision,
    edit_write_decision,
    extract_pending_approval,
    reject_write_decision,
    resume_with_decision,
)
from app.state import ApprovalDecision
from app.tools.agent_toolkit import build_artifact_edit_tool, build_artifact_write_tool


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


def _artifact(base: Path, filename: str) -> Path:
    return base / filename


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
    assert _artifact(tmp_path, "brief.md").read_text() == "hello\n"


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

    assert _artifact(tmp_path, "final.md").read_text() == "polished content\n"
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
    assert _artifact(tmp_path, "brief.md").read_text() == "hello\n"


def test_extract_pending_approval_describes_the_paused_write(tmp_path: Path) -> None:
    agent = _build_write_agent(
        tmp_path,
        responses=[_write_call("brief.md", "hello world"), AIMessage(content="done")],
    )
    config = {"configurable": {"thread_id": "thread-extract"}}

    paused = agent.invoke({"messages": [{"role": "user", "content": "please save"}]}, config)
    approval = extract_pending_approval(paused, tmp_path)

    assert approval is not None
    assert approval.artifact_path == "brief.md"
    assert approval.risk_level == "low"
    assert approval.decision == ApprovalDecision.PENDING
    # Prefixed with the action and its target: one pause can hold several
    # calls, and a bare content snippet cannot say which one it belongs to.
    assert approval.notes == "Write brief.md: hello world"


# ---------------------------------------------------------------------------
# Several gated calls in one turn
#
# `HumanInTheLoopMiddleware` raises ONE interrupt for a turn and attaches every
# gated call in it to that interrupt, then demands exactly one decision per call
# on resume. While `write_artifact` was the only mutation tool this never came
# up: replacing a whole file is naturally one call per turn. The moment agents
# could edit passages, a real architect asked for seven edits in a single turn -
# correct behaviour - and the run died on
# `ValueError: Number of human decisions (1) does not match number of hanging
# tool calls (7).`
# ---------------------------------------------------------------------------


def _edit_calls(*edits: tuple[str, str, str]) -> AIMessage:
    """One AIMessage asking for several `edit_artifact` calls at once."""
    return AIMessage(
        content="",
        tool_calls=[
            ToolCall(
                name="edit_artifact",
                args={"relative_path": path, "find": find, "replace": replace},
                id=f"call_{index}",
                type="tool_call",
            )
            for index, (path, find, replace) in enumerate(edits)
        ],
    )


def _build_edit_agent(tmp_path: Path, responses: list[AIMessage]):
    return create_deep_agent(
        model=_ScriptedToolCallingModel(responses=responses),
        tools=[build_artifact_edit_tool(str(tmp_path))],
        interrupt_on={
            "edit_artifact": {"allowed_decisions": ["approve", "edit", "reject"]},
        },
        checkpointer=InMemorySaver(),
    )


def test_one_approval_answers_every_gated_call_in_the_turn(tmp_path: Path) -> None:
    (tmp_path / "spec.md").write_text("alpha\nbravo\ncharlie\n")
    agent = _build_edit_agent(
        tmp_path,
        [
            _edit_calls(
                ("spec.md", "alpha", "ALPHA"),
                ("spec.md", "bravo", "BRAVO"),
                ("spec.md", "charlie", "CHARLIE"),
            ),
            AIMessage(content="All three applied."),
        ],
    )
    config = {"configurable": {"thread_id": "thread-batch-approve"}}

    paused = agent.invoke({"messages": [{"role": "user", "content": "fix these"}]}, config)
    assert "__interrupt__" in paused

    result = resume_with_decision(agent, "thread-batch-approve", approve_write_decision())

    assert not result.get("__interrupt__")
    assert (tmp_path / "spec.md").read_text() == "ALPHA\nBRAVO\nCHARLIE\n"


def test_one_rejection_blocks_every_gated_call_in_the_turn(tmp_path: Path) -> None:
    (tmp_path / "spec.md").write_text("alpha\nbravo\n")
    agent = _build_edit_agent(
        tmp_path,
        [
            _edit_calls(("spec.md", "alpha", "ALPHA"), ("spec.md", "bravo", "BRAVO")),
            AIMessage(content="Understood."),
        ],
    )
    config = {"configurable": {"thread_id": "thread-batch-reject"}}

    agent.invoke({"messages": [{"role": "user", "content": "fix these"}]}, config)
    resume_with_decision(agent, "thread-batch-reject", reject_write_decision("not yet"))

    assert (tmp_path / "spec.md").read_text() == "alpha\nbravo\n"


def test_an_edit_decision_refuses_to_answer_a_batch() -> None:
    """One replacement action cannot stand in for several different calls.

    Replicating it the way approve and reject are replicated would apply one
    edit's arguments to every call in the turn, writing the wrong thing to all
    but one of them - silently, and to files the reviewer never looked at.
    """
    import pytest

    with pytest.raises(ValueError, match="can only answer one"):
        decisions_for(edit_write_decision("final.md", "content"), 3)


def test_a_single_decision_is_left_alone() -> None:
    decision = approve_write_decision()
    assert decisions_for(decision, 1) == [decision]
    assert decisions_for(decision, 0) == [decision]


def test_the_approval_shown_to_a_reviewer_lists_every_pending_change(tmp_path: Path) -> None:
    """A reviewer approving a batch is consenting to all of it, so must see all of it."""
    (tmp_path / "spec.md").write_text("alpha\nbravo\n")
    agent = _build_edit_agent(
        tmp_path,
        [_edit_calls(("spec.md", "alpha", "ALPHA"), ("notes.md", "bravo", "BRAVO"))],
    )
    config = {"configurable": {"thread_id": "thread-batch-describe"}}

    paused = agent.invoke({"messages": [{"role": "user", "content": "fix these"}]}, config)
    approval = extract_pending_approval(paused, tmp_path)

    assert approval is not None
    assert approval.artifact_path == "spec.md (+1 more)"
    assert "2 changes in one step" in approval.notes
    assert "alpha" in approval.notes and "ALPHA" in approval.notes
    assert "bravo" in approval.notes and "BRAVO" in approval.notes


def test_the_brief_shows_no_filename_for_the_document() -> None:
    """A path the agent cannot read, and must not write.

    `source_path` is where the upload landed on the HOST
    (`/app/data/uploads/brief_low_752e3b83.md`). Inside the agent every path
    resolves against a workspace rooted at "/", so reading it answers "not
    found" and writing it would build a mirror of the host layout inside the
    workspace - which is what one run actually did.

    Measured across three runs: the product
    manager opens by trying to read that exact string and gets an error for its
    first tool call of the run. The rule was already stated one line below, for
    the repository's path; the document's was left as it was.

    That fix showed the upload's *basename* instead, on the reasoning that a
    name was safe where a path was not. One run shows it was not: the
    stored basename carries an upload suffix, names nothing in a workspace
    rooted at "/", and `product_manager` spent its first two calls on
    `read_file` and then `glob` for that exact string. So no filename is shown
    at all now - a filename in a prompt is an affordance, and the document's
    text is already quoted in full.
    """
    from app.agents.product_manager import build_intake_request

    class Document:
        source_path = "/app/data/uploads/brief_low_752e3b83.md"
        source_type = "markdown"
        text = "Build a to-do list."
        truncated = False
        truncation_note = None

    class Repository:
        branch = "master"
        commit = "abc1234"
        root_path = "/app/data/workspaces/t18-run-1"
        files = []

    request = build_intake_request(Document(), Repository())
    rendered = str(request)

    assert "brief_low_752e3b83" not in rendered
    assert "/app/data/uploads" not in rendered
    # The document itself still reaches the agent; only its name is withheld.
    assert "Build a to-do list." in rendered
    # The repository's host path was already withheld; keep it that way.
    assert "/app/data/workspaces" not in rendered
