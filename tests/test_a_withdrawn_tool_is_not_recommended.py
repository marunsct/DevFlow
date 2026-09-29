"""A stage whose read tool was withdrawn is not told to use it.

One run's `defect_fix_2_2` was refused three re-reads of files it already held,
and the harness withheld `read_file` for the rest of the stage. It then asked
`read_command_output` for `simple-todo-list/app.js (425 lines)` - copied from
the workspace listing - and was told "read it with `read_file`": the tool it no
longer had.
"""

from __future__ import annotations

import inspect
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


def test_the_middleware_records_it_where_it_withholds() -> None:
    source = inspect.getsource(settled_answer)
    block = source.split("without_reads = _without_the_read_tools_in(kept)", 1)[1][:300]

    assert "_remember_the_read_tool_is_withheld()" in block
