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
    """Node's default patterns, each one - verified by running Node, not by
    reading the documentation. See `test_the_prefix_form_takes_a_hyphen_only`."""
    assert undiscoverable_test(path, NODE_TEST) is None


@pytest.mark.parametrize(
    "name",
    [
        "test_add_task.mjs",
        "test_delete_task.mjs",
        "test_persistence.mjs",
        "test_toggle_task.cjs",
    ],
)
def test_the_prefix_form_takes_a_hyphen_only(name: str) -> None:
    """`test-*` is collected; `test_*` is not, and this check said it was.

    Verified by running Node over six names in one directory:

        ok  add-task-test.mjs   ok  add.test.mjs   ok  add_task_test.mjs
        ok  test-add-task.mjs   ok  test.mjs       --  test_add_task.mjs

    Five of six. run-04576307 wrote six suites in the underscore-prefix form -
    `test_add_task.mjs`, `test_delete_task.mjs`, `test_edit_task.mjs`,
    `test_filter_tasks.mjs`, `test_persistence.mjs`, `test_toggle_task.mjs` -
    none of which Node runs, and this check called every one of them fine.
    """
    note = undiscoverable_test(f"todo-app/{name}", NODE_TEST)

    assert note is not None
    assert "will not collect it" in note


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


# --- a browser API built by hand -------------------------------------------


RUN_D3965815 = """import test from 'node:test';
import assert from 'node:assert';

global.document = {
  getElementById: (id) => ({ innerHTML: '', children: [], appendChild() {} }),
};

test('renders', () => { assert.ok(true); });
"""


def test_a_hand_built_dom_is_flagged() -> None:
    """Three runs have lost remediation rounds to this.

    The mock holds until the code under test touches something it does not
    have, and the failure then reads as an application bug inside application
    code: `TypeError: Cannot read properties of undefined (reading
    'children')`. run-d3965815 spent three remediation rounds on exactly that.
    """
    from app.analysis.test_discovery import a_dom_built_by_hand

    note = a_dom_built_by_hand("app.test.mjs", RUN_D3965815)

    assert note is not None
    assert "npm install --save-dev jsdom" in note
    assert "runtime dependency" in note, "a brief that forbids dependencies means the product's"


@pytest.mark.parametrize(
    "content",
    [
        # A real DOM is already in use.
        "import test from 'node:test';\nimport { JSDOM } from 'jsdom';\n"
        "global.document = new JSDOM().window.document;\n",
        "import test from 'node:test';\nimport 'global-jsdom/register';\n"
        "global.window = window;\n",
        # No browser API at all.
        "import test from 'node:test';\nimport { addTask } from './app.js';\n",
    ],
)
def test_what_this_must_not_flag(content: str) -> None:
    from app.analysis.test_discovery import a_dom_built_by_hand

    assert a_dom_built_by_hand("app.test.mjs", content) is None


def test_application_code_is_not_a_test(tmp_path) -> None:
    from app.analysis.test_discovery import a_dom_built_by_hand

    assert a_dom_built_by_hand("app.js", "global.document = {};\n") is None


def test_the_note_reaches_the_write_as_well(tmp_path) -> None:
    from app.tools.repository import write_approved_artifact

    write_approved_artifact(tmp_path, "proj/package.json", '{"name": "proj"}')

    result = write_approved_artifact(tmp_path, "proj/app.test.mjs", RUN_D3965815)

    assert "npm install --save-dev jsdom" in (result.get("note") or "")


RUN_A7150A6C = """// Test to ensure style.css is linked in index.html
import fs from 'fs';
const html = fs.readFileSync('simple-to-do-list-app/index.html', 'utf8');
if (!html.includes('<link rel="stylesheet" href="style.css">')) {
  throw new Error('style.css link missing');
}
console.log('Style link found');
"""


def test_a_test_by_name_with_no_framework_import_is_still_judged() -> None:
    """Requiring a `node:test` import missed the shape run-a7150a6c produced.

    `app.test.mjs`, importing only `fs`, reading `index.html`, throwing if a
    `<link>` tag was absent. No framework import, so the first version of this
    check said nothing - about a file the project calls a test and that
    exercises no application code at all.
    """
    from app.analysis.test_discovery import tests_nothing_of_the_project

    note = tests_nothing_of_the_project("proj/app.test.mjs", RUN_A7150A6C)

    assert note is not None
    assert "imports nothing from the project" in note


def test_an_application_file_is_still_not_a_test() -> None:
    from app.analysis.test_discovery import tests_nothing_of_the_project

    assert tests_nothing_of_the_project(
        "proj/app.js", "import fs from 'fs';\nexport const a = 1;\n"
    ) is None


def test_an_empty_test_file_says_nothing() -> None:
    from app.analysis.test_discovery import tests_nothing_of_the_project

    assert tests_nothing_of_the_project("proj/app.test.mjs", "") is None
    assert tests_nothing_of_the_project("proj/app.test.mjs", "\n\n") is None


# --- a test that needs a DOM and has none ----------------------------------


DOM_MODULE = """export function addTask(title) { render(); }
function render() { const list = document.getElementById('task-list'); }
if (typeof document !== "undefined") { render(); }
"""

RUN_740EDB6B = """import { addTask } from './app.js';
import { test } from 'node:test';
import assert from 'assert';

let storage = {};
global.localStorage = {
  getItem: (key) => storage[key] || null,
  setItem: (key, value) => { storage[key] = value; }
};

test('addTask persists a new task', () => { addTask('x'); });
"""


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "app.js").write_text(DOM_MODULE, encoding="utf-8")
    (tmp_path / "pure.js").write_text("export const add = (a, b) => a + b;\n", encoding="utf-8")
    return tmp_path


def test_the_run_740edb6b_test_is_warned(project) -> None:
    """Four runs have ended a stage on `document is not defined`.

    run-740edb6b's `addTask.test.mjs` imported `addTask` from a module whose
    render path calls `document.getElementById`, mocked `localStorage` and
    nothing else, and reported that ReferenceError for every test in the file.
    The module guards its top level, so the import succeeds and the failure
    arrives only when a function is called - which is why no syntax or import
    check sees it.
    """
    from app.analysis.test_discovery import a_test_that_needs_a_dom

    note = a_test_that_needs_a_dom("addTask.test.mjs", RUN_740EDB6B, project)

    assert note is not None
    assert "document is not defined" in note
    assert "jsdom" in note


@pytest.mark.parametrize(
    "prelude",
    [
        "import { JSDOM } from 'jsdom';\nglobal.document = new JSDOM().window.document;\n",
        "import 'global-jsdom/register';\n",
        "global.document = { getElementById: () => ({}) };\n",
    ],
)
def test_a_test_that_provides_a_dom_is_silent(project, prelude: str) -> None:
    from app.analysis.test_discovery import a_test_that_needs_a_dom

    assert a_test_that_needs_a_dom("a.test.mjs", prelude + RUN_740EDB6B, project) is None


def test_a_dom_free_module_is_silent(project) -> None:
    from app.analysis.test_discovery import a_test_that_needs_a_dom

    content = "import { add } from './pure.js';\nimport { test } from 'node:test';\n"

    assert a_test_that_needs_a_dom("a.test.mjs", content, project) is None


def test_a_localstorage_mock_is_not_a_hand_built_dom() -> None:
    """It is a string-keyed map with four methods and does not collapse the way
    a `document` stub does.

    Including it meant run-740edb6b's test - which mocks `localStorage`, sets
    up no DOM, and fails with `document is not defined` - was told its
    localStorage mock was the problem, and the right note could not fire.
    """
    from app.analysis.test_discovery import a_dom_built_by_hand

    content = "import test from 'node:test';\nglobal.localStorage = { getItem: () => null };\n"

    assert a_dom_built_by_hand("a.test.mjs", content) is None


def test_a_document_stub_is_still_a_hand_built_dom() -> None:
    from app.analysis.test_discovery import a_dom_built_by_hand

    content = "import test from 'node:test';\nglobal.document = { getElementById: () => ({}) };\n"

    assert a_dom_built_by_hand("a.test.mjs", content) is not None
