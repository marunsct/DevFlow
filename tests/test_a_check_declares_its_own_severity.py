"""Severity graded from prose can be lost by editing the prose.

`_severity_of` decides between BREAKS and untidy by matching a phrase from the
message against `_BREAKS_BEHAVIOUR`. A message that matches no marker is graded
untidy, silently, and the reviewer is handed "untidy rather than broken - dead
rules, unused files. Worth a minor finding, not a blocking one".

`integration_checks` records this happening three times in its own comments and
names it "the stale-marker failure this file is most exposed to". The test that
guards it checks every marker matches some message and, in its own words,
"cannot check that every breaking message matches some marker" - so the gap is
known and was not closeable from that direction.

run-6e50b630 is the fourth instance, and the most expensive.
`_a_control_group_no_script_operates` found `todo-app/index.html`'s three
`data-filter` buttons and reported that they

    render, respond to hover and do nothing when clicked

The marker is "does nothing when a user". This message says "do nothing when
clicked", so it was graded untidy, `problems_that_break_the_product` returned
nothing, the test round was never told - and the milestone reviewer raised the
same defect itself:

    [blocking] correctness: Filter functionality is entirely missing despite UI
    elements existing. Users see clickable filter buttons that do nothing.

three times, until the run hit the revision limit and failed. The harness proved
the defect and then talked itself out of it.

A registry entry can now declare its own floor. Attached to the check rather than
to its words, so no edit of a message can lose it.

Nothing here is about HTML or JavaScript. A dead control is the shape this one
check reads; the mechanism is about how any check's finding is graded.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _CHECKS,
    _FLOORS,
    _floor_of,
    _severity_of,
    problems_that_break_the_product,
    summarise_integration,
)

#: run-6e50b630's page, reduced to the shape that failed it: a wired page with
#: one dead corner.
A_PAGE_WITH_DEAD_FILTERS = """<!doctype html>
<html><head><link rel="stylesheet" href="style.css"></head>
<body>
  <form id="add-form"><input id="title"></form>
  <nav id="filter-bar">
    <button data-filter="all" class="filter-btn">All</button>
    <button data-filter="active" class="filter-btn">Active</button>
    <button data-filter="completed" class="filter-btn">Completed</button>
  </nav>
  <ul id="tasks"></ul>
  <script type="module" src="./app.js"></script>
</body></html>
"""

#: Wired for everything but the filters, which is why the "nothing is wired at
#: all" check stays quiet and this one has to speak.
A_SCRIPT_THAT_WIRES_EVERYTHING_ELSE = """
export function addTask(title) { return { title, completed: false }; }
export function init() {
  document.getElementById('add-form').addEventListener('submit', (e) => {
    e.preventDefault();
    addTask(document.getElementById('title').value);
    document.getElementById('tasks').textContent = 'rendered';
  });
}
init();
"""


@pytest.fixture
def the_workspace_that_failed(tmp_path):
    project = tmp_path / "todo-app"
    project.mkdir()
    (project / "index.html").write_text(A_PAGE_WITH_DEAD_FILTERS)
    (project / "app.js").write_text(A_SCRIPT_THAT_WIRES_EVERYTHING_ELSE)
    (project / "style.css").write_text(
        "#filter-bar { display: flex; }\n.filter-btn { padding: 4px; }\n#tasks { margin: 0; }\n"
        "#add-form { display: block; }\n#title { width: 100%; }\n"
    )
    return tmp_path


class TestTheRunThatFailed:
    def test_the_dead_controls_now_reach_the_breaking_tier(self, the_workspace_that_failed):
        """Which is the channel the test round is given, inside the sprint."""
        problems = problems_that_break_the_product(str(the_workspace_that_failed))

        assert any("data-filter" in problem for problem in problems), problems

    def test_the_summary_no_longer_calls_it_untidy(self, the_workspace_that_failed):
        summary = summarise_integration(str(the_workspace_that_failed), None, "")

        breaking = summary.split("DOES NOT WORK")[1] if "DOES NOT WORK" in summary else ""
        assert "data-filter" in breaking, summary

    def test_its_message_still_matches_no_marker(self):
        """The point of the mechanism: the wording did not have to change.

        If this ever starts returning BREAKS, a marker was added and this test
        no longer proves the floor is what did the work.
        """
        message = (
            "todo-app/index.html has 3 clickable controls carrying `data-filter`, "
            "and no script in this project mentions `data-filter`, their classes "
            "or their ids. A `data-` attribute on a button exists to be read by "
            "script, so these render, respond to hover and do nothing when clicked."
        )

        assert _severity_of(message) == "untidy"


class TestTheMechanism:
    def test_the_control_check_declares_a_floor(self):
        declared = [entry for entry in _CHECKS if _floor_of(entry) == "BREAKS"]

        assert declared, "no check declares a floor, so the mechanism is unused"
        assert any("clickable controls" in entry[0] for entry in declared)

    def test_a_check_with_no_floor_grades_by_its_message(self):
        assert _floor_of(("a description nothing declares", lambda *a: [])) == ""

    def test_every_declared_floor_names_a_real_check(self):
        """The one way this mechanism can be lost: a description renamed.

        A floor keyed on a description that no longer exists is a floor that
        silently stops applying, which is the failure the floor exists to end.
        Renaming a check must break this test rather than downgrade its finding.
        """
        registered = {entry[0] for entry in _CHECKS}

        for described in _FLOORS:
            assert described in registered, (
                f"{described!r} declares a severity floor and is not in the "
                "registry - it was probably renamed"
            )

    def test_every_declared_floor_is_a_grade_that_exists(self):
        assert set(_FLOORS.values()) <= {"BREAKS", "CRITERION"}

    def test_the_registry_shape_is_unchanged(self):
        """Seven test files unpack these as pairs; the floor must not change that."""
        for entry in _CHECKS:
            description, check = entry
            assert isinstance(description, str)
            assert callable(check)


class TestNothingElseMoved:
    def test_a_workspace_with_no_problems_is_still_silent(self, tmp_path):
        project = tmp_path / "app"
        project.mkdir()
        (project / "index.html").write_text(
            '<!doctype html><html><body><ul id="tasks"></ul>'
            '<script type="module" src="./app.js"></script></body></html>'
        )
        (project / "app.js").write_text(
            "export const add = (t) => t;\n"
            "document.getElementById('tasks').textContent = 'x';\n"
        )

        assert problems_that_break_the_product(str(tmp_path)) == []

    def test_wired_controls_are_not_reported(self, the_workspace_that_failed):
        """A handler for them, and the finding must go."""
        project = the_workspace_that_failed / "todo-app"
        (project / "app.js").write_text(
            A_SCRIPT_THAT_WIRES_EVERYTHING_ELSE
            + "document.querySelectorAll('[data-filter]').forEach("
            "(b) => b.addEventListener('click', () => {}));\n"
        )

        problems = problems_that_break_the_product(str(the_workspace_that_failed))

        assert not any("data-filter" in problem for problem in problems), problems

    def test_an_unreadable_workspace_still_reports_nothing(self, tmp_path):
        assert problems_that_break_the_product(str(tmp_path / "gone")) == []

    def test_the_summary_still_names_every_check(self, the_workspace_that_failed):
        """The registry change must not drop the list of what ran."""
        summary = summarise_integration(str(the_workspace_that_failed), None, "")

        assert "clickable controls against the scripts that should operate them" in summary
        assert summary.count(",") > 20, "the check list looks truncated"
