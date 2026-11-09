"""A folder in the setup's declaration is told so, not that it "does not exist".

Measured on one run (a Hono service): the setup listed `node_modules` under `kept_files`. The check asked whether it was
a file, answered "these declared files do not exist: node_modules", the setup ran `npm install` to create it, and the
same message came back. Two attempts, then the setup was left to the agents.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.stacks import custom_setup


def _project(root: Path, kept: list[str]) -> Path:
    project = root / "notes-api"
    (project / "node_modules").mkdir(parents=True)
    (project / "tests").mkdir()
    (project / "acceptance").mkdir()
    (project / "package.json").write_text("{}")
    (project / "tests" / "unit.test.ts").write_text("x")
    (project / "acceptance" / "acc.test.ts").write_text("x")
    (project / "stack-setup.json").write_text(json.dumps({
        "kind": "http_api", "install": [["npm", "install"]], "unit_test": ["npx", "vitest", "run"],
        "unit_report": "reports/unit.xml", "unit_dir": "tests", "unit_pattern": "*.test.ts",
        "acceptance_test": ["npx", "vitest", "run"], "acceptance_report": "reports/acc.xml",
        "acceptance_dir": "acceptance", "acceptance_pattern": "*.test.ts",
        "kept_files": kept, "smoke_files": ["tests/unit.test.ts", "acceptance/acc.test.ts"]}))
    return project


def test_a_folder_in_kept_files_is_named_as_a_folder(tmp_path):
    project = _project(tmp_path, ["package.json", "node_modules"])

    declaration, problem = custom_setup.read_declaration(project)

    assert declaration is None
    assert "are folders" in problem and "`node_modules`" in problem
    assert "does not exist" not in problem
    assert "leave the folder out" in problem


def test_a_missing_file_is_still_said_to_be_missing(tmp_path):
    project = _project(tmp_path, ["package.json", "tsconfig.json"])

    _, problem = custom_setup.read_declaration(project)

    assert "do not exist: `tsconfig.json`" in problem and "folders" not in problem


def test_a_declaration_of_files_that_exist_is_accepted(tmp_path):
    project = _project(tmp_path, ["package.json"])

    declaration, problem = custom_setup.read_declaration(project)

    assert declaration is not None and not problem
