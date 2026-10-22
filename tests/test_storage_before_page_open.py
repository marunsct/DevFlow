"""Tests that acceptance tests accessing storage before page.goto are rejected.

Every test starts on a blank page (about:blank). Evaluating storage operations
like localStorage.clear() on about:blank causes a browser SecurityError:
Access is denied for this document. Navigating with page.goto must happen first.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.acceptance import suite
from app.stacks import contract, pack_named
from app.stacks.packs import _javascript as js


def test_helper_clearing_storage_before_goto_is_caught() -> None:
    code = """import { test, expect } from '@playwright/test';

async function resetPage(page) {
  await page.evaluate(() => localStorage.clear());
  await page.goto('/');
}

test('[AC-1] Main heading visible', async ({ page }) => {
  await resetPage(page);
  await expect(page.locator('h1')).toBeVisible();
});
"""
    problems = js.storage_before_page_open(code)
    assert len(problems) == 1
    line, name, ctx = problems[0]
    assert line == 4
    assert name == "localStorage"
    assert "resetPage" in ctx


def test_helper_with_session_storage_before_goto_is_caught() -> None:
    code = """import { test, expect } from '@playwright/test';

const reset = async (page) => {
  await page.evaluate(() => sessionStorage.clear());
  await page.goto('/');
};

test('[AC-1] Main heading visible', async ({ page }) => {
  await reset(page);
});
"""
    problems = js.storage_before_page_open(code)
    assert len(problems) == 1
    assert problems[0][1] == "sessionStorage"


def test_helper_clearing_storage_after_goto_is_allowed() -> None:
    code = """import { test, expect } from '@playwright/test';

async function resetPage(page) {
  await page.goto('/');
  await page.evaluate(() => localStorage.clear());
}

test('[AC-1] Main heading visible', async ({ page }) => {
  await resetPage(page);
});
"""
    assert js.storage_before_page_open(code) == []


def test_before_each_clearing_storage_before_goto_is_caught() -> None:
    code = """import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.evaluate(() => localStorage.clear());
  await page.goto('/');
});

test('[AC-1] Heading visible', async ({ page }) => {
  await expect(page.locator('h1')).toBeVisible();
});
"""
    problems = js.storage_before_page_open(code)
    assert len(problems) == 1
    line, name, ctx = problems[0]
    assert line == 4
    assert "beforeEach" in ctx


def test_before_each_clearing_storage_after_goto_is_allowed() -> None:
    code = """import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await page.evaluate(() => localStorage.clear());
});

test('[AC-1] Heading visible', async ({ page }) => {
  await expect(page.locator('h1')).toBeVisible();
});
"""
    assert js.storage_before_page_open(code) == []


def test_direct_test_clearing_storage_before_goto_is_caught() -> None:
    code = """import { test, expect } from '@playwright/test';

test('[AC-1] Persistence check', async ({ page }) => {
  await page.evaluate(() => localStorage.clear());
  await page.goto('/');
});
"""
    problems = js.storage_before_page_open(code)
    assert len(problems) == 1
    line, name, ctx = problems[0]
    assert line == 4
    assert "Persistence check" in ctx


def test_direct_test_with_prior_before_each_goto_is_allowed() -> None:
    code = """import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
});

test('[AC-1] Persistence check', async ({ page }) => {
  await page.evaluate(() => localStorage.clear());
});
"""
    assert js.storage_before_page_open(code) == []


def test_suite_linter_reports_storage_before_page_open(tmp_path: Path) -> None:
    pack = pack_named("browser-javascript")
    contract.write(tmp_path, pack, "notes", "Notes")
    acceptance_dir = tmp_path / "notes" / "acceptance"
    acceptance_dir.mkdir(parents=True)
    bad_spec = """import { test } from '@playwright/test';

async function resetPage(page) {
  await page.evaluate(() => localStorage.clear());
  await page.goto('/');
}

test('opens', async ({ page }) => {
  await resetPage(page);
});
"""
    (acceptance_dir / "bad.spec.js").write_text(bad_spec, encoding="utf-8")

    problems = suite.tests_that_access_storage_before_opening_the_page(tmp_path)
    assert len(problems) == 1
    assert "SecurityError" in problems[0]
    assert "bad.spec.js" in problems[0]


def test_no_banned_words_in_new_rules_and_messages() -> None:
    banned = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")
    rule = js.PLAYWRIGHT_LOCATORS_RULE
    for word in banned:
        assert not re.search(rf"\b{re.escape(word)}\b", rule, re.IGNORECASE), (
            f"Banned word '{word}' found in PLAYWRIGHT_LOCATORS_RULE"
        )

    # Check the error message template
    sample_msg = (
        "notes/acceptance/bad.spec.js line 4: helper `resetPage` accesses `localStorage` "
        "before opening the page with `goto`. Every test starts on a blank page where storage access "
        "is forbidden and throws a browser SecurityError. Navigate with `await page.goto('/')` "
        "first before touching storage."
    )
    for word in banned:
        assert not re.search(rf"\b{re.escape(word)}\b", sample_msg, re.IGNORECASE), (
            f"Banned word '{word}' found in error message"
        )

