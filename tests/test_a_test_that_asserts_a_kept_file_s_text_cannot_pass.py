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
    assert "tests_that_assert_a_kept_file_s_text(repo_root, result)" in inspect.getsource(suite.tests_that_cannot_pass)


def test_a_passing_read_of_the_kept_file_is_left_when_the_suite_s_result_is_known(tmp_path):
    """Measured on one run: a green suite was reopened for a passing test of the start file's text; QA spent three
    rounds and locked with it as it was. A passing test proves nothing but costs nothing; only a failing one cannot pass."""
    from types import SimpleNamespace

    root = _suite(tmp_path, WRONG)
    passing = SimpleNamespace(ran=True, report=SimpleNamespace(tests=[
        SimpleNamespace(name="[AC-15] start.sh exists and contains expected commands", outcome="passed"),
        SimpleNamespace(name="[AC-1] creates", outcome="failed")]))
    assert suite.tests_that_assert_a_kept_file_s_text(root, passing) == []
    failing = SimpleNamespace(ran=True, report=SimpleNamespace(tests=[
        SimpleNamespace(name="[AC-15] start.sh exists and contains expected commands", outcome="failed")]))
    assert len(suite.tests_that_assert_a_kept_file_s_text(root, failing)) == 1
    assert "tests_that_assert_a_kept_file_s_text(repo_root, result)" in inspect.getsource(suite.tests_that_cannot_pass)


PYTHON_WRONG = '''import httpx
from pathlib import Path


def test_ac17_start_sh_exists_and_starts_service(base_url):
    start_sh = Path(__file__).resolve().parent.parent / "start.sh"
    content = start_sh.read_text(encoding="utf-8")
    assert "DATA_DIR" in content or "data" in content.lower()
    assert httpx.get(f"{base_url}/health").status_code == 200


def test_ac1_signup(base_url):
    assert httpx.post(f"{base_url}/signup", json={"username": "a", "password": "b"}).status_code == 201
'''
PYTHON_RIGHT = '''import httpx


def test_ac6_data_survives_a_restart(base_url, service):
    httpx.post(f"{base_url}/signup", json={"username": "a", "password": "b"})
    service.restart()
    assert httpx.post(f"{base_url}/signup", json={"username": "a", "password": "b"}).status_code == 409
'''


def _python_suite(tmp_path, text):
    contract.write(tmp_path, pack_named("python-http-api"), "items", "Items")
    folder = tmp_path / "items" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "test_api.py").write_text(text)
    return tmp_path


def test_a_python_test_that_reads_the_kept_start_file_and_asserts_its_text_is_found(tmp_path):
    """Measured on a held-out run: a Python suite's test asserted that `start.sh` contained `DATA_DIR`; the check
    knew only JavaScript suites, so the test stayed locked and the last sprint was planned again three times."""
    [found] = suite.tests_that_assert_a_kept_file_s_text(_python_suite(tmp_path, PYTHON_WRONG))
    assert "`start.sh`" in found and "cannot pass on any product" in found and "line 5" in found
    assert not BANNED.search(found)


def test_a_python_test_that_only_uses_the_service_is_left(tmp_path):
    assert suite.tests_that_assert_a_kept_file_s_text(_python_suite(tmp_path, PYTHON_RIGHT)) == []


def test_a_passing_python_read_is_left_when_the_result_is_known(tmp_path):
    from types import SimpleNamespace

    root = _python_suite(tmp_path, PYTHON_WRONG)
    passing = SimpleNamespace(ran=True, report=SimpleNamespace(tests=[
        SimpleNamespace(name="test_ac17_start_sh_exists_and_starts_service", outcome="passed")]))
    failing = SimpleNamespace(ran=True, report=SimpleNamespace(tests=[
        SimpleNamespace(name="test_ac17_start_sh_exists_and_starts_service", outcome="failed")]))
    assert suite.tests_that_assert_a_kept_file_s_text(root, passing) == []
    assert len(suite.tests_that_assert_a_kept_file_s_text(root, failing)) == 1
