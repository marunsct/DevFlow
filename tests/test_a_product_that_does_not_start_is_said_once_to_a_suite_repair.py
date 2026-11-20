"""A suite repair asked while the product does not start says so once, and a start failure is never a test's fault.

Measured on one run: right after drafting, the product did not start. The suite check found one test with a true fault
of its own (it signed in as a user it never signed up), and the repair request showed every test's failure as
"failed on setup with "Failed: The service did not start: ...". Over three repair stages the suite writer tried six
times to edit the product's database module, refused each time, while it was told the two tests it was sent for had
"not changed" - which the one-call rewrite had in fact changed.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from app.acceptance import junit, suite
from app.acceptance.criteria import Criterion
from app.acceptance.requests import build_author_request
from app.graph import rewritten_tests
from app.stacks import contract, pack_named
from app.tools import repository

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

HEAD = "import httpx\n\n\n"
NOBODY = ("def test_ac12_title_refused(base_url):\n"
          "    token = _signin(base_url, 'notinstore', 'pass123')\n"
          "    assert token\n"
          "    assert httpx.get(f'{base_url}/items').status_code == 200\n\n\n")
HEALTH = ("def test_ac1_health(base_url):\n"
          "    assert httpx.get(f'{base_url}/health').status_code == 200\n"
          "    assert httpx.get(f'{base_url}/health').json() == {'status': 'ok'}\n")
DID_NOT_START = ('failed on setup with "Failed: The service did not start:\n'
                 "INFO:     Waiting for application startup.\n"
                 '  File "/workspace/notes-api/notes_api/database.py", line 20, in init_db\n'
                 "sqlite3.OperationalError: unable to open database file\n"
                 "NameError: name 'db_path' is not defined\n")
FINDING = ("`notes-api/acceptance/test_items.py` line 5: the test signs in as `notinstore`, a user nothing in the suite "
           "creates. Create the user first, through the product as a person would, and sign in as that user.")


def _named(_finding):
    return "test_ac12_title_refused"


class _Model:
    def __init__(self, reply):
        self.reply, self.asked = reply, []

    def invoke(self, messages, **_):
        self.asked.append(messages)
        return SimpleNamespace(content=self.reply)


def _saved(root, messages: dict[str, str]):
    (root / suite.RESULT_FILE).parent.mkdir(parents=True, exist_ok=True)
    (root / suite.RESULT_FILE).write_text(json.dumps({"criteria": {
        f"AC-{n}": {"id": f"AC-{n}", "text": f"criterion {n}", "status": "failed",
                    "tests": [{"name": name, "outcome": "failed", "message": message}]}
        for n, (name, message) in enumerate(messages.items(), start=1)}}))


def _repairing(tmp_path, message: str):
    contract.write(tmp_path, pack_named("python-http-api"), "notes-api", "Notes")
    folder = tmp_path / "notes-api" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "test_items.py").write_text(HEAD + NOBODY + HEALTH)
    suite.lock(tmp_path)
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["test_ac12_title_refused"])
    _saved(tmp_path, {"test_ac12_title_refused": message, "test_ac1_health": message})
    return folder / "test_items.py"


def _asked(tmp_path) -> str:
    model = _Model("### test_ac12_title_refused\n```python\n" + NOBODY.replace("    token", "    _signup(base_url)\n    token")
                   + "```\n")
    rewritten_tests.repair(tmp_path, [FINDING], model, which_test=_named)
    return model.asked[0][1].content


def test_a_rewrite_asked_while_the_product_does_not_start_says_so_once_and_keeps_the_finding(tmp_path):
    _repairing(tmp_path, DID_NOT_START)

    prompt = _asked(tmp_path)

    assert len(re.findall(r"does not start|did not start", prompt)) == 1, prompt
    assert "builders'" in prompt and "only about the findings named" in prompt
    assert "unable to open database file" not in prompt, "the product's start trace is not shown"
    assert "test_ac1_health" not in prompt, "a test failing only because the product did not start is not offered"
    assert FINDING in prompt and "_signin(base_url, 'notinstore', 'pass123')" in prompt
    assert not BANNED.search(rewritten_tests.NOT_STARTED)


def test_a_rewrite_asked_for_a_failure_of_another_kind_shows_it_as_before(tmp_path):
    _repairing(tmp_path, "AssertionError: assert 401 == 200")

    prompt = _asked(tmp_path)

    assert "AssertionError: assert 401 == 200" in prompt and "### test_ac1_health" in prompt
    assert "builders'" not in prompt


def test_a_test_repaired_for_sharing_the_fault_is_not_sent_back_as_unchanged(tmp_path):
    """The one-call rewrite changed a sibling, and the review then said it was "exactly as it was locked"."""
    spec = _repairing(tmp_path, "NameError: name '_signin' is not defined")
    reply = ("### test_ac12_title_refused\n```python\n" + NOBODY.replace("_signin", "_login") + "```\n\n"
             "### test_ac1_health\n```python\n" + HEALTH.replace("== 200", "== 200  # kept") + "```\n")

    done = rewritten_tests.repair(tmp_path, [FINDING], _Model(reply), which_test=_named)

    assert done["tests"] == ["test_ac12_title_refused", "test_ac1_health"]
    assert "# kept" in spec.read_text()
    assert suite.tests_left_unrepaired(tmp_path) == []


def _result(message: str):
    return SimpleNamespace(report=SimpleNamespace(tests=[
        junit.TestResult(name="test_ac12_title_refused", outcome="failed", message=message),
        junit.TestResult(name="test_ac1_health", outcome="failed", message=message)]), problem="", ran=True,
        shows={})


def test_a_start_failure_alone_never_makes_a_test_one_that_cannot_pass(tmp_path):
    contract.write(tmp_path, pack_named("python-http-api"), "notes-api", "Notes")

    assert suite.tests_that_broke_themselves(tmp_path, _result(DID_NOT_START)) == []


def test_a_test_s_own_error_still_makes_it_one_that_cannot_pass(tmp_path):
    contract.write(tmp_path, pack_named("python-http-api"), "notes-api", "Notes")

    found = suite.tests_that_broke_themselves(tmp_path, _result("NameError: name '_signin' is not defined"))

    assert len(found) == 2 and "_signin" in found[0]


@pytest.mark.parametrize("message, reopens", [(DID_NOT_START, False), ("AssertionError: assert 401 == 200", True)])
def test_a_finding_read_in_a_test_reopens_the_suite_only_when_the_test_failed_for_more_than_the_start(
        tmp_path, message, reopens):
    contract.write(tmp_path, pack_named("python-http-api"), "notes-api", "Notes")
    folder = tmp_path / "notes-api" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "test_items.py").write_text(HEAD + NOBODY + HEALTH)
    suite.lock(tmp_path)
    found = suite._CannotPass([FINDING], [FINDING])

    kept = suite.findings_that_reopen(tmp_path, _result(message), found)

    assert kept == ([FINDING] if reopens else [])


def _author_request(tmp_path) -> str:
    return build_author_request(tmp_path, [Criterion(id="AC-1", text="Health answers", source="brief")],
                                feedback=[FINDING])["messages"][-1]["content"]


def test_the_suite_writer_repairing_while_the_product_does_not_start_is_told_once(tmp_path):
    _repairing(tmp_path, DID_NOT_START)

    request = _author_request(tmp_path)

    assert request.count("The product does not start at the moment") == 1
    assert "Nothing of the product's features is built yet" not in request
    assert FINDING in request
    assert not BANNED.search(__import__("app.acceptance.requests", fromlist=["x"]).THE_PRODUCT_DOES_NOT_START_YET)


def test_the_suite_writer_repairing_for_another_failure_is_asked_as_before(tmp_path):
    _repairing(tmp_path, "AssertionError: assert 401 == 200")

    assert "The product does not start at the moment" not in _author_request(tmp_path)


def test_the_suite_writer_refused_product_code_is_told_a_product_that_does_not_start_is_the_builders(
        tmp_path, monkeypatch):
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "acceptance.json").write_text(json.dumps({"project": "notes-api", "acceptance_dir": "acceptance"}))
    (tmp_path / "notes-api" / "acceptance").mkdir(parents=True)
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: "acceptance_author_0")

    refused = repository._the_harness_s_own_or_the_locked_suite(tmp_path, tmp_path / "notes-api/notes_api/database.py")

    assert "does not start is theirs to fix" in refused
    assert not BANNED.search(refused)
