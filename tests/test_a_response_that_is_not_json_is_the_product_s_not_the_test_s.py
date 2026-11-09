"""A test whose `response.json()` fails because the product answered with something other than JSON is not a broken test.

Measured on one run: the product served none of its routes, so each request was answered `404 Not Found`
as text, and `await res.json()` threw `SyntaxError: Unexpected non-whitespace character after JSON at
position 4`. The JavaScript pack read every `SyntaxError` as an error in the test's own code, reopened the
locked suite for fourteen tests, and sent QA to repair tests that were right.
"""
from __future__ import annotations

import re

import pytest

from app.stacks.packs._javascript import TEST_BUGS


def _a_test_bug(message: str) -> bool:
    return any(re.search(pattern, message, re.I | re.M) for pattern in TEST_BUGS)


@pytest.mark.parametrize("message", [
    "SyntaxError: Unexpected non-whitespace character after JSON at position 4 (line 1 column 5)",
    "SyntaxError: Unexpected token '<', \"<!DOCTYPE \"... is not valid JSON",
    "SyntaxError: Unexpected end of JSON input",
])
def test_a_body_that_is_not_json_is_not_the_test_s_bug(message: str) -> None:
    assert not _a_test_bug(message)


def test_a_syntax_error_in_the_test_s_own_code_still_is() -> None:
    assert _a_test_bug("SyntaxError: Unexpected identifier 'expect'")
    assert _a_test_bug("TypeError: res.status is not a function")


def test_a_request_nothing_answered_is_not_the_test_s_bug() -> None:
    """Measured on one run: the start-script test's `fetch` got no answer - the service it started had not come up -
    and `TypeError: fetch failed` reopened the locked suite as an error in the test's own code."""
    assert not _a_test_bug("TypeError: fetch failed")
    assert _a_test_bug("TypeError: res.status is not a function")
