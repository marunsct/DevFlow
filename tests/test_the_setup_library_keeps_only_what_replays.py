"""The setup library keeps only entries that can replay, and sets aside one that failed across a restart (SF.0b).

A smoke test importing the product's own module passes in the run that wrote both and fails in every later run the
entry is replayed into; and the note of which entry was replayed lived in memory only, so a worker restarted between
replay and proof never set a failing entry aside.
"""
from __future__ import annotations

from pathlib import Path

from app.stacks import custom_setup
from app.stacks.custom_setup import Declaration, _smoke_tests_import_the_product


def _declared() -> Declaration:
    return Declaration(kind="http_api", install=(), unit_test=("pytest",), unit_report="u.xml", unit_dir="tests",
                       unit_pattern="test_*.py", acceptance_test=("pytest",), acceptance_report="a.xml",
                       acceptance_dir="acceptance", acceptance_pattern="test_*.py", kept_files=("acceptance/conftest.py",),
                       smoke_files=("tests/test_smoke.py",), guide="", acceptance_guide="")


def test_a_smoke_test_importing_a_product_module_is_found(tmp_path):
    (tmp_path / "notes_api").mkdir()
    (tmp_path / "notes_api" / "__init__.py").write_text("")
    (tmp_path / "notes_api" / "main.py").write_text("app = 1\n")
    files = {"tests/test_smoke.py": "from notes_api.main import app\nimport json\n", "acceptance/conftest.py": ""}
    assert _smoke_tests_import_the_product(tmp_path, _declared(), files) == ["notes_api/__init__.py"]
    files["notes_api/__init__.py"] = ""
    assert _smoke_tests_import_the_product(tmp_path, _declared(), files) == []


def test_a_relative_javascript_import_of_product_code_is_found(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.js").write_text("export default 1\n")
    declared = _declared()
    files = {"tests/test_smoke.py": "import app from '../src/app.js'\n"}
    assert _smoke_tests_import_the_product(tmp_path, declared, files) == ["src/app.js"]


def test_a_failed_replay_is_set_aside_after_a_restart(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    entry = library / "python-falcon.json"
    entry.write_text('{"files": {"pytest.ini": ""}, "declaration": "{}"}')
    monkeypatch.setattr(custom_setup, "_entry_for", lambda stack: entry)
    project = tmp_path / "workspace" / "notes-api"
    project.mkdir(parents=True)
    assert custom_setup.replay(project, stack=None)
    custom_setup._REPLAYED.clear()  # the worker restarted
    assert custom_setup.set_aside_what_did_not_prove(project) == "python-falcon.json"
    assert (library / "failed" / "python-falcon.json").is_file()
