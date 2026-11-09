"""A suite repair may remove a test that was only a skipped stub, and may not turn a kept test into one.

Measured on one run: a repair was refused for removing tests it was not sent
for, and wrote those tests back as `test.skip('[AC-n] ...', async () => {})`
with empty bodies: the names stayed, the checks were gone, and the suite was
locked. Sent back for the stubs, every rewrite of the file was refused again
for removing them, and QA wrote three new files of tests beside it instead.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.acceptance import suite
from app.tools.repository import RepositoryToolError, write_approved_artifact

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
FILE = "notes-api/acceptance/api.spec.js"
HEALTH = "test('[AC-14] health', async ({ request }) => {\n  expect((await request.get('/health')).ok()).toBe(true);\n});\n"
CREATE = "test('[AC-1] creates a note', async ({ request }) => {\n  expect((await request.post('/notes')).status()).toBe(201);\n});\n"
STUB = "test.skip('[AC-4] updates a note', async ({ request }) => {});\n"


def _reopened(root: Path, locked: str) -> Path:
    (root / ".harness").mkdir()
    (root / ".harness" / "acceptance.json").write_text(json.dumps({"project": "notes-api", "acceptance_dir": "acceptance"}))
    (root / "notes-api" / "acceptance").mkdir(parents=True)
    (root / FILE).write_text(locked)
    suite.lock(root)
    suite.unlock(root)
    suite.repairing(root, ["[AC-14] health"])
    return root


def test_a_skipped_stub_may_be_written_out_of_the_file(tmp_path: Path):
    root = _reopened(tmp_path, HEALTH + CREATE + STUB)

    write_approved_artifact(root, FILE, HEALTH + CREATE, by_the_workflow=True)

    assert "test.skip" not in (root / FILE).read_text()


def test_a_kept_test_turned_into_a_skipped_stub_is_refused_as_removed(tmp_path: Path):
    root = _reopened(tmp_path, HEALTH + CREATE)
    gutted = HEALTH + "test.skip('[AC-1] creates a note', async ({ request }) => {});\n"

    with pytest.raises(RepositoryToolError) as refused:
        write_approved_artifact(root, FILE, gutted, by_the_workflow=True)

    message = str(refused.value)
    assert "remove 1 test(s)" in message and "[AC-1] creates a note" in message
    assert not BANNED.search(message)
    assert (root / FILE).read_text() == HEALTH + CREATE
