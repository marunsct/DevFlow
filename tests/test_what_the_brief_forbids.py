"""Dependencies the brief rules out and the product declares anyway.

`what_the_brief_asked_for_that_is_missing` checks one direction - the brief
asks for a page, the product has none. Nothing checked the other, and it is the
direction one run failed in: a brief reading "No external dependencies
beyond basic HTML/CSS/JS" against a product built on Express with a 32KB
lockfile.

One run is the same thing more quietly. It installed `jsdom` to get a DOM
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


def test_a_shipped_dependency_is_reported(project):
    root = project({"name": "t", "dependencies": {"express": "^4"}})
    (root / "todo" / "index.js").write_text("const express = require('express');\n")

    found = what_the_brief_forbids_that_is_there(FORBIDS, root)

    assert len(found) == 1
    assert "`express`" in found[0]


def test_a_test_only_devdependency_is_not_a_violation(project):
    """A test runner in `devDependencies` ships to nobody, so a brief that
    forbids dependencies has nothing to say about it. Measured on one run,
    which spent all three remediation attempts on `@playwright/test` here and
    failed without a product defect in it.
    """
    root = project({"name": "t", "devDependencies": {"@playwright/test": "^1.49"}})
    (root / "todo" / "app.js").write_text("export function add(a, b) { return a + b; }\n")
    (root / "todo" / "app.test.mjs").write_text(
        "import { test } from '@playwright/test';\n"
    )

    found = what_the_brief_forbids_that_is_there(FORBIDS, root)

    assert len(found) == 1
    # The tail sentence is boilerplate on every finding; the head is what
    # distinguishes a violation from a note that the check ran and found none.
    assert found[0].startswith("todo/package.json declares no product dependencies")
    assert "not shipped" in found[0]
    # It used to end with the violation's own closing sentences.
    assert "cannot accept the milestone" not in found[0]
    assert "rules that out" not in found[0]


def test_a_devdependency_the_product_itself_imports_is_still_reported(project):
    """`devDependencies` is not a loophole. A package the product imports at
    runtime is a product dependency wherever it is declared, and `npm ci
    --omit=dev` would break it into the bargain.
    """
    root = project({"name": "t", "devDependencies": {"jsdom": "^21"}})
    (root / "todo" / "app.js").write_text("import { JSDOM } from 'jsdom';\n")

    found = what_the_brief_forbids_that_is_there(FORBIDS, root)

    assert len(found) == 1
    assert "`jsdom`" in found[0]
    assert "rules that out in its own words" in found[0]


def test_it_says_the_brief_rules_it_out_in_its_own_words(project):
    root = project({"name": "t", "dependencies": {"express": "^4"}})
    (root / "todo" / "index.js").write_text("const express = require('express');\n")

    assert "rules that out in its own words" in what_the_brief_forbids_that_is_there(FORBIDS, root)[0]


def test_it_does_not_argue_about_why_it_was_needed(project):
    """A shipped dependency is forbidden whatever it was for."""
    root = project({"name": "t", "dependencies": {"express": "^4"}})
    (root / "todo" / "index.js").write_text("const express = require('express');\n")

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

    root = project({"name": "t", "dependencies": {"express": "^4"}})
    (root / "todo" / "index.js").write_text("const express = require('express');\n")

    body = build_milestone_review_request(
        "goal", ["todo/app.js"], "tests pass", "none", str(root), None, FORBIDS
    )["messages"][0]["content"]

    assert "`express`" in body
    assert "Checked deterministically against what was built" in body


def test_a_package_imported_but_never_declared_is_still_a_dependency(tmp_path):
    """One run imported `jsdom` into three test files under an empty
    `devDependencies`, with a full `node_modules` and a lockfile of thirty-nine
    packages. Reading declarations alone, the check went dark on it.
    """
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(json.dumps({"devDependencies": {}}))
    (project / "app.test.mjs").write_text("import { JSDOM } from 'jsdom';\n")
    found = what_the_brief_forbids_that_is_there(FORBIDS, tmp_path)
    assert found and "jsdom" in found[0] and "without declaring it" in found[0]


def test_a_package_the_product_imports_but_never_declares_is_reported(tmp_path):
    """The undeclared-import check still fires for product code: a package the
    shipped code needs is a dependency whether it is declared or not.
    """
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(json.dumps({"dependencies": {}}))
    (project / "index.js").write_text("const express = require('express');\n")
    found = what_the_brief_forbids_that_is_there(FORBIDS, tmp_path)
    assert found and "express" in found[0] and "without declaring it" in found[0]


def test_a_test_only_package_imported_but_never_declared_is_reported(tmp_path):
    """Undeclared is still undeclared, even for test tooling: `npm ci` will not
    install it, so the suite fails on any other machine for a second reason.
    """
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(json.dumps({"devDependencies": {}}))
    (project / "app.js").write_text("export const x = 1;\n")
    (project / "app.test.mjs").write_text("import { test } from '@playwright/test';\n")
    found = what_the_brief_forbids_that_is_there(FORBIDS, tmp_path)
    assert found and "@playwright/test" in found[0] and "without declaring it" in found[0]


def test_a_declared_package_and_an_undeclared_one_are_both_named(tmp_path):
    """Run a000000c declared `jsdom` and `vitest` and imported `linkedom` too.

    The two declared ones are test-only, so they are no longer a violation; the
    undeclared one still is, because `npm ci` will not install it and the suite
    fails on any other machine.
    """
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps({"devDependencies": {"jsdom": "^1", "vitest": "^1"}})
    )
    (project / "app.test.mjs").write_text("import { parseHTML } from 'linkedom';\n")
    found = what_the_brief_forbids_that_is_there(FORBIDS, tmp_path)
    assert found and "linkedom" in found[0] and "without declaring it" in found[0]


def test_a_shipped_package_and_a_test_only_one_are_named_separately(tmp_path):
    """The report distinguishes what ships from what tests with. A reviewer
    reading it needs to know which is a violation and which is not.
    """
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps({"dependencies": {"express": "^4"}, "devDependencies": {"vitest": "^1"}})
    )
    (project / "index.js").write_text("const express = require('express');\n")
    (project / "index.test.mjs").write_text("import { test } from 'vitest';\n")
    found = what_the_brief_forbids_that_is_there(FORBIDS, tmp_path)
    assert len(found) == 1
    assert "declares `express`" in found[0]
    assert "rules that out in its own words" in found[0]
    # `vitest` is test-only and declared as such, so it must not be named as a
    # violation - only the shipped `express` is.
    assert "vitest" not in found[0]


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


def test_a_test_framework_config_file_is_test_tooling_not_product_code(tmp_path):
    """The one import that cost one run its milestone.

    `@playwright/test` sat in `devDependencies` with no `dependencies` at all,
    imported by a test file and by `playwright.config.ts`. `file_kinds` classifies
    that config as `config`, not `test` - correctly, it is not a test - so
    `_imported_only_by_tests` treated the runner's own configuration as product
    code and the check reported a dependency that ships to nobody. The milestone
    reviewer filed it BLOCKING and the run ended after three remediation rounds.
    """
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps({"devDependencies": {"@playwright/test": "latest"}})
    )
    (project / "app.js").write_text("export const addTask = () => {};\n")
    (project / "tests").mkdir()
    (project / "tests" / "playwright.test.ts").write_text(
        "import { test } from '@playwright/test';\n"
    )
    (project / "playwright.config.ts").write_text(
        "import { defineConfig } from '@playwright/test';\n"
        "export default defineConfig({});\n"
    )
    found = what_the_brief_forbids_that_is_there(FORBIDS, tmp_path)
    # Nothing is reported as a violation. The check still says it ran, so a
    # reviewer knows the product carries no dependencies - that is the note,
    # not a finding against the brief.
    assert len(found) == 1
    assert "declares no product dependencies" in found[0]
    assert "not shipped" in found[0]


def test_a_test_framework_imported_by_product_code_is_still_reported(tmp_path):
    """The exemption is for the suite's own files, not for product code that
    happens to sit beside a config. `app.js` importing the runner is a shipped
    dependency filed in the wrong place."""
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps({"devDependencies": {"@playwright/test": "latest"}})
    )
    (project / "app.js").write_text("import { chromium } from '@playwright/test';\n")
    (project / "playwright.config.ts").write_text(
        "import { defineConfig } from '@playwright/test';\n"
    )
    found = what_the_brief_forbids_that_is_there(FORBIDS, tmp_path)
    assert found and "@playwright/test" in found[0]


def test_a_package_a_declared_test_runner_brings_is_not_undeclared(tmp_path):
    """One run's suite imported `@jest/globals` under a declared `jest`. The
    lockfile installs it, only tests import it, and the reviewer was told the
    product broke the brief's rule on dependencies - through its last revision.
    """
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(json.dumps({"devDependencies": {"jest": "^29"}}))
    (project / "package-lock.json").write_text(json.dumps({"packages": {
        "": {}, "node_modules/jest": {}, "node_modules/@jest/globals": {},
        "node_modules/jest/node_modules/chalk": {},
    }}))
    (project / "app.js").write_text("export const x = 1;\n")
    (project / "app.test.js").write_text("const { test } = require('@jest/globals');\n")

    found = what_the_brief_forbids_that_is_there(FORBIDS, tmp_path)

    assert not any("without declaring it" in line for line in found)
    assert not any("@jest/globals" in line for line in found)


def test_the_same_package_imported_by_the_product_is_still_reported(tmp_path):
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(json.dumps({"devDependencies": {"jest": "^29"}}))
    (project / "package-lock.json").write_text(json.dumps({"packages": {
        "": {}, "node_modules/jest": {}, "node_modules/@jest/globals": {},
    }}))
    (project / "app.js").write_text("import { jest } from '@jest/globals';\n")

    found = what_the_brief_forbids_that_is_there(FORBIDS, tmp_path)

    assert found and "@jest/globals" in found[0] and "without declaring it" in found[0]
