"""Two blocking checks demanded opposite things, so no workspace satisfied both.

`_missing_playwright_for_ui` required `@playwright/test` in any project with an
HTML UI and client logic. `_a_test_runner_the_stack_did_not_choose` reports a
test runner installed over the one `stack_selector` chose. Both grade BREAKS.

On a project whose stack chose `node --test with JSDOM`, measured directly:

    without @playwright/test -> "Playwright is not installed ... You MUST
                                 install `@playwright/test`"            BREAKS
    with @playwright/test    -> "installs '@playwright/test', but this run's
                                 stack chose 'node --test with JSDOM'"  BREAKS

The remedy for each is the thing the other forbids, so a milestone reviewer
cannot accept either and every revision swaps one finding for the other.

One run hit the second horn and failed at the revision limit:

    [major] contracts: @playwright/test is declared as a devDependency in
    todo-app/package.json, but technology_stack.md explicitly chose
    'node --test with JSDOM' as the testing framework.

    [suggestion] playwright.config.ts and e2e/ui-interactions.spec.js are
    orphaned artifacts from a previous specialist.

Earlier runs hit the first.

Resolved towards the run's own decision. `stack_selector` chooses the testing
framework and writes it to `technology_stack.md`, and the runner check already
enforces the project against that choice - two authorities on one question is
what produced the loop. The Playwright check also hard-codes one vendor's tool,
which a harness that has to build products in every framework and language
cannot do.

So the requirement stands where the stack named Playwright or named nothing, and
defers where the stack named something else.
"""

from __future__ import annotations

import json

import pytest

from app.analysis.integration_checks import (
    _a_test_runner_the_stack_did_not_choose,
    _missing_playwright_for_ui,
    _severity_of,
)


class Stack:
    def __init__(self, testing_framework: str) -> None:
        self.testing_framework = testing_framework


@pytest.fixture
def a_ui_project(tmp_path):
    """A project with an HTML UI and client logic - what both checks look at."""

    def _build(with_playwright: bool):
        project = tmp_path / "todo-app"
        project.mkdir(exist_ok=True)
        (project / "index.html").write_text(
            '<!doctype html><html><body><ul id="tasks"></ul>'
            '<script type="module" src="./app.js"></script></body></html>'
        )
        (project / "app.js").write_text(
            "export const add = (t) => t;\n"
            "document.getElementById('tasks').textContent = 'x';\n"
        )
        manifest = {
            "type": "module",
            "scripts": {"test": "node --test"},
            "devDependencies": {},
        }
        if with_playwright:
            manifest["devDependencies"]["@playwright/test"] = "^1.40.0"
        (project / "package.json").write_text(json.dumps(manifest))
        return tmp_path, [f for f in tmp_path.rglob("*") if f.is_file()]

    return _build


def _both(a_ui_project, framework: str, with_playwright: bool):
    root, files = a_ui_project(with_playwright)
    stack = Stack(framework)
    return (
        _missing_playwright_for_ui(files, root, stack),
        _a_test_runner_the_stack_did_not_choose(files, root, stack),
    )


class TestNoWorkspaceCanTriggerBoth:
    """The property that matters: some state of the workspace must be acceptable."""

    @pytest.mark.parametrize(
        "framework",
        [
            "node --test with JSDOM",
            "Playwright",
            "playwright",
            "jest + jsdom",
            "vitest",
            "Custom JS assert tests",
            "",
        ],
    )
    def test_some_state_satisfies_both_checks(self, a_ui_project, framework):
        states = {
            "without playwright": _both(a_ui_project, framework, False),
            "with playwright": _both(a_ui_project, framework, True),
        }

        clean = [name for name, (a, b) in states.items() if not a and not b]

        assert clean, (
            f"stack chose {framework!r} and neither state is acceptable: "
            + "; ".join(
                f"{name}: {len(a)} missing-playwright, {len(b)} wrong-runner"
                for name, (a, b) in states.items()
            )
        )

    @pytest.mark.parametrize(
        "framework", ["node --test with JSDOM", "jest + jsdom", "vitest"]
    )
    def test_never_both_at_once(self, a_ui_project, framework):
        for with_playwright in (False, True):
            missing, wrong = _both(a_ui_project, framework, with_playwright)

            assert not (missing and wrong)


class TestTheRunThatFailed:
    def test_a_stack_that_chose_node_test_is_not_told_to_install_playwright(
        self, a_ui_project
    ):
        """One run's stack. The demand contradicted its own stack document."""
        missing, _ = _both(a_ui_project, "node --test with JSDOM", False)

        assert missing == []

    def test_playwright_installed_over_it_is_still_reported(self, a_ui_project):
        """The other side of the contradiction is the side that was right."""
        _, wrong = _both(a_ui_project, "node --test with JSDOM", True)

        assert len(wrong) == 1
        assert "@playwright/test" in wrong[0]

    def test_removing_it_now_clears_everything(self, a_ui_project):
        """Which is what makes the finding actionable rather than a loop."""
        missing, wrong = _both(a_ui_project, "node --test with JSDOM", False)

        assert missing == [] and wrong == []


class TestTheRequirementIsNotGone:
    def test_a_stack_that_chose_playwright_must_install_it(self, a_ui_project):
        missing, _ = _both(a_ui_project, "Playwright", False)

        assert len(missing) == 1
        assert "@playwright/test" in missing[0]

    def test_a_stack_that_chose_nothing_still_gets_the_finding(self, a_ui_project):
        """No decision was recorded, so there is no decision to defer to."""
        missing, _ = _both(a_ui_project, "", False)

        assert len(missing) == 1

    def test_it_is_still_graded_as_breaking(self, a_ui_project):
        missing, _ = _both(a_ui_project, "", False)

        assert _severity_of(missing[0]) == "BREAKS"

    def test_a_stack_object_that_is_none_still_gets_the_finding(self, a_ui_project):
        root, files = a_ui_project(False)

        assert len(_missing_playwright_for_ui(files, root, None)) == 1

    def test_playwright_named_inside_a_longer_choice_counts(self, a_ui_project):
        """`Playwright for e2e, node --test for units` named it, so it is required."""
        missing, _ = _both(a_ui_project, "Playwright for e2e, node --test for units", False)

        assert len(missing) == 1

    def test_a_word_containing_playwright_is_not_a_match(self, a_ui_project):
        """Matched on word boundaries, as the runner check matches its aliases."""
        missing, _ = _both(a_ui_project, "playwrights-custom-harness", False)

        assert missing == []


class TestTheOtherNarrowingsSurvive:
    def test_a_static_page_is_left_alone(self, tmp_path):
        (tmp_path / "index.html").write_text("<html><body><div>hi</div></body></html>")
        files = [f for f in tmp_path.rglob("*") if f.is_file()]

        assert _missing_playwright_for_ui(files, tmp_path, Stack("")) == []

    def test_a_project_with_no_manifest_is_left_alone(self, tmp_path):
        (tmp_path / "index.html").write_text(
            '<html><body><script type="module" src="./app.js"></script></body></html>'
        )
        (tmp_path / "app.js").write_text("document.title = 'x';\n")
        files = [f for f in tmp_path.rglob("*") if f.is_file()]

        assert _missing_playwright_for_ui(files, tmp_path, Stack("")) == []

    def test_no_html_is_left_alone(self, tmp_path):
        (tmp_path / "app.js").write_text("export const a = 1;\n")
        (tmp_path / "package.json").write_text("{}")
        files = [f for f in tmp_path.rglob("*") if f.is_file()]

        assert _missing_playwright_for_ui(files, tmp_path, Stack("")) == []
