"""The project's own manifest is changed in place, never deleted.

Measured on one run: a test round had an edit of `package.json` refused as
invalid JSON, deleted the file to clear the way, had two whole-file writes
refused for a path in the test script, and returned saying it could not finish.
The project was left with no manifest at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import PROJECT_MARKER, RepositoryToolError, delete_approved_artifact

MANIFEST = '{\n  "name": "the-app",\n  "scripts": {"test": "node --test"}\n}\n'


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: "defect_fix_1_0")
    project = tmp_path / "the-app"
    project.mkdir()
    (tmp_path / PROJECT_MARKER).write_text("the-app\n", encoding="utf-8")
    (project / "package.json").write_text(MANIFEST, encoding="utf-8")
    return tmp_path


def test_the_project_s_manifest_is_kept(workspace) -> None:
    with pytest.raises(RepositoryToolError) as caught:
        delete_approved_artifact(workspace, "the-app/package.json")

    assert "this project's manifest" in str(caught.value)
    assert "edit_artifact" in str(caught.value)
    assert (workspace / "the-app" / "package.json").read_text(encoding="utf-8") == MANIFEST


def test_a_second_manifest_outside_the_project_can_go(workspace) -> None:
    """A duplicate at the workspace root is what a cleanup is right to remove."""
    (workspace / "package.json").write_text(MANIFEST, encoding="utf-8")

    delete_approved_artifact(workspace, "package.json")

    assert not (workspace / "package.json").exists()
    assert (workspace / "the-app" / "package.json").exists()


def test_a_manifest_the_plan_says_to_delete_can_go(workspace) -> None:
    (workspace / "docs").mkdir()
    (workspace / "docs" / "milestone_plan.md").write_text(
        "## Delegated tasks\n#### backend - Delete `the-app/package.json`; the product ships no manifest.\n",
        encoding="utf-8",
    )

    delete_approved_artifact(workspace, "the-app/package.json")

    assert not (workspace / "the-app" / "package.json").exists()


def test_other_files_in_the_project_are_unaffected(workspace) -> None:
    (workspace / "the-app" / "notes.tmp").write_text("x\n", encoding="utf-8")

    delete_approved_artifact(workspace, "the-app/notes.tmp")

    assert not (workspace / "the-app" / "notes.tmp").exists()


def test_the_project_s_manifest_is_not_moved_out_of_the_project(workspace) -> None:
    """One run's stage, refused a manifest at the workspace root four times,
    moved the project's own there instead."""
    from app.tools.repository import move_approved_artifact

    with pytest.raises(RepositoryToolError) as caught:
        move_approved_artifact(workspace, "the-app/package.json", "package.json")

    assert "this project's manifest" in str(caught.value)
    assert (workspace / "the-app" / "package.json").exists()
    assert not (workspace / "package.json").exists()


def test_nothing_is_moved_to_a_manifest_at_the_workspace_root(workspace) -> None:
    from app.tools.repository import move_approved_artifact

    (workspace / "the-app" / "old.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        move_approved_artifact(workspace, "the-app/old.json", "package.json")

    assert "second project" in str(caught.value)
    assert not (workspace / "package.json").exists()
