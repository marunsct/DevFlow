"""The stages that plan and build are told the conditions the design review approved the specification on (LF.1512).

Measured on one medium run: the reviewer approved with three approval conditions, among them that the error catalogue
section stays and holds every error code the specification uses, and four accepted risks. Nothing read either: they
reached only `docs/architecture_review.md`, so the sprint planner, the technical lead and the builders never saw them.
The conditions go to all three, the accepted risks to the two planners only, as known risks.
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from workflow_nodes import a_builder, a_lead, a_plan, a_specification, a_work_order, run_node

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

CONDITIONS = [
    "The error_catalogue section (lines 230-251) must remain present and contain all error codes referenced "
    "elsewhere in the spec",
    "Every route listed in the interface contract keeps the status codes the contract gives it",
]
RISK = "The signing secret defaults to a deterministic seed when the environment sets none"


def _a_review(status: str = "approved", conditions=CONDITIONS, risks=(RISK,)):
    from app.agents.architecture_reviewer import ArchitectureReviewOutput

    return ArchitectureReviewOutput(status=status, findings=[], approval_conditions=list(conditions),
                                    accepted_risks=list(risks))


def _the_sprint_planner_s_request(tmp_path, review) -> str:
    from app.agents.scrum_master import SprintDefinition, SprintPlanOutput

    asked = []

    def gated(state, config, *, initial_request, output_key, **kwargs):
        asked.append(initial_request["messages"][-1]["content"])
        return {output_key: SprintPlanOutput(sprints=[SprintDefinition(goal="Users can keep notes", user_value="v")])}

    run_node("scrum_master", {
        "repository": SimpleNamespace(root_path=str(tmp_path)), "technical_specification": a_specification(),
        "product_intake": {"product_name": "Notes"}, "architecture_review": review,
    }, str(tmp_path), {
        "app.graph.workflow.create_scrum_master_agent": lambda **kwargs: MagicMock(),
        "app.graph.workflow.build_sprint_planning_request":
            lambda *args, **kwargs: {"messages": [{"role": "user", "content": "Plan the sprints."}]},
        "app.graph.workflow._run_gated_agent": gated,
    })
    return asked[0]


def _the_lead_s_request(tmp_path, review) -> str:
    _, asked = a_lead(tmp_path, a_plan(a_work_order("backend", "build", ["app.py"])),
                      state={"architecture_review": review})
    return asked["requests"][0]


def _a_builder_s_request(tmp_path, review, worker=None) -> str:
    _, asked = a_builder(tmp_path, [a_work_order("backend", "build", ["app.py"])], worker=worker,
                         state={"architecture_review": review})
    return asked[0]


PLANNERS = {"the sprint planner": _the_sprint_planner_s_request, "the technical lead": _the_lead_s_request}
BUILDERS = {
    "a builder in linear mode": lambda tmp_path, review: _a_builder_s_request(tmp_path, review),
    "a parallel builder": lambda tmp_path, review: _a_builder_s_request(tmp_path, review, worker=0),
}


@pytest.mark.parametrize("stage", sorted(PLANNERS))
def test_the_planners_are_told_the_conditions_and_the_accepted_risks(tmp_path, stage):
    asked = PLANNERS[stage](tmp_path, _a_review())
    assert "Conditions the design review approved the specification on" in asked
    assert all(f"- {condition}" in asked for condition in CONDITIONS)
    assert "Known risks the design review accepted" in asked and f"- {RISK}" in asked


@pytest.mark.parametrize("stage", sorted(BUILDERS))
def test_the_builders_are_told_the_conditions_and_not_the_risks(tmp_path, stage):
    asked = BUILDERS[stage](tmp_path, _a_review())
    assert all(f"- {condition}" in asked for condition in CONDITIONS)
    assert RISK not in asked


def test_a_review_that_did_not_approve_hands_on_no_conditions(tmp_path):
    asked = _the_sprint_planner_s_request(tmp_path, _a_review(status="changes_required"))
    assert CONDITIONS[0] not in asked and RISK not in asked


def test_many_conditions_are_given_whole_within_the_bound_and_the_rest_counted():
    from app.agents.design_review_conditions import conditions_section

    many = [f"Condition {n}: the section named in this line stays as the review read it, word for word." for n in range(40)]
    section = conditions_section({"architecture_review": _a_review(conditions=many)})
    assert len(section) < 1_800
    assert f"- {many[0]}" in section and many[-1] not in section
    assert re.search(r"And \d+ more in docs/architecture_review\.md", section)


def test_the_new_request_text_avoids_the_banned_words():
    from app.agents.design_review_conditions import conditions_section, risks_section, what_is_carried

    review = _a_review(conditions=["A plain line."], risks=["A plain risk."])
    state = {"architecture_review": review}
    assert not BANNED.findall(conditions_section(state) + risks_section(state) + what_is_carried(review))
