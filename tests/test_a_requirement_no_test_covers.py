"""A requirement the documents state and no test anywhere names.

Every verification this harness performs reads the implementation. Unit tests
import the module that exists; browser tests drive the page as built; reviewers
read the code in front of them. Nothing is derived from the requirement list,
so a requirement that was never built has no *failing* test - it has no test at
all, and a green suite reports that with confidence.

Run b0db10b1 demonstrates it cleanly. Its Playwright suite is good: 72
assertions, 22 `toHaveCount`, four page reloads checking persistence. It ran
six times, caught real failures early (`2 failed, 10 passed`) and finished
green at 14 tests. It grew from 12 tests to 14 as features were built, so the
filter tests arrived in the sprint that wired the filter buttons and never
existed while they were dead. `edit`, which that product never built, has no
test in any of its four files.

The companion to `_a_required_action_nothing_implements`, asking the other
question: not "does the product do it" but "would anything notice if it
stopped".
"""

from __future__ import annotations

import pytest

from app.analysis.integration_checks import (
    _a_required_action_no_test_covers,
    _source_files,
)

INTAKE = """# Product Intake

## Acceptance criteria
- Users can add, edit, delete tasks
"""


def _problems(root):
    return _a_required_action_no_test_covers(_source_files(root), root)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text(INTAKE)
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><script src="app.js"></script></body></html>'
    )
    # A complete implementation: the point is that the *suite* is the gap.
    (tmp_path / "app.js").write_text(
        "function addTask(t) { return t; }\n"
        "function editTask(id) { return id; }\n"
        "function deleteTask(id) { return id; }\n"
    )
    return tmp_path


def test_a_requirement_with_no_test_is_reported(project):
    (project / "app.test.mjs").write_text(
        "import { test } from 'node:test';\n"
        "test('adds a task', () => {});\n"
        "test('deletes a task', () => {});\n"
    )

    problems = _problems(project)

    assert len(problems) == 1, problems
    assert "`edit`" in problems[0]
    assert "app.test.mjs" in problems[0]
    assert "a failing test is the only thing here that remembers" in problems[0]


def test_a_covered_requirement_is_silent(project):
    (project / "app.test.mjs").write_text(
        "import { test } from 'node:test';\n"
        "test('adds a task', () => {});\n"
        "test('edits a task title', () => {});\n"
        "test('deletes a task', () => {});\n"
    )
    assert _problems(project) == []


def test_a_browser_test_counts_as_a_test(project):
    """Run b0db10b1 kept its filter coverage in a Playwright spec."""
    (project / "app.test.mjs").write_text(
        "import { test } from 'node:test';\ntest('adds', () => {});\n"
        "test('deletes', () => {});\n"
    )
    (project / "app.pw.spec.ts").write_text(
        "import { test } from '@playwright/test';\n"
        "test('renames a task inline', async ({ page }) => {});\n"
    )
    assert _problems(project) == []


def test_a_synonym_in_a_test_counts(project):
    (project / "app.test.mjs").write_text(
        "import { test } from 'node:test';\n"
        "test('adds', () => {});\ntest('renames a task', () => {});\n"
        "test('deletes', () => {});\n"
    )
    assert _problems(project) == []


def test_a_project_with_no_tests_is_left_to_the_other_checks(project):
    """A suite that does not exist is a different finding, already made."""
    assert _problems(project) == []


def test_implementation_alone_is_not_coverage(project):
    """The distinction from `_a_required_action_nothing_implements`.

    `editTask` is in `app.js` and the feature works. Nothing would notice if it
    stopped, and that is what this reports.
    """
    (project / "app.test.mjs").write_text(
        "import { test } from 'node:test';\ntest('adds', () => {});\n"
        "test('deletes', () => {});\n"
    )

    from app.analysis.integration_checks import _a_required_action_nothing_implements

    built = _a_required_action_nothing_implements(_source_files(project), project)
    tested = _problems(project)

    assert built == [], "the product does implement editing"
    assert len(tested) == 1, "and nothing tests it"


def test_a_method_of_the_same_name_is_not_coverage(project):
    """`tasks.filter(...)` taught this lesson once already."""
    (project / "app.test.mjs").write_text(
        "import { test } from 'node:test';\n"
        "test('adds', () => {});\ntest('deletes', () => {});\n"
        "const kept = tasks.edit;\n"  # member access, not a test of editing
    )
    problems = _problems(project)
    assert len(problems) == 1 and "`edit`" in problems[0]


def test_it_blocks_rather_than_reading_as_untidy():
    from app.analysis.integration_checks import _severity_of

    message = (
        "No test names `edit`, which this project's own documents require a "
        "user can do. Write the test for `edit` even if it fails today: a "
        "failing test is the only thing here that remembers."
    )
    assert _severity_of(message) == "BREAKS"
