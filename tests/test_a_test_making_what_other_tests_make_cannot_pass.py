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


REFUSED = '''
def test_ac10_signin_success(base_url):
    signup(base_url, "alice", "secret123")
    resp = signin(base_url, "alice", "secret123")
    assert resp.status_code == 200


def test_ac19_isolation(base_url):
    signup(base_url, "alice", "pass1")
    assert signin(base_url, "alice", "pass1").status_code == 200


def test_ac11_no_auth(base_url):
    signup(base_url, "alice", "secret123")
    assert get_items(base_url).status_code == 401
'''


def test_a_refusal_after_making_a_value_another_test_makes_differently_is_named(tmp_path):
    _a_suite(tmp_path, REFUSED)
    said = "assert 401 == 200\n +  where 401 = <Response [401 UNAUTHORIZED]>.status_code"
    [found] = suite.tests_that_make_what_other_tests_make(tmp_path, _failed("test_ac10_signin_success", said))
    assert found.startswith("`test_ac10_signin_success` makes its record with 'alice'")
    assert "refused what this test presented" in found and not BANNED.search(found)


def test_a_refusal_the_test_expected_or_a_value_made_alike_is_the_product_s(tmp_path):
    _a_suite(tmp_path, REFUSED)
    # The product let in what the test expected refused: its fault, whatever the names.
    assert suite.tests_that_make_what_other_tests_make(
        tmp_path, _failed("test_ac11_no_auth", "assert 200 == 401\n +  where 200 = <Response [200 OK]>")) == []
    alike = tmp_path / "alike"
    alike.mkdir()
    _a_suite(alike, SUITE)
    # Every test makes 'alice' with the same password: a sign-in refused is not the suite's doing.
    assert suite.tests_that_make_what_other_tests_make(
        alike, _failed("test_ac9_signup_success", "assert 401 == 201")) == []


EMPTIED = '''
def test_ac12_empty_title_rejected(base_url):
    token = signin_user(base_url, "alice", "secret")
    assert create(base_url, token, "").status_code == 400
    assert list_items(base_url, token).json() == []


def test_ac4_lists(base_url):
    token = signin_user(base_url, "alice", "secret")
    create(base_url, token, "first")


def test_ac4_empty_for_a_new_account(base_url):
    token = signin_user(base_url, "zed_only", "secret")
    assert list_items(base_url, token).json() == []
'''


def test_an_empty_list_expected_under_a_shared_value_is_named(tmp_path):
    _a_suite(tmp_path, EMPTIED)
    said = "AssertionError: assert [{'done': Fal...'first'}] == []\nLeft contains 4 more items, first extra item"
    [found] = suite.tests_that_make_what_other_tests_make(tmp_path, _failed("test_ac12_empty_title_rejected", said))
    assert found.startswith("`test_ac12_empty_title_rejected` makes its record with 'alice'")
    assert "found the records other tests made" in found and not BANNED.search(found)
    # A value of its own: the records it found are the product's doing.
    assert suite.tests_that_make_what_other_tests_make(
        tmp_path, _failed("test_ac4_empty_for_a_new_account", said)) == []
