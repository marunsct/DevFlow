"""A matcher met with a value the product never gave, or an error the harness appended, is not a bug in the test.

Measured on one run: a right test read a missing `Location` header and Playwright reported
`TypeError: expect(received).toMatch(expected) ... Received has value: undefined`; the TypeError pattern read it as
the test's own code, the suite was reopened twice before any round, and QA spent two full cycles on a test it could
not change. Deep review A4: the page tree and the service log the harness appends carry the product's errors.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import suite
from app.stacks import contract, pack_named

MISSING = ("expect(received).toMatch(expected)\n"
           "    TypeError: expect(received).toMatch(expected)\n\n    Matcher error: received value must be a string\n\n"
           "    Received has value: undefined\n")
OWN_BUG = "TypeError: res.status is not a function\n    at notes.spec.js:12:5\n"
PRODUCT_ON_PAGE = ("expect(locator).toHaveCount(expected)\n    Expected: 1\n    Received: 0\n"
                   + suite._PAGE_MARK + "text: TypeError: Cannot read properties of undefined (reading 'map')\n")


def _result(message):
    contract_root = None
    return SimpleNamespace(ran=True, report=SimpleNamespace(found=True, tests=[
        SimpleNamespace(name="[AC-8] POST /notes returns Location header", outcome="failed", message=message)]))


def _root(tmp_path, pack="node-hono-native-api"):
    contract.write(tmp_path, pack_named(pack), "notes", "Notes")
    (tmp_path / "notes" / "acceptance").mkdir(parents=True)
    (tmp_path / "notes" / "acceptance" / "notes.spec.js").write_text(
        "test('[AC-8] POST /notes returns Location header', async ({ request }) => {});\n")
    return tmp_path


def test_a_matcher_given_undefined_by_the_product_is_the_product_s(tmp_path):
    assert suite.tests_that_broke_themselves(_root(tmp_path), _result(MISSING)) == []


def test_an_error_in_the_test_s_own_code_is_still_found(tmp_path):
    [found] = suite.tests_that_broke_themselves(_root(tmp_path), _result(OWN_BUG))
    assert "is not a function" in found


def test_an_error_the_harness_appended_from_the_page_is_not_the_test_s(tmp_path):
    assert suite.tests_that_broke_themselves(_root(tmp_path, "browser-javascript"), _result(PRODUCT_ON_PAGE)) == []


#: Measured on one run: nine locked tests failed reading the product's "Internal Server Error" as JSON; read as the
#: tests' own code, the suite went back to its writers for about 40 minutes instead of the product to its fixers.
NOT_JSON = ("SyntaxError: Unexpected token 'I', \"Internal S\"... is not valid JSON\n"
            "    at notes.spec.js:20:31\n")
NOT_JSON_PAGE = "SyntaxError: Unexpected token '<', \"<!DOCTYPE \"... is not valid JSON\n"


def test_a_product_answering_something_that_is_not_json_is_the_product_s(tmp_path):
    root = _root(tmp_path, "fullstack-page-fastapi")
    assert suite.tests_that_broke_themselves(root, _result(NOT_JSON)) == []
    assert suite.tests_that_broke_themselves(root, _result(NOT_JSON_PAGE)) == []
