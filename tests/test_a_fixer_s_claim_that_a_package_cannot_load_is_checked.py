"""A fixer that changes nothing because "a package cannot be imported" is answered with what the harness finds.

Measured on one run: two fixers in a row reported "Cannot correctly import sqlite3 module under current ES module
configuration" and "Unable to resolve SQLite import in ESM context", changed nothing, and one ran to the 60-call cap.
`await import('sqlite3')` loaded fine in the project. The next fixer was shown their claim, not the fact.
"""
from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

from app.graph import workflow


def _project(tmp_path):
    (tmp_path / ".project-directory").write_text("notes-api\n")
    (tmp_path / "notes-api").mkdir()
    (tmp_path / "notes-api" / "package.json").write_text(json.dumps({"dependencies": {"hono": "4", "sqlite3": "5"}}))
    return tmp_path


def test_a_package_the_fixer_says_cannot_load_is_loaded_and_the_answer_said(tmp_path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.setattr("app.stacks.contract.the_pack",
                        lambda r: (SimpleNamespace(code_runs_in="node"), {"project": "notes-api"}))
    ran = []
    monkeypatch.setattr("app.stacks.scaffold.sandbox_runner",
                        lambda r: lambda argv, category, project: ran.append(argv) or {"returncode": 0, "stdout": "LOADS default"})

    note = workflow._what_a_claimed_unloadable_package_does(
        str(root), ["Cannot correctly import sqlite3 module under current ES module configuration"])

    assert "`sqlite3` loads in this project" in note and "default" in note
    assert any("sqlite3" in " ".join(map(str, argv)) for argv in ran)


def test_a_claim_naming_no_declared_package_is_left_alone(tmp_path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.setattr("app.stacks.contract.the_pack",
                        lambda r: (SimpleNamespace(code_runs_in="node"), {"project": "notes-api"}))
    assert workflow._what_a_claimed_unloadable_package_does(str(root), ["The route returns 404"]) == ""


def test_the_blocked_fix_carries_the_answer_to_the_next_fixer():
    source = inspect.getsource(workflow)
    at = source.index('detail="the fix stage changed nothing and reported: "')
    assert "_what_a_claimed_unloadable_package_does(" in source[at - 1500:at + 1500]
