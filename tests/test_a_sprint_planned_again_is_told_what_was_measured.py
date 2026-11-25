"""A sprint planned again for its foundation is planned from what the harness measured, not one line (LF.1441).

Measured on a medium run (deep review 2026-11-25, decisions finding 2 and evidence finding 4): the re-plan request's
whole reason was "the plan has sprint 2, 3 depend on sprint 1, which passes 8 of its 21 acceptance tests. Find the one
cause behind these failures first". It held no failing test's output and none of the five defects the test round had
raised one second earlier. The lead read files for 19 minutes and decided the service could not start - which the
harness had measured false - and the tester's finding (an `ARRAY` column SQLite cannot create) never appeared again.
The saved acceptance and unit results are the run's own; the defects are the five the round raised, as recorded.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from types import SimpleNamespace

from app.graph import escalation, foundation
from app.sprint import Defect, RemediationCycle

CAPTURED = Path(__file__).parent / "captured"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

RAISED = [
    ("test round", "SQLAlchemy ARRAY type blocks SQLite table creation in test fixtures",
     "'SQLiteTypeCompiler' object has no attribute 'visit_ARRAY'"),
    ("code review", "Code review (Create the login page, register page, and basic responsive layout for Sprint 1.): "
                    "The [AC-8] acceptance test (auth.spec.js line 177) verifies that a token is invalidated after "
                    "logout by calling GET /api/tasks with the same token and expecting 401.", ""),
    ("page check", "Styling faults: the page's stylesheets and markup disagree in ways a script can prove, none of "
                   "them holding the sprint. raw colours where the design tokens should be used.", ""),
    ("acceptance suite", "[AC-1] User registration and authentication (JWT-based) - the acceptance suite says this "
                         "does not work yet.", ""),
    ("acceptance suite", "[AC-13] All endpoints have proper error handling - the acceptance suite says this does not "
                         "work yet.", ""),
]


def _state(tmp_path: Path) -> dict:
    (tmp_path / ".harness").mkdir()
    shutil.copy(CAPTURED / "acceptance-result-a-foundation-sprint-fastapi.json",
                tmp_path / ".harness" / "acceptance-result.json")
    shutil.copy(CAPTURED / "unit-result-a-foundation-sprint-fastapi.json", tmp_path / ".harness" / "unit-result.json")
    defects = [Defect(description=text, severity="major", reproduction_steps="run the tests",
                      expected_behavior="it works", actual_behavior=printed, owner="backend", source=source)
               for source, text, printed in RAISED]
    sprints = [SimpleNamespace(goal="sign-up and sign-in", criteria=["AC-1", "AC-8", "AC-12", "AC-13", "AC-14",
                                                                     "AC-15"], dependencies=[]),
               SimpleNamespace(goal="the list", criteria=["AC-2"], dependencies=["Sprint 1"])]
    return {"repository": SimpleNamespace(root_path=str(tmp_path)), "current_sprint_index": 0,
            "sprint_plan": SimpleNamespace(sprints=sprints),
            "remediation": RemediationCycle(sprint_goal="sign-up and sign-in", defects=defects)}


def test_the_re_plan_request_carries_each_open_defect_and_what_the_tests_said(tmp_path):
    state = _state(tmp_path)
    needed = ["the plan has sprint 2 depend on sprint 1, which passes 8 of its 21 acceptance tests"]

    update = escalation._the_foundation_first(state, {}, [{"id": "AC-1"}, {"id": "AC-8"}, {"id": "AC-13"}],
                                              "", needed)

    request = "\n".join(update["revision_comments"])
    for _source, text, _printed in RAISED:
        assert text[:60] in request
    assert "visit_ARRAY" in request
    assert "Received: 500" in request
    assert "AmbiguousForeignKeysError" in request
    assert "the product starts for the acceptance suite" in request


def test_the_lead_is_told_its_reading_of_a_cause_is_not_a_measurement():
    said = foundation.replan_guidance(1, "sign-up", ["AC-1"], ["it fails"])

    assert foundation.READING_NOT_MEASURED in said
    assert not BANNED.search(foundation.READING_NOT_MEASURED + foundation.MEASURED_HEADING)
