"""A review finding that only says a test fails because the product is not built yet does not send the suite back.

The suite is written before the product, so its tests fail now by design. One
run's QA lead sent it back with fifteen findings, each "test_acN fails with 404
because ... is not implemented", and QA, handed them, set about writing the
product again - refused at every turn.
"""
from __future__ import annotations

import inspect

from app.acceptance import suite

ABOUT_THE_PRODUCT = [
    "AC-3: test_ac3_fetch_note_by_id fails with 404 because GET /notes/{id} is not implemented.",
    "AC-6: test_ac6_persist_across_restart fails with 404 because the /notes routes are not implemented.",
    "AC-9: test_ac9_list_notes returns 404: the list route has not been built.",
]
ABOUT_THE_TESTS = [
    "AC-15: test_ac15_start_sh fails because the data directory does not exist in the environment.",
    "AC-2: test_ac2_list only asserts the status code, not that the created note is in the array.",
    "AC-8 has no test whose name carries `AC-8`.",
    "test_ac10 expects 404 for a note that exists; it should expect 200.",
    "AC-4: test_ac4 fails with 404 because PUT is not implemented, and it never asserts the body was replaced.",
]


def test_findings_about_the_unbuilt_product_are_dropped_and_the_rest_kept():
    assert suite.findings_about_the_suite(ABOUT_THE_PRODUCT + ABOUT_THE_TESTS) == ABOUT_THE_TESTS


def test_the_review_sends_back_only_what_is_left():
    from app.graph import acceptance_nodes

    source = inspect.getsource(acceptance_nodes.acceptance_review)
    filtered = source.index("findings = suite.findings_about_the_suite(")
    sent_back = source.index('acceptance_feedback=findings)')
    assert filtered < sent_back and "if not review.approved and findings:" in source
