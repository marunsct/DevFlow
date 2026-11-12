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


def _root_with(tmp_path, body):
    contract.write(tmp_path, pack_named("fullstack-page-fastapi"), "bookmarks", "Bookmarks")
    (tmp_path / "bookmarks" / "acceptance").mkdir(parents=True)
    (tmp_path / "bookmarks" / "acceptance" / "api.spec.js").write_text(
        "test('[AC-13] deletes a bookmark', async ({ request }) => {\n" + body + "\n});\n")
    return tmp_path


def _a_failure():
    return SimpleNamespace(ran=True, report=SimpleNamespace(found=True, tests=[SimpleNamespace(
        name="[AC-13] deletes a bookmark", outcome="failed", message="Expected: 204\nReceived: 422")]))


def test_a_field_read_off_json_itself_is_the_test_s_own_code(tmp_path):
    """Measured on one run: `createResp.json().id` sent `DELETE /api/bookmarks/undefined`, the service rightly
    answered 422, and five locked tests went past the reclassification cap."""
    root = _root_with(tmp_path, "  const id = createResp.json().id;\n  await request.delete(`/api/bookmarks/${id}`);")
    [found] = suite.tests_that_broke_themselves(root, _a_failure())
    assert "createResp.json().id" in found and "await it" in found


def test_an_awaited_json_or_a_then_is_left_alone(tmp_path):
    for i, body in enumerate(["  const id = (await createResp.json()).id;",
                              "  const body = await createResp.json();\n  const id = body.id;",
                              "  const id = await createResp.json().then((b) => b.id);"]):
        assert suite.tests_that_broke_themselves(_root_with(tmp_path / str(i), body), _a_failure()) == [], body
