"""A page test that counts every item of a list other tests also add to cannot hold on a shared service.

Measured on three full-stack runs: one test expected `getByRole('listitem')` to hold exactly 2 while every test adds
bookmarks to the one service the suite starts; another filtered by the tag "A" that five tests gave their records and
expected exactly 2. The check for shared lists read only API routes, so both were locked and charged to the product.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import suite
from app.stacks import contract, pack_named

WHOLE = """test('[AC-9] lists both', async ({ page, request }) => {
  await request.post('/api/bookmarks', { data: { title: 'Link One', url: 'https://one.test' } });
  await page.goto('/');
  const items = page.getByRole('listitem');
  await expect(items).toHaveCount(2);
});
test('[AC-1] saves', async ({ page }) => {
  await page.getByLabel('Title', { exact: true }).fill('Other');
});
"""
SHARED_TAG = """test('[AC-10] filters', async ({ page }) => {
  await page.getByLabel('Tag', { exact: true }).fill('A');
  await expect(page.getByRole('listitem').filter({ hasText: 'A' })).toHaveCount(2);
});
test('[AC-4] deletes while filtered', async ({ page }) => {
  await page.getByLabel('Tag', { exact: true }).fill('A');
});
"""
OWN = """test('[AC-10] filters', async ({ page }) => {
  const tag = `t-${Date.now()}`;
  await expect(page.getByRole('listitem').filter({ hasText: 'Only Mine 1' })).toHaveCount(1);
});
test('[AC-1] saves', async ({ page }) => {
  await page.getByLabel('Title', { exact: true }).fill('Other');
});
"""


def _root(tmp_path, spec, pack="fullstack-page-fastapi"):
    contract.write(tmp_path, pack_named(pack), "bookmarks", "Bookmarks")
    (tmp_path / "bookmarks" / "acceptance").mkdir(parents=True, exist_ok=True)
    (tmp_path / "bookmarks" / "acceptance" / "ui.spec.js").write_text(spec)
    return tmp_path


def _failed(name, message):
    return SimpleNamespace(ran=True, report=SimpleNamespace(found=True, tests=[
        SimpleNamespace(name=name, outcome="failed", message=message)]))


def test_a_count_of_the_whole_list_is_named(tmp_path):
    [found] = suite.page_tests_that_count_a_shared_list(_root(tmp_path, WHOLE))
    assert "line 5" in found and "toHaveCount(2)" in found


def test_a_count_narrowed_by_a_value_other_tests_use_is_named(tmp_path):
    [found] = suite.page_tests_that_count_a_shared_list(_root(tmp_path, SHARED_TAG))
    assert "'A'" in found


def test_a_count_narrowed_to_the_test_s_own_record_is_not(tmp_path):
    assert suite.page_tests_that_count_a_shared_list(_root(tmp_path, OWN)) == []


def test_a_page_with_its_own_store_is_not(tmp_path):
    assert suite.page_tests_that_count_a_shared_list(_root(tmp_path, WHOLE, "browser-javascript")) == []


def test_once_locked_only_more_than_expected_names_it(tmp_path, monkeypatch):
    root = _root(tmp_path, WHOLE)
    monkeypatch.setattr(suite, "is_locked", lambda _root: True)
    fewer = _failed("[AC-9] lists both", "Expected: 2\nReceived: 0\n")
    more = _failed("[AC-9] lists both", "Expected: 2\nReceived: 7\n")
    assert suite.page_tests_that_count_a_shared_list(root, fewer) == []
    assert len(suite.page_tests_that_count_a_shared_list(root, more)) == 1


def test_it_is_one_of_the_checks_a_locked_test_cannot_pass():
    import inspect
    assert "page_tests_that_count_a_shared_list(" in inspect.getsource(suite.tests_that_cannot_pass)


CLEARED = """test('[AC-4] narrows', async ({ page, request }) => {
  await clearBookmarks(request);
  await expect(page.getByRole('listitem')).toHaveCount(3);
});
"""
TYPED = """test('[AC-15] filters', async ({ page }) => {
  await page.getByLabel('Filter by tag', { exact: true }).fill('mine-only');
  await expect(page.getByRole('listitem')).toHaveCount(1);
  await page.getByLabel('Filter by tag', { exact: true }).fill('');
  await expect(page.getByRole('listitem')).toHaveCount(1);
});
test('[AC-1] saves', async ({ page }) => {
  await page.getByLabel('Tag', { exact: true }).fill('other');
});
"""


def test_a_list_emptied_first_may_be_counted(tmp_path):
    assert suite.page_tests_that_count_a_shared_list(_root(tmp_path, CLEARED)) == []


def test_a_list_narrowed_by_typing_a_value_of_its_own_is_not_named_until_the_filter_is_cleared(tmp_path):
    [found] = suite.page_tests_that_count_a_shared_list(_root(tmp_path, TYPED))
    assert "line 5" in found


def test_a_file_whose_hook_empties_the_list_may_count(tmp_path):
    spec = "test.beforeEach(async ({ request }) => { await resetStore(request); });\n" + WHOLE
    assert suite.page_tests_that_count_a_shared_list(_root(tmp_path, spec)) == []


def test_at_the_lock_the_shape_is_enough_though_other_tests_pass(tmp_path, monkeypatch):
    """Measured on the run it was built for: at the lock the starting page passed some tests and the counts met an
    empty list (`Received: 0`); waiting for more to come back named nothing, and the suite was locked again."""
    root = _root(tmp_path, WHOLE)
    monkeypatch.setattr(suite, "is_locked", lambda _root: False)
    result = SimpleNamespace(ran=True, report=SimpleNamespace(found=True, tests=[
        SimpleNamespace(name="[AC-9] lists both", outcome="failed", message="Expected: 2\nReceived: 0\n"),
        SimpleNamespace(name="[AC-1] saves", outcome="passed", message="")]))
    assert len(suite.page_tests_that_count_a_shared_list(root, result)) == 1


#: As a later run's suite wrote it: narrowed by a value of its own held in a name, directly and on a bound locator.
BY_A_NAME = """test('[AC-4] filters', async ({ page }) => {
  const workTag = `work-${Date.now()}`;
  const allWorkItems = page.getByRole('listitem').filter({ hasText: workTag });
  await expect(allWorkItems).toHaveCount(2);
  const filteredItems = page.getByRole('listitem');
  await expect(filteredItems.filter({ hasText: workTag })).toHaveCount(2);
});
test('[AC-1] saves', async ({ page }) => {
  await page.getByLabel('Title', { exact: true }).fill('Other');
});
"""


def test_a_list_narrowed_by_a_value_held_in_a_name_is_not_named(tmp_path):
    """Measured on the run after it shipped: six such counts were sent back at the review's limit, the writer could
    not see what to change, and the suite was locked with a false finding spent."""
    assert suite.page_tests_that_count_a_shared_list(_root(tmp_path, BY_A_NAME)) == []


# Measured on one run: "an invalid bookmark is refused" counted the whole list as 0 after other tests had saved theirs
# to the one service, could never pass, and a dispute reopened the suite after the build.
NONE_AT_ALL = """test('[AC-8][AC-17] invalid bookmarks are rejected', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Title', { exact: true }).fill('');
  await expect(page.getByRole('listitem')).toHaveCount(0);
});
test('[AC-1] saves', async ({ page }) => {
  await page.getByLabel('Title', { exact: true }).fill('Other');
});
"""
NONE_OF_MINE = NONE_AT_ALL.replace("page.getByRole('listitem'))", "page.getByRole('listitem').filter({ hasText: 'Refused 1' }))")


def test_no_record_at_all_on_a_shared_list_is_named(tmp_path):
    [found] = suite.page_tests_that_count_a_shared_list(_root(tmp_path, NONE_AT_ALL))
    assert "toHaveCount(0)" in found and "every item of the page's list" in found


def test_none_of_the_test_s_own_records_left_is_not(tmp_path):
    assert suite.page_tests_that_count_a_shared_list(_root(tmp_path, NONE_OF_MINE)) == []
