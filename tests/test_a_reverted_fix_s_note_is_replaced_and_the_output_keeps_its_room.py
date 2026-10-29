"""A defect's revert note is replaced, not appended to, and the runner's output keeps half of the failure budget.

Found in a code review of the defect-fix loop: each reverted fix appended the same ~400-character note to its
defect's actual behaviour, and `rewritten_fixes.what_failed` put the defect's own words first and cut the runner's
output from the end. After three reverts the notes were about 4,200 characters and the output was cut at test 23 of
79. The note is now one, counting the reverts and the locked tests they broke, and what the runner printed keeps at
least half of the budget.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.graph import rewritten_fixes, workflow
from app.sprint import Defect, RemediationCycle

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
LOCKED = "acceptance: notes.spec.js › [AC-2] lists the notes"


def _cycle(actual: str = "The list is empty after a note is added.") -> RemediationCycle:
    return RemediationCycle(sprint_goal="Sprint 2", defects=[Defect(
        description="[AC-1] Add a note", severity="major", reproduction_steps="r", expected_behavior="e",
        actual_behavior=actual, owner="backend", affected_files=["src/notes.js"],
    )])


def _reverted(cycle: RemediationCycle, times: int, broke: list[str]) -> RemediationCycle:
    for _ in range(times):
        cycle = workflow._noted_as_reverted(cycle, [0], broke)
    return cycle


def test_three_reverts_leave_one_note_that_counts_them() -> None:
    once = _reverted(_cycle(), 1, [LOCKED, "unit: notes.test.js › adds"]).defects[0].actual_behavior
    thrice = _reverted(_cycle(), 3, [LOCKED, "unit: notes.test.js › adds"]).defects[0].actual_behavior

    assert thrice.startswith("The list is empty after a note is added.")
    assert thrice.count("A fix was tried and reverted") == 1
    assert thrice.count("If the behaviour this sprint delivers is different") == 1
    assert "Fixes of this defect reverted so far: 3." in thrice
    assert len(thrice) < len(once) + 300
    assert not BANNED.search(thrice)


def test_the_reverts_are_still_counted_for_the_escalation_and_the_dispute() -> None:
    once = _reverted(_cycle(), 1, [LOCKED])
    twice = _reverted(_cycle(), 2, [LOCKED])

    assert workflow._a_revert_escalates_this_fix(once, 0) is True
    assert workflow._a_revert_escalates_this_fix(twice, 0) is False
    assert workflow._a_locked_test_two_fixes_broke(once) == ""
    assert workflow._a_locked_test_two_fixes_broke(twice) == LOCKED


def test_a_batch_revert_then_a_revert_alone_counts_two() -> None:
    cycle = workflow._noted_as_reverted(_cycle(), [0], [LOCKED], in_a_batch=True)
    cycle = workflow._noted_as_reverted(cycle, [0], ["acceptance: notes.spec.js › [AC-3] deletes"])
    said = cycle.defects[0].actual_behavior

    assert "A batch of fixes including this one" not in said
    assert "Fixes of this defect reverted so far: 2." in said
    assert workflow._a_locked_test_two_fixes_broke(cycle) == ""


def test_what_came_after_the_note_is_kept_when_the_note_is_replaced() -> None:
    cycle = _reverted(_cycle(), 1, [LOCKED])
    later = cycle.defects[0].actual_behavior + "\nThe harness loaded it: `sqlite3` loads in this project."
    cycle = _reverted(_cycle(later), 1, [LOCKED])
    said = cycle.defects[0].actual_behavior

    assert "The harness loaded it" in said and said.count("A fix was tried and reverted") == 1


def test_the_runner_s_output_keeps_half_of_the_budget_after_a_long_defect(tmp_path) -> None:
    budget = rewritten_fixes.MOST_FAILURE_CHARACTERS
    defect = SimpleNamespace(description="d", actual_behavior="The page is blank. " * 400, reproduction_steps="")
    printed = "\n".join(f"not ok {n} - case {n} fails" for n in range(1, 80))

    failure = rewritten_fixes.what_failed(defect, tmp_path, {"command": "npm test", "stdout": printed})

    assert len(failure) <= budget
    assert failure.startswith("The page is blank.")
    assert rewritten_fixes.THE_LAST_FAILING_COMMAND in failure
    assert "not ok 79 - case 79 fails" in failure


def test_a_short_failure_is_handed_over_as_it_was(tmp_path) -> None:
    defect = SimpleNamespace(description="d", actual_behavior="It fails.", reproduction_steps="Open it.")

    failure = rewritten_fixes.what_failed(defect, tmp_path, {"command": "npm test", "stdout": "1 failing"})

    assert failure == f"It fails.\n\nOpen it.\n\n{rewritten_fixes.THE_LAST_FAILING_COMMAND}\nnpm test\n1 failing"
