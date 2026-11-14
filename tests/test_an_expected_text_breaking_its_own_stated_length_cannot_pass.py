"""A failing test whose own words give its result's length, where the product returned that length and the expected
text has another, was counted by hand and cannot pass a right product.

Measured on one run: `truncate("Hello, world!", 10, suffix=">>")` was expected to equal "Hello, wo>>" (11 characters)
under a docstring saying "exactly 10 chars"; the product returned "Hello, w>>", the dispute counted the slice the
test's way, and a right product was planned again.
"""
import re
from types import SimpleNamespace

from app.acceptance import suite
from tests.test_whitespace_is_tested_with_more_than_a_space import _a_suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SUITE = '''
def test_ac3_custom_suffix(tk):
    """AC-3: truncates with a custom suffix to exactly 10 chars."""
    result = tk.truncate("Hello, world!", 10, suffix=">>")
    assert result == "Hello, wo>>"


def test_ac3_default_suffix(tk):
    """AC-3: exactly 5 characters."""
    assert tk.truncate("Hello, world!", 5) == "He..."
'''


def _failed(name, message):
    return SimpleNamespace(ran=True, report=SimpleNamespace(found=True, tests=[
        SimpleNamespace(name=name, outcome="failed", message=message)]))


def test_the_hand_counted_text_is_named(tmp_path):
    _a_suite(tmp_path, SUITE)
    said = "E       AssertionError: assert 'Hello, w>>' == 'Hello, wo>>'\n\nacceptance/test_truncate.py:52"
    [found] = suite.tests_whose_expected_text_breaks_their_own_length(tmp_path, _failed("test_ac3_custom_suffix", said))
    assert found.startswith("`test_ac3_custom_suffix` says its result has exactly 10 characters")
    assert "'Hello, wo>>' (11)" in found and not BANNED.search(found)


def test_a_product_that_returned_another_length_is_the_product_s(tmp_path):
    _a_suite(tmp_path, SUITE)
    # The product returned 9 characters: the test's text has the length it states, the product is wrong.
    said = "assert 'He..' == 'He...'"
    assert suite.tests_whose_expected_text_breaks_their_own_length(tmp_path, _failed("test_ac3_default_suffix", said)) == []


def test_it_is_among_the_measured_checks():
    import inspect

    assert "tests_whose_expected_text_breaks_their_own_length(repo_root, result)" in inspect.getsource(
        suite.tests_that_cannot_pass)
