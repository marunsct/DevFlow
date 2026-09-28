"""A test runner installed over the one the stack chose is a finding.

Measured on one run. `stack_selector` chose "Custom JS assert tests",
reasoning "no node test runners available, avoiding large dependencies".
`specialist_ui_ux_0` installed jest anyway and spent four `npm test` calls on
`TextEncoder is not defined` - a jsdom failure belonging to the runner it had
just added, which the chosen approach could not have reached.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from app.analysis.integration_checks import (
    _a_test_runner_the_stack_did_not_choose,
    _severity_of,
)


@dataclass
class Stack:
    testing_framework: str = ""
    database: str = ""
    language: str = ""
    framework: str = ""


def _project(tmp_path: Path, manifest: dict) -> tuple[list[Path], Path]:
    (tmp_path / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    return [tmp_path / "package.json"], tmp_path


def test_the_measured_case(tmp_path):
    files, root = _project(tmp_path, {"devDependencies": {"jest": "^29.5.0"}})

    found = _a_test_runner_the_stack_did_not_choose(
        files, root, Stack(testing_framework="Custom JS assert tests")
    )

    assert len(found) == 1
    assert "installs 'jest'" in found[0]
    assert "Custom JS assert tests" in found[0]


def test_it_reads_as_something_that_breaks_the_suite(tmp_path):
    files, root = _project(tmp_path, {"devDependencies": {"jest": "^29.5.0"}})
    found = _a_test_runner_the_stack_did_not_choose(
        files, root, Stack(testing_framework="node --test")
    )
    assert _severity_of(found[0]) == "BREAKS"


def test_the_runner_the_stack_chose_is_silent(tmp_path):
    files, root = _project(tmp_path, {"devDependencies": {"jest": "^29.5.0"}})
    assert (
        _a_test_runner_the_stack_did_not_choose(files, root, Stack(testing_framework="Jest"))
        == []
    )


def test_a_stack_that_named_no_runner_is_silent(tmp_path):
    """Nothing was chosen, so nothing was overruled."""
    files, root = _project(tmp_path, {"devDependencies": {"jest": "^29.5.0"}})
    assert _a_test_runner_the_stack_did_not_choose(files, root, Stack()) == []


def test_packages_that_are_not_test_runners_are_silent(tmp_path):
    files, root = _project(tmp_path, {"dependencies": {"lodash": "^4.0.0"}})
    assert (
        _a_test_runner_the_stack_did_not_choose(
            files, root, Stack(testing_framework="node --test")
        )
        == []
    )


def test_vitest_is_recognised_under_the_stacks_own_spelling(tmp_path):
    files, root = _project(tmp_path, {"devDependencies": {"vitest": "^1.0.0"}})
    assert (
        _a_test_runner_the_stack_did_not_choose(
            files, root, Stack(testing_framework="Vite test runner")
        )
        == []
    )


def test_a_manifest_that_will_not_parse_is_not_an_error(tmp_path):
    (tmp_path / "package.json").write_text("{not json", encoding="utf-8")
    assert (
        _a_test_runner_the_stack_did_not_choose(
            [tmp_path / "package.json"], tmp_path, Stack(testing_framework="node --test")
        )
        == []
    )


def test_no_stack_at_all_is_not_an_error(tmp_path):
    files, root = _project(tmp_path, {"devDependencies": {"jest": "^29.5.0"}})
    assert _a_test_runner_the_stack_did_not_choose(files, root, None) == []


def test_the_check_is_named_in_what_the_reviewer_is_told_was_checked():
    from app.analysis.integration_checks import _CHECKS

    assert any("test runner" in description for description, _ in _CHECKS)
