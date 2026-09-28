"""Changing the test runner must not exempt a manifest from being asked.

`_tests_the_project_never_runs` asks whether the project's own test command
reaches its test files, and asks it only of a manifest whose `scripts.test`
already contains `node --test`. The reason it gives is good: Jest, Vitest and
Playwright decide discovery in their own configuration, which it cannot read, so
a claim about them could be wrong.

The effect is that the check gets weaker the worse the problem gets. Changing the
runner does not answer the question, it exempts the manifest from being asked.

Measured live on one run. `scripts.test` was
`node --test main.test.js storage.test.js`, and this harness refused that write -
correctly - because it left `main.crud.test.js` unrun. The next write made
`scripts.test` be `npx playwright test`, which runs none of the three, and every
check fell silent: `_tests_the_project_never_runs` and `_manifest_defects` both
returned nothing against that workspace. The ledger shows the suite the gates
measured going from 13 tests to 1:

    09:21:25  npm test       tests=13  passed=6   failed=7
    09:26:50  npm test       tests=13  passed=9   failed=4
    09:39:18  npm test       tests=13  passed=9   failed=4
    09:40:21  playwright     tests=1   passed=0   failed=1
    09:41:05  npm run test   tests=1   passed=0   failed=1

Ten test cases dropped out of what the gates measured and nothing said so. Later
in the same run, with `scripts.test` still `npx playwright test`, the two
commands disagreed outright:

    09:54:09  node --test    tests=17  passed=10  failed=7
    09:59:34  npm run test   tests=3   passed=2   failed=1

Fourteen cases outside the only number any gate reads. That disagreement is what
this claims, and not a stronger thing: Playwright's default `testMatch` does pick
these filenames up, so some of their assertions do run, and "never executed"
would be false. A false blocking finding is the worst shape a check can take.

Decided without reading any runner's configuration. A file importing `node:test`
needs `node --test` to be collected the way it was written; if no script invokes
that, no gate is measuring what these files hold.
"""

from __future__ import annotations

import json

import pytest

from app.analysis.integration_checks import (
    _node_suites_nothing_runs,
    _severity_of,
    _source_files,
)

A_NODE_SUITE = """import { test } from 'node:test';
import assert from 'node:assert';

test('adds a task', () => { assert.ok(true); });
"""

A_PLAYWRIGHT_SPEC = """import { test, expect } from '@playwright/test';

test('adds a task', async ({ page }) => { await page.goto('/'); });
"""


def _project(root, scripts, files):
    project = root / "todo-app"
    project.mkdir(exist_ok=True)
    (project / "package.json").write_text(
        json.dumps({"name": "todo-app", "type": "module", "scripts": scripts})
    )
    for name, body in files.items():
        (project / name).write_text(body)
    return project


def _problems(root):
    return _node_suites_nothing_runs(_source_files(root.resolve()), root.resolve())


class TestTheRunDfWasMeasuredOn:
    def test_the_three_orphaned_suites_are_reported(self, tmp_path):
        _project(
            tmp_path,
            {"test": "npx playwright test", "e2e-test": "npx playwright test"},
            {
                "main.test.js": A_NODE_SUITE,
                "main.crud.test.js": A_NODE_SUITE,
                "storage.test.js": A_NODE_SUITE,
                "e2e.test.js": A_PLAYWRIGHT_SPEC,
            },
        )

        problems = _problems(tmp_path)

        assert len(problems) == 1
        for name in ("main.test.js", "main.crud.test.js", "storage.test.js"):
            assert name in problems[0]

    def test_the_playwright_spec_is_not_among_them(self, tmp_path):
        """It is the one file that command does run."""
        _project(
            tmp_path,
            {"test": "npx playwright test"},
            {"main.test.js": A_NODE_SUITE, "e2e.test.js": A_PLAYWRIGHT_SPEC},
        )

        assert "e2e.test.js" not in _problems(tmp_path)[0]

    def test_it_grades_as_breaking_not_untidy(self, tmp_path):
        """A false green is the whole point, and `untidy` is where this hid before.

        Run-b6436e36's version of this finding reached a live review classified
        "untidy rather than broken - dead rules, unused files".
        """
        _project(
            tmp_path, {"test": "npx playwright test"}, {"main.test.js": A_NODE_SUITE}
        )

        assert _severity_of(_problems(tmp_path)[0]) == "BREAKS"

    def test_it_says_what_to_do(self, tmp_path):
        _project(
            tmp_path, {"test": "npx playwright test"}, {"main.test.js": A_NODE_SUITE}
        )

        assert "node --test" in _problems(tmp_path)[0]

    def test_it_does_not_claim_the_assertions_never_ran(self, tmp_path):
        """The first wording of this check said they had, and that is not certain.

        Playwright's default `testMatch` is
        `**/*.@(spec|test).?(c|m)[jt]s?(x)`, which matches these filenames, so
        it does pick them up and some of their assertions do run - measured on
        one run, whose `npm run test` reported 2 of 3 passing out of files
        `node --test` counted 17 cases in. What is certain is the disagreement
        between the two counts, which is what the message claims.

        Kept as a test because a false blocking finding is the worst shape a
        check can take: the stage will do as it is told.
        """
        _project(
            tmp_path, {"test": "npx playwright test"}, {"main.test.js": A_NODE_SUITE}
        )
        problem = _problems(tmp_path)[0]

        assert "never executed" not in problem
        assert "never ran" not in problem
        assert "not the number of" in problem, (
            "it must still say the measured count is wrong"
        )


class TestSayingNothing:
    def test_a_script_that_does_invoke_node_test_clears_it(self, tmp_path):
        """The suite is reachable, so it is not orphaned."""
        _project(
            tmp_path,
            {"test": "npx playwright test", "unit": "node --test"},
            {"main.test.js": A_NODE_SUITE},
        )

        assert _problems(tmp_path) == []

    def test_a_compound_test_script_clears_it(self, tmp_path):
        _project(
            tmp_path,
            {"test": "node --test && npx playwright test"},
            {"main.test.js": A_NODE_SUITE},
        )

        assert _problems(tmp_path) == []

    def test_a_project_with_no_node_test_files_says_nothing(self, tmp_path):
        _project(
            tmp_path, {"test": "npx playwright test"}, {"e2e.test.js": A_PLAYWRIGHT_SPEC}
        )

        assert _problems(tmp_path) == []

    def test_a_manifest_with_no_test_script_says_nothing(self, tmp_path):
        """Nothing claims to run the suite, so nothing is contradicted."""
        _project(tmp_path, {"build": "vite build"}, {"main.test.js": A_NODE_SUITE})

        assert _problems(tmp_path) == []

    def test_a_broken_manifest_is_left_to_the_check_that_owns_it(self, tmp_path):
        project = tmp_path / "todo-app"
        project.mkdir()
        (project / "package.json").write_text("{not json")
        (project / "main.test.js").write_text(A_NODE_SUITE)

        assert _problems(tmp_path) == []

    def test_a_file_that_is_not_a_test_is_not_reported(self, tmp_path):
        """`is_test` decides that, and a helper importing `node:test` is not a suite."""
        _project(
            tmp_path,
            {"test": "npx playwright test"},
            {"helpers.js": A_NODE_SUITE},
        )

        assert _problems(tmp_path) == []

    def test_an_empty_project_says_nothing(self, tmp_path):
        assert _problems(tmp_path) == []


class TestHowItDecides:
    def test_the_require_form_counts_too(self, tmp_path):
        _project(
            tmp_path,
            {"test": "npx playwright test"},
            {"main.test.js": "const { test } = require('node:test');\ntest('x', () => {});\n"},
        )

        assert "main.test.js" in _problems(tmp_path)[0]

    def test_a_bare_describe_is_not_claimed_for_any_runner(self, tmp_path):
        """Four runners provide `describe`, and guessing would strand a working suite."""
        _project(
            tmp_path,
            {"test": "npx vitest run"},
            {"main.test.js": "describe('x', () => { it('y', () => {}); });\n"},
        )

        assert _problems(tmp_path) == []

    def test_each_manifest_is_judged_on_its_own_scripts(self, tmp_path):
        """A monorepo's other package must not answer for this one."""
        for name, scripts in (
            ("api", {"test": "node --test"}),
            ("web", {"test": "npx playwright test"}),
        ):
            package = tmp_path / name
            package.mkdir()
            (package / "package.json").write_text(
                json.dumps({"name": name, "type": "module", "scripts": scripts})
            )
            (package / "main.test.js").write_text(A_NODE_SUITE)

        problems = _problems(tmp_path)

        assert len(problems) == 1
        assert "web/" in problems[0]
        assert "api/" not in problems[0]


class TestItIsWiredIn:
    def test_the_registry_carries_it(self):
        """A check nothing calls is a check that does not run."""
        from app.analysis.integration_checks import _CHECKS

        assert any(
            "node:test suites" in description for description, _ in _CHECKS
        ), [description for description, _ in _CHECKS]

    def test_the_summary_reports_it(self, tmp_path):
        """End to end through what the milestone reviewer is actually given."""
        from app.analysis.integration_checks import summarise_integration

        _project(
            tmp_path,
            {"test": "npx playwright test"},
            {"main.test.js": A_NODE_SUITE, "index.html": "<html><body></body></html>"},
        )

        assert "has no script that runs" in summarise_integration(tmp_path, "javascript")
