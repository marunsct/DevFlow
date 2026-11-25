"""A defect whose own tests measured passing after its fix is closed, whether or not the fix named a regression test.

Deep review 2026-11-18, item A7: 17 defects were left open as "the fix named no regression test" after 17-19 model calls
each, even when the defect's tests passed in the measurement taken after the fix. The regression test the harness
would like is now a note in the resolution; only a defect its measurement cannot answer for stays open on that rule.
"""
from __future__ import annotations

from types import SimpleNamespace

from app import ci
from app.agents.specialists import SpecialistOutput
from app.graph.workflow import _settle_the_fix
from app.sprint import Defect, RemediationCycle

LABEL = "after defect_fix_1_0"


def _settled(tmp_path, unit: dict[str, str]) -> Defect:
    ci.save(tmp_path, ci.Snapshot(label=LABEL, unit=unit, unit_ran=bool(unit)))
    defect = Defect(description="Saving a note loses its title", severity="major", reproduction_steps="save a note",
                    expected_behavior="the title is kept", actual_behavior="it is empty", owner="backend",
                    affected_files=["src/notes_store.py"], regression_test_required=True,
                    # Raised from its failing unit test, which is what answers for it (LF.1443).
                    kind="failing_test", evidence=[{"test": "test_keeps_the_title"}])
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "specialist_outputs": {}}
    fix = SpecialistOutput(changed_files=["src/notes_store.py"], tests=[], decisions=["kept the title on save"])

    update, _ = _settle_the_fix(state, RemediationCycle(sprint_goal="g", defects=[defect]), 0, "defect_fix_1_0", fix,
                                measured=LABEL)

    return update["remediation"].defects[0]


def test_a_defect_whose_own_tests_pass_is_closed_though_no_regression_test_was_named(tmp_path):
    defect = _settled(tmp_path, {"tests/test_notes_store.py › test_keeps_the_title": "passed"})

    assert defect.status == "fixed"
    assert "no regression test" in defect.resolution


def test_a_defect_its_measurement_cannot_answer_for_still_waits_for_a_named_test(tmp_path):
    defect = _settled(tmp_path, {"tests/test_other.py › test_something_else": "passed"})

    assert defect.status != "fixed"
