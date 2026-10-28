"""A locked test that looks for values by a pattern none of the values it sent could match cannot pass.

Measured on one run: a test created `list-a-${slug}` and `list-b-${slug}`, kept the notes whose title
`startsWith(`list-${slug}-`)` and expected two; the QA lead read it twice and called it sound.
"""
from __future__ import annotations

import inspect
import re

from app.acceptance import suite
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

WRONG = """import { test, expect } from '@playwright/test';
test('[AC-2] lists', async ({ request }) => {
  const slug = Date.now();
  await request.post('/notes', { data: { title: `list-a-${slug}`, body: `body-a` } });
  await request.post('/notes', { data: { title: `list-b-${slug}`, body: `body-b` } });
  const notes = await (await request.get('/notes')).json();
  const mine = notes.filter((n) => n.title.startsWith(`list-${slug}-`));
  expect(mine.length).toBe(2);
});
"""
RIGHT = """import { test, expect } from '@playwright/test';
test('[AC-2] lists', async ({ request }) => {
  const slug = Date.now();
  await request.post('/notes', { data: { title: `list-${slug}-a`, body: 'x' } });
  await request.post('/notes', { data: { title: `list-${slug}-b`, body: 'y' } });
  const notes = await (await request.get('/notes')).json();
  expect(notes.filter((n) => n.title.startsWith(`list-${slug}-`)).length).toBe(2);
  expect(notes.filter((n) => n.title.includes(`${other}`)).length).toBe(0);
  expect(notes.find((n) => n.body === 'y')).toBeTruthy();
});
"""


def _suite(tmp_path, text):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "api.spec.js").write_text(text)
    return tmp_path


def test_a_prefix_none_of_the_sent_titles_has_is_found(tmp_path):
    found = suite.tests_that_filter_for_what_they_never_made(_suite(tmp_path, WRONG))
    assert len(found) == 1 and "line 7" in found[0] and "`list-${slug}-`" in found[0] and "`list-a-${slug}`" in found[0]
    assert not BANNED.search(found[0])


def test_matching_filters_and_free_expressions_are_left(tmp_path):
    assert suite.tests_that_filter_for_what_they_never_made(_suite(tmp_path, RIGHT)) == []


def test_every_caller_of_the_cannot_pass_list_asks_it():
    assert "tests_that_filter_for_what_they_never_made(repo_root)" in inspect.getsource(suite.tests_that_cannot_pass)
