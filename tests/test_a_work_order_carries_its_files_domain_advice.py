"""A work order carries the adopted advice of the domains its files are in, and goes to the role owning them (SK.1).

Measured on a medium run (thorough delivery, a Python service with a React page): only the backend and testing
builders ran. The backend builder wrote the database models with no database guidance, and its first request named
only BE-2 and SR-8 of the adopted advice - none of the database specialist's DB items - so the models had integer ids
where the specification adopted UUIDs, no timestamps and no indexes, which the database specialist then reported as
not built.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.agents.principal_architect import TechnicalSpecificationOutput
from app.agents.specialists import SpecialistOutput
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.analysis.file_domains import domains_of
from app.graph import workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

ADVICE = {
    "ui_ux": ["The list shows each note's title in bold above its body."],
    "database": ["Every note is identified by a UUID, never a sequential integer.",
                 "Each note stores created_at and updated_at, set by the store.",
                 "Notes are kept in one JSON file per user."],
    "backend": ["Every error answers with one JSON shape: {\"error\": message}."],
    "security_reliability": ["A sign-in token expires after one hour."],
}
SPEC = TechnicalSpecificationOutput(
    product_scope="Notes.",
    specialist_advice_decisions=[
        "UX-1: adopted - interface_design", "DB-1: adopted - data model", "DB-2: adopted - data model",
        "DB-3: declined - the brief asks for SQLite", "BE-1: adopted - error catalogue", "SR-1: adopted - security",
    ],
)
MODELS_AND_ROUTES = ["notes/app/models.py", "notes/app/schemas.py", "notes/app/routes.py", "notes/app/main.py"]


def a_sprint(root: Path, *orders: SpecialistTask) -> dict:
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "milestone_plan": MilestonePlanOutput(selected_sprint_goal="Notes", delegated_tasks=list(orders)),
        "drafted_for_plan": True,
        "specialist_advice": ADVICE,
        "technical_specification": SPEC,
        "specialist_outputs": {},
        "specialist_task_index": 0,
    }


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


def test_a_backend_builder_writing_the_data_models_is_handed_the_database_specialist_s_adopted_items(tmp_path, builders):
    order = SpecialistTask(specialist_role="backend", task_description="Build the notes service",
                           files=MODELS_AND_ROUTES)

    dispatch(tmp_path, a_sprint(tmp_path, order))

    told = builders["specialist_backend_0"]
    assert "DB-1: Every note is identified by a UUID" in told
    assert "DB-2: Each note stores created_at and updated_at" in told
    assert "BE-1: Every error answers with one JSON shape" in told
    assert "DB-3" not in told, "a declined item is no builder's"
    assert "UX-1" not in told, "no file of this order is the interface's"
    # And the database specialist's guidance, naming the data-layer files.
    guidance = told[told.index("--- Your files in another specialist's domain ---"):]
    assert "database specialist" in guidance and "`notes/app/models.py`" in guidance


def test_a_page_builder_gets_only_the_interface_s_items_and_no_guidance_for_its_own_domain(tmp_path, builders):
    order = SpecialistTask(specialist_role="ui_ux", task_description="Build the notes page",
                           files=["web/src/NoteList.tsx", "web/src/styles.css"])

    dispatch(tmp_path, a_sprint(tmp_path, order))

    told = builders["specialist_ui_ux_0"]
    assert "UX-1: The list shows each note's title" in told
    assert "DB-1" not in told and "BE-1" not in told
    assert "another specialist's domain" not in told


def test_a_builder_whose_files_hold_sign_in_gets_the_security_items(tmp_path, builders):
    order = SpecialistTask(specialist_role="backend", task_description="Build sign-in",
                           files=["notes/app/routes/auth.py"])

    dispatch(tmp_path, a_sprint(tmp_path, order))

    told = builders["specialist_backend_0"]
    assert "SR-1: A sign-in token expires after one hour." in told
    assert "security specialist" in told


def test_the_advice_one_builder_carries_is_bounded(tmp_path, builders):
    many = {role: [f"{role} item {n}: " + "a long sentence of advice " * 20 for n in range(10)]
            for role in ("database", "backend", "ui_ux")}
    state = a_sprint(tmp_path, SpecialistTask(specialist_role="backend", task_description="Build it",
                                              files=[*MODELS_AND_ROUTES, "web/src/App.tsx"]))
    state["specialist_advice"] = many
    state["technical_specification"] = TechnicalSpecificationOutput(product_scope="x")

    dispatch(tmp_path, state)

    told = builders["specialist_backend_0"]
    block = told[told.index("--- The specialists' adopted advice"):]
    block = block[:block.index("--- Your files in another specialist's domain ---")]
    assert len(block) < 5_000
    assert "more adopted item(s) are in the specification's Specialist Advice and Decisions" in block


def _the_lead_s_plan_after_the_harness(tmp_path, monkeypatch, plan: MilestonePlanOutput) -> MilestonePlanOutput:
    """The technical lead node's plan, its agent stood in for and returning `plan` (thorough delivery)."""
    from app import delivery
    from app.agents.scrum_master import SprintDefinition, SprintPlanOutput

    monkeypatch.setattr(delivery, "fast", lambda environment=None: False)
    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "off")
    sprint = SprintDefinition(goal="Notes", user_value="notes", in_scope=["Build the notes service"],
                              out_of_scope=[], acceptance_criteria=["works"], dependencies=[])
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "sprint_plan": SprintPlanOutput(sprints=[sprint], success_measure_coverage=[]),
        "technical_specification": SPEC,
        "current_sprint_index": 0,
    }
    with patch("app.graph.workflow.create_technical_lead_agent", return_value=MagicMock()), \
         patch("app.graph.acceptance_nodes.sprint_already_done", return_value=""), \
         patch("app.graph.workflow._run_gated_agent", return_value={"milestone_plan": plan}):
        graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))
        update = graph.nodes["technical_lead"].bound.invoke(state, {"configurable": {"thread_id": "t"}})
    return update["milestone_plan"]


def test_a_work_order_mainly_in_one_domain_goes_to_the_role_owning_it_and_one_spanning_domains_keeps_its_role(
        tmp_path, monkeypatch):
    lead_s = MilestonePlanOutput(selected_sprint_goal="Notes", delegated_tasks=[
        SpecialistTask(specialist_role="backend", title="Data layer", task_description="Write the store",
                       files=["notes/app/models.py", "notes/app/db.py", "notes/app/schemas.py"]),
        SpecialistTask(specialist_role="backend", title="Service", task_description="Write the service",
                       files=["notes/app/main.py", "notes/app/routes/notes.py", "notes/app/repository.py"]),
        SpecialistTask(specialist_role="backend", title="Page", task_description="Write the page",
                       files=["notes/web/index.html", "notes/web/styles.css"]),
        SpecialistTask(specialist_role="testing", title="Tests", task_description="Write the unit tests",
                       files=["notes/tests/test_models.py"]),
    ])

    plan = _the_lead_s_plan_after_the_harness(tmp_path, monkeypatch, lead_s)

    roles = {task.title: task.specialist_role for task in plan.delegated_tasks}
    assert roles == {"Data layer": "database", "Service": "backend", "Page": "ui_ux", "Tests": "testing"}


@pytest.mark.parametrize(("path", "primary"), [
    ("notes/app/models.py", "data"),
    ("backend/app/schemas.py", "data"),
    ("db/migrations/001_init.sql", "data"),
    ("prisma/schema.prisma", "data"),
    ("src/main/java/com/acme/notes/repository/NoteRepository.java", "data"),
    ("internal/store/sqlite.go", "data"),
    ("app/routers/notes.py", "service"),
    ("src/controllers/NotesController.cs", "service"),
    ("server.js", "service"),
    ("web/src/components/NoteList.tsx", "interface"),
    ("public/styles.css", "interface"),
    ("app/views/notes/index.html.erb", "interface"),
    ("frontend/src/api/client.ts", "interface"),
])
def test_a_file_s_domain_is_read_from_its_path_in_any_stack(path, primary):
    assert domains_of(path)[0] == primary


@pytest.mark.parametrize("path", [
    "tests/test_models.py", "src/__tests__/NoteList.test.tsx", "README.md", "package.json", "app/main.py", "app.js",
])
def test_a_test_a_document_a_manifest_and_a_file_whose_path_says_nothing_have_no_domain(path):
    assert domains_of(path) == ()


def test_the_text_a_builder_is_given_avoids_the_banned_words(tmp_path, builders):
    order = SpecialistTask(specialist_role="ui_ux", task_description="Build the notes page",
                           files=["notes/app/models.py", "notes/app/routes.py", "notes/app/auth.py", "web/page.tsx"])
    dispatch(tmp_path, a_sprint(tmp_path, order))
    told = builders["specialist_ui_ux_0"]
    guidance = told.index("--- Your files in another specialist's domain ---")
    harness_s = told[told.index("--- The specialists' adopted advice"):told.find("\n\n", guidance)]

    assert "database specialist" in harness_s and "backend specialist" in harness_s and "security specialist" in harness_s
    assert not BANNED.findall(harness_s)


class _Drafter:
    """The drafting model stood in for at its edge: records each request and answers with a small file."""

    def __init__(self):
        self.asked: list[str] = []

    def bind(self, **kwargs):
        return self

    def invoke(self, messages, **kwargs):
        self.asked.append(str(messages[-1].content))
        return SimpleNamespace(content="```python\nVALUE = 1\n```")


def test_a_file_drafted_whole_is_handed_its_domain_s_adopted_items(tmp_path, monkeypatch):
    """Fast delivery drafts each file from the specification: the data-layer file of a backend order is given the
    database specialist's items and guidance, the route file the backend's."""
    from app.graph.drafting import draft_work_orders

    monkeypatch.delenv("DOMAIN_CRAFT_CHECKLISTS", raising=False)
    monkeypatch.setenv("DRAFTING_IN_WAVES", "off")
    order = SpecialistTask(specialist_role="backend", task_description="Build the notes service",
                           files=["notes/app/models.py", "notes/app/routes.py"])
    drafter = _Drafter()

    draft_work_orders([order], SPEC, None, str(tmp_path), drafter, write=lambda root, path, content: None,
                      advice=ADVICE)

    models = next(text for text in drafter.asked if "`notes/app/models.py`" in text.split("\n", 1)[0])
    routes = next(text for text in drafter.asked if "`notes/app/routes.py`" in text.split("\n", 1)[0])
    assert "DB-1: Every note is identified by a UUID" in models and "database specialist would" in models
    assert "BE-1: Every error answers with one JSON shape" in routes
    assert "DB-1" not in routes


def test_a_builder_whose_order_spans_the_page_is_given_the_interface_design(tmp_path, builders):
    state = a_sprint(tmp_path, SpecialistTask(specialist_role="backend", task_description="Build the service and page",
                                              files=["notes/app/routes.py", "notes/web/index.html"]))
    state["technical_specification"] = SPEC.model_copy(update={"interface_design": ["Titles in bold, 1.25rem."]})

    dispatch(tmp_path, state)

    told = builders["specialist_backend_0"]
    assert "--- The interface design in the specification" in told and "Titles in bold, 1.25rem." in told
