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
