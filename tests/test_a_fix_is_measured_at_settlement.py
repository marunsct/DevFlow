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


# --- Initiative AO.1: the edges of the measurement -------------------------------

from app.ci import WHERE  # noqa: E402


def test_a_skipped_test_is_neither_the_fixer_s_failure_nor_its_proof(tmp_path) -> None:
    """Only skipped tests name the criterion: the snapshot cannot say, and today's behaviour stands."""
    defect = _settle(tmp_path, {f"tests/acceptance/ac-3.spec.ts{WHERE}AC-3 lists a new note": "skipped"})
    assert defect.status == "fixed"


def test_a_skipped_test_beside_a_passing_one_does_not_hold_the_fix_open(tmp_path) -> None:
    defect = _settle(tmp_path, {
        f"tests/acceptance/ac-3.spec.ts{WHERE}AC-3 lists a new note": "passed",
        f"tests/acceptance/ac-3.spec.ts{WHERE}AC-3 on a phone": "skipped",
    })
    assert defect.status == "fixed"


def test_a_failing_test_is_still_a_failure_beside_a_skipped_one(tmp_path) -> None:
    defect = _settle(tmp_path, {
        f"tests/acceptance/ac-3.spec.ts{WHERE}AC-3 lists a new note": "failed",
        f"tests/acceptance/ac-3.spec.ts{WHERE}AC-3 on a phone": "skipped",
    })
    assert defect.status != "fixed"


def _about(files, description="The note store loses the last note on save"):
    return _defect(description).model_copy(update={"affected_files": files})


def test_another_file_s_failing_unit_test_does_not_hold_this_defect_open(tmp_path) -> None:
    defect = _settle(
        tmp_path, {}, defect=_about(["src/store.ts"]),
        unit={f"tests/store.test.ts{WHERE}keeps every note": "passed",
              f"tests/render.test.ts{WHERE}draws the list": "failed"},
    )
    assert defect.status == "fixed"


def test_a_failing_unit_test_about_this_defect_s_file_holds_it_open(tmp_path) -> None:
    defect = _settle(
        tmp_path, {}, defect=_about(["src/store.ts"]),
        unit={f"tests/store.test.ts{WHERE}keeps every note": "failed"},
    )
    assert defect.status != "fixed"


def test_no_unit_test_about_its_files_means_the_snapshot_cannot_say(tmp_path) -> None:
    defect = _settle(
        tmp_path, {}, defect=_about(["src/store.ts"]),
        unit={f"tests/render.test.ts{WHERE}draws the list": "failed"},
    )
    assert defect.status == "fixed"


def test_a_defect_naming_no_file_is_still_measured_by_every_unit_test(tmp_path) -> None:
    defect = _settle(
        tmp_path, {}, defect=_about([]),
        unit={f"tests/render.test.ts{WHERE}draws the list": "failed"},
    )
    assert defect.status != "fixed"


def test_a_fix_whose_own_tests_still_fail_is_recorded_as_that_even_naming_no_test(tmp_path, monkeypatch) -> None:
    """Measured live: three fixes of "the unit tests fail" were each recorded as
    "the fix named no regression test" while the measurement after each showed its
    unit tests still failing - the record named the lesser reason."""
    from app.graph.workflow import UNIT_TESTS_FAIL
    from app.observability import defect_ledger

    noted = []
    monkeypatch.setattr(defect_ledger, "note", lambda event, stage, **kw: noted.append((event, kw.get("detail"))))
    ci.save(tmp_path, ci.Snapshot(label=LABEL, unit={"tests/test_auth.py::test_login": "failed"}, unit_ran=True))
    defect = _defect(f"{UNIT_TESTS_FAIL} The runner's output ends: 1 failed")
    defect.regression_test_required = True
    cycle = RemediationCycle(sprint_goal="g", defects=[defect])
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "specialist_outputs": {}}
    fix = SpecialistOutput(changed_files=["app/schemas.py"], tests=[])

    _settle_the_fix(state, cycle, 0, "defect_fix_1_0", fix, measured=LABEL)

    assert noted == [("left open", "its own tests still fail, measured after the fix")]
