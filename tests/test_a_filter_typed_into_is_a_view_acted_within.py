"""A view narrowed by typing into a field counts, like one chosen by a control.

Measured on one run: the brief's view is a text field labelled "Filter by tag"; the suite filled it, deleted a
record while it was on and checked the view, and the check - which knew only views chosen by pressing a control -
said no test acted within the view, sending the locked suite back to its writers.
"""
from app.acceptance import suite

BRIEF = '- A text field labelled "Filter by tag" shows only the bookmarks with exactly that tag; when it is empty, all are shown\n'
ACTED = """import { test, expect } from '@playwright/test';
test('[AC-4] deleting while filtered', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Filter by tag', { exact: true }).fill('work');
  await page.getByRole('listitem').filter({ hasText: 'Docs' }).getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByRole('listitem')).toHaveCount(1);
});
"""
NOT_ACTED = """import { test, expect } from '@playwright/test';
test('[AC-4] filter', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Filter by tag', { exact: true }).fill('work');
  await expect(page.getByRole('listitem')).toHaveCount(1);
});
test('[AC-3] delete', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByRole('listitem')).toHaveCount(0);
});
"""


def _with(tmp_path, monkeypatch, text):
    path = tmp_path / "page.spec.js"
    path.write_text(text)
    monkeypatch.setattr(suite, "suite_files", lambda root: [path])
    return tmp_path


def test_an_action_after_typing_the_filter_is_within_the_view(tmp_path, monkeypatch):
    assert suite.views_never_acted_within(_with(tmp_path, monkeypatch, ACTED), BRIEF) == []


def test_the_view_and_the_action_apart_are_still_found(tmp_path, monkeypatch):
    assert suite.views_never_acted_within(_with(tmp_path, monkeypatch, NOT_ACTED), BRIEF)
