"""A page test that narrows a locator by a text two records it made hold, then needs one element from it, cannot pass.

Measured on one run: a locked test made bookmarks titled `ac9-link-${t}` and `ac9-link-${t}-no-tag`, found "its" item
by `filter({ hasText: `ac9-link-${t}` })` and asserted the tag and the Delete control inside it. A string `hasText` is
matched ignoring case and as part of the text, so the locator found both items and the runner refused every use
("strict mode violation"). Two attempts of fixes went to a right page; the suite review, the cannot-pass checks and the
dispute missed it, and the repair the dispute asked for changed one line and left the locator as it was.
Only text is read, and the runner's reports are made up: no suite runs.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.acceptance import junit, suite
from app.agents import suite_dispute
from app.stacks import contract, pack_named
from app.stacks.packs import _javascript as js

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CORPUS = Path(__file__).parent / "fixtures" / "locked_suites"
TITLE = "[AC-9] Bookmark items display title as link to URL, tag, and Delete button"
HEAD = """import { test, expect } from '@playwright/test';

function tag() {
  return `ac7-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function createBookmark(request, opts) {
  const { title, url, tag: t } = opts;
  const res = await request.post('/api/bookmarks', {
    data: { title, url, tag: t ?? '' },
  });
  expect(res.status()).toBe(201);
  return await res.json();
}

"""
#: The locked test as the run had it, shortened.
AS_LOCKED = HEAD + """test('""" + TITLE + """', async ({
  page,
  request,
}) => {
  const t = tag();
  const bm1 = await createBookmark(request, {
    title: `ac9-link-${t}`,
    url: 'https://example.com/first',
    tag: t,
  });
  const bm2 = await createBookmark(request, {
    title: `ac9-link-${t}-no-tag`,
    url: 'https://example.com/second',
  });
  await page.goto('/');
  const item1 = page.getByRole('listitem').filter({ hasText: `ac9-link-${t}` });
  await expect(item1.getByText(bm1.tag)).toBeVisible();
  await expect(
    item1.getByRole('button', { name: 'Delete', exact: true }),
  ).toBeAttached();
  const item2 = page.getByRole('listitem').filter({ hasText: `ac9-link-${t}-no-tag` });
  await expect(
    item2.getByRole('button', { name: 'Delete', exact: true }),
  ).toBeAttached();
});
"""
#: As the dispute's repair left it: one line changed, the locator kept.
AS_REPAIRED = AS_LOCKED.replace("await expect(item1.getByText(bm1.tag)).toBeVisible();",
                                "await expect(item1).toContainText(bm1.tag);")
#: The line the locator is narrowed on.
LINE = 31


def _workspace(tmp_path: Path, spec: str) -> Path:
    contract.write(tmp_path, pack_named("fullstack-node"), "bookmarks", "Bookmarks")
    (tmp_path / "bookmarks" / "acceptance").mkdir(parents=True)
    (tmp_path / "bookmarks" / "acceptance" / "ui-validation.spec.js").write_text(spec, encoding="utf-8")
    return tmp_path


def _failed(message: str = "Error: strict mode violation", name: str = TITLE) -> suite.AcceptanceResult:
    report = junit.Report(tests=[junit.TestResult(name=name, outcome="failed", message=message)], found=True)
    return suite.AcceptanceResult(ran=True, report=report)


def _cannot_pass(root: Path, result: suite.AcceptanceResult | None = None) -> list[str]:
    result = result or _failed()
    return [item for item in suite.findings_that_reopen(root, result, suite.tests_that_cannot_pass(root, result))
            if "strict mode violation" in item]


@pytest.mark.parametrize("spec", [AS_LOCKED, AS_REPAIRED], ids=["as-locked", "as-repaired"])
def test_the_measured_test_goes_back_naming_its_line_and_the_other_record(tmp_path, spec):
    root = _workspace(tmp_path, spec)
    suite.lock(root)

    found = _cannot_pass(root)

    assert len(found) == 1
    assert found[0].startswith(f"`bookmarks/acceptance/ui-validation.spec.js` line {LINE} ")
    assert "`ac9-link-${t}`" in found[0] and "`ac9-link-${t}-no-tag`" in found[0] and "`title`" in found[0]


def test_the_check_is_read_before_the_suite_is_locked_too(tmp_path):
    root = _workspace(tmp_path, AS_LOCKED)
    assert len([item for item in suite.tests_that_cannot_pass(root, _failed()) if "strict mode violation" in item]) == 1


@pytest.mark.parametrize("spec", [
    # Narrowed exactly, by what only the first record shows whole.
    AS_LOCKED.replace("filter({ hasText: `ac9-link-${t}` })",
                      "filter({ has: page.getByRole('link', { name: `ac9-link-${t}`, exact: true }) })"),
    # A regular expression.
    AS_LOCKED.replace("filter({ hasText: `ac9-link-${t}` })", "filter({ hasText: /^ac9-link-\\S+$/ })"),
    # Texts neither of which holds the other.
    AS_LOCKED.replace("`ac9-link-${t}-no-tag`", "`ac9-second-${t}`"),
    # The first of what it finds.
    AS_LOCKED.replace("filter({ hasText: `ac9-link-${t}` });", "filter({ hasText: `ac9-link-${t}` }).first();"),
    # The second record made after the page was loaded, and the page never loaded again.
    AS_LOCKED.replace("  await page.goto('/');\n", "").replace("  const t = tag();\n",
                                                               "  const t = tag();\n  await page.goto('/');\n"),
    # Something removes a record before the look.
    AS_LOCKED.replace("  await page.goto('/');", "  await request.delete(`/api/bookmarks/${bm2.id}`);\n"
                                                 "  await page.goto('/');"),
], ids=["exact", "regex", "distinct-texts", "first", "made-after-the-load", "a-record-removed"])
def test_a_locator_that_can_find_one_is_left_alone(spec):
    assert js.own_records_a_text_filter_also_matches(spec) == []


def test_a_count_and_a_negated_assertion_need_no_one_element():
    spec = AS_LOCKED.split("  const item1")[0] + """  const item1 = page.getByRole('listitem').filter({ hasText: `ac9-link-${t}` });
  await expect(item1).toHaveCount(2);
  await expect(item1).not.toBeHidden();
});
"""
    assert js.own_records_a_text_filter_also_matches(spec) == []


def test_a_look_inside_the_test_never_says_the_other_item_holds_is_left_alone():
    """Only the tag is looked for: the other record has none, so the look may find one element."""
    spec = AS_LOCKED.split("  await expect(\n    item1.getByRole")[0] + "});\n"
    assert js.own_records_a_text_filter_also_matches(spec) == []


def test_a_locator_written_in_place_is_read_too():
    spec = AS_LOCKED.split("  const item1")[0] + """  await expect(page.getByText(`ac9-link-${t}`)).toBeVisible();
});
"""
    assert js.own_records_a_text_filter_also_matches(spec) == [(31, "`ac9-link-${t}`", "`ac9-link-${t}-no-tag`", "title")]


def test_the_finding_speaks_of_the_test_in_plain_words(tmp_path):
    root = _workspace(tmp_path, AS_LOCKED)
    finding = _cannot_pass(root)[0]
    assert "about the test, not the product" in finding and "exact: true" in finding
    assert not BANNED.search(finding)


def test_the_stored_suites_that_passed_their_hidden_tests_give_no_finding():
    found = {str(path.relative_to(CORPUS)): hits
             for path in sorted(CORPUS.rglob("*.spec.*"))
             if (hits := js.own_records_a_text_filter_also_matches(path.read_text(encoding="utf-8", errors="replace")))}
    assert len(list(CORPUS.rglob("*.spec.*"))) >= 100
    assert found == {}


def test_the_dispute_is_told_and_cannot_keep_the_test(tmp_path):
    root = _workspace(tmp_path, AS_REPAIRED)
    shown = suite.what_the_code_shows_of(root, [TITLE, "[AC-7] Page contains Title"])

    text = suite_dispute.build_dispute_request(
        [(TITLE, "AC-9: x", "m")], "code", "brief", found_in_the_code=[finding for _, finding in shown],
    )["messages"][0]["content"]

    assert [name for name, _ in shown] == [TITLE]
    assert "strict mode violation" in text


def test_every_pack_that_reads_locked_suites_reads_this_too():
    for name in ("fullstack-node", "browser-javascript", "browser-react"):
        pack = pack_named(name)
        assert pack.own_records_a_text_filter_matches is js.own_records_a_text_filter_also_matches
        assert pack.several_of_its_own_records_matched is js.several_of_its_own_records_matched


# --- at test time: the runner's own refusal (LF.1615) -----------------------------------------------------------------

#: The runner's words on the measured run, shortened.
REFUSED = """Error: expect(locator).toBeVisible() failed

    Locator: getByRole('listitem').filter({ hasText: 'ac9-link-ac7-1795778706878-0x5cs9' }).getByText('ac7-1795778706878-0x5cs9')
    Error: strict mode violation: getByRole('listitem').filter({ hasText: 'ac9-link-ac7-1795778706878-0x5cs9' }).getByText('ac7-1795778706878-0x5cs9') resolved to 3 elements:
        1) <a target="_blank" class="bookmark-title" href="https://example.com/second">ac9-link-ac7-1795778706878-0x5cs9-no-tag</a> aka getByRole('link', { name: 'ac9-link-ac7-1795778706878-0x5cs9-no-tag' })
        2) <a target="_blank" class="bookmark-title" href="https://example.com/first">ac9-link-ac7-1795778706878-0x5cs9</a> aka getByRole('link', { name: 'ac9-link-ac7-1795778706878-0x5cs9', exact: true })
        3) <span class="bookmark-tag">ac7-1795778706878-0x5cs9</span> aka getByText('ac7-1795778706878-0x5cs9', { exact: true })

    Call log:
"""
#: The same refusal for whole list items, which the runner shows by what it would find each by.
REFUSED_ITEMS = """Error: strict mode violation: getByRole('listitem').filter({ hasText: 'ac9-link-ac7-1-q' }) resolved to 2 elements:
    1) <li class="bookmark-item">…</li> aka getByRole('listitem').filter({ hasText: 'ac9-link-ac7-1-q-no-tagDelete' })
    2) <li class="bookmark-item">…</li> aka getByRole('listitem').filter({ hasText: 'ac9-link-ac7-1-qac7-1-qDelete' })
"""


def _measured(tmp_path: Path, message: str, spec: str = AS_LOCKED) -> list[str]:
    """What the round's measured checks say, with the static reading of the file left out."""
    root = _workspace(tmp_path, spec)
    return suite.tests_whose_text_found_several_of_their_own_records(root, _failed(message))


@pytest.mark.parametrize("message", [REFUSED, REFUSED_ITEMS], ids=["inside-the-items", "the-items"])
def test_a_refusal_over_two_records_the_test_writes_is_the_test_s(tmp_path, message):
    found = _measured(tmp_path, message)

    assert len(found) == 1 and found[0].startswith(f"`{TITLE}` ")
    assert "ac9-link-ac7-1795778706878-0x5cs9-no-tag" in found[0] or "ac9-link-ac7-1-q-no-tagDelete" in found[0]
    assert not BANNED.search(found[0].replace(TITLE, ""))


def test_the_refusal_reaches_the_round_as_a_test_that_cannot_pass(tmp_path):
    """Measured, so it needs no reading of the file: here its records are made by a function from elsewhere, which the
    static check does not read."""
    spec = AS_LOCKED.replace(HEAD, "import { test, expect } from '@playwright/test';\n"
                                   "import { createBookmark, tag } from './helpers.js';\n\n")
    root = _workspace(tmp_path, spec)
    suite.lock(root)
    assert js.own_records_a_text_filter_also_matches(spec) == []

    found = _cannot_pass(root, _failed(REFUSED))

    assert len(found) == 1 and found[0].startswith(f"`{TITLE}` ")


@pytest.mark.parametrize("message", [
    # The page shows one record twice, with the same text: the product's to fix.
    REFUSED.replace("ac9-link-ac7-1795778706878-0x5cs9-no-tag", "ac9-link-ac7-1795778706878-0x5cs9"),
    # Exact: one name matched whole.
    REFUSED_ITEMS.replace("getByRole('listitem').filter({ hasText: 'ac9-link-ac7-1-q' })",
                          "getByRole('link', { name: 'ac9-link-ac7-1-q', exact: true })"),
    # Texts the test never writes: some other record's.
    REFUSED_ITEMS.replace("ac9-link", "zz9-item"),
    # A failure that is no refusal for several.
    "Error: expect(locator).toBeVisible() failed\n    Locator: getByText('x')\n    Expected: visible\n",
], ids=["one-record-twice", "exact", "not-the-test-s-own", "not-refused-for-several"])
def test_a_refusal_the_product_may_answer_for_is_left_alone(tmp_path, message):
    assert _measured(tmp_path, message) == []


@pytest.mark.parametrize("spec", [
    AS_LOCKED.replace("  await page.goto('/');", "  await request.delete(`/api/bookmarks/${bm2.id}`);\n"
                                                 "  await page.goto('/');"),
    AS_LOCKED.replace("  await page.goto('/');", "  await page.goto('/');\n  await page.getByLabel('Filter').fill(t);"),
    AS_LOCKED.replace("  await page.goto('/');", "  await page.goto(`/?tag=${t}`);"),
], ids=["a-record-removed", "the-list-filtered", "an-address-with-a-query"])
def test_a_refusal_after_the_test_took_a_record_off_or_filtered_is_the_product_s(tmp_path, spec):
    """A product that failed to remove or hide the other record is refused the same way."""
    assert _measured(tmp_path, REFUSED, spec) == []
