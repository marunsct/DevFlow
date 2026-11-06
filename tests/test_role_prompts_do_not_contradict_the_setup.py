"""Role prompts say what is true of the setup, and no rule a role is given cancels another it is given.

From a review of every role's prompt (2026-11-06): the suite writer was told both that the service's data is shared
by every test and that each test runs against a product that holds no data (the reviewer only the second), the
cause of tests that count a shared table; two read-only roles were told to write "through the approved artifact
tool" they do not have; and the scope rule said there is no browser and no screenshot while the page is opened in a
real browser and screenshotted.
"""
import inspect
import re

from app.acceptance import requests
from app.agents import acceptance_reviewer, milestone_reviewer, scope_discipline, scrum_master


def test_no_role_is_told_the_product_holds_no_data():
    for text in (inspect.getsource(requests), inspect.getsource(acceptance_reviewer)):
        assert "holds no data" not in text
    for text in (requests.TESTS_ASSUME_ONLY_WHAT_THEY_MADE, acceptance_reviewer.TESTS_ASSUME_ONLY_WHAT_THEY_MADE):
        assert "creates first" in text and "never counts" in text
        assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", text, re.I)


def test_read_only_roles_are_not_sent_to_a_write_tool():
    for module in (scrum_master, milestone_reviewer):
        assert "through the approved artifact tool" not in inspect.getsource(module)


def test_the_scope_rule_does_not_deny_the_browser():
    text = inspect.getsource(scope_discipline)
    assert "no\n  browser" not in text and "no browser" not in text and '"no screenshot"' not in text


def test_a_test_round_and_the_testing_rule_agree_on_installs(tmp_path):
    """The test round said "Do not install a test framework or add a dependency ... report that as a blocker", while
    the same agent's `TESTING_DEPENDENCY_RULE` says "install what the suite needs in the test-only scope"."""
    from app.agents import specialists

    text = specialists.build_test_run_request("ship notes", ["notes/app.py"], str(tmp_path))["messages"][0]["content"]
    assert "test-only scope" in text and "not a new framework" in text


def test_the_interface_role_s_test_ban_leaves_a_fix_its_regression_test():
    """A fix of a defect no test catches yet is told "You MUST also add or update a regression test", and the UI/UX
    role's prompt said "Do not write or change test files" without exception - one agent, both rules."""
    from app.agents.specialists import _ROLE_DESCRIPTIONS

    text = _ROLE_DESCRIPTIONS["ui_ux"]
    assert "Do not write or change test files: the Testing specialist owns them." not in text
    assert "in a work order" in text.lower() and "regression test" in text


def test_the_suite_writer_s_system_prompt_agrees_with_its_request():
    """The suite writer is the testing specialist, whose system prompt said to start the product, to report every
    failure as a defect and to change the function, not the test - while its request says never to start the
    product, that every test fails now and that product code is not its own."""
    from app.agents.specialists import _system_prompt
    from app.agents.testability import TESTABILITY_RULE

    writing = _system_prompt("testing", writing_the_suite=True)
    assert "build it, start it, or test it" not in writing
    assert "Report every failure as a structured defect" not in " ".join(writing.split())
    assert TESTABILITY_RULE not in writing
    assert "never start the product" in writing.lower()
    normal = _system_prompt("testing")
    assert TESTABILITY_RULE in normal and "start it, or test it" in normal


def test_no_role_is_told_it_runs_shell_commands():
    from app.agents.specialists import _system_prompt

    assert "execute shell commands" not in _system_prompt("backend")


def test_the_testability_rule_does_not_send_a_test_writer_into_another_s_file():
    """"IF A FUNCTION IS AWKWARD TO CALL, CHANGE THE FUNCTION" reached the testing specialist writing a work order's
    unit tests, whose functions are other roles' files: 29 refused writes over 30 runs (15 in one)."""
    import re as _re

    from app.agents.testability import TESTABILITY_RULE

    flat = " ".join(TESTABILITY_RULE.split())
    i = flat.index("CHANGE THE FUNCTION, NOT THE TEST")
    rule = flat[i:i + 400]
    assert "another role" in rule and "defect" in rule
    assert not _re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", rule, _re.I)
