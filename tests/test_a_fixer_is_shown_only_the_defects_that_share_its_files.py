"""A fixer is shown only the defects that share its files, two at most.

Every open defect of the same owner was bundled into one fixer's request. Over
every recorded run, a fixer handed one defect fixed it 64% of the time in a
median 18k output tokens; one handed four or more fixed 26% in 73k, with 62% of
those stages cut off at the reply limit against 11%. A defect an earlier fix
resolved is closed by measurement whether or not it was bundled, so bundling
bought nothing but a wider question.
"""
from __future__ import annotations

from app.graph.workflow import MOST_BUNDLED_DEFECTS, _bundle_co_defects
from app.sprint import Defect, RemediationCycle


def _d(n: int, files: list[str]) -> Defect:
    return Defect(description=f"[AC-{n}] criterion {n} fails", severity="major", reproduction_steps="r",
                  expected_behavior="e", actual_behavior="a", owner="backend", failing_criteria=[f"AC-{n}"],
                  affected_files=files)


def test_unrelated_defects_each_get_their_own_fixer():
    cycle = RemediationCycle(sprint_goal="g", defects=[_d(1, ["api/notes.py"]), _d(2, ["api/users.py"]), _d(3, ["db.py"])])

    assert _bundle_co_defects(cycle, 0) == []


def test_at_most_two_related_most_files_in_common_first_in_round_order():
    defects = [_d(1, ["api/notes.py", "db.py"]), _d(2, ["api/notes.py"]), _d(3, ["api/notes.py", "db.py"]),
               _d(4, ["db.py"]), _d(5, ["api/notes.py", "db.py"]), _d(6, ["other.py"])]

    bundled = [pos for pos, _ in _bundle_co_defects(RemediationCycle(sprint_goal="g", defects=defects), 0)]

    assert MOST_BUNDLED_DEFECTS == 2 and bundled == [2, 4]


def test_a_defect_that_names_no_file_is_fixed_alone():
    cycle = RemediationCycle(sprint_goal="g", defects=[_d(1, []), _d(2, ["api/notes.py"])])

    assert _bundle_co_defects(cycle, 0) == []
