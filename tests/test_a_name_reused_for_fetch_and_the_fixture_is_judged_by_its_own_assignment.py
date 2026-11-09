"""A response name used once for the `request` fixture and once for `fetch` is judged by the assignment before each read.

Measured on one run: a spec held `const getResp = await request.get(...)` in one test and
`const getResp = await fetch(...)` in the restart test. The checks bound each name to one kind for the whole file, so
the restart test's correct `getResp.status` was called wrong for the fixture, and its correct `fetch(..., { body })` was
called a fetch-style body handed to the fixture. QA was sent to "repair" right lines, and the suite went round its
review again and again without locking.
"""
from __future__ import annotations

from app.acceptance import suite
from app.stacks import contract, pack_named

SPEC = """import { test, expect } from '@playwright/test';
test('[AC-5] deletes', async ({ request }) => {
  const getResp = await request.get(`/notes/${id}`);
  expect(getResp.status).toBe(404);
});
test('[AC-6] survives a restart', async () => {
  const createResp = await fetch(`${first.baseURL}/notes`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'Persist', body: 'Data' })
  });
  expect(createResp.status).toBe(201);
  const getResp = await fetch(`${second.baseURL}/notes/${id}`);
  expect(getResp.status).toBe(200);
});
"""


def _suite(tmp_path):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "notes.spec.js").write_text(SPEC)
    return tmp_path


def test_only_the_fixture_s_uncalled_status_is_named(tmp_path):
    found = suite.responses_read_without_the_call(_suite(tmp_path))
    assert len(found) == 1 and "line(s) 4:" in found[0]


def test_a_body_in_a_plain_fetch_call_is_not_called_the_fixture_s(tmp_path):
    assert suite.requests_with_a_fetch_body(_suite(tmp_path)) == []


def test_nothing_is_named_wrong_for_fetch_either(tmp_path):
    assert suite.fetch_calls_written_like_the_fixture(_suite(tmp_path)) == []
