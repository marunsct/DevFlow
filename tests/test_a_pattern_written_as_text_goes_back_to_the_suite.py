"""A page locator given a pattern as plain text goes back to the suite.

`filter({ hasText: '^B$' })` asks for the characters `^B$`: a string is matched as text, only a
`/^B$/` literal is a pattern. Measured on one run: a filtering test waited for a checkbox inside an
item no page shows, fixers spent an hour on a product that filtered, and `expect(item).not.toBeVisible()`
on the same locator passed whatever the page drew.
"""
from app.acceptance import suite
from app.stacks.packs import _javascript as js
from app.stacks.packs import browser_javascript

SUITE = """
test('filters', async ({ page }) => {
  const liB = page.getByRole('listitem').filter({ hasText: '^B$' });
  const anywhere = page.getByText("Done$");
  const right = page.getByRole('listitem').filter({ hasText: /^B$/ });
  const plain = page.getByRole('listitem').filter({ hasText: 'Buy milk' });
  const price = page.getByText('Costs $5');
  // a comment saying hasText: '^B$' is not code
});
"""


def test_the_lines_with_an_anchor_in_a_text_match_are_found():
    assert js.locators_matching_a_pattern_as_text(SUITE) == [3, 4]


def test_every_pack_that_reads_locators_reads_this_too():
    assert browser_javascript.PACK.locators_matching_a_pattern_as_text is js.locators_matching_a_pattern_as_text


def test_the_suite_is_told_no_product_can_satisfy_it(tmp_path, monkeypatch):
    path = tmp_path / "acceptance" / "crud.spec.js"
    path.parent.mkdir()
    path.write_text(SUITE)
    monkeypatch.setattr(suite, "suite_files", lambda root: [path])
    monkeypatch.setattr(suite.contract, "the_pack", lambda root: (browser_javascript.PACK, None))

    found = suite.locators_matching_a_pattern_as_text(tmp_path)

    assert len(found) == 1 and "line(s) 3, 4" in found[0] and "/^B$/" in found[0]
