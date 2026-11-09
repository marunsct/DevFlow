"""A Playwright page assertion written without `await` goes back to the suite.

Measured on one run: dozens of `expect(page.getByRole('listitem').filter(...)).toBeVisible();` with no `await`. A page
assertion waits and returns a promise; unawaited, the test does not wait for it - it passes a product that fails it,
or fails detached at a line it never reached (`page.spec.js:418:3`), and two fixers in a row chased that failure.
"""
from app.acceptance import suite
from app.stacks.packs import _javascript as js

SPEC = """import { test, expect } from '@playwright/test';
test('[AC-4] filter', async ({ page }) => {
  await page.goto('/');
  expect(page.getByRole('listitem').filter({ hasText: 'Docs' })).toBeVisible();
  await expect(page.getByRole('listitem')).toHaveCount(1);
  expect(page.getByText('Saved')).not.toBeVisible();
  const items = await page.getByRole('listitem').count();
  expect(items).toBe(1);
  expect(response.status()).toBe(201);
});
"""


def test_unawaited_page_assertions_are_found_and_awaited_or_plain_ones_are_not():
    assert js.unawaited_page_assertions(SPEC) == [4, 6]


def test_the_suite_check_names_the_lines(tmp_path, monkeypatch):
    path = tmp_path / "page.spec.js"
    path.write_text(SPEC)
    monkeypatch.setattr(suite, "suite_files", lambda root: [path])
    [found] = suite.page_assertions_without_await(tmp_path)
    assert "line(s) 4, 6" in found and "await" in found


def test_it_is_among_the_checks_that_reopen_a_suite():
    import inspect

    assert "page_assertions_without_await(repo_root)" in inspect.getsource(suite.tests_that_cannot_pass)


def test_every_line_is_named_so_a_failing_test_s_line_reopens_the_suite(tmp_path, monkeypatch):
    """Measured on its first round: the finding named only the first 12 lines, all in passing tests; after a lock a
    finding reopens the suite only for a failing test it names, so the failing test's unawaited line - past the
    first twelve - never sent the suite back."""
    body = "".join(f"  expect(page.getByText('t{n}')).toBeVisible();\n" for n in range(20))
    text = "import { test, expect } from '@playwright/test';\ntest('[AC-1] many', async ({ page }) => {\n" + body + "});\n"
    path = tmp_path / "page.spec.js"
    path.write_text(text)
    monkeypatch.setattr(suite, "suite_files", lambda root: [path])
    [found] = suite.page_assertions_without_await(tmp_path)
    assert "22" in found.split("line(s)")[1].split("assert")[0]
