"""Application modules that nothing but a test ever loads.

`_orphaned_scripts` asks whether anything references a module at all, and a
test importing it counts - right for "is this dead code", wrong for "does the
product run". A suite can exercise every function in a module the page never
loads, and does.

Run 7e960f06's milestone review found it by reading, which is luck rather than
design: `index.html` carried no `<script>` tag of any kind, `app.js` was
imported only by `app.test.mjs`, and the deterministic checks reported one
untidy problem and nothing else. The suite was 5 of 5 green over a product that
never loaded.

Across the 55 stored workspaces this holds for 8 of them - including run
2bcdc19, which shipped both `app.js` and `app.mjs`, loaded `app.js` from the
page, and pointed both test files at `app.mjs`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _reached_only_by_its_tests as only_tests_reach,
    _severity_of,
)

APP = "export function addTask(t) { return t; }\n"
SUITE = (
    "import { test } from 'node:test';\n"
    "import { addTask } from './app.js';\n"
    "test('x', () => { addTask(1); });\n"
)
PAGE_WITHOUT = "<!DOCTYPE html><button id='a'>A</button><button id='b'>B</button>"
PAGE_WITH = PAGE_WITHOUT + "<script type='module' src='app.js'></script>"


@pytest.fixture
def build(tmp_path: Path):
    def make(files: dict[str, str]) -> tuple[list[Path], Path]:
        project = tmp_path / "app"
        project.mkdir(exist_ok=True)
        for name, content in files.items():
            (project / name).write_text(content, encoding="utf-8")
        return [p for p in project.rglob("*") if p.is_file()], tmp_path

    return make


def test_a_module_the_page_never_loads_is_reported(build):
    files, root = build({"index.html": PAGE_WITHOUT, "app.js": APP, "app.test.mjs": SUITE})

    problems = only_tests_reach(files, root)

    assert len(problems) == 1
    assert "app.js" in problems[0]
    assert "the page never runs it" in problems[0]


def test_it_blocks(build):
    """A green suite over a product that never loads is the worst kind of green."""
    files, root = build({"index.html": PAGE_WITHOUT, "app.js": APP, "app.test.mjs": SUITE})

    assert _severity_of(only_tests_reach(files, root)[0]) == "BREAKS"


def test_a_module_the_page_loads_is_left_alone(build):
    files, root = build({"index.html": PAGE_WITH, "app.js": APP, "app.test.mjs": SUITE})

    assert only_tests_reach(files, root) == []


def test_a_module_another_application_file_imports_is_left_alone(build):
    files, root = build({
        "index.html": PAGE_WITH,
        "app.js": "import { helper } from './helper.js';\n" + APP,
        "helper.js": "export function helper() {}\n",
        "app.test.mjs": "import { helper } from './helper.js';\n",
    })

    assert only_tests_reach(files, root) == []


def test_the_parallel_implementation_case(build):
    """Run 2bcdc19: the page loads `app.js`, both suites import `app.mjs`."""
    files, root = build({
        "index.html": PAGE_WITHOUT + "<script src='app.js'></script>",
        "app.js": APP,
        "app.mjs": APP,
        "app.test.mjs": "import { addTask } from './app.mjs';\n",
    })

    problems = only_tests_reach(files, root)

    assert len(problems) == 1
    assert "app.mjs" in problems[0]


def test_a_node_side_module_is_not_page_code(build):
    """Run bb1ee9b's `server.js`. "Load it from the page" is wrong for a server."""
    files, root = build({
        "index.html": PAGE_WITH,
        "app.js": APP,
        "server.js": "import { createServer } from 'http';\nexport function start() {}\n",
        "server.test.mjs": "import { start } from './server.js';\n",
    })

    assert only_tests_reach(files, root) == []


def test_a_project_with_no_page_is_not_judged(build):
    """A library or a CLI is not expected to be loaded by a page."""
    files, root = build({"app.js": APP, "app.test.mjs": SUITE})

    assert only_tests_reach(files, root) == []


def test_dead_code_no_test_touches_is_a_different_finding(build):
    """That one is `_unreferenced_scripts`, and it says something else."""
    files, root = build({"index.html": PAGE_WITHOUT, "app.js": APP})

    assert only_tests_reach(files, root) == []
