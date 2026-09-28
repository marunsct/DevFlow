"""Exported functions that no test file names.

The runs keep shipping a suite thinner than the product. One run's
`npm test` reported `# tests 1` for an application exporting five functions;
one run reported three; one run had seven test files of which one
ran. None of that is visible in a passing suite, and a reviewer reading "all
tests passed" cannot tell a thorough suite from a token one.

Evidence, not a fault: an export used only by other application code is
legitimately exercised through it, and this cannot tell the difference. What it
can say exactly is which names appear in no test at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _exports_no_test_mentions,
    _severity_of,
    _source_files,
)

MODULE = (
    "export function addTask(t) {}\n"
    "export function editTask(id, u) {}\n"
    "export function deleteTask(id) {}\n"
    "export function loadTasks() { return []; }\n"
    "export function filterTasks(s) { return []; }\n"
)


def _check(tmp_path: Path, module: str, test: str | None, test_name: str = "app.test.mjs"):
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(json.dumps({"name": "app", "type": "module"}), encoding="utf-8")
    (project / "app.js").write_text(module, encoding="utf-8")
    if test is not None:
        (project / test_name).write_text(test, encoding="utf-8")
    return _exports_no_test_mentions(_source_files(tmp_path), tmp_path)


def test_the_names_no_test_mentions_are_listed(tmp_path: Path) -> None:
    (problem,) = _check(
        tmp_path,
        MODULE,
        "import { addTask, loadTasks } from './app.js';\n"
        "test('adds', () => { addTask({}); loadTasks(); });\n",
    )

    assert "deleteTask" in problem and "editTask" in problem and "filterTasks" in problem
    assert "addTask" not in problem.split("no test mentions")[1]


def test_it_is_evidence_rather_than_a_fault(tmp_path: Path) -> None:
    """A thin suite is worth a minor finding, not a blocking one."""
    (problem,) = _check(tmp_path, MODULE, "import { addTask } from './app.js';\n")

    assert _severity_of(problem) == "untidy"


def test_a_suite_that_names_everything_is_silent(tmp_path: Path) -> None:
    every = "import { addTask, editTask, deleteTask, loadTasks, filterTasks } from './app.js';\n"

    assert _check(tmp_path, MODULE, every) == []


def test_a_project_with_no_tests_at_all_is_not_judged(tmp_path: Path) -> None:
    """That is a different finding, and a louder one."""
    assert _check(tmp_path, MODULE, None) == []


def test_a_module_that_exports_nothing_is_not_judged(tmp_path: Path) -> None:
    assert _check(tmp_path, "function helper() {}\nhelper();\n", "import './app.js';\n") == []


def test_the_test_file_itself_is_not_judged(tmp_path: Path) -> None:
    """A test that exports a helper is not untested application code."""
    problems = _check(
        tmp_path,
        MODULE,
        "export function makeTask() {}\n"
        "import { addTask, editTask, deleteTask, loadTasks, filterTasks } from './app.js';\n",
    )

    assert problems == []


def test_an_export_list_is_read_as_well_as_declarations(tmp_path: Path) -> None:
    problems = _check(
        tmp_path,
        "function a() {}\nfunction b() {}\nexport { a, b };\n",
        "import { a } from './app.js';\n",
    )

    assert problems and "b" in problems[0]
