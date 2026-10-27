"""A restart test that sends nothing to the service it restarts cannot pass, and the guide loads the helper as the file does.

Measured on one run: the restart test wrote its record through the `request` fixture - the suite's own server - then
started a service on a fresh folder, stopped it, started a second on that folder and read the record from it: 404 on
every product, the only acceptance test left failing. The guide had shown only `require('./service.cjs')`, and QA
wrote it inside a test of a file Node loads as an ES module.
"""
from __future__ import annotations

import inspect
import re

from app.acceptance import suite
from app.stacks import contract, pack_named
from app.stacks.packs import _service

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

WRONG = """import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';
test('[AC-6] notes persist after restarting the server', async ({ request }) => {
  const firstRes = await request.post('/notes', { data: { title: 'Persist', body: 'Data' } });
  const id = (await firstRes.json()).id;
  const service1 = await startService();
  await service1.stop();
  const service2 = await startService({ dataDir: service1.dataDir });
  const resp = await fetch(service2.baseURL + `/notes/${id}`);
  expect(resp.status).toBe(200);
  await service2.stop();
});
"""
RIGHT = """import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';
test('[AC-6] notes persist', async ({ request }) => {
  const first = await startService();
  const made = await request.post(first.baseURL + '/notes', { data: { title: 'a', body: 'b' } });
  await first.stop();
  const second = await startService({ dataDir: first.dataDir });
  expect((await request.get(second.baseURL + '/notes')).status()).toBe(200);
  await second.stop();
});
"""


def _suite(tmp_path, text):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "notes.spec.js").write_text(text)
    return tmp_path


def test_a_restart_on_a_folder_nothing_was_written_to_is_found(tmp_path):
    [found] = suite.tests_that_restart_on_data_they_never_wrote(_suite(tmp_path, WRONG))
    assert "line 6" in found and "`service1.baseURL` is not used" in found and "notes.spec.js" in found
    assert not BANNED.search(found)


def test_a_restart_test_that_writes_to_the_service_it_restarts_is_left(tmp_path):
    assert suite.tests_that_restart_on_data_they_never_wrote(_suite(tmp_path, RIGHT)) == []


def test_it_is_among_the_tests_that_cannot_pass():
    assert "tests_that_restart_on_data_they_never_wrote(repo_root)" in inspect.getsource(suite.tests_that_cannot_pass)


def test_the_guide_loads_the_helper_as_the_file_loads_its_other_modules():
    guide = _service.RESTART_GUIDE
    assert "import { startService } from './service.cjs';" in guide
    assert guide.index("import { startService }") < guide.index("require('./service.cjs')")
    assert not BANNED.search(guide)
