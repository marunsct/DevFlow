"""The architect is told the layout the scaffold sets up before it writes the file plan.

Measured on one run: the file plan put the service in `backend/app/` and the
page in `frontend/src/` while the scaffold served the package's `main.py` and
`src/App.tsx`; the repair that checks it came too late and never ran, and 28
files were drafted where nothing served them.
"""
from __future__ import annotations

import inspect
import re
from types import SimpleNamespace

from app.graph import workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_layout_names_the_served_files_and_the_test_folders(tmp_path):
    (tmp_path / ".project-directory").write_text("board-app\n")
    (tmp_path / "board-app").mkdir()
    stack = SimpleNamespace(language="Python", framework="FastAPI", frontend_framework="React",
                            testing_framework="pytest, Playwright", product_kind="fullstack")
    state = {"stack_selection": SimpleNamespace(technology_stack=stack), "document": SimpleNamespace(text=""),
             "repository": SimpleNamespace(root_path=str(tmp_path))}

    text = workflow._the_scaffold_s_layout(state)

    assert "`board-app/src/App.tsx`" in text and "`board-app/board_app/main.py`" in text
    assert "in `board-app/tests/`" in text and "in `board-app/acceptance/`" in text
    assert not BANNED.search(text)


def test_no_pack_says_nothing():
    assert workflow._the_scaffold_s_layout({}) == ""


def test_the_architect_s_first_request_carries_it():
    source = inspect.getsource(workflow)
    assert 'request["messages"][-1]["content"] += _the_scaffold_s_layout(state)' in source


def _state(tmp_path, **stack):
    (tmp_path / ".project-directory").write_text("board-app\n")
    (tmp_path / "board-app").mkdir(exist_ok=True)
    return {"stack_selection": SimpleNamespace(technology_stack=SimpleNamespace(**stack)),
            "document": SimpleNamespace(text=""), "repository": SimpleNamespace(root_path=str(tmp_path))}


def test_the_layout_says_where_data_lives_and_what_the_schema_must_work_on(tmp_path):
    """Measured live: told the files and not the data, the architect planned a
    server's column types and search for a product every test runs on the file
    database - a schema that fails before the service can start."""
    state = _state(tmp_path, language="Python", framework="FastAPI", frontend_framework="React",
                   testing_framework="pytest, Playwright", product_kind="fullstack", database="PostgreSQL")

    text = workflow._the_scaffold_s_layout(state)

    assert "file database" in text and "`DATABASE_URL`" in text
    assert "must work on that file database" in text
    assert not BANNED.search(text)


def test_a_service_pack_says_it_too(tmp_path):
    state = _state(tmp_path, language="Go", framework="Gin", frontend_framework="",
                   testing_framework="", product_kind="service", database="PostgreSQL")

    assert "must work on that file database" in workflow._the_scaffold_s_layout(state)


def test_whoever_writes_the_code_is_told_it_as_well():
    from app.stacks.packs import _fullstack, _service, fullstack_next

    for guide in (_fullstack.DATA_GUIDE, _service.DATA_GUIDE, fullstack_next.GUIDE):
        assert "must work on that file database" in guide
        assert not BANNED.search(guide)
