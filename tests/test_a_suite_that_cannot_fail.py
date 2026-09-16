r"""Two ways a test file reports something other than the truth about the code.

Both measured on run f81808a4, on the same file, within one hour.

It was first written as its whole suite, 164 bytes:

    import assert from 'node:assert';
    import { test } from 'node:test';
    import './main.js';
    test('main.js loads without error', () => {
      // no assertions needed
    });

`node --test` reports "# pass 1  # fail 0". `assert` is imported and never
called. The file imports the project, so `tests_nothing_of_the_project` is
satisfied; it runs, so `undiscoverable_test` is; it passes, so every gate that
asks whether the tests pass is too.

Rewritten with four real tests, it then imported the wrong module - first
`import assert from 'node:test'`, then `import { test, assert } from
'node:test'` - and every case threw before asserting anything.
"""

import pytest

from app.analysis.test_discovery import (
    a_test_that_asserts_nothing,
    assertions_called_on_the_test_module,
)

VACUOUS = (
    "import assert from 'node:assert';\n"
    "import { test } from 'node:test';\n"
    "import './main.js';\n\n"
    "test('main.js loads without error', () => {\n"
    "  // no assertions needed\n"
    "});\n"
)

REAL = (
    "import { test } from 'node:test';\n"
    "import assert from 'node:assert';\n"
    "import { addTask } from './main.js';\n\n"
    "test('addTask appends a task', () => {\n"
    "  assert.strictEqual(addTask('x').length, 1);\n"
    "});\n"
)


# --- a suite that cannot fail --------------------------------------------


def test_the_measured_vacuous_suite_is_reported():
    problem = a_test_that_asserts_nothing("main.test.js", VACUOUS)

    assert problem is not None
    assert "cannot fail" in problem
    assert "main.js loads without error" in problem


def test_a_suite_with_assertions_is_silent():
    assert a_test_that_asserts_nothing("main.test.js", REAL) is None


@pytest.mark.parametrize(
    "body",
    [
        "expect(add(1, 2)).toBe(3);",
        "assert.ok(x);",
        "should.equal(a, b);",
        "if (!x) throw new Error('nope');",
        "strictEqual(a, b);",
        "await assert.rejects(fn);",
    ],
)
def test_assertions_are_recognised_across_runners(body):
    source = f"import {{ test }} from 'node:test';\ntest('a', () => {{ {body} }});\n"
    assert a_test_that_asserts_nothing("a.test.js", source) is None


def test_a_helper_beside_the_suite_is_not_a_vacuous_test():
    """No test cases registered, so there is nothing that cannot fail."""
    assert a_test_that_asserts_nothing("helpers.test.js", "export const make = () => ({});") is None


def test_a_file_that_is_not_a_test_is_left_alone():
    """An application module calling a function named `test` is not a suite."""
    assert a_test_that_asserts_nothing("main.js", VACUOUS) is None


# --- assertions called on the test module --------------------------------


def test_the_default_import_form_is_reported():
    source = "import assert from 'node:test';\nassert.test('a', () => { assert.strictEqual(1, 1); });\n"

    problem = assertions_called_on_the_test_module("main.test.js", source)

    assert problem is not None
    assert "node:assert" in problem


def test_the_named_import_form_is_reported():
    """The second spelling the same run produced for the same file."""
    source = "import { test, assert } from 'node:test';\ntest('a', () => assert.strictEqual(1, 1));\n"

    problem = assertions_called_on_the_test_module("main.test.js", source)

    assert problem is not None
    assert "does not export it" in problem
    assert "undefined" in problem


def test_the_correct_imports_are_silent():
    assert assertions_called_on_the_test_module("main.test.js", REAL) is None


@pytest.mark.parametrize(
    "line",
    [
        "import { test, describe, it, beforeEach } from 'node:test';",
        "import { test as t } from 'node:test';",
        "import test from 'node:test';",
        "import test, { describe } from 'node:test';",
    ],
)
def test_legitimate_node_test_imports_are_silent(line):
    source = f"{line}\nimport assert from 'node:assert';\nassert.ok(1);\n"
    assert assertions_called_on_the_test_module("main.test.js", source) is None


def test_the_require_form_is_reported():
    source = "const assert = require('node:test');\nassert.ok(1);\n"

    assert assertions_called_on_the_test_module("main.test.js", source) is not None


# --- both reach a reviewer ------------------------------------------------


def test_both_are_blocking_findings():
    from app.analysis.integration_checks import _severity_of

    assert _severity_of(a_test_that_asserts_nothing("main.test.js", VACUOUS)) == "BREAKS"
    source = "import { test, assert } from 'node:test';\ntest('a', () => assert.ok(1));\n"
    assert _severity_of(assertions_called_on_the_test_module("a.test.js", source)) == "BREAKS"


def test_the_reviewer_is_told_these_were_checked():
    from app.analysis.integration_checks import _CHECKS

    assert any("cannot fail" in description for description, _ in _CHECKS)
