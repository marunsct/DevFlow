"""A value a test makes while sending it to the product, and reads back from its answer, was given to the product.

Measured on one run: `const bm = await (await request.post('/api/bookmarks', { data: { title: `x-${Date.now()}` } })).json()`
then `hasText: bm.title` was read as a value the test made and never gave; the locked suite went back to its writers
four times for it, over an hour.
"""
from app.stacks.packs import _javascript as js

GIVEN = """
test('[AC-4] deleting while filtered', async ({ page, request }) => {
  const bmDeleteMe = await (await request.post('/api/bookmarks', { data: { title: `delete-${Date.now()}`, url: 'https://d.com' } })).json();
  await page.goto('/');
  await expect(page.getByRole('listitem').filter({ hasText: bmDeleteMe.title })).toBeVisible();
});
"""
NEVER_GIVEN = """
test('[AC-1] add', async ({ page }) => {
  const title = `note-${Date.now()}`;
  await page.goto('/');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('listitem').filter({ hasText: title })).toBeVisible();
});
"""


def test_a_value_sent_in_its_own_making_is_given():
    assert js.expects_what_it_never_gave(GIVEN) == []


def test_a_value_never_given_is_still_found():
    assert [value for _, _, value in js.expects_what_it_never_gave(NEVER_GIVEN)] == ["title"]


def test_a_text_locator_with_regex_escapes_is_a_pattern_given_as_text():
    """Measured on one run: `filter({ hasText: 'Lifecycle task \\\\(edited\\\\)' })` - backslashes meant for a regular
    expression, in a string, so Playwright looked for the backslashes - failed every round until a dispute named it."""
    spec = ("test('[AC-13] lifecycle', async ({ page }) => {\n"
            "  await expect(page.getByRole('listitem').filter({ hasText: 'Lifecycle task \\\\(edited\\\\)' })).toBeVisible();\n"
            "  await expect(page.getByText('Saved (2)')).toBeVisible();\n"
            "});\n")
    assert js.locators_matching_a_pattern_as_text(spec) == [2]
