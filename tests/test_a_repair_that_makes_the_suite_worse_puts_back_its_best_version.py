"""A repair that leaves a locked suite worse puts back the repair's best measured version, not the lock.

Measured on one run: a dispute reopened the suite for three tests, the harness's own rewrite changed six and the suite
measured 57 of 62 passing where the lock had 52. QA's next change measured worse, the suite as locked came back, the
six rewrites were lost, and the six tests went back for repair as "not changed"; measured again, 52 of 62.
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
BROKEN_A = "\ntest('[AC-1] a', async ({ request }) => {\n  expect(await request.get('/x')).toBe(2);\n});\n"
REWRITTEN_A = "\ntest('[AC-1] a', async ({ request }) => {\n  expect((await request.get('/notes')).status()).toBe(200);\n});\n"
WORSE_A = "\ntest('[AC-1] a', async ({ request }) => {\n  expect((await request.get('/nothing')).status()).toBe(201);\n});\n"
B = "\ntest('[AC-2] b', async ({ request }) => {\n  expect((await request.get('/notes/1')).status()).toBe(200);\n});\n"
C = "\ntest('[AC-3] c', async ({ request }) => {\n  expect((await request.delete('/notes/1')).status()).toBe(204);\n});\n"
LOCKED = HEAD + BROKEN_A + B + C
REWRITTEN = HEAD + REWRITTEN_A + B + C
#: QA's later change: the test under repair made wrong again, and a test dropped.
WORSE = HEAD + WORSE_A + B
SENT_BACK = SimpleNamespace(approved=False, findings=["The test `[AC-2] b` asserts only the status; assert the note too."])


def _measured(passing: dict[str, set[str]]):
    """The suite's run in the sandbox: the tests in the file, passing as `passing` says for that version of it."""
    def run(root, **kwargs):
        text = Path(root, "notes", "acceptance", "notes.spec.js").read_text()
        titles = re.findall(r"test\('([^']+)'", text)
        passed = passing.get(text, set())
        return suite.AcceptanceResult(ran=True, exit_code=1, report=junit.Report(found=True, tests=[
            junit.TestResult(name=title, outcome="passed" if title in passed else "failed", message="" if title in passed
                             else "expected 200, received 500") for title in titles]))
    return run


def _reopened(tmp_path, before: dict) -> None:
    """The suite locked as `LOCKED`, measured `before`, and reopened for `[AC-1] a`."""
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "notes.spec.js").write_text(LOCKED)
    (tmp_path / ".project-directory").write_text("notes\n")
    suite.lock(tmp_path)
    (tmp_path / suite.RESULT_FILE).write_text(json.dumps({"ran": True, **before}))
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["[AC-1] a"])


def _reviewed(tmp_path, text: str, measured, review_round: int) -> dict:
    return an_acceptance_review_measured(tmp_path, measured, files={"notes.spec.js": text},
                                         reviews=(SENT_BACK,), state={"acceptance_round": review_round})


def _ran(tests: int, passed: int) -> suite.AcceptanceResult:
    return suite.AcceptanceResult(ran=True, report=junit.Report(found=True, tests=[
        junit.TestResult(name=f"t{n}", outcome="passed" if n < passed else "failed") for n in range(tests)]))


def test_a_repair_that_makes_the_suite_worse_puts_back_the_best_measured_version_not_the_lock(tmp_path):
    _reopened(tmp_path, {"passed": 2, "failed": 1})
    measured = _measured({LOCKED: {"[AC-2] b", "[AC-3] c"}, REWRITTEN: {"[AC-1] a", "[AC-2] b", "[AC-3] c"},
                          WORSE: {"[AC-2] b"}})
    _reviewed(tmp_path, REWRITTEN, measured, 1)

    update = _reviewed(tmp_path, WORSE, measured, 2)

    assert (tmp_path / "notes" / "acceptance" / "notes.spec.js").read_text() == REWRITTEN
    told = next(item for item in update["acceptance_feedback"] if "worse" in item)
    assert "best measured version" in told and "3 test(s) and 3 passed" in told and "`[AC-1] a`" in told


def test_a_rewrite_kept_by_the_best_version_is_not_sent_back_as_unchanged(tmp_path):
    """The kept version's test still fails (the product's fault now); it is changed, so it is not "exactly as locked"."""
    _reopened(tmp_path, {"passed": 2, "failed": 1})
    measured = _measured({LOCKED: {"[AC-2] b", "[AC-3] c"}, REWRITTEN: {"[AC-2] b", "[AC-3] c"}, WORSE: {"[AC-2] b"}})
    _reviewed(tmp_path, REWRITTEN, measured, 1)

    update = _reviewed(tmp_path, WORSE, measured, 2)

    assert (tmp_path / "notes" / "acceptance" / "notes.spec.js").read_text() == REWRITTEN
    assert not [item for item in update["acceptance_feedback"] if "has not changed" in item]


def test_with_no_version_better_than_the_lock_the_suite_as_locked_comes_back(tmp_path):
    _reopened(tmp_path, {"passed": 2, "failed": 1})
    measured = _measured({LOCKED: {"[AC-2] b", "[AC-3] c"}, WORSE: {"[AC-2] b"}})

    update = _reviewed(tmp_path, WORSE, measured, 1)

    assert (tmp_path / "notes" / "acceptance" / "notes.spec.js").read_text() == LOCKED
    told = next(item for item in update["acceptance_feedback"] if "worse" in item)
    assert "as it was locked has been put back" in told


def test_a_version_that_passes_more_by_running_fewer_tests_is_never_kept_as_the_best(tmp_path):
    _reopened(tmp_path, {"passed": 2, "failed": 1})
    folder = tmp_path / "notes" / "acceptance"
    (folder / "notes.spec.js").write_text(REWRITTEN)
    suite.keep_the_best_of_the_repair(tmp_path, _ran(4, 3))
    (folder / "notes.spec.js").write_text(HEAD + REWRITTEN_A + B)
    suite.keep_the_best_of_the_repair(tmp_path, _ran(3, 3))  # passes as many, runs one test fewer
    (folder / "notes.spec.js").write_text(WORSE)

    suite.put_back_the_best_of_the_repair(tmp_path)

    assert (folder / "notes.spec.js").read_text() == REWRITTEN


def test_a_best_version_from_before_the_last_lock_never_comes_back(tmp_path):
    _reopened(tmp_path, {"passed": 2, "failed": 1})
    folder = tmp_path / "notes" / "acceptance"
    (folder / "notes.spec.js").write_text(REWRITTEN)
    suite.keep_the_best_of_the_repair(tmp_path, _ran(3, 3))
    relocked = HEAD + REWRITTEN_A + B + C.replace("204", "200")
    (folder / "notes.spec.js").write_text(relocked)
    suite.lock(tmp_path)
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["[AC-3] c"])
    (folder / "notes.spec.js").write_text(WORSE)

    suite.put_back_the_best_of_the_repair(tmp_path)

    assert (folder / "notes.spec.js").read_text() == relocked


def test_what_the_writers_are_told_of_the_version_put_back_avoids_the_banned_words(tmp_path):
    _reopened(tmp_path, {"passed": 2, "failed": 1})
    (tmp_path / "notes" / "acceptance" / "notes.spec.js").write_text(REWRITTEN)
    suite.keep_the_best_of_the_repair(tmp_path, _ran(3, 3))

    told = suite.a_repair_that_made_it_worse(tmp_path, _ran(2, 1))

    assert "best measured version" in told and not BANNED.search(told)
