"""A workflow document read before the stage that renders it has run.

The layout brief named every document in `docs/` and said "Read them". Most
exist only once their stage has run. One run's `technical_lead`, in the first
sprint, listed the workspace, saw `docs/`, and read `docs/security_review.md` -
which the security review renders at the end of a milestone. It was answered
only "File does not exist within the repository", which says nothing about
when it will.

Both read tools now name the stage that renders it and say it has not run yet,
and the brief says to read the ones that exist.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.agents import stage_memory
from app.agents.project_layout import PROJECT_LAYOUT
from app.agents.workspace_backend import WorkspaceBackend
from app.analysis.document_manifest import not_rendered_yet
from app.tools.repository import RepositoryToolError, read_text_file


class TestTheHint:
    def test_a_missing_workflow_document_names_its_stage(self):
        hint = not_rendered_yet("docs/security_review.md")

        assert "'security_review' stage" in hint
        assert "has not run yet" in hint

    def test_a_leading_slash_is_the_same_path(self):
        assert "'milestone_review' stage" in not_rendered_yet("/docs/milestone_review.md")

    @pytest.mark.parametrize(
        "path",
        [
            "docs/notes.md",  # not a workflow document
            "todo-app/docs/security_review.md",  # a project's own docs folder
            "security_review.md",  # not under docs/
            "docs/security_review.txt",  # not the rendered file
        ],
    )
    def test_other_paths_get_nothing(self, path):
        assert not_rendered_yet(path) == ""


class TestBothReadTools:
    def test_read_repository_file_says_why_it_is_missing(self, tmp_path: Path):
        (tmp_path / "docs").mkdir()

        with pytest.raises(RepositoryToolError) as caught:
            read_text_file(tmp_path, "docs/security_review.md")

        message = str(caught.value)
        assert "File does not exist within the repository" in message
        assert "'security_review' stage" in message

    def test_read_file_says_why_it_is_missing(self, monkeypatch):
        stage_memory.forget_everything()
        monkeypatch.setattr(stage_memory, "current_stage_key", lambda: ("t-1", "technical_lead"))
        root = Path(tempfile.mkdtemp())
        (root / "docs").mkdir()
        (root / "docs" / "product_intake.md").write_text("# Intake\n", encoding="utf-8")
        backend = WorkspaceBackend(root_dir=str(root), virtual_mode=True)

        result = backend.read("/docs/security_review.md")

        assert result.error
        assert "'security_review' stage" in result.error
        stage_memory.forget_everything()


class TestTheBrief:
    def test_it_says_some_are_not_there_yet(self):
        text = " ".join(PROJECT_LAYOUT.split())

        assert "early in a run some are not there yet" in text
        assert "Read the ones that exist" in text

    def test_it_no_longer_says_read_them_all(self):
        assert "Read them;" not in PROJECT_LAYOUT
