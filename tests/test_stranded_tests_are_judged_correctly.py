"""`node --test` strandedness: quoted paths resolve, other runners' specs don't strand.

Two false positives, both found live on 2026-09-21 and both **blocking** - the
check's worst shape, because a stage does what a blocking finding tells it.

**Quoted arguments.** `task-manager/package.json` held::

    "test": "node --test \\"app.test.mjs\\" \\"line-budget.test.mjs\\""

`command.split()` kept the quote characters, so `'"app.test.mjs"'` never matched
the real relative path `app.test.mjs`. The finding listed both files as the ones
the command *names* and as *stranded*, in the same sentence.

**Another runner's spec.** `e2e/task-manager.spec.js` is a Playwright spec, run
by `npx playwright test` through `scripts["test:e2e"]` - twenty assertions, all
green in that run. The check reported it stranded and advised "name them too" in
`scripts.test`. Verified in the run image, that advice throws::

    $ node --test e2e/task-manager.spec.js
    Error: Playwright Test did not expect test.describe() to be called here.

A remedy that breaks a passing suite is worse than no check.
"""

from __future__ import annotations

import json

import pytest

from app.analysis.integration_checks import (
    _belongs_to_another_runner,
    _paths_named_after_the_test_flag,
)


class TestQuotedPathsResolve:
    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            ('node --test "app.test.mjs" "line-budget.test.mjs"',
             ["app.test.mjs", "line-budget.test.mjs"]),
            ("node --test 'app.test.mjs'", ["app.test.mjs"]),
            ("node --test app.test.mjs", ["app.test.mjs"]),
            ("node --test tests/", ["tests/"]),
            ('node --test "tests/"', ["tests/"]),
            # Flags are still ignored.
            ('node --test --experimental-test-coverage "a.test.mjs"', ["a.test.mjs"]),
        ],
    )
    def test_arguments_come_back_unquoted(self, command, expected):
        assert _paths_named_after_the_test_flag(command) == expected

    def test_an_unbalanced_quote_does_not_lose_the_check(self):
        """A broken manifest is reported elsewhere; this must not raise."""
        assert isinstance(_paths_named_after_the_test_flag('node --test "a.mjs'), list)

    def test_no_test_flag_means_no_paths(self):
        assert _paths_named_after_the_test_flag("vitest run") == []


class TestAnotherRunnersSpecIsRecognised:
    @pytest.mark.parametrize(
        ("source", "owner"),
        [
            ("import { test, expect } from '@playwright/test';", "@playwright/test"),
            ('import { test } from "@playwright/test";', "@playwright/test"),
            ("import { describe, it } from 'vitest';", "vitest"),
            ("import { test } from '@jest/globals';", "@jest/globals"),
        ],
    )
    def test_it_names_the_owner(self, tmp_path, source, owner):
        spec = tmp_path / "a.spec.js"
        spec.write_text(source + "\ntest('x', () => {});\n")
        assert _belongs_to_another_runner(spec) == owner

    def test_a_plain_node_test_file_is_not_owned_elsewhere(self, tmp_path):
        spec = tmp_path / "a.test.mjs"
        spec.write_text(
            "import { test } from 'node:test';\n"
            "import assert from 'node:assert';\n"
            "test('x', () => assert.ok(true));\n"
        )
        assert _belongs_to_another_runner(spec) == ""


class TestTheWholeCheckOnTheRealShape:
    """End to end over a workspace shaped like the one that found this."""

    @pytest.fixture
    def project(self, tmp_path):
        p = tmp_path / "task-manager"
        (p / "e2e").mkdir(parents=True)
        (p / "package.json").write_text(json.dumps({
            "name": "task-manager", "type": "module",
            "scripts": {
                "test": 'node --test "app.test.mjs" "line-budget.test.mjs"',
                "test:e2e": "npx playwright test",
            },
        }))
        (p / "app.js").write_text("export const add = (a, b) => a + b;\n")
        (p / "index.html").write_text(
            '<html><body><script type="module" src="app.js"></script></body></html>'
        )
        for name in ("app.test.mjs", "line-budget.test.mjs"):
            (p / name).write_text(
                "import { test } from 'node:test';\n"
                "import assert from 'node:assert';\n"
                "import { add } from './app.js';\n"
                "test('x', () => assert.equal(add(1,1), 2));\n"
            )
        (p / "e2e" / "task-manager.spec.js").write_text(
            "import { test, expect } from '@playwright/test';\n"
            "test('loads', async ({ page }) => { await page.goto('/'); });\n"
        )
        return tmp_path

    def test_nothing_is_stranded_in_this_shape(self, project):
        from app.analysis.integration_checks import _source_files, _tests_the_project_never_runs

        problems = _tests_the_project_never_runs(_source_files(project), project)
        stranded = [p for p in problems if "Stranded" in p]
        assert not stranded, f"false positive returned: {stranded}"

    def test_a_genuinely_stranded_suite_is_still_caught(self, project):
        """The check must keep working - this is the case it exists for."""
        from app.analysis.integration_checks import _source_files, _tests_the_project_never_runs

        orphan = project / "task-manager" / "forgotten.test.mjs"
        orphan.write_text(
            "import { test } from 'node:test';\n"
            "import assert from 'node:assert';\n"
            "test('never runs', () => assert.ok(true));\n"
        )
        problems = _tests_the_project_never_runs(_source_files(project), project)
        assert any("forgotten.test.mjs" in p for p in problems), (
            "a real stranded suite stopped being reported"
        )

    def test_a_playwright_spec_with_no_runner_script_is_reported(self, project):
        """Not stranded by `node --test`, but genuinely run by nothing."""
        from app.analysis.integration_checks import _source_files, _tests_the_project_never_runs

        manifest = project / "task-manager" / "package.json"
        data = json.loads(manifest.read_text())
        del data["scripts"]["test:e2e"]
        manifest.write_text(json.dumps(data))

        problems = _tests_the_project_never_runs(_source_files(project), project)
        assert any("task-manager.spec.js" in p for p in problems)
        assert not any("name them too" in p.lower() for p in problems), (
            "must not advise adding a Playwright spec to `node --test`"
        )
