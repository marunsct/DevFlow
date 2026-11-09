"""A browser test runner that is installed and that no test uses is no browser test.

One completed run listed `@playwright/test` in its devDependencies, wrote no spec
that imports it, and shipped on four unit tests of its state module. The check
for a UI with no browser test was satisfied by the manifest line alone.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.analysis.integration_checks import _missing_playwright_for_ui, _source_files, summarise_integration

SPEC = "import { test, expect } from '@playwright/test';\ntest('adds', async ({ page }) => { await page.goto('/'); });\n"


def _product(tmp_path: Path, spec: str | None) -> Path:
    app = tmp_path / "app"
    (app / "tests").mkdir(parents=True)
    (app / "package.json").write_text(json.dumps({
        "type": "module", "scripts": {"test": "jest"},
        "devDependencies": {"jest": "^29.7.0", "@playwright/test": "^1.45.0"},
    }), encoding="utf-8")
    (app / "index.html").write_text('<html><body><script type="module" src="app.js"></script></body></html>', encoding="utf-8")
    (app / "app.js").write_text("export const add = (a) => a;\n", encoding="utf-8")
    (app / "tests" / "state.test.js").write_text("import { add } from '../app.js';\ntest('x', () => expect(add(1)).toBe(1));\n", encoding="utf-8")
    if spec is not None:
        (app / "tests" / "ui.spec.js").write_text(spec, encoding="utf-8")
    return tmp_path


def test_installed_and_unused_is_reported(tmp_path: Path) -> None:
    root = _product(tmp_path, None)

    (problem,) = _missing_playwright_for_ui(_source_files(root), root, None)

    assert "no test imports it" in problem


def test_it_blocks(tmp_path: Path) -> None:
    root = _product(tmp_path, None)

    assert "no test imports it" in summarise_integration(root).split("DOES NOT WORK")[1].split("untidy")[0]


def test_a_spec_that_imports_it_answers_it(tmp_path: Path) -> None:
    root = _product(tmp_path, SPEC)

    assert _missing_playwright_for_ui(_source_files(root), root, None) == []


def test_a_page_test_in_python_answers_it(tmp_path: Path) -> None:
    """Measured on one run: every page test was Python Playwright, and this asked for a JavaScript one."""
    root = _product(tmp_path, None)
    (root / "app" / "tests" / "test_ui.py").write_text(
        "from playwright.sync_api import Page, expect\n\n\ndef test_saves(page: Page):\n    page.goto('/')\n",
        encoding="utf-8")

    assert _missing_playwright_for_ui(_source_files(root), root, None) == []


def test_a_python_file_that_only_mentions_it_does_not(tmp_path: Path) -> None:
    root = _product(tmp_path, None)
    (root / "app" / "tests" / "test_notes.py").write_text("# playwright is installed for later\nx = 1\n", encoding="utf-8")

    assert len(_missing_playwright_for_ui(_source_files(root), root, None)) == 1
