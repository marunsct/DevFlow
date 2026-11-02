"""A failure saying an element is there and hidden points the fixer at what holds it.

Measured on one run: a list's parent section shrank to 34 pixels in a row of a flexible layout, every item in it was
squeezed to no width, and the browser reported a text as hidden. The element's own style hid nothing, and fixers read
it for two hours across five attempts.
"""
from __future__ import annotations

import re

from app.acceptance import junit, suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
HIDDEN = (
    "expect(locator).toBeVisible() failed Locator: getByText('Milk') Expected: visible Received: hidden "
    "- 10 x locator resolved to <p class=\"note\">Milk</p> - unexpected value \"hidden\""
)


def _result(*messages):
    tests = [junit.TestResult(name=f"[AC-{i}] t", outcome="failed", message=m) for i, m in enumerate(messages)]
    return suite.AcceptanceResult(ran=True, report=junit.Report(tests=tests, found=True))


def test_a_found_but_hidden_element_is_told_to_measure_its_parents():
    result = _result(HIDDEN)

    suite._with_what_may_hide_it(result)

    told = result.report.tests[0].message
    assert told.startswith(HIDDEN) and "parent" in told and "width" in told
    assert not BANNED.search(told.replace(HIDDEN, ""))


def test_an_element_that_was_not_found_is_left_alone():
    message = "expect(locator).toBeVisible() failed Expected: visible Error: element(s) not found"
    result = _result(message)

    suite._with_what_may_hide_it(result)

    assert result.report.tests[0].message == message
