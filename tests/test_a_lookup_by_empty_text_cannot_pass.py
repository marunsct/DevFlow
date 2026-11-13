"""A page test that looks an element up by empty text is the test's own fault: it matches nearly every element.

Measured on one run: a dispute's rewrite asserted `expect(page.getByText('')).not.toBeVisible()`, and a right product
failed it through every round after.
"""
import re
from types import SimpleNamespace

from app.acceptance import suite
from app.stacks.packs import _javascript as js

EMPTY = re.compile(js.TEST_SOURCE_BUGS[-1])


def test_empty_text_lookups_are_found():
    assert EMPTY.search("await expect(page.getByText('')).not.toBeVisible();")
    assert EMPTY.search("page.getByRole('listitem').filter({ hasText: \"\" })")
    assert EMPTY.search("page.getByLabel(``, { exact: true })")


def test_real_lookups_are_not():
    for text in ("page.getByText('Save')", "page.getByText(`${title}`)", "filter({ hasText: title })",
                 "page.getByLabel('Title', { exact: true })"):
        assert not EMPTY.search(text), text


def test_a_failing_test_with_one_is_the_test_s_own(tmp_path):
    from app.stacks import contract, pack_named

    contract.write(tmp_path, pack_named("browser-javascript"), "app", "App")
    folder = tmp_path / "app" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "page.spec.js").write_text(
        "test('[AC-8] refused', async ({ page }) => {\n  await expect(page.getByText('')).not.toBeVisible();\n});\n")
    result = SimpleNamespace(ran=True, output="", report=SimpleNamespace(found=True, tests=[
        SimpleNamespace(name="[AC-8] refused", outcome="failed", message="Error: expect(locator).not.toBeVisible() failed")]))
    found = suite.tests_that_broke_themselves(tmp_path, result)
    [said] = [f for f in found if "[AC-8] refused" in f]
    assert "empty text" in said and "promise" not in said
