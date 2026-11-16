"""A label tests find a control by, or a 409 that is a line number, is not a record tests share (recurring: tests that
collide on shared data).

Measured on one run: a page storing in the browser, with no service, was read as answering 409 (a `\\b409\\b` match)
on a value 17 tests "made" - `getByLabel('Title')`, the field's label - and its locked suite was reopened for it.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from app.acceptance import suite

BODY = ("await page.getByLabel('Title', { exact: true }).fill(title);\\n"
        "await expect(page.getByText('Title is required')).toBeVisible();\\n")


def test_a_locator_s_argument_is_not_a_value_made():
    assert suite._values_made_in(BODY) == set()
    assert suite._values_made_in("await signup(request, 'alice', 'secret1');") == {"alice"}


def test_only_a_409_the_service_answered_is_one():
    assert not suite._ALREADY_HELD.search("at app.spec.js:409:12 timed out")
    assert suite._ALREADY_HELD.search("assert 409 == 201")
    assert suite._ALREADY_HELD.search("Received: 409")


def test_the_page_suite_of_one_run_is_not_reopened_for_its_label(tmp_path):
    bodies = {f"[AC-{n}] t{n}": BODY for n in range(1, 18)}
    result = SimpleNamespace(ran=True, report=SimpleNamespace(tests=[
        SimpleNamespace(name="[AC-3] t3", outcome="failed", message="Error: timed out at app.spec.js:409")]))
    with mock.patch.object(suite, "_test_bodies", return_value=bodies):
        assert suite.tests_that_make_what_other_tests_make(tmp_path, result) == []
