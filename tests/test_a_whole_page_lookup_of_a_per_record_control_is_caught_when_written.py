"""A test that asks the whole page for a control the brief gives each record goes back when the suite is written.

Measured on one run: `[AC-9]` looked for "Delete" across the whole page while the brief gives every bookmark its
own; it only failed with "resolved to 3 elements" once the product drew three bookmarks, after a whole fix round.
Read from the test's text, it is caught before any product exists.
"""
from app.acceptance import suite
from app.stacks.packs import _javascript as js
from app.stacks.packs import browser_javascript

SUITE = """
test('[AC-9] a saved bookmark can be deleted', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Delete' }).click();
  const row = page.getByRole('listitem').filter({ hasText: 'Docs' });
  await row.getByRole('button', { name: 'Delete' }).click();
  await page.getByRole('button', { name: 'Save bookmark' }).click();
});
"""


def test_the_whole_page_lookup_of_a_per_record_name_is_found():
    assert js.whole_page_lookups(SUITE, ["Delete"]) == [4]


def test_a_control_the_page_has_once_is_left_alone():
    assert js.whole_page_lookups(SUITE, []) == []


def test_the_suite_check_reads_the_per_record_names_from_the_criteria(tmp_path, monkeypatch):
    from types import SimpleNamespace

    path = tmp_path / "acceptance" / "page.spec.js"
    path.parent.mkdir()
    path.write_text(SUITE)
    monkeypatch.setattr(suite, "suite_files", lambda root: [path])
    monkeypatch.setattr(suite.contract, "the_pack", lambda root: (browser_javascript.PACK, None))
    monkeypatch.setattr(suite, "criteria", lambda root: [SimpleNamespace(
        id="AC-9", text='Each bookmark is an item of a list showing its title. Each has a button named "Delete".')])

    found = suite.whole_page_lookups_of_a_per_record_control(tmp_path)

    assert len(found) == 1 and "line(s) 4" in found[0] and '"Delete"' in found[0]
