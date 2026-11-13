"""A repair that rewrites a test it was not sent for has that test put back as it was locked, before the review reads it.

Measured over the runs that lost a hidden test after a dispute: in 3 of 4, the repair after the ruling also rewrote
tests no ruling named, loosened to what the product did (an exact name made a pattern, a link found by its text made
any link), and the hidden tests of those behaviours failed.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import suite
from app.stacks import contract, pack_named

HEAD = "import { test, expect } from '@playwright/test';\n\n"
CALLED_WRONG = "test('[AC-2] counts', async ({ page }) => {\n  expect(await count()).toBe(3);\n});\n\n"
RIGHT = "test('[AC-5] names', async ({ page }) => {\n  await page.getByRole('button', { name: 'All', exact: true }).click();\n});\n"


def _repairing(tmp_path, names):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    spec = folder / "page.spec.js"
    spec.write_text(HEAD + CALLED_WRONG + RIGHT)
    suite.save_criteria(tmp_path, [SimpleNamespace(id="AC-2", text="It counts", source="brief"),
                                   SimpleNamespace(id="AC-5", text="Views are named", source="brief")])
    suite.lock(tmp_path)
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, names)
    return spec


def test_a_test_not_sent_for_is_put_back_and_the_one_sent_for_kept(tmp_path):
    spec = _repairing(tmp_path, ["[AC-2] counts"])
    loosened = RIGHT.replace("{ name: 'All', exact: true }", "{ name: /^All/ }")
    spec.write_text(HEAD + CALLED_WRONG.replace("toBe(3)", "toBe(2)") + loosened)

    assert suite.put_back_tests_the_repair_was_not_sent_for(tmp_path) == ["[AC-5] names"]
    text = spec.read_text()
    assert "toBe(2)" in text and "exact: true" in text and "/^All/" not in text


def test_nothing_changes_outside_a_repair(tmp_path):
    spec = _repairing(tmp_path, ["[AC-2] counts"])
    suite.lock(tmp_path)
    spec.write_text(HEAD + CALLED_WRONG + RIGHT.replace("exact: true", "exact: false"))
    assert suite.put_back_tests_the_repair_was_not_sent_for(tmp_path) == []


def test_the_review_puts_them_back_before_it_reads_the_suite():
    import inspect

    from app.graph import acceptance_nodes

    source = inspect.getsource(acceptance_nodes.acceptance_review)
    assert source.index("put_back_tests_the_repair_was_not_sent_for") < source.index("problems = suite.gaps(root)")
