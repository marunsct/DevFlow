"""A test that reads the server's data-directory variable in the test process cannot pass.

Measured on one run: a restart test wrote through `request`, then started a service on `process.env.DATA_DIR` and read
`[]`; the suite gives `DATA_DIR` only to the server it starts, so the service began on a fresh folder on every product.
"""
from __future__ import annotations

import re

from app.acceptance import suite
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

WRONG = """import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';
test('[AC-6] notes survive a restart', async ({ request }) => {
  await request.post('/notes', { data: { title: 'a', body: 'b' } });
  const second = await startService({ dataDir: process.env.DATA_DIR });
  const res = await request.get(second.baseURL + '/notes');
  expect((await res.json()).length).toBe(1);
  await second.stop();
});
"""


def _suite(tmp_path, pack, text):
    contract.write(tmp_path, pack_named(pack), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "crud.spec.js").write_text(text)
    return tmp_path


def test_a_read_of_the_data_directory_variable_is_found(tmp_path):
    [found] = suite.reads_of_what_the_test_does_not_have(_suite(tmp_path, "node-hono-native-api", WRONG))
    assert "line(s) 5" in found and "process.env.DATA_DIR" in found and "first.dataDir" in found
    assert not BANNED.search(found)


def test_a_pack_without_a_data_directory_variable_is_not_checked_for_it(tmp_path):
    assert suite.reads_of_what_the_test_does_not_have(_suite(tmp_path, "browser-javascript", WRONG)) == []


EXPLAINED = """import { test, expect } from '@playwright/test';
// This file replaces the runner probe that read `process.env.DATA_DIR` and `process.env.PORT`, which no test
// can have: the suite gives them only to the server it starts. A test reaches the product through `request`,
// and `request.baseURL` is undefined, so none of them is read here.
/* A block comment may name `process.env.DATA_DIR` too. */
test('[AC-1] lists', async ({ request }) => {
  expect((await request.get('/notes')).status()).toBe(200);
});
"""


def test_a_comment_that_names_the_variable_is_not_a_read_of_it(tmp_path):
    """Measured on a held-out run: QA replaced a flagged probe with a test whose comment explained why the probe was
    wrong, and the check read the comment as code, sending the suite back again for the explanation."""
    assert suite.reads_of_what_the_test_does_not_have(_suite(tmp_path, "node-hono-native-api", EXPLAINED)) == []
