"""A page test that fetches a relative address before opening the page cannot pass: a blank page has no origin.

Measured on one run: four tests made their records with `page.evaluate(() => fetch('/api/...'))` before
`page.goto('/')`; a fixer spent fifteen minutes on a right product and changed nothing. 3 stored suites did the same.
"""
import re

from app.stacks.packs import _javascript as js

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
BEFORE = """test('[AC-4] filters', async ({ page }) => {
  await page.evaluate(async () => {
    await fetch('/api/bookmarks', { method: 'POST', body: '{}' });
  });
  await page.goto('/');
});
"""
AFTER = BEFORE.replace("  await page.goto('/');\n", "").replace("async ({ page }) => {\n", "async ({ page }) => {\n  await page.goto('/');\n", 1)
ABSOLUTE = BEFORE.replace("fetch('/api", "fetch('http://localhost:3000/api")


def test_a_relative_fetch_before_goto_is_found():
    found = js.storage_before_page_open(BEFORE)
    assert found and found[0][1].startswith("fetch(") and "[AC-4] filters" in found[0][2]


def test_after_goto_or_to_a_full_address_it_is_not():
    assert js.storage_before_page_open(AFTER) == []
    assert js.storage_before_page_open(ABSOLUTE) == []


def test_storage_is_still_found():
    assert js.storage_before_page_open(BEFORE.replace("await fetch('/api/bookmarks', { method: 'POST', body: '{}' });",
                                                      "localStorage.clear();"))[0][1] == "localStorage"


def test_the_finding_says_what_a_blank_page_cannot_do_and_uses_no_banned_word():
    import inspect

    from app.acceptance import suite

    source = inspect.getsource(suite.tests_that_access_storage_before_opening_the_page)
    assert "an address starting with `/` reaches nothing" in source
    assert not BANNED.search(source.split('"""')[-1])
