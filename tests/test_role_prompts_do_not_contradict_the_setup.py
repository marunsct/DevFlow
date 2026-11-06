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
