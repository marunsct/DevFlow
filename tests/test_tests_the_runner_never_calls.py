"""A green suite whose cases never execute.

Run d6297b2f's test round hit `ReferenceError: describe is not defined` - a
Jest-shaped suite under `node --test` - and fixed it by moving every case
inside a default-exported function. `npm test` then returned 0 with

    # tests 1   # suites 0   # pass 1   # fail 0

That one passing test is the file, not anything in it: `node --test` runs the
cases that register themselves as a test file loads and never calls what the
module exports. Seven cases with real assertions over real behaviour, none of
them run, and every gate that asks whether the tests pass was satisfied.
"""

from __future__ import annotations

from pathlib import Path

# Aliased because pytest collects any module-level name matching `test*`,
# and would call the check itself as a test case.
from app.analysis.test_discovery import (
    tests_the_runner_will_never_call as will_never_run,
)

STRANDED = """// Simple Todo List App Tests
import { loadTasks, addTask } from './app.js';
import assert from 'assert';
export default function (t) {
  t.test('loadTasks returns empty array when no data', () => {
    assert.deepStrictEqual(loadTasks(), []);
  });

  t.test('addTask adds a new task with unique id', () => {
    assert.strictEqual(addTask('Buy milk', '', []).length, 1);
  });
}
"""

RUNS = """import { test } from 'node:test';
import assert from 'node:assert';

test('addTask adds a new task with unique id', () => {
  assert.strictEqual(addTask('Buy milk', '', []).length, 1);
});
"""


def test_cases_stranded_in_a_default_export_are_reported():
    note = will_never_run("app.test.mjs", STRANDED)

    assert note is not None
    assert "2 test case(s)" in note
    assert "loadTasks returns empty array when no data" in note


def test_the_note_says_what_to_do_instead():
    note = will_never_run("app.test.mjs", STRANDED)

    assert "top level" in note
    assert "node:test" in note


def test_a_suite_the_runner_does_run_is_left_alone():
    assert will_never_run("app.test.mjs", RUNS) is None


def test_an_exported_helper_beside_real_cases_is_left_alone():
    """A file may export something and still register its cases properly."""
    both = RUNS + "\nexport default function helper(t) {\n  t.test('inner', () => {});\n}\n"

    assert will_never_run("app.test.mjs", both) is None


def test_a_module_that_exports_a_function_and_has_no_cases_is_left_alone():
    plain = "export default function setup() {\n  return 1;\n}\n"

    assert will_never_run("helpers.mjs", plain) is None


def test_the_commonjs_spelling_of_the_same_mistake_is_reported():
    cjs = STRANDED.replace("export default function (t) {", "module.exports = function (t) {")

    assert will_never_run("app.test.js", cjs) is not None


def test_the_reviewer_reports_it_too(tmp_path: Path):
    from app.analysis.integration_checks import _tests_that_cannot_fail

    project = tmp_path / "todo"
    project.mkdir()
    suite = project / "app.test.mjs"
    suite.write_text(STRANDED, encoding="utf-8")

    problems = _tests_that_cannot_fail([suite], tmp_path)

    assert any("never calls the export" in p or "never calls" in p for p in problems)
