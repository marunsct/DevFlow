"""Every MVP feature the intake selected must be assigned to a sprint.

The sprint plan was checked against the intake's success measures alone.
Measured on one run: the MVP candidates held "Toggle complete/incomplete with
visual cue", the specification specified `toggleComplete(id)` and a
`task:toggled` event, and no sprint planned either, because the brief's
acceptance criteria never said "complete". The last sprint's milestone plan
"declined to add ... complete toggle functionality (future work)" with no
sprint after it, and the run was accepted with a Completed filter that could
never show a task.
"""

from __future__ import annotations

from app.agents.product_manager import ProductManagerOutput
from app.agents.scrum_master import (
    SprintDefinition,
    SprintPlanOutput,
    build_sprint_planning_request,
    unaccounted_success_measures,
)
from app.graph.workflow import MVP_FEATURE_LABEL, _what_the_sprints_must_deliver

#: That run's intake, verbatim.
MEASURES = [
    "Users can add, edit, delete tasks",
    "Tasks persist between page refreshes",
    "Filter functionality works correctly",
    "Responsive design for mobile and desktop",
]
MVP = [
    "Add new task form and list rendering",
    "Toggle complete/incomplete with visual cue",
    "Delete button for each task",
    "Basic filtering UI (All, Active, Completed) that updates the list",
    "Persistence using localStorage or a JSON file",
]


def _intake(measures=MEASURES, mvp=MVP) -> ProductManagerOutput:
    return ProductManagerOutput(
        product_name="Simple To-Do List App", success_measures=list(measures), mvp_candidates=list(mvp)
    )


def test_the_mvp_features_follow_the_measures() -> None:
    checklist = _what_the_sprints_must_deliver(_intake())

    assert checklist[:4] == MEASURES
    assert checklist[5] == f"Toggle complete/incomplete with visual cue{MVP_FEATURE_LABEL}"
    assert len(checklist) == 9


def test_a_feature_the_measures_already_state_is_not_repeated() -> None:
    checklist = _what_the_sprints_must_deliver(
        _intake(mvp=["users can add, edit, delete tasks", "Toggle completion"])
    )

    assert len(checklist) == 5
    assert checklist[-1].startswith("Toggle completion")


def test_an_intake_with_no_mvp_list_is_checked_as_before() -> None:
    assert _what_the_sprints_must_deliver(_intake(mvp=[])) == MEASURES
    assert _what_the_sprints_must_deliver(None) == []


def test_that_run_s_plan_is_caught_leaving_the_toggle_out() -> None:
    """Its three sprints built add/persist, edit/delete, and filter/responsive."""
    plan = SprintPlanOutput(
        sprints=[SprintDefinition(goal=f"Sprint {k}", user_value="v") for k in (1, 2, 3)],
        success_measure_coverage=[
            "1: Sprint 1", "2: Sprint 1", "3: Sprint 3", "4: Sprint 3",
            "5: Sprint 1", "7: Sprint 2", "8: Sprint 3", "9: Sprint 1",
        ],
    )

    assert unaccounted_success_measures(plan, _what_the_sprints_must_deliver(_intake())) == [6]


def test_the_planner_is_shown_the_feature_and_told_it_cannot_wait() -> None:
    request = build_sprint_planning_request(
        "spec", "/", success_measures=_what_the_sprints_must_deliver(_intake())
    )
    text = request["messages"][0]["content"]

    assert "6. Toggle complete/incomplete with visual cue (an MVP feature" in text
    assert "no release after this one" in text


# --- the feature lines are assigned, not word-checked -----------------------

#: Another run's intake: sentences, not short measures.
SENTENCES = [
    "One HTML file with embedded or sibling CSS/JS holding the task list UI",
    "Inline validation: reject empty titles, ignore no-op toggles, and confirm "
    "deletion acts on the selected task only.",
]


def test_a_feature_line_s_words_are_not_required_of_the_plan() -> None:
    """That run's complete plan was handed back for "embedded", "sibling" and "confirm"."""
    from app.agents.scrum_master import capabilities_the_plan_never_names
    from app.graph.workflow import _without_the_mvp_features

    checklist = _what_the_sprints_must_deliver(_intake(measures=MEASURES, mvp=SENTENCES))
    plan = SprintPlanOutput(
        sprints=[SprintDefinition(goal="Add, edit, delete; persist; filter; mobile and desktop", user_value="v")],
        success_measure_coverage=[],
    )

    assert capabilities_the_plan_never_names(plan, _without_the_mvp_features(checklist)) == {}


def test_blanking_the_features_keeps_the_numbering() -> None:
    from app.graph.workflow import _without_the_mvp_features

    checklist = _what_the_sprints_must_deliver(_intake())

    blanked = _without_the_mvp_features(checklist)
    assert blanked[:4] == MEASURES
    assert blanked[4:] == [""] * 5


def test_a_measure_s_list_is_still_checked() -> None:
    from app.agents.scrum_master import capabilities_the_plan_never_names
    from app.graph.workflow import _without_the_mvp_features

    plan = SprintPlanOutput(
        sprints=[SprintDefinition(goal="Add and delete tasks", user_value="v")],
        success_measure_coverage=[],
    )
    checklist = _without_the_mvp_features(_what_the_sprints_must_deliver(_intake()))

    assert capabilities_the_plan_never_names(plan, checklist)[1] == ["edit"]


def test_a_verb_after_and_is_not_a_capability() -> None:
    """"shows an empty list and does not error" asked the plan to deliver "does"."""
    from app.agents.success_measures import enumerations

    assert enumerations("opening the page shows an empty list and does not error") == []
