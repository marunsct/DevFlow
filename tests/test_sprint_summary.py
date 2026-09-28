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

from app.agents.sprint_summary import (
    LONGEST_FEATURE_LINE,
    _one_line,
    count_test_cases,
    render_sprint_summary,
)


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


class TestEverySprintEndingIsRecorded:
    """A sprint that ends must leave a summary, whichever way it ended.

    The summary is written at each ending rather than in one place, because the
    figures it needs - the attempt's defects, its rounds, the plan it was
    working to - are on the state at that moment. The cost of that is one more
    ending to forget, and `one run` found the one that was: the milestone
    review ran out of revisions, the run stopped, and `docs/` held the plan, the
    review and the specification with no `sprint_1_summary.md` beside them.

    This counts the endings in the source instead of trusting that list, so a
    seventh ending has to be added here too.
    """

    def _workflow_source(self) -> str:
        import inspect

        from app.graph import workflow

        return inspect.getsource(workflow)

    def test_the_review_revision_limit_records_one(self):
        """The ending one run took."""
        source = self._workflow_source()
        limit_block = source[source.index("revision_count >= MAX_MILESTONE_REVISIONS"):]
        limit_block = limit_block[: limit_block.index("return _handing_on(")]

        assert "_record_sprint_summary(" in limit_block, (
            "a sprint that ends because the review ran out of revisions leaves no summary"
        )

    def test_completion_records_the_final_sprint(self):
        source = self._workflow_source()
        complete = source[source.index("def complete_node("):]
        complete = complete[: complete.index("def failed_node(")]

        assert "_record_sprint_summary(" in complete, (
            "the last sprint never advances, so completion is where its summary comes from"
        )

    def test_every_recorded_summary_is_carried_into_the_state(self):
        """A summary that is not returned is a summary the next attempt cannot see.

        `_record_sprint_summary` returns the `sprint_attempts` update, and an
        attempt that is not checkpointed is one the re-run cannot append to - it
        would overwrite the document instead, which is the fault the attempt list
        exists to fix.
        """
        import re

        source = self._workflow_source()
        calls = [
            line.strip()
            for line in source.splitlines()
            if "_record_sprint_summary(" in line and "def " not in line
        ]
        # Each call must bind its result; a bare call throws the update away.
        unbound = [
            line for line in calls
            if not re.match(r"^(summary\s*=|return \{\*\*_record_sprint_summary)", line)
        ]

        assert not unbound, f"these calls discard the attempt list: {unbound}"


class TestFeaturesReadAsAList:
    """`features` is the delegated task text, and a task is not a feature line.

    Measured on one run's `sprint_1_summary.md`, live. Two delegated tasks
    rendered as an 18-line "Features Implemented" section in which the second
    task began inside the first one's acceptance-criteria list, because that
    list is written with `-` and Markdown had no reason to think otherwise.
    Nothing was wrong with the data; a reader could not see two features in it.
    """

    A_TASK = """Modify index.html: add a viewport meta tag before the CSP meta tag. Ensure the existing CSP meta tag remains unchanged.

Modify style.css: add media queries for screen widths under 600px.

Acceptance criteria:
- index.html contains the viewport meta tag as specified.
- style.css includes at least one media query for max-width 600px."""

    def test_a_multi_paragraph_task_becomes_one_line(self):
        line = _one_line(self.A_TASK)

        assert "\n" not in line
        assert line.startswith("Modify index.html:")

    def test_the_acceptance_criteria_list_is_left_out(self):
        """It is what turned two features into one bullet."""
        line = _one_line(self.A_TASK)

        assert "Acceptance criteria" not in line
        assert "max-width 600px" not in line

    def test_two_tasks_render_as_two_bullets(self):
        document = render_sprint_summary(
            sprint_number=1,
            total_sprints=6,
            goal="Set up the project",
            planned=["Create the project directory"],
            attempts=[{
                "sprint_index": 0,
                "number": 1,
                "status": "Completed",
                "reason": "",
                "cases": {"tests": 3, "passed": 3, "failed": 0},
                "rounds": 2,
                "features": [self.A_TASK, "In main.js, implement add(), edit() and delete()."],
                "defects": [],
                "ended_at": "2026-09-26T09:00:00+00:00",
            }],
        )
        section = document.split("## Features Implemented", 1)[1].split("##", 1)[0]
        bullets = [line for line in section.splitlines() if line.startswith("- ")]

        assert len(bullets) == 2, section

    def test_a_failed_sprint_does_not_claim_the_work_was_implemented(self):
        """`features` is what the milestone delegated, not what passed.

        Measured on one run, which failed its first sprint with
        `index.html references style.css which does not exist` as a blocking
        finding, while this section read "Create style.css with basic
        responsive CSS rules". Nothing in the state records per-task
        completion, so the honest move is to say what the list is.

        The heading stays: it is the one `SprintSummaryPanel` parses and it
        came with the feature. The qualification goes in the body, and not as a
        bullet, because the UI keeps only lines that start with one.
        """
        document = render_sprint_summary(
            sprint_number=1,
            total_sprints=6,
            goal="Implement CRUD",
            planned=["Add index.html, style.css, app.js"],
            attempts=[{
                "sprint_index": 0,
                "number": 1,
                "status": "Failed",
                "reason": "the milestone review still required changes after 3 revisions",
                "cases": {"tests": 1, "passed": 0, "failed": 1},
                "rounds": 3,
                "features": ["Create style.css with basic responsive CSS rules."],
                "defects": [],
                "ended_at": "2026-09-27T01:00:00+00:00",
            }],
        )
        section = document.split("## Features Implemented", 1)[1].split("##", 1)[0]

        assert "not a record of what passed" in section
        assert "Create style.css" in section, "the tasks are still listed"
        assert not any(
            line.startswith("- ") and "not a record" in line
            for line in section.splitlines()
        ), "the qualifier must not be a bullet, or the UI lists it as a feature"

    def test_a_completed_sprint_is_not_qualified(self):
        """A sprint that passed its review needs no caveat on its own work."""
        document = render_sprint_summary(
            sprint_number=1,
            total_sprints=6,
            goal="Implement CRUD",
            planned=["Add index.html"],
            attempts=[{
                "sprint_index": 0,
                "number": 1,
                "status": "Completed",
                "reason": "",
                "cases": {"tests": 6, "passed": 6, "failed": 0},
                "rounds": 2,
                "features": ["Create index.html."],
                "defects": [],
                "ended_at": "2026-09-27T01:00:00+00:00",
            }],
        )
        section = document.split("## Features Implemented", 1)[1].split("##", 1)[0]

        assert "not a record of what passed" not in section

    def test_a_short_task_is_left_exactly_as_it_is(self):
        assert _one_line("Add a filter for completed tasks.") == (
            "Add a filter for completed tasks."
        )

    def test_a_long_line_is_cut_at_the_last_sentence_end_that_fits(self):
        """A whole thought, and as many of them as the line holds."""
        first = "Implement the add, edit and delete handlers in the main module."
        second = "Keep the existing storage helpers untouched while doing it."
        line = _one_line(f"{first} {second} " + "and a trailing clause " * 12)

        assert line == f"{first} {second}"
        assert not line.endswith("\u2026"), "a clean sentence cut needs no marker"

    def test_a_first_sentence_too_short_to_carry_the_line_does_not_win(self):
        """Cutting to "Fix it." would lose everything a reader needed.

        The line is filled and marked instead. Marked, because it no longer ends
        where the sentence did.
        """
        line = _one_line("Fix it. " + "and then a much longer clause " * 12)

        assert line.startswith("Fix it. and then")
        assert line.endswith("\u2026")

    def test_a_cut_is_always_marked(self):
        """A truncation with no marker reads as the whole text."""
        line = _one_line(" ".join(["word"] * 200))

        assert line.endswith("\u2026")
        assert len(line) <= LONGEST_FEATURE_LINE + 1

    def test_an_unbroken_string_is_still_cut_and_marked(self):
        """No spaces means no word boundary, and it must still not run on."""
        line = _one_line("x" * 500)

        assert line.endswith("\u2026")
        assert len(line) <= LONGEST_FEATURE_LINE + 2

    def test_leading_blank_lines_are_skipped(self):
        assert _one_line("\n\n   Real content here.  ") == "Real content here."

    def test_nothing_at_all_stays_nothing(self):
        """`_bullets` drops empties, so this must not become a bullet of its own."""
        assert _one_line("") == ""
        assert _one_line("   \n  \n ") == ""


class TestTheAttemptsLineCountsWhatCameBefore:
    """"re-run after N failed attempts" means N attempts came first.

    `failures` counted every attempt whose status is not Completed, and `latest`
    is `attempts[-1]` - so the current attempt was counted among the failures
    that preceded it. Wrong exactly when this attempt also failed, which is the
    case a reader most needs right.

    One run's sprint 1, its second and final attempt, read

        **Attempts:** 2 (re-run after 2 failed attempts at this same sprint)

    with one attempt behind it.
    """

    def _attempts_line(self, attempts):
        from app.agents.sprint_summary import render_sprint_summary

        text = render_sprint_summary(
            sprint_number=1, total_sprints=2, goal="g", planned=["a"], attempts=attempts
        )
        return next(l for l in text.splitlines() if l.startswith("**Attempts:"))

    def test_the_line_run_6e50b630_got(self):
        """Two attempts, both failed: one failure came before this one."""
        line = self._attempts_line(
            [{"number": 1, "status": "Failed"}, {"number": 2, "status": "Failed"}]
        )

        assert line == (
            "**Attempts:** 2 (re-run after 1 failed attempt at this same sprint)"
        )

    def test_three_attempts_all_failed(self):
        line = self._attempts_line([{"number": n, "status": "Failed"} for n in (1, 2, 3)])

        assert "re-run after 2 failed attempts" in line

    def test_a_re_run_that_succeeded_is_unchanged(self):
        """This case was already right and must stay right."""
        line = self._attempts_line(
            [{"number": 1, "status": "Failed"}, {"number": 2, "status": "Completed"}]
        )

        assert "re-run after 1 failed attempt" in line

    def test_three_attempts_ending_in_success(self):
        line = self._attempts_line(
            [
                {"number": 1, "status": "Failed"},
                {"number": 2, "status": "Failed"},
                {"number": 3, "status": "Completed"},
            ]
        )

        assert "re-run after 2 failed attempts" in line

    def test_the_singular_is_used_for_one(self):
        line = self._attempts_line(
            [{"number": 1, "status": "Failed"}, {"number": 2, "status": "Failed"}]
        )

        assert "1 failed attempt at" in line
        assert "attempts at" not in line

    def test_a_single_attempt_still_says_no_re_run(self):
        assert self._attempts_line([{"number": 1, "status": "Failed"}]) == (
            "**Attempts:** 1 (no re-run)"
        )

    def test_the_count_itself_is_every_attempt(self):
        """The headline number is all of them, including this one."""
        line = self._attempts_line([{"number": n, "status": "Failed"} for n in (1, 2, 3)])

        assert line.startswith("**Attempts:** 3 ")

    def test_an_earlier_attempt_with_no_status_counts_as_a_failure(self):
        """An attempt that recorded nothing did not complete."""
        line = self._attempts_line([{"number": 1}, {"number": 2, "status": "Failed"}])

        assert "re-run after 1 failed attempt" in line
