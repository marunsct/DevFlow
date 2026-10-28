"""`body:` written in a comment above a correct `fetch` call is not a fixture call given a fetch-style body.

Measured on one run: "Playwright's request fixture does not read a `body:` option, so we reach the service directly"
above a correct `fetch(...)` was read as the misuse, and the locked suite was reopened for a test that passed.
"""
from __future__ import annotations

from app.acceptance import suite
from app.stacks import contract, pack_named

COMMENTED = """import { test, expect } from '@playwright/test';
test('[AC-14] health', async ({ request }) => {
  expect((await request.get('/health')).status()).toBe(200);
});

test('[AC-16] invalid JSON body returns 400', async ({ request }) => {
  // Use native fetch to send raw non-JSON text — Playwright's request fixture
  // does not read a `body:` option, so we reach the service directly.
  const port = process.env.ACCEPTANCE_PORT;
  const res = await fetch(`http://127.0.0.1:${port}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: 'not valid json',
  });
  expect(res.status).toBe(400);
});

// ---------------------------------------------------------------------------
"""
MISUSED = """import { test, expect } from '@playwright/test';
test('[AC-1] creates', async ({ request }) => {
  const res = await request.fetch('/notes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: 'a' }) });
  expect(res.status()).toBe(201);
});
"""


def _suite(tmp_path, text):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "api.spec.js").write_text(text)
    return tmp_path


def test_a_commented_body_beside_a_real_fetch_is_left(tmp_path):
    assert suite.requests_with_a_fetch_body(_suite(tmp_path, COMMENTED)) == []


def test_the_misuse_itself_is_still_found(tmp_path):
    found = suite.requests_with_a_fetch_body(_suite(tmp_path, MISUSED))
    assert len(found) == 1 and "line(s) 3" in found[0]
