"""A locked test that signs in as a user nothing in the suite creates cannot pass.

Measured on two runs of the held-out family: QA's tests signed in as `ac3user` through a helper and never signed
that user up. Every product answered 401, the test round raised the tests as product defects, and a fix round and a
dispute were spent before QA repaired them. In the second run seven tests had the fault.
"""
from __future__ import annotations

import inspect
import re

from app.acceptance import suite
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

HELPERS = '''import httpx


def _signup(base_url, username, password):
    return httpx.post(f"{base_url}/signup", json={"username": username, "password": password})


def _signin(base_url, username, password):
    return httpx.post(f"{base_url}/signin", json={"username": username, "password": password})

'''
WRONG = HELPERS + '''
def test_ac3_creates(base_url):
    token = _signin(base_url, "ana", "secret").json()["token"]
    assert token
'''
SIGNED_UP = HELPERS + '''
def test_ac3_creates(base_url):
    _signup(base_url, "ana", "secret")
    token = _signin(base_url, "ana", "secret").json()["token"]
    assert token
'''
UNKNOWN_ON_PURPOSE = HELPERS + '''
def test_ac10_unknown_user(base_url):
    assert _signin(base_url, "nobody", "secret").status_code == 401
'''
SEEDED = HELPERS + '''
def test_ac3_creates(base_url):
    token = _signin(base_url, "seeded", "secret").json()["token"]
    assert token
'''
CONFTEST = '''import pytest


@pytest.fixture(scope="session", autouse=True)
def seeded_user(base_url):
    import httpx
    httpx.post(f"{base_url}/users", json={"username": "seeded", "password": "secret"})
'''
JAVASCRIPT = """import { test, expect } from '@playwright/test';
async function signIn(request, username, password) {
  return request.post('/signin', { data: { username, password } });
}
test('[AC-3] lists', async ({ request }) => {
  const res = await signIn(request, 'ana', 'secret');
  expect(res.status()).toBe(200);
});
"""


def _suite(tmp_path, *files, pack="python-http-api"):
    contract.write(tmp_path, pack_named(pack), "items", "Items")
    folder = tmp_path / "items" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in files:
        (folder / name).write_text(text)
    return tmp_path


def test_a_sign_in_as_a_user_nothing_creates_is_found(tmp_path):
    [found] = suite.tests_that_sign_in_as_nobody(_suite(tmp_path, ("test_api.py", WRONG)))
    assert "signs in as `ana`" in found and "line 13" in found and "nothing in the suite creates" in found
    assert not BANNED.search(found)


def test_a_test_that_signs_the_user_up_first_is_left(tmp_path):
    assert suite.tests_that_sign_in_as_nobody(_suite(tmp_path, ("test_api.py", SIGNED_UP))) == []


def test_a_test_that_expects_the_refusal_is_left(tmp_path):
    assert suite.tests_that_sign_in_as_nobody(_suite(tmp_path, ("test_api.py", UNKNOWN_ON_PURPOSE))) == []


def test_a_user_a_fixture_creates_is_left(tmp_path):
    root = _suite(tmp_path, ("test_api.py", SEEDED), ("conftest.py", CONFTEST))
    assert suite.tests_that_sign_in_as_nobody(root) == []


def test_a_javascript_suite_is_read_too(tmp_path):
    root = _suite(tmp_path, ("api.spec.js", JAVASCRIPT), pack="node-hono-native-api")
    [found] = suite.tests_that_sign_in_as_nobody(root)
    assert "signs in as `ana`" in found


def test_it_is_among_the_tests_that_cannot_pass():
    assert "tests_that_sign_in_as_nobody(repo_root)" in inspect.getsource(suite.tests_that_cannot_pass)
