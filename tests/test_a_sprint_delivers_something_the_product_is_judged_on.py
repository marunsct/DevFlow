"""A sprint that no success measure is assigned to is sent back to be folded in.

Measured over one day's runs of the same small brief, by each plan's own
coverage lines. The two that shipped a sound product assigned a measure to
every sprint. Three that failed opened with a sprint nothing was assigned to -
"Set up project structure and initial render", "Establish core architecture
and persistence", "Establish the foundation ... with unit tests" - and one of
them spent three hours and all four attempts on it: a page that rendered
nothing, with a browser suite written to test it.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.scrum_master import (
    _the_success_measures,
    build_sprint_planning_request,
    sprints_that_deliver_nothing,
)

MEASURES = [
    "Users can add, edit and delete tasks",
    "Tasks persist between page refreshes",
    "Filter functionality works correctly",
    "No external dependencies",
]


def _plan(coverage: list[str], sprints: int) -> SimpleNamespace:
    return SimpleNamespace(
        sprints=[SimpleNamespace(goal=f"goal {k}") for k in range(1, sprints + 1)],
        success_measure_coverage=coverage,
    )


def test_the_setup_sprints_of_the_run_that_failed_are_named() -> None:
    plan = _plan(["1: Sprint 4", "2: Sprint 3", "3: Sprint 3", "4: every sprint"], sprints=4)

    assert sprints_that_deliver_nothing(plan, MEASURES) == [1, 2]


def test_a_plan_whose_every_sprint_delivers_is_left_alone() -> None:
    plan = _plan(["1: Sprint 2", "2: Sprint 1", "3: Sprint 1", "4: Sprint 2"], sprints=2)

    assert sprints_that_deliver_nothing(plan, MEASURES) == []


def test_keeping_a_constraint_is_not_delivering_a_measure() -> None:
    """"Every sprint" names no sprint: a constraint kept is not a thing built."""
    plan = _plan(["1: Sprint 2", "2: Sprint 2", "3: Sprint 2", "4: every sprint"], sprints=2)

    assert sprints_that_deliver_nothing(plan, MEASURES) == [1]


def test_one_sprint_cannot_be_folded_into_another() -> None:
    assert sprints_that_deliver_nothing(_plan(["4: every sprint"], sprints=1), MEASURES) == []


def test_a_plan_that_assigns_nothing_is_another_check_s_to_report() -> None:
    assert sprints_that_deliver_nothing(_plan([], sprints=3), MEASURES) == []
    assert sprints_that_deliver_nothing(_plan(["4: every sprint"], sprints=3), MEASURES) == []


def test_a_line_naming_a_sprint_that_does_not_exist_delivers_nothing() -> None:
    plan = _plan(["1: Sprint 1", "2: Sprint 7"], sprints=2)

    assert sprints_that_deliver_nothing(plan, MEASURES) == [2]


def test_the_second_request_names_the_sprint_and_what_to_do_with_it() -> None:
    gaps = [{"sprint": 1, "goal": "Set up project structure and initial render"}]

    section = _the_success_measures(MEASURES, gaps)

    assert "Sprint 1: Set up project structure and initial render" in section
    assert "fold that work into the first sprint that needs it" in section
    # A sprint that is not setup but builds half of what another finishes -
    # one run's "Add the task creation form" - is told what to do as well.
    assert "merge them" in section
    assert "fewer sprints" in section
    # And it is not also listed as an unassigned measure.
    assert "LEFT THESE UNASSIGNED" not in section


def test_both_kinds_of_gap_can_be_asked_about_at_once() -> None:
    gaps = [{"measure": 3, "missing": []}, {"sprint": 1, "goal": "Foundation"}]

    request = build_sprint_planning_request("the spec", "/", success_measures=MEASURES, gaps=gaps)
    text = request["messages"][0]["content"]

    assert "Sprint 1: Foundation" in text
    assert "LEFT THESE UNASSIGNED" in text and "3. Filter functionality works correctly" in text
