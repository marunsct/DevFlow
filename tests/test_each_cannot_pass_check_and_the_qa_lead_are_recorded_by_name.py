"""Each check inside `tests_that_cannot_pass` and the QA lead's findings are recorded under their own names (HR2.Q.1).

Measured: 36 checks were recorded as one bucket and the QA lead - the sender of 240 of the 295 items left open at the
lock - not at all, so no check's settle rate could be told apart.
"""
from __future__ import annotations

from the_acceptance_review import (
    A_FAIR_TEST, FAILED, NO_PRODUCT_CAN_PASS, PASSED, a_service_suite, measured, qa_lead, recorded_checks, reviewed,
)


def test_the_review_records_each_finding_under_the_check_that_raised_it(tmp_path):
    root = a_service_suite(tmp_path, NO_PRODUCT_CAN_PASS)

    reviewed(root, measured(FAILED))

    assert "responses_read_without_the_call" in recorded_checks(root)
    assert "tests_that_cannot_pass" not in recorded_checks(root)


def test_the_qa_lead_s_findings_are_recorded_as_its_own(tmp_path):
    root = a_service_suite(tmp_path, A_FAIR_TEST)

    reviewed(root, measured(PASSED), review=qa_lead(False, "AC-1: the test never reads the created note back."))

    assert recorded_checks(root) == ["qa_lead"]
