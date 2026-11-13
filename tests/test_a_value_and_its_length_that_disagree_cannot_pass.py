"""A test asserting a value equals a text and has a length that text does not have cannot pass: no value is both.

Measured on one run: `truncate("Hello, World!", 10)` was asserted to equal `"Hello, W..."` (11 characters) and to have
length 10; the dispute upheld it, two fixes of a right product were reverted, and the sprint was planned again.
"""
from __future__ import annotations

import inspect
import re

from app.acceptance import suite
from tests.test_whitespace_is_tested_with_more_than_a_space import _a_suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
PY = '''
def test_ac3_ac8_truncate_default_suffix():
    result = textkit.truncate("Hello, World!", 10)
    assert result == "Hello, W..."
    assert len(result) == 10


def test_ac3_ac8_right():
    result = textkit.truncate("Hello, World!", 10)
    assert result == "Hello, ..."
    assert len(result) == 10


def test_ac9_tab_counts_as_one():
    assert out == "a\\tb"
    assert len(out) == 3
'''
JS = '''
test('[AC-3] shortens', () => {
  const r = shorten('Hello, World!', 8);
  expect(r).toBe('Hello, >>');
  expect(r).toHaveLength(8);
});
test('[AC-3] right', () => {
  const r = shorten('Hello, World!', 8);
  expect(r).toBe('Hello>>>');
  expect(r.length).toBe(8);
});
'''


def test_a_python_value_of_the_wrong_length_is_found_and_right_ones_are_not(tmp_path):
    _a_suite(tmp_path, PY)
    found = suite.tests_whose_value_and_length_disagree(tmp_path)
    assert len(found) == 1 and found[0].startswith("`test_ac3_ac8_truncate_default_suffix` asserts `result`")
    assert "(11 characters)" in found[0] and not BANNED.search(found[0])


def test_a_javascript_value_of_the_wrong_length_is_found(tmp_path):
    _a_suite(tmp_path, "")
    (tmp_path / "lib" / "acceptance" / "shorten.spec.js").write_text(JS)
    found = suite.tests_whose_value_and_length_disagree(tmp_path)
    assert len(found) == 1 and "`[AC-3] shortens`" in found[0] and "(9 characters)" in found[0]


def test_it_is_one_of_the_checks_a_locked_test_cannot_pass_by():
    assert "tests_whose_value_and_length_disagree(repo_root)" in inspect.getsource(suite.tests_that_cannot_pass)
