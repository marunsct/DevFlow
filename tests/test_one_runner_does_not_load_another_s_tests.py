"""Two test runners in one project must not load each other's files.

Measured on one run, which this ended. Its stack was two runners - one for the
logic, one that drives a browser - and both look for `*.test.js` and
`*.spec.js` unless told where to look. Nothing told either. The unit runner
loaded all ten browser specs, each failed before a test in it could run, the
suite took 220 seconds to say so, and because the test script chained the two
the browser suite never ran once. Three rounds reported it as three different
defects, every fix added a browser spec, and the run re-ran the suite 76 times
over three hours.

Across the 46 runs that reached a test round, 253 of 400 reported defects were
about the tests and their setup rather than the product.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.analysis import integration_checks as checks

PLAYWRIGHT_SPEC = "import { test, expect } from '@playwright/test';\ntest('x', async ({ page }) => { expect(1).toBe(1); });\n"
VITEST_TEST = "import { test, expect } from 'vitest';\ntest('x', () => { expect(1).toBe(1); });\n"
NODE_TEST = "import { test } from 'node:test';\nimport assert from 'node:assert';\ntest('x', () => { assert.ok(true); });\n"
JEST_TEST = "import { test, expect } from '@jest/globals';\ntest('x', () => { expect(1).toBe(1); });\n"


def _project(root: Path, scripts: dict, files: dict) -> Path:
    project = root / "app"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps({"name": "app", "type": "module", "scripts": scripts}), encoding="utf-8"
    )
    for name, content in files.items():
        target = project / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return project


TWO_RUNNERS = {
    "test:unit": "vitest run",
    "test:e2e": "npx playwright test",
    "test": "npm run test:unit && npm run test:e2e",
}

AS_THE_RUN_HAD_IT = {
    "vitest.config.ts": "import { defineConfig } from 'vitest/config';\nexport default defineConfig({ test: { environment: 'jsdom' } });\n",
    "playwright.config.ts": "import { defineConfig } from '@playwright/test';\nexport default defineConfig({ testDir: 'tests' });\n",
    "tests/e2e/page-load.spec.js": PLAYWRIGHT_SPEC,
    "tests/e2e/regression.test.js": PLAYWRIGHT_SPEC,
    "src/__tests__/storage.test.js": VITEST_TEST,
    "src/app.js": "export const a = 1;\n",
}


def _collisions(root: Path) -> list[str]:
    return checks._a_test_file_a_second_runner_collects(checks._source_files(root), root)


def test_the_unit_runner_loading_the_browser_specs_is_named(tmp_path: Path) -> None:
    _project(tmp_path, TWO_RUNNERS, AS_THE_RUN_HAD_IT)

    (problem,) = _collisions(tmp_path)

    assert "nothing tells `vitest` where to look" in problem
    assert "app/tests/e2e/page-load.spec.js" in problem and "app/tests/e2e/regression.test.js" in problem
    assert "not a defect in those files" in problem


def test_it_is_a_blocking_finding(tmp_path: Path) -> None:
    _project(tmp_path, TWO_RUNNERS, AS_THE_RUN_HAD_IT)

    breaking = checks.problems_that_break_the_product(tmp_path)

    assert any("nothing tells `vitest` where to look" in problem for problem in breaking)


@pytest.mark.parametrize("change", [
    # The unit runner's configuration says where it looks.
    {"vitest.config.ts": "export default { test: { exclude: ['tests/e2e/**'] } };\n"},
    {"vitest.config.ts": "export default { test: { include: ['src/**/*.test.js'] } };\n"},
])
def test_a_project_that_keeps_them_apart_in_configuration_is_left_alone(tmp_path: Path, change) -> None:
    _project(tmp_path, TWO_RUNNERS, {**AS_THE_RUN_HAD_IT, **change})

    assert _collisions(tmp_path) == []


@pytest.mark.parametrize("unit_script", ["vitest run src", "vitest run --dir src", "jest src", "node --test src/"])
def test_a_script_that_names_where_to_look_is_left_alone(tmp_path: Path, unit_script: str) -> None:
    files = {**AS_THE_RUN_HAD_IT, "src/__tests__/storage.test.js": NODE_TEST}
    _project(tmp_path, {**TWO_RUNNERS, "test:unit": unit_script}, files)

    assert _collisions(tmp_path) == []


def test_the_browser_runner_loading_the_unit_tests_is_named_too(tmp_path: Path) -> None:
    files = {
        "__tests__/logic.test.js": NODE_TEST,
        "e2e/page.spec.js": PLAYWRIGHT_SPEC,
        "app.js": "export const a = 1;\n",
    }
    _project(tmp_path, {"test": "node --test __tests__/", "e2e": "npx playwright test"}, files)

    (problem,) = _collisions(tmp_path)

    assert "nothing tells `playwright` where to look" in problem
    assert "app/__tests__/logic.test.js" in problem


def test_one_runner_has_nothing_to_collide_with(tmp_path: Path) -> None:
    _project(tmp_path, {"test": "vitest run"}, {"a.test.js": VITEST_TEST, "b.spec.js": PLAYWRIGHT_SPEC})

    assert _collisions(tmp_path) == []


# --- unit tests split between two runners -------------------------------------

STACK = SimpleNamespace(testing_framework="Jest + jsdom for the logic, Playwright for the page")


def _split(root: Path, stack=STACK) -> list[str]:
    return checks._unit_tests_split_between_runners(checks._source_files(root), root, stack)


def test_unit_tests_written_for_two_runners_are_named(tmp_path: Path) -> None:
    _project(tmp_path, {"test": "node --test"}, {
        "__tests__/logic.test.js": JEST_TEST,
        "__tests__/export.test.js": NODE_TEST,
        "__tests__/global.test.js": NODE_TEST,
        "e2e/page.spec.js": PLAYWRIGHT_SPEC,
    })

    (problem,) = _split(tmp_path)

    # The stack's choice is the one kept, though more files use the other.
    assert "Keep `@jest/globals`" in problem and "this run's stack chose" in problem
    assert "app/__tests__/export.test.js" in problem
    assert "Do not change the test command" in problem


def test_a_suite_written_consistently_for_another_runner_is_left_alone(tmp_path: Path) -> None:
    """A deviation that runs. One sound product shipped this way."""
    _project(tmp_path, {"test": "node --test"}, {
        "tests/unit/app.test.js": NODE_TEST,
        "tests/unit/feature.test.js": NODE_TEST,
        "e2e/page.spec.js": PLAYWRIGHT_SPEC,
    })

    assert _split(tmp_path) == []


def test_with_no_stack_to_decide_the_larger_half_is_kept(tmp_path: Path) -> None:
    _project(tmp_path, {"test": "node --test"}, {
        "a.test.js": NODE_TEST, "b.test.js": NODE_TEST, "c.test.js": VITEST_TEST,
    })

    (problem,) = _split(tmp_path, stack=None)

    assert "Keep `node:test`" in problem and "most of the suite" in problem


# --- a file in the product that does not parse --------------------------------


def _unparsed(root: Path) -> list[str]:
    return checks._a_source_file_that_does_not_parse(checks._source_files(root), root)


def test_a_file_that_arrived_broken_is_reported_whoever_wrote_it(tmp_path: Path) -> None:
    project = _project(tmp_path, {"test": "node --test"}, {"app.js": "export const a = 1;\n"})
    # Written past the tools, as a command or an earlier run would have left it.
    (project / "settings.toml").write_text("a = [1, 2\n", encoding="utf-8")
    (project / "broken.js").write_text("export function f() { if (x { }\n", encoding="utf-8")

    problems = _unparsed(tmp_path)

    assert any(problem.startswith("app/settings.toml does not parse") for problem in problems)
    assert any(problem.startswith("app/broken.js does not parse") for problem in problems)
    assert not any("Send the file again" in problem for problem in problems)
    breaking = checks.problems_that_break_the_product(tmp_path)
    assert any("settings.toml does not parse" in problem for problem in breaking)


def test_a_project_whose_files_all_parse_reports_nothing(tmp_path: Path) -> None:
    _project(tmp_path, TWO_RUNNERS, AS_THE_RUN_HAD_IT)

    assert _unparsed(tmp_path) == []


@pytest.mark.parametrize("unit_script", [
    "node --experimental-vm-modules node_modules/jest/bin/jest.js",
    "NODE_OPTIONS=--experimental-vm-modules npx jest",
    "node node_modules/vitest/vitest.mjs run",
])
def test_a_runner_started_through_its_entry_point_is_not_told_where_to_look(
    tmp_path: Path, unit_script: str
) -> None:
    """`node_modules/jest/bin/jest.js` is how `seed.py` says an ES-module
    project starts Jest, and the directory on the way to it was read as a path
    the script narrows collection to. One run failed its sprint on the
    collision that hid: Jest loading `e2e/index.spec.js`, three rounds in a row."""
    runner = "vitest" if "vitest" in unit_script else "jest"
    unit_file = VITEST_TEST if runner == "vitest" else JEST_TEST
    _project(tmp_path, {
        "test:unit": unit_script,
        "test": "npm run test:unit && npx playwright test",
    }, {
        "playwright.config.cjs": "module.exports = { testDir: './e2e' };\n",
        "e2e/index.spec.js": PLAYWRIGHT_SPEC,
        "__tests__/state.test.js": unit_file,
        "state.js": "export const a = 1;\n",
    })

    (problem,) = _collisions(tmp_path)

    assert f"nothing tells `{runner}` where to look" in problem
    assert "app/e2e/index.spec.js" in problem


@pytest.mark.parametrize("body, expected", [
    ("node --experimental-vm-modules node_modules/jest/bin/jest.js", ("jest", False)),
    ("node --experimental-vm-modules node_modules/jest/bin/jest.js __tests__", ("jest", True)),
    ("npx jest", ("jest", False)),
    ("jest --testPathPattern=unit", ("jest", True)),
    ("vitest run src", ("vitest", True)),
    ("echo jestful", ("", False)),
])
def test_what_a_script_says_about_where_its_runner_looks(body: str, expected) -> None:
    assert checks._the_runner_a_script_invokes(body) == expected
