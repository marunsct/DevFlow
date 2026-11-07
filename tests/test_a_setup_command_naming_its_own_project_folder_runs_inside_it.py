"""A declared command that names the project folder it already runs in is read as running inside it (SF bug).

Measured on a custom-stack baseline: the setup declared `./notes-api/.venv/bin/pip install -e ./notes-api`; the proof
runs declared commands inside `notes-api/`, the path became `notes-api/notes-api/...`, the install failed, and the
setup was left to the agents. The same doubled-folder class as LF.655. A folder of that name that really exists inside
the project (a package named like it) is left as written.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.stacks.custom_setup import read_declaration

DECLARED = {
    "kind": "http_api",
    "install": [["./notes-api/.venv/bin/pip", "install", "-e", "./notes-api"]],
    "unit_test": ["notes-api/.venv/bin/pytest", "tests", "--junitxml=reports/unit.xml"],
    "unit_report": "reports/unit.xml", "unit_dir": "tests", "unit_pattern": "test_*.py",
    "acceptance_test": [".venv/bin/pytest", "acceptance", "--junitxml=reports/acceptance.xml"],
    "acceptance_report": "reports/acceptance.xml", "acceptance_dir": "acceptance", "acceptance_pattern": "test_*.py",
    "kept_files": [], "smoke_files": ["tests/test_smoke.py", "acceptance/test_smoke.py"],
}


def _project(tmp_path: Path, name: str = "notes-api") -> Path:
    root = tmp_path / name
    for path in (".venv/bin/pip", ".venv/bin/pytest", "tests/test_smoke.py", "acceptance/test_smoke.py"):
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text("")
    return root


def test_the_doubled_project_folder_is_dropped(tmp_path):
    root = _project(tmp_path)
    (root / "stack-setup.json").write_text(json.dumps(DECLARED))
    declared, problem = read_declaration(root)
    assert problem == ""
    assert declared.install == ((".venv/bin/pip", "install", "-e", "."),)
    assert declared.unit_test[0] == ".venv/bin/pytest"


def test_a_real_folder_of_that_name_is_kept(tmp_path):
    root = _project(tmp_path, "bookmarks")
    (root / "bookmarks").mkdir()
    (root / "bookmarks" / "main.py").write_text("")
    declared_text = {**DECLARED, "install": [[".venv/bin/pip", "install", "-e", "."]],
                     "unit_test": [".venv/bin/pytest", "tests", "bookmarks/main.py"]}
    (root / "stack-setup.json").write_text(json.dumps(declared_text))
    declared, problem = read_declaration(root)
    assert problem == ""
    assert "bookmarks/main.py" in declared.unit_test
