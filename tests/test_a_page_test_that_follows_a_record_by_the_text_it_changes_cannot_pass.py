"""A page test that held a record by one text, edited it and sought the new text inside, cannot pass.

Measured on one run: three locked edit tests held `filter({ hasText: 'Old title' })`, typed 'New title' and looked
for it inside; a locator is read again on each use, so after a right edit it finds nothing, and fixers spent nine fix
stages on a right product.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from app.acceptance import junit, suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SPEC = """import { test, expect } from '@playwright/test';
test('[AC-3] edits a title', async ({ page }) => {
  const item = page.getByRole('listitem').filter({ hasText: 'Old title' });
  await item.getByRole('textbox', { name: 'Edit title' }).fill('New title');
  await expect(item.getByText('New title')).toBeVisible();
});
test('[AC-4] adds a description', async ({ page }) => {
  const item = page.getByRole('listitem').filter({ hasText: 'Keep me' });
  await expect(item.getByText('Elsewhere')).toBeVisible();
});
"""
STALE = ("Error: expect(locator).toBeVisible() failed\\n Locator: getByRole('listitem').filter({ hasText: 'Old title' })"
         ".getByText('New title')\\n Expected: visible\\n Error: element(s) not found")
OTHER = ("Error: expect(locator).toBeVisible() failed\\n Locator: getByRole('listitem').filter({ hasText: 'Keep me' })"
         ".getByText('Elsewhere')\\n Expected: visible\\n Error: element(s) not found")


def _a_suite(root: Path) -> None:
    suite_dir = root / "app" / "acceptance"
    suite_dir.mkdir(parents=True)
    (suite_dir / "run.json").write_text(json.dumps({"command": ["run"], "report": "r.xml"}))
    (suite_dir / "items.spec.js").write_text(SPEC)
    (root / ".project-directory").write_text("app\n")


def _result(*tests):
    return SimpleNamespace(report=SimpleNamespace(tests=list(tests)), problem="", ran=True)


def test_the_stale_filter_is_found_and_a_text_it_never_typed_is_not(tmp_path):
    _a_suite(tmp_path)
    found = suite.tests_that_follow_a_record_by_the_text_they_change(tmp_path, _result(
        junit.TestResult(name="items.spec.js › [AC-3] edits a title", outcome="failed", message=STALE.replace("\\\\n", "\n")),
        junit.TestResult(name="items.spec.js › [AC-4] adds a description", outcome="failed", message=OTHER.replace("\\\\n", "\n")),
    ))
    assert len(found) == 1 and "[AC-3] edits a title" in found[0] and "'Old title'" in found[0]
    assert not BANNED.search(found[0].split("`")[0] + found[0].split("`")[-1])


def test_a_passing_test_is_never_named(tmp_path):
    _a_suite(tmp_path)
    assert suite.tests_that_follow_a_record_by_the_text_they_change(tmp_path, _result(
        junit.TestResult(name="items.spec.js › [AC-3] edits a title", outcome="passed"))) == []


def test_it_is_one_of_the_cannot_pass_checks():
    import inspect
    assert '"tests_that_follow_a_record_by_the_text_they_change"' in inspect.getsource(suite.tests_that_cannot_pass)
