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
        (_stack("http_api", database="PostgreSQL", framework="Express"), ["database", "backend"]),
        (_stack("fullstack", database="SQLite", framework="Express", frontend="React"), ["ui_ux", "database", "backend"]),
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
    def _consulting(monkeypatch, agents: ScriptedAgents, roles: list[str]) -> None:
        monkeypatch.setattr(specialist_advice, "roles_to_consult", lambda *args, **kwargs: list(roles))
        monkeypatch.setattr(
            workflow_module, "create_specialist_advice_agent",
            lambda role, *args, **kwargs: agents.agent(f"advisor_{role}"),
        )

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
