"""A browser suite is held to the same page checks with or without a stack pack, and finds records as the brief shows them.

Measured on one run with no pack: the brief said each record is an item of a list and gave a field its label. The
product drew plain containers and a placeholder, the locked suite found them by a CSS class and passed 27 of 27, and 5
of the benchmark's 8 hidden tests failed. Every check that would have noticed read its patterns from the pack.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.acceptance import suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
BRIEF = 'A text field labelled "Filter by tag".\nEach bookmark is an item of a list showing its title.\n'


def _a_suite(root: Path, text: str, name: str = "ui.spec.ts") -> None:
    suite_dir = root / "app" / "acceptance"
    suite_dir.mkdir(parents=True)
    (suite_dir / "run.json").write_text(json.dumps({"command": ["run"], "report": "r.xml"}))
    (suite_dir / name).write_text(text)
    (root / ".project-directory").write_text("app\n")


PLAYWRIGHT = "import { test } from '@playwright/test';\n"
BY_CLASS = PLAYWRIGHT + "await page.locator('.bookmark-item').first();\nawait page.locator('#filter-tag').fill('x');\n"
BY_ROLE = PLAYWRIGHT + "await page.getByRole('listitem');\nawait page.getByLabel('Filter by tag', { exact: true }).fill('x');\n"


def test_with_no_pack_a_browser_suite_gets_the_control_checks(tmp_path):
    _a_suite(tmp_path, BY_CLASS)

    assert any('"Filter by tag"' in p for p in suite.controls_never_found_by_name(tmp_path, BRIEF))
    assert suite.locators_nobody_sees(tmp_path)


def test_a_suite_finding_records_by_a_class_is_told_the_brief_s_kind(tmp_path):
    _a_suite(tmp_path, BY_CLASS)

    found = suite.records_never_found_as_the_brief_shows_them(tmp_path, BRIEF)

    assert len(found) == 1 and "item of a list" in found[0] and "listitem" in found[0]
    assert not BANNED.search(found[0])


def test_a_suite_finding_records_by_role_or_element_passes(tmp_path):
    for index, text in enumerate((BY_ROLE, PLAYWRIGHT + "await page.locator('ul > li');\n",
                                  'from playwright.sync_api import Page\npage.get_by_role("listitem")\n')):
        root = tmp_path / str(index)
        _a_suite(root, text)
        assert suite.records_never_found_as_the_brief_shows_them(root, BRIEF) == []


def test_a_table_row_is_asked_for_too(tmp_path):
    _a_suite(tmp_path, BY_CLASS)

    assert "row" in suite.records_never_found_as_the_brief_shows_them(tmp_path, "Each entry is a row of a table.")[0]


def test_a_suite_with_no_browser_is_not_asked(tmp_path):
    _a_suite(tmp_path, "def test_api(client):\n    assert client.get('/').status_code == 200\n", "test_api.py")

    assert suite.records_never_found_as_the_brief_shows_them(tmp_path, BRIEF) == []
    assert suite.controls_never_found_by_name(tmp_path, BRIEF) == []
    assert suite.locators_nobody_sees(tmp_path) == []


def test_a_brief_that_says_no_kind_asks_nothing(tmp_path):
    _a_suite(tmp_path, BY_CLASS)

    assert suite.records_never_found_as_the_brief_shows_them(tmp_path, "Show the bookmarks.") == []
