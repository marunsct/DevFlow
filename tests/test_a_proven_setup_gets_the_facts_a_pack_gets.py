"""A stack no pack covers, once its setup is proven, gets the same layout facts every stage reads for a pack (SF.0a).

The facts were read through `pack_named`, which knows only the code packs: a proven setup's contract named
"proven-setup", so its runs got no layout facts at all - where the tests go, what the harness keeps, the route the
suite waits on - while every pack run did. `contract.the_pack` already builds the proven setup's pack.
"""
from __future__ import annotations

import json

from app.agents.shared_facts import facts_from_the_workspace
from app.stacks import contract

SETUP = {
    "kind": "http_api", "language": "python", "stack_line": "Python, Falcon, pytest",
    "stack": {"language": "Python", "framework": "Falcon", "testing_framework": "pytest"},
    "install": [[".venv/bin/pip", "install", "-r", "requirements.txt"]],
    "unit_test": [".venv/bin/pytest", "tests/unit"], "acceptance_test": [".venv/bin/pytest", "tests/acceptance"],
    "unit_report": "test-results/unit.xml", "acceptance_report": "test-results/acceptance.xml",
    "unit_dir": "tests/unit", "acceptance_dir": "tests/acceptance",
    "unit_pattern": "test_*.py", "acceptance_pattern": "test_*.py",
    "kept": {"tests/acceptance/conftest.py": "import pytest\n"}, "kept_scripts": {},
}


def _workspace(tmp_path):
    (tmp_path / "notes-api").mkdir()
    path = tmp_path / contract.CONTRACT_FILE
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"pack": "proven-setup", "project": "notes-api", "title": "Notes", "setup": SETUP}))
    return tmp_path


def test_a_proven_setup_s_run_reads_its_layout(tmp_path):
    facts = "\n".join(facts_from_the_workspace(_workspace(tmp_path), built=False))
    assert "`notes-api/tests/unit/`" in facts and "`notes-api/tests/acceptance/`" in facts
    assert "`notes-api/tests/acceptance/conftest.py`" in facts


def test_no_contract_still_gives_nothing(tmp_path):
    assert facts_from_the_workspace(tmp_path, built=False) == []
