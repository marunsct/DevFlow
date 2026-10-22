"""Criteria that fail the same way on the same page are one cause, one fixer.

An assertion is a symptom, not a layer, so assertion failures never
clustered. Measured live: eight criteria each failed
`expect(page).toHaveURL(expected)` on one sign-in page showing "Login
failed", and were queued as eight defects for fixers to work one by one.
"""
from __future__ import annotations

from app.agents.specialists import ReportedDefect
from app.graph.acceptance_nodes import THE_PAGE_WHEN_IT_FAILED
from app.graph.workflow import SAME_FAILURE_BEFORE_ONE_CAUSE, _one_defect_per_root_error

SIGN_IN_PAGE = '- heading "Sign in" [level=1]\n- paragraph: Sign-in failed\n- textbox "Email"'


def _d(cid, line, page, port):
    return ReportedDefect(
        description=f"[{cid}] does not work yet.", severity="major", reproduction_steps="r",
        expected_behavior="e", owner="backend", affected_files=[],
        actual_behavior=f"[{cid}] a test: {line} at http://127.0.0.1:{port}/login{THE_PAGE_WHEN_IT_FAILED}{page}",
    )


def test_criteria_failing_alike_on_one_page_merge():
    reported = [_d(f"AC-{n}", "expect(page).toHaveURL(expected) failed", SIGN_IN_PAGE, 39000 + n) for n in range(SAME_FAILURE_BEFORE_ONE_CAUSE)]

    merged = _one_defect_per_root_error(reported)

    assert len(merged) == 1
    assert "the same failure on the same page" in merged[0].description


def test_what_each_test_typed_does_not_split_them():
    reported = [
        _d(f"AC-{n}", "expect(page).toHaveURL(expected) failed", SIGN_IN_PAGE + f': user{chr(97 + n)}@example.com', 1)
        for n in range(SAME_FAILURE_BEFORE_ONE_CAUSE)
    ]

    assert len(_one_defect_per_root_error(reported)) == 1


def test_fewer_than_the_threshold_stay_apart():
    reported = [_d(f"AC-{n}", "expect(page).toHaveURL(expected) failed", SIGN_IN_PAGE, 1) for n in range(SAME_FAILURE_BEFORE_ONE_CAUSE - 1)]

    assert len(_one_defect_per_root_error(reported)) == SAME_FAILURE_BEFORE_ONE_CAUSE - 1


def test_the_same_assertion_on_different_pages_stays_apart():
    reported = [_d(f"AC-{n}", "expect(page).toHaveURL(expected) failed", f'- heading "Page {chr(65 + n)}"', 1) for n in range(4)]

    assert len(_one_defect_per_root_error(reported)) == 4


def test_a_failure_with_no_page_stays_apart():
    reported = [
        ReportedDefect(description=f"[AC-{n}] x", severity="major", reproduction_steps="r", expected_behavior="e",
                       owner="backend", affected_files=[], actual_behavior="expect(received).toBe(expected)")
        for n in range(4)
    ]

    assert len(_one_defect_per_root_error(reported)) == 4
