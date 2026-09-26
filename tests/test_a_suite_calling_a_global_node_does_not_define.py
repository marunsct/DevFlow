"""A suite calling `describe`/`it`/`test` without importing them.

Jest, Vitest and Mocha inject them as globals. `node --test` does not - they
are exports of `node:test`, and a file that calls one without importing it
throws on the first case. Verified in the worker image on Node 20.20.2: a
well-formed suite with a real assertion, using `describe`/`it` and importing
neither, reports

    # ReferenceError: describe is not defined
    # pass 0   # fail 1

`_suites_calling_a_global_node_does_not_define` already finds it at a
milestone review, and it cost run d6297b2f and run 0afef410 a round each
before that. This asks the same question at the write, where one import line
fixes it.
"""

from __future__ import annotations

import json

import pytest

from app.analysis.test_discovery import a_suite_calling_a_global_node_does_not_define

WITH_GLOBALS = (
    "import assert from 'node:assert';\n"
    "import { addTask } from './app.js';\n"
    "describe('addTask', () => {\n"
    "  it('returns a task', () => { assert.ok(addTask('a')); });\n"
    "});\n"
)


def _project(tmp_path, **files: str):
    for name, body in files.items():
        (tmp_path / name.replace("__", ".")).write_text(body)
    return tmp_path


def test_a_suite_that_imports_neither_is_named(tmp_path):
    note = a_suite_calling_a_global_node_does_not_define(
        "app.test.mjs", WITH_GLOBALS, _project(tmp_path)
    )
    assert note is not None
    assert "ReferenceError: describe is not defined" in note
    assert "import { describe } from 'node:test';" in note


def test_importing_them_from_node_test_says_nothing(tmp_path):
    imported = "import { describe, it } from 'node:test';\n" + WITH_GLOBALS
    assert (
        a_suite_calling_a_global_node_does_not_define(
            "app.test.mjs", imported, _project(tmp_path)
        )
        is None
    )


@pytest.mark.parametrize(
    "files",
    [
        {"package__json": json.dumps({"devDependencies": {"jest": "^29"}})},
        {"package__json": json.dumps({"devDependencies": {"vitest": "^1"}})},
        {"vitest__config__js": "export default {};\n"},
        {"jest__config__js": "module.exports = {};\n"},
    ],
)
def test_a_runner_that_provides_the_globals_makes_this_silent(tmp_path, files):
    assert (
        a_suite_calling_a_global_node_does_not_define(
            "app.test.mjs", WITH_GLOBALS, _project(tmp_path, **files)
        )
        is None
    )


def test_the_manifest_is_found_from_a_subdirectory(tmp_path):
    """`src/sprint2.test.js` and `tests/tasks.test.js` both sit a level below
    the `package.json` that declares their runner. Looking only beside the
    suite reported three working files as broken.
    """
    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"vitest": "^1"}})
    )
    nested = tmp_path / "src"
    nested.mkdir()
    assert (
        a_suite_calling_a_global_node_does_not_define(
            "sprint2.test.js", WITH_GLOBALS, nested
        )
        is None
    )


def test_a_file_that_is_not_a_test_is_left_alone(tmp_path):
    assert (
        a_suite_calling_a_global_node_does_not_define(
            "main.js", WITH_GLOBALS, _project(tmp_path)
        )
        is None
    )


def test_a_file_defining_its_own_helper_is_left_alone(tmp_path):
    own = "function describe(name, fn) { fn(); }\n" + WITH_GLOBALS
    assert (
        a_suite_calling_a_global_node_does_not_define(
            "app.test.mjs", own, _project(tmp_path)
        )
        is None
    )


def test_the_two_readings_of_a_suite_global_agree(tmp_path):
    """The write-time note and the cross-file check must not drift.

    They share their patterns by import rather than by copy; this pins the
    behaviour as well, in both directions.
    """
    from app.analysis.integration_checks import (
        _suites_calling_a_global_node_does_not_define,
    )

    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.js").write_text("export function addTask(t) { return t; }\n")
    suite = project / "app.test.mjs"
    suite.write_text(WITH_GLOBALS)

    from_review = _suites_calling_a_global_node_does_not_define(
        [suite, project / "app.js"], project
    )
    from_write = a_suite_calling_a_global_node_does_not_define(
        "app.test.mjs", WITH_GLOBALS, project
    )
    assert bool(from_review) == bool(from_write)

    # And silent together once the import is there.
    imported = "import { describe, it } from 'node:test';\n" + WITH_GLOBALS
    suite.write_text(imported)
    assert not _suites_calling_a_global_node_does_not_define(
        [suite, project / "app.js"], project
    )
    assert (
        a_suite_calling_a_global_node_does_not_define("app.test.mjs", imported, project)
        is None
    )


PLAYWRIGHT_SUITE = (
    "import { test, expect } from '@playwright/test';\n"
    "test('adds a task', async ({ page }) => {\n"
    "  await page.goto('/');\n"
    "  await expect(page.locator('#task-list')).toContainText('Test Task');\n"
    "});\n"
)


def test_a_playwright_suite_is_not_told_its_import_is_missing(tmp_path) -> None:
    """The import is on line 1 and names `test`. Saying "nothing imports
    `test`" here is false, and the remedy it offers - a second
    `import { test } from 'node:test'` - makes the file a SyntaxError.

    run-ac04a164's testing specialist was given this note at sequences 118,
    130 and 144 while writing a `@playwright/test` suite, and rewrote the file
    after each one.
    """
    project = tmp_path / "proj"
    project.mkdir()

    assert (
        a_suite_calling_a_global_node_does_not_define(
            "proj/app.test.js", PLAYWRIGHT_SUITE, project
        )
        is None
    )


def test_the_two_readings_agree_on_a_playwright_suite(tmp_path) -> None:
    """The drift this missed once already.

    `test_the_two_readings_of_a_suite_global_agree` pins the two checks on a
    `node:test` suite, which both read the same way through the shared regex.
    The cross-file check then grew a second guard, `_imports_the_name`, for
    exactly this input - and the write-time check kept only the regex, so the
    two agreed on the case that was tested and disagreed on the case the guard
    was added for.
    """
    from app.analysis.integration_checks import (
        _suites_calling_a_global_node_does_not_define,
    )

    project = tmp_path / "proj"
    project.mkdir()
    suite = project / "app.test.js"
    suite.write_text(PLAYWRIGHT_SUITE)

    from_review = _suites_calling_a_global_node_does_not_define([suite], project)
    from_write = a_suite_calling_a_global_node_does_not_define(
        "app.test.js", PLAYWRIGHT_SUITE, project
    )

    assert not from_review, "the cross-file check already reads this correctly"
    assert from_write is None, "and the write-time check must read it the same way"


@pytest.mark.parametrize(
    "importer",
    [
        "import { test } from '@playwright/test';",
        "import { test as check } from 'vitest';",
        "import test from 'ava';",
        "const { test } = require('node:test');",
    ],
)
def test_the_name_is_bound_whichever_module_bound_it(tmp_path, importer: str) -> None:
    """Which module binds `test` does not change whether it is defined."""
    project = tmp_path / "proj"
    project.mkdir()
    called = "check" if " as check" in importer else "test"
    content = f"{importer}\n{called}('a case', () => {{}});\n"

    assert (
        a_suite_calling_a_global_node_does_not_define("app.test.js", content, project)
        is None
    )


def test_a_suite_that_really_has_no_import_is_still_caught(tmp_path) -> None:
    """The check must keep doing its job: this is the failure it exists for."""
    project = tmp_path / "proj"
    project.mkdir()
    content = "test('a case', () => {});\n"

    note = a_suite_calling_a_global_node_does_not_define("app.test.js", content, project)

    assert note is not None
    assert "ReferenceError: test is not defined" in note
