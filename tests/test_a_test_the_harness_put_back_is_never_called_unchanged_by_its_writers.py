"""A test the writers changed and the harness then put back is never sent back as one the writers left unchanged.

Measured on one run: a repair left the suite worse, the harness put back the suite as locked - and with it three
rewritten tests - and the send-back said the repair "has not changed" those three; QA redid the work for about ten
minutes. The send-back says the harness undid the change, and names each test to repair again.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from app.acceptance import junit, suite
from workflow_nodes import an_acceptance_review_measured

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
HEAD = "const { test, expect } = require('@playwright/test');\n"
A = "\ntest('[AC-1] a', async ({ request }) => {\n  expect(await request.get('/x')).toBe(2);\n});\n"
A_CHANGED = "\ntest('[AC-1] a', async ({ request }) => {\n  expect((await request.get('/notes')).status()).toBe(200);\n});\n"
B = "\ntest('[AC-2] b', async ({ request }) => {\n  expect((await request.get('/notes/1')).status()).toBe(200);\n});\n"
C = "\ntest('[AC-3] c', async ({ request }) => {\n  expect((await request.delete('/notes/1')).status()).toBe(204);\n});\n"
LOCKED = HEAD + A + B + C
#: The writers' change: the test under repair changed, and another test dropped, so the suite runs fewer.
WORSE = HEAD + A_CHANGED + B
SENT_BACK = SimpleNamespace(approved=False, findings=["The test `[AC-2] b` asserts only the status; assert the note too."])


def _measured(root, **kwargs):
    """The suite's run in the sandbox: every test in the file, `[AC-2] b` alone passing."""
    titles = re.findall(r"test\('([^']+)'", Path(root, "notes", "acceptance", "notes.spec.js").read_text())
    return suite.AcceptanceResult(ran=True, exit_code=1, report=junit.Report(found=True, tests=[
        junit.TestResult(name=title, outcome="passed" if title == "[AC-2] b" else "failed",
                         message="" if title == "[AC-2] b" else "expected 200, received 500") for title in titles]))


def _reviewed_after_a_worse_repair(tmp_path) -> dict:
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "notes.spec.js").write_text(LOCKED)
    (tmp_path / ".project-directory").write_text("notes\n")
    suite.lock(tmp_path)
    (tmp_path / suite.RESULT_FILE).write_text(json.dumps({"ran": True, "passed": 1, "failed": 2}))
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["[AC-1] a"])
    return an_acceptance_review_measured(tmp_path, _measured, files={"notes.spec.js": WORSE}, reviews=(SENT_BACK,),
                                         state={"acceptance_round": 1})


def test_a_test_the_harness_put_back_is_not_sent_back_as_unchanged(tmp_path):
    update = _reviewed_after_a_worse_repair(tmp_path)

    assert (tmp_path / "notes" / "acceptance" / "notes.spec.js").read_text() == LOCKED
    assert not [item for item in update["acceptance_feedback"] if "has not changed" in item]


def test_the_send_back_names_the_test_whose_change_the_harness_undid(tmp_path):
    update = _reviewed_after_a_worse_repair(tmp_path)

    told = next(item for item in update["acceptance_feedback"] if "put-back" in item)
    assert "`[AC-1] a`" in told and "undone by the harness" in told
    assert not BANNED.search(told)


def test_a_test_the_writers_never_changed_is_still_sent_back_as_unchanged(tmp_path):
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "notes.spec.js").write_text(LOCKED)
    (tmp_path / ".project-directory").write_text("notes\n")
    suite.lock(tmp_path)
    (tmp_path / suite.RESULT_FILE).write_text(json.dumps({"ran": True, "passed": 1, "failed": 2}))
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["[AC-1] a"])

    update = an_acceptance_review_measured(tmp_path, _measured, files={"notes.spec.js": HEAD + A + B + C + "\n"},
                                           reviews=(SENT_BACK,), state={"acceptance_round": 1})

    assert [item for item in update["acceptance_feedback"] if "`[AC-1] a`" in item and "has not changed" in item]
