"""The harness puts `baseURL` for `request.baseURL` itself, adding `baseURL` to the test's fixtures.

Measured on two runs: told the exact lines to change, QA left `request.baseURL` - `undefined` on every product -
through three review rounds and the suite was locked with it.
"""
from __future__ import annotations

from app.acceptance import suite
from app.stacks import contract, pack_named

TEXT = """import { test, expect } from '@playwright/test';
test('[AC-3] gets a note', async ({ request }) => {
  const res = await fetch(request.baseURL + '/notes/1');
  expect(res.status).toBe(404);
});
test('[AC-4] updates', async ({ request, baseURL }) => {
  await fetch(baseURL + '/notes');
  await fetch(request.baseURL + '/notes/1', { method: 'PUT' });
});
test('[AC-5] leaves others', async ({ request }) => {
  await request.get('/notes');
});
"""


def _suite(tmp_path, text):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    path = folder / "api.spec.js"
    path.write_text(text)
    return path


def test_each_read_becomes_baseurl_and_the_fixture_is_added_where_missing(tmp_path):
    path = _suite(tmp_path, TEXT)
    changed = suite.correct_reads_of_the_fixture_s_baseurl(tmp_path)
    after = path.read_text()
    assert changed and "2 test(s)" in changed[0]
    assert "request.baseURL" not in after
    assert "async ({ request, baseURL }) => {\n  const res = await fetch(baseURL + '/notes/1');" in after
    assert after.count("async ({ request, baseURL })") == 2
    assert "test('[AC-5] leaves others', async ({ request }) =>" in after
    assert suite.reads_of_what_the_test_does_not_have(tmp_path) == []


def test_a_suite_without_the_read_is_left_alone(tmp_path):
    path = _suite(tmp_path, "test('[AC-1] a', async ({ request, baseURL }) => { await fetch(baseURL); });\n")
    before = path.read_text()
    assert suite.correct_reads_of_the_fixture_s_baseurl(tmp_path) == [] and path.read_text() == before


def test_the_review_makes_the_correction_before_it_checks(tmp_path):
    from app.acceptance import junit
    from workflow_nodes import an_acceptance_review

    failing = suite.AcceptanceResult(ran=True, exit_code=1, report=junit.Report(found=True, tests=[
        junit.TestResult(name=f"[AC-{n}] t", outcome="failed", message="no product") for n in (3, 4, 5)]))

    update = an_acceptance_review(tmp_path, failing, pack="node-hono-native-api", files={"api.spec.js": TEXT})

    assert "request.baseURL" not in (tmp_path / "notes" / "acceptance" / "api.spec.js").read_text()
    assert not any("request.baseURL" in problem for problem in update.get("acceptance_feedback") or [])
