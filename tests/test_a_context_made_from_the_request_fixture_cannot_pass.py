"""A locked test that calls `newContext` on the `request` fixture cannot pass.

Measured on five runs, each in a restart test reaching the second service through
`request.newContext({ baseURL: second.baseURL })`. The fixture has no `newContext`; the call throws only after the
first service has run, so the review locked the suite and it was reopened after the first draft.
"""
from __future__ import annotations

import re

from app.acceptance import suite
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

ON_THE_FIXTURE = """import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';
test('[AC-6] notes survive a restart', async ({ request }) => {
  const first = await startService();
  await request.post(first.baseURL + '/notes', { data: { title: 'a' } });
  await first.stop();
  const second = await startService({ dataDir: first.dataDir });
  const again = await request.newContext({ baseURL: second.baseURL });
  expect((await again.get('/notes')).status()).toBe(200);
});
"""
ON_TEST = """import { test, expect } from '@playwright/test';
test('[AC-6] restart', async ({ request }) => {
  const ctx = await test.request.newContext({ baseURL: 'http://127.0.0.1:1' });
});
"""
IMPORTED = """import { test, expect, request } from '@playwright/test';
test('[AC-6] restart', async () => {
  const ctx = await request.newContext({ baseURL: 'http://127.0.0.1:1' });
  expect((await ctx.get('/notes')).status()).toBe(200);
});
"""
BY_FULL_URL = """import { test, expect } from '@playwright/test';
test('[AC-6] restart', async ({ request }) => {
  expect((await request.get(second.baseURL + '/notes')).status()).toBe(200);
});
"""


def _suite(tmp_path, text):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "api.spec.js").write_text(text)
    return tmp_path


def test_a_context_made_from_the_fixture_is_found_with_its_correction(tmp_path):
    found = suite.contexts_made_from_the_fixture(_suite(tmp_path, ON_THE_FIXTURE))
    assert len(found) == 1 and "line(s) 8" in found[0] and "baseURL + '/items'" in found[0]
    assert not BANNED.search(found[0])


def test_test_request_new_context_is_found(tmp_path):
    assert len(suite.contexts_made_from_the_fixture(_suite(tmp_path, ON_TEST))) == 1


def test_the_imported_request_and_full_urls_are_left(tmp_path):
    assert suite.contexts_made_from_the_fixture(_suite(tmp_path, IMPORTED)) == []
    assert suite.contexts_made_from_the_fixture(_suite(tmp_path, BY_FULL_URL)) == []


def test_every_caller_of_the_cannot_pass_list_asks_it():
    import inspect

    assert "contexts_made_from_the_fixture(repo_root)" in inspect.getsource(suite.tests_that_cannot_pass)
