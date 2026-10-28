"""A locked test asserting a success status the interface contract never gives for that call cannot pass.

Measured on one run: a test looped over `GET /health` and `POST /notes` asserting 200 for both; the contract says
`POST /notes -> 201`. It named no criterion, so every criterion read green beside a red suite.
"""
from __future__ import annotations

import inspect
import re

from app.acceptance import suite
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CONTRACT = [
    "AC-1 POST /notes -> 201", "AC-3 GET /notes/{id} -> 200 or 404", "AC-14 GET /health -> 200",
    "AC-5 DELETE /notes/{id} -> 204 or 404", "AC-13 POST /notes -> 400",
]

LOOPED = """import { test, expect } from '@playwright/test';
test('Response headers on all endpoints', async ({ request }) => {
  const endpoints = [
    { method: 'get', path: '/health' },
    { method: 'post', path: '/notes', data: { title: 'h' } },
  ];
  for (const ep of endpoints) {
    let res;
    if (ep.method === 'get') { res = await request.get(ep.path); } else { res = await request.post(ep.path, { data: ep.data }); }
    expect(res.status()).toBe(200);
  }
});
"""
DIRECT = """test('[AC-1] creates', async ({ request }) => {
  const res = await request.post('/notes', { data: { title: 'a' } });
  expect(res.status()).toBe(200);
});
test('[AC-5] deletes', async ({ request }) => {
  const created = await (await request.post('/notes', { data: { title: 'a' } })).json();
  const gone = await request.delete(`/notes/${created.id}`);
  expect(gone.status()).toBe(200);
});
"""
RIGHT = """test('[AC-1] creates then reads', async ({ request }) => {
  let res = await request.post('/notes', { data: { title: 'a' } });
  expect(res.status()).toBe(201);
  res = await request.get('/notes/1');
  expect(res.status()).toBe(200);
  const bad = await request.post('/notes', { data: {} });
  expect(bad.status()).toBe(400);
});
test('[AC-7] each its own', async ({ request }) => {
  const endpoints = [{ method: 'get', path: '/health', status: 200 }, { method: 'post', path: '/notes', status: 201 }];
  for (const ep of endpoints) { const r = await request[ep.method](ep.path); expect(r.status()).toBe(200); }
});
"""


def _suite(tmp_path, text):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "api.spec.js").write_text(text)
    return tmp_path


def test_a_loop_asserting_200_on_a_create_is_found(tmp_path):
    found = suite.tests_whose_success_status_the_contract_does_not_give(_suite(tmp_path, LOOPED), CONTRACT)
    assert len(found) == 1 and "`POST /notes` is given 201" in found[0] and "AC-1 POST /notes -> 201" in found[0]
    assert not BANNED.search(found[0])


def test_direct_calls_are_found_by_their_own_route(tmp_path):
    found = suite.tests_whose_success_status_the_contract_does_not_give(_suite(tmp_path, DIRECT), CONTRACT)
    assert len(found) == 1 and "`POST /notes` asserted 200" in found[0] and "`DELETE /notes/${created.id}`" in found[0]


def test_right_statuses_refusals_and_entries_with_their_own_status_are_left(tmp_path):
    assert suite.tests_whose_success_status_the_contract_does_not_give(_suite(tmp_path, RIGHT), CONTRACT) == []


def test_the_review_and_the_rounds_ask_it():
    from app.graph import acceptance_nodes

    assert "tests_whose_success_status_the_contract_does_not_give(" in inspect.getsource(acceptance_nodes.acceptance_review)
    assert "tests_whose_success_status_the_contract_does_not_give(repo_root)" in inspect.getsource(suite.tests_that_cannot_pass)
