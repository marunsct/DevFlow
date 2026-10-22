"""A working test file cannot be emptied or skipped into passing.

Measured on one run. A testing stage wrote 72 lines of real assertions, ran
them, and was answered "Failed to import app.js: document is not defined" - a
true finding about the product. It replaced all 72 lines with one `skip(...)`,
did the same to the browser spec, and both edits were answered "edited". The
next `npm test` exited 0 having run nothing, a fix stage returned "All good",
and the ledger held a passing suite every later gate would have believed.

Deleting a test is refused for this reason. Emptying one where it stands is the
same act through another tool.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analysis.test_discovery import a_suite_this_change_switches_off, how_many_tests_run
from app.graph.workflow import (
    _the_test_command_this_stage_left_failing,
    _where_each_test_command_stands,
)
from app.tools.repository import (
    RepositoryToolError,
    replace_approved_lines,
    write_approved_artifact,
)
from app.tools.sandbox import _ledger_path

A_SUITE = (
    "import { test } from 'node:test';\n"
    "import assert from 'node:assert/strict';\n"
    "import { addTask } from '../app.js';\n\n"
    "test('adds a task', () => {\n  assert.equal(addTask('a').title, 'a');\n});\n\n"
    "test('rejects an empty title', () => {\n  assert.throws(() => addTask(''));\n});\n"
)

AS_THE_RUN_WROTE_IT = (
    "import { test, skip } from 'node:test';\n\n"
    "// Skipping unit tests because the app logic depends on browser environment.\n"
    "skip('Unit tests are skipped due to environment constraints');\n"
)

SWITCHED_OFF = [
    AS_THE_RUN_WROTE_IT,
    "import { test } from '@playwright/test';\ntest.skip('E2E tests are skipped', () => {});\n",
    "import { it } from 'vitest';\nit.todo('adds a task');\n",
    "// tests removed for now\n",
    "import { test } from 'node:test';\ntest.skip('a', () => {});\ntest.skip('b', () => {});\n",
]


def test_the_cases_a_runner_would_execute_are_counted() -> None:
    assert how_many_tests_run(A_SUITE) == 2
    assert how_many_tests_run(AS_THE_RUN_WROTE_IT) == 0
    assert how_many_tests_run("test('a', () => {});\ntest.skip('b', () => {});\nit.only('c', () => {});\n") == 2
    assert how_many_tests_run("def test_a():\n    assert 1\n\ndef test_b():\n    assert 2\n") == 2
    assert how_many_tests_run("import pytest\n\n@pytest.mark.skip\ndef test_a():\n    assert 1\n") == 0


@pytest.mark.parametrize("after", SWITCHED_OFF)
def test_a_change_that_leaves_nothing_running_is_named(after: str) -> None:
    problem = a_suite_this_change_switches_off("app/tests/app.test.js", A_SUITE, after)

    assert problem and "holds 2 tests that run, and this would leave none" in problem
    assert "report that in `defects` or `blockers`" in problem


@pytest.mark.parametrize("after", [
    # One test dropped, one kept.
    A_SUITE.replace("test('rejects an empty title'", "test.skip('rejects an empty title'"),
    # Rewritten for another runner.
    "import { test, expect } from 'vitest';\ntest('adds', () => { expect(1).toBe(1); });\n",
    A_SUITE + "\ntest('a third', () => { assert.ok(true); });\n",
])
def test_an_ordinary_edit_is_left_alone(after: str) -> None:
    assert a_suite_this_change_switches_off("app/tests/app.test.js", A_SUITE, after) is None


def test_a_file_that_never_ran_a_test_is_not_this() -> None:
    assert a_suite_this_change_switches_off("app/tests/app.test.js", AS_THE_RUN_WROTE_IT, "// gone\n") is None
    assert a_suite_this_change_switches_off("app/src/app.js", A_SUITE, "// gone\n") is None


def _a_project_with_the_suite(root: Path) -> None:
    write_approved_artifact(root, "app/package.json", '{"name": "app", "type": "module"}')
    write_approved_artifact(root, "app/app.js", "export function addTask(t) { if (!t) throw new Error('x'); return { title: t }; }\n")
    write_approved_artifact(root, "app/tests/app.test.js", A_SUITE)


def test_the_line_edit_the_run_made_is_refused(tmp_path: Path) -> None:
    _a_project_with_the_suite(tmp_path)

    with pytest.raises(RepositoryToolError) as refused:
        replace_approved_lines(
            tmp_path, "app/tests/app.test.js", 1, len(A_SUITE.splitlines()), AS_THE_RUN_WROTE_IT
        )

    assert "would leave none" in str(refused.value)
    assert (tmp_path / "app" / "tests" / "app.test.js").read_text(encoding="utf-8") == A_SUITE


def test_a_whole_file_write_is_refused_the_same_way(tmp_path: Path) -> None:
    _a_project_with_the_suite(tmp_path)

    with pytest.raises(RepositoryToolError):
        write_approved_artifact(tmp_path, "app/tests/app.test.js", AS_THE_RUN_WROTE_IT)

    assert (tmp_path / "app" / "tests" / "app.test.js").read_text(encoding="utf-8") == A_SUITE


# --- and a command that ran nothing is not a pass -----------------------------


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "the-app-run-abc"
    root.mkdir()
    return root


def _ran(root: Path, *entries: dict) -> None:
    path = _ledger_path(str(root))
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")


def _entry(stage: str, code: int, **counts) -> dict:
    return {"stage": stage, "command": ["npm", "test"], "category": "test", "returncode": code, "error": None, **counts}


def test_exit_zero_with_every_test_skipped_is_not_a_pass(workspace) -> None:
    _ran(workspace, _entry("test_round_1", 0, passed=0, failed=0, tests=1))

    assert _where_each_test_command_stands(str(workspace)) == {"npm test": False}
    assert _the_test_command_this_stage_left_failing(str(workspace), "test_round_1") == (
        "npm test", "exited 0 without a single test passing",
    )


def test_a_run_whose_totals_cannot_be_read_is_judged_by_its_exit_code(workspace) -> None:
    _ran(workspace, _entry("test_round_1", 0))

    assert _where_each_test_command_stands(str(workspace)) == {"npm test": True}
    assert _the_test_command_this_stage_left_failing(str(workspace), "test_round_1") == ("", "")


def test_a_run_with_passing_tests_is_a_pass(workspace) -> None:
    _ran(workspace, _entry("test_round_1", 0, passed=4, failed=0, tests=4))

    assert _where_each_test_command_stands(str(workspace)) == {"npm test": True}
