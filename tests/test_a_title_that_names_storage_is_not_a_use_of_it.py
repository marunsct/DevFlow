"""A test whose title names the storage it checks does not use that storage before opening the page.

Measured on one run: "[AC-9] Checking the Done checkbox updates localStorage completed flag" opened the page on its
first line and read storage only after. The check read the title as an early use, called the test one that can never
pass, the repair of a correct suite made it worse, the criterion was deferred, and its hidden test failed.
"""
from __future__ import annotations

from app.stacks.packs import _javascript as js

RIGHT = """import { test, expect } from '@playwright/test';

test('[AC-9] Checking the Done checkbox updates localStorage completed flag', async ({ page }) => {
  await page.goto('/');
  const tasks = await page.evaluate(() => JSON.parse(localStorage.getItem('todo_tasks') || '[]'));
  expect(tasks).toEqual([]);
});
"""

EARLY = """import { test, expect } from '@playwright/test';

test('[AC-9] keeps the list', async ({ page }) => {
  await page.evaluate(() => localStorage.clear());
  await page.goto('/');
});
"""


def test_a_title_naming_storage_is_not_read_as_a_use_before_the_page_opens():
    assert js.storage_before_page_open(RIGHT) == []


def test_storage_used_before_the_page_opens_is_still_found():
    [(line, name, context)] = js.storage_before_page_open(EARLY)
    assert name == "localStorage" and line == 4 and "keeps the list" in context


def test_a_title_naming_storage_with_a_real_early_use_is_still_found():
    both = EARLY.replace("keeps the list", "keeps the list in localStorage")
    [(line, name, _)] = js.storage_before_page_open(both)
    assert line == 4
