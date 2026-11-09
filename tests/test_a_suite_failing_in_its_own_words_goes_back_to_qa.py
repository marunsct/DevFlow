"""Every test failing in one sentence the suite itself raises, with the product running, is the suite's fault, not the product's.

Measured on one run: all 46 locked tests failed with one message raised by a helper of the suite, reading a second copy of
its module with empty state; no test reached the product. Only text is read here and the reports are made up: no suite runs.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from app.acceptance import junit, start_output, suite
from app.agents import suite_dispute
from app.stacks.packs import python_cli, python_http_api, python_library

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SAID = "Server not started - did the session-scoped 'server' fixture run?"
HELPER = f'''STATE = {{}}


def _request(method, path):
    """Send a request and return the response."""
    if not STATE.get("url"):
        raise RuntimeError("{SAID}")
    return call(STATE["url"], method, path)
'''
STILL_UP = f"{start_output.START_MARK} (`sh start.sh`): it was still running after 20 seconds, when it was ended. It wrote:\nup"
STOPPED = f"{start_output.START_MARK} (`sh start.sh`): it stopped by itself with exit code 1. It wrote:\nboom"


def _result(messages, passed=0, server_log=STILL_UP, problem=""):
    tests = [junit.TestResult(name=f"test_ac{i}_x", outcome="failed", message=m) for i, m in enumerate(messages)]
    tests += [junit.TestResult(name=f"test_ok{i}", outcome="passed") for i in range(passed)]
    return suite.AcceptanceResult(ran=True, report=junit.Report(tests=tests, found=True), server_log=server_log, problem=problem)


def _make(tmp_path, helper=HELPER, *, lock=True) -> Path:
    (tmp_path / ".project-directory").write_text("notes\n")
    (tmp_path / "notes" / "acceptance").mkdir(parents=True)
    (tmp_path / "notes" / "acceptance" / "conftest.py").write_text(helper)
    (tmp_path / "notes" / "acceptance" / "test_x.py").write_text("from conftest import _request\n\ndef test_ac1_x():\n    assert _request('GET', '/x').status == 200\n")
    (tmp_path / "notes" / "main.py").write_text("print('the product')\n")
    if lock:
        suite.lock(tmp_path)
    return tmp_path


def _own(root, result):
    found = suite.tests_that_cannot_pass(root, result)
    return [item for item in suite.findings_that_reopen(root, result, found) if "no test reached the product" in item]


def test_the_measured_shape_goes_back_to_qa_naming_no_product_fault(tmp_path):
    root = _make(tmp_path)
    found = _own(root, _result([f"RuntimeError: {SAID}\nconftest.py:7: RuntimeError"] * 46))
    assert len(found) == 1
    assert found[0].startswith("`notes/acceptance/conftest.py`") and SAID in found[0] and "46" in found[0]
    assert "helpers are loaded and shared" in found[0] and "without changing what any test asserts" in found[0]
    assert not BANNED.search(found[0].replace(SAID, ""))
    # The first name is the helper: no criterion is deferred for it, and the one-call rewrite leaves it to QA's loop.
    assert not junit.tags_in(found[0])


def test_it_names_the_line_raising_the_words_and_the_lines_bringing_the_helper_in(tmp_path):
    root = _make(tmp_path)
    finding = _own(root, _result([f"RuntimeError: {SAID}"] * 6))[0]
    assert "`notes/acceptance/conftest.py` at line 7 raises" in finding
    assert "`notes/acceptance/test_x.py:1: from conftest import _request`" in finding
    assert not BANNED.search(finding.replace(SAID, ""))


def test_the_lines_are_found_in_any_language_s_words_and_not_inside_a_longer_name(tmp_path):
    root = _make(tmp_path, helper=HELPER)
    acceptance = root / "notes" / "acceptance"
    (acceptance / "test_y.js").write_text(
        "const { request } = require('./conftest');\n"
        "import { other } from './conftest-two';\n"
        "// conftest is named in a comment\n"
    )
    lines = suite._the_lines_that_bring_in(root, "notes/acceptance/conftest.py")
    assert "notes/acceptance/test_y.js:1: const { request } = require('./conftest');" in lines
    assert not any("conftest-two" in line or "in a comment" in line for line in lines)


def test_when_nothing_names_the_helper_the_finding_says_so(tmp_path):
    root = _make(tmp_path)
    (root / "notes" / "acceptance" / "test_x.py").write_text("def test_ac1_x():\n    assert _request('GET', '/x').status == 200\n")
    finding = _own(root, _result([f"RuntimeError: {SAID}"] * 6))[0]
    assert "No other file of the suite names `conftest.py`." in finding


def test_many_lines_are_counted_not_all_quoted(tmp_path):
    root = _make(tmp_path)
    (root / "notes" / "acceptance" / "test_x.py").write_text("from conftest import a\n" * 11)
    finding = _own(root, _result([f"RuntimeError: {SAID}"] * 6))[0]
    assert "; and 3 more." in finding and "test_x.py:9:" not in finding


def test_a_runner_s_header_before_the_error_does_not_hide_it(tmp_path):
    root = _make(tmp_path)
    messages = [f"acceptance/x.spec.js:{i}:5 › [AC-{i}] x\n\nError: {SAID}\n    at helper (x.js:3:9)" for i in range(6)]
    assert len(_own(root, _result(messages))) == 1


@pytest.mark.parametrize("helper, message", [
    # An assertion is the test checking the product.
    ("def f(r):\n    assert r.status == 200, 'the record was never kept'\n", "AssertionError: the record was never kept"),
    ("def f(s):\n    raise AssertionError('the record was never kept')\n", "AssertionError: the record was never kept"),
    ("def f(s):\n    pytest.fail('the record was never kept')\n", "the record was never kept"),
    # A helper's words for a product really not answering, not starting or refusing.
    ("def f():\n    raise RuntimeError('the service did not answer')\n", "RuntimeError: the service did not answer"),
    ("def f():\n    raise RuntimeError('the server did not start')\n", "RuntimeError: the server did not start"),
    ("def f():\n    raise RuntimeError('sign in step failed here')\n", "RuntimeError: sign in step failed here"),
    ("def f():\n    raise RuntimeError('not started in time here')\n", "RuntimeError: not started in time here"),
    # Raised after reading what the product answered, whatever the words.
    ("def f(r):\n    if r.status != 200:\n        raise RuntimeError('the record was never kept')\n", "RuntimeError: the record was never kept"),
    # Too short to mean anything.
    ("def f():\n    raise RuntimeError('no state')\n", "RuntimeError: no state"),
    # Built from a value: not a whole literal of the suite.
    ("def f(x):\n    raise RuntimeError(f'the record {x} was never kept')\n", "RuntimeError: the record 7 was never kept"),
])
def test_what_speaks_of_the_product_is_left_alone(tmp_path, helper, message):
    root = _make(tmp_path, helper)
    assert _own(root, _result([message] * 20)) == []


def test_a_product_that_stopped_by_itself_is_the_product_s(tmp_path):
    root = _make(tmp_path)
    assert _own(root, _result([f"RuntimeError: {SAID}"] * 46, server_log=STOPPED)) == []


def test_without_the_start_s_evidence_nothing_is_said(tmp_path):
    root = _make(tmp_path)
    assert _own(root, _result([f"RuntimeError: {SAID}"] * 46, server_log="")) == []


def test_errors_the_service_logged_mean_the_product_was_reached(tmp_path):
    root = _make(tmp_path)
    assert _own(root, _result([f"RuntimeError: {SAID}"] * 46, server_log=f"Error: boom at main.py:3\n{STILL_UP}")) == []
    logged = f"RuntimeError: {SAID}\nThe service logged this while the suite ran:\nboom"
    assert _own(root, _result([logged] * 46)) == []


def test_too_few_tests_are_left_alone(tmp_path):
    root = _make(tmp_path)
    assert _own(root, _result([f"RuntimeError: {SAID}"] * 4)) == []


def test_differing_messages_are_left_alone(tmp_path):
    root = _make(tmp_path)
    assert _own(root, _result([f"RuntimeError: {SAID}"] * 45 + ["RuntimeError: something else altogether here"])) == []


def test_a_test_that_passed_reached_the_product(tmp_path):
    root = _make(tmp_path)
    assert _own(root, _result([f"RuntimeError: {SAID}"] * 45, passed=1)) == []


def test_words_the_product_also_writes_are_left_alone(tmp_path):
    root = _make(tmp_path)
    (root / "notes" / "main.py").write_text(f'print("{SAID}")\n')
    assert _own(root, _result([f"RuntimeError: {SAID}"] * 46)) == []


def test_a_report_the_run_left_in_the_project_is_not_the_product(tmp_path):
    root = _make(tmp_path)
    (root / "notes" / "results.xml").write_text(f"<testcase><failure>{SAID}</failure></testcase>")
    (root / "notes" / "test-results").mkdir()
    (root / "notes" / "test-results" / "last.txt").write_text(SAID)
    assert len(_own(root, _result([f"RuntimeError: {SAID}"] * 46))) == 1


def test_the_start_is_asked_for_this_shape_once_a_product_exists_and_not_at_a_first_lock(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(start_output, "what_it_wrote", lambda root: calls.append(root) or STILL_UP)
    message = "RuntimeError: Base address was never set by the setup"
    helper = "def f():\n    raise RuntimeError('Base address was never set by the setup')\n"

    first = _make(tmp_path, helper, lock=False)
    result = _result([message] * 46, server_log="")
    start_output.add_to(first, result)
    assert calls == [] and result.server_log == ""
    assert _own(first, result) == []

    suite.lock(first)
    start_output.add_to(first, result)
    assert len(calls) == 1 and start_output.START_MARK in result.server_log
    assert len(_own(first, result)) == 1


def test_a_repair_that_leaves_it_as_it_was_is_not_locked_on_it(tmp_path, monkeypatch):
    monkeypatch.setattr(start_output, "what_it_wrote", lambda root: STILL_UP)
    root = _make(tmp_path)
    suite.unlock(root)
    suite.repairing(root, ["notes/acceptance/conftest.py"])
    result = _result([f"RuntimeError: {SAID}"] * 46, server_log="")
    start_output.add_to(root, result)
    assert len(_own(root, result)) == 1


def test_the_dispute_is_told(tmp_path, monkeypatch):
    root = _make(tmp_path)
    saved = {"passed": 0, "problem": "", "server_log": STILL_UP, "criteria": {
        f"AC-{i}": {"tests": [{"name": f"test_ac{i}_x", "outcome": "failed", "message": f"RuntimeError: {SAID}"}]} for i in range(46)
    }}
    monkeypatch.setattr(suite, "last_result", lambda _: saved)
    told = getattr(suite, "the_suite_s_own_words_when_last_measured", lambda _: [])(root)
    assert len(told) == 1 and "no test reached the product" in told[0]

    assert "measured" in inspect.signature(suite_dispute.build_dispute_request).parameters, "the request takes no measurement"
    text = suite_dispute.build_dispute_request([("t", "AC-1: x", "m")], "code", "brief", measured=told)["messages"][0]["content"]
    assert "no test reached the product" in text and "not only on what they assert" in text
    plain = suite_dispute.build_dispute_request([("t", "AC-1: x", "m")], "code", "brief")["messages"][0]["content"]
    assert "What the harness measured" not in plain
    assert not BANNED.search(text.split("--- The suite's code ---")[0].replace("AC-1: x", "").replace(SAID, ""))

    node = (Path(suite.__file__).parents[1] / "graph" / "workflow.py").read_text(encoding="utf-8")
    assert "measured=acceptance_suite.the_suite_s_own_words_when_last_measured(root)" in node


@pytest.mark.parametrize("pack", [python_http_api, python_cli, python_library])
def test_the_python_packs_say_how_to_share_a_helper(pack):
    guide = pack.ACCEPTANCE_GUIDE
    assert "never imports `conftest`" in guide
    line = next(item for item in guide.split("\n\n") if "never imports `conftest`" in item)
    assert not BANNED.search(line)
