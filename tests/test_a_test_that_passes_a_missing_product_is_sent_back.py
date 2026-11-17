"""A test that passes a product that is not there is sent back before the suite is locked (LR.23).

Measured on two larger briefs: 52 of 97 and 84 of 110 locked tests passed on the empty scaffold, most because their
assertions sat inside `if (response.ok()) { ... }`, so an answer of 404 skipped every check.
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from unittest import mock

from app.acceptance import suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _spec(tmp_path, text):
    folder = tmp_path / "acceptance"
    folder.mkdir()
    (folder / "api.spec.js").write_text(text)
    return [folder / "api.spec.js"]


def test_an_assertion_made_only_on_a_good_answer_is_named(tmp_path):
    files = _spec(tmp_path, "test('[AC-1] lists', async ({ request }) => {\n  const r = await request.get('/x');\n"
                            "  if (r.ok()) {\n    expect((await r.json()).length).toBe(0);\n  }\n});\n"
                            "test('[AC-2] adds', async ({ request }) => {\n  const r = await request.post('/x');\n"
                            "  expect(r.status()).toBe(201);\n});\n")
    with mock.patch.object(suite, "suite_files", return_value=files):
        found = suite.tests_guarded_by_the_answer(tmp_path)
    assert len(found) == 1 and "line(s) 3:" in found[0]


def test_python_guards_are_named_too(tmp_path):
    files = _spec(tmp_path, "def test_ac1(client):\n    r = client.get('/x')\n    if r.status_code == 200:\n"
                            "        assert r.json() == []\n")
    with mock.patch.object(suite, "suite_files", return_value=files):
        assert suite.tests_guarded_by_the_answer(tmp_path)


def _result(outcomes):
    tests = [SimpleNamespace(name=f"[AC-{n}] t{n}", outcome=o) for n, o in enumerate(outcomes, 1)]
    return SimpleNamespace(ran=True, report=SimpleNamespace(tests=tests))


def test_tests_passing_before_anything_is_built_are_sent_back_only_then():
    many = _result(["passed"] * 5 + ["failed"] * 5)
    assert suite.tests_that_pass_before_the_product(many, nothing_built=True)
    assert suite.tests_that_pass_before_the_product(many, nothing_built=False) == []
    assert suite.tests_that_pass_before_the_product(_result(["passed"] * 2 + ["failed"] * 8), nothing_built=True) == []
    assert suite.tests_that_pass_before_the_product(_result(["passed"] * 3 + ["failed"] * 27), nothing_built=True) == []


def test_the_review_runs_both_and_their_words_ban_the_product_s_nouns(tmp_path):
    from app.acceptance import junit
    from workflow_nodes import an_acceptance_review

    spec = "".join(f"test('[AC-{n}] reads', async ({{ request }}) => {{\n  const r = await request.get('/x');\n"
                   f"  if (r.ok()) {{\n    expect((await r.json()).length).toBe(0);\n  }}\n}});\n" for n in range(1, 6))
    every_test_passes = suite.AcceptanceResult(ran=True, exit_code=0, report=junit.Report(found=True, tests=[
        junit.TestResult(name=f"[AC-{n}] reads") for n in range(1, 6)]))

    update = an_acceptance_review(tmp_path, every_test_passes, pack="node-hono-native-api", files={"api.spec.js": spec})

    feedback = update["acceptance_feedback"]
    [guarded] = [problem for problem in feedback if "api.spec.js" in problem and "line(s) 3" in problem]
    [before] = [problem for problem in feedback if "5 of 5 test(s) pass although nothing of the product is built" in problem]
    assert update["stage"] == "acceptance_author"
    assert not BANNED.search(re.sub(r"\[AC-\d+\] reads", "", guarded + before))
