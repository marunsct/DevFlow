"""A repair that rewrites a test it was not sent for has that test put back as it was locked, before the review reads it.

Measured over the runs that lost a hidden test after a dispute: in 3 of 4, the repair after the ruling also rewrote
tests no ruling named, loosened to what the product did (an exact name made a pattern, a link found by its text made
any link), and the hidden tests of those behaviours failed.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import suite
from app.stacks import contract, pack_named

HEAD = "import { test, expect } from '@playwright/test';\n\n"
CALLED_WRONG = "test('[AC-2] counts', async ({ page }) => {\n  expect(await count()).toBe(3);\n});\n\n"
RIGHT = "test('[AC-5] names', async ({ page }) => {\n  await page.getByRole('button', { name: 'All', exact: true }).click();\n});\n"


def _repairing(tmp_path, names):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    spec = folder / "page.spec.js"
    spec.write_text(HEAD + CALLED_WRONG + RIGHT)
    suite.save_criteria(tmp_path, [SimpleNamespace(id="AC-2", text="It counts", source="brief"),
                                   SimpleNamespace(id="AC-5", text="Views are named", source="brief")])
    suite.lock(tmp_path)
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, names)
    return spec


def test_a_test_not_sent_for_is_put_back_and_the_one_sent_for_kept(tmp_path):
    spec = _repairing(tmp_path, ["[AC-2] counts"])
    loosened = RIGHT.replace("{ name: 'All', exact: true }", "{ name: /^All/ }")
    spec.write_text(HEAD + CALLED_WRONG.replace("toBe(3)", "toBe(2)") + loosened)

    assert suite.put_back_tests_the_repair_was_not_sent_for(tmp_path) == ["[AC-5] names"]
    text = spec.read_text()
    assert "toBe(2)" in text and "exact: true" in text and "/^All/" not in text


def test_nothing_changes_outside_a_repair(tmp_path):
    spec = _repairing(tmp_path, ["[AC-2] counts"])
    suite.lock(tmp_path)
    spec.write_text(HEAD + CALLED_WRONG + RIGHT.replace("exact: true", "exact: false"))
    assert suite.put_back_tests_the_repair_was_not_sent_for(tmp_path) == []


def test_the_review_puts_them_back_before_it_reads_the_suite():
    import inspect

    from app.graph import acceptance_nodes

    source = inspect.getsource(acceptance_nodes._the_repair_measured)
    assert source.index("put_back_tests_the_repair_was_not_sent_for") < source.index("problems = suite.gaps(root)")
    review = inspect.getsource(acceptance_nodes.acceptance_review)
    assert review.index("_the_repair_measured(root)") < review.index("suite.put_back_the_suite_before_the_repair")


BROKEN = ("test('[AC-7] isolated', async ({ page }) => {\n  const id = await made(page.request, 'x');\n"
          "  expect(await count(id)).toBe(1);\n});\n")


def _failed_last(tmp_path, title, message):
    import json

    path = tmp_path / suite.RESULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"criteria": {"AC-7": {"id": "AC-7", "tests": [
        {"name": title, "outcome": "failed", "message": message}]}}}))


def test_a_test_that_failed_on_its_own_code_keeps_a_mend_that_keeps_its_assertions(tmp_path):
    spec = _repairing(tmp_path, ["[AC-2] counts"])
    spec.write_text(HEAD + CALLED_WRONG + RIGHT + "\n" + BROKEN)
    suite.lock(tmp_path)
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["[AC-2] counts"])
    _failed_last(tmp_path, "[AC-7] isolated",
                 "TypeError: Cannot read properties of undefined (reading 'post')\n    at made (acceptance/page.spec.js:7:3)")
    mended = BROKEN.replace("made(page.request, 'x')", "made(page, 'x')")
    spec.write_text(HEAD + CALLED_WRONG + RIGHT + "\n" + mended)

    assert suite.put_back_tests_the_repair_was_not_sent_for(tmp_path) == []
    assert "made(page, 'x')" in spec.read_text()

    # Its assertion changed too: put back, whatever it failed on.
    spec.write_text(HEAD + CALLED_WRONG + RIGHT + "\n" + mended.replace("toBe(1)", "toBeGreaterThan(0)"))
    assert suite.put_back_tests_the_repair_was_not_sent_for(tmp_path) == ["[AC-7] isolated"]

    # An assertion's failure is the product's to answer, not the test's code: put back.
    _failed_last(tmp_path, "[AC-7] isolated", "Error: expect(received).toBe(expected) at page.spec.js:8")
    spec.write_text(HEAD + CALLED_WRONG + RIGHT + "\n" + mended)
    assert suite.put_back_tests_the_repair_was_not_sent_for(tmp_path) == ["[AC-7] isolated"]


PY_HEAD = ('from ._helpers import signup\n\n\ndef _two(base_url, a, b):\n    signup(base_url, a, "p1")\n'
           '    return 1, 2\n\n\n')
PY_SENT = 'def test_ac2_sent(base_url):\n    assert _two(base_url, "x", "y")\n\n\n'
PY_OTHER = ('def test_ac19_other(base_url):\n    one = _two(base_url, "alice", "pass1")\n'
            '    assert one != 3\n')


def _python_repairing(tmp_path):
    contract.write(tmp_path, pack_named("python-flask-api"), "api", "Api")
    folder = tmp_path / "api" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    spec = folder / "test_things.py"
    spec.write_text(PY_HEAD + PY_SENT + PY_OTHER)
    suite.save_criteria(tmp_path, [SimpleNamespace(id="AC-2", text="Two", source="brief"),
                                   SimpleNamespace(id="AC-19", text="Kept apart", source="brief")])
    suite.lock(tmp_path)
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["test_ac2_sent"])
    return spec


def test_a_test_calling_a_helper_the_repair_changed_keeps_its_mended_call(tmp_path):
    spec = _python_repairing(tmp_path)
    head = PY_HEAD.replace('def _two(base_url, a, b):\n    signup(base_url, a, "p1")',
                           'def _two(base_url, a, b):\n    signup(base_url, a, b)')
    mended = PY_OTHER.replace('_two(base_url, "alice", "pass1")', '_two(base_url, "other_alice", "other_bob")')
    spec.write_text(head + PY_SENT + mended)

    assert suite.put_back_tests_the_repair_was_not_sent_for(tmp_path) == []
    assert "other_alice" in spec.read_text()

    # Its assertion loosened as well: put back, helper or not.
    spec.write_text(head + PY_SENT + mended.replace("assert one != 3", "assert one"))
    assert suite.put_back_tests_the_repair_was_not_sent_for(tmp_path) == ["test_ac19_other"]


def test_a_test_calling_an_unchanged_helper_is_put_back(tmp_path):
    spec = _python_repairing(tmp_path)
    mended = PY_OTHER.replace('"alice"', '"other_alice"')
    spec.write_text(PY_HEAD + PY_SENT + mended)
    assert suite.put_back_tests_the_repair_was_not_sent_for(tmp_path) == ["test_ac19_other"]
