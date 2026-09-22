"""A round that found only test defects must not spend the product's budget.

Run b6436e36 failed after three remediation attempts with a working product:
43 of its 43 unit tests passed, all five features the brief names were built,
and the cross-file checks found one stranded spec and a 518-line product
against a 500-line cap. Of the eleven defects it spent those attempts on,
seven were in `ui.pw.test.mjs` - the Playwright suite the run had just written
- and its entire second attempt was that file and nothing else:

    round 1   2 in app.js, 2 in ui.pw.test.mjs
    round 2   0 in app.js, 3 in ui.pw.test.mjs
    round 3   2 in app.js, 2 in ui.pw.test.mjs

A suite settling down is not the product failing.
"""

from __future__ import annotations

import types

import pytest

from app.graph.workflow import _a_round_that_found_a_product_defect
from app.sprint import (
    ROUNDS_PER_ATTEMPT_CEILING,
    Defect,
    RemediationLimitExceeded,
    record_test_run,
    start_remediation,
)


def _defect(*files: str, description: str = "a failure") -> Defect:
    return Defect(
        description=description,
        severity="major",
        reproduction_steps="run the suite",
        expected_behavior="it passes",
        actual_behavior="it fails",
        affected_files=list(files),
        owner="testing",
        regression_test_required=False,
    )


def _round(cycle, defects, *, charge=None):
    if charge is None:
        charge = _a_round_that_found_a_product_defect(defects)
    return record_test_run(
        cycle,
        command=["specialist", "testing", "round"],
        passed=not defects,
        summary=f"{len(defects)} defect(s)",
        new_defects=defects,
        charge_the_budget=charge,
    )


# --- which rounds count ---------------------------------------------------


def test_a_round_of_only_test_defects_does_not_count() -> None:
    assert not _a_round_that_found_a_product_defect(
        [_defect("task-manager/ui.pw.test.mjs"), _defect("app.test.mjs")]
    )


def test_one_product_file_among_them_counts() -> None:
    assert _a_round_that_found_a_product_defect(
        [_defect("task-manager/ui.pw.test.mjs"), _defect("task-manager/app.js")]
    )


def test_a_defect_that_names_no_file_counts() -> None:
    """The question is "do we know this was only the tests?", and an unlocated
    defect is not known to be anything. Reading silence as good news is the
    mistake every other check in this codebase is written against."""
    assert _a_round_that_found_a_product_defect([_defect()])


def test_a_clean_round_counts_as_ordinary() -> None:
    assert _a_round_that_found_a_product_defect([])


# --- what that does to the budget ----------------------------------------


def test_three_test_only_rounds_do_not_exhaust_the_sprint() -> None:
    """Run b6436e36's shape. Under the old rule this escalated."""
    cycle = start_remediation("inline editing and filtering", max_attempts=3)
    for _ in range(3):
        cycle = _round(cycle, [_defect("task-manager/ui.pw.test.mjs")])

    assert not cycle.escalated
    assert cycle.attempt == 0


def test_product_rounds_still_exhaust_it() -> None:
    cycle = start_remediation("a sprint", max_attempts=3)
    for _ in range(3):
        cycle = _round(cycle, [_defect("task-manager/app.js")])

    assert cycle.escalated
    assert cycle.attempt == 3


def test_a_mixed_round_counts_as_a_product_round() -> None:
    cycle = start_remediation("a sprint", max_attempts=3)
    cycle = _round(cycle, [_defect("ui.pw.test.mjs"), _defect("app.js")])

    assert cycle.attempt == 1


def test_a_suite_that_never_settles_is_still_bounded() -> None:
    """Not charging a round has to have a floor, or a flaky suite loops for
    ever."""
    cycle = start_remediation("a sprint", max_attempts=3)
    ceiling = 3 * ROUNDS_PER_ATTEMPT_CEILING

    with pytest.raises(RemediationLimitExceeded) as raised:
        for _ in range(ceiling + 2):
            cycle = _round(cycle, [_defect("ui.pw.test.mjs")])

    assert "the suite is not settling" in str(raised.value)


def test_the_ceiling_is_derived_from_the_budget() -> None:
    """A second copy of the number is how two limits drift apart."""
    import inspect

    from app import sprint

    source = inspect.getsource(sprint)

    assert "cycle.max_attempts * ROUNDS_PER_ATTEMPT_CEILING" in source


def test_a_passing_round_still_clears_nothing_unexpected() -> None:
    cycle = start_remediation("a sprint", max_attempts=3)
    cycle = _round(cycle, [_defect("app.js")])
    cycle = _round(cycle, [])

    assert cycle.attempt == 1
    assert not cycle.escalated
