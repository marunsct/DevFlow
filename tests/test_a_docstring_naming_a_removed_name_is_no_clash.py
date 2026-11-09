"""A clash is settled once the using file no longer imports the removed name, whatever its docstring mentions.

Measured on one run: a removed `health` was re-checked after each of two fixes, and held open both times because the
test's module docstring listed "health" among what it covers - a triple-quoted string spanning lines was read as code.
"""
from __future__ import annotations

from app.agents import interface_clashes

DESCRIPTION = ("`health` was removed from `app/notes_api/main.py` by specialist_backend_0, and "
               "`app/tests/test_main.py` still uses it")

TEST = '''"""Tests of the service.

Covers:
- HTTP endpoints (POST, GET list, PUT, DELETE, health)
"""
from notes_api.main import NoteCreate, app


def test_health_returns_200(client):
    assert client.get("/health").status_code == 200
'''


def _workspace(tmp_path, test_text):
    (tmp_path / "app" / "notes_api").mkdir(parents=True)
    (tmp_path / "app" / "tests").mkdir()
    (tmp_path / "app" / "notes_api" / "main.py").write_text("app = object()\nclass NoteCreate: ...\n")
    (tmp_path / "app" / "tests" / "test_main.py").write_text(test_text)
    return tmp_path


def test_a_name_only_in_the_docstring_and_a_route_string_is_settled(tmp_path):
    assert interface_clashes.still_clashing(_workspace(tmp_path, TEST), DESCRIPTION) is False


def test_a_name_still_imported_still_clashes(tmp_path):
    root = _workspace(tmp_path, TEST.replace("import NoteCreate, app", "import NoteCreate, app, health"))
    assert interface_clashes.still_clashing(root, DESCRIPTION) is True


def test_a_name_still_used_in_code_still_clashes(tmp_path):
    root = _workspace(tmp_path, TEST.replace('client.get("/health")', "main.health(client)").replace(
        "from notes_api.main import NoteCreate, app", "from notes_api import main"))
    assert interface_clashes.still_clashing(root, DESCRIPTION) is True
