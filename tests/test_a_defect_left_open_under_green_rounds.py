"""A defect no fix closes cannot loop a sprint through passing rounds forever.

`defect_remediation` leaves a defect open on purpose when its fix names no
regression test, trusting that "the next test round will count this as another
failed attempt, so the bounded loop still terminates". But both bounds in
`record_test_run` - attempts, and the round ceiling - were written for failing
rounds, and the next round passed. The workflow routes any round that leaves a
defect open straight back to remediation, so nothing ever ended it.

Measured on one run: one defect no stage could close looped

    test_round_3 -> defect_fix_4_3 -> test_round_4 -> ... -> test_round_7 -> defect_fix_8_3

with every round reporting `"defects": []` and no limit reached.
"""

from __future__ import annotations

import pytest

from app.sprint import Defect, RemediationLimitExceeded, record_test_run, start_remediation


def _stuck_defect() -> Defect:
    return Defect(
        description="filtered.map mentioned in milestone plan but no such file exists",
        severity="minor",
        reproduction_steps="Read milestone_plan.md",
        expected_behavior="The file exists or the plan is updated",
        actual_behavior="No such file",
        affected_files=["docs/milestone_plan.md"],
        owner="backend",
    )


def _a_green_round(cycle):
    return record_test_run(cycle, command=["specialist", "testing"], passed=True, new_defects=[])


def test_green_rounds_over_an_open_defect_reach_the_limit() -> None:
    cycle = record_test_run(
        start_remediation("Sprint 2", max_attempts=3),
        command=["specialist", "testing"],
        passed=False,
        new_defects=[_stuck_defect()],
    )

    with pytest.raises(RemediationLimitExceeded):
        for _ in range(20):
            cycle = _a_green_round(cycle)


def test_each_such_round_uses_an_attempt() -> None:
    cycle = record_test_run(
        start_remediation("Sprint 2", max_attempts=3),
        command=["specialist", "testing"],
        passed=False,
        new_defects=[_stuck_defect()],
    )
    before = cycle.attempt

    assert _a_green_round(cycle).attempt == before + 1


def test_a_green_round_with_nothing_open_is_still_free() -> None:
    """The case the old rule was written for, unchanged."""
    cycle = start_remediation("Sprint 2", max_attempts=3)

    for _ in range(10):
        cycle = _a_green_round(cycle)

    assert cycle.attempt == 0
