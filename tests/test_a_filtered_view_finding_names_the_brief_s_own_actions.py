"""The filtered-view finding asks for an action the brief offers, never one it does not.

Measured over 23 runs: on briefs offering only adding and removing records, the finding asked for a test that "changes
an item"; writers left it open for three rounds or more in 6 runs, and one invented an edit the brief never had.
"""
import re

from app.acceptance import suite

BOOKMARKS = ('# Bookmarks\n- Save a bookmark with a title, a URL and an optional tag\n- Delete a bookmark\n'
             '- A text field labelled "Filter by tag" shows only the bookmarks with exactly that tag\n')
TODO_LIKE = ('# List\n- Add an item\n- Mark an item complete\n- Edit an item\'s title\n'
             '- Filter buttons "All", "Active" and "Completed"\n')
NOT_ACTED = """import { test, expect } from '@playwright/test';
test('[AC-4] filter', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Filter by tag', { exact: true }).fill('work');
  await expect(page.getByRole('listitem')).toHaveCount(1);
});
"""
BANNED = re.compile(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _finding(tmp_path, monkeypatch, brief):
    path = tmp_path / "page.spec.js"
    path.write_text(NOT_ACTED.replace("Filter by tag", "Active") if "Active" in brief else NOT_ACTED)
    monkeypatch.setattr(suite, "suite_files", lambda root: [path])
    found = suite.views_never_acted_within(tmp_path, brief)
    assert len(found) == 1
    return found[0]


def test_a_brief_that_only_removes_is_asked_for_a_removal(tmp_path, monkeypatch):
    text = _finding(tmp_path, monkeypatch, BOOKMARKS)
    assert "removes" in text and "changes an item" not in text and "edits" not in text and "marks" not in text


def test_a_brief_with_marking_and_editing_names_both(tmp_path, monkeypatch):
    text = _finding(tmp_path, monkeypatch, TODO_LIKE)
    assert "marks" in text and "edits" in text and "removes" not in text


def test_a_brief_naming_no_item_action_gets_a_neutral_phrase():
    assert suite._an_action_the_brief_offers("# Notes\n- Filter by tag\n") == "takes an action the brief offers on"


def test_the_finding_uses_none_of_the_banned_words(tmp_path, monkeypatch):
    for brief in (BOOKMARKS,):
        assert not BANNED.search(_finding(tmp_path, monkeypatch, brief))
    assert not BANNED.search(suite._an_action_the_brief_offers(TODO_LIKE))
