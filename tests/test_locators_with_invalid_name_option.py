"""Tests that acceptance tests calling locator(selector, { name: ... }) are caught.

In Playwright, locator(selector, options) only accepts has, hasNot, hasText, hasNotText.
Passing { name: ... } is silently ignored, causing the locator to match every element
matching the selector rather than filtering by accessible name.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.acceptance import suite
from app.stacks import contract, pack_named
from app.stacks.packs import _javascript as js


def test_locator_with_name_option_is_caught(tmp_path: Path) -> None:
    pack = pack_named("browser-javascript")
    contract.write(tmp_path, pack, "notes", "Notes")
    suite_dir = tmp_path / "notes" / "acceptance"
    suite_dir.mkdir(parents=True)

    spec = """import { test, expect } from '@playwright/test';

test('[AC-1] control check', async ({ page }) => {
  const item = page.getByRole('listitem');
  await expect(item.locator('span', { name: 'Target', exact: true })).toHaveCount(1);
});
"""
    (suite_dir / "edit.spec.js").write_text(spec, encoding="utf-8")

    problems = suite.locators_with_invalid_name_option(tmp_path)
    assert len(problems) == 1
    assert "edit.spec.js" in problems[0]
    assert "does not accept a name option" in problems[0]


def test_valid_locators_are_not_flagged(tmp_path: Path) -> None:
    pack = pack_named("browser-javascript")
    contract.write(tmp_path, pack, "notes", "Notes")
    suite_dir = tmp_path / "notes" / "acceptance"
    suite_dir.mkdir(parents=True)

    spec = """import { test, expect } from '@playwright/test';

test('[AC-1] control check', async ({ page }) => {
  const item = page.getByRole('listitem');
  await expect(item.getByRole('link', { name: 'Target', exact: true })).toHaveCount(1);
  await expect(item.locator('span', { hasText: 'Target' })).toHaveCount(1);
});
"""
    (suite_dir / "valid.spec.js").write_text(spec, encoding="utf-8")

    problems = suite.locators_with_invalid_name_option(tmp_path)
    assert len(problems) == 0


def test_no_banned_words_in_rule_and_error_message() -> None:
    banned = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")
    rule = js.PLAYWRIGHT_LOCATORS_RULE
    for word in banned:
        assert not re.search(rf"\b{re.escape(word)}\b", rule, re.IGNORECASE), (
            f"Banned word '{word}' found in PLAYWRIGHT_LOCATORS_RULE"
        )

    sample_msg = (
        "notes/acceptance/edit.spec.js line(s) 5 (`item.locator('span', { name: 'Target' })`) calls "
        "`locator(..., { name: ... })`. `locator()` does not accept a name option; "
        "use `getByRole('role', { name: '...' })` or `locator('...', { hasText: '...' })` instead."
    )
    for word in banned:
        assert not re.search(rf"\b{re.escape(word)}\b", sample_msg, re.IGNORECASE), (
            f"Banned word '{word}' found in error message"
        )

