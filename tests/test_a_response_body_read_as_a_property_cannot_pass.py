"""A `request` fixture response read as `.body.<field>` cannot pass: `body()` is a method giving bytes.

Measured on one run: `created.body.id` was `undefined`, the next request went to `/notes/undefined` and answered 400,
and two sprint attempts of fixes went on a test no product passes.
"""
from __future__ import annotations

import re

from app.acceptance import suite
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
WRONG = """import { test, expect } from '@playwright/test';
test('[AC-16] contract', async ({ request }) => {
  const created = await request.post('/notes', { data: { title: 'Valid', body: 'body' } });
  expect(created.status()).toBe(201);
  const verify = await request.get(`/notes/${created.body.id}`);
  expect(verify.status()).toBe(200);
});
"""
RIGHT = """import { test, expect } from '@playwright/test';
test('[AC-16] contract', async ({ request }) => {
  const created = await request.post('/notes', { data: { title: 'Valid', body: 'body' } });
  const id = (await created.json()).id;
  const raw = await created.body();
  expect(raw.length).toBeGreaterThan(0);
});
"""


def _suite(tmp_path, text):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "api.spec.js").write_text(text)
    return tmp_path


def test_a_body_field_read_is_found_with_its_correction(tmp_path):
    [found] = suite.responses_read_without_the_call(_suite(tmp_path, WRONG))
    assert "line(s) 5" in found and "`.body.<field>`" in found and "(await created.json()).id" in found
    assert not BANNED.search(found)


def test_the_parsed_answer_and_a_called_body_are_left(tmp_path):
    assert suite.responses_read_without_the_call(_suite(tmp_path, RIGHT)) == []
