"""A sprint scope that names a document the harness keeps beside the project is not a file nobody was given.

Measured on a small-model run: every sprint's scope named `technical_specification.md`, which lives in the workspace's
`docs/` and not in the project folder; the plan was sent back to the lead three times each sprint ("the sprint's scope
names technical_specification.md and no work order lists it") and then dispatched with the problem noted.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.analysis import work_orders


def test_a_document_in_the_workspace_docs_folder_exists(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text("# spec\n")
    (tmp_path / "notes-api" / "src").mkdir(parents=True)
    (tmp_path / "notes-api" / "src" / "app.ts").write_text("export {};\n")
    tasks = [SimpleNamespace(files=["notes-api/src/app.ts"])]

    named = work_orders._files_the_sprint_names_and_nobody_is_given(
        "Change src/app.ts as the technical_specification.md says", tasks, tmp_path, "notes-api")

    assert named == []


def test_a_file_that_exists_nowhere_is_still_named(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "notes-api" / "src").mkdir(parents=True)
    tasks = [SimpleNamespace(files=["notes-api/src/app.ts"])]

    named = work_orders._files_the_sprint_names_and_nobody_is_given(
        "Write src/routes.ts and src/app.ts", tasks, tmp_path, "notes-api")

    assert named == ["routes.ts"]
