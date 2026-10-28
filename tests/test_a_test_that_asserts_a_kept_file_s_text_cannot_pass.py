"""A locked test that reads a file the harness keeps and asserts its text cannot pass on any product.

Measured on one run: a test read `./start.sh` and expected it to match `/DATA_DIR/`; the harness's start file reads
nothing but its service and is put back before every run, so the test failed on every product and no fixer could
reach it.
"""
from __future__ import annotations

import inspect
import re

from app.acceptance import suite
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

WRONG = """import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
test('[AC-15] start.sh exists and contains expected commands', async () => {
  const content = await fs.readFile('./start.sh', 'utf8');
  expect(content).toContain('node src/main.ts');
  expect(content).toMatch(/DATA_DIR/);
});
test('[AC-1] creates', async ({ request }) => {
  expect((await request.post('/notes', { data: { title: 'a', body: 'b' } })).status()).toBe(201);
});
"""
RIGHT = """import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
test('[AC-6] data is written under DATA_DIR', async ({ request }) => {
  await request.post('/notes', { data: { title: 'a', body: 'b' } });
  const kept = await fs.readFile(process.env.DATA_DIR + '/notes.json', 'utf8');
  expect(kept).toContain('"a"');
});
"""


def _suite(tmp_path, text):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "a.spec.js").write_text(text)
    return tmp_path


def test_a_read_of_the_kept_start_file_with_an_assertion_is_found(tmp_path):
    [found] = suite.tests_that_assert_a_kept_file_s_text(_suite(tmp_path, WRONG))
    assert "line 3" in found and "`start.sh`" in found and "cannot pass on any product" in found
    assert not BANNED.search(found)


def test_a_read_of_a_product_file_is_left(tmp_path):
    assert suite.tests_that_assert_a_kept_file_s_text(_suite(tmp_path, RIGHT)) == []


def test_it_is_among_the_tests_that_cannot_pass():
    assert "tests_that_assert_a_kept_file_s_text(repo_root)" in inspect.getsource(suite.tests_that_cannot_pass)
