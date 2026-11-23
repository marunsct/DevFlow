"""A page test that asserts an exact number of every record the page lists cannot pass on a service all tests share.

Measured on four full-stack runs: the suite starts one service for all its tests and never empties it, yet locked
page tests asserted that, after saving one bookmark through the form and deleting it, the page listed none at all
(`expect(await page.getByRole('listitem').count()).toBe(0)`), or none after a refused save. Other tests' bookmarks are
on the same page, so the number is never 0. The dispute found it only after the build, the suite could not be repaired
again, and the criteria shipped deferred. Only text is read here: no suite runs.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.acceptance import suite
from app.agents import suite_dispute
from app.stacks import contract, pack_named
from app.stacks.packs import _javascript as js

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CORPUS = Path(__file__).parent / "fixtures" / "locked_suites"
SAVES = """test('[AC-1] saves a bookmark from the page', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Title', { exact: true }).fill(`Saved ${Date.now()}`);
  await page.getByLabel('URL', { exact: true }).fill('https://one.test');
  await page.getByRole('button', { name: 'Save bookmark' }).click();
});
"""
WORKFLOW = "[AC-15] Full workflow: save, list, filter, delete from the page"
REFUSED = "[AC-17] refuses a bookmark whose address is not http(s)"
EMPTY_TITLE = "[AC-8] refuses a bookmark with an empty title"
EMPTY_TITLE_TEST = f"""
test('{EMPTY_TITLE}', async ({{ page }}) => {{
  await page.goto('/');
  await page.getByRole('button', {{ name: 'Save bookmark' }}).click();
  await expect(page.getByRole('listitem')).toHaveCount(0);
}});
"""
MEASURED = SAVES + f"""
test('{WORKFLOW}', async ({{ page }}) => {{
  const title = `Flow ${{Date.now()}}`;
  await page.goto('/');
  await page.getByLabel('Title', {{ exact: true }}).fill(title);
  await page.getByLabel('URL', {{ exact: true }}).fill('https://flow.test');
  await page.getByRole('button', {{ name: 'Save bookmark' }}).click();
  await page.getByRole('listitem').filter({{ hasText: title }}).getByRole('button', {{ name: 'Delete' }}).click();
  const afterDeleteCount = await page.getByRole('listitem').count();
  expect(afterDeleteCount).toBe(0);
}});

test('{REFUSED}', async ({{ page }}) => {{
  await page.goto('/');
  await page.getByLabel('Title', {{ exact: true }}).fill('Refused');
  await page.getByLabel('URL', {{ exact: true }}).fill('ftp://refused.test');
  await page.getByRole('button', {{ name: /save/i }}).click();
  await expect(page.locator('ul > li')).toHaveCount(0);
}});
""" + EMPTY_TITLE_TEST


def _workspace(tmp_path: Path, spec: str, pack: str = "fullstack-node", **others: str) -> Path:
    contract.write(tmp_path, pack_named(pack), "bookmarks", "Bookmarks")
    (tmp_path / "bookmarks" / "acceptance").mkdir(parents=True)
    (tmp_path / "bookmarks" / "acceptance" / "ui.spec.js").write_text(spec, encoding="utf-8")
    for name, text in others.items():
        (tmp_path / "bookmarks" / "acceptance" / f"{name}.spec.js").write_text(text, encoding="utf-8")
    return tmp_path


def _counting_all(found: list[str]) -> list[str]:
    return [item for item in found if "filter the list by a marker only they carry" in item]


@pytest.mark.parametrize("pack", ["fullstack-node", "fullstack-page-fastapi"])
def test_the_measured_counts_go_back_before_the_lock_naming_line_assertion_and_fix(tmp_path, pack):
    root = _workspace(tmp_path, MEASURED, pack)

    found = _counting_all(suite.tests_that_cannot_pass(root, suite.AcceptanceResult(ran=False)))

    assert [item.split(":", 1)[0] for item in found] == [
        "`bookmarks/acceptance/ui.spec.js` line 16", "`bookmarks/acceptance/ui.spec.js` line 24"]
    assert f"`{WORKFLOW}`" in found[0] and "`expect(afterDeleteCount).toBe(0)`" in found[0]
    assert "`expect(page.locator('ul > li')).toHaveCount(0)`" in found[1]
    assert all("compare with a count taken before the test's own action" in item for item in found)


def test_a_line_the_page_count_check_already_names_goes_back_once(tmp_path):
    root = _workspace(tmp_path, MEASURED)

    found = suite.tests_that_cannot_pass(root, suite.AcceptanceResult(ran=False))

    assert len([item for item in found if item.startswith("`bookmarks/acceptance/ui.spec.js` line 30")]) == 1


def test_records_made_by_another_file_are_enough(tmp_path):
    root = _workspace(tmp_path, EMPTY_TITLE_TEST, saves=SAVES)
    [found] = suite.counts_of_every_record_on_a_shared_page(root)
    assert found.startswith("`bookmarks/acceptance/ui.spec.js` line 5:")


def _one(lines: str, title: str = "[AC-9] lists") -> str:
    return SAVES + f"""
test('{title}', async ({{ page, request }}) => {{
  const marker = `m-${{Date.now()}}`;
  await page.goto('/');
{lines}
}});
"""


def test_the_same_test_counting_the_whole_list_goes_back():
    assert js.counts_of_every_listed_record(_one("  await expect(page.getByRole('listitem')).toHaveCount(2);")) == [
        (11, "[AC-9] lists", "expect(page.getByRole('listitem')).toHaveCount(2)", 2)]


@pytest.mark.parametrize("lines", [
    # Narrowed to the test's own records by a marker.
    "  await expect(page.getByRole('listitem').filter({ hasText: marker })).toHaveCount(0);",
    "  const mine = page.getByRole('listitem').filter({ hasText: marker });\n  expect(await mine.count()).toBe(1);",
    "  await expect(page.getByRole('listitem', { name: marker })).toHaveCount(1);",
    "  await expect(page.getByRole('listitem').getByText(marker)).toHaveCount(1);",
    # A number worked out from a count taken before the test's own action.
    "  const before = await page.getByRole('listitem').count();\n"
    "  await expect(page.getByRole('listitem')).toHaveCount(before + 1);",
    # A filter typed with the test's own value, and left so.
    "  await page.getByLabel('Filter by tag').fill(marker);\n  await expect(page.getByRole('listitem')).toHaveCount(2);",
    # A control named by the test's own value acted on first: a tag of its own, say.
    "  await page.getByRole('button', { name: marker }).click();\n"
    "  await expect(page.getByRole('listitem')).toHaveCount(2);",
    # A page address with a query.
    "  await page.goto(`/?tag=${marker}`);\n  await expect(page.getByRole('listitem')).toHaveCount(2);",
    # The list emptied first, in a loop or by a call that says so.
    "  for (const b of await (await request.get('/api/bookmarks')).json()) await request.delete(`/api/bookmarks/${b.id}`);\n"
    "  await expect(page.getByRole('listitem')).toHaveCount(0);",
    "  await resetStore(request);\n  await expect(page.getByRole('listitem')).toHaveCount(0);",
    # A list shown in parts of a set size: a full part holds whatever the service holds.
    "  await expect(page.getByRole('listitem')).toHaveCount(20); // per page\n  const perPage = 20;",
], ids=["filtered", "filtered-and-bound", "named", "text-inside", "relative", "own-filter", "own-control", "query",
        "emptied-in-a-loop", "emptied-by-a-call", "a-part-of-a-set-size"])
def test_a_count_of_the_test_s_own_records_or_of_a_list_it_emptied_is_left_alone(lines):
    assert js.counts_of_every_listed_record(_one(lines)) == []


@pytest.mark.parametrize("spec", [
    # Hooks that may empty the store before each test.
    "test.beforeEach(async ({ request }) => { await request.delete('/api/bookmarks'); });\n" + MEASURED,
    # The page's service answered by the test itself.
    MEASURED.replace("await page.goto('/');", "await page.route('**/api/bookmarks', r => r.fulfill({ json: [] }));\n"
                     "  await page.goto('/');", 1),
    # Each test signed in as a user of its own.
    "test.use({ storageState: 'user.json' });\n" + MEASURED,
    # No other test makes a record.
    EMPTY_TITLE_TEST,
], ids=["emptied-by-a-hook", "answered-by-the-test", "signed-in", "nothing-else-made"])
def test_a_file_whose_list_may_hold_only_its_own_records_is_left_alone(spec):
    assert js.counts_of_every_listed_record(spec) == []


def test_a_suite_whose_tests_each_have_their_own_store_is_not_read(tmp_path):
    root = _workspace(tmp_path, MEASURED, "browser-javascript")
    assert suite.counts_of_every_record_on_a_shared_page(root) == []


def test_the_finding_speaks_of_the_test_in_plain_words(tmp_path):
    finding = suite.counts_of_every_record_on_a_shared_page(_workspace(tmp_path, MEASURED))[0]
    assert "about the test, not the product" in finding
    assert not BANNED.search(finding)


def test_the_stored_suites_that_passed_their_hidden_tests_give_no_finding():
    paths = sorted(CORPUS.rglob("*.spec.*"))
    found = {str(path.relative_to(CORPUS)): hits for path in paths
             if (hits := js.counts_of_every_listed_record(path.read_text(encoding="utf-8", errors="replace")))}
    assert len(paths) >= 100
    assert found == {}


def test_the_dispute_is_told_what_the_code_shows(tmp_path):
    root = _workspace(tmp_path, MEASURED)
    shown = suite.what_the_code_shows_of(root, [WORKFLOW, "[AC-1] saves a bookmark from the page"])

    text = suite_dispute.build_dispute_request(
        [(WORKFLOW, "AC-15: x", "Expected: 0 Received: 4")], "code", "brief", shared_service=True,
        found_in_the_code=[finding for _, finding in shown],
    )["messages"][0]["content"]

    assert [name for name, _ in shown] == [WORKFLOW]
    assert "filter the list by a marker only they carry" in text
