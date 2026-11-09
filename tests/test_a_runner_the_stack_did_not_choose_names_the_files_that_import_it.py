"""A test runner installed over the stack's names the files importing it, and the defect hands them to the fixer.

Measured on one run: "package.json installs 'vitest', but this run's stack chose node:test"; three fixes in a row
removed vitest from the manifest alone, broke the 19 tests whose files still imported it, and were reverted.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.analysis import integration_checks
from app.graph import workflow


def _project(tmp_path):
    (tmp_path / "notes-api" / "test").mkdir(parents=True)
    manifest = tmp_path / "notes-api" / "package.json"
    manifest.write_text(json.dumps({"devDependencies": {"vitest": "^2.0.0"}}))
    test = tmp_path / "notes-api" / "test" / "persistence.test.ts"
    test.write_text("import { describe, it, expect } from 'vitest';\n")
    other = tmp_path / "notes-api" / "test" / "health.test.ts"
    other.write_text("import { test } from 'node:test';\n")
    return [manifest, test, other]


def test_the_finding_names_the_importers(tmp_path):
    files = _project(tmp_path)
    [found] = integration_checks._a_test_runner_the_stack_did_not_choose(
        files, tmp_path, SimpleNamespace(testing_framework="node:test for unit tests"))
    assert "notes-api/test/persistence.test.ts" in found and "health.test.ts" not in found
    assert "in the same change, before the package is removed" in found


def test_the_left_out_defect_carries_the_files_it_names(tmp_path):
    _project(tmp_path)
    problem = ("notes-api/package.json installs 'vitest', but this run's stack chose 'node:test'. These files import "
               "'vitest' and must be rewritten for the chosen approach in the same change, before the package is "
               "removed: notes-api/test/persistence.test.ts.")
    [defect] = workflow._proven_problems_the_round_left_out([problem], [], SimpleNamespace(delegated_tasks=[]), str(tmp_path))
    assert defect.affected_files == ["notes-api/package.json", "notes-api/test/persistence.test.ts"]
