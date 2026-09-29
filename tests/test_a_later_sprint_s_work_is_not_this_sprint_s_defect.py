"""A requirement a later sprint builds is not reported as this sprint's defect.

The required-action checks read the whole project's requirements and run in
every test round. On one run the specification described inline editing and the
sprint plan put it in sprint 2; sprint 1's first test round reported "Edit
feature required by product_intake.md but not implemented" as major, and a
defect fixer built editing inside sprint 1, outside any plan.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.analysis.integration_checks import planned_for_a_later_sprint
from app.graph.workflow import _what_later_sprints_build

NOTHING_IMPLEMENTS = (
    "This project's own documents require that a user can `edit`: \"- Users can add, "
    "edit, delete tasks\". Nothing in the product names it."
)
NO_TEST = "No test names `edit`, which this project's own documents require a user can do."
OTHER = "index.html links style.css, which does not exist."


def _sprint(goal: str, in_scope=(), out_of_scope=(), criteria=()):
    return SimpleNamespace(
        goal=goal, in_scope=list(in_scope), out_of_scope=list(out_of_scope),
        acceptance_criteria=list(criteria),
    )


def _state(*sprints, index=0):
    return {"sprint_plan": SimpleNamespace(sprints=list(sprints)), "current_sprint_index": index}


class TestTheFilter:
    LATER = "Users can toggle completion and edit task titles inline"

    def test_a_missing_action_a_later_sprint_builds_is_dropped(self):
        assert planned_for_a_later_sprint(NOTHING_IMPLEMENTS, self.LATER)

    def test_the_test_check_is_dropped_the_same_way(self):
        assert planned_for_a_later_sprint(NO_TEST, self.LATER)

    def test_an_action_no_later_sprint_builds_stays(self):
        assert not planned_for_a_later_sprint(NOTHING_IMPLEMENTS, "Users can filter by status")

    def test_the_last_sprint_keeps_everything(self):
        assert not planned_for_a_later_sprint(NOTHING_IMPLEMENTS, "")

    def test_other_findings_are_never_dropped(self):
        assert not planned_for_a_later_sprint(OTHER, self.LATER)


class TestWhatLaterSprintsBuild:
    def test_only_the_sprints_after_this_one(self):
        state = _state(
            _sprint("Add and delete tasks"),
            _sprint("Toggle and edit tasks", in_scope=["Inline editing of titles"]),
            index=0,
        )

        later = _what_later_sprints_build(state)

        assert "Inline editing of titles" in later
        assert "Add and delete" not in later

    def test_out_of_scope_is_not_a_plan_to_build(self):
        state = _state(
            _sprint("Add and delete tasks"),
            _sprint("Filter tasks", out_of_scope=["Editing task titles"]),
            index=0,
        )

        assert not planned_for_a_later_sprint(NOTHING_IMPLEMENTS, _what_later_sprints_build(state))

    def test_the_last_sprint_has_nothing_later(self):
        state = _state(_sprint("One"), _sprint("Two, with editing"), index=1)

        assert _what_later_sprints_build(state) == ""

    def test_no_plan_is_nothing_later(self):
        assert _what_later_sprints_build({}) == ""


def test_the_test_round_is_given_the_later_sprints():
    import inspect

    from app.graph import workflow

    assert "later_sprints=_what_later_sprints_build(state)" in inspect.getsource(workflow)
