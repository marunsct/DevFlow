"""A setup's declared test commands run every test of their kind, not the one smoke test the proof runs (SF bug).

Measured on the first custom-stack baseline (Python, Falcon): the setup declared
`pytest tests/test_store.py::test_store_smoke` and `pytest acceptance_tests/test_api.py::test_api_smoke`. The proof
passed - only the smoke tests existed - the contract kept the commands for every later round, and the smoke tests
were removed: no unit or acceptance test the sprints wrote would ever have run.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.stacks.custom_setup import problems_with

DECLARED = {
    "kind": "http_api",
    "install": [[".venv/bin/pip", "install", "-r", "requirements.txt"]],
    "unit_test": [".venv/bin/pytest", "tests", "--junitxml=reports/unit.xml"],
    "unit_report": "reports/unit.xml",
    "unit_dir": "tests",
    "unit_pattern": "test_*.py",
    "acceptance_test": [".venv/bin/pytest", "acceptance_tests", "--junitxml=reports/acceptance.xml"],
    "acceptance_report": "reports/acceptance.xml",
    "acceptance_dir": "acceptance_tests",
    "acceptance_pattern": "test_*.py",
    "kept_files": [],
    "smoke_files": ["tests/test_store.py", "acceptance_tests/test_api.py"],
}


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    return tmp_path / "notes-api"


def test_commands_that_run_their_directories_are_fine(project):
    assert problems_with(json.dumps(DECLARED), project) == ""


@pytest.mark.parametrize("key, argv", [
    ("unit_test", [".venv/bin/pytest", "tests/test_store.py::test_store_smoke", "--junitxml=reports/unit.xml"]),
    ("unit_test", [".venv/bin/pytest", "tests/test_store.py", "--junitxml=reports/unit.xml"]),
    ("acceptance_test", [".venv/bin/pytest", "acceptance_tests/test_api.py::test_api_smoke"]),
    ("acceptance_test", [".venv/bin/pytest", "./acceptance_tests/test_api.py"]),
])
def test_a_command_that_runs_only_the_smoke_test_is_refused(project, key, argv):
    problem = problems_with(json.dumps({**DECLARED, key: argv}), project)
    assert f"`{key}`" in problem and "every test" in problem


def test_the_setup_is_told_before_it_declares():
    import re
    from types import SimpleNamespace

    from app.stacks.custom_setup import build_setup_request

    stack = SimpleNamespace(language="Python", framework="Falcon", frontend_framework="", testing_framework="pytest",
                            database="SQLite")
    text = build_setup_request("notes-api", stack, "http_api")["messages"][0]["content"]
    rule = text[text.index("Each\n   declared command"):text.index("4. Bring")]
    assert "every test of its kind" in rule and "never the smoke test" in rule
    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", rule, re.I)
