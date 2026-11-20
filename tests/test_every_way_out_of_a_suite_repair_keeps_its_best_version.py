"""Every way a suite repair ends keeps the repair's best measured version when the suite now stands worse than it.

Suite-repair design review 2026-11-20: "worse" was measured against the suite before the repair only, so a version
passing fewer than the best but more than before stayed and was locked at the limit; and a repair that ran out of
rounds put back the suite as last locked even when a better version had been measured.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from app.acceptance import junit, suite
from app.graph import acceptance_nodes
from workflow_nodes import an_acceptance_review_measured

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
HEAD = "const { test, expect } = require('@playwright/test');\n"
B = "\ntest('[AC-2] b', async ({ request }) => {\n  expect((await request.get('/notes/1')).status()).toBe(200);\n});\n"
C = "\ntest('[AC-3] c', async ({ request }) => {\n  expect((await request.delete('/notes/1')).status()).toBe(204);\n});\n"


def _a(body: str) -> str:
    return f"\ntest('[AC-1] a', async ({{ request }}) => {{\n  {body}\n}});\n"


LOCKED = HEAD + _a("expect(await request.get('/x')).toBe(2);") + B + C
REWRITTEN = HEAD + _a("expect((await request.get('/notes')).status()).toBe(200);") + B + C
#: QA's later change to the test under repair: better than the lock, worse than the rewrite.
HALFWAY = HEAD + _a("expect((await request.get('/notes?all')).status()).toBe(200);") + B + C
#: A later change the suite cannot even load.
UNLOADABLE = HEAD + _a("expect((await request.get('/notes'))") + B + C
SENT_BACK = SimpleNamespace(approved=False, findings=["The test `[AC-2] b` asserts only the status; assert the note too."])


def _measured(passing: dict[str, set[str]]):
    """The suite's run in the sandbox: the tests in the file, passing as `passing` says for that version of it."""
    def run(root, **kwargs):
        text = Path(root, "notes", "acceptance", "notes.spec.js").read_text()
        if text not in passing:
            return suite.AcceptanceResult(ran=False, problem="SyntaxError: the spec file cannot load")
        titles = re.findall(r"test\('([^']+)'", text)
        return suite.AcceptanceResult(ran=True, exit_code=1, report=junit.Report(found=True, tests=[
            junit.TestResult(name=title, outcome="passed" if title in passing[text] else "failed",
                             message="" if title in passing[text] else "expected 200, received 500") for title in titles]))
    return run


MEASURED = _measured({LOCKED: {"[AC-2] b"}, REWRITTEN: {"[AC-1] a", "[AC-2] b", "[AC-3] c"},
                      HALFWAY: {"[AC-2] b", "[AC-3] c"}})


def _reopened(tmp_path) -> Path:
    """The suite locked as `LOCKED`, measured 1 of 3 passing, and reopened for `[AC-1] a`."""
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    spec = folder / "notes.spec.js"
    spec.write_text(LOCKED)
    (tmp_path / ".project-directory").write_text("notes\n")
    suite.lock(tmp_path)
    (tmp_path / suite.RESULT_FILE).write_text(json.dumps({"ran": True, "passed": 1, "failed": 2}))
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["[AC-1] a"])
    return spec


def _reviewed(tmp_path, text: str, review_round: int, **state) -> dict:
    return an_acceptance_review_measured(tmp_path, MEASURED, files={"notes.spec.js": text}, reviews=(SENT_BACK,),
                                         state={"acceptance_round": review_round, **state})


def test_a_version_better_than_before_the_repair_but_worse_than_its_best_puts_back_the_best(tmp_path):
    spec = _reopened(tmp_path)
    _reviewed(tmp_path, REWRITTEN, 1)

    update = _reviewed(tmp_path, HALFWAY, 2)

    assert spec.read_text() == REWRITTEN
    told = next(item for item in update["acceptance_feedback"] if "worse" in item)
    assert "runs 3 test(s) and 2 pass" in told and "best measured version ran 3 and 3 passed" in told
    assert not BANNED.search(told)


def test_a_repair_out_of_rounds_locks_its_best_measured_version_not_the_lock(tmp_path):
    spec = _reopened(tmp_path)
    _reviewed(tmp_path, REWRITTEN, 1)

    update = _reviewed(tmp_path, UNLOADABLE, acceptance_nodes.MAX_ACCEPTANCE_ROUNDS + 2, acceptance_return_to="release")

    assert update["stage"] == "release"
    assert suite.is_locked(tmp_path) and spec.read_text() == REWRITTEN
    assert "best measured version was kept" in update["acceptance_open_problems"][0]


def test_the_repair_s_record_holds_every_version_measured_and_which_is_the_best(tmp_path):
    from app.acceptance import suite_repair

    _reopened(tmp_path)
    _reviewed(tmp_path, REWRITTEN, 1)

    _reviewed(tmp_path, HALFWAY, 2)

    record = suite_repair.read(tmp_path)
    assert [(v["by"], v["tests"], v["passed"]) for v in record["versions"]] == [
        ("lock", 3, 1), ("writers", 3, 3), ("writers", 3, 2), ("put back", 3, 3)]
    assert record["versions"][record["best"]]["passed"] == 3
    assert list(record["sent"]) == ["[AC-1] a"]


def test_the_lock_ends_the_repair_s_record(tmp_path):
    from app.acceptance import suite_repair

    _reopened(tmp_path)
    _reviewed(tmp_path, REWRITTEN, 1)

    suite.lock(tmp_path)

    assert suite_repair.read(tmp_path) == {} and suite.the_best_of_the_repair(tmp_path) == {}
