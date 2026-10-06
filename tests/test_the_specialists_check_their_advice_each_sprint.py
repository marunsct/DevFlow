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
