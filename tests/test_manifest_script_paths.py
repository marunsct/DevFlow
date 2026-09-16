"""Paths in `package.json` scripts, against where npm actually runs them.

`npm run` sets the working directory to the package directory, so a path in a
script is relative to the manifest beside it. A model that writes the project
directory into the path as well produces `todo-app/todo-app/app.test.mjs`,
which exists nowhere.

`strip_a_doubled_working_directory` catches that shape in a
`run_terminal_command` argument and cannot reach this one: a path written into
`package.json` is persisted, and `npm test` fails the same way every time, for
the rest of the project's life.

run-a7150a6c's manifest said

    "test": "node --test simple-to-do-list-app/app.test.mjs"

inside `simple-to-do-list-app/`, and `npm test` reported
`Could not find '.../simple-to-do-list-app/simple-to-do-list-app/app.test.mjs'`
while `app.test.mjs` sat beside the manifest.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _manifest_scripts_that_cannot_resolve,
    _severity_of,
    _source_files,
)


def _project(tmp_path: Path, scripts: dict, files: list[str]) -> list[str]:
    project = tmp_path / "todo-app"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps({"name": "todo-app", "type": "module", "scripts": scripts}),
        encoding="utf-8",
    )
    for name in files:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("export const a = 1;\n", encoding="utf-8")
    return _manifest_scripts_that_cannot_resolve(_source_files(tmp_path), tmp_path)


def test_the_doubled_project_directory_in_a_script(tmp_path: Path) -> None:
    (problem,) = _project(
        tmp_path, {"test": "node --test todo-app/app.test.mjs"}, ["app.test.mjs"]
    )

    assert "does not exist from todo-app/" in problem
    assert "The file is at app.test.mjs" in problem
    assert "written into the manifest" in problem


def test_it_counts_as_breaking_the_product(tmp_path: Path) -> None:
    (problem,) = _project(
        tmp_path, {"test": "node --test todo-app/app.test.mjs"}, ["app.test.mjs"]
    )

    assert _severity_of(problem) == "BREAKS"


@pytest.mark.parametrize(
    ("script", "files"),
    [
        ("node --test app.test.mjs", ["app.test.mjs"]),
        ("node --test ./app.test.mjs", ["app.test.mjs"]),
        ("node --test test/app.test.mjs", ["test/app.test.mjs"]),
        ("node --test", ["app.test.mjs"]),
        ("jest", ["app.test.mjs"]),
        ("vitest run --coverage", ["app.test.mjs"]),
    ],
)
def test_a_script_that_resolves_is_not_reported(tmp_path: Path, script: str, files) -> None:
    assert _project(tmp_path, {"test": script}, files) == []


def test_a_path_that_exists_nowhere_is_left_alone(tmp_path: Path) -> None:
    """A script naming a file that is about to be written is not a defect -
    only one whose file is demonstrably somewhere else."""
    assert _project(tmp_path, {"test": "node --test not-written-yet.mjs"}, []) == []


def test_every_script_is_checked_not_only_test(tmp_path: Path) -> None:
    problems = _project(
        tmp_path,
        {"build": "node todo-app/build.mjs", "test": "node --test app.test.mjs"},
        ["build.mjs", "app.test.mjs"],
    )

    assert len(problems) == 1
    assert "npm run build" in problems[0]


def test_a_broken_manifest_is_reported_elsewhere(tmp_path: Path) -> None:
    project = tmp_path / "todo-app"
    project.mkdir()
    (project / "package.json").write_text("{not json", encoding="utf-8")

    assert _manifest_scripts_that_cannot_resolve(_source_files(tmp_path), tmp_path) == []
