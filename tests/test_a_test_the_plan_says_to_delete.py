"""A test the milestone plan names for removal can be deleted.

A plan delegated "Delete `simple-to-do-list-app/app.test.js` (root-level Jest
unit test - duplicate of tests/app.test.js)". The delete was refused twice as
another stage's test, `rm` and `node -e` were refused, and the stage wrote a
script that deleted the files anyway.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis import project_memory
from app.tools.repository import RepositoryToolError, delete_approved_artifact

PLAN = (
    "## Delegated tasks\n"
    "#### testing - Consolidate duplicate test files: 1) Delete "
    "`simple-to-do-list-app/app.test.js` (root-level Jest unit test - duplicate of "
    "tests/app.test.js). 2) Keep tests/app.test.js.\n"
)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(
        "app.observability.transcript._stage_from_config", lambda fallback: "specialist_testing_2"
    )
    (tmp_path / "docs").mkdir()
    project = tmp_path / "simple-to-do-list-app"
    (project / "tests").mkdir(parents=True)
    for name in ("app.test.js", "tests/app.test.js"):
        (project / name).write_text("test('adds', () => {});\n", encoding="utf-8")
        project_memory.record(tmp_path, f"simple-to-do-list-app/{name}", "specialist_ui_ux_2")
    return tmp_path


def test_a_test_the_plan_names_for_removal_is_deleted(workspace):
    (workspace / "docs" / "milestone_plan.md").write_text(PLAN, encoding="utf-8")

    delete_approved_artifact(workspace, "simple-to-do-list-app/app.test.js")

    assert not (workspace / "simple-to-do-list-app" / "app.test.js").exists()


def test_the_one_it_says_to_keep_is_still_protected(workspace):
    """`tests/app.test.js` is named too - in a sentence that keeps it."""
    (workspace / "docs" / "milestone_plan.md").write_text(PLAN, encoding="utf-8")

    with pytest.raises(RepositoryToolError):
        delete_approved_artifact(workspace, "simple-to-do-list-app/tests/app.test.js")


def test_without_the_plan_it_is_refused(workspace):
    with pytest.raises(RepositoryToolError):
        delete_approved_artifact(workspace, "simple-to-do-list-app/app.test.js")


def test_a_plan_that_only_mentions_the_file_does_not_count(workspace):
    (workspace / "docs" / "milestone_plan.md").write_text(
        "Tests live in `simple-to-do-list-app/app.test.js`.\n", encoding="utf-8"
    )

    with pytest.raises(RepositoryToolError):
        delete_approved_artifact(workspace, "simple-to-do-list-app/app.test.js")


def test_a_basename_alone_does_not_count(workspace):
    (workspace / "docs" / "milestone_plan.md").write_text(
        "Delete the duplicate app.test.js.\n", encoding="utf-8"
    )

    with pytest.raises(RepositoryToolError):
        delete_approved_artifact(workspace, "simple-to-do-list-app/app.test.js")
