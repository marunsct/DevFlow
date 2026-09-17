"""Dependencies the brief rules out and the product declares anyway.

`what_the_brief_asked_for_that_is_missing` checks one direction - the brief
asks for a page, the product has none. Nothing checked the other, and it is the
direction run 0c5aabdb failed in: a brief reading "No external dependencies
beyond basic HTML/CSS/JS" against a product built on Express with a 32KB
lockfile.

Run 551640d3 is the same thing more quietly. It installed `jsdom` to get a DOM
for its tests - a reasonable instinct, and exactly what the brief forbids -
leaving a full `node_modules` and a 29KB lockfile. Nothing reported it: the
cross-file checks look at how files relate, and the missing-things check has
nothing to say about a thing that is present.

Across the stored workspaces 11 of 55 declare dependencies - jsdom, vitest,
tap, jest, babel-jest, crypto-js, express, node-fetch among them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.brief_constraints import what_the_brief_forbids_that_is_there

FORBIDS = """# Brief

## Technical Constraints
- Single-page application
- No external dependencies beyond basic HTML/CSS/JS
"""

ALLOWS = """# Brief

## Technical Constraints
- Backend: Python/FastAPI or Node.js/Express
- Frontend: React or Vue.js
"""


@pytest.fixture
def project(tmp_path: Path):
    def build(manifest: dict | None) -> Path:
        directory = tmp_path / "todo"
        directory.mkdir(exist_ok=True)
        if manifest is not None:
            (directory / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
        return tmp_path

    return build


def test_a_declared_dependency_is_reported(project):
    root = project({"name": "t", "devDependencies": {"jsdom": "^21"}})

    found = what_the_brief_forbids_that_is_there(FORBIDS, root)

    assert len(found) == 1
    assert "`jsdom`" in found[0]


def test_it_says_the_brief_rules_it_out_in_its_own_words(project):
    root = project({"name": "t", "dependencies": {"express": "^4"}})

    assert "rules that out in its own words" in what_the_brief_forbids_that_is_there(FORBIDS, root)[0]


def test_it_does_not_argue_about_why_it_was_needed(project):
    """jsdom for a DOM in tests is a reasonable instinct and still forbidden."""
    root = project({"name": "t", "devDependencies": {"jsdom": "^21"}})

    assert "Whatever it was needed for" in what_the_brief_forbids_that_is_there(FORBIDS, root)[0]


def test_a_manifest_with_no_dependencies_is_silent(project):
    root = project({"name": "t", "scripts": {"test": "node --test"}})

    assert what_the_brief_forbids_that_is_there(FORBIDS, root) == []


def test_a_brief_that_allows_them_is_silent(project):
    """`brief_medium.md` names Express and React in its own constraints."""
    root = project({"name": "t", "dependencies": {"express": "^4"}})

    assert what_the_brief_forbids_that_is_there(ALLOWS, root) == []


def test_a_project_with_no_manifest_is_silent(project):
    assert what_the_brief_forbids_that_is_there(FORBIDS, project(None)) == []


def test_an_empty_brief_is_silent(project):
    root = project({"name": "t", "dependencies": {"express": "^4"}})

    assert what_the_brief_forbids_that_is_there("", root) == []


def test_installed_packages_are_not_read_as_the_projects_own(project):
    """`node_modules/*/package.json` declares the dependencies of a dependency."""
    root = project({"name": "t"})
    buried = root / "todo" / "node_modules" / "left-pad"
    buried.mkdir(parents=True)
    (buried / "package.json").write_text(
        json.dumps({"name": "left-pad", "dependencies": {"nope": "1"}}), encoding="utf-8"
    )

    assert what_the_brief_forbids_that_is_there(FORBIDS, root) == []


def test_the_milestone_reviewer_is_given_it(project):
    from app.agents.milestone_reviewer import build_milestone_review_request

    root = project({"name": "t", "devDependencies": {"jsdom": "^21"}})

    body = build_milestone_review_request(
        "goal", ["todo/app.js"], "tests pass", "none", str(root), None, FORBIDS
    )["messages"][0]["content"]

    assert "`jsdom`" in body
    assert "Checked deterministically against what was built" in body


def test_a_package_imported_but_never_declared_is_still_a_dependency(tmp_path):
    """Run 9bd3a091 imported `jsdom` into three test files under an empty
    `devDependencies`, with a full `node_modules` and a lockfile of thirty-nine
    packages. Reading declarations alone, the check went dark on it.
    """
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(json.dumps({"devDependencies": {}}))
    (project / "app.test.mjs").write_text("import { JSDOM } from 'jsdom';\n")
    found = what_the_brief_forbids_that_is_there(FORBIDS, tmp_path)
    assert found and "jsdom" in found[0] and "without declaring it" in found[0]


def test_a_declared_package_and_an_undeclared_one_are_both_named(tmp_path):
    """Run cbd22a34 declared `jsdom` and `vitest` and imported `linkedom` too."""
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps({"devDependencies": {"jsdom": "^1", "vitest": "^1"}})
    )
    (project / "app.test.mjs").write_text("import { parseHTML } from 'linkedom';\n")
    found = what_the_brief_forbids_that_is_there(FORBIDS, tmp_path)
    assert found and "jsdom" in found[0] and "linkedom" in found[0]


def test_node_builtins_are_not_dependencies(tmp_path):
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(json.dumps({"devDependencies": {}}))
    (project / "app.test.mjs").write_text(
        "import { test } from 'node:test';\n"
        "import assert from 'assert';\n"
        "import fs from 'fs';\n"
        "const path = require('path');\n"
    )
    assert what_the_brief_forbids_that_is_there(FORBIDS, tmp_path) == []


def test_relative_and_url_imports_are_not_packages(tmp_path):
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(json.dumps({"devDependencies": {}}))
    (project / "app.js").write_text(
        "import { addTask } from './app.js';\n"
        "import x from '../lib/x.mjs';\n"
        "import y from 'https://cdn.example.com/y.js';\n"
        "import z from '/src/z.js';\n"
    )
    assert what_the_brief_forbids_that_is_there(FORBIDS, tmp_path) == []
