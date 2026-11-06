"""A test whose matcher received a promise turned to text compared the promise, not its value: no product can pass it.

Measured on one run: two locked tests read `String(res?.headerValue('content-type'))` - a call that returns a
promise - and failed `Expected pattern: /text\\/html/ Received string: "[object Promise]"` against a product that
answered `text/html`. Nothing in the failure named the test's code, so both were charged to the backend as defects.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import suite
from app.stacks import contract, pack_named

PROMISE = ("Error: expect(received).toMatch(expected)\n\n    Expected pattern: /text\\/html/\n"
           "    Received string:  \"[object Promise]\"\n\n      at ui.spec.js:18:23\n")
PRODUCT = ("Error: expect(received).toMatch(expected)\n\n    Expected pattern: /text\\/html/\n"
           "    Received string:  \"application/json\"\n")


def _result(message):
    return SimpleNamespace(ran=True, report=SimpleNamespace(found=True, tests=[
        SimpleNamespace(name="[AC-6] The service serves the page", outcome="failed", message=message)]))


def _root(tmp_path):
    contract.write(tmp_path, pack_named("fullstack-page-fastapi"), "bookmarks", "Bookmarks")
    (tmp_path / "bookmarks" / "acceptance").mkdir(parents=True)
    (tmp_path / "bookmarks" / "acceptance" / "ui.spec.js").write_text(
        "test('[AC-6] The service serves the page', async ({ page }) => {});\n")
    return tmp_path


def test_a_promise_received_as_text_is_the_test_s_own_code(tmp_path):
    [found] = suite.tests_that_broke_themselves(_root(tmp_path), _result(PROMISE))
    assert "[AC-6]" in found and "await" in found


def test_a_value_the_product_gave_is_still_the_product_s(tmp_path):
    assert suite.tests_that_broke_themselves(_root(tmp_path), _result(PRODUCT)) == []
