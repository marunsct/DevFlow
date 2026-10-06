"""Each sprint, the specialists consulted before the specification check their advice was built.

Advice the specification adopted is a promise about the product, and nothing
held a sprint to it. Now every consulted specialist with adopted advice checks
it against the sprint's work, the UI/UX specialist sees the page when its model
reads images, and what they find goes to the milestone reviewer to weigh.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from app.agents import advice_review as review_module
from app.agents.advice_review import (
    AdviceReview,
    build_advice_review_request,
    findings_block,
    findings_from,
    roles_to_review,
)
from app.graph import workflow as workflow_module
from app.graph.workflow import start_workflow
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _approved_review,
    _document,
    _graph,
    _repository,
    _script_through_sprint,
    _spec,
    agents,
    responds_with,
)

ADVICE = {
    "ui_ux": ["Stack the form above the list below 600px."],
    "database": ["Give every record a generated id."],
    "testing": ["AC-1: find the field by its label."],
}


class TestWhoChecks:
    def test_each_role_with_adopted_advice_except_testing(self) -> None:
        spec = SimpleNamespace(specialist_advice_decisions=["UX-1: adopted", "DB-1: adopted", "TS-1: adopted"])

        assert roles_to_review(ADVICE, spec) == ["ui_ux", "database"]

    def test_a_role_whose_advice_was_all_declined_has_nothing_to_check(self) -> None:
        spec = SimpleNamespace(specialist_advice_decisions=["UX-1: adopted", "DB-1: declined - ids exist"])

        assert roles_to_review(ADVICE, spec) == ["ui_ux"]

    def test_no_advice_means_no_review(self) -> None:
        assert roles_to_review({}, None) == []


class TestWhatTheyAreAskedAndWhatComesOfIt:
    def test_the_request_carries_the_adopted_items_and_the_sprint(self) -> None:
        text = build_advice_review_request(
            "ui_ux", ["UX-1: Stack the form above the list below 600px."], "Add notes", "", ["notes/styles.css"],
        )["messages"][0]["content"]

        assert "UX-1: Stack the form" in text and "Add notes" in text and "notes/styles.css" in text

    def test_findings_name_the_specialist(self) -> None:
        answer = AdviceReview(not_built=["UX-1: styles.css has no rule below 600px"], design_problems=["the phone screenshot scrolls sideways"])

        assert findings_from("ui_ux", answer) == [
            "[UI/UX specialist] not built: UX-1: styles.css has no rule below 600px",
            "[UI/UX specialist] design: the phone screenshot scrolls sideways",
        ]

    def test_the_milestone_reviewer_is_told_to_weigh_them(self) -> None:
        block = findings_block({"ui_ux": ["[UI/UX specialist] not built: UX-1: missing"]})

        assert "not built" in block and "blocking or major" in block and "minor when it is polish" in block

    def test_nothing_found_tells_the_reviewer_nothing(self) -> None:
        assert findings_block({"ui_ux": []}) == "" and findings_block(None) == ""

    def test_the_prompt_names_no_product_and_no_control(self) -> None:
        text = (review_module._SYSTEM_PROMPT + findings_block({"ui_ux": ["x"]})).lower()
        for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
            assert not re.search(rf"\b{word}\b", text), word


class TestThroughTheGraph:
    def test_the_milestone_reviewer_hears_what_the_specialists_found(self, agents, monkeypatch, tmp_path) -> None:
        from test_the_specialists_advise_before_the_specification import TestThroughTheGraph as Consulting

        from app.agents.specialist_advice import SpecialistAdvice

        Consulting._consulting(monkeypatch, agents, ["ui_ux"], reviewing=True)
        Consulting._script_the_stack(agents)
        monkeypatch.setattr(
            workflow_module, "create_advice_reviewer_agent",
            lambda role, *args, **kwargs: agents.agent(f"advice_reviewer_{role}"),
        )
        agents.script("advisor_ui_ux", [responds_with(SpecialistAdvice(recommendations=ADVICE["ui_ux"]))])
        agents.script("principal_architect", [responds_with(_spec(
            interface_design=["Below 600px the form sits above the list."],
            specialist_advice_decisions=["UX-1: adopted - interface_design"],
        ))])
        agents.script("architecture_review", [responds_with(_approved_review())])
        agents.script("advice_reviewer_ui_ux", [responds_with(AdviceReview(not_built=["UX-1: no rule below 600px in styles.css"]))])
        _script_through_sprint(agents)

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-advice-review")

        asked = agents.last_request_text("milestone_reviewer")
        assert "[UI/UX specialist] not built: UX-1: no rule below 600px in styles.css" in asked
        assert "UX-1: Stack the form above the list below 600px." in agents.last_request_text("advice_reviewer_ui_ux")
        assert state["stage"] == "complete"

    def test_a_finding_from_another_review_is_not_carried_into_this_one(self) -> None:
        state = {"current_sprint_index": 1, "milestone_revision_count": 0,
                 "advice_review_cycle": "0:0", "advice_findings": {"ui_ux": ["old"]}}

        assert workflow_module._this_review_s_advice_findings(state) == {}


class TestWhatTheyFindIsCarriedForward:
    """Measured on one run: the UI/UX and database specialists reported thirteen
    adopted items not built, the milestone review accepted the sprint without a
    word about any, and the next two sprints closed with nothing to build - so
    none of it was built, taken or declined."""

    def test_a_specialist_s_findings_are_one_minor_finding_of_the_sprint_s_own(self) -> None:
        """One per specialist: one run's lead, carried fifteen items, was sent back
        twice a plan for recording a decision on six, then ten, then fourteen."""
        from app.agents.advice_review import as_sprint_findings
        from app.sprint.record import carried_from, with_dispositions

        findings = as_sprint_findings([
            "[UI/UX specialist] not built: UX-4: no feedback after a change",
            "[UI/UX specialist] design: the phone screenshot shows the list beside the form",
        ], 1)

        [finding] = findings
        assert finding["source"] == "advice" and finding["gating"] is False
        assert with_dispositions(findings, completed=True, more_sprints=True)[0]["disposition"] == (
            "carried to the next sprint"
        )
        [carried] = carried_from(findings, 1)
        assert carried.startswith(
            "[UI/UX specialist] 2 adopted item(s) the code does not follow: UX-4: no feedback after a "
            "change; design: the phone screenshot shows the list beside the form (sprint 1 advice review"
        )
        assert as_sprint_findings([], 1) == []

    def test_a_plan_that_finishes_a_failed_sprint_is_not_carried_them_again(self) -> None:
        carried = ["[UI/UX specialist] 1 adopted item(s) the code does not follow: UX-1: x"]
        first = {"current_sprint_index": 1, "carried_forward": carried,
                 "sprint_attempts": [{"sprint_index": 0, "status": "Completed"}]}
        again = {**first, "sprint_attempts": [*first["sprint_attempts"], {"sprint_index": 1, "status": "Failed"}]}

        assert workflow_module._carried_to_this_plan(first) == carried
        assert workflow_module._carried_to_this_plan(again) == []

    def test_the_brief_for_a_sprint_with_only_carried_work_names_no_product(self) -> None:
        text = workflow_module._only_what_was_carried("Every criterion due by sprint 2 already passes (AC-1).\nmore").lower()

        assert "every criterion due by sprint 2 already passes (ac-1)." in text and "more" not in text
        assert "carried_forward_decisions" in text and "hand out no work orders" in text
        for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
            assert not re.search(rf"\b{word}\b", text), word

    @staticmethod
    def _two_sprints(agents, monkeypatch, second_plan) -> None:
        from test_the_specialists_advise_before_the_specification import TestThroughTheGraph as Consulting

        from app.agents.scrum_master import SprintDefinition, SprintPlanOutput
        from app.agents.specialist_advice import SpecialistAdvice
        from app.agents.technical_lead import MilestonePlanOutput
        from app.graph import acceptance_nodes
        from test_graph_routing import _milestone, _milestone_review, _security_review, _specialist

        Consulting._consulting(monkeypatch, agents, ["ui_ux"], reviewing=True)
        Consulting._script_the_stack(agents)
        monkeypatch.setattr(
            workflow_module, "create_advice_reviewer_agent",
            lambda role, *args, **kwargs: agents.agent(f"advice_reviewer_{role}"),
        )
        # Sprint 2's criteria pass before it starts.
        monkeypatch.setattr(
            acceptance_nodes, "sprint_already_done",
            lambda state: "Every criterion due by sprint 2 already passes (AC-1)."
            if int(state.get("current_sprint_index") or 0) == 1 else "",
        )
        agents.script("advisor_ui_ux", [responds_with(SpecialistAdvice(recommendations=ADVICE["ui_ux"]))])
        agents.script("principal_architect", [responds_with(_spec(
            interface_design=["Below 600px the form sits above the list."],
            specialist_advice_decisions=["UX-1: adopted - interface_design"],
        ))])
        agents.script("architecture_review", [responds_with(_approved_review())])
        agents.script("advice_reviewer_ui_ux", [
            responds_with(AdviceReview(not_built=["UX-1: no rule below 600px in styles.css"])),
            responds_with(AdviceReview()),
        ])
        agents.script("scrum_master", [responds_with(SprintPlanOutput(sprints=[
            SprintDefinition(goal="Sprint 1: booking", user_value="v"),
            SprintDefinition(goal="Sprint 2: more", user_value="v"),
        ]))])
        agents.script("technical_lead", [responds_with(_milestone("testing")), responds_with(second_plan)])
        agents.script("specialist_testing", [responds_with(_specialist())] * 4)
        agents.script("milestone_reviewer", [responds_with(_milestone_review())] * 2)
        agents.script("security_reviewer", [responds_with(_security_review())] * 2)

    def test_the_next_sprint_s_lead_takes_or_declines_it_and_may_decline(self, agents, monkeypatch, tmp_path) -> None:
        from app.agents.technical_lead import MilestonePlanOutput

        self._two_sprints(agents, monkeypatch, MilestonePlanOutput(
            selected_sprint_goal="Sprint 2: more",
            carried_forward_decisions=["UX-1: declined - the stylesheet has the rule at 600px"],
        ))

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-advice-carried")

        asked = agents.last_request_text("technical_lead")
        assert "[UI/UX specialist] 1 adopted item(s) the code does not follow: UX-1: no rule below 600px in styles.css" in asked
        assert "Every criterion due by this sprint already passes" in asked
        assert state["stage"] == "complete"
        closed = [d for d in state["decisions"] if d.get("decision") == "accept without new work"]
        assert closed and closed[-1]["rationale"].startswith(
            "The lead took none of what earlier sprints carried here: UX-1: declined - the stylesheet has the rule at 600px"
        )
        assert not state.get("nothing_left_but_carried")

    def test_a_sprint_with_nothing_carried_still_closes_without_its_lead(self, agents, monkeypatch, tmp_path) -> None:
        from app.agents.technical_lead import MilestonePlanOutput

        self._two_sprints(agents, monkeypatch, MilestonePlanOutput(selected_sprint_goal="never asked"))
        agents.script("advice_reviewer_ui_ux", [responds_with(AdviceReview())])

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-advice-none")

        assert state["stage"] == "complete"
        assert len(agents.requests["technical_lead"]) == 1


class TestUntestedIsNoReasonToDecline:
    """One run's lead declined fifteen carried items "not required by current
    sprint tests" after being told that was no reason, and the sprint closed."""

    def test_such_decisions_are_named(self) -> None:
        from app.analysis.work_orders import declined_because_untested

        decisions = [
            "UX-3 declined: not required by current sprint tests",
            "DB-2 deferred - no impact on passing criteria",
            "UX-1: declined - the stylesheet already stacks the form below 600px",
            "UX-4 -> work order 2",
        ]

        assert declined_because_untested(decisions) == decisions[:2]

    def test_a_plan_that_declines_so_is_not_ready(self, monkeypatch) -> None:
        from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
        from app.analysis.work_orders import readiness_problems

        monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")
        plan = MilestonePlanOutput(
            selected_sprint_goal="g",
            delegated_tasks=[SpecialistTask(specialist_role="testing", task_description="Write the unit tests for storage.js", acceptance_criteria=["they run"])],
            carried_forward_decisions=["UX-3 declined: not required by current sprint tests"],
        )

        problems = readiness_problems(plan, "/nonexistent", carried_forward=["[UI/UX specialist] 1 adopted item(s) ..."])

        assert any("because no test requires it" in p for p in problems)

    def test_the_lead_is_asked_again_once_before_the_sprint_closes(self, agents, monkeypatch, tmp_path) -> None:
        from app.agents.technical_lead import MilestonePlanOutput

        declined = MilestonePlanOutput(
            selected_sprint_goal="Sprint 2: more",
            carried_forward_decisions=["UX-1 declined: not required by current sprint tests"],
        )
        TestWhatTheyFindIsCarriedForward._two_sprints(agents, monkeypatch, declined)
        from test_graph_routing import _milestone

        agents.script("technical_lead", [
            responds_with(_milestone("testing")), responds_with(declined),
            responds_with(declined.model_copy(update={
                "carried_forward_decisions": ["UX-1: declined - styles.css already has the rule at 600px"],
            })),
        ])

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-untested-decline")

        assert len(agents.requests["technical_lead"]) == 3
        assert "because no test requires it" in agents.last_request_text("technical_lead")
        assert state["stage"] == "complete"

    def test_the_send_back_names_no_product(self) -> None:
        from app.analysis.work_orders import untested_is_no_reason

        text = untested_is_no_reason(["X-1 declined: not required by tests"]).lower()
        for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
            assert not re.search(rf"\b{word}\b", text), word


def test_a_lead_that_answers_nothing_is_asked_again_once(agents, monkeypatch, tmp_path) -> None:
    """One run's lead returned no work orders and no decisions on eight carried
    items, and the sprint closed as if it had declined them."""
    from app.agents.technical_lead import MilestonePlanOutput
    from test_graph_routing import _milestone

    silent = MilestonePlanOutput(selected_sprint_goal="Sprint 2: more")
    TestWhatTheyFindIsCarriedForward._two_sprints(agents, monkeypatch, silent)
    agents.script("technical_lead", [
        responds_with(_milestone("testing")), responds_with(silent),
        responds_with(silent.model_copy(update={
            "carried_forward_decisions": ["UX-1: declined - styles.css already has the rule at 600px"],
        })),
    ])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-silent-lead")

    assert len(agents.requests["technical_lead"]) == 3
    assert "records 0. Give one line per item" in agents.last_request_text("technical_lead")
    assert state["stage"] == "complete"
