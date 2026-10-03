"""A sprint that no success measure is assigned to is folded into its neighbour.

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
    SprintDefinition,
    SprintPlanOutput,
    how_much_a_plan_leaves_out,
    sprints_that_deliver_nothing,
    unaccounted_success_measures,
    with_setup_folded_into_the_sprint_that_needs_it,
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


# --- and it is put right here, not asked for ----------------------------------


def _real_plan(goals_and_scope: list[tuple[str, list[str]]], coverage: list[str]) -> SprintPlanOutput:
    return SprintPlanOutput(
        sprints=[
            SprintDefinition(
                goal=goal, user_value=f"value of {goal}", in_scope=scope,
                out_of_scope=[f"not in {goal}"], acceptance_criteria=[f"{goal} works"],
                dependencies=[f"Sprint {k}" for k in range(1, index)],
            )
            for index, (goal, scope) in enumerate(goals_and_scope, start=1)
        ],
        success_measure_coverage=coverage,
    )


AS_THE_RUN_PLANNED_IT = [
    ("Establish the project foundation", ["Set up package.json", "Create placeholders"]),
    ("Implement core logic and persistence", ["Implement CRUD functions"]),
    ("Build the UI layer", ["Render the task list"]),
    ("Finalize polish", ["Refine the filter"]),
]


def test_the_foundation_sprint_is_folded_into_the_one_that_needs_it() -> None:
    plan = _real_plan(AS_THE_RUN_PLANNED_IT, ["1: Sprint 4", "2: Sprint 3", "3: Sprint 2", "4: every sprint"])

    folded_plan, folded = with_setup_folded_into_the_sprint_that_needs_it(plan, MEASURES)

    assert folded == ["Establish the project foundation"]
    assert [sprint.goal for sprint in folded_plan.sprints] == [
        # Both goals, in the order the work is done.
        "Establish the project foundation; then Implement core logic and persistence.",
        "Build the UI layer", "Finalize polish",
    ]
    first = folded_plan.sprints[0]
    # The setup comes first, in the sprint that needs it, and nothing it did is lost.
    assert first.in_scope == ["Set up package.json", "Create placeholders", "Implement CRUD functions"]
    assert "Establish the project foundation works" in first.acceptance_criteria
    # What the folded sprint ruled out was its neighbour's own work.
    assert first.out_of_scope == ["not in Implement core logic and persistence"]
    assert first.user_value == "value of Implement core logic and persistence"


def test_the_plan_s_own_references_are_renumbered() -> None:
    plan = _real_plan(AS_THE_RUN_PLANNED_IT, ["1: Sprint 4", "2: Sprint 3", "3: Sprint 2", "4: every sprint"])

    folded_plan, _ = with_setup_folded_into_the_sprint_that_needs_it(plan, MEASURES)

    assert folded_plan.success_measure_coverage == ["1: Sprint 3", "2: Sprint 2", "3: Sprint 1", "4: every sprint"]
    assert folded_plan.sprints[0].dependencies == []
    assert folded_plan.sprints[1].dependencies == ["Sprint 1"]
    assert folded_plan.sprints[2].dependencies == ["Sprint 1", "Sprint 2"]
    # And nothing is left for a second pass to find.
    assert sprints_that_deliver_nothing(folded_plan, MEASURES) == []
    assert unaccounted_success_measures(folded_plan, MEASURES) == []


def test_a_last_sprint_that_delivers_nothing_goes_into_the_one_before() -> None:
    plan = _real_plan(
        [("Build everything", ["Build it"]), ("Write the documentation", ["Write the README"])],
        ["1: Sprint 1", "2: Sprint 1", "3: Sprint 1", "4: every sprint"],
    )

    folded_plan, folded = with_setup_folded_into_the_sprint_that_needs_it(plan, MEASURES)

    assert folded == ["Write the documentation"]
    assert [sprint.goal for sprint in folded_plan.sprints] == [
        "Build everything; then Write the documentation."
    ]
    assert folded_plan.sprints[0].in_scope == ["Build it", "Write the README"]


def test_several_are_folded_until_every_sprint_delivers() -> None:
    plan = _real_plan(AS_THE_RUN_PLANNED_IT, ["1: Sprint 4", "2: Sprint 4", "3: Sprint 4", "4: every sprint"])

    folded_plan, folded = with_setup_folded_into_the_sprint_that_needs_it(plan, MEASURES)

    # "Implement core logic and persistence" builds something whatever the
    # coverage lines say, so it is not folded away and the plan keeps two
    # sprints rather than collapsing into one.
    assert len(folded) == 2 and len(folded_plan.sprints) == 2
    assert [sprint.goal for sprint in folded_plan.sprints] == [
        "Establish the project foundation; then Implement core logic and persistence.",
        "Build the UI layer; then Finalize polish.",
    ]
    assert folded_plan.success_measure_coverage[0] == "1: Sprint 2"


def test_a_plan_whose_sprints_all_deliver_is_returned_as_it_came() -> None:
    plan = _real_plan(AS_THE_RUN_PLANNED_IT[:2], ["1: Sprint 2", "2: Sprint 1", "3: Sprint 1", "4: Sprint 2"])

    folded_plan, folded = with_setup_folded_into_the_sprint_that_needs_it(plan, MEASURES)

    assert folded == [] and folded_plan is plan


def test_a_plan_with_no_coverage_lines_is_not_folded_into_one_sprint() -> None:
    """Nothing says which sprint delivers what, so nothing can be called setup."""
    plan = _real_plan(AS_THE_RUN_PLANNED_IT, [])

    folded_plan, folded = with_setup_folded_into_the_sprint_that_needs_it(plan, MEASURES)

    assert folded == [] and len(folded_plan.sprints) == 4


def test_how_much_a_plan_leaves_out_is_what_decides_between_two() -> None:
    """One run's second plan dropped its coverage lines altogether, and the run
    was failed for a plan that "assigns none" when the first had assigned all."""
    first = _real_plan(AS_THE_RUN_PLANNED_IT, ["1: Sprint 4", "2: Sprint 3", "3: Sprint 2", "4: every sprint"])
    second = _real_plan(AS_THE_RUN_PLANNED_IT[1:], [])

    assert how_much_a_plan_leaves_out(second, MEASURES) > how_much_a_plan_leaves_out(first, MEASURES)


def test_the_workflow_keeps_the_better_plan_and_folds_before_it_checks() -> None:
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    node = source[source.index("def scrum_master_node("):source.index("def technical_lead_node(")]

    assert "how_much_a_plan_leaves_out(earlier, measures)" in node
    assert 'update["sprint_plan"] = earlier' in node
    assert node.index("with_setup_folded_into_the_sprint_that_needs_it(") < node.index("unaccounted_success_measures(")
    # The first plan is kept in state when the second is asked for.
    assert 'sprint_plan=update["sprint_plan"]' in node


def test_a_plan_is_not_handed_back_for_a_verb_it_uses_in_another_person() -> None:
    """One run's measure ended "stays under 500 lines and runs on the latest
    browsers". The sprint that held it said "run comprehensive E2E tests", and
    the plan was handed back - twice - for never delivering "runs"."""
    from app.agents.success_measures import capabilities_never_named

    measure = ["Code stays under 500 lines and runs on latest Chrome and Firefox browsers."]
    plan = "Run comprehensive E2E tests on Chrome and Firefox, and confirm the code stays under 500 lines."

    assert capabilities_never_named(plan, measure) == {}
    # Still asked for when the plan says nothing of the kind.
    assert capabilities_never_named("Polish the page.", measure) != {}


def test_a_plan_is_not_handed_back_for_the_places_a_measure_names() -> None:
    """ "Responsive design for mobile and desktop" asks for one thing and names
    two places it must hold. Two plans in one morning were handed back for
    never delivering "desktop"; one of the answers was worse than the plan."""
    from app.agents.success_measures import capabilities_never_named

    measure = ["Responsive design for mobile and desktop"]

    assert capabilities_never_named("Add a responsive layout with a media query.", measure) == {}
    # Still asked for when the plan names neither the thing nor the places.
    assert capabilities_never_named("Polish the page.", measure) == {1: ["mobile", "desktop"]}
    # A list of things to build is every item, as before.
    assert capabilities_never_named("Add and delete tasks.", ["Users can add, edit, and delete tasks"]) == {1: ["edit"]}


def test_a_sprint_whose_goal_builds_something_is_not_folded_for_missing_coverage() -> None:
    """One run's plan put every measure against sprint 3. Folded by coverage
    alone, a setup sprint, "Implement full task-list logic and persistence" and
    an end-to-end test sprint all went into one, and the whole product was one
    sprint. The persistence sprint builds something; the other two fold."""
    goals = [
        "Set up project structure and core logic module",
        "Implement full task-list logic and persistence",
        "Create single-page UI, inline all assets, and satisfy acceptance criteria",
        "Implement Playwright end-to-end tests for full user flow",
    ]
    plan = SimpleNamespace(
        sprints=[SimpleNamespace(goal=goal) for goal in goals],
        success_measure_coverage=["1: Sprint 3", "2: Sprint 3", "3: Sprint 3", "4: Sprint 3"],
    )

    assert sprints_that_deliver_nothing(plan, MEASURES) == [1, 4]
