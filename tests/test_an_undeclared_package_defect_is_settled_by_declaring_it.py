"""A defect saying the code imports packages no manifest declares is settled by the same reconciliation, once they are declared.

Measured on a gate run: the fixer declared both packages in the manifest the
install reads, and the defect was left open - "its own tests" were unit tests
that mentioned the package and failed for another reason.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.analysis import dependency_drift
from app.graph import workflow
from app.stacks import contract

DESCRIPTION = f"{dependency_drift.OPENING} `bcrypt` (imported in `items_api/auth.py`)."


def _project(tmp_path, declared):
    (tmp_path / contract.CONTRACT_FILE).parent.mkdir(parents=True)
    (tmp_path / contract.CONTRACT_FILE).write_text(json.dumps({"pack": "python-http-api", "project": "items-api",
        "install": [[".venv/bin/python", "-m", "pip", "install", "-r", "requirements.txt"]]}))
    package = tmp_path / "items-api" / "items_api"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "auth.py").write_text("import bcrypt\n")
    (tmp_path / "items-api" / "requirements.txt").write_text("fastapi\n" + ("bcrypt>=4\n" if declared else ""))
    return str(tmp_path)


def test_declared_is_settled_and_still_missing_is_not(tmp_path):
    defect = SimpleNamespace(description=DESCRIPTION)
    assert workflow._the_defect_s_tests_in(_project(tmp_path / "a", True), "after defect_fix_1_0", defect) is True
    assert workflow._the_defect_s_tests_in(_project(tmp_path / "b", False), "after defect_fix_1_0", defect) is False
