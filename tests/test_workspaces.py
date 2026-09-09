"""Workspace allocation and path containment.

These cover the fix for the arbitrary-file-read vulnerability: the workspace
root is server-owned, and every caller-supplied path is resolved inside it.
"""

import os

import pytest

from app.server.workspaces import (
    WorkspaceError,
    allocate_workspace,
    delete_workspace,
    resolve_within_workspace,
    safe_label,
    workspace_root,
)


@pytest.fixture
def workspace_base(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_WORKSPACE_ROOT", str(tmp_path / "ws"))
    return tmp_path / "ws"


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("supplied", "expected"),
    [
        ("checkout-service", "checkout-service"),
        ("../../etc/passwd", "passwd"),  # only the final segment survives
        ("/absolute/path", "path"),
        ("weird!!chars@@here", "weird-chars-here"),
        ("", "workspace"),
        (None, "workspace"),
    ],
)
def test_labels_are_reduced_to_one_safe_segment(supplied, expected):
    assert safe_label(supplied) == expected


def test_label_length_is_bounded():
    assert len(safe_label("x" * 500)) <= 48


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------


def test_allocation_creates_a_directory_under_the_root(workspace_base):
    path = allocate_workspace("run-123", "my-app")
    assert path.is_dir()
    assert workspace_base.resolve() in path.parents
    assert "run-123" in path.name


def test_two_runs_never_share_a_workspace(workspace_base):
    first = allocate_workspace("run-a", "same-label")
    second = allocate_workspace("run-b", "same-label")
    assert first != second


def test_a_traversal_label_cannot_escape_the_root(workspace_base):
    """The label is caller-supplied, so it must not steer the path."""
    path = allocate_workspace("run-x", "../../../../tmp/escaped")
    assert workspace_base.resolve() in path.parents


# ---------------------------------------------------------------------------
# Containment - the SEC-01 regression
# ---------------------------------------------------------------------------


def test_a_relative_path_inside_the_workspace_resolves(workspace_base):
    workspace = allocate_workspace("run-1", "app")
    (workspace / "docs").mkdir()
    (workspace / "docs" / "spec.md").write_text("hello")

    resolved = resolve_within_workspace(workspace, "docs/spec.md")
    assert resolved.read_text() == "hello"


@pytest.mark.parametrize(
    "attack",
    [
        "/etc/passwd",
        "/app/.env",
        "../../../../etc/shadow",
        "docs/../../../../etc/hosts",
        "./../../secrets.env",
    ],
)
def test_traversal_and_absolute_paths_are_refused(workspace_base, attack):
    """Each of these previously returned the file's contents to an
    unauthenticated caller."""
    workspace = allocate_workspace("run-2", "app")
    with pytest.raises(WorkspaceError):
        resolve_within_workspace(workspace, attack)


def test_a_symlink_out_of_the_workspace_is_refused(workspace_base, tmp_path):
    """Resolution follows symlinks, so the check must happen after resolving."""
    workspace = allocate_workspace("run-3", "app")
    secret = tmp_path / "outside-secret.txt"
    secret.write_text("do not read me")
    (workspace / "link").symlink_to(secret)

    with pytest.raises(WorkspaceError):
        resolve_within_workspace(workspace, "link")


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------


def test_deleting_a_workspace_removes_it(workspace_base):
    workspace = allocate_workspace("run-4", "app")
    (workspace / "file.txt").write_text("x")

    delete_workspace(workspace)
    assert not workspace.exists()


def test_deleting_outside_the_root_is_refused(workspace_base, tmp_path):
    """A guard against a stale or hand-edited repo_root wiping something else."""
    outside = tmp_path / "not-a-workspace"
    outside.mkdir()

    with pytest.raises(WorkspaceError):
        delete_workspace(outside)
    assert outside.exists()


def test_workspace_root_falls_back_to_data_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("WORKFLOW_WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert workspace_root() == (tmp_path / "workspaces").resolve()
