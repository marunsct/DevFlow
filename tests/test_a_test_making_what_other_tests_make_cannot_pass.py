"""A failing test the service answered 409, making its record with a value other tests make theirs with, cannot pass.

Measured on one run: 40 calls signed up "alice" against one shared service; 24 of 48 locked tests failed
`assert 409 == 201`, and the dispute's rulings on them were refused.
"""
import inspect
import re
from types import SimpleNamespace

from app.acceptance import suite
from tests.test_whitespace_is_tested_with_more_than_a_space import _a_suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SUITE = '''
def test_ac9_signup_success(base_url):
    resp = signup(base_url, "alice", "secret")
    assert resp.status_code == 201


def test_ac11_items_no_auth(base_url):
    signup(base_url, "alice", "secret")
    assert get_items(base_url).status_code == 401


def test_ac9_signup_unique(base_url):
    resp = signup(base_url, "carol_unique", "secret")
    assert resp.status_code == 201
'''


def _failed(name, message):
    return SimpleNamespace(ran=True, report=SimpleNamespace(found=True, tests=[
        SimpleNamespace(name=name, outcome="failed", message=message)]))


def test_a_409_on_a_value_others_use_is_named(tmp_path):
    _a_suite(tmp_path, SUITE)
    [found] = suite.tests_that_make_what_other_tests_make(tmp_path, _failed("test_ac9_signup_success", "assert 409 == 201"))
    assert found.startswith("`test_ac9_signup_success` makes its record with 'alice'") and not BANNED.search(found)


def test_a_value_of_its_own_or_another_failure_is_not(tmp_path):
    _a_suite(tmp_path, SUITE)
    assert suite.tests_that_make_what_other_tests_make(tmp_path, _failed("test_ac9_signup_unique", "assert 409 == 201")) == []
    assert suite.tests_that_make_what_other_tests_make(tmp_path, _failed("test_ac9_signup_success", "assert 500 == 201")) == []


def test_it_is_one_of_the_cannot_pass_checks():
    assert "tests_that_make_what_other_tests_make(repo_root, result)" in inspect.getsource(suite.tests_that_cannot_pass)
