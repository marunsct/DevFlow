"""Tests for the safe repository inspection tool layer.

The core idea is simple: tools may inspect a repository, but only inside a
trusted boundary. These tests make that contract explicit by proving that reads,
searches, and writes stay inside the repository or approved artifact directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import (
    RepositoryToolError,
    build_repository_context,
    list_repository_files,
    read_dependency_metadata,
    read_text_file,
    run_approved_validation,
    search_text,
    write_approved_artifact,
)


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    # Build a tiny, controlled repository so the tests exercise the tool behavior
    # without relying on the real workspace structure.
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "docs/generated").mkdir()
    (root / ".git").mkdir()
    (root / "node_modules").mkdir()

    (root / "pyproject.toml").write_text(
        "[project]\nname = \"demo-app\"\nversion = \"0.1.0\"\n",
        encoding="utf-8",
    )
    (root / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "docs" / "brief.md").write_text("# Product\n\nKeep this note.\n", encoding="utf-8")
    (root / "docs" / "generated" / "artifact.md").write_text("draft\n", encoding="utf-8")
    return root


def test_list_repository_files_skips_ignored_directories(repo_root: Path) -> None:
    files = list_repository_files(repo_root)

    assert "src/main.py" in files
    assert "docs/brief.md" in files
    assert ".git" not in "\n".join(files)
    assert "node_modules" not in "\n".join(files)


def test_read_text_file_requires_repo_boundary(repo_root: Path) -> None:
    result = read_text_file(repo_root, "docs/brief.md")

    assert "Keep this note" in result

    with pytest.raises(RepositoryToolError):
        read_text_file(repo_root, "../outside.txt")


def test_search_text_finds_matching_content(repo_root: Path) -> None:
    matches = search_text(repo_root, "Keep this note")

    assert matches
    assert "docs/brief.md" in matches[0]["path"]


def test_read_dependency_metadata_reads_project_file(repo_root: Path) -> None:
    metadata = read_dependency_metadata(repo_root)

    assert metadata["project"]["name"] == "demo-app"


def test_write_approved_artifact_only_allows_in_artifact_directory(repo_root: Path) -> None:
    result = write_approved_artifact(repo_root, "new-note.md", "hello from artifact\n")

    assert result["path"].endswith("new-note.md")
    assert (repo_root / "new-note.md").read_text(encoding="utf-8") == "hello from artifact\n"

    with pytest.raises(RepositoryToolError):
        write_approved_artifact(repo_root, "../not-allowed.txt", "bad")


def test_run_approved_validation_accepts_whitelisted_commands(repo_root: Path) -> None:
    import sys
    result = run_approved_validation(repo_root, [sys.executable, "-m", "compileall", "-q", "src"])

    assert result["returncode"] == 0

    with pytest.raises(RepositoryToolError):
        run_approved_validation(repo_root, ["rm", "-rf", "/tmp/evil"])


def test_repository_context_reports_the_current_git_revision() -> None:
    """The workflow's own repo is a git checkout, so branch and commit resolve."""
    context = build_repository_context(Path(__file__).resolve().parents[1])

    assert context.branch != "unknown"
    assert len(context.commit) == 40, "expected a full commit sha"
    assert "pyproject.toml" in context.dependency_files


def test_repository_context_does_not_report_an_unknown_repo_as_clean(tmp_path: Path) -> None:
    """A non-git directory must not look like a clean, stable checkout.

    Reporting "clean" here would be a false stability signal: downstream roles
    treat a clean repo as safe to build on, so an unknown state must say so.
    """
    context = build_repository_context(tmp_path)

    assert context.branch == "unknown"
    assert context.commit == "unknown"
    assert "unknown" in context.status
    assert context.status != "clean"


def test_repository_context_rejects_a_missing_root() -> None:
    with pytest.raises(RepositoryToolError):
        build_repository_context("/does/not/exist/anywhere")
