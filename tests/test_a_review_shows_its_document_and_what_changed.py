"""A review shows its document in place, and what changed since the last revision (plan BG.3).

A review on the run page named its artifact and offered a download: the owner
downloaded the document, edited it, and uploaded it again, and a second
revision gave no way to see what the agents had changed in answer.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.server.changes import document_diff
from app.server.models import ReviewPayload
from app.server.runs import _the_review_document


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    (root / "docs").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "loop@example.com")
    _git(root, "config", "user.name", "loop")
    return root


def test_a_review_names_the_document_the_workflow_wrote(tmp_path):
    root = _workspace(tmp_path)
    for name in ("technical_specification.md", "milestone_plan.md", "tools_and_models.md", "acceptance_tests.md"):
        (root / "docs" / name).write_text("# A document\n")

    assert _the_review_document(str(root), "technical-specification") == "docs/technical_specification.md"
    assert _the_review_document(str(root), "sprint-milestone") == "docs/milestone_plan.md"
    assert _the_review_document(str(root), "tools-and-models") == "docs/tools_and_models.md"
    assert _the_review_document(str(root), "acceptance-tests") == "docs/acceptance_tests.md"
    assert _the_review_document(str(root), "release") is None
    assert _the_review_document(None, "technical-specification") is None
    assert "document" in ReviewPayload.model_fields


def test_what_changed_since_the_version_before(tmp_path):
    root = _workspace(tmp_path)
    spec = root / "docs" / "spec.md"
    spec.write_text("# Spec\n\nUsers sign in with a username.\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "First revision")
    spec.write_text("# Spec\n\nUsers sign in with an email address.\n")

    found = document_diff(root, "docs/spec.md")

    assert found["since"] and found["since_at"]
    assert "-Users sign in with a username." in found["diff"]
    assert "+Users sign in with an email address." in found["diff"]


def test_a_committed_revision_is_compared_with_the_version_before_it(tmp_path):
    root = _workspace(tmp_path)
    spec = root / "docs" / "spec.md"
    spec.write_text("one\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "First")
    spec.write_text("two\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "Second")

    assert "-one" in document_diff(root, "docs/spec.md")["diff"]


def test_a_document_with_no_earlier_version_has_nothing_changed(tmp_path):
    root = _workspace(tmp_path)
    (root / "docs" / "new.md").write_text("first\n")

    assert document_diff(root, "docs/new.md") == {"path": "docs/new.md", "since": None, "since_at": None, "diff": "", "truncated": False}


def test_a_path_is_never_a_pattern(tmp_path):
    root = _workspace(tmp_path)
    (root / "docs" / "spec.md").write_text("one\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "First")
    (root / "docs" / "spec.md").write_text("two\n")

    assert document_diff(root, "docs/*.md")["diff"] == ""
