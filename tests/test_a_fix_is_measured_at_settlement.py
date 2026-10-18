"""A defect closes on its own tests passing after the fix, not on the fixer naming one.

A fix that broke nothing was settled as "fixed" when the fixer named a test
and reported no blocker; what the execution ledger confirmed was an info log.
The harness had already measured the fix: `engineering.after_a_fix` runs the
unit and acceptance suites and keeps the snapshot. Nothing read the defect's
own tests in it, so a fix whose criterion still failed was closed, found
again by the next test round, and charged as another failed attempt a round
late.

So settlement reads the defect's tests in the snapshot its fix just took: green
closes it, red leaves it open and counts the failed attempt now, and a
snapshot that cannot say keeps today's behaviour.
"""

from __future__ import annotations

from types import SimpleNamespace

from app import ci
from app.agents.specialists import SpecialistOutput
from app.graph.workflow import _settle_the_fix
from app.sprint import Defect, RemediationCycle

LABEL = "after defect_fix_1_0"


def _defect(description: str = "AC-3: adding a note does not show it in the list") -> Defect:
    return Defect(
        description=description,
        severity="major",
        reproduction_steps="add a note",
        expected_behavior="it is listed",
        actual_behavior="it is not",
        owner="backend",
        regression_test_required=False,
    )


def _settle(tmp_path, acceptance: dict[str, str], *, label: str = LABEL, defect: Defect | None = None, unit=None):
    ci.save(
        tmp_path,
        ci.Snapshot(
            label=label, acceptance=acceptance, acceptance_ran=bool(acceptance),
            unit=unit or {}, unit_ran=bool(unit),
        ),
    )
    cycle = RemediationCycle(sprint_goal="g", defects=[defect or _defect()])
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "specialist_outputs": {}}
    fix = SpecialistOutput(changed_files=["src/notes.ts"], tests=["notes list test"])
    update, _ = _settle_the_fix(state, cycle, 0, "defect_fix_1_0", fix, measured=LABEL)
    return update["remediation"].defects[0]


def test_a_fix_whose_own_test_still_fails_is_left_open(tmp_path) -> None:
    defect = _settle(tmp_path, {"tests/acceptance/ac-3.spec.ts::AC-3 lists a new note": "failed"})
    assert defect.status != "fixed"


def test_the_failed_attempt_is_counted_at_once(tmp_path) -> None:
    defect = _settle(tmp_path, {"tests/acceptance/ac-3.spec.ts::AC-3 lists a new note": "failed"})
    assert defect.fix_attempts == 1


def test_a_fix_whose_own_tests_pass_is_fixed(tmp_path) -> None:
    defect = _settle(tmp_path, {
        "tests/acceptance/ac-3.spec.ts::AC-3 lists a new note": "passed",
        "tests/acceptance/ac-4.spec.ts::AC-4 deletes a note": "failed",
    })
    assert defect.status == "fixed"


def test_a_snapshot_from_another_moment_does_not_decide(tmp_path) -> None:
    """A stale snapshot measured some other change; today's behaviour stands."""
    defect = _settle(
        tmp_path, {"tests/acceptance/ac-3.spec.ts::AC-3 lists a new note": "failed"}, label="before defect_fix_1_0",
    )
    assert defect.status == "fixed"


def test_a_defect_naming_no_criterion_is_measured_by_the_unit_tests(tmp_path) -> None:
    defect = _settle(
        tmp_path, {}, defect=_defect("The note store loses the last note on save"),
        unit={"tests/store.test.ts::keeps every note": "failed"},
    )
    assert defect.status != "fixed"
