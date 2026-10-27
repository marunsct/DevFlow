"""A test that calls `fetch` the way Playwright's `request` fixture is called cannot pass on any product, and the review says so.

Measured on two runs of a small model, in the test that restarts the service (it starts its own server, so it calls
`fetch`): one passed the body as `data: {...}`, which `fetch` does not read - the product answered 400 - and one called
`res.status()`, which on a `fetch` response is a number, not a method. Each was found only after the suite was locked,
cost its repairs, and shipped its criteria unproven.
"""
from __future__ import annotations

import re

from app.acceptance import suite
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

WRONG = """import { test, expect } from '@playwright/test';
test('[AC-6] survives a restart', async () => {
  const res1 = await fetch(`${base}/notes`, {
    method: 'POST',
    data: { title: 'Persist', body: 'Data' },
  });
  expect(res1.status()).toBe(201);
});
"""
RIGHT = """import { test, expect } from '@playwright/test';
test('[AC-6] survives a restart', async ({ request }) => {
  const res1 = await fetch(`${base}/notes`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'Persist', body: 'Data' }),
  });
  expect(res1.status).toBe(201);
  const res2 = await request.post('/notes', { data: { title: 'a' } });
  expect(res2.status()).toBe(201);
});
"""


def _suite(tmp_path, text):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "restart.spec.js").write_text(text)
    return tmp_path


def test_a_data_option_and_a_called_status_on_fetch_are_found_with_their_lines(tmp_path):
    found = suite.fetch_calls_written_like_the_fixture(_suite(tmp_path, WRONG))
    assert len(found) == 2
    assert any("line(s) 5" in item and "`data:`" in item for item in found)
    assert any("line(s) 7" in item and "res.status" in item for item in found)
    for item in found:
        assert not BANNED.search(item)


def test_fetch_written_as_fetch_and_the_fixture_as_the_fixture_are_left_alone(tmp_path):
    assert suite.fetch_calls_written_like_the_fixture(_suite(tmp_path, RIGHT)) == []


def test_it_is_one_of_the_checks_that_reopen_a_locked_suite():
    import inspect

    assert "fetch_calls_written_like_the_fixture(repo_root)" in inspect.getsource(suite.tests_that_cannot_pass)
