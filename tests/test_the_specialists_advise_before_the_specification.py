"""The specialists a product needs advise before the specification is written.

The architect wrote the specification alone, and nothing in it described the
interface. Measured over the last 26 stored products: 20 shipped the scaffold's
11-line stylesheet untouched by any stage. Now the UI/UX specialist is asked
when the product has an interface, the database specialist when it keeps data
of its own, the backend specialist when it serves requests; the specification
answers each item by id, a product with an interface gets an `interface_design`
section, and the UI/UX work orders are built to it.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents import specialist_advice
from app.agents.specialist_advice import (
    SpecialistAdvice,
    advice_block,
    roles_to_consult,
    unanswered,
    what_the_specification_owes,
)
from app.agents.tools_models import TechnologyStack
from app.graph import workflow as workflow_module
from app.graph.workflow import start_workflow
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _approved_review,
    _document,
    _graph,
    _intake,
    _repository,
    _script_through_sprint,
    _spec,
    _tools,
    agents,
    responds_with,
)


def _stack(kind: str, database: str = "None", framework: str = "None", frontend: str = "") -> TechnologyStack:
    return TechnologyStack(language="JavaScript", framework=framework, frontend_framework=frontend,
                           database=database, testing_framework="node --test and Playwright",
                           product_kind=kind)


class TestWhoIsAsked:
    @pytest.mark.parametrize("stack, roles", [
        (_stack("browser_app", database="Browser localStorage"), ["ui_ux", "database"]),
        (_stack("browser_app"), ["ui_ux"]),
        # An API anyone can call is one a security specialist must see.
        (_stack("http_api", database="PostgreSQL", framework="Express"), ["database", "backend", "security_reliability"]),
        (_stack("fullstack", database="SQLite", framework="Express", frontend="React"),
         ["ui_ux", "database", "backend", "security_reliability"]),
        # A program run from a terminal has an interface: its commands and messages.
        (_stack("cli"), ["ui_ux"]),
        (_stack("library"), []),
    ])
    def test_by_what_the_product_has(self, stack, roles) -> None:
        assert roles_to_consult(stack) == roles

    @pytest.mark.parametrize("database", ["None", "N/A", "none (not required)", "No database", "not needed", ""])
    def test_a_stack_with_no_store_has_no_data_to_model(self, database) -> None:
        assert "database" not in roles_to_consult(_stack("browser_app", database=database))

    def test_nothing_to_judge_by_asks_nobody(self) -> None:
        assert roles_to_consult(None) == []


class TestTheNewRoles:
    BRIEF = "# Brief\n## Acceptance Criteria\n- Users can add notes\n- Notes persist between page refreshes\n"

    def test_a_brief_with_criteria_asks_the_testing_specialist(self) -> None:
        assert roles_to_consult(_stack("browser_app"), self.BRIEF)[-1] == "testing"

    def test_without_criteria_there_is_nothing_to_make_testable(self) -> None:
        assert "testing" not in roles_to_consult(_stack("browser_app"), "Make something nice.")

    @pytest.mark.parametrize("text", [
        "Users sign in with an email address and a password.",
        "Customers pay by credit card at checkout.",
        "People can upload a photo to each note.",
        "Each account keeps its own list.",
    ])
    def test_a_brief_about_sign_in_money_data_or_files_asks_for_security(self, text) -> None:
        assert "security_reliability" in roles_to_consult(_stack("browser_app"), text)

    @pytest.mark.parametrize("text", [
        "No authentication required",
        "It works without an account.",
        "Users never sign in.",
        "A page that lists notes.",
    ])
    def test_one_that_rules_them_out_does_not(self, text) -> None:
        assert "security_reliability" not in roles_to_consult(_stack("browser_app"), text)

    def test_the_testing_specialist_is_shown_the_criteria_numbered(self) -> None:
        from app.agents.specialist_advice import build_advice_request

        text = build_advice_request("testing", self.BRIEF, "intake", "stack")["messages"][0]["content"]

        assert "- AC-1: Users can add notes" in text and "- AC-2:" in text
        assert "Start each recommendation with the id of the" in text

    def test_its_items_are_answered_like_any_other(self) -> None:
        advice = {"testing": ["AC-1: find the field by its label Title."]}

        assert "TS-1: AC-1: find the field" in advice_block(advice)
        assert unanswered(SimpleNamespace(specialist_advice_decisions=[]), advice) == ["TS-1"]


class TestWhatWasAdopted:
    ADVICE = {"testing": ["AC-1: one", "AC-2: two", "AC-3: three"]}

    def test_declined_items_are_left_out_and_unanswered_ones_kept(self) -> None:
        from app.agents.specialist_advice import adopted

        spec = SimpleNamespace(specialist_advice_decisions=[
            "TS-1: adopted - testing", "TS-2: Declined - the brief names no such field",
        ])

        assert adopted(self.ADVICE, spec, "testing") == ["TS-1: AC-1: one", "TS-3: AC-3: three"]

    def test_another_role_s_items_are_not_its(self) -> None:
        from app.agents.specialist_advice import adopted

        assert adopted(self.ADVICE, SimpleNamespace(), "ui_ux") == []


ADVICE = {
    "ui_ux": ["Stack the form above the list below 600px.", "Show a message when the list is empty."],
    "database": ["Give every record a generated id."],
}


class TestWhatTheArchitectIsTold:
    def test_each_item_is_numbered_by_its_role(self) -> None:
        block = advice_block(ADVICE)

        assert "UX-1: Stack the form above the list below 600px." in block
        assert "UX-2: Show a message when the list is empty." in block
        assert "DB-1: Give every record a generated id." in block
        assert "`specialist_advice_decisions`" in block and "`interface_design`" in block

    def test_no_advice_tells_it_nothing(self) -> None:
        assert advice_block({}) == "" and advice_block(None) == ""

    def test_both_of_its_requests_carry_the_advice(self, tmp_path) -> None:
        from app.agents.principal_architect import build_architecture_request, build_architecture_revision_request

        first = build_architecture_request("intake", "tools", "stack", _repository(tmp_path), _document(), advice=ADVICE)
        again = build_architecture_revision_request(
            "{}", ["fix it"], "intake", "tools", "stack", _repository(tmp_path), _document(), advice=ADVICE
        )

        for request in (first, again):
            assert "UX-1:" in request["messages"][0]["content"]


class TestWhatTheSpecificationOwes:
    def test_every_item_answered_and_a_design_written_owes_nothing(self) -> None:
        spec = SimpleNamespace(
            specialist_advice_decisions=["UX-1: adopted - interface_design", "UX-2: adopted", "DB-1: declined - ids exist"],
            interface_design=["Below 600px the form sits above the list."],
        )

        assert what_the_specification_owes(spec, ADVICE) == []

    def test_an_item_it_skipped_is_named(self) -> None:
        spec = SimpleNamespace(specialist_advice_decisions=["UX-1: adopted"], interface_design=["x"])

        assert unanswered(spec, ADVICE) == ["UX-2", "DB-1"]

    def test_ux_10_does_not_answer_ux_1(self) -> None:
        advice = {"ui_ux": [f"item {n}" for n in range(1, 11)]}
        spec = SimpleNamespace(specialist_advice_decisions=[f"UX-{n}: adopted" for n in range(2, 11)])

        assert unanswered(spec, advice) == ["UX-1"]

    def test_a_product_with_an_interface_needs_its_design(self) -> None:
        spec = SimpleNamespace(
            specialist_advice_decisions=["UX-1: adopted", "UX-2: adopted", "DB-1: adopted"], interface_design=[]
        )

        assert any("`interface_design` is empty" in problem for problem in what_the_specification_owes(spec, ADVICE))

    def test_without_advice_it_owes_nothing(self) -> None:
        assert what_the_specification_owes(SimpleNamespace(), {}) == []


def test_the_advice_names_no_product_and_no_control() -> None:
    text = " ".join([specialist_advice._SYSTEM_PROMPT, *specialist_advice._WHAT_TO_COVER.values(), advice_block(ADVICE).split("\n", 1)[0]])
    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert not re.search(rf"\b{word}\b", text.lower()), word


class TestTheInterfaceDesignReachesItsBuilders:
    def test_a_ui_ux_work_order_is_given_it(self) -> None:
        from app.agents.specialists import build_specialist_task_request

        request = build_specialist_task_request(
            "Build the list view", ["AC-1"], "/", interface_design=["Below 600px the form sits above the list."]
        )

        text = request["messages"][0]["content"]
        assert "interface design in the specification" in text and "Below 600px" in text

    def test_only_a_ui_ux_task_gets_it(self) -> None:
        state = {"technical_specification": SimpleNamespace(interface_design=["Below 600px ..."])}

        assert workflow_module._the_interface_design_for(state, SimpleNamespace(specialist_role="ui_ux"))
        assert workflow_module._the_interface_design_for(state, SimpleNamespace(specialist_role="backend")) == []

    def test_the_lead_sees_it_among_the_contracts(self) -> None:
        from app.agents.technical_lead import _the_contracts

        spec = _spec(interface_design=["Below 600px the form sits above the list."])

        assert "Interface design" in _the_contracts(spec) and "Below 600px" in _the_contracts(spec)

    def test_the_specification_document_shows_it(self) -> None:
        from app.agents.specification_document import render_specification

        page = render_specification(_spec(
            interface_design=["Below 600px the form sits above the list."],
            specialist_advice_decisions=["UX-1: adopted - interface_design"],
        ))

        assert "## Interface Design" in page and "## Specialist Advice and Decisions" in page

    def test_a_specification_without_them_says_so(self) -> None:
        """Every section has its heading; an empty one says it is empty."""
        from app.agents.specification_document import render_specification

        page = render_specification(_spec())

        assert "## Interface Design" in page and "Below 600px" not in page


class TestThroughTheGraph:
    @staticmethod
    def _consulting(monkeypatch, agents: ScriptedAgents, roles: list[str], reviewing: bool = False) -> None:
        monkeypatch.setattr(specialist_advice, "roles_to_consult", lambda *args, **kwargs: list(roles))
        monkeypatch.setattr(
            workflow_module, "create_specialist_advice_agent",
            lambda role, *args, **kwargs: agents.agent(f"advisor_{role}"),
        )
        if not reviewing:
            # The sprint's check of the adopted advice has tests of its own
            # (`test_the_specialists_check_their_advice_each_sprint.py`).
            from app.agents import advice_review

            monkeypatch.setattr(advice_review, "roles_to_review", lambda *args, **kwargs: [])

    @staticmethod
    def _script_the_stack(agents: ScriptedAgents) -> None:
        from app.agents.stack_selector import StackSelectorOutput

        agents.script("product_manager", [responds_with(_intake())])
        agents.script("tools_models", [responds_with(_tools())])
        agents.script("stack_selector", [responds_with(StackSelectorOutput(
            technology_stack=_stack("browser_app", database="Browser localStorage"), rationale="r",
        ))])

    def test_the_architect_is_told_what_each_specialist_advised(self, agents, monkeypatch, tmp_path) -> None:
        self._consulting(monkeypatch, agents, ["ui_ux", "database"])
        self._script_the_stack(agents)
        agents.script("advisor_ui_ux", [responds_with(SpecialistAdvice(recommendations=ADVICE["ui_ux"]))])
        agents.script("advisor_database", [responds_with(SpecialistAdvice(recommendations=ADVICE["database"]))])
        agents.script("principal_architect", [responds_with(_spec(
            interface_design=["Below 600px the form sits above the list."],
            specialist_advice_decisions=["UX-1: adopted", "UX-2: adopted", "DB-1: adopted"],
        ))])
        agents.script("architecture_review", [responds_with(_approved_review())])
        _script_through_sprint(agents)

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-advised")

        asked = agents.last_request_text("principal_architect")
        assert "UX-1: Stack the form above the list below 600px." in asked and "DB-1:" in asked
        assert state["specialist_advice"] == ADVICE and state["stage"] == "complete"

    def test_a_specification_that_ignores_the_advice_is_sent_straight_back(self, agents, monkeypatch, tmp_path) -> None:
        self._consulting(monkeypatch, agents, ["ui_ux"])
        self._script_the_stack(agents)
        agents.script("advisor_ui_ux", [responds_with(SpecialistAdvice(recommendations=ADVICE["ui_ux"]))])
        agents.script("principal_architect", [
            responds_with(_spec()),
            responds_with(_spec(
                interface_design=["Below 600px the form sits above the list."],
                specialist_advice_decisions=["UX-1: adopted", "UX-2: declined - the brief shows the list only"],
            )),
        ])
        agents.script("architecture_review", [responds_with(_approved_review())])
        _script_through_sprint(agents)

        start_workflow(_graph(), _document(), _repository(tmp_path), "run-advice-owed")

        repair = agents.requests["principal_architect"][1]["messages"][-1]["content"]
        assert "UX-1, UX-2" in repair and "`interface_design` is empty" in repair


def test_a_repair_keeps_the_interface_design_it_did_not_return() -> None:
    previous = _spec(interface_design=["Below 600px the form sits above the list."],
                     specialist_advice_decisions=["UX-1: adopted"])
    repaired = _spec(testing=["node --test runs the logic"])

    kept = workflow_module._with_the_sections_it_dropped(repaired, previous)

    assert kept.interface_design == previous.interface_design
    assert kept.specialist_advice_decisions == ["UX-1: adopted"]


class TestQaWritesAndReviewsToTheTestabilityAdvice:
    LINES = ["TS-1: AC-1: find the field by its label Title, exactly."]

    def test_the_author_is_given_it(self, tmp_path) -> None:
        from app.acceptance import requests as acceptance_requests
        from app.acceptance.criteria import Criterion

        request = acceptance_requests.build_author_request(
            tmp_path, [Criterion(id="AC-1", text="Add a note", source="brief")], testability=self.LINES
        )

        text = request["messages"][0]["content"]
        assert "made testable" in text and "TS-1: AC-1: find the field by its label Title" in text

    def test_the_qa_lead_is_given_it(self) -> None:
        from app.agents.acceptance_reviewer import build_acceptance_review_request

        text = build_acceptance_review_request("AC-1", "suite", "ran", [], "", testability=self.LINES)["messages"][0]["content"]

        assert "testability advice the specification adopted" in text and "TS-1:" in text

    def test_without_it_both_read_as_before(self, tmp_path) -> None:
        from app.agents.acceptance_reviewer import build_acceptance_review_request

        assert "testability" not in build_acceptance_review_request("AC-1", "s", "r", [], "")["messages"][0]["content"]

    def test_the_stage_takes_what_the_specification_adopted(self) -> None:
        state = {
            "specialist_advice": {"testing": ["AC-1: one", "AC-2: two"]},
            "technical_specification": SimpleNamespace(specialist_advice_decisions=["TS-2: declined - no"]),
        }

        assert acceptance_nodes_module()._the_testability_advice(state) == ["TS-1: AC-1: one"]


def acceptance_nodes_module():
    from app.graph import acceptance_nodes

    return acceptance_nodes
