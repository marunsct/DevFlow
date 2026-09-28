"""A re-planned milestone must dispatch its specialists, in parallel mode too.

The parallel router decides what to fan out by subtracting the stage names that
already produced output from the plan's tasks:

    done = set(state.get("specialist_outputs") or {})
    pending = [... if _specialist_stage_name(task, index) not in done]

That is the resume guard - a run that paused inside a fan-out re-enters the
dispatcher, and without it every finished task would run a second time and
re-apply its edits. Linear mode gets the same protection from
`specialist_task_index`, which `technical_lead_node` sets back to 0 whenever it
stores a plan. Nothing set `specialist_outputs` back to empty there, and a
stage name carries no plan identity - it is `specialist_{role}_{index}` - so the
guard could not tell "already done in this fan-out" from "done in the sprint
before".

Measured on one run, whose three milestone plans produced the identical
three names, because the lead assigns ui_ux, backend and testing in that order
every time:

    plan 1  ['specialist_ui_ux_0', 'specialist_backend_1', 'specialist_testing_2']
    plan 2  ['specialist_ui_ux_0', 'specialist_backend_1', 'specialist_testing_2']
    plan 3  ['specialist_ui_ux_0', 'specialist_backend_1', 'specialist_testing_2']

Sprint 1 ran all three and recorded them. Plans 2 and 3 were revisions the
milestone review asked for, and every task in both was already "done", so the
fan-out was empty and the run went straight to a test round - 174ms after the
plan was stored, with no specialist in between. Two full planning cycles, one of
them 16,959 output tokens, produced nothing, and the filter and inline-edit work
they described was eventually done by nine `defect_fix` stages instead.

The `blocked` branch of the same reviewer already cleared `specialist_outputs`;
the `changes_required` branch beside it did not, and that is the common one.
Fixed in `technical_lead_node` rather than on that one edge, so no future path
into the lead can miss it.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.agents.milestone_reviewer import MilestoneReviewFinding, MilestoneReviewOutput
from app.graph.workflow import start_workflow
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _approved_review,
    _document,
    _graph,
    _milestone,
    _milestone_review,
    _repository,
    _script_through_architecture,
    _security_review,
    _specialist,
    _sprint_plan,
    agents,
    responds_with,
)

#: The roles a lead assigns, in the order it assigns them. The order is the
#: point: it is what makes the second plan's stage names collide with the first's.
ROLES = ("ui_ux", "backend", "testing")


@pytest.fixture
def parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    real = config.load_settings()
    monkeypatch.setattr(
        config,
        "load_settings",
        lambda *args, **kwargs: dataclasses.replace(real, execution_mode="parallel"),
    )


def _review_asking_for_changes() -> MilestoneReviewOutput:
    """A review whose finding is severe enough to send the sprint back."""
    return MilestoneReviewOutput(
        status="changes_required",
        findings=[
            MilestoneReviewFinding(
                severity="blocking",
                category="correctness",
                description="The filter buttons are on the page and nothing reads them.",
                affected_files=["app/index.html"],
                required_remediation="Wire the filter buttons to the render path.",
            )
        ],
        acceptance_evidence="Filtering does not work.",
        documentation_reviewed=True,
        tests_reviewed=True,
    )


def _script_a_sprint_that_is_sent_back_once(agents: ScriptedAgents) -> None:
    """One milestone, a review that asks for changes, then a clean second pass."""
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    # Two plans with the same roles in the same order: the revision is what the
    # run actually produced, not a contrivance.
    agents.script(
        "technical_lead",
        [responds_with(_milestone(*ROLES)), responds_with(_milestone(*ROLES))],
    )
    for role in set(ROLES):
        # Four each: two sprint passes, plus the verification round for testing.
        agents.script(f"specialist_{role}", [responds_with(_specialist())] * 4)
    agents.script(
        "milestone_reviewer",
        [responds_with(_review_asking_for_changes()), responds_with(_milestone_review())],
    )
    agents.script(
        "security_reviewer",
        [responds_with(_security_review())] * 2,
    )


class TestARePlannedSprintDoesTheWork:
    def test_parallel_mode_dispatches_the_second_plan(
        self, agents: ScriptedAgents, parallel: None, tmp_path: Any
    ) -> None:
        """Each specialist runs for the revision as well as the first plan."""
        _script_a_sprint_that_is_sent_back_once(agents)

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-replan")

        assert state["stage"] != "failed", state.get("error")
        assert len(agents.requests["technical_lead"]) == 2, (
            "the review did not send the sprint back, so this proves nothing"
        )
        for role in ROLES:
            calls = len(agents.requests[f"specialist_{role}"])
            assert calls >= 2, (
                f"specialist_{role} ran {calls} time(s) across two milestone "
                "plans: the revision was planned and never dispatched"
            )

    def test_a_revision_that_moves_one_role_still_dispatches_the_others(
        self, agents: ScriptedAgents, parallel: None, tmp_path: Any
    ) -> None:
        """The shape this actually takes in a run: partial dispatch.

        A collision is per task, not per plan, so a revision runs exactly the
        tasks whose `(role, index)` pair is new and silently skips the rest. That
        is worse than skipping the sprint outright, because the sprint looks like
        it did work.

        Measured on the second sprint of one run. Its first plan ran
        `specialist_ui_ux_0` and `specialist_testing_1`; the revision's index-1
        task was `backend`, so `specialist_backend_1` did not collide and ran,
        while `specialist_ui_ux_0` - unchanged in the new plan and still needed -
        did not.
        """
        first = ("ui_ux", "testing")
        revised = ("ui_ux", "backend")
        _script_through_architecture(agents, _approved_review())
        agents.script("scrum_master", [responds_with(_sprint_plan())])
        agents.script(
            "technical_lead",
            [responds_with(_milestone(*first)), responds_with(_milestone(*revised))],
        )
        for role in {*first, *revised}:
            agents.script(f"specialist_{role}", [responds_with(_specialist())] * 4)
        agents.script(
            "milestone_reviewer",
            [
                responds_with(_review_asking_for_changes()),
                responds_with(_milestone_review()),
            ],
        )
        agents.script("security_reviewer", [responds_with(_security_review())] * 2)

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-partial")

        assert state["stage"] != "failed", state.get("error")
        # `specialist_ui_ux_0` is the collision: index 0 and role ui_ux in both
        # plans. It must run for the revision as well as the first plan.
        assert len(agents.requests["specialist_ui_ux"]) >= 2, (
            "the revision kept the ui_ux task at index 0, so its stage name "
            "matched the first plan's and the task was treated as already done"
        )
        assert len(agents.requests["specialist_backend"]) >= 1

    def test_linear_mode_dispatches_the_second_plan(
        self, agents: ScriptedAgents, tmp_path: Any
    ) -> None:
        """The same run without the toggle. Linear mode was never affected.

        Kept so the fix cannot be "make linear match parallel" by accident.
        """
        _script_a_sprint_that_is_sent_back_once(agents)

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-replan-linear")

        assert state["stage"] != "failed", state.get("error")
        for role in ROLES:
            assert len(agents.requests[f"specialist_{role}"]) >= 2


def test_storing_a_plan_clears_the_previous_plan_s_specialist_outputs() -> None:
    """The invariant, stated where it is enforced.

    A stage name is `specialist_{role}_{index}` and carries no plan identity, so
    outputs recorded under one plan must not be visible to the next. The linear
    counter beside this one has always been reset here; this is its parallel
    twin.
    """
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow.build_workflow_graph)
    lead = source.split("def technical_lead_node", 1)[1].split("def specialist_dispatch_node", 1)[0]

    assert 'update["specialist_task_index"] = 0' in lead
    assert 'update["specialist_outputs"] = {}' in lead, (
        "technical_lead_node zeroes the linear counter but leaves the parallel "
        "router's completed-task set, so a re-planned sprint fans out nothing"
    )
