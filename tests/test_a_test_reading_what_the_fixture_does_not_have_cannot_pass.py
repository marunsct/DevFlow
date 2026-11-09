"""A test that reads `request.baseURL`, or the server's `PORT` in the test process, cannot pass on any product.

Measured on one run: both AC-15 tests read `request.baseURL` - Playwright's request fixture has no such property, so
it is `undefined` - and one compared it with `process.env.PORT ?? '3000'`; the suite gives `PORT` only to the server
it starts, so the tests never see it. Both failed on every product and went to the product's fixers as defects.
"""
from __future__ import annotations

import re

from app.acceptance import suite
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

WRONG = """import { test, expect } from '@playwright/test';
test('[AC-15] uses PORT', async ({ request }) => {
  const baseURL = request.baseURL;
  const portEnv = process.env.PORT ?? '3000';
  expect(baseURL).toContain(`:${portEnv}`);
});
"""
RIGHT = """import { test, expect } from '@playwright/test';
test('[AC-15] listens on 127.0.0.1', async ({ request, baseURL }) => {
  expect(baseURL.startsWith('http://127.0.0.1:')).toBeTruthy();
  expect((await request.get('/health')).status()).toBe(200);
});
"""


def _suite(tmp_path, text):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "start.spec.js").write_text(text)
    return tmp_path


def test_both_are_found_with_their_lines(tmp_path):
    found = suite.reads_of_what_the_test_does_not_have(_suite(tmp_path, WRONG))
    assert len(found) == 2
    assert any("line(s) 3" in item and "`baseURL`" in item for item in found)
    assert any("line(s) 4" in item and "PORT" in item for item in found)
    for item in found:
        assert not BANNED.search(item)


def test_the_baseurl_argument_is_left_alone(tmp_path):
    assert suite.reads_of_what_the_test_does_not_have(_suite(tmp_path, RIGHT)) == []


def test_it_is_one_of_the_checks_that_reopen_a_locked_suite():
    import inspect

    assert "reads_of_what_the_test_does_not_have(repo_root)" in inspect.getsource(suite.tests_that_cannot_pass)
