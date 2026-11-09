"""A QA lead's reason about a test's own steps reopens it, even in the words that also describe products.

Measured on one run: "calls uid() twice ... so it asserts that updated.title equals a freshly generated random string
rather than the one actually sent to the server; its own steps never set up" - the dispute prompt's own phrasing -
matched "never set" as the product's, and a test no product can pass stayed locked.
"""
from __future__ import annotations

from app.agents import suite_dispute

AC4 = ("calls uid() twice (in the PUT body and in the assertion), so it asserts that updated.title equals a freshly "
       "generated random string rather than the one actually sent to the server; its own steps never set up that value")
AC13 = ("calls uid() twice, producing two different UIDs. This test would fail even if the product correctly rejects "
        "the PUT and leaves the note unchanged. It should compare note.title against created.title.")


def test_reasons_about_the_test_s_own_steps_are_the_test_s():
    assert suite_dispute.judged_by_the_code(AC4) is False
    assert suite_dispute.judged_by_the_code(AC13) is False


def test_reasons_about_the_product_still_are_the_product_s():
    assert suite_dispute.judged_by_the_code(
        "the implementation includes createdAt and updatedAt, which are not part of the criterion") is True
    assert suite_dispute.judged_by_the_code("StorageService.load() is never called, so data is lost") is True
