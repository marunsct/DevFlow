"""What a suite repair's review says - its gaps and its decision record - is true of the version of the suite it keeps.

Suite-repair design review: after the harness put back a better version, the gaps of the worse version taken out were
still sent to the writers; and a reopened suite locked again on the harness's checks alone was recorded as approved by
the QA lead, who never read it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from app.acceptance import junit, suite
from app.acceptance.criteria import number
from workflow_nodes import an_acceptance_review_measured

HEAD = "const { test, expect } = require('@playwright/test');\n"
A = "\ntest('[AC-1] a', async ({ request }) => {\n  expect(await request.get('/x')).toBe(2);\n});\n"
B = "\ntest('[AC-2] b', async ({ request }) => {\n  expect((await request.get('/notes/1')).status()).toBe(200);\n});\n"
C = "\ntest('[AC-3] c', async ({ request }) => {\n  expect((await request.delete('/notes/1')).status()).toBe(204);\n});\n"
LOCKED = HEAD + A + B + C
#: The writers' version: the test under repair lost its criterion tag, and another test was dropped.
UNTAGGED = HEAD + A.replace("[AC-1] a", "a") + B
BRIEF = "# Brief\n## Features\n- Add a note\n- Read a note\n- Delete a note\n"
SENT_BACK = SimpleNamespace(approved=False, findings=["The test `[AC-2] b` asserts only the status; assert the note too."])


def _measured(root, **kwargs):
    """The suite's run in the sandbox: every test in the file, `[AC-2] b` alone passing."""
    titles = re.findall(r"test\('([^']+)'", Path(root, "notes", "acceptance", "notes.spec.js").read_text())
    return suite.AcceptanceResult(ran=True, exit_code=1, report=junit.Report(found=True, tests=[
        junit.TestResult(name=title, outcome="passed" if title == "[AC-2] b" else "failed",
                         message="" if title == "[AC-2] b" else "expected 200, received 500") for title in titles]))


def _reopened(tmp_path, locked: str, sent: str) -> None:
    (tmp_path / ".project-directory").write_text("notes\n")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "notes.spec.js").write_text(locked)
    suite.save_criteria(tmp_path, number(BRIEF))
    suite.lock(tmp_path)
    (tmp_path / suite.RESULT_FILE).write_text(json.dumps({"ran": True, "passed": 1, "failed": 2}))
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, [sent])


def test_a_gap_only_the_worse_version_had_is_not_sent_after_the_put_back(tmp_path):
    _reopened(tmp_path, LOCKED, "[AC-1] a")

    update = an_acceptance_review_measured(tmp_path, _measured, files={"notes.spec.js": UNTAGGED},
                                           reviews=(SENT_BACK,), state={"acceptance_round": 1})

    assert (tmp_path / "notes" / "acceptance" / "notes.spec.js").read_text() == LOCKED
    assert not [item for item in update["acceptance_feedback"] if "has no test whose name carries" in item]
    assert not [item for item in update["acceptance_feedback"] if "has not changed" in item]


def test_a_suite_locked_again_on_the_harness_s_checks_is_not_recorded_as_approved_by_the_qa_lead(tmp_path, monkeypatch):
    monkeypatch.setenv("TARGETED_SUITE_REPAIR", "on")
    _reopened(tmp_path, LOCKED, "[AC-1] a")
    repaired = LOCKED.replace("expect(await request.get('/x')).toBe(2);",
                              "expect((await request.get('/notes')).status()).toBe(200);")

    update = an_acceptance_review_measured(tmp_path, _measured, files={"notes.spec.js": repaired},
                                           state={"acceptance_round": 1})

    assert suite.is_locked(tmp_path)
    rationale = update["decisions"][-1]["rationale"]
    assert "QA lead approved" not in rationale and "harness's checks" in rationale
