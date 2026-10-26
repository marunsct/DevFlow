"""A test that hands Playwright's `request` fixture a fetch-style `body:` cannot pass on any product, and the review says so.

Measured on two runs: every write in the locked suite was `request.fetch(url, { method, headers, body: JSON.stringify(x) })`;
Playwright's request API takes `data`, the service received no body and answered 400, and a product that passed every
hidden test was stopped as failed. The restart helper's guide had told QA to "write with fetch", which invited it.
"""
from __future__ import annotations

import re

from app.acceptance import suite
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

DIRECT = """import { test, expect } from '@playwright/test';
test('[AC-1] creates', async ({ request }) => {
  const res = await request.post('/notes', {
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'a', body: 'b' }),
  });
  expect(res.status()).toBe(201);
});
"""
THROUGH_A_HELPER = """import { test, expect } from '@playwright/test';
const fetchJSON = async (request, url, init = {}) => request.fetch(url, init);
test('[AC-1] creates', async ({ request }) => {
  const r = await fetchJSON(request, '/notes', { method: 'POST', body: JSON.stringify({ title: 'a' }) });
  expect(r.status()).toBe(201);
});
"""
RIGHT = """import { test, expect } from '@playwright/test';
test('[AC-1] creates', async ({ request }) => {
  const res = await request.post('/notes', { data: { title: 'a', body: 'b' } });
  expect(res.status()).toBe(201);
  const note = { title: 'x', body: 'y' };
  expect((await request.put('/notes/1', { data: note })).status()).toBe(200);
});
"""


def _suite(tmp_path, text):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "notes.spec.js").write_text(text)
    return tmp_path


def test_a_direct_fetch_style_body_is_found(tmp_path):
    found = suite.requests_with_a_fetch_body(_suite(tmp_path, DIRECT))
    assert len(found) == 1 and "line(s) 5" in found[0] and "data: { ... }" in found[0]
    assert not BANNED.search(found[0])


def test_a_body_passed_through_a_helper_is_found(tmp_path):
    assert len(suite.requests_with_a_fetch_body(_suite(tmp_path, THROUGH_A_HELPER))) == 1


def test_a_note_whose_field_is_called_body_is_not_flagged(tmp_path):
    assert suite.requests_with_a_fetch_body(_suite(tmp_path, RIGHT)) == []


def test_the_check_is_one_of_the_tests_that_cannot_pass():
    import inspect

    assert "requests_with_a_fetch_body(repo_root)" in inspect.getsource(suite.tests_that_cannot_pass)


def test_the_restart_guide_keeps_the_helper_to_the_restart_criterion():
    guide = pack_named("node-hono-native-api").acceptance_guide
    assert "only that criterion uses the" in guide and "data: { ... }" in guide
    assert "with fetch" not in guide
    assert not BANNED.search(guide.split("A criterion about the data")[-1])
