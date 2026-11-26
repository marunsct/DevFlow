"""A read whose content is held back as a repeat counts toward the read rung.

Measured live: a fixer read one file fourteen times with the same arguments.
The last eleven came back "This file has given you these same bytes N times
... The content is not repeated here", which held the content back but never
said "Refusing to read" - so the read tool was never withheld, and the stage
ran out of its budget reading.
"""
from __future__ import annotations

from unittest import mock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents.settled_answer import READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL, build_settled_answer_middleware


class Verdict(BaseModel):
    status: str
    reason: str


class _Tool:
    def __init__(self, name):
        self.name = name


class _Request:
    def __init__(self, messages, tools):
        self.messages = messages
        self.tools = tools
        self.captured: dict = {}

    def override(self, **changes):
        self.captured.update(changes)
        other = _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))
        other.captured = self.captured
        return other


def _held_back(times):
    """A stage that read one unchanged file until the backend held its content back `times` times."""
    import tempfile
    from pathlib import Path

    from app.agents import stage_memory
    from app.agents.workspace_backend import READS_BEFORE_WITHHOLDING, WorkspaceBackend

    stage_memory.forget_everything()
    root = tempfile.mkdtemp()
    (Path(root) / "app.py").write_text("value = 1\n")
    backend = WorkspaceBackend(root_dir=root, virtual_mode=True)
    with mock.patch.object(stage_memory, "current_stage_key", lambda: ("t-1", "defect_fix_1_2")):
        answers = [backend.read("/app.py") for _ in range(READS_BEFORE_WITHHOLDING + times)]
    stage_memory.forget_everything()
    messages = [HumanMessage(content="fix it")]
    for i, answer in enumerate(answers[-times:] if times else []):
        content = ((getattr(answer, "file_data", None) or {}).get("content") or "") + (getattr(answer, "error", None) or "")
        messages.append(AIMessage(content="", id=f"a{i}"))
        messages.append(ToolMessage(content=content, tool_call_id=f"c{i}"))
    messages.append(AIMessage(content="reading again", id="last"))
    return messages


def _decided(messages):
    """What the next call is told, and the tools it lists."""
    request = _Request(messages, [_Tool("read_file"), _Tool("grep"), _Tool("write_artifact")])
    build_settled_answer_middleware(Verdict, "defect_fix_1_2", 40).wrap_model_call(request, lambda r: r)
    said = str((request.captured.get("messages") or [""])[-1])
    return said, {t.name for t in request.captured.get("tools", request.tools)}


def test_reads_held_back_as_repeats_turn_the_read_rung(monkeypatch):
    # STABLE_TOOLS off: this checks the bound tool list.
    monkeypatch.setenv("STABLE_TOOLS", "off")
    said, kept = _decided(_held_back(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL))

    # Since TR.2 the rung decides reads file by file and leaves the tool listed.
    assert "file by file" in said
    assert {"read_file", "grep", "write_artifact"} <= kept


def test_fewer_than_the_threshold_leave_reading_alone():
    said, kept = _decided(_held_back(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL - 1))

    assert "file by file" not in said and "read_file" in kept
