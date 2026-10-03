"""A test round that reports the same defect many times has reported it once.

One run's round returned 71 defects with two distinct descriptions - one line
repeated as the model's output ran on - and the workflow dispatched a fix stage
per entry. Twenty-five fix stages in a row were each handed the same defect
before the run was stopped.
"""

from __future__ import annotations

from app.agents.specialists import ReportedDefect
from app.graph.workflow import _each_defect_once


def _defect(description: str, owner: str = "ui_ux", files: list[str] | None = None) -> ReportedDefect:
    return ReportedDefect(
        description=description, severity="major", reproduction_steps="npm test",
        expected_behavior="passes", actual_behavior="fails",
        affected_files=files if files is not None else ["app/app.js"], owner=owner,
    )


CANCEL = "Inline edit flow: cancel reverts to original fails - edit button not found."
EMPTY = "Inline edit flow: empty title validation fails - edit button not found after adding task."


def test_seventy_one_reports_of_two_defects_are_two_defects() -> None:
    reported = [_defect(CANCEL)] + [_defect(EMPTY) for _ in range(70)]

    kept = _each_defect_once(reported)

    assert [d.description for d in kept] == [CANCEL, EMPTY]


def test_spacing_and_case_do_not_make_a_new_defect() -> None:
    kept = _each_defect_once([_defect(EMPTY), _defect("  " + EMPTY.upper().replace(" ", "  "))])

    assert len(kept) == 1


def test_the_same_words_for_another_owner_or_file_are_another_defect() -> None:
    kept = _each_defect_once([
        _defect(EMPTY),
        _defect(EMPTY, owner="backend"),
        _defect(EMPTY, files=["app/state.js"]),
    ])

    assert len(kept) == 3
