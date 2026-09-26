"""A sprint summary has to answer what the sprint promised and what proved it.

The first version answered neither. It carried a goal, a status, a count of test
*rounds* and a count of defects - so a reader could see that three rounds ran
and not whether a single test case passed. And because it was written to
`docs/sprint_{N}_summary.md` on every attempt, a sprint that failed and was
re-planned overwrote its own failure: the document said "Completed" and nothing
recorded that it had taken two attempts to get there, which is why a run that
worked through five milestones against a three-sprint plan looked like it had
invented two extra sprints.
"""

from __future__ import annotations

import pytest

from app.agents.sprint_summary import count_test_cases, render_sprint_summary


def _run(at: str, tests: int, passed: int, failed: int) -> dict:
    return {"at": at, "command": ["npm", "test"], "returncode": 0,
            "tests": tests, "passed": passed, "failed": failed}


class TestCountingCases:
    def test_the_last_run_is_the_result_not_the_sum_of_every_round(self):
        """Three rounds of a 31-case suite is 31 cases, not 93.

        A sprint runs its suite once per remediation round and the ledger keeps
        every one. Summing them reports a suite several times the size of the
        one that exists, and the number a reader wants from "how many test
        cases" is the state the sprint ended in.
        """
        entries = [
            _run("2026-09-26T01:00:00+00:00", 31, 20, 11),
            _run("2026-09-26T02:00:00+00:00", 31, 28, 3),
            _run("2026-09-26T03:00:00+00:00", 31, 31, 0),
        ]

        assert count_test_cases(entries) == {"tests": 31, "passed": 31, "failed": 0}

    def test_an_attempt_is_counted_from_where_the_last_one_ended(self):
        """A re-run reports its own suite, not the failed attempt's."""
        entries = [
            _run("2026-09-26T01:00:00+00:00", 31, 28, 3),
            _run("2026-09-26T05:00:00+00:00", 34, 34, 0),
        ]

        assert count_test_cases(entries, since="2026-09-26T04:00:00+00:00") == {
            "tests": 34, "passed": 34, "failed": 0
        }

    def test_commands_that_are_not_test_runs_are_ignored(self):
        entries = [
            {"at": "2026-09-26T01:00:00+00:00", "command": ["ls"], "returncode": 0},
            {"at": "2026-09-26T02:00:00+00:00", "command": ["npm", "install"], "returncode": 0},
        ]

        assert count_test_cases(entries) is None

    def test_no_counts_is_none_rather_than_zero(self):
        """A runner this ledger cannot parse must not read as an empty suite.

        `{"tests": 0, "passed": 0, "failed": 0}` and "nobody measured" are
        different facts, and the summary says so in different words. Reporting
        zero would make a sprint that tested a language the count parser does
        not know look like a sprint that ran no tests.
        """
        assert count_test_cases([]) is None
        assert count_test_cases(None) is None

    def test_an_entry_without_a_timestamp_is_kept(self):
        """A missing `at` is not evidence of belonging to an earlier attempt."""
        entries = [{"command": ["pytest"], "tests": 4, "passed": 4, "failed": 0}]

        assert count_test_cases(entries, since="2026-09-26T04:00:00+00:00") == {
            "tests": 4, "passed": 4, "failed": 0
        }


def _attempt(number: int, status: str, **extra) -> dict:
    base = {
        "sprint_index": 1, "number": number, "status": status, "reason": "",
        "cases": None, "rounds": 0, "features": [], "defects": [],
        "ended_at": f"2026-09-26T0{number}:00:00+00:00",
    }
    base.update(extra)
    return base


class TestRendering:
    def test_the_heading_states_the_sprint_s_place_in_the_plan(self):
        """So "how many sprints were planned" is answerable from one file.

        The count was only derivable by listing how many summary documents
        existed, which counts what a run got through rather than what it
        planned - and those differ exactly when a sprint is re-run.
        """
        document = render_sprint_summary(
            sprint_number=2, total_sprints=3, goal="Users can filter tasks",
            planned=["Filter control", "Filter persists"],
            attempts=[_attempt(1, "Completed")],
        )

        assert document.startswith("# Sprint 2 of 3 Summary")

    def test_a_single_attempt_says_so_rather_than_saying_nothing(self):
        document = render_sprint_summary(
            sprint_number=1, total_sprints=1, goal="g", planned=["p"],
            attempts=[_attempt(1, "Completed")],
        )

        assert "**Attempts:** 1 (no re-run)" in document

    def test_a_re_run_keeps_the_failed_attempt_and_its_reason(self):
        """The whole point: the second attempt must not erase the first."""
        document = render_sprint_summary(
            sprint_number=2, total_sprints=3, goal="Users can filter tasks",
            planned=["Filter control"],
            attempts=[
                _attempt(1, "Failed", reason="exhausted remediation attempts",
                         cases={"tests": 31, "passed": 28, "failed": 3}, rounds=3,
                         defects=[{"status": "open", "description": "filter drops completed",
                                   "owner": "testing"}]),
                _attempt(2, "Completed", cases={"tests": 34, "passed": 34, "failed": 0}, rounds=2),
            ],
        )

        assert "**Status:** Completed" in document
        assert "**Attempts:** 2 (re-run after 1 failed attempt at this same sprint)" in document
        assert "## Attempt History" in document
        assert "exhausted remediation attempts" in document
        assert "31 (28 passed, 3 failed)" in document
        assert "34 (34 passed, 0 failed)" in document

    def test_the_headline_counts_are_the_cases_not_the_rounds(self):
        document = render_sprint_summary(
            sprint_number=1, total_sprints=2, goal="g", planned=["p"],
            attempts=[_attempt(1, "Completed", cases={"tests": 12, "passed": 11, "failed": 1}, rounds=2)],
        )

        assert "**Test Cases:** 12" in document
        assert "- **Passed:** 11" in document
        assert "- **Failed:** 1" in document
        assert "- **Rounds Completed:** 2" in document

    def test_an_unmeasured_suite_says_so_instead_of_reporting_zero(self):
        document = render_sprint_summary(
            sprint_number=1, total_sprints=1, goal="g", planned=["p"],
            attempts=[_attempt(1, "Completed")],
        )

        assert "**Test Cases:** not reported" in document

    def test_what_was_planned_and_what_was_built_are_separate_sections(self):
        """Delegated tasks are what the milestone chose, not what was promised."""
        document = render_sprint_summary(
            sprint_number=1, total_sprints=1, goal="Users can add a task",
            planned=["An add control", "The task persists"],
            attempts=[_attempt(1, "Completed", features=["Wire the add handler"])],
        )

        assert "## Planned for This Sprint" in document
        assert "- An add control" in document
        assert "## Features Implemented" in document
        assert "- Wire the add handler" in document

    @pytest.mark.parametrize("field", [
        "**Goal:**", "**Status:**", "## Features Implemented",
        "- **Rounds Completed:**", "- **Total Bugs Found:**",
        "- **Bugs Fixed:**", "- **Bugs Open:**", "### Defect Summary",
    ])
    def test_the_fields_the_dashboard_parses_are_all_present(self, field):
        """`SprintSummaryPanel.tsx` reads this document by prefix match.

        It is a parser with no schema, in another language, that fails silently
        by showing zeroes. Every prefix it looks for is asserted here so a
        change to the wording of this document cannot quietly empty the panel.
        """
        document = render_sprint_summary(
            sprint_number=1, total_sprints=1, goal="g", planned=["p"],
            attempts=[_attempt(1, "Completed",
                               defects=[{"status": "fixed", "description": "d", "owner": "o"}])],
        )

        assert field in document

    def test_a_defect_line_matches_what_the_dashboard_matches(self):
        document = render_sprint_summary(
            sprint_number=1, total_sprints=1, goal="g", planned=["p"],
            attempts=[_attempt(1, "Failed", reason="r",
                               defects=[{"status": "open", "description": "it drops tasks",
                                         "owner": "testing"}])],
        )

        assert "- [OPEN] it drops tasks (Owner: testing)" in document

    def test_an_attempt_missing_every_optional_key_still_renders(self):
        """This runs after the outcome is decided and must never be the failure."""
        document = render_sprint_summary(
            sprint_number=1, total_sprints=0, goal="", planned=[], attempts=[{}],
        )

        assert "# Sprint 1 Summary" in document
        assert "Unknown goal" in document
