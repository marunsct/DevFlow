"""A "cannot pass" finding that names a file and its lines is judged by the tests at those lines.

Measured on one run: findings were told apart by the first name they quote - for a file-level finding, the file
itself. Earlier (false) findings for the same file had been sent, so a real one - page assertions without `await`
in the failing test - counted as "already sent" and the suite was not repaired; and with its criteria read from AC
tags the finding's text does not carry, nothing was deferred either, and fixers were sent a test fault.
"""
from types import SimpleNamespace

from app.acceptance import suite
from app.graph import acceptance_nodes as nodes

SPEC = """import { test, expect } from '@playwright/test';
test('[AC-1] lists', async ({ page }) => {
  await page.goto('/');
});
test('[AC-4][AC-15] filters', async ({ page }) => {
  expect(page.getByText('x')).toBeVisible();
});
"""
FINDING = '`acceptance/page.spec.js` line(s) 6 assert on the page without `await`.'


def _state(tmp_path, monkeypatch, sent):
    (tmp_path / "acceptance").mkdir()
    path = tmp_path / "acceptance" / "page.spec.js"
    path.write_text(SPEC)
    monkeypatch.setattr(suite, "suite_files", lambda root: [path])
    return {"repository": SimpleNamespace(root_path=str(tmp_path)), "suite_repairs": nodes.MAX_SUITE_REPAIRS,
            "suite_repaired_tests": sent}


def test_a_file_already_sent_does_not_make_a_new_test_s_fault_old(tmp_path, monkeypatch):
    state = _state(tmp_path, monkeypatch, ["acceptance/page.spec.js"])
    assert nodes.may_repair(state, [FINDING]) == (nodes.MAX_SUITE_REPAIRS < nodes.MAX_SUITE_REPAIRS_IN_ALL)
    assert nodes._which_tests(state, FINDING) == ["[AC-4][AC-15] filters"]


def test_beyond_repair_reads_the_criteria_of_the_tests_it_names(tmp_path, monkeypatch):
    state = _state(tmp_path, monkeypatch, ["[AC-4][AC-15] filters"])
    state["suite_repairs"] = nodes.MAX_SUITE_REPAIRS_IN_ALL
    assert nodes.beyond_repair(state, [FINDING]) == ["AC-15", "AC-4"]
