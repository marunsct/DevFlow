"""A setup's declared smoke tests stay until the harness has proven the setup (SF bug, LF.657's wording).

Measured on a custom-stack baseline: told "the smoke tests are removed once the setup is proven", the setup stage
deleted its own smoke tests before ending - on both attempts - the proof found "these declared files do not exist",
and the setup was left to the agents.
"""
from __future__ import annotations

import json
import re

import pytest

from app.stacks.custom_setup import build_setup_request
from app.tools.repository import PROJECT_MARKER, RepositoryToolError, delete_approved_artifact


def _workspace(tmp_path):
    project = tmp_path / "notes-api"
    (project / "unit_tests").mkdir(parents=True)
    (project / "unit_tests" / "test_smoke.py").write_text("def test_smoke():\n    assert True\n")
    (project / "unit_tests" / "test_scratch.py").write_text("")
    (project / "stack-setup.json").write_text(json.dumps(
        {"smoke_files": ["unit_tests/test_smoke.py", "acceptance_tests/test_smoke.py"]}))
    (tmp_path / PROJECT_MARKER).write_text("notes-api\n")
    return tmp_path


def test_a_declared_smoke_test_is_not_deleted(tmp_path):
    root = _workspace(tmp_path)
    with pytest.raises(RepositoryToolError, match="removes it itself"):
        delete_approved_artifact(root, "notes-api/unit_tests/test_smoke.py")
    assert (root / "notes-api" / "unit_tests" / "test_smoke.py").exists()


def test_the_setup_is_told_to_leave_them():
    from types import SimpleNamespace

    stack = SimpleNamespace(language="Python", framework="Falcon", frontend_framework="", testing_framework="pytest",
                            database="SQLite")
    text = build_setup_request("notes-api", stack, "http_api")["messages"][0]["content"]
    rule = text[text.index("Each\n   declared command"):text.index("4. Bring")]
    assert "leave them in place" in rule and "the harness removes" in rule
    assert "are removed once" not in rule
    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", rule, re.I)
