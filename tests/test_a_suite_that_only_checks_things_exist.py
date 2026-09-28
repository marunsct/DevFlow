"""A suite whose every assertion is an existence check.

`a_test_that_asserts_nothing` catches a suite with no assertion at all. This is
the next shape along: every assertion is `typeof x === 'function'` or similar,
so the suite is green the moment the exports exist and says nothing whatever
about what they do.

Run 1c9854c7 wrote `app.test.js` as five cases of exactly one form:

    test('loadTasks is a function', () => {
      assert.strictEqual(typeof loadTasks, 'function');
    });

against an `app.js` whose five exported functions were each an empty body and a
`// TODO` comment. `npm test` reported `# tests 5 # pass 5 # fail 0`, and every
gate that asks whether the tests pass was satisfied by a product that does
nothing at all.
"""

from __future__ import annotations

from app.analysis.test_discovery import (
    a_suite_that_only_checks_things_exist as only_existence,
)

TAUTOLOGICAL = """import { test } from 'node:test';
import assert from 'node:assert';
import { loadTasks, addTask } from './app.js';

test('loadTasks is a function', () => {
  assert.strictEqual(typeof loadTasks, 'function');
});

test('addTask is a function', () => {
  assert.strictEqual(typeof addTask, 'function');
});
"""

BEHAVIOURAL = """import { test } from 'node:test';
import assert from 'node:assert';
import { addTask } from './app.js';

test('addTask adds one', () => {
  assert.strictEqual(addTask('milk', []).length, 1);
});
"""


def test_a_suite_of_only_existence_checks_is_reported():
    note = only_existence("app.test.js", TAUTOLOGICAL)

    assert note is not None
    assert "only checks that something exists" in note


def test_it_says_why_that_cannot_fail():
    note = only_existence("app.test.js", TAUTOLOGICAL)

    assert "cannot fail for a stub" in note
    assert "Assert what each function returns or changes" in note


def test_one_behavioural_assertion_is_enough_to_stay_quiet():
    """Checking an export exists and then what it does is a guard, not a fault."""
    both = TAUTOLOGICAL + BEHAVIOURAL

    assert only_existence("app.test.js", both) is None


def test_a_behavioural_suite_is_left_alone():
    assert only_existence("app.test.js", BEHAVIOURAL) is None


def test_a_deep_equality_assertion_is_not_an_existence_check():
    """The regex once allowed an optional `.method` and matched almost every
    real assertion. Three suites across the stored workspaces were reported
    for asserting `assert.deepStrictEqual(tasks, [])`, which is behaviour."""
    suite = (
        "import assert from 'assert';\n"
        "assert.strictEqual(typeof init, 'function');\n"
        "assert.deepStrictEqual(tasks, []);\n"
    )

    assert only_existence("a.test.mjs", suite) is None


def test_a_bare_truthiness_check_still_counts_as_existence():
    suite = (
        "import assert from 'assert';\n"
        "assert(loadTasks);\n"
        "assert(addTask, 'should be exported');\n"
    )

    assert only_existence("a.test.mjs", suite) is not None


def test_a_single_assertion_is_below_the_floor():
    """One existence check is a guard at the top of a file, not a suite."""
    suite = "import assert from 'assert';\nassert.strictEqual(typeof a, 'function');\n"

    assert only_existence("a.test.mjs", suite) is None


def test_the_reviewer_reports_it_too(tmp_path):
    from pathlib import Path

    from app.analysis.integration_checks import _severity_of, _tests_that_cannot_fail

    project = tmp_path / "app"
    project.mkdir()
    suite = project / "app.test.js"
    suite.write_text(TAUTOLOGICAL, encoding="utf-8")

    problems = _tests_that_cannot_fail([suite], tmp_path)

    assert any("only checks that something exists" in p for p in problems)
    assert all(_severity_of(p) == "BREAKS" for p in problems)


def test_feature_detection_is_not_an_existence_assertion():
    """`typeof window !== 'undefined'` is what application code does constantly.

    Run 551640d3's `app.js` guards every storage access that way, and with
    `'undefined'` in the pattern it was reported as a suite of existence checks
    - a blocking finding against the application itself.
    """
    defensive = (
        "const s = typeof window !== 'undefined' ? window.localStorage : null;\n"
        "const g = typeof global !== 'undefined' ? global.localStorage : null;\n"
        "export function loadTasks() { return []; }\n"
    )

    assert only_existence("app.test.js", defensive) is None


def test_the_tautological_suite_is_still_caught():
    """The narrowing must not cost the case the check exists for."""
    assert only_existence("app.test.js", TAUTOLOGICAL) is not None


def test_application_files_are_not_asked_whether_they_can_fail(tmp_path):
    """`_tests_that_cannot_fail` ran all four checks over every file.

    "Can this suite fail" is not a question about application code, and asking
    it of `app.js` is how one run's application became a blocking finding.
    """
    from app.analysis.integration_checks import _tests_that_cannot_fail

    project = tmp_path / "app"
    project.mkdir()
    application = project / "app.js"
    application.write_text(
        "const s = typeof window !== 'undefined' ? window.localStorage : null;\n"
        "const d = typeof document !== 'undefined' ? document.body : null;\n"
        "export function loadTasks() { return []; }\n",
        encoding="utf-8",
    )

    assert _tests_that_cannot_fail([application], tmp_path) == []
