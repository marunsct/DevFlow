"""A stale edit after a `read_file`, and a writer that was another stage.

One run's `specialist_ui_ux_0`, in parallel mode, read `app.js` with
`read_file`. `specialist_testing_1` then edited it twice, and the ui stage's
edit came back "Could not find that text" with the nearest match - a JSDoc
block at the top of the file. Two gaps:

- `read_file` never recorded what it had shown, so the stale-edit check had
  nothing to compare with and stayed silent. Only `read_repository_file` and
  the write tools recorded it.
- the stale-edit message blamed "a command you ran", which was the only cause
  when stages ran one at a time.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.agents import stage_memory
from app.agents.workspace_backend import WorkspaceBackend
from app.analysis import project_memory
from app.tools.repository import RepositoryToolError, edit_approved_artifact

BEFORE = "export function a() {\n  return 1;\n}\n\nexport function b() {\n  return 2;\n}\n"
AFTER = "export function a() {\n  return 10;\n}\n\nexport function b() {\n  return 2;\n}\n"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch):
    stage_memory.forget_everything()
    key = f"t-{uuid.uuid4()}:specialist_ui_ux_0"
    monkeypatch.setattr(stage_memory, "current_stage_key", lambda: key)
    (tmp_path / "todo-list").mkdir()
    (tmp_path / "todo-list" / "app.js").write_text(BEFORE, encoding="utf-8")
    yield tmp_path
    stage_memory.forget_everything()


def _stale_edit(root: Path) -> str:
    with pytest.raises(RepositoryToolError) as caught:
        edit_approved_artifact(
            root, "todo-list/app.js", "  return 1;\n}\n", "  return 100;\n}\n"
        )
    return str(caught.value)


def _read_then_changed_by(root: Path, writer: str, offset: int = 0, limit: int = 2000) -> None:
    backend = WorkspaceBackend(root_dir=str(root), virtual_mode=True)
    assert not backend.read("/todo-list/app.js", offset=offset, limit=limit).error
    (root / "todo-list" / "app.js").write_text(AFTER, encoding="utf-8")
    if writer:
        project_memory.record(root, "todo-list/app.js", writer)


class TestReadFileIsRemembered:
    def test_a_stale_edit_after_read_file_says_the_file_changed(self, workspace):
        _read_then_changed_by(workspace, "")

        assert "changed after you last read it" in _stale_edit(workspace)

    def test_a_ranged_read_counts_as_having_seen_the_file(self, workspace):
        _read_then_changed_by(workspace, "", offset=4, limit=2)

        assert "changed after you last read it" in _stale_edit(workspace)

    def test_an_unchanged_file_keeps_the_ordinary_message(self, workspace):
        backend = WorkspaceBackend(root_dir=str(workspace), virtual_mode=True)
        backend.read("/todo-list/app.js")

        with pytest.raises(RepositoryToolError) as caught:
            edit_approved_artifact(
                workspace, "todo-list/app.js", "  return 99;\n}\n", "  return 100;\n}\n"
            )

        assert "changed after you last read it" not in str(caught.value)


class TestTheWriterIsNamed:
    def test_another_stage_is_named(self, workspace, monkeypatch):
        monkeypatch.setattr(
            "app.observability.transcript._stage_from_config", lambda fallback: "specialist_ui_ux_0"
        )
        _read_then_changed_by(workspace, "specialist_testing_1")

        message = _stale_edit(workspace)

        assert "'specialist_testing_1', a stage working alongside you" in message
        assert "a command you ran" not in message

    def test_its_own_last_write_still_blames_a_command(self, workspace, monkeypatch):
        """It wrote last, so something it ran changed the file since."""
        monkeypatch.setattr(
            "app.observability.transcript._stage_from_config", lambda fallback: "specialist_ui_ux_0"
        )
        _read_then_changed_by(workspace, "specialist_ui_ux_0")

        assert "a command you ran" in _stale_edit(workspace)

    def test_no_recorded_writer_blames_a_command(self, workspace):
        _read_then_changed_by(workspace, "")

        assert "a command you ran" in _stale_edit(workspace)
