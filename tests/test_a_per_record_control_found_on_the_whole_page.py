"""A test that asks the whole page for a control every record has cannot pass; it goes back to the suite.

Measured on one run: the brief gave each bookmark a "Delete" control, three tests asked the whole page for it, the
runner refused with "resolved to 4 elements", and fixers went at a product that drew one per bookmark as it should.
"""
from __future__ import annotations

import re

from app.acceptance import junit, suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
EACH = 'Each bookmark is an item of a list. Each has a control named "Delete".\n'
ONCE = 'The page has a control named "Delete all".\n'
REFUSED = ('playwright._impl._errors.Error: Locator.is_visible: Error: strict mode violation: '
           'get_by_role("button", name="Delete") resolved to 4 elements: 1) <button>Delete</button>')


def _ran(*tests):
    return suite.AcceptanceResult(ran=True, report=junit.Report(tests=list(tests), found=True))


def test_a_per_record_control_asked_of_the_whole_page_is_named(tmp_path):
    result = _ran(junit.TestResult(name="test_delete_via_page", outcome="failed", message=REFUSED))
    [found] = suite.tests_finding_a_per_record_control_on_the_whole_page(tmp_path, result, EACH)
    assert "test_delete_via_page" in found and '"Delete"' in found and "found 4" in found
    assert not BANNED.search(found)


def test_a_control_the_brief_gives_the_page_once_is_the_product_s(tmp_path):
    once = REFUSED.replace('name="Delete"', 'name="Delete all"')
    result = _ran(junit.TestResult(name="test_clear", outcome="failed", message=once))
    assert suite.tests_finding_a_per_record_control_on_the_whole_page(tmp_path, result, ONCE) == []


def test_a_failure_of_another_kind_is_left_alone(tmp_path):
    result = _ran(junit.TestResult(name="test_x", outcome="failed", message="AssertionError: assert 1 == 2"))
    assert suite.tests_finding_a_per_record_control_on_the_whole_page(tmp_path, result, EACH) == []
