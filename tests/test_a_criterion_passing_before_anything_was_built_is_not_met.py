"""A criterion whose every test passed before anything was built is not shown as met (LF.1446).

Measured on a medium run (deep review 2026-11-25, decisions finding 7): the lock recorded "8 of 21 test(s) pass although
nothing of the product is built yet", naming both AC-12 tests, both AC-15 tests and all four AC-14 tests; from then on
the re-plan listed "AC-15: Database migrations required - currently PASSED", and the time budget and the escalation
said "still failing: AC-1, AC-8, AC-13" while AC-15's tests passed with a migration function that ran no migration.
The names are the lock's real record; the saved result is the run's own.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from types import SimpleNamespace

from app.acceptance import passed_unbuilt, suite
from app.graph import foundation, sprint_time_budget

CAPTURED = Path(__file__).parent / "captured" / "acceptance-result-a-foundation-sprint-fastapi.json"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

#: The lock's own list of the tests that passed with nothing built.
AT_THE_LOCK = [
    "[AC-12] /docs returns Swagger/OpenAPI documentation", "[AC-12] /openapi.json returns valid OpenAPI schema",
    "[AC-15] service starts with migrations applied", "[AC-15] service remains stable after startup",
    "[AC-14] main container is visible on page load", "[AC-14] viewport meta tag is present",
    "[AC-14] page loads without console errors", "[AC-14] page has a title",
]
SPRINT = ["AC-1", "AC-8", "AC-12", "AC-13", "AC-14", "AC-15"]


def _locked_with_nothing_built(root: Path) -> None:
    (root / ".harness").mkdir()
    shutil.copy(CAPTURED, root / ".harness" / "acceptance-result.json")
    tests = [SimpleNamespace(name=name, outcome="passed") for name in AT_THE_LOCK]
    tests += [SimpleNamespace(name="[AC-1] registration creates a new user", outcome="failed")]
    passed_unbuilt.record(root, SimpleNamespace(ran=True, report=SimpleNamespace(tests=tests)), nothing_built=True)


def test_criteria_passing_only_on_those_tests_are_not_shown_as_passed(tmp_path):
    _locked_with_nothing_built(tmp_path)
    saved = suite.last_result(tmp_path)
    unproven = passed_unbuilt.unproven(tmp_path)

    shown = {cid: passed_unbuilt.shown(saved["criteria"][cid]["status"], cid, unproven) for cid in SPRINT}

    assert shown["AC-14"] != "PASSED" and shown["AC-15"] != "PASSED" and shown["AC-12"] != "PASSED"
    assert shown["AC-1"] == "FAILED"


def test_the_foundation_rule_does_not_count_them_as_the_sprint_s_passes(tmp_path):
    _locked_with_nothing_built(tmp_path)
    sprints = [SimpleNamespace(criteria=SPRINT, dependencies=[]),
               SimpleNamespace(criteria=["AC-2"], dependencies=["Sprint 1"])]

    reasons = foundation.later_work_needs(sprints, 0, suite.last_result(tmp_path), ["AC-1", "AC-8", "AC-13"], SPRINT,
                                          passed_unbuilt=passed_unbuilt.names(tmp_path))

    assert any("passes 1 of its 21 acceptance tests" in reason for reason in reasons)


def test_the_time_budget_names_them_beside_what_still_fails(tmp_path):
    _locked_with_nothing_built(tmp_path)

    why = sprint_time_budget.Budget(minutes=389, limit=218, size=6, due=tuple(SPRINT)).why(tmp_path)

    assert "AC-14" in why and "AC-15" in why
    assert not BANNED.search(passed_unbuilt.SAID)


def test_nothing_is_kept_once_something_is_built(tmp_path):
    tests = [SimpleNamespace(name=name, outcome="passed") for name in AT_THE_LOCK]

    passed_unbuilt.record(tmp_path, SimpleNamespace(ran=True, report=SimpleNamespace(tests=tests)),
                          nothing_built=False)

    assert passed_unbuilt.names(tmp_path) == set()
