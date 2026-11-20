"""A test that expects a locator found by a loose text gone, while it expects a longer text holding it shown, cannot pass.

Playwright matches a string given as `hasText`, to `getByText` or as a role's `name` without `exact: true` ignoring case
and as part of the text. Measured on one run: a locked test made records titled 'case-work' and 'case-Work', filtered,
then expected the item with 'case-work' gone and the one with 'case-Work' shown. The first locator also matched the
second item, three attempts over two hours went to a product that already filtered right, and a dispute called the test
sound. Only text is read here and the reports are made up: no suite runs.
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
TITLE = "[AC-4] filter is case-sensitive"


def _a_test(absent: str, present: str = "page.getByRole('listitem').filter({ hasText: 'case-Work' })",
            between: str = "") -> str:
    return f"""import {{ test, expect }} from '@playwright/test';

test('{TITLE}', async ({{ page, request }}) => {{
  await page.goto('/');
  await request.post('/api/records', {{ data: {{ title: 'case-work', label: 'work' }} }});
  await request.post('/api/records', {{ data: {{ title: 'case-Work', label: 'Work' }} }});
  await page.reload();
  await page.getByLabel('Filter by label', {{ exact: true }}).fill('Work');

  const lower = {absent};
  await expect(lower).not.toBeAttached();
{between}
  const upper = {present};
  await expect(upper).toBeAttached();
}});
"""


MEASURED = _a_test("page.getByRole('listitem').filter({ hasText: 'case-work' })")


def _workspace(tmp_path: Path, spec: str) -> Path:
    contract.write(tmp_path, pack_named("fullstack-node"), "records", "Records")
    (tmp_path / "records" / "acceptance").mkdir(parents=True)
    (tmp_path / "records" / "acceptance" / "workflow.spec.js").write_text(spec, encoding="utf-8")
    return tmp_path


def _failed(name: str = TITLE) -> suite.AcceptanceResult:
    report = junit.Report(tests=[junit.TestResult(name=name, outcome="failed", message="expected not attached")], found=True)
    return suite.AcceptanceResult(ran=True, report=report)


def _cannot_pass(root: Path) -> list[str]:
    result = _failed()
    return [item for item in suite.findings_that_reopen(root, result, suite.tests_that_cannot_pass(root, result))
            if "ignoring case and as part of the text" in item]


def test_the_measured_test_goes_back_to_the_suite_naming_both_texts_and_the_exact_match(tmp_path):
    root = _workspace(tmp_path, MEASURED)
    suite.lock(root)

    found = _cannot_pass(root)

    assert len(found) == 1
    assert found[0].startswith("`records/acceptance/workflow.spec.js` line 11 ")
    assert '"case-work"' in found[0] and '"case-Work"' in found[0]
    assert "exact: true" in found[0] and "/^case-work$/" in found[0]


@pytest.mark.parametrize("absent, present", [
    ("page.getByText('case-work')", "page.getByText('case-Work', { exact: true })"),
    ("page.getByRole('link', { name: 'case-work' })", "page.getByRole('link', { name: 'case-Work', exact: true })"),
    ("page.locator('li', { hasText: 'case-work' })", "page.locator('li', { hasText: /^case-Work$/ })"),
])
def test_each_way_of_matching_a_string_loosely_is_found(absent, present):
    assert [hit[1:] for hit in js.absences_a_longer_text_also_meets(_a_test(absent, present))] == [("case-work", "case-Work")]


def test_a_title_kept_after_an_edit_that_lengthened_it_is_found():
    edited = """test('[AC-2] edit a title', async ({ page }) => {
  const title = 'Lifecycle record';
  await page.getByLabel('Edit title', { exact: true }).fill(title + ' - edited');
  await page.getByRole('menuitem', { name: 'Save', exact: true }).press('Enter');
  await expect(page.getByText('Lifecycle record - edited')).toBeVisible();
  await expect(page.getByText(title)).not.toBeVisible();
});
"""
    assert js.absences_a_longer_text_also_meets(edited) == [(6, "Lifecycle record", "Lifecycle record - edited")]


@pytest.mark.parametrize("spec", [
    # Matched exactly: `exact: true`, or a regular expression with anchors.
    _a_test("page.getByText('case-work', { exact: true })", "page.getByText('case-Work', { exact: true })"),
    _a_test("page.getByRole('listitem').filter({ hasText: /^case-work$/ })"),
    _a_test("page.getByRole('listitem').filter({ has: page.getByText('case-work', { exact: true }) })"),
    # Texts that differ by more than case or a part.
    _a_test("page.getByRole('listitem').filter({ hasText: 'case-play' })"),
    # A step between the two assertions: what the page shows may have changed.
    _a_test("page.getByRole('listitem').filter({ hasText: 'case-work' })",
            between="  await page.getByLabel('Filter by label', { exact: true }).fill('');"),
    # Another locator: it may look in another place.
    _a_test("page.getByRole('listitem').filter({ hasText: 'case-work' })", "page.getByRole('heading', { name: 'case-Work' })"),
], ids=["exact", "anchored-pattern", "has-exact", "different-texts", "step-between", "other-locator"])
def test_a_test_whose_absence_can_hold_is_left_alone(tmp_path, spec):
    root = _workspace(tmp_path, spec)
    suite.lock(root)
    assert _cannot_pass(root) == []


def test_a_test_that_only_expects_records_shown_is_left_alone(tmp_path):
    spec = MEASURED.replace("await expect(lower).not.toBeAttached();", "await expect(lower).toBeAttached();")
    root = _workspace(tmp_path, spec)
    suite.lock(root)
    assert _cannot_pass(root) == []


def test_the_finding_speaks_of_the_test_in_plain_words(tmp_path):
    root = _workspace(tmp_path, MEASURED)
    finding = _cannot_pass(root)[0]
    assert "about the test, not the product" in finding
    assert not BANNED.search(finding)


def test_the_stored_suites_that_passed_their_hidden_tests_give_no_finding():
    found = {str(path.relative_to(CORPUS)): hits
             for path in sorted(CORPUS.rglob("*.spec.*"))
             if (hits := js.absences_a_longer_text_also_meets(path.read_text(encoding="utf-8", errors="replace")))}
    assert len(list(CORPUS.rglob("*.spec.*"))) >= 100
    assert found == {}


def test_the_dispute_is_told_what_the_code_shows(tmp_path):
    root = _workspace(tmp_path, MEASURED)
    shown = suite.what_the_code_shows_of(root, [TITLE, "[AC-1] save a record"])

    text = suite_dispute.build_dispute_request(
        [(TITLE, "AC-4: x", "m")], "code", "brief", found_in_the_code=[finding for _, finding in shown],
    )["messages"][0]["content"]

    assert [name for name, _ in shown] == [TITLE]
    assert "ignoring case and as part of the text" in text and "cannot pass as it is written" in text
    told = text.split("--- What the harness found in these tests' own code ---")[1].split("--- The suite's code ---")[0]
    assert not BANNED.search(told)


def test_a_dispute_that_calls_the_test_sound_still_reopens_it(tmp_path):
    from workflow_nodes import a_dispute

    root = _workspace(tmp_path, MEASURED)
    spec = root / "records" / "acceptance" / "workflow.spec.js"
    judged: list[str] = []

    def the_judge(state, config, *, initial_request, output_key, **kwargs):
        judged.append(" ".join(str(message["content"]) for message in initial_request["messages"]))
        return {output_key: object()}

    _, asked = a_dispute(tmp_path, [(TITLE, "AC-4: x", "expected not attached")], [], reopened={}, patches={
        "app.acceptance.suite.suite_files": lambda _: [spec],
        "app.graph.workflow._run_gated_agent": the_judge,
    })

    assert judged and "ignoring case and as part of the text" in judged[0]
    assert len(asked["reopen"]) == 1
    assert [item for item in asked["reopen"][0]["broken"] if item.startswith(f"`{TITLE}` cannot pass")]


def test_every_pack_that_reads_locators_reads_this_too():
    for name in ("fullstack-node", "browser-javascript", "browser-react"):
        assert pack_named(name).absences_a_longer_text_meets is js.absences_a_longer_text_also_meets
