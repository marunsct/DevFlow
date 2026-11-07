"""Builders on a proven setup see the setup's own product code as it was proven.

Measured on a stack no pack covers: the specification, written before the setup existed, created the application with
the framework's other server interface; the builders followed it, and the product the setup had proven to start
answered nothing - every acceptance criterion failed at once.
"""
from __future__ import annotations

import re

from app.agents.shared_facts import layout_facts
from app.stacks.custom_setup import PROVEN_SETUP, Declaration, _the_setup_s_own_code, pack_from

ENTRY = "import falcon\nimport falcon.asgi\n\napp = falcon.asgi.App()\n"


def _declared(**over):
    base = dict(kind="http_api", install=(), unit_test=("pytest",), unit_report="u.xml", unit_dir="tests",
                unit_pattern="test_*.py", acceptance_test=("pytest",), acceptance_report="a.xml",
                acceptance_dir="acceptance", acceptance_pattern="test_*.py", kept_files=("start.sh",),
                smoke_files=("tests/test_smoke.py",), guide="", acceptance_guide="")
    return Declaration(**{**base, **over})


def test_the_setup_s_own_entry_is_recorded_and_tests_and_dependencies_are_not(tmp_path):
    (tmp_path / "notes_api").mkdir()
    (tmp_path / "notes_api" / "main.py").write_text(ENTRY)
    (tmp_path / "notes_api" / "__init__.py").write_text("")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_smoke.py").write_text("def test_x(): pass\n")
    (tmp_path / ".venv" / "lib").mkdir(parents=True)
    (tmp_path / ".venv" / "lib" / "site.py").write_text("x = 1\n")
    (tmp_path / "start.sh").write_text("exec x\n")
    assert _the_setup_s_own_code(tmp_path, _declared()) == {"notes_api/main.py": ENTRY}


def test_the_builders_are_shown_it_and_told_it_stands_over_the_specification():
    setup = {"kind": "http_api", "unit_test": ["pytest"], "acceptance_test": ["pytest"], "unit_report": "u.xml",
             "acceptance_report": "a.xml", "unit_dir": "tests", "acceptance_dir": "acceptance",
             "unit_pattern": "test_*.py", "acceptance_pattern": "test_*.py", "kept": {},
             "proven_code": {"notes_api/main.py": ENTRY}}
    pack = pack_from({"pack": PROVEN_SETUP, "setup": setup})
    text = "\n".join(layout_facts(pack, "notes-api", "notes_api"))
    assert "app = falcon.asgi.App()" in text and "`notes-api/notes_api/main.py`" in text
    assert "proven to start" in text
    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert not re.search(rf"\b{re.escape(word)}\b", text, re.I)
