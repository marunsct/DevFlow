"""A defect's fixer is handed the specification's entries for its files and criteria.

A fix is built by the faster model too, and was handed none of it. Measured
on one run: the specification gave the store's load rule as
"nextId = max(stored nextId, max(existing id)+1)" and the route handlers'
body parsing inside a try/catch; the builder wrote neither, and the fixers
sent to repair both were shown only the defect.
"""

from __future__ import annotations

from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    _approved_review,
    _defect,
    _document,
    _graph,
    _milestone,
    _milestone_review,
    _repository,
    _security_review,
    _spec,
    _specialist,
    _sprint_plan,
    agents,
    responds_with,
)
from test_graph_routing import _intake, _stack_selector, _tools

from app.graph.workflow import start_workflow

RULE = "load() sets nextId = max(stored nextId, max(existing id)+1)"


def test_the_fixer_reads_the_contract_for_the_file_it_fixes(agents, tmp_path, monkeypatch):
    monkeypatch.setattr("app.agents.specialists.what_the_files_already_prove", lambda *a, **k: [])
    spec = _spec().model_copy(update={
        "function_contracts": [f"src/store.py {RULE}", "src/page.py render() draws the list"],
        "test_cases": ["AC-3 test_ac3_restart_keeps_ids: create, restart, create; ids never repeat"],
    })
    defect = _defect(owner="backend", description="[AC-3] ids repeat after a restart").model_copy(
        update={"affected_files": ["src/store.py"]}
    )
    agents.script("product_manager", [responds_with(_intake())])
    agents.script("tools_models", [responds_with(_tools())])
    agents.script("stack_selector", [responds_with(_stack_selector())])
    agents.script("principal_architect", [responds_with(spec)])
    agents.script("architecture_review", [responds_with(_approved_review())])
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    agents.script("specialist_backend", [responds_with(_specialist()), responds_with(_specialist(tests=["t-1"]))])
    agents.script("specialist_testing", [responds_with(_specialist(defects=[defect])), responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-fix-spec")

    assert state["stage"] == "complete", state.get("error")
    fix = agents.last_request_text("specialist_backend")
    assert RULE in fix
    assert "test_ac3_restart_keeps_ids" in fix, "the criterion's tests, by its id"
    assert "render() draws the list" not in fix, "only this defect's entries"
