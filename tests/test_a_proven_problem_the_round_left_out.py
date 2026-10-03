"""A problem a test round was handed as proven, and did not report, is still a defect.

Every round of one run was told, under "Already proven by reading the files ...
Report every one as a defect", that the page `index.html` its plan named was
missing. Rounds 0, 1 and 2 each reported one defect - the first proven item -
and left the rest, so the page that made every browser test fail waited three
rounds to become anyone's task.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.specialists import ReportedDefect
from app.graph.workflow import _proven_problems_the_round_left_out

PAGE_MISSING = (
    "The plan names `index.html` and the workspace holds no such file - nothing "
    "was written for it."
)
RUNNERS = (
    "simple-to-do-list-app/package.json runs two test runners, and nothing tells `jest` "
    "where to look - so it also loads the files written for `playwright`: "
    "simple-to-do-list-app/e2e/app.spec.js."
)

MILESTONE = SimpleNamespace(delegated_tasks=[
    SimpleNamespace(specialist_role=SimpleNamespace(value="ui_ux"), files=["simple-to-do-list-app/index.html"]),
    SimpleNamespace(specialist_role=SimpleNamespace(value="backend"), files=["simple-to-do-list-app/package.json"]),
])


def _reported(description: str, files: list[str] | None = None) -> ReportedDefect:
    return ReportedDefect(
        description=description, severity="major", reproduction_steps="npm test",
        expected_behavior="passes", actual_behavior="fails", affected_files=files or [], owner="testing",
    )


def test_what_it_left_out_is_added_for_the_owner_of_the_file() -> None:
    reported = [_reported("Jest loads the Playwright spec app.spec.js", ["simple-to-do-list-app/package.json"])]

    left_out = _proven_problems_the_round_left_out([RUNNERS, PAGE_MISSING], reported, MILESTONE)

    assert [d.description for d in left_out] == [PAGE_MISSING]
    assert str(getattr(left_out[0].owner, "value", left_out[0].owner)) == "ui_ux"


def test_what_it_reported_is_not_added_again() -> None:
    reported = [
        _reported("Jest also runs e2e/app.spec.js", ["simple-to-do-list-app/package.json"]),
        _reported("There is no index.html, so the browser tests have no page"),
    ]

    assert _proven_problems_the_round_left_out([RUNNERS, PAGE_MISSING], reported, MILESTONE) == []


def test_a_round_that_reported_nothing_gets_them_all() -> None:
    left_out = _proven_problems_the_round_left_out([RUNNERS, PAGE_MISSING], [], MILESTONE)

    assert len(left_out) == 2


def test_a_problem_whose_files_nobody_owns_goes_to_testing() -> None:
    orphan = "tests/helper.js defines load itself and calls its own copy rather than storage.js's."

    (defect,) = _proven_problems_the_round_left_out([orphan], [], SimpleNamespace(delegated_tasks=[]))

    assert str(getattr(defect.owner, "value", defect.owner)) == "testing"
