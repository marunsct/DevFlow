"""No check may tell a reviewer that an application file is a bad test suite.

Run 551640d3 was handed, thirteen times, a blocking finding reading

    todo-app/app.js has 3 assertion(s) and every one of them only checks that
    something exists

and echoed it into its milestone review as a defect to fix. It cannot be
fixed: `app.js` is the application, and the `typeof window !== 'undefined'`
guards it flagged are feature detection. The run spent 1,681 events returning
`changes_required` on a requirement nothing could satisfy.

Two faults made it. `_tests_that_cannot_fail` ran every test-discovery check
over every file, and `_ONLY_CHECKS_IT_EXISTS` read `'undefined'` as an
existence assertion. Both are fixed; this is the invariant that keeps them so,
and that catches the next check written into that group without a guard of its
own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.file_kinds import is_test
from app.analysis.integration_checks import _tests_that_cannot_fail

#: An ordinary application file: feature detection, a DOM write, no test cases.
APPLICATION = """const storage = typeof window !== 'undefined' ? window.localStorage : null;
const root = typeof document !== 'undefined' ? document.getElementById('list') : null;

export function loadTasks() {
  if (typeof storage === 'object' && storage) {
    return JSON.parse(storage.getItem('tasks') || '[]');
  }
  return [];
}

export function render(tasks) {
  if (typeof root !== 'undefined' && root) {
    root.textContent = String(tasks.length);
  }
}
"""


@pytest.mark.parametrize(
    "name", ["app.js", "app.mjs", "index.js", "storage.js", "main.cjs"]
)
def test_an_application_file_is_never_reported_as_a_suite(tmp_path: Path, name: str):
    project = tmp_path / "app"
    project.mkdir(exist_ok=True)
    path = project / name
    path.write_text(APPLICATION, encoding="utf-8")

    assert _tests_that_cannot_fail([path], tmp_path) == []


def test_the_group_only_looks_at_files_it_considers_tests(tmp_path: Path):
    """The guard is the filter, not each check's own luck.

    Three of the four checks in this group escaped the bug only because they
    happen to require test cases or a `node:test` import first. A fourth
    written without such a guard would have the same fault again.
    """
    project = tmp_path / "app"
    project.mkdir()
    application = project / "app.js"
    application.write_text(APPLICATION, encoding="utf-8")
    suite = project / "app.test.js"
    suite.write_text(
        "import { test } from 'node:test';\n"
        "import assert from 'node:assert';\n"
        "test('a', () => { assert.strictEqual(typeof loadTasks, 'function'); });\n"
        "test('b', () => { assert.strictEqual(typeof render, 'function'); });\n",
        encoding="utf-8",
    )

    problems = _tests_that_cannot_fail([application, suite], tmp_path)

    assert problems, "the real tautological suite must still be reported"
    assert all(is_test(p.split()[0]) for p in problems)


def test_every_finding_in_the_corpus_names_a_test_file(tmp_path: Path):
    """Swept over shapes this harness actually produces, not only tidy ones."""
    project = tmp_path / "app"
    project.mkdir()
    shapes = {
        "app.js": APPLICATION,
        "styles.js": "export const css = 'body { margin: 0 }';\n",
        "config.js": "module.exports = { port: typeof process !== 'undefined' ? 1 : 2 };\n",
        "app.test.mjs": "import { test } from 'node:test';\ntest('x', () => {});\n",
    }
    written = []
    for name, body in shapes.items():
        path = project / name
        path.write_text(body, encoding="utf-8")
        written.append(path)

    for problem in _tests_that_cannot_fail(written, tmp_path):
        named = problem.split()[0]
        assert is_test(named), f"{named} is not a test file but was reported: {problem[:80]}"
