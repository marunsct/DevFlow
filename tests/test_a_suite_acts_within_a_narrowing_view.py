"""A browser suite takes an action while a narrowing view the brief names is on.

Measured on two runs: the brief named filters "All", "Active" and "Completed"; the suite tested each filter and the
action that changes an item's state apart; the product left a completed item in the Active view and a hidden test of
exactly that failed. A prompt rule asking for the test did not make the writers write it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.acceptance import suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
BRIEF = '- Each item has a box labelled "Done".\n- Three controls named "All", "Active" and "Completed" filter the list.\n'
HEAD = "import { test, expect } from '@playwright/test';\n"

APART = HEAD + """test('filters', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Done').check();
  const activeBtn = page.getByRole('button', { name: 'Active', exact: true });
  await activeBtn.click();
  await expect(page.getByRole('listitem')).toHaveCount(2);
  const completedBtn = page.getByRole('button', { name: 'Completed', exact: true });
  await completedBtn.click();
  await expect(page.getByRole('listitem')).toHaveCount(1);
});
"""
WITHIN = HEAD + """test('completing an item under Active removes it', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Active', exact: true }).click();
  await page.getByRole('listitem').first().getByLabel('Done').check();
  await expect(page.getByRole('listitem')).toHaveCount(1);
});
"""


def _suite(root: Path, text: str) -> Path:
    folder = root / "app" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(json.dumps({"command": ["run"], "report": "r.xml"}))
    (folder / "ui.spec.js").write_text(text)
    (root / ".project-directory").write_text("app\n")
    return root


def test_a_suite_testing_each_view_and_the_action_apart_is_named(tmp_path):
    [found] = suite.views_never_acted_within(_suite(tmp_path, APART), BRIEF)
    assert '"Active"' in found and '"All"' not in found
    assert not BANNED.search(found)


def test_a_suite_that_acts_within_a_narrowing_view_is_left_alone(tmp_path):
    assert suite.views_never_acted_within(_suite(tmp_path, APART + WITHIN.replace(HEAD, "")), BRIEF) == []


def test_a_brief_with_no_narrowing_view_or_a_suite_with_no_browser_says_nothing(tmp_path):
    root = _suite(tmp_path, APART)
    assert suite.views_never_acted_within(root, "- A list of items, each with a box labelled \"Done\".\n") == []
    (root / "app" / "acceptance" / "ui.spec.js").write_text("def test_x():\n    assert True\n")
    assert suite.views_never_acted_within(root, BRIEF) == []
