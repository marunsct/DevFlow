"""A test that reads the `request` fixture's `status` without calling it cannot pass on any product, and the review says so.

Measured on a small-model run: `expect(response.status).toBe(201)` beside `expect(resp.status()).toBe(200)` in one file;
Playwright's response has `status()` as a method, so the first compares a function with 201 on every product.
"""
from __future__ import annotations

import re

from app.acceptance import suite
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

WRONG = """import { test, expect } from '@playwright/test';
test('[AC-1] creates', async ({ request }) => {
  const response = await request.post('/notes', { data: { title: 'a', body: 'b' } });
  expect(response.status).toBe(201);
  expect(response.ok).toBeTruthy();
});
"""
RIGHT = """import { test, expect } from '@playwright/test';
test('[AC-1] creates', async ({ request }) => {
  const res = await request.post('/notes', { data: { title: 'a', body: 'b' } });
  expect(res.status()).toBe(201);
  expect(res.ok()).toBeTruthy();
  expect(res.headers()['content-type']).toContain('json');
  const raw = await fetch('http://127.0.0.1:1/notes');
  expect(raw.status).toBe(200);
});
"""


def _suite(tmp_path, text):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "notes.spec.js").write_text(text)
    return tmp_path


def test_a_status_read_as_a_property_is_found_with_its_lines(tmp_path):
    found = suite.responses_read_without_the_call(_suite(tmp_path, WRONG))
    assert len(found) == 1
    assert "line(s) 4, 5" in found[0] and "res.status()" in found[0]
    assert not BANNED.search(found[0])


def test_called_methods_and_a_plain_fetch_response_are_left_alone(tmp_path):
    assert suite.responses_read_without_the_call(_suite(tmp_path, RIGHT)) == []


def test_it_is_one_of_the_checks_that_reopen_a_locked_suite():
    import inspect

    assert "responses_read_without_the_call(repo_root)" in inspect.getsource(suite.tests_that_cannot_pass)
