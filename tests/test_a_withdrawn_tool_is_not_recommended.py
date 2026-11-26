"""A stage whose read tool was withdrawn is not told to use it.

One run's `defect_fix_2_2` was refused three re-reads of files it already held,
and the harness withheld `read_file` for the rest of the stage. It then asked
`read_command_output` for `simple-todo-list/app.js (425 lines)` - copied from
the workspace listing - and was told "read it with `read_file`": the tool it no
longer had.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from app.agents import settled_answer
from app.agents.stage_memory import remembering
from app.tools.agent_toolkit import _and_a_path_is_read_with_read_file


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "app.js").write_text("export {}\n", encoding="utf-8")
    return tmp_path


def test_before_withholding_it_still_names_read_file(tmp_path: Path) -> None:
    root = _workspace(tmp_path)

    with remembering(f"stage-{uuid.uuid4().hex}"):
        hint = _and_a_path_is_read_with_read_file("app/app.js (1 lines)", str(root))

    assert "read it with `read_file`" in hint


def test_after_withholding_it_says_the_content_is_already_there(tmp_path: Path) -> None:
    root = _workspace(tmp_path)

    with remembering(f"stage-{uuid.uuid4().hex}"):
        settled_answer._remember_the_read_tool_is_withheld()
        hint = _and_a_path_is_read_with_read_file("app/app.js (1 lines)", str(root))

    assert "read it with `read_file`" not in hint
    assert "its content is already in this conversation from your earlier reads" in hint
    assert "that is why `read_file` was withdrawn" in hint


def test_another_stage_is_not_affected(tmp_path: Path) -> None:
    root = _workspace(tmp_path)

    with remembering(f"stage-{uuid.uuid4().hex}"):
        settled_answer._remember_the_read_tool_is_withheld()
    with remembering(f"stage-{uuid.uuid4().hex}"):
        hint = _and_a_path_is_read_with_read_file("app/app.js", str(root))

    assert "read it with `read_file`" in hint


def test_while_reads_are_decided_per_file_the_stage_is_sent_to_the_read_tool(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    from pydantic import BaseModel

    from tests.test_a_tool_that_only_ever_fails_is_taken_away import TestTheReadOrdinalIsNotTheStages, _conversation

    monkeypatch.setenv("STABLE_TOOLS", "off")  # the bound tool list is what is withheld from

    class _Answer(BaseModel):
        ok: bool = True

    class _Request:
        def __init__(self, messages, tools):
            self.messages, self.tools, self.model, self.model_settings = messages, tools, None, {}

        def override(self, **changes):
            return _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))

    root = _workspace(tmp_path)
    refusal = TestTheReadOrdinalIsNotTheStages._refusal("3rd").content
    refused = _conversation(3, tool="read_file", args={"file_path": "app/app.js"}, result=refusal)
    messages = [SimpleNamespace(type="human", content="Fix the defect."), *refused]
    tools = [SimpleNamespace(name="read_file"), SimpleNamespace(name="edit_artifact")]
    sent: list = []
    middleware = settled_answer.build_settled_answer_middleware(_Answer, "defect_fix", step_limit=60)

    with remembering(f"stage-{uuid.uuid4().hex}"):
        middleware.wrap_model_call(_Request(messages, tools), sent.append)
        hint = _and_a_path_is_read_with_read_file("app/app.js (1 lines)", str(root))

    # Since TR.2 the read rung decides reads file by file: the tool stays, and a file not held can still be read.
    assert "read_file" in [tool.name for tool in sent[0].tools]
    assert "read it with `read_file`" in hint
