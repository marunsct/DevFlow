"""Craft checklists by the domains of a builder's files, and the same bars for the advisers (SK.2 with PQ.6 and PQ.9;
`DOMAIN_CRAFT_CHECKLISTS`, off until measured).

A review of eight stored products found them correct and plain: no empty, busy or failure state on the pages, raw
colours beside the pack's design tokens; no constraints, indexes or timestamps in the data; services answering 500
for a forbidden or duplicate request, with several error shapes. The UI/UX adviser was never told the pack ships
design tokens, and the database and backend advice requests asked for less than the UI/UX one.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.agents.specialists import SpecialistOutput
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.graph import workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
HEADING = "--- Craft checklist for your files ---"


def a_sprint(root: Path, *orders: SpecialistTask) -> dict:
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "milestone_plan": MilestonePlanOutput(selected_sprint_goal="Notes", delegated_tasks=list(orders)),
        "drafted_for_plan": True,
        "specialist_outputs": {},
        "specialist_task_index": 0,
    }


def scaffolded_from(root: Path, pack: str, project: str) -> Path:
    (root / ".harness").mkdir(parents=True, exist_ok=True)
    (root / ".harness" / "stack-pack.json").write_text(json.dumps({"pack": pack, "project": project}))
    return root


@pytest.fixture()
def builders(monkeypatch):
    """The builder stages, their model stood in for: each request handed to a builder is recorded by stage."""
    handed: dict[str, str] = {}

    def gated(state, config, *, stage_name, initial_request, output_key, **kwargs):
        handed[stage_name] = initial_request["messages"][-1]["content"]
        return {output_key: SpecialistOutput(changed_files=[]), "stage": kwargs.get("next_stage")}

    monkeypatch.setenv("DELIVERY_MODE", "thorough")
    monkeypatch.delenv("DOMAIN_CRAFT_CHECKLISTS", raising=False)
    monkeypatch.setattr(workflow, "create_specialist_agent", lambda role, *a, **k: SimpleNamespace(role=role))
    monkeypatch.setattr(workflow, "_run_gated_agent", gated)
    monkeypatch.setattr("app.server.runtime_settings.effective_settings",
                        lambda: SimpleNamespace(execution_mode="linear"))
    return handed


def dispatch(root: Path, state: dict) -> dict:
    graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(root))
    return graph.nodes["specialist_dispatch"].bound.invoke(state, {"configurable": {"thread_id": "t"}})


SERVICE_ORDER = SpecialistTask(specialist_role="backend", task_description="Build the notes service",
                               files=["notes/app/models.py", "notes/app/routes.py"])


def test_off_a_builder_is_given_no_checklist(tmp_path, builders):
    dispatch(tmp_path, a_sprint(tmp_path, SERVICE_ORDER))

    assert HEADING not in builders["specialist_backend_0"]


def test_on_a_builder_of_models_and_routes_gets_the_data_and_service_lines_and_not_the_interface_s(
        tmp_path, builders, monkeypatch):
    monkeypatch.setenv("DOMAIN_CRAFT_CHECKLISTS", "on")

    dispatch(tmp_path, a_sprint(tmp_path, SERVICE_ORDER))

    checklist = builders["specialist_backend_0"].split(HEADING, 1)[1]
    assert "an index on each field records are looked up, filtered or sorted by" in checklist
    assert "created and last changed" in checklist
    assert "one error shape for every failure" in checklist
    assert "a record that is not the caller's" in checklist
    assert "no input accepted and then ignored" in checklist
    assert "in flight" not in checklist


def test_on_a_page_builder_is_pointed_at_the_tokens_its_pack_ships(tmp_path, builders, monkeypatch):
    monkeypatch.setenv("DOMAIN_CRAFT_CHECKLISTS", "on")
    root = scaffolded_from(tmp_path, "browser-javascript", "notes")
    order = SpecialistTask(specialist_role="ui_ux", task_description="Build the page",
                           files=["notes/index.html", "notes/app.js"])

    dispatch(root, a_sprint(root, order))

    checklist = builders["specialist_ui_ux_0"].split(HEADING, 1)[1]
    assert "while a request is in flight" in checklist and "outside the list of records" in checklist
    assert "`notes/styles.css` declares them" in checklist and "`--color-bg`" in checklist
    assert "never a raw value where a token exists" in checklist
    assert "one error shape" not in checklist


def test_on_a_file_drafted_whole_gets_its_domain_s_checklist(tmp_path, monkeypatch):
    from app.graph.drafting import draft_request

    monkeypatch.setenv("DOMAIN_CRAFT_CHECKLISTS", "on")

    asked = draft_request(tmp_path, "notes/app/db.py", SERVICE_ORDER, None, None)

    assert HEADING in asked and "an index on each field" in asked


def _adviser_s_request(root: Path, role: str, pack: str) -> str:
    """What the consulted `role` is sent (its agent and the model stood in for)."""
    from app.agents.stack_selector import StackSelectorOutput, TechnologyStack
    from workflow_nodes import run_node

    sent = []

    def gated(state, config, *, initial_request, **kwargs):
        sent.append(initial_request["messages"][-1]["content"])
        return {}

    stack = TechnologyStack(language="JavaScript", framework="none", frontend_framework="React", database="SQLite",
                            testing_framework="vitest")
    state = {"repository": SimpleNamespace(root_path=str(root)), "document": SimpleNamespace(text="A notes page."),
             "consultation_roles": [role], "product_intake": "Notes.", "stack_pack": pack,
             "stack_selection": StackSelectorOutput(technology_stack=stack, rationale="It fits.")}
    run_node("specialist_consultation", state, str(root), patches={
        "app.graph.workflow._run_gated_agent": gated,
        "app.graph.workflow.create_specialist_advice_agent": lambda *a, **k: MagicMock()})
    return sent[0]


def test_on_the_ui_ux_adviser_is_told_the_design_tokens_the_pack_ships(tmp_path, monkeypatch):
    monkeypatch.delenv("DOMAIN_CRAFT_CHECKLISTS", raising=False)
    off = _adviser_s_request(tmp_path, "ui_ux", "browser-react")
    monkeypatch.setenv("DOMAIN_CRAFT_CHECKLISTS", "on")

    on = _adviser_s_request(tmp_path, "ui_ux", "browser-react")

    assert "`--color-primary`" not in off
    assert "`src/styles.css` starts with these design tokens" in on and "`--color-primary`" in on
    assert "never a raw value" in on


@pytest.mark.parametrize(("role", "bar"), [
    ("database", "an index on each field records are looked up, filtered or sorted by"),
    ("database", "a stored field the brief does not list is never returned"),
    ("backend", "one error shape for every failure"),
    ("backend", "a stored field the brief does not list is never returned"),
])
def test_on_the_database_and_backend_advisers_are_asked_for_the_same_bars(tmp_path, monkeypatch, role, bar):
    monkeypatch.setenv("DOMAIN_CRAFT_CHECKLISTS", "on")

    assert bar in _adviser_s_request(tmp_path, role, "browser-react")


def test_on_the_architect_is_told_the_design_tokens_the_pack_ships(tmp_path, monkeypatch):
    from app.agents.principal_architect import TechnicalSpecificationOutput
    from app.agents.stack_selector import StackSelectorOutput, TechnologyStack
    from app.state import RepositoryContext

    monkeypatch.setenv("DOMAIN_CRAFT_CHECKLISTS", "on")
    stack = TechnologyStack(language="JavaScript", framework="none", frontend_framework="", database="localStorage",
                            testing_framework="node:test, Playwright", product_kind="browser_app")
    state = {
        "stack_selection": StackSelectorOutput(technology_stack=stack, rationale="As the brief asks."),
        "stack_pack": "browser-javascript",
        "document": SimpleNamespace(text="A notes page."),
        "repository": RepositoryContext(root_path=str(tmp_path), branch="main", commit="abc", status="clean"),
        "product_intake": {"product_name": "Notes"},
        "tools_models": {"plan": "local"},
    }
    asked: list[str] = []

    def gated(_state, _config, *, initial_request, output_key, **_kwargs):
        asked.append(initial_request["messages"][-1]["content"])
        return {output_key: TechnicalSpecificationOutput(product_scope="Notes."), "stage": "architecture_review"}

    with patch("app.graph.workflow.create_principal_architect_agent", return_value=MagicMock()), \
         patch("app.agents.research_brief.research_notes", return_value=""), \
         patch("app.graph.workflow._fast_delivery", return_value=False), \
         patch("app.graph.workflow._run_gated_agent", side_effect=gated):
        graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))
        graph.nodes["principal_architect"].bound.invoke(state, {"configurable": {"thread_id": "t", "run_id": "r"}})

    assert "`styles.css` starts with these design tokens" in asked[0] and "`--color-text`" in asked[0]


def test_the_checklists_and_the_adviser_bars_avoid_the_banned_words(tmp_path, monkeypatch):
    from app.agents import domain_craft
    from app.stacks import pack_named

    monkeypatch.setenv("DOMAIN_CRAFT_CHECKLISTS", "on")
    texts = [
        domain_craft.checklist("backend", ["web/index.html", "app/models.py", "app/routes.py"],
                               pack_named("browser-react"), "notes"),
        domain_craft.tokens_note("browser-react"),
        _adviser_s_request(tmp_path, "database", "browser-react"),
        _adviser_s_request(tmp_path, "backend", "browser-react"),
    ]

    assert all(texts[:2])
    for text in texts[:2]:
        assert not BANNED.findall(text)
    for text in texts[2:]:
        bars = text[text.index("Cover these bars too"):]
        assert not BANNED.findall(bars)
