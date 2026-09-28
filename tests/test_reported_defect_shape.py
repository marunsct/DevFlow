"""The defect shape a specialist actually sends, taken from one run.

`defect_fix_2_0` produced this answer and the harness rejected it five times
running, until the repeat guard stopped the stage and the run failed. Every
rejection was about spelling: `name` instead of `description`, `status` as an
extra key, `High` instead of `major`, `Testing Specialist` instead of `testing`.
The defect itself was real, correctly diagnosed and precisely reproduced.

Recorded verbatim so the shape cannot quietly stop being accepted.
"""

from __future__ import annotations

import pytest

from app.agents.specialists import ReportedDefect, SpecialistOutput

RUN_0DEEB8BF = {
    "changed_files": ["simple-to-do-list-app/app.test.js", "docs/defects.md"],
    "decisions": ["Added regression test 'testAddTaskRegression'."],
    "tests": ["testAddTaskRegression"],
    "verification": [],
    "documentation": [],
    "risks": [],
    "blockers": ["Tests remain failing."],
    "defects": [
        {
            "name": "LocalStorage Integration Failure in Unit Tests",
            "description": "addTask does not persist tasks to localStorage.",
            "severity": "High",
            "reproduction_steps": "Run node simple-to-do-list-app/app.test.js",
            "expected_behavior": "addTask stores the task in localStorage.",
            "actual_behavior": "The test throws a TypeError.",
            "owner": "Testing Specialist",
            "status": "Unresolved",
        }
    ],
}


def test_the_answer_that_killed_run_0deeb8bf_is_accepted() -> None:
    output = SpecialistOutput.model_validate(RUN_0DEEB8BF)

    (defect,) = output.defects
    assert defect.severity == "major"
    assert defect.owner == "testing"
    assert defect.description == "addTask does not persist tasks to localStorage."


def test_a_defect_that_only_has_a_name_uses_it_as_the_description() -> None:
    """`name` is the key models reach for when there is no `description`."""
    defect = ReportedDefect.model_validate(
        {
            "name": "Login returns 500",
            "severity": "blocker",
            "reproduction_steps": "POST /login",
            "expected_behavior": "200",
            "actual_behavior": "500",
            "owner": "Backend",
        }
    )

    assert defect.description == "Login returns 500"
    assert defect.severity == "blocking"
    assert defect.owner == "backend"


def test_the_lifecycle_fields_are_still_withheld() -> None:
    """`extra="ignore"` drops them; it must not start accepting them.

    `status`, `regression_test` and `accepted_risk_reason` belong to the
    controller's `app.sprint.Defect`. Letting a specialist set them here would
    let it declare its own defects fixed.
    """
    defect = ReportedDefect.model_validate(
        {
            "description": "d",
            "severity": "major",
            "reproduction_steps": "r",
            "expected_behavior": "e",
            "actual_behavior": "a",
            "owner": "testing",
            "status": "resolved",
            "regression_test": "already written",
            "accepted_risk_reason": "we decided not to care",
        }
    )

    for withheld in ("status", "regression_test", "accepted_risk_reason"):
        assert not hasattr(defect, withheld)


@pytest.mark.parametrize("owner", ["the team", "everyone", "unassigned"])
def test_an_unroutable_defect_is_still_refused(owner: str) -> None:
    with pytest.raises(Exception):
        ReportedDefect.model_validate(
            {
                "description": "d",
                "severity": "major",
                "reproduction_steps": "r",
                "expected_behavior": "e",
                "actual_behavior": "a",
                "owner": owner,
            }
        )


def test_a_defect_missing_its_evidence_is_still_refused() -> None:
    """The first answer one run sent really was incomplete.

    It carried a name, a description and a status and nothing else - no
    reproduction, no expected behaviour. That one must still be rejected, so
    the model is told which fields are missing rather than having a hollow
    defect recorded for it.
    """
    with pytest.raises(Exception):
        ReportedDefect.model_validate(
            {
                "name": "LocalStorage Integration Failure",
                "description": "addTask does not persist tasks.",
                "status": "Unresolved",
            }
        )
