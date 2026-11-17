"""A file plan that never names the files the scaffold serves goes back to the architect.

One run planned its product in frontend/ and backend/app/; the scaffold served
src/App.tsx and the package's main.py, nothing drafted was served, and every
page test failed its first control.
"""

from __future__ import annotations

import inspect
import re
from types import SimpleNamespace

from app.graph import workflow
from app.graph.workflow import _the_served_files_the_plan_leaves_out

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
STACK = SimpleNamespace(
    language="Python", framework="FastAPI", frontend_framework="React", database="SQLite",
    testing_framework="pytest and Playwright", product_kind="fullstack", additional_tools=[],
)


def _state(tmp_path):
    (tmp_path / ".project-directory").write_text("notes-app\n")
    return {
        "stack_selection": SimpleNamespace(technology_stack=STACK),
        "document": SimpleNamespace(text="A notes page with its own service."),
        "repository": SimpleNamespace(root_path=str(tmp_path)),
    }


def test_a_plan_elsewhere_is_told_the_files_that_are_served(tmp_path):
    spec = SimpleNamespace(file_plan=["notes-app/frontend/src/App.jsx: the page", "notes-app/backend/app/main.py: routes"])

    assert _the_served_files_the_plan_leaves_out(spec, _state(tmp_path)) == ["src/App.tsx", "notes_app/main.py"]


def test_a_plan_in_the_served_files_passes(tmp_path):
    spec = SimpleNamespace(file_plan=["notes-app/src/App.tsx: the page", "notes-app/notes_app/main.py: routes"])

    assert _the_served_files_the_plan_leaves_out(spec, _state(tmp_path)) == []


def test_the_send_back_names_them_in_plain_words():
    source = inspect.getsource(workflow)
    at = source.index("The project's scaffold serves ")
    told = source[at:at + 700]
    assert "Return only `file_plan`" in told and not BANNED.search(told)


def test_a_served_path_inside_another_folder_is_not_the_served_file(tmp_path):
    spec = SimpleNamespace(file_plan=["notes-app/frontend/src/App.tsx: the page", "notes-app/notes_app/main.py: routes"])

    assert _the_served_files_the_plan_leaves_out(spec, _state(tmp_path)) == ["src/App.tsx"]


SERVED = ["notes-api/src/app.ts"]


def _a_plan_that_leaves_out(served, **owing):
    """The checks the node runs after a draft: the served files left out, a setting it cannot start without and
    advice it does not answer, each as given."""
    return {
        "app.graph.workflow._the_served_files_the_plan_leaves_out": lambda spec, state: list(served),
        "app.graph.workflow._settings_it_cannot_start_without": lambda spec: list(owing.get("startup", [])),
        "app.agents.specialist_advice.what_the_specification_owes": lambda spec, advice: list(owing.get("advice", [])),
    }


def test_the_layout_is_checked_first_on_a_budget_of_its_own(tmp_path):
    """Measured live: the check came last in a chain sharing two repairs, both
    went to earlier problems, and a plan building where nothing served it was
    approved; 28 files were drafted there."""
    from typing import get_type_hints

    from workflow_nodes import a_specification, an_architect, an_architect_state

    owing = _a_plan_that_leaves_out(SERVED, startup=["PORT"], advice=["the database advice is not answered"])
    # Ahead of the other repairs, and on its own count: the specification's repairs being spent does not stop it.
    state = an_architect_state(tmp_path, specification_repair_count=workflow.MAX_SPECIFICATION_REPAIRS)
    update, _, _ = an_architect(state, a_specification(), patches=owing)

    assert update["stage"] == "principal_architect"
    assert update["layout_repair_count"] == 1
    assert update.get("specification_repair_count") is None
    # Its own repairs spent, the draft goes on to the review.
    state = an_architect_state(tmp_path, layout_repair_count=workflow.MAX_SPECIFICATION_REPAIRS)
    update, _, _ = an_architect(state, a_specification(), patches=_a_plan_that_leaves_out(SERVED))
    assert update["stage"] == "architecture_review" and update.get("layout_repair_count") is None
    # A count the graph's state does not declare is dropped between stages, and the budget would never be spent.
    assert "layout_repair_count" in get_type_hints(workflow.WorkflowGraphState)


def test_the_architect_sends_it(tmp_path):
    from workflow_nodes import a_specification, an_architect, an_architect_state

    state = an_architect_state(tmp_path)
    update, _, _ = an_architect(state, a_specification(), patches=_a_plan_that_leaves_out(SERVED))

    (repair,) = update["revision_comments"]
    assert repair == workflow._the_layout_repair(SERVED, state)
    assert "notes-api/src/app.ts" in repair


def test_the_send_back_names_each_served_file_from_the_workspace_root(tmp_path):
    """Measured live: told "the scaffold serves `src/App.tsx`, `pkg/main.py`" with no
    folder, the architect planned `pkg/src/App.tsx` - the page inside the service's
    package - and two repairs later the plan still built it where nothing served it."""
    told = workflow._the_layout_repair(["src/App.tsx", "notes_app/main.py"], _state(tmp_path))

    assert "`notes-app/src/App.tsx`" in told and "`notes-app/notes_app/main.py`" in told
    assert "workspace root" in told
    assert "Return only `file_plan`" in told and not BANNED.search(told)
