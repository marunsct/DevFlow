"""Test files the project's own `npm test` will not execute.

One run reached its third milestone round with seven test files -
`app.test.mjs` and six standalone assertion scripts named `test_add_task.mjs`,
`test_delete_task.mjs`, `test_edit_task.mjs`, `test_filter_tasks.mjs`,
`test_persistence.mjs` and `test_toggle_task.mjs`, 3,845 bytes of real
assertions. Its `scripts.test` is `node --test`, whose prefix pattern takes a
hyphen, so `node --test .` reported `# tests 1`.

The cross-file checks reported no problems, and the size report described
"tests: 207 lines across 7 file(s)" - asserting coverage that had never run.
A false green is worse than a red: every stage after it reads a passing suite
as evidence the product works.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _severity_of,
    _source_files,
    _tests_the_project_never_runs,
)


def _project(tmp_path: Path, test_script: str, names: list[str]) -> list[str]:
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps({"name": "app", "type": "module", "scripts": {"test": test_script}}),
        encoding="utf-8",
    )
    (project / "app.js").write_text("export const a = 1;\n", encoding="utf-8")
    for name in names:
        (project / name).write_text("import assert from 'node:assert';\n", encoding="utf-8")
    return _tests_the_project_never_runs(_source_files(tmp_path), tmp_path)


MEASURED_TEST_FILES = [
    "test_add_task.mjs",
    "test_delete_task.mjs",
    "test_edit_task.mjs",
    "test_filter_tasks.mjs",
    "test_persistence.mjs",
    "test_toggle_task.mjs",
]


def test_the_six_stranded_suites_are_reported(tmp_path: Path) -> None:
    (problem,) = _project(tmp_path, "node --test ./", [*MEASURED_TEST_FILES, "app.test.mjs"])

    for name in MEASURED_TEST_FILES:
        assert name in problem
    assert "app.test.mjs" not in problem, "the one that does run is not listed"


def test_it_counts_as_breaking_the_product(tmp_path: Path) -> None:
    """The run believes it has coverage it does not have."""
    (problem,) = _project(tmp_path, "node --test", MEASURED_TEST_FILES)

    assert _severity_of(problem) == "BREAKS"


@pytest.mark.parametrize(
    "names",
    [
        ["app.test.mjs"],
        ["app-test.mjs"],
        ["app_test.mjs"],
        ["test-add.mjs"],
        ["test.mjs"],
        ["app.test.mjs", "store.test.mjs"],
    ],
)
def test_a_suite_node_does_collect_is_not_reported(tmp_path: Path, names) -> None:
    assert _project(tmp_path, "node --test", names) == []


@pytest.mark.parametrize("script", ["jest", "vitest run", "mocha", "npx playwright test"])
def test_another_runner_is_left_alone(tmp_path: Path, script: str) -> None:
    """Jest, Vitest and Mocha decide discovery in their own configuration,
    which this cannot read. A wrong claim about a suite that runs perfectly
    well would be worse than no claim."""
    assert _project(tmp_path, script, MEASURED_TEST_FILES) == []


def test_a_project_with_no_test_script_is_left_alone(tmp_path: Path) -> None:
    assert _project(tmp_path, "", MEASURED_TEST_FILES) == []


def test_a_broken_manifest_is_reported_elsewhere(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text("{not json", encoding="utf-8")
    (project / "test_a.mjs").write_text("import assert from 'node:assert';\n", encoding="utf-8")

    assert _tests_the_project_never_runs(_source_files(tmp_path), tmp_path) == []
