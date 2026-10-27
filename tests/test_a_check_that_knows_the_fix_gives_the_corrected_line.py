"""A check that knows the correction quotes each line it names with the line as it should read.

Measured on one run: told that two tests read `request.baseURL` and `process.env.PORT`, QA's repair fixed the first
and kept the second, and the suite's repairs were spent; the criterion shipped deferred. A check that knows the exact
correction - a call added or removed, a fixture argument used - hands it over line by line.
"""
from __future__ import annotations

import re

from app.acceptance import suite
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _suite(tmp_path, text):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "notes.spec.js").write_text(text)
    return tmp_path


def test_an_uncalled_fixture_status_is_given_with_the_call_added(tmp_path):
    root = _suite(tmp_path, "test('[AC-1] x', async ({ request }) => {\n"
                            "  const res = await request.post('/notes', { data: {} });\n"
                            "  expect(res.status).toBe(201);\n});\n")

    found = suite.responses_read_without_the_call(root)

    assert "`expect(res.status).toBe(201);` -> `expect(res.status()).toBe(201);`" in found[0]
    assert not BANNED.search(found[0])


def test_a_called_fetch_status_is_given_with_the_call_taken_away(tmp_path):
    root = _suite(tmp_path, "test('[AC-6] x', async () => {\n"
                            "  const res = await fetch(base + '/notes');\n"
                            "  expect(res.status()).toBe(200);\n});\n")

    found = suite.fetch_calls_written_like_the_fixture(root)

    assert "`expect(res.status()).toBe(200);` -> `expect(res.status).toBe(200);`" in found[0]


def test_request_baseurl_is_given_as_the_baseurl_argument(tmp_path):
    root = _suite(tmp_path, "test('[AC-15] x', async ({ request }) => {\n"
                            "  expect(request.baseURL.startsWith('http://127.0.0.1:')).toBeTruthy();\n});\n")

    found = suite.reads_of_what_the_test_does_not_have(root)

    assert "-> `expect(baseURL.startsWith('http://127.0.0.1:')).toBeTruthy();`" in found[0]
