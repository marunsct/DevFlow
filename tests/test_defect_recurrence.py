"""A defect that was fixed and came back is evidence the fix did not work.

Treating it as a new defect spends another remediation attempt on the same
problem and tells the specialist nothing it does not already believe.

Measured on one run, which exhausted all six remediation attempts and
never wrote a line of application code:

    fixed: Regression test fails due to missing y18n module import
    fixed: Regression test fails due to improper import of y18n module.
    fixed: Regression tests fail due to y18n module import issues.

One problem, three wordings, three attempts, each closed as done.
"""

from __future__ import annotations

from app.sprint import (
    Defect,
    build_defect_report,
    recurrence_of,
    recurring_defect_note,
    start_remediation,
)


def _defect(description: str, status: str = "open") -> Defect:
    return Defect(
        description=description,
        severity="major",
        reproduction_steps="npm test",
        expected_behavior="tests pass",
        actual_behavior="tests fail",
        owner="testing",
        status=status,
    )


def test_the_same_problem_in_different_words_is_recognised():
    earlier = _defect("Regression test fails due to missing y18n module import", "fixed")
    again = _defect("Regression tests fail due to y18n module import issues.")

    assert recurrence_of(again, [earlier]) is earlier


def test_a_third_wording_is_still_recognised():
    history = [
        _defect("Regression test fails due to missing y18n module import", "fixed"),
        _defect("Regression test fails due to improper import of y18n module.", "fixed"),
    ]
    again = _defect("Regression tests fail due to y18n module import issues.")

    assert recurrence_of(again, history) is not None


def test_a_genuinely_different_defect_is_not_a_recurrence():
    earlier = _defect("Regression test fails due to missing y18n module import", "fixed")
    other = _defect("Cypress integration test failing due to undefined cy")

    assert recurrence_of(other, [earlier]) is None


def test_a_still_open_defect_is_not_a_recurrence():
    """Only a defect someone claimed to have fixed can come back."""
    earlier = _defect("Regression test fails due to missing y18n module import")
    again = _defect("Regression tests fail due to y18n module import issues.")

    assert recurrence_of(again, [earlier]) is None


def test_a_description_with_almost_no_content_is_not_matched():
    """Two vague defects are not evidence of anything."""
    earlier = _defect("tests fail", "fixed")

    assert recurrence_of(_defect("tests fail"), [earlier]) is None


def test_the_report_tells_the_specialist_its_fix_did_not_work():
    cycle = start_remediation("Sprint 1")
    cycle = cycle.model_copy(
        update={
            "defects": [
                _defect("Regression test fails due to missing y18n module import", "fixed"),
                _defect("Regression tests fail due to y18n module import issues."),
            ]
        }
    )

    report = build_defect_report(cycle)

    assert "already been 'fixed' once and came back" in report
    assert "That fix did not work" in report
    assert "outside what you can change" in report


def test_a_clean_cycle_adds_no_note():
    cycle = start_remediation("Sprint 1")
    cycle = cycle.model_copy(update={"defects": [_defect("Cypress test lacks cy")]})

    assert recurring_defect_note(cycle) == ""
    assert "came back" not in build_defect_report(cycle)
