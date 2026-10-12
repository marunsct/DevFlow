"""Which pack a run is built from is the stack decision's to say; nothing guesses it.

Measured on two runs whose stack decision said no pack fits (a Python service
with a React page): a lookup of the contract guessed a pack from the words of
the stack document and wrote its guess down. One run was given a JavaScript
service's contract because its stack document explained why a JavaScript
option was rejected, the other a Python service's - and every run of the suite
then wrote that pack's runner configuration into the project, and told the
agents it was the harness's to keep.

A scaffold that could not be proven still records the pack its files came
from, so the pack's checks of the tests apply; but nothing in it is the
harness's to keep or to put back.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.acceptance import suite
from app.stacks import contract, pack_named

THE_RUNS_STACK_DOCUMENT = """# Technology Stack
- **Language:** Python
- **Framework:** FastAPI
- **Frontend framework:** React on Vite

No single available scaffolded stack provides both a React frontend and a FastAPI backend together - the closest listed option (Browser app with its own HTTP service in JavaScript on Express) uses plain HTML/CSS/JavaScript for the page.
"""

THE_RUNS_DECISION = {
    "id": "DR-1", "point": "stack", "options": [],
    "decision": "Python / FastAPI - no stack pack fits; the agents set the project up",
    "rationale": "Support tier: custom stack - no pack fits, so there is no scaffold.",
}

AGENTS_CONFIG = "// the agents' own runner configuration\nexport default {};\n"


def _the_runs_workspace(root: Path) -> Path:
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "technology_stack.md").write_text(THE_RUNS_STACK_DOCUMENT)
    (root / ".harness").mkdir()
    (root / ".harness" / "decisions.json").write_text(json.dumps([THE_RUNS_DECISION]))
    (root / ".project-directory").write_text("dashboard\n")
    project = root / "dashboard"
    project.mkdir()
    (project / "package.json").write_text('{"name": "dashboard"}')
    (project / "playwright.config.js").write_text(AGENTS_CONFIG)
    return project


class TestAStackNoPackFits:
    def test_has_no_contract(self, tmp_path):
        _the_runs_workspace(tmp_path)

        assert contract.the_pack(tmp_path) is None

    def test_a_lookup_writes_nothing(self, tmp_path):
        _the_runs_workspace(tmp_path)

        contract.the_pack(tmp_path)

        assert not (tmp_path / contract.CONTRACT_FILE).exists()

    def test_its_runner_configuration_stays_the_agents(self, tmp_path):
        project = _the_runs_workspace(tmp_path)

        assert contract.enforce(tmp_path) == []
        assert (project / "playwright.config.js").read_text() == AGENTS_CONFIG
        assert contract.owned_by_the_harness(tmp_path, "dashboard/playwright.config.js") == ""

    def test_a_file_in_it_finds_no_pack_above(self, tmp_path):
        project = _the_runs_workspace(tmp_path)

        assert contract.the_pack_above(project / "src" / "main.tsx") is None


def _unproven(root: Path) -> Path:
    project = root / "notes"
    project.mkdir(parents=True)
    (project / "playwright.config.js").write_text(AGENTS_CONFIG)
    contract.write(root, pack_named("browser-javascript"), "notes", "Notes", scaffolded=False)
    return project


class TestAScaffoldThatCouldNotBeProven:
    def test_keeps_its_pack_s_checks(self, tmp_path):
        project = _unproven(tmp_path)
        spec = project / "acceptance" / "a.spec.js"
        spec.parent.mkdir()
        spec.write_text(
            "import { test, expect } from '@playwright/test';\n"
            "test('[AC-1] reads', async ({ page }) => {\n"
            "  await page.evaluate(() => localStorage.clear());\n"
            "  await page.goto('/');\n"
            "});\n"
        )
        suite.save_criteria(tmp_path, [])

        assert contract.the_pack(tmp_path)[0].name == "browser-javascript"
        assert suite.tests_that_access_storage_before_opening_the_page(tmp_path)

    def test_keeps_no_file_and_puts_none_back(self, tmp_path):
        project = _unproven(tmp_path)

        assert contract.kept_paths(tmp_path) == frozenset()
        assert contract.enforce(tmp_path) == []
        assert (project / "playwright.config.js").read_text() == AGENTS_CONFIG


def test_a_proven_scaffold_still_keeps_its_configuration(tmp_path):
    project = tmp_path / "notes"
    project.mkdir()
    (project / "playwright.config.js").write_text(AGENTS_CONFIG)
    contract.write(tmp_path, pack_named("browser-javascript"), "notes", "Notes")

    assert "notes/playwright.config.js" in contract.kept_paths(tmp_path)
    assert contract.enforce(tmp_path)
    assert (project / "playwright.config.js").read_text() != AGENTS_CONFIG
