"""Tests on disk and no `package.json` at all.

The manifest checks iterate over the `package.json` files they find, so a
project with none produces no finding - and that is the worse version of the
fault they exist for. `npm test` answers ENOENT rather than "missing script:
test", so not one suite can be reached by the command every stage is told to
use, and nothing has executed a single assertion.

Run 1cd4597b reached 699 events with two suites on disk and no manifest. Runs
37476645, f0630b10 and c150cb2e ended that way.

Reported at the cross-file checks rather than at the write of a test file:
across the stored transcripts the manifest is written first in 12 runs and
second in 11, so a write-time note would be premature about half the time.
By the end of a sprint it is decidable.
"""

from __future__ import annotations

import json

from app.analysis.integration_checks import summarise_integration

A_SUITE = "import { test } from 'node:test';\nimport assert from 'node:assert';\ntest('x', () => assert.ok(1));\n"


def _findings(root) -> list[str]:
    return [line[2:] for line in summarise_integration(root).splitlines() if line.startswith("- ")]


def test_tests_with_no_manifest_anywhere_are_reported(tmp_path):
    project = tmp_path / "todo-app"
    project.mkdir()
    (project / "app.js").write_text("export function addTask(t) { return t; }\n")
    (project / "app.test.mjs").write_text(A_SUITE)
    found = [f for f in _findings(tmp_path) if "no `package.json` at all" in f]
    assert found
    assert "app.test.mjs" in found[0]
    assert "ENOENT" in found[0]


def test_it_says_what_to_do(tmp_path):
    project = tmp_path / "todo-app"
    project.mkdir()
    (project / "app.test.mjs").write_text(A_SUITE)
    found = [f for f in _findings(tmp_path) if "no `package.json` at all" in f]
    assert "Add a `package.json` whose `test` script runs them" in found[0]


def test_a_project_with_a_manifest_is_left_to_the_other_checks(tmp_path):
    """Having one but with no `test` script is a different, existing finding."""
    project = tmp_path / "todo-app"
    project.mkdir()
    (project / "app.js").write_text("export function addTask(t) { return t; }\n")
    (project / "app.test.mjs").write_text(A_SUITE)
    (project / "package.json").write_text(json.dumps({"name": "p", "scripts": {"test": "node --test"}}))
    assert not [f for f in _findings(tmp_path) if "no `package.json` at all" in f]


def test_a_project_with_no_tests_is_not_asked_for_a_manifest(tmp_path):
    """Nothing to run means nothing to reach; this is about unreachable suites."""
    project = tmp_path / "todo-app"
    project.mkdir()
    (project / "app.js").write_text("export function addTask(t) { return t; }\n")
    (project / "index.html").write_text(
        "<!doctype html><body><script type='module' src='app.js'></script></body>\n"
    )
    assert not [f for f in _findings(tmp_path) if "no `package.json` at all" in f]
