"""A locked test that asserts a JSON content type on a DELETE the contract answers with 204 cannot pass.

Measured on one run (hidden 5/9): AC-7's test looped over every endpoint, the DELETE included, and asserted
`content-type` contains `application/json`; the contract says `DELETE /notes/{id} -> 204 or 404`, and a 204 has no
body. Every fix that made delete right broke that test and was reverted - eight times over four attempts.
"""
from __future__ import annotations

import re

from app.acceptance import suite
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CONTRACT = ["AC-5 DELETE /notes/{id} -> 204 or 404", "AC-1 POST /notes -> 201"]

LOOPED = """import { test, expect } from '@playwright/test';
const endpoints = [
  { method: 'post', url: '/notes', status: 201 },
  { method: 'delete', url: '/notes/1', status: 404 },
];
for (const ep of endpoints) {
  test(`[AC-7] ${ep.method} returns Content-Type application/json`, async ({ request }) => {
    const resp = await request[ep.method](ep.url);
    const ct = resp.headers()['content-type'];
    expect(ct.toLowerCase()).toContain('application/json');
  });
}
"""
DIRECT = """test('[AC-5] delete answers json', async ({ request }) => {
  const res = await request.delete('/notes/1');
  expect(res.headers()['content-type']).toContain('application/json');
});
"""
RIGHT = """test('[AC-7] create answers json', async ({ request }) => {
  const res = await request.post('/notes', { data: { title: 'a' } });
  expect(res.headers()['content-type']).toContain('application/json');
});
test('[AC-5] deletes', async ({ request }) => {
  const res = await request.delete('/notes/1');
  expect(res.status()).toBe(204);
});
"""


def _suite(tmp_path, text):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "api.spec.js").write_text(text)
    return tmp_path


def test_a_looped_check_over_a_delete_is_found(tmp_path):
    found = suite.tests_that_want_json_from_a_204(_suite(tmp_path, LOOPED), CONTRACT)
    assert len(found) == 1 and "204" in found[0] and "api.spec.js" in found[0]
    assert not BANNED.search(found[0])


def test_a_direct_check_on_a_delete_is_found(tmp_path):
    assert len(suite.tests_that_want_json_from_a_204(_suite(tmp_path, DIRECT), CONTRACT)) == 1


def test_json_checked_on_other_answers_and_a_204_checked_by_status_are_left(tmp_path):
    assert suite.tests_that_want_json_from_a_204(_suite(tmp_path, RIGHT), CONTRACT) == []


def test_a_contract_whose_delete_answers_200_says_nothing(tmp_path):
    assert suite.tests_that_want_json_from_a_204(_suite(tmp_path, DIRECT), ["AC-5 DELETE /notes/{id} -> 200"]) == []


def test_the_review_and_the_rounds_ask_it():
    import inspect

    from app.graph import acceptance_nodes

    assert "tests_that_want_json_from_a_204(" in inspect.getsource(acceptance_nodes.acceptance_review)
    assert "tests_that_want_json_from_a_204(repo_root)" in inspect.getsource(suite.tests_that_cannot_pass)


AFTER_A_LOOP = """import { test, expect } from '@playwright/test';
const endpoints = [{ method: 'delete', url: '/notes/1' }];
test('[AC-5] deletes each', async ({ request }) => {
  for (const ep of endpoints) {
    expect((await request.delete(ep.url)).status()).toBe(404);
  }
});
test('[AC-7] create answers json', async ({ request }) => {
  const res = await request.post('/notes', { data: { title: 'a' } });
  expect(res.headers()['content-type']).toContain('application/json');
});
"""


def test_a_loop_in_the_previous_test_does_not_count(tmp_path):
    """Deep review, acceptance A6: the loop detection reached a `for (` in the previous test and flagged a right check."""
    assert suite.tests_that_want_json_from_a_204(_suite(tmp_path, AFTER_A_LOOP), CONTRACT) == []
