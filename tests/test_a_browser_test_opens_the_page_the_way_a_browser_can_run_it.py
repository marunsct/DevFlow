"""A browser test that opens `file://` on a page of ES modules is named for what it is.

A browser does not run module scripts from a page opened off the disk. The
page loads, none of its code runs, and every case ends in a timeout that says
only what it was waiting for.

Measured on one run: three test rounds reported three different defects - a
selector, a timeout, a missing input - each a guess at a symptom, and the
sprint was planned again with the spec unchanged. The runner's configuration
already started a server and named its address.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis import integration_checks as checks

MODULE_PAGE = (
    "<!DOCTYPE html>\n<html><body><add-task-form></add-task-form>\n"
    "<script type=\"module\">\nimport './components/add-task-form.js';\n</script>\n</body></html>\n"
)
PLAIN_PAGE = "<!DOCTYPE html>\n<html><body><script src=\"app.js\"></script></body></html>\n"

AS_THE_RUN_WROTE_IT = (
    "import { test, expect } from '@playwright/test';\n\n"
    "test.beforeEach(async ({ page }) => {\n"
    "  const path = 'file://' + process.cwd() + '/index.html';\n"
    "  await page.goto(path, { waitUntil: 'domcontentloaded' });\n});\n\n"
    "test('adds', async ({ page }) => { await expect(page.locator('li')).toHaveCount(1); });\n"
)

CONFIG = (
    "module.exports = {\n  webServer: { command: 'npx http-server . -p 3000', port: 3000 },\n"
    "  use: { baseURL: 'http://localhost:3000' }\n};\n"
)


def _project(root: Path, files: dict) -> None:
    for name, content in {"app/package.json": '{"name": "app", "type": "module"}', **files}.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _found(root: Path) -> list[str]:
    return checks._a_browser_test_that_opens_a_module_page_from_disk(checks._source_files(root), root)


def test_the_run_s_spec_is_named_with_the_address_to_use(tmp_path: Path) -> None:
    _project(tmp_path, {
        "app/index.html": MODULE_PAGE,
        "app/tests/e2e.spec.js": AS_THE_RUN_WROTE_IT,
        "app/playwright.config.cjs": CONFIG,
    })

    (problem,) = _found(tmp_path)

    assert problem.startswith("app/tests/e2e.spec.js opens the page from disk (line 4")
    assert "app/index.html loads its code with `<script type=\"module\">`" in problem
    assert "Nothing is wrong with the selectors or with the product" in problem
    assert "app/playwright.config.cjs already names where the product is served" in problem
    assert "`baseURL: 'http://localhost:3000'`" in problem


def test_it_is_a_blocking_finding(tmp_path: Path) -> None:
    _project(tmp_path, {"app/index.html": MODULE_PAGE, "app/tests/e2e.spec.js": AS_THE_RUN_WROTE_IT})

    breaking = checks.problems_that_break_the_product(tmp_path)

    assert any("opens the page from disk" in problem for problem in breaking)
    assert any("start a static server" in problem for problem in breaking)


@pytest.mark.parametrize("spec", [
    AS_THE_RUN_WROTE_IT.replace("'file://' + process.cwd() + '/index.html'", "new URL('../index.html', import.meta.url).href"),
    AS_THE_RUN_WROTE_IT.replace("'file://' + process.cwd() + '/index.html'", "pathToFileURL('index.html').href"),
])
def test_an_address_built_from_a_path_on_disk_counts_however_it_is_built(tmp_path: Path, spec: str) -> None:
    _project(tmp_path, {"app/index.html": MODULE_PAGE, "app/tests/e2e.spec.js": spec})

    assert len(_found(tmp_path)) == 1


def test_a_page_of_plain_scripts_opens_from_disk_perfectly_well(tmp_path: Path) -> None:
    _project(tmp_path, {"app/index.html": PLAIN_PAGE, "app/tests/e2e.spec.js": AS_THE_RUN_WROTE_IT})

    assert _found(tmp_path) == []


def test_a_test_that_opens_the_served_address_is_left_alone(tmp_path: Path) -> None:
    served = AS_THE_RUN_WROTE_IT.replace("'file://' + process.cwd() + '/index.html'", "'/'")
    _project(tmp_path, {"app/index.html": MODULE_PAGE, "app/tests/e2e.spec.js": served})

    assert _found(tmp_path) == []


def test_a_unit_test_that_reads_a_file_is_not_a_browser_test(tmp_path: Path) -> None:
    unit = "import { test } from 'node:test';\nimport { pathToFileURL } from 'node:url';\ntest('x', () => { pathToFileURL('a'); });\n"
    _project(tmp_path, {"app/index.html": MODULE_PAGE, "app/tests/unit.test.js": unit})

    assert _found(tmp_path) == []


def test_an_inline_module_that_imports_nothing_runs_from_disk(tmp_path: Path) -> None:
    page = "<html><body><script type=\"module\">\ndocument.title = 'x';\n</script></body></html>\n"
    _project(tmp_path, {"app/index.html": page, "app/tests/e2e.spec.js": AS_THE_RUN_WROTE_IT})

    assert _found(tmp_path) == []
