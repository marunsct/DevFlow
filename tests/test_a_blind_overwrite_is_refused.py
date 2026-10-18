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
        assert _page(workspace) == THEIRS

    def test_a_short_file_is_shown_in_the_refusal(self, workspace):
        """"Read it first" cost a call the stage often did not make. One fix
        stage sent the same whole-file write of a 13-line manifest twice, tried
        to delete the file, and reported the change as blocked."""
        with pytest.raises(RepositoryToolError) as caught:
            write_approved_artifact(workspace, "todo-app/index.html", MINE)

        message = str(caught.value)
        assert '<form id="task-form">' in message
        assert "You have now seen it" in message
        assert "Read it first" not in message

    def test_having_been_shown_it_the_next_write_is_a_decision(self, workspace):
        with pytest.raises(RepositoryToolError):
            write_approved_artifact(workspace, "todo-app/index.html", MINE)

        write_approved_artifact(workspace, "todo-app/index.html", MINE)

        assert _page(workspace) == MINE

    def test_a_long_file_still_has_to_be_read(self, workspace):
        long = "<!DOCTYPE html>\n" + "".join(f"<p>{n}</p>\n" for n in range(80))
        (workspace / "todo-app" / "index.html").write_text(long, encoding="utf-8")
        project_memory.record(workspace, "todo-app/index.html", "specialist_testing_4")

        with pytest.raises(RepositoryToolError) as caught:
            write_approved_artifact(workspace, "todo-app/index.html", MINE)
        assert "Read it first" in str(caught.value)

        with pytest.raises(RepositoryToolError):
            write_approved_artifact(workspace, "todo-app/index.html", MINE)

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


def test_the_refusal_names_only_the_edit_tools_offered(workspace, monkeypatch):
    """`replace_lines` is off unless LINE_EDITS=on; a refusal must not send the stage to it."""
    monkeypatch.delenv("LINE_EDITS", raising=False)
    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(workspace, "todo-app/index.html", MINE)
    assert "replace_lines" not in str(caught.value) and "`edit_artifact`" in str(caught.value)

    monkeypatch.setenv("LINE_EDITS", "on")
    stage_memory.forget_everything()
    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(workspace, "todo-app/index.html", MINE)
    assert "`replace_lines`" in str(caught.value)


def test_with_the_read_tool_withheld_a_long_file_is_shown_in_the_refusal(workspace, monkeypatch):
    """A fix stage stalled on reads lost its read tool, then was refused a write over a
    244-line file as unseen - "read it first", with nothing left to read with."""
    from app.agents import settled_answer
    from app.tools import repository

    long_file = "\n".join(f"<p id=\"line-{n}\">{n}</p>" for n in range(repository.MOST_LINES_A_REFUSAL_SHOWS + 40)) + "\n"
    (workspace / "todo-app" / "index.html").write_text(long_file, encoding="utf-8")
    project_memory.record(workspace, "todo-app/index.html", "specialist_testing_4")

    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(workspace, "todo-app/index.html", MINE)
    assert "Read it first" in str(caught.value)

    monkeypatch.setattr(settled_answer, "the_read_tool_is_withheld", lambda: True)
    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(workspace, "todo-app/index.html", MINE)
    assert "You have now seen it" in str(caught.value) and 'id="line-90"' in str(caught.value)
