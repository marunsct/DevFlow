"""What the run workspaces cost, and what it takes to reclaim any of it.

Nothing ages these out. `delete_workspace` is called from exactly one place -
`DELETE /api/runs/{id}` - so a workspace lives as long as the deployment.
Measured on the development deployment: 846 MB across twelve runs of a to-do
list app, most of it `node_modules` and `.agent-home/.npm` that every run
installs again from scratch.

Deleting a workspace destroys the only copy of what a run built, so this
reports by default and needs two separate flags to remove anything.
"""

from __future__ import annotations

import types

import pytest

from app.server import manage


class _Record:
    def __init__(self, status: str) -> None:
        self.status = status


@pytest.fixture
def workspaces(tmp_path, monkeypatch):
    root = tmp_path / "workspaces"
    (root / "default").mkdir(parents=True)

    def make(name: str, size: int, age_days: float) -> None:
        directory = root / "default" / name
        directory.mkdir()
        (directory / "app.js").write_bytes(b"x" * size)
        when = __import__("time").time() - age_days * 86400
        __import__("os").utime(directory, (when, when))

    make("todo-run-11111111-aaaa", 4096, 30)
    make("todo-run-22222222-bbbb", 2048, 30)
    make("todo-run-33333333-cccc", 1024, 0.5)

    # The pre-tenant layout, which is on disk beside the other one: a
    # workspace directly under the root, with subdirectories of its own.
    old = root / "todo-run-44444444-dddd"
    (old / "docs").mkdir(parents=True)
    (old / ".git").mkdir()
    (old / "app.js").write_bytes(b"y" * 8192)
    when = __import__("time").time() - 30 * 86400
    __import__("os").utime(old, (when, when))

    statuses = {
        "run-11111111-aaaa": "completed",
        "run-22222222-bbbb": "running",
        "run-33333333-cccc": "completed",
        "run-44444444-dddd": "completed",
    }
    store = types.SimpleNamespace(
        load=lambda run_id: _Record(statuses[run_id]) if run_id in statuses else None
    )
    monkeypatch.setattr(
        "app.server.run_store.RunStore.shared", staticmethod(lambda: store)
    )
    monkeypatch.setattr("app.server.workspaces.workspace_root", lambda: root)
    return root


def test_it_reports_every_workspace_with_its_run_status(workspaces, capsys) -> None:
    manage.workspaces()
    out = capsys.readouterr().out

    assert "todo-run-11111111-aaaa" in out
    assert "completed" in out
    assert "running" in out
    assert "total across 4 workspace(s)" in out


def test_nothing_is_offered_without_an_age(workspaces, capsys) -> None:
    manage.workspaces()

    assert "Would delete" not in capsys.readouterr().out


def test_an_age_reports_what_could_go_and_removes_nothing(workspaces, capsys) -> None:
    manage.workspaces(older_than_days=7)
    out = capsys.readouterr().out

    assert "Would delete todo-run-11111111-aaaa" in out
    assert "Re-run with --delete" in out
    assert (workspaces / "default" / "todo-run-11111111-aaaa").exists()


def test_a_live_run_keeps_its_workspace_however_old(workspaces, capsys) -> None:
    """A run parked for a human decision is still going to be resumed."""
    manage.workspaces(older_than_days=7, delete=True)
    out = capsys.readouterr().out

    assert "Kept todo-run-22222222-bbbb" in out
    assert (workspaces / "default" / "todo-run-22222222-bbbb").exists()


def test_a_younger_workspace_is_left_alone(workspaces) -> None:
    manage.workspaces(older_than_days=7, delete=True)

    assert (workspaces / "default" / "todo-run-33333333-cccc").exists()


def test_delete_removes_only_the_finished_and_old(workspaces, capsys) -> None:
    manage.workspaces(older_than_days=7, delete=True)
    out = capsys.readouterr().out

    assert not (workspaces / "default" / "todo-run-11111111-aaaa").exists()
    assert "Reclaimed" in out


def test_the_cli_reaches_it(monkeypatch) -> None:
    seen: dict = {}
    monkeypatch.setattr(manage, "init_db_pool", lambda: None)
    monkeypatch.setattr(
        manage,
        "workspaces",
        lambda older_than_days=None, delete=False: seen.update(
            older=older_than_days, delete=delete
        )
        or 0,
    )

    assert manage.main(["workspaces", "--older-than-days", "14", "--delete"]) == 0
    assert seen == {"older": 14.0, "delete": True}


def test_the_cli_defaults_to_reporting(monkeypatch) -> None:
    seen: dict = {}
    monkeypatch.setattr(manage, "init_db_pool", lambda: None)
    monkeypatch.setattr(
        manage,
        "workspaces",
        lambda older_than_days=None, delete=False: seen.update(
            older=older_than_days, delete=delete
        )
        or 0,
    )

    assert manage.main(["workspaces"]) == 0
    assert seen == {"older": None, "delete": False}


# --- the two layouts on disk at once --------------------------------------


def test_a_pre_tenant_workspace_is_found(workspaces, capsys) -> None:
    """`allocate_workspace` put workspaces directly under the root before
    tenant segments existed, and six of them are still there."""
    manage.workspaces()
    out = capsys.readouterr().out

    assert "todo-run-44444444-dddd" in out
    assert "total across 4 workspace(s)" in out


def test_its_subdirectories_are_not_counted_as_workspaces(workspaces, capsys) -> None:
    """The bug this fixes: `.git` and `docs` were listed in their own right,
    each with a status of "no run", and the real workspace was never listed."""
    manage.workspaces()
    out = capsys.readouterr().out

    assert "/docs" not in out
    assert "/.git" not in out
    assert "no run" not in out


def test_it_is_offered_for_deletion_like_any_other(workspaces, capsys) -> None:
    """It never was: a `docs` directory carries no run id, so its status read
    "no run", which is not terminal, so nothing was ever reclaimed."""
    manage.workspaces(older_than_days=7)
    out = capsys.readouterr().out

    assert "Would delete todo-run-44444444-dddd" in out


def test_a_workspace_that_exists_never_reads_as_empty(workspaces, capsys) -> None:
    """One decimal place prints anything under 50 KB as "0.0 MB", and a column
    of zeroes is what makes an operator stop reading the report."""
    manage.workspaces()
    line = next(
        l for l in capsys.readouterr().out.splitlines() if "todo-run-44444444-dddd" in l
    )

    assert line.strip().startswith("<0.1 MB")
