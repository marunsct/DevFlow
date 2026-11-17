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


def test_the_finding_says_what_a_blank_page_cannot_do_and_uses_no_banned_word(tmp_path, monkeypatch):
    from app.acceptance import spec_dry_run, suite
    from app.stacks import contract, pack_named

    monkeypatch.setattr(spec_dry_run, "findings", lambda root: [])  # it runs the suite's own runner
    contract.write(tmp_path, pack_named("fullstack-node"), "marks", "Marks")
    (tmp_path / "marks" / "acceptance").mkdir(parents=True)
    (tmp_path / "marks" / "acceptance" / "page.spec.js").write_text(BEFORE)

    found = [f for f in suite.tests_that_cannot_pass(tmp_path, suite.AcceptanceResult(ran=False)) if "page.spec.js" in f]

    assert len(found) == 1 and "line 3" in found[0] and "`/`" in found[0] and "goto" in found[0]
    assert not BANNED.search(found[0].replace("[AC-4] filters", ""))
