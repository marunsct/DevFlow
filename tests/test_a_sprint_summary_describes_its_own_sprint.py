"""The sprint summary must describe the sprint it is named after.

Two faults, both measured live on one run's `sprint_1_summary.md`, in the
one document a reader opens to find out what a sprint did.

The header said:

    # Sprint 1 of 2 Summary
    **Goal:** Wire filter button functionality and inline edit UI to complete
              the full CRUD workflow described in the product intake.

That was the *third* milestone plan's goal. Sprint 1's goal, from the sprint
plan, was "Users can add tasks with title validation, toggle completion, delete
tasks, and have all changes persist across page refreshes" - and "Planned for
This Sprint", two lines below, correctly listed sprint 1's scope. A milestone
plan is re-stored on every revision and the lead may restate the goal each
time, so a sprint that gets sent back ends up summarised under whichever goal
the last revision happened to carry. Here that goal belonged to sprint 2.

And its "Features Implemented" section read:

    - Create the following changes in two files:
    - Modify simple-to-do-list/app.js to wire filter buttons, ...
    - Create changes to two files:

Two of three bullets named no file and no change. Each is the first non-blank
line of a delegated task, and a line ending in a colon announces a list rather
than naming anything.
"""

from __future__ import annotations

from app.agents.sprint_summary import LONGEST_FEATURE_LINE, _one_line


class TestAFeatureLineNamesSomething:
    #: The task description that produced the empty bullet, in the shape the
    #: lead wrote it.
    A_TASK_WITH_A_PREAMBLE = (
        "Create the following changes in two files:\n"
        "\n"
        "1. index.html - Update CSP meta tag only (line 7):\n"
        "   Change content attribute to add upgrade-insecure-requests.\n"
    )

    def test_a_line_that_only_announces_a_list_is_not_the_feature(self) -> None:
        line = _one_line(self.A_TASK_WITH_A_PREAMBLE)

        assert line != "Create the following changes in two files:"
        assert "index.html" in line, (
            "the bullet still names no file, so it tells a reader nothing"
        )

    def test_a_colon_line_that_does_name_something_keeps_it(self) -> None:
        """A colon is not always an empty preamble.

        Appending rather than skipping is what keeps this one whole.
        """
        line = _one_line("Wire filter buttons in init():\n   Read data-filter.")

        assert line.startswith("Wire filter buttons in init():")

    def test_a_preamble_with_nothing_after_it_is_left_alone(self) -> None:
        assert _one_line("Create the following changes:") == (
            "Create the following changes:"
        )

    def test_the_joined_line_still_obeys_the_length_rules(self) -> None:
        line = _one_line("Do these things:\n" + "and a much longer clause " * 20)

        assert len(line) <= LONGEST_FEATURE_LINE + 2
        assert "\n" not in line

    def test_an_ordinary_first_line_is_untouched(self) -> None:
        """The path every other task takes must not change."""
        assert _one_line("Add a filter for completed tasks.") == (
            "Add a filter for completed tasks."
        )


class TestTheGoalIsTheSprintsOwn:
    """`_record_sprint_summary` must prefer the sprint plan's goal."""

    def test_a_revised_milestone_does_not_rename_the_sprint(self, tmp_path, monkeypatch) -> None:
        """A sprint sent back for revision is summarised under its own goal,
        not whatever the last revision of the milestone plan restated."""
        from types import SimpleNamespace

        from app.graph import workflow

        written = {}
        monkeypatch.setattr(workflow, "_record_document", lambda state, path, text: written.update({path: text}))
        monkeypatch.setattr(workflow, "_the_accepted_counts", lambda root, *which: None)
        state = {
            "repository": SimpleNamespace(root_path=str(tmp_path)),
            "current_sprint_index": 0,
            "sprint_plan": SimpleNamespace(sprints=[
                SimpleNamespace(goal="Users can add, toggle and delete tasks that persist.", in_scope=["Build the page"]),
                SimpleNamespace(goal="Wire filter buttons and inline edit.", in_scope=["Filters"]),
            ]),
            "milestone_plan": SimpleNamespace(delegated_tasks=[],
                                              selected_sprint_goal="Wire filter button functionality and inline edit UI."),
        }

        workflow._record_sprint_summary(state, "Completed")

        document = written["docs/sprint_1_summary.md"]
        assert "**Goal:** Users can add, toggle and delete tasks that persist." in document
        assert "Wire filter button" not in document, (
            "the milestone plan's goal is preferred, so a sprint sent back for "
            "revision is summarised under whatever the last revision restated"
        )

        # With no sprint plan to say otherwise, the milestone's goal still names it.
        written.clear()
        workflow._record_sprint_summary({**state, "sprint_plan": None}, "Completed")
        assert "**Goal:** Wire filter button functionality and inline edit UI." in written["docs/sprint_1_summary.md"]

    def test_the_sprint_plan_goal_is_used_when_both_exist(self, tmp_path) -> None:
        """Through the renderer, with the two goals different.

        `render_sprint_summary` takes the goal it is given, so this pins the
        choice made in `_record_sprint_summary` at the point it reaches a reader.
        """
        from app.agents.sprint_summary import render_sprint_summary

        document = render_sprint_summary(
            sprint_number=1,
            total_sprints=2,
            goal="Users can add, toggle and delete tasks that persist.",
            planned=["Build index.html", "Build app.js"],
            attempts=[
                {
                    "number": 1,
                    "status": "Completed",
                    "cases": {"tests": 75, "passed": 75, "failed": 0},
                    "rounds": 5,
                    "features": ["Modify app.js to wire the filter buttons."],
                    "defects": [],
                }
            ],
        )

        assert "**Goal:** Users can add, toggle and delete tasks" in document
        assert "Wire filter button" not in document
