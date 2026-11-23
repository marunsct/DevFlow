"""A field read off nothing the product's answer gave is the product's failure, not an error in the test's own code.

Measured on one run: a sign-in helper of the suite gave `body: response.ok() ? await response.json() : null`, the
product's sign-in answered not OK, and the runner said `TypeError: Cannot read properties of null (reading
'refresh_token')`. Read as the test's own code, the suite went back to its writers four times (about two hours), each
pass adding a status assertion to one test while the next threw the same error, and the product's sign-in never
reached a fixer. The tests that read the answer without asserting its status are named together, as advice, so one
repair of the file covers them all.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.stacks import contract, pack_named

SPEC = """const { test, expect } = require('@playwright/test');

async function loginUser(request, email, password) {
  const response = await request.post('/api/login', { data: { email, password } });
  return { response, body: response.ok() ? await response.json() : null };
}

test('[AC-1] sign-in gives a refresh token', async ({ request }) => {
  const { body } = await loginUser(request, 'a@example.com', 'secret12');
  expect(typeof body.refresh_token).toBe('string');
});

test('[AC-2] sign-in gives an access token', async ({ request }) => {
  const { body } = await loginUser(request, 'b@example.com', 'secret12');
  expect(typeof body.access_token).toBe('string');
});

test('[AC-3] sign-in answers 200 before its body is read', async ({ request }) => {
  const { response, body } = await loginUser(request, 'c@example.com', 'secret12');
  expect(response.status()).toBe(200);
  expect(body.user.email).toBe('c@example.com');
});

test('[AC-4] a profile lists its sessions', async ({ request }) => {
  const res = await request.get('/api/me');
  const me = await res.json();
  expect(me.sessions.length).toBe(0);
});

test('[AC-5] a record the test made itself', async ({ request }) => {
  const made = { owner: null };
  expect(made.owner.name).toBe('x');
});
"""

FRAME = """TypeError: Cannot read properties of null (reading 'refresh_token')

   8 |   const { body } = await loginUser(request, 'a@example.com', 'secret12');
>  9 |   expect(typeof body.refresh_token).toBe('string');
     |                      ^
  10 | });

    at /work/notes/acceptance/auth.spec.js:9:22
"""
NO_FRAME = "TypeError: Cannot read properties of null (reading 'refresh_token')\n"
OWN = """TypeError: Cannot read properties of null (reading 'name')

> 30 |   expect(made.owner.name).toBe('x');
     |                     ^
"""


def _root(tmp_path, pack="fullstack-page-fastapi"):
    contract.write(tmp_path, pack_named(pack), "notes", "Notes")
    (tmp_path / "notes" / "acceptance").mkdir(parents=True)
    (tmp_path / "notes" / "acceptance" / "auth.spec.js").write_text(SPEC)
    return tmp_path


def _result(name, message):
    return SimpleNamespace(ran=True, report=SimpleNamespace(found=True, tests=[
        SimpleNamespace(name=name, outcome="failed", message=message)]))


def _measured(root, failed):
    """The last measurement as the suite saves it, with `failed` (name, message) failing."""
    (root / ".harness").mkdir(exist_ok=True)
    (root / ".harness" / "acceptance-result.json").write_text(json.dumps({"ran": True, "criteria": {
        name[1:5]: {"id": name[1:5], "status": "failed",
                    "tests": [{"name": name, "outcome": "failed", "message": message}]}
        for name, message in failed}}))
    return root


@pytest.mark.parametrize("message", [FRAME, NO_FRAME], ids=["with the runner's code frame", "without it"])
def test_a_field_read_off_a_refused_sign_in_is_not_the_test_s_own_code(tmp_path, message):
    found = suite.tests_that_broke_themselves(_root(tmp_path), _result("[AC-1] sign-in gives a refresh token", message))
    assert found == []


@pytest.mark.parametrize("pack", ["fullstack-page-fastapi", "node-hono-native-api"])
def test_a_field_read_off_a_value_the_test_made_itself_is_still_the_test_s(tmp_path, pack):
    [found] = suite.tests_that_broke_themselves(_root(tmp_path, pack), _result("[AC-5] a record the test made itself", OWN))
    assert "[AC-5]" in found and "test's own code" in found


def test_the_advice_names_every_test_reading_the_answer_without_its_status(tmp_path):
    root = _measured(_root(tmp_path), [("[AC-1] sign-in gives a refresh token", FRAME)])
    names = ["[AC-1] sign-in gives a refresh token", "[AC-2] sign-in gives an access token",
             "[AC-3] sign-in answers 200 before its body is read", "[AC-4] a profile lists its sessions",
             "[AC-5] a record the test made itself"]

    named = {name for name, _ in suite.what_the_code_suggests_of(root, names)}

    assert named == {names[0], names[1], names[3]}


def test_the_advice_is_one_line_for_the_file(tmp_path):
    root = _measured(_root(tmp_path), [("[AC-1] sign-in gives a refresh token", FRAME)])
    [advice] = suite.advice_about_the_suite(root)
    assert "auth.spec.js" in advice and "status" in advice


def test_no_advice_when_no_failure_read_the_product_s_answer(tmp_path):
    root = _measured(_root(tmp_path), [("[AC-5] a record the test made itself", OWN)])
    assert suite.advice_about_the_suite(root) == []


def test_the_advice_avoids_the_banned_words(tmp_path):
    root = _measured(_root(tmp_path), [("[AC-1] sign-in gives a refresh token", FRAME)])
    [advice] = suite.advice_about_the_suite(root)
    assert not re.search(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", advice, re.I)
