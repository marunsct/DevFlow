""""A passing suite says nothing about those" was not true of a browser test.

The export-coverage finding lists exported names no test file mentions. Its
own docstring is careful - "reported as evidence rather than as a fault: an
export used only by other application code is legitimately exercised through
it, and this cannot tell the difference" - and the message a reviewer actually
reads was not: it said flatly that a passing suite says nothing about them.

A browser spec names `.edit-btn` and `page.locator`, never `editTask`, so
every export the page reaches is missing from it by construction.

Measured on run-07cd52ae, which shipped `editTask` and a Playwright test
`test('edits a task title')` that clicks the edit button, waits for the input
and checks the new title. The finding correctly said no test mentions
`editTask`, and then told the reviewer a passing suite said nothing about it.

The other machine's session notes put the cost of this shape in one sentence:
a check two consecutive reviewers have to overrule is the check's problem.

No inference from a selector to a function. That guess would be wrong often
enough to be worse than the caveat.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _exports_no_test_mentions,
    _source_files,
)

APP = """\
export function addTask(title) {}
export function editTask(id, title) {}
"""

UNIT_SUITE = """\
import { test } from 'node:test';
import { addTask } from './app.js';
test('adds', () => { addTask('x'); });
"""

BROWSER_SUITE = """\
import { test, expect } from '@playwright/test';
test('edits a task title', async ({ page }) => {
  await page.goto('/');
  await page.locator('.edit-btn').click();
});
"""


def _project(root: Path, **files: str) -> list[Path]:
    for name, text in files.items():
        path = root / name.replace("__", ".")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return _source_files(root)


def test_without_a_browser_test_the_claim_stands(tmp_path: Path):
    files = _project(tmp_path, app__js=APP, app__test__mjs=UNIT_SUITE)

    problems = _exports_no_test_mentions(files, tmp_path)

    assert len(problems) == 1
    assert "editTask" in problems[0]
    assert "A passing suite says nothing about those." in problems[0]
    assert "browser test" not in problems[0]


def test_with_a_browser_test_the_claim_is_qualified(tmp_path: Path):
    files = _project(
        tmp_path, app__js=APP, app__test__mjs=UNIT_SUITE, index__spec__mjs=BROWSER_SUITE
    )

    problems = _exports_no_test_mentions(files, tmp_path)

    assert len(problems) == 1
    assert "editTask" in problems[0], "still named - that part was correct"
    assert "may still be covered end to end" in problems[0]
    assert "before treating this as a gap" in problems[0]


@pytest.mark.parametrize(
    "spec",
    [
        "import { test } from '@playwright/test';\ntest('a', async ({page}) => {});",
        "test('a', async () => { await page.goto('/'); });",
        "describe('a', () => { it('b', () => { cy.visit('/'); }); });",
        "it('a', async () => { await browser.url('/'); });",
        "test('a', async ({ page }) => { await page.locator('.x').click(); });",
    ],
)
def test_every_shape_of_browser_suite_is_recognised(tmp_path: Path, spec: str):
    files = _project(tmp_path, app__js=APP, e2e__spec__mjs=spec)

    problems = _exports_no_test_mentions(files, tmp_path)

    assert problems, "the names are still reported"
    assert "may still be covered end to end" in problems[0]


def test_a_unit_suite_is_not_mistaken_for_a_browser_one(tmp_path: Path):
    """The word `page` in a variable name is not a browser driver."""
    suite = (
        "import { test } from 'node:test';\n"
        "test('a', () => { const page = 1; addTask(page); });\n"
    )
    files = _project(tmp_path, app__js=APP, app__test__mjs=suite)

    problems = _exports_no_test_mentions(files, tmp_path)

    assert problems
    assert "browser test" not in problems[0]


def test_the_finding_is_still_only_untidy(tmp_path: Path):
    """It is evidence for a reviewer, not a blocking defect, either way."""
    from app.analysis.integration_checks import _severity_of

    files = _project(
        tmp_path, app__js=APP, app__test__mjs=UNIT_SUITE, index__spec__mjs=BROWSER_SUITE
    )
    problem = _exports_no_test_mentions(files, tmp_path)[0]

    assert _severity_of(problem) == "untidy"


def test_a_fully_covered_module_says_nothing_at_all(tmp_path: Path):
    suite = (
        "import { test } from 'node:test';\n"
        "import { addTask, editTask } from './app.js';\n"
        "test('a', () => { addTask('x'); editTask(1, 'y'); });\n"
    )
    files = _project(tmp_path, app__js=APP, app__test__mjs=suite)

    assert _exports_no_test_mentions(files, tmp_path) == []
