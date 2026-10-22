"""The digest must not present a stage's own edit as another stage's work.

A stage is never told its own name. One stage exported a class in a file an
earlier stage had written; the next call's digest then said the file was
"written by" that stage's name, the model read it as a colleague's rewrite,
re-planned from the top, and sent the same first edit three more times.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.project_memory import record


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "app.js").write_text("export class TaskStore {}\n", encoding="utf-8")
    record(tmp_path, "app/app.js", "specialist_backend_2")
    return tmp_path


def _as_stage(monkeypatch, stage: str) -> None:
    import app.observability.transcript as transcript

    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: stage or fallback)


def test_the_stage_that_changed_a_file_is_told_it_was_itself(workspace, monkeypatch):
    from app.agents.workspace_digest import render_workspace_digest

    _as_stage(monkeypatch, "specialist_backend_2")
    digest = render_workspace_digest(workspace)

    assert "app/app.js (1 lines) - last changed by you, in this stage" in digest
    assert "written by specialist_backend_2" not in digest


def test_another_stage_is_still_told_who_changed_it(workspace, monkeypatch):
    from app.agents.workspace_digest import render_workspace_digest

    _as_stage(monkeypatch, "specialist_ui_ux_1")
    digest = render_workspace_digest(workspace)

    assert "written by specialist_backend_2" in digest
    assert "last changed by you" not in digest


def test_outside_a_run_the_writer_is_named(workspace, monkeypatch):
    from app.agents.workspace_digest import render_workspace_digest

    _as_stage(monkeypatch, "")
    assert "written by specialist_backend_2" in render_workspace_digest(workspace)


def test_an_edit_already_made_by_this_stage_says_so(tmp_path, monkeypatch):
    from app.tools.repository import edit_approved_artifact

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "store.js").write_text("class TaskStore {}\n", encoding="utf-8")
    _as_stage(monkeypatch, "specialist_backend_2")
    edit_approved_artifact(tmp_path, "app/store.js", "class TaskStore {", "export class TaskStore {")
    record(tmp_path, "app/store.js", "specialist_backend_2")

    again = edit_approved_artifact(tmp_path, "app/store.js", "class TaskStore {", "export class TaskStore {")

    assert again["status"] == "already_applied"
    assert "You made this change yourself, earlier in this stage" in again["detail"]


def test_an_edit_another_stage_made_is_not_claimed_as_this_one_s(tmp_path, monkeypatch):
    from app.tools.repository import edit_approved_artifact

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "store.js").write_text("export class TaskStore {}\n", encoding="utf-8")
    record(tmp_path, "app/store.js", "specialist_ui_ux_1")
    _as_stage(monkeypatch, "specialist_backend_2")

    result = edit_approved_artifact(tmp_path, "app/store.js", "class TaskStore {", "export class TaskStore {")

    assert result["status"] == "already_applied"
    assert "It was applied earlier" in result["detail"]
    assert "yourself" not in result["detail"]


def test_a_file_the_stage_s_own_edit_changed_is_not_blamed_on_a_command(workspace, monkeypatch):
    """Measured live: seven parallel edits to one test file, and the one that
    missed was told a command it never ran had rewritten the file, and that its
    passage was correct for the version it had - which nothing had checked."""
    from app.tools import repository

    _as_stage(monkeypatch, "specialist_backend_2")
    said = repository._who_changed_it(workspace, "app/app.js")

    assert "your own edit" in said and "same batch" in said
    source = open(repository.__file__).read()
    assert "The passage you sent was correct for the version you had" not in source
