"""A locked test asserting a kept file's text is found however it names the file; one that only checks or runs it is left.

Measured on two runs of one service pack: a test held the start file's path in a variable, another named it with a
folder before it, and neither was found before the lock; fixers tried to edit the file, were refused, and rounds were
spent. And a test that only asked whether the file exists was charged as if it had read it.
"""
from __future__ import annotations

import re

import pytest

from app.acceptance import suite
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
HEAD = """import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const PROJECT_ROOT = path.resolve(__dirname, '..');
"""


def _js(tmp_path, text):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "a.spec.js").write_text(HEAD + text)
    return tmp_path


def _py(tmp_path, text):
    contract.write(tmp_path, pack_named("python-http-api"), "items", "Items")
    folder = tmp_path / "items" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "test_api.py").write_text(text)
    return tmp_path


CANNOT_PASS = {
    "the path is named in the read": """test('[AC-9] start file', async () => {
  const script = fs.readFileSync(path.join(PROJECT_ROOT, 'start.sh'), 'utf-8');
  expect(script).toMatch(/^#!\\/usr\\/bin\\/env bash/m);
  expect(script).toMatch(/PORT.*=.*3000|3000/);
});
""",
    "a variable holds the path": """test('[AC-9] start file', async () => {
  const startShPath = path.join(PROJECT_ROOT, 'start.sh');
  const content = fs.readFileSync(startShPath, 'utf-8');
  expect(content).toContain('PORT');
});
""",
    "a variable above the tests holds the path": """const startShPath = path.join(PROJECT_ROOT, 'start.sh');
test('[AC-9] start file', async () => {
  const content = fs.readFileSync(startShPath, 'utf-8');
  expect(content).toContain('PORT');
});
""",
    "the path is written across lines": """test('[AC-9] start file', async () => {
  const where = path.join(
    PROJECT_ROOT,
    'start.sh',
  );
  expect(fs.readFileSync(where, 'utf-8')).toContain('PORT');
});
""",
    "a folder comes first": """test('[AC-9] start file', async () => {
  const script = fs.readFileSync(path.resolve(__dirname, '..', 'start.sh'), 'utf-8');
  expect(script).toMatch(/PORT/);
});
""",
    "the assertion is a regular expression's test": """test('[AC-9] start file', async () => {
  const script = fs.readFileSync(path.join(PROJECT_ROOT, 'start.sh'), 'utf-8');
  expect(/PORT/.test(script)).toBe(true);
});
""",
    "the text is read before the tests": """const script = fs.readFileSync(path.join(PROJECT_ROOT, 'start.sh'), 'utf-8');
test('[AC-9] start file', async () => {
  expect(script).toMatch(/PORT/);
});
""",
    "what is asserted is made from the text": """test('[AC-9] start file', async () => {
  const script = fs.readFileSync(`${PROJECT_ROOT}/start.sh`, 'utf-8');
  const first = script.split('\\n')[0];
  expect(first).toContain('bash');
});
""",
}


@pytest.mark.parametrize("text", CANNOT_PASS.values(), ids=CANNOT_PASS.keys())
def test_a_test_asserting_the_kept_file_s_text_is_found(tmp_path, text):
    [found] = suite.tests_that_assert_a_kept_file_s_text(_js(tmp_path, text))
    assert "`start.sh`" in found and "cannot pass on any product" in found
    assert "reaching the running service" in found
    assert not BANNED.search(found)


RIGHT = {
    "it only asks that the file exists": """test('[AC-9] start file', async () => {
  const where = path.join(PROJECT_ROOT, 'start.sh');
  expect(fs.existsSync(where)).toBe(true);
});
""",
    "it only asks that the file may be run": """test('[AC-9] start file', async () => {
  const where = path.join(PROJECT_ROOT, 'start.sh');
  expect(fs.statSync(where).mode & 0o111).toBeTruthy();
  fs.accessSync(where, fs.constants.X_OK);
});
""",
    "it runs the file": """import { execSync } from 'node:child_process';
test('[AC-9] start file', async () => {
  const out = execSync(path.join(PROJECT_ROOT, 'start.sh') + ' --version');
  expect(String(out)).toContain('1');
});
""",
    "it imports the kept helper": """const { startService } = require('./service.cjs');
test('[AC-9] restart', async () => {
  const service = await startService();
  expect(service.baseURL).toBeTruthy();
});
""",
    "the file read is not one the pack keeps": """test('[AC-9] a fixture', async () => {
  const content = fs.readFileSync(path.join(PROJECT_ROOT, 'fixtures', 'start.sh'), 'utf-8');
  expect(content).toContain('PORT');
});
""",
    "another file is read under the same variable elsewhere": """test('[AC-1] one', async () => {
  const content = fs.readFileSync(process.env.DATA_DIR + '/notes.json', 'utf-8');
  expect(content).toContain('a');
});
""",
    "it reads the kept file and asserts on something else": """test('[AC-9] answers', async ({ request }) => {
  const script = fs.readFileSync(path.join(PROJECT_ROOT, 'start.sh'), 'utf-8');
  console.log(script.length);
  expect((await request.get('/health')).status()).toBe(200);
});
""",
    "the read is in a comment": """test('[AC-9] answers', async ({ request }) => {
  // const script = fs.readFileSync(path.join(PROJECT_ROOT, 'start.sh'), 'utf-8');
  // expect(script).toContain('PORT');
  expect((await request.get('/health')).status()).toBe(200);
});
""",
}


@pytest.mark.parametrize("text", RIGHT.values(), ids=RIGHT.keys())
def test_a_right_test_is_left(tmp_path, text):
    assert suite.tests_that_assert_a_kept_file_s_text(_js(tmp_path, text)) == []


def test_the_kept_names_come_from_the_pack_not_from_the_check(tmp_path):
    """Any file the pack keeps: `tsconfig.json` here, on a pack that keeps it."""
    pack = pack_named("node-hono-native-api")
    assert "tsconfig.json" in pack.kept_files
    [found] = suite.tests_that_assert_a_kept_file_s_text(_js(tmp_path, """test('[AC-9] config', async () => {
  const where = path.join(PROJECT_ROOT, 'tsconfig.json');
  expect(fs.readFileSync(where, 'utf-8')).toContain('strict');
});
"""))
    assert "`tsconfig.json`" in found


def test_a_second_test_with_the_same_variable_name_is_judged_by_its_own(tmp_path):
    text = """test('[AC-9] start file', async () => {
  const content = fs.readFileSync(path.join(PROJECT_ROOT, 'start.sh'), 'utf-8');
  expect(content).toContain('PORT');
});
test('[AC-1] reply', async ({ request }) => {
  const content = await (await request.get('/health')).text();
  expect(content).toContain('ok');
});
"""
    found = suite.tests_that_assert_a_kept_file_s_text(_js(tmp_path, text))
    assert len(found) == 1 and "line 5" in found[0]


def test_a_passing_test_is_still_left_when_the_result_is_known(tmp_path):
    from types import SimpleNamespace

    root = _js(tmp_path, CANNOT_PASS["a variable holds the path"])
    title = "[AC-9] start file"
    passing = SimpleNamespace(ran=True, report=SimpleNamespace(tests=[SimpleNamespace(name=title, outcome="passed")]))
    failing = SimpleNamespace(ran=True, report=SimpleNamespace(tests=[SimpleNamespace(name=title, outcome="failed")]))
    assert suite.tests_that_assert_a_kept_file_s_text(root, passing) == []
    assert len(suite.tests_that_assert_a_kept_file_s_text(root, failing)) == 1


def test_a_python_test_is_followed_as_well(tmp_path):
    root = _py(tmp_path, '''from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_ac9_start_file():
    with open(ROOT / "start.sh") as handle:
        content = handle.read()
    assert "PORT" in content
''')
    [found] = suite.tests_that_assert_a_kept_file_s_text(root)
    assert "`start.sh`" in found


def test_a_python_test_that_only_asks_the_file_exists_is_left(tmp_path):
    """A reply's own `.read()` beside it is not a read of the kept file."""
    root = _py(tmp_path, '''from pathlib import Path
from urllib.request import urlopen


def test_ac9_start_file(base_url):
    assert (Path(__file__).parent.parent / "start.sh").exists()
    assert b"ok" in urlopen(f"{base_url}/health").read()
''')
    assert suite.tests_that_assert_a_kept_file_s_text(root) == []
