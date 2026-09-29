"""A whole-file write over another stage's file this stage has not seen is refused.

In parallel mode, one run's `specialist_ui_ux_0` listed an empty workspace at
16:14, spent twelve minutes on one reply, and at 16:26 wrote
`todo-app/index.html` over the page `specialist_testing_4` had written at 16:25,
never having seen it. A page defines no functions, so the guard for a rewrite
that drops definitions had nothing to say.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.agents import stage_memory
from app.agents.workspace_backend import WorkspaceBackend
from app.analysis import project_memory
from app.tools.repository import (
    RepositoryToolError,
    read_text_file,
    write_approved_artifact,
)

THEIRS = "<!DOCTYPE html>\n<html><body><form id=\"task-form\"></form></body></html>\n"
MINE = "<!DOCTYPE html>\n<html><body><main id=\"app\"></main></body></html>\n"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch):
    stage_memory.forget_everything()
    key = f"t-{uuid.uuid4()}:specialist_ui_ux_0"
    monkeypatch.setattr(stage_memory, "current_stage_key", lambda: key)
    monkeypatch.setattr(
        "app.observability.transcript._stage_from_config", lambda fallback: "specialist_ui_ux_0"
    )
    (tmp_path / "todo-app").mkdir()
    (tmp_path / "todo-app" / "index.html").write_text(THEIRS, encoding="utf-8")
    project_memory.record(tmp_path, "todo-app/index.html", "specialist_testing_4")
    yield tmp_path
    stage_memory.forget_everything()


def _page(root: Path) -> str:
    return (root / "todo-app" / "index.html").read_text(encoding="utf-8")


class TestRefused:
    def test_an_unseen_file_of_another_stage_is_not_replaced(self, workspace):
        with pytest.raises(RepositoryToolError) as caught:
            write_approved_artifact(workspace, "todo-app/index.html", MINE)

        message = str(caught.value)
        assert "'specialist_testing_4' wrote the version there now" in message
        assert "Read it first" in message
        assert _page(workspace) == THEIRS

    def test_a_version_changed_since_it_was_read_is_not_replaced(self, workspace):
        read_text_file(workspace, "todo-app/index.html")
        (workspace / "todo-app" / "index.html").write_text(THEIRS + "<!-- more -->\n")
        project_memory.record(workspace, "todo-app/index.html", "specialist_testing_4")

        with pytest.raises(RepositoryToolError):
            write_approved_artifact(workspace, "todo-app/index.html", MINE)


class TestAllowed:
    def test_after_read_repository_file(self, workspace):
        read_text_file(workspace, "todo-app/index.html")

        write_approved_artifact(workspace, "todo-app/index.html", MINE)

        assert _page(workspace) == MINE

    def test_after_read_file(self, workspace):
        backend = WorkspaceBackend(root_dir=str(workspace), virtual_mode=True)
        assert not backend.read("/todo-app/index.html").error

        write_approved_artifact(workspace, "todo-app/index.html", MINE)

        assert _page(workspace) == MINE

    def test_its_own_file(self, workspace):
        project_memory.record(workspace, "todo-app/index.html", "specialist_ui_ux_0")

        write_approved_artifact(workspace, "todo-app/index.html", MINE)

        assert _page(workspace) == MINE

    def test_a_new_file(self, workspace):
        write_approved_artifact(workspace, "todo-app/about.html", MINE)

        assert (workspace / "todo-app" / "about.html").read_text(encoding="utf-8") == MINE

    def test_a_file_nobody_recorded(self, workspace, tmp_path):
        (workspace / "todo-app" / "notes.txt").write_text("x\n", encoding="utf-8")

        write_approved_artifact(workspace, "todo-app/notes.txt", "y\n")

    def test_outside_a_stage(self, workspace, monkeypatch):
        monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: "")

        write_approved_artifact(workspace, "todo-app/index.html", MINE)

        assert _page(workspace) == MINE
