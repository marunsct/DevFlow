"""A test that asserts only constants is reported, not counted as evidence.

One run finished with "26 passed" in its Sprint Record; 4 of its 20 unit tests
were placeholders such as `assert.strictEqual(1 + 1, 2)` and `assert.ok(true)`
left by stages clearing their own debugging. The existing checks passed them:
there is an assertion, and it is not an existence check.
"""
from __future__ import annotations

import pytest

from app.analysis.test_discovery import a_suite_that_asserts_only_constants

HEAD = "import { test } from 'node:test';\nimport assert from 'node:assert';\n"


@pytest.mark.parametrize("body", [
    "test('quick placeholder', () => {\n  assert.strictEqual(1 + 1, 2);\n});\n",
    "test('tmp placeholder', () => {\n  assert.ok(true);\n});\n",
    "test('a', () => { assert.equal('x', 'x'); });\ntest('b', () => { assert(true); });\n",
])
def test_a_suite_of_constant_assertions_is_reported(body):
    problem = a_suite_that_asserts_only_constants("app/tests/quick.test.js", HEAD + body)

    assert problem and "asserts only constants" in problem


@pytest.mark.parametrize("body", [
    "import { addTask } from '../model.js';\ntest('adds', () => {\n  assert.strictEqual(addTask('a').title, 'a');\n});\n",
    "import { total } from '../cart.js';\ntest('sum', () => {\n  const t = total([1, 2]);\n  assert.strictEqual(t, 3);\n  assert.ok(true);\n});\n",
    "test('no assertion here', () => {});\n",
])
def test_a_suite_that_names_anything_is_not(body):
    assert a_suite_that_asserts_only_constants("app/tests/model.test.js", HEAD + body) is None


def test_a_browser_test_is_not():
    content = (
        "import { test, expect } from '@playwright/test';\n"
        "test('adds', async ({ page }) => {\n  await page.goto('/');\n"
        "  await expect(page.locator('li')).toHaveCount(1);\n});\n"
    )
    assert a_suite_that_asserts_only_constants("app/e2e/add.spec.js", content) is None


def test_the_reviewer_s_cross_file_checks_report_it(tmp_path):
    from app.analysis.integration_checks import _tests_that_cannot_fail

    (tmp_path / "app" / "tests").mkdir(parents=True)
    placeholder = tmp_path / "app" / "tests" / "tmp.test.js"
    placeholder.write_text(HEAD + "test('tmp', () => { assert.ok(true); });\n", encoding="utf-8")

    problems = _tests_that_cannot_fail([placeholder], tmp_path)

    assert any("asserts only constants" in p for p in problems)
