"""A Playwright suite named for the other runner, which Playwright never sees.

`undiscoverable_test` asks whether `node --test` would collect a file and
answers only for Node: it returns early unless the file imports `node:test`.
A Playwright suite passes through it unexamined, and the two runners do not
agree on names.

Measured, both ways, on Node 22.22.2 and Playwright 1.63.0:

    name           node --test   npx playwright test
    a.spec.js          --                ok
    a.test.js          ok                ok
    a_test.js          ok                --
    a-test.js          ok                --
    test-a.js          ok                --

run-ac04a164 paid for the gap. Its testing specialist wrote
`task-manager/playwright_test.js`, a name every discovery check in the module
approved, and `npx playwright test` answered "No tests found" with exit code 1
at sequence 114 and again at 159. Read as a failing suite rather than an
absent one, the stage rewrote the file four more times and the run ended in
the loop.
"""

from __future__ import annotations

import pytest

from app.analysis.test_discovery import (
    a_playwright_test_the_runner_will_not_collect,
    undiscoverable_test,
)

PLAYWRIGHT_TEST = (
    "import { test, expect } from '@playwright/test';\n"
    "test('adds a task', async ({ page }) => {\n"
    "  await page.goto('/');\n"
    "  await expect(page.locator('#task-list')).toContainText('Test Task');\n"
    "});\n"
)


def test_the_file_from_run_ac04a164_is_caught() -> None:
    note = a_playwright_test_the_runner_will_not_collect(
        "task-manager/playwright_test.js", PLAYWRIGHT_TEST
    )

    assert note is not None
    assert "No tests found" in note, "the symptom the stage actually saw"
    assert "playwright.spec.js" in note, "a name that works must be offered"


def test_the_node_check_does_not_catch_it() -> None:
    """Why this check has to exist: the name is valid for the other runner, so
    the check that was already there says nothing about it."""
    assert undiscoverable_test("task-manager/playwright_test.js", PLAYWRIGHT_TEST) is None


@pytest.mark.parametrize(
    "path",
    [
        # Every name `npx playwright test --list` collected, run rather than
        # read off the glob. `.cjs` and `.cts` are in the list, which reading
        # the documented pattern alone got wrong, and matching is
        # case-insensitive.
        "app/a.spec.js",
        "app/a.spec.jsx",
        "app/a.spec.mjs",
        "app/a.spec.cjs",
        "app/a.spec.ts",
        "app/a.spec.tsx",
        "app/a.spec.mts",
        "app/a.spec.cts",
        "app/a.Spec.js",
        "app/a.test.cjs",
        "app/sub.dir.spec.js",
        "app/nested/deep.spec.js",
    ],
)
def test_a_name_playwright_collects_is_left_alone(path: str) -> None:
    assert a_playwright_test_the_runner_will_not_collect(path, PLAYWRIGHT_TEST) is None


@pytest.mark.parametrize(
    "path",
    [
        # Collected by `node --test`, invisible to Playwright.
        "app/a_test.js",
        "app/a-test.js",
        "app/test-a.js",
        # Playwright wants something before the dot; these two are bare.
        "app/spec.js",
        "app/test.js",
    ],
)
def test_a_name_playwright_misses_is_caught(path: str) -> None:
    assert a_playwright_test_the_runner_will_not_collect(path, PLAYWRIGHT_TEST) is not None


def test_the_rename_offered_avoids_the_shared_name() -> None:
    """`.test.` is collected by both runners, and a Playwright suite run under
    `node --test` fails rather than skips - the `{ page }` fixture is not
    there. So the rename has to say `.spec.`, and say why."""
    note = a_playwright_test_the_runner_will_not_collect("app/ui_test.js", PLAYWRIGHT_TEST)

    assert note is not None
    assert "ui.spec.js" in note
    assert "`.spec.` and not `.test.`" in note


def test_a_file_that_is_not_a_playwright_suite_is_left_alone() -> None:
    node_test = "import test from 'node:test';\ntest('x', () => {});\n"

    assert a_playwright_test_the_runner_will_not_collect("app/a_test.js", node_test) is None


def test_a_config_that_sets_its_own_pattern_silences_the_note(tmp_path) -> None:
    """A project is allowed its own discovery rule. This cannot evaluate the
    replacement, so it says nothing rather than warn about a file that runs."""
    project = tmp_path / "app"
    project.mkdir()
    (project / "playwright.config.ts").write_text(
        "export default { testMatch: '**/*_test.js' };\n", encoding="utf-8"
    )

    assert (
        a_playwright_test_the_runner_will_not_collect(
            "app/a_test.js", PLAYWRIGHT_TEST, project
        )
        is None
    )


def test_a_config_without_a_pattern_leaves_the_note_standing(tmp_path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    (project / "playwright.config.ts").write_text(
        "export default { use: { headless: true } };\n", encoding="utf-8"
    )

    assert (
        a_playwright_test_the_runner_will_not_collect(
            "app/a_test.js", PLAYWRIGHT_TEST, project
        )
        is not None
    )


def test_a_config_above_the_suite_is_found(tmp_path) -> None:
    """A config sits at the project root and the suite a directory below it."""
    project = tmp_path / "app"
    (project / "e2e").mkdir(parents=True)
    (project / "playwright.config.ts").write_text(
        "export default { testMatch: '**/*_test.js' };\n", encoding="utf-8"
    )

    assert (
        a_playwright_test_the_runner_will_not_collect(
            "app/e2e/a_test.js", PLAYWRIGHT_TEST, project / "e2e"
        )
        is None
    )
