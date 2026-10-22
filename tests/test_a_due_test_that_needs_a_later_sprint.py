"""A test of a criterion due now that cannot pass before a later sprint.

Measured on one run. Its locked suite tagged two persistence tests with sprint
1's "a task cannot be added without a title"; they ticked "Done" and pressed
"Delete", which sprint 2's criteria name. Judged with sprint 1, they failed that
criterion, and sprint 1's fix stage built completion and deletion - sprint 2's
work - to make them pass, though it had been told which criteria were later.

A due criterion is now judged by its tests that can pass now. A test waits on a
later sprint when it carries a criterion not yet due, or quotes a control name
only later criteria quote.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.acceptance import junit, sprint_scope, suite
from app.acceptance.criteria import Criterion

PROJECT = "notes"

CRITERIA = [
    Criterion("AC-1", 'A note cannot be added without a heading; the "Add note" button refuses', "brief"),
    Criterion("AC-2", 'Each note has a checkbox labelled "Pinned"', "brief"),
    Criterion("AC-3", 'Each note has a button named "Remove" that removes it', "brief"),
    Criterion("AC-4", 'A button named "Add note" adds it', "brief"),
]

REFUSAL = """import { test, expect } from '@playwright/test';
test('[AC-1] an empty heading is refused', async ({ page }) => {
  await page.getByRole('button', { name: 'Add note' }).click();
});
"""

MIS_TAGGED = """import { test, expect } from '@playwright/test';
test('[AC-1] removing a note survives a reload', async ({ page }) => {
  await page.getByRole('button', { name: 'Remove' }).click();
});
test('[AC-1][AC-2] a pinned note keeps its heading', async ({ page }) => {
  await page.getByLabel('Pinned').check();
});
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / ".project-directory").write_text(f"{PROJECT}\n")
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "stack-pack.json").write_text(json.dumps({
        "pack": "any", "project": PROJECT, "acceptance_dir": "acceptance",
        "unit_report": "test-results/unit.xml", "acceptance_report": "test-results/acceptance.xml",
    }))
    suite_dir = tmp_path / PROJECT / "acceptance"
    suite_dir.mkdir(parents=True)
    (suite_dir / "refusal.spec.js").write_text(REFUSAL)
    (suite_dir / "persistence.spec.js").write_text(MIS_TAGGED)
    suite.save_criteria(tmp_path, CRITERIA)
    suite.lock(tmp_path)
    return tmp_path


def _sprint_one(root: Path) -> None:
    sprint_scope.record(root, sprint=1, of=2, not_yet_due=["AC-2", "AC-3"])


def _ran(*cases: tuple[str, bool]) -> suite.AcceptanceResult:
    report = junit.Report(found=True, tests=[
        junit.TestResult(name=name, outcome="passed" if passed else "failed", message="" if passed else "no")
        for name, passed in cases
    ])
    return suite.AcceptanceResult(ran=True, exit_code=1, command="npm run test:acceptance", report=report)


RUN = (
    ("[AC-1] an empty heading is refused", True),
    ("[AC-1] removing a note survives a reload", False),
    ("[AC-1][AC-2] a pinned note keeps its heading", False),
)


class TestWhichTestsWait:
    def test_a_test_that_drives_a_later_control_waits(self, root):
        _sprint_one(root)

        assert sprint_scope.waiting_tests(root)["[AC-1] removing a note survives a reload"] == ["AC-3"]

    def test_a_test_that_carries_a_later_criterion_waits(self, root):
        _sprint_one(root)

        assert sprint_scope.waiting_tests(root)["[AC-1][AC-2] a pinned note keeps its heading"] == ["AC-2"]

    def test_a_control_a_due_criterion_names_never_makes_one_wait(self, root):
        """"Add note" is quoted by AC-1 and AC-4 alike; AC-1 is due."""
        sprint_scope.record(root, sprint=1, of=2, not_yet_due=["AC-2", "AC-3", "AC-4"])

        assert "[AC-1] an empty heading is refused" not in sprint_scope.waiting_tests(root)

    def test_nothing_waits_in_the_last_sprint(self, root):
        sprint_scope.record(root, sprint=2, of=2, not_yet_due=[])

        assert sprint_scope.waiting_tests(root) == {}

    def test_a_runner_s_group_prefix_still_matches(self, root):
        _sprint_one(root)

        waiting = sprint_scope.waiting_tests(root)

        assert sprint_scope.waits_on("persistence.spec.js › [AC-1] removing a note survives a reload", waiting) == ["AC-3"]


class TestTheJudgement:
    def test_a_due_criterion_is_judged_by_the_tests_that_can_pass_now(self, root):
        _sprint_one(root)

        judged = suite._judged(root, _ran(*RUN), save=False)

        assert judged.criteria["AC-1"].status == "passed"
        assert [t["name"] for t in judged.criteria["AC-1"].tests] == ["[AC-1] an empty heading is refused"]

    def test_without_a_sprint_every_test_counts(self, root):
        judged = suite._judged(root, _ran(*RUN), save=False)

        assert judged.criteria["AC-1"].status == "failed"

    def test_in_the_last_sprint_every_test_counts(self, root):
        sprint_scope.record(root, sprint=2, of=2, not_yet_due=[])

        assert suite._judged(root, _ran(*RUN), save=False).criteria["AC-1"].status == "failed"

    def test_a_criterion_whose_every_test_waits_keeps_them(self, root):
        """Nothing else proves it: judged as before, so it is not passed by default."""
        _sprint_one(root)

        judged = suite._judged(root, _ran(*RUN[1:]), save=False)

        assert judged.criteria["AC-1"].status == "failed"

    def test_a_later_criterion_is_still_reported(self, root):
        _sprint_one(root)

        assert suite._judged(root, _ran(*RUN), save=False).criteria["AC-2"].status == "failed"


class TestWhatAStageIsTold:
    def test_a_failure_that_waits_is_named_a_later_sprints(self, root):
        _sprint_one(root)
        since = time.time() - 1
        path = root / PROJECT / "test-results" / "acceptance.xml"
        path.parent.mkdir(parents=True)
        path.write_text(
            '<testsuites><testsuite name="s">'
            '<testcase name="[AC-1] an empty heading is refused" classname="x"/>'
            '<testcase name="[AC-1] removing a note survives a reload" classname="x">'
            '<failure message="no">no</failure></testcase>'
            "</testsuite></testsuites>"
        )

        note = sprint_scope.note_on_failures(root, since)

        assert "Every failing test here (1) needs what a later sprint builds (AC-3)" in note

    def test_a_file_whose_every_test_waits_is_a_later_sprints(self, root):
        _sprint_one(root)

        assert sprint_scope.later_sprints_files(root) == {
            f"{PROJECT}/acceptance/persistence.spec.js": ["AC-2", "AC-3"]
        }


def _reports(root: Path, *cases: tuple[str, bool], unit: tuple[tuple[str, bool], ...] = ()) -> None:
    for name, rows in (("acceptance.xml", cases), ("unit.xml", unit)):
        if not rows:
            continue
        body = "".join(
            f'<testcase name="{title}" classname="x">' + ("" if ok else '<failure message="no">no</failure>') + "</testcase>"
            for title, ok in rows
        )
        path = root / PROJECT / "r" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'<testsuites><testsuite name="s">{body}</testsuite></testsuites>')


class TestOnlyLaterSprintsFail:
    """One run's `npm test` ran the whole acceptance suite after the unit tests,
    so sprint 2's round ended "exited 1" on sprint 3's tests alone - and the
    harness recorded that as a defect, which spent the attempt."""

    @pytest.fixture(autouse=True)
    def reports_where_the_contract_says(self, root):
        contract = json.loads((root / ".harness" / "stack-pack.json").read_text())
        contract.update({"unit_report": "r/unit.xml", "acceptance_report": "r/acceptance.xml"})
        (root / ".harness" / "stack-pack.json").write_text(json.dumps(contract))

    def test_failures_that_all_wait(self, root):
        _sprint_one(root)
        _reports(root, ("[AC-1] an empty heading is refused", True), ("[AC-1] removing a note survives a reload", False),
                 unit=(("unit test", True),))

        assert sprint_scope.only_later_sprints_fail(root)

    def test_a_failure_due_now(self, root):
        _sprint_one(root)
        _reports(root, ("[AC-1] an empty heading is refused", False), ("[AC-1] removing a note survives a reload", False))

        assert not sprint_scope.only_later_sprints_fail(root)

    def test_a_failing_unit_test(self, root):
        _sprint_one(root)
        _reports(root, ("[AC-1] removing a note survives a reload", False), unit=(("unit test", False),))

        assert not sprint_scope.only_later_sprints_fail(root)

    def test_no_failure_listed_is_not_only_later_failures(self, root):
        """A run that crashed lists nothing failed; that is its own failure."""
        _sprint_one(root)
        _reports(root, ("[AC-1] an empty heading is refused", True))

        assert not sprint_scope.only_later_sprints_fail(root)

    def test_the_last_sprint_has_no_later_failures(self, root):
        sprint_scope.record(root, sprint=2, of=2, not_yet_due=[])
        _reports(root, ("[AC-1] removing a note survives a reload", False))

        assert not sprint_scope.only_later_sprints_fail(root)

    def test_the_round_records_no_defect_for_them(self, root, monkeypatch):
        from app.graph.workflow import _a_suite_failure_the_round_did_not_report

        _sprint_one(root)
        _reports(root, ("[AC-1] removing a note survives a reload", False))
        monkeypatch.setattr(
            "app.graph.workflow._the_test_command_this_stage_left_failing", lambda root, stage: ("npm test", "exited 1")
        )

        assert _a_suite_failure_the_round_did_not_report(str(root), "test_round_2") is None

    def test_the_round_still_records_one_due_now(self, root, monkeypatch):
        from app.graph.workflow import _a_suite_failure_the_round_did_not_report

        _sprint_one(root)
        _reports(root, ("[AC-1] an empty heading is refused", False))
        monkeypatch.setattr(
            "app.graph.workflow._the_test_command_this_stage_left_failing", lambda root, stage: ("npm test", "exited 1")
        )

        assert _a_suite_failure_the_round_did_not_report(str(root), "test_round_2") is not None
