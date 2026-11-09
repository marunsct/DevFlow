"""A product no pack set up that serves through a development server ships with a note saying so (HR2.PR.12).

Both Falcon products served through `wsgiref.simple_server` while their declared dependencies named a production
server. A pack's start is the pack's own choice and is not read.
"""
from __future__ import annotations

import inspect

from app import completion_verdict
from app.graph import delivery
from app.plugins import seed


def _a_product(tmp_path, code: str):
    (tmp_path / ".project-directory").write_text("notes")
    (tmp_path / "notes" / "notes_api").mkdir(parents=True)
    (tmp_path / "notes" / "notes_api" / "main.py").write_text(code)
    (tmp_path / "notes" / "tests").mkdir()
    (tmp_path / "notes" / "tests" / "test_x.py").write_text("from wsgiref.simple_server import make_server\n")
    return tmp_path


def test_a_product_serving_through_wsgiref_gets_a_note(tmp_path) -> None:
    root = _a_product(tmp_path, "from wsgiref.simple_server import make_server\nmake_server('', 8000, app).serve_forever()\n")
    note = delivery._a_development_server(root)
    assert len(note) == 1 and "`wsgiref.simple_server` in `notes/notes_api/main.py`" in note[0]
    assert not completion_verdict.is_blocking(note[0]), "a note: the product works, it is not served for others"


def test_a_product_on_a_production_server_gets_none_and_tests_are_not_read(tmp_path) -> None:
    root = _a_product(tmp_path, "import uvicorn\n")
    assert delivery._a_development_server(root) == []


def test_a_pack_s_own_choice_is_not_read(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    root = _a_product(tmp_path, "from wsgiref.simple_server import make_server\n")
    monkeypatch.setattr("app.stacks.contract.the_pack", lambda root: (SimpleNamespace(name="php-slim-api"), {}))
    assert delivery._a_development_server(root) == []


def test_the_servers_are_listed_per_language_in_the_seed_table() -> None:
    assert "wsgiref.simple_server" in seed.DEVELOPMENT_SERVERS["python"]
    assert "wsgiref" not in inspect.getsource(delivery._a_development_server)
