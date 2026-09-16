"""A test file the runner will never collect.

run-d3965815's security specialist wrote `todo-app/app.test_xss.mjs`: real
assertions, for a real XSS concern. `node --test todo-app/` collected
`app.test.mjs` and reported "# tests 1" while two test files sat in the
directory. Nothing failed, because an uncollected test does not error - it is
simply absent, and the testing round, the milestone review and the defect loop
all read a green result that never included it.
"""

from __future__ import annotations

import pytest

from app.analysis.test_discovery import undiscoverable_test

NODE_TEST = (
    "import test from 'node:test';\n"
    "import assert from 'node:assert';\n"
    "test('escapes markup', () => assert.ok(true));\n"
)


def test_the_file_from_run_d3965815_is_caught() -> None:
    note = undiscoverable_test("todo-app/app.test_xss.mjs", NODE_TEST)

    assert note is not None
    assert "will not collect it" in note
    assert "app-xss.test.mjs" in note, "a name that works must be offered"


@pytest.mark.parametrize(
    "path",
    [
        "todo-app/app.test.mjs",
        "todo-app/app.test.js",
        "todo-app/app.test.cjs",
        "todo-app/app-test.mjs",
        "todo-app/app_test.mjs",
        "todo-app/test-xss.mjs",
        "todo-app/test.mjs",
        "todo-app/test/anything.mjs",
        "todo-app/tests/anything.mjs",
        "todo-app/__tests__/anything.mjs",
    ],
)
def test_a_name_node_collects_is_left_alone(path: str) -> None:
    """Node's documented default patterns, each one."""
    assert undiscoverable_test(path, NODE_TEST) is None


@pytest.mark.parametrize(
    ("path", "content"),
    [
        # Another runner, with its own patterns and its own config file.
        ("src/Widget.spec.ts", "import { describe, it } from 'vitest';\n"),
        ("src/Widget.spec.mjs", "import { describe } from 'vitest';\n"),
        # An application module that happens to export something called `test`.
        ("todo-app/app.mjs", "export function test(a) { return a; }\ntest(1);\n"),
        # Not JavaScript at all.
        ("todo-app/style.css", ".a { color: red }"),
        ("scripts/check.py", "import pytest\n"),
        # Empty.
        ("todo-app/thing.mjs", ""),
    ],
)
def test_what_this_must_not_warn_about(path: str, content: str) -> None:
    """A wrong warning about a file that runs fine is worse than no warning."""
    assert undiscoverable_test(path, content) is None


def test_a_plausible_name_that_still_does_not_match() -> None:
    """`security.mjs` is a perfectly reasonable name and is never collected."""
    note = undiscoverable_test("todo-app/security.mjs", NODE_TEST)

    assert note is not None
    assert "security.test.mjs" in note


def test_the_note_reaches_the_write(tmp_path) -> None:
    from app.tools.repository import write_approved_artifact

    write_approved_artifact(tmp_path, "todo-app/package.json", '{"name": "todo-app"}')

    result = write_approved_artifact(tmp_path, "todo-app/app.test_xss.mjs", NODE_TEST)

    assert "will not collect it" in (result.get("note") or "")


# --- a test that tests nothing ---------------------------------------------


DOCUMENTATION_TEST = """import { test } from 'node:test';
import assert from 'assert';
import fs from 'fs';
import path from 'path';

const __dirname = path.dirname(new URL(import.meta.url).pathname);

test('package.json has correct name', () => {
  const data = JSON.parse(fs.readFileSync(path.join(__dirname, 'package.json'), 'utf8'));
  assert.strictEqual(data.name, 'simple-to-do-list-app');
});

test('README.md exists and contains title', () => {
  const content = fs.readFileSync(path.join(__dirname, 'README.md'), 'utf8');
  assert.ok(content.includes('# Simple To-Do List App'));
});
"""


def test_the_four_green_tests_from_run_84e05d4b_are_flagged() -> None:
    """Four passing assertions, none touching a line of application code.

    There was none in the project to touch. The test round passed, the security
    review passed, and the milestone review raised two minor issues about
    paths. Every gate asks whether the tests pass; none asked what they test.
    """
    from app.analysis.test_discovery import tests_nothing_of_the_project

    note = tests_nothing_of_the_project("app.test.js", DOCUMENTATION_TEST)

    assert note is not None
    assert "imports nothing from the project" in note
    assert "Import the module under test" in note


@pytest.mark.parametrize(
    "content",
    [
        "import test from 'node:test';\nimport { addTask } from './app.js';\n",
        "import test from 'node:test';\nimport store from '../src/store.mjs';\n",
        "const test = require('node:test');\nconst { addTask } = require('./app.js');\n",
        "import test from 'node:test';\nconst mod = await import('./app.js');\n",
    ],
)
def test_a_test_that_imports_the_code_is_left_alone(content: str) -> None:
    from app.analysis.test_discovery import tests_nothing_of_the_project

    assert tests_nothing_of_the_project("app.test.js", content) is None


def test_a_file_that_is_not_a_test_is_left_alone() -> None:
    from app.analysis.test_discovery import tests_nothing_of_the_project

    assert tests_nothing_of_the_project("app.js", "export const a = 1;\n") is None


def test_the_note_reaches_the_write_too(tmp_path) -> None:
    from app.tools.repository import write_approved_artifact

    write_approved_artifact(tmp_path, "proj/package.json", '{"name": "proj"}')

    result = write_approved_artifact(tmp_path, "proj/app.test.js", DOCUMENTATION_TEST)

    assert "imports nothing from the project" in (result.get("note") or "")
