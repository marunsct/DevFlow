"""One problem reported by several checks is one defect, for one fixer.

Measured on one run: one colour a sprint's restyle had put back was reported by
the test round, the regression check, the code review and the page check - five
defects, five fix stages, the first of which fixed it and the rest of which
found nothing to do (two of them left "open" for it, and the attempt was spent).
"""

from __future__ import annotations

from app.agents.specialists import ReportedDefect
from app.graph.workflow import _one_defect_per_cause, _the_same_cause

STYLES = "app/styles.css"


def _d(description, files=(), source="test round", owner="ui_ux", severity="major"):
    return ReportedDefect(
        description=description, severity=severity, reproduction_steps="r", expected_behavior="e",
        actual_behavior="a", affected_files=list(files), owner=owner,
    ).model_copy(update={"source": source})


THE_RUNS_ROUND = [
    _d("WCAG AA contrast failure: #add-task-btn foreground/background contrast is 4.02:1", [STYLES]),
    _d("WCAG AA contrast failure: .filter-btn.active foreground/background contrast is 4.01:1", [STYLES]),
    _d("WCAG AA contrast failure: #empty-state foreground/background contrast is 2.85:1", [STYLES]),
    _d("Acceptance test logic error: expects 0 items after switching to the Active view", ["app/acceptance/views.spec.js"], owner="testing"),
    _d("Regression: `unit: test › #empty-state foreground/background contrast ≥ 4.5:1` passed before and fails now.", source="regression"),
    _d("Code review (Restyle the page (ui_ux)): The #empty-state color was changed back to #999999", [STYLES], source="code review", severity="blocking"),
    _d("An accessibility check of the page finds 1 serious or critical rule(s) broken: color-contrast.", source="page check"),
]


class TestTheRunsRound:
    def test_every_report_of_the_contrast_problem_is_one_defect(self):
        merged = _one_defect_per_cause(THE_RUNS_ROUND)

        assert len(merged) == 2
        assert merged[0].description.startswith("WCAG AA contrast failure: #add-task-btn")
        assert merged[1].description.startswith("Acceptance test logic error")

    def test_the_one_defect_carries_what_every_check_said(self):
        merged = _one_defect_per_cause(THE_RUNS_ROUND)[0]

        assert "The same problem, as other checks reported it:" in merged.description
        for source in ("[regression]", "[code review]", "[page check]"):
            assert source in merged.description

    def test_it_is_as_severe_as_the_most_severe_report(self):
        assert _one_defect_per_cause(THE_RUNS_ROUND)[0].severity == "blocking"

    def test_it_keeps_the_first_report_s_owner_and_every_file(self):
        merged = _one_defect_per_cause(THE_RUNS_ROUND)[0]

        assert merged.owner == "ui_ux"
        assert merged.affected_files == [STYLES]


class TestWhatStaysApart:
    def test_two_problems_in_one_file_named_differently(self):
        one = _d("Code review (ui_ux_0): The form handler does not check the input", ["app/src/app.js"], source="code review")
        other = _d("Code review (ui_ux_0): `titleError.textContent = err.message` shows the raw message", ["app/src/app.js"], source="code review")

        assert not _the_same_cause(one, other)

    def test_one_name_in_two_different_files(self):
        one = _d("`renderList` drops the last item", ["app/src/list.js"])
        other = _d("`renderList` is never exported", ["app/src/index.js"])

        assert not _the_same_cause(one, other)

    def test_two_criteria(self):
        assert len(_one_defect_per_cause([
            _d("[AC-3] Renaming does not work yet.", source="acceptance suite"),
            _d("[AC-10] The rename field is missing.", source="acceptance suite"),
        ])) == 2

    def test_a_name_whose_words_are_merely_mentioned(self):
        """`empty-state` is not matched by any text that says "state"."""
        one = _d("The #empty-state message is missing", [STYLES])
        other = _d("The saved state is lost on reload", [STYLES])

        assert not _the_same_cause(one, other)


class TestWhatIsOne:
    def test_a_regression_and_a_failing_criterion_of_one_test(self):
        merged = _one_defect_per_cause([
            _d("Regression: `acceptance: list.spec.js › [AC-4] removing an item` passed before and fails now.", source="regression"),
            _d("[AC-4] Removing items does not work yet.", source="acceptance suite"),
        ])

        assert len(merged) == 1

    def test_nothing_to_merge_is_left_as_it_was(self):
        reported = [_d("one thing"), _d("another")]

        assert _one_defect_per_cause(reported) == reported


def test_a_pack_contract_finding_leads_the_unit_test_symptom_it_is_merged_with():
    symptom = _d(
        "The unit tests fail. It says: SyntaxError: The requested module './app.ts' does not provide an export named "
        "'createApp'", ["notes-api/src/app.ts"], source="test round", owner="backend",
    )
    cause = _d(
        "notes-api/src/app.ts no longer exports `createApp`, which the scaffold's start file and unit smoke test import.",
        ["notes-api/src/app.ts"], source="pack contract", owner="backend",
    )

    merged = _one_defect_per_cause([symptom, cause])

    assert len(merged) == 1
    assert merged[0].description.startswith("notes-api/src/app.ts no longer exports `createApp`")


def test_a_folder_named_in_a_path_is_not_what_a_defect_is_about():
    # Measured on one run: "notes" in a criterion's `/notes/{id}` matched the project folder `notes-api` in the unit
    # run's paths. The criterion lost its own defect and shipped deferred after six fixes aimed at another file.
    unit = _d("The unit tests fail. It says: TypeError at notes-api/test/store.test.ts:12 and file:///w/notes-api/src/a.ts:3")
    criterion = _d("[AC-11] GET /notes/{id} answers 404 for an id that does not exist. Expected: 404, Received: 500")
    assert not _the_same_cause(unit, criterion)
    assert not _the_same_cause(criterion, unit)


def test_a_check_s_rule_named_on_its_own_is_still_matched():
    rule = _d("Page check: color-contrast fails on the home page")
    prose = _d("The contrast of the heading is too low on the home page")
    assert _the_same_cause(rule, prose)
