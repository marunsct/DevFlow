"""A page test that filters records by `/^text$/` matches none that hold a control, on every product.

Measured on one run: a test rewritten by a dispute used `/^Filter test active$/`; each record's text also held its
controls' names, the filter matched nothing on a page showing that record, and the run went on to fix the product.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import suite

PAGE = suite._PAGE_MARK + "- listitem: Filter test active Done Edit Delete\n"
STALE = ("Error: expect(locator).toBeVisible() failed\n Locator: getByRole('listitem').filter({ hasText: /^Filter test "
         "active$/ })\n Expected: visible\n Error: element(s) not found" + PAGE)


def _result(message):
    return SimpleNamespace(ran=True, report=SimpleNamespace(tests=[
        SimpleNamespace(name="[AC-5] filters show the right records", outcome="failed", message=message)]))


def test_an_anchored_filter_on_a_shown_record_is_the_test_s_own_code(tmp_path):
    [found] = suite.tests_that_match_a_record_by_its_whole_text(tmp_path, _result(STALE))
    assert "/^Filter test active$/" in found and "[AC-5]" in found


def test_a_record_the_page_does_not_show_is_the_product_s(tmp_path):
    message = STALE.replace("Filter test active Done", "Other record Done")
    assert suite.tests_that_match_a_record_by_its_whole_text(tmp_path, _result(message)) == []


def test_the_one_list_every_caller_reads_carries_it(tmp_path):
    found = suite.tests_that_cannot_pass(tmp_path, _result(STALE))

    assert any("/^Filter test active$/" in item and "[AC-5]" in item for item in found)
