"""A UI stack must name the browser runner, because saying so was not enough.

The stack selector's own prompt says it in capitals, with the measurement behind
it: "A PRODUCT WITH A USER INTERFACE NEEDS BOTH RUNNERS, AND NAMING BOTH IS THE
RIGHT ANSWER ... write both into `testing_framework` - for example 'node --test
for the logic, Playwright for the page'". It also says twice that there is no
display and nobody to look at one, so manual browser checking is impossible.

run-1bdbc08a did neither. For a brief asking for a "Simple web-based interface
with HTML/CSS/JavaScript" its stack came back:

    Testing framework: node --test

    ... The app's extreme simplicity means configuring multiple test frameworks
    would consume disproportionate effort ...; a single-page vanilla JS app of
    this size is adequately verified by testing its core logic and manual
    browser verification.

Its specialists then did the right thing - `package.json` ran
`test:unit && test:e2e` with `@playwright/test` declared - so the delivered
product was correct and the stack document contradicted it. That contradiction is
a blocking finding: `_a_test_runner_the_stack_did_not_choose` reports a package
the stack never named, and it fires against every UI run whose specialists behave
well.

The three sprints were otherwise clean: 16, 56 and 42 tests, all passing, 384
code lines against a 500-line budget, and this was the only problem the checks
found in what it delivered.
"""

from __future__ import annotations

import pytest

from app.agents.stack_selector import the_browser_runner_this_stack_forgot


class Stack:
    def __init__(self, **fields: str) -> None:
        self.language = fields.get("language", "JavaScript")
        self.framework = fields.get("framework", "")
        self.frontend_framework = fields.get("frontend_framework", "")
        self.database = fields.get("database", "")
        self.testing_framework = fields.get("testing_framework", "")


class TestABrowserProductGetsTheRunner:
    def test_the_run_1bdbc08a_stack_is_corrected(self) -> None:
        corrected = the_browser_runner_this_stack_forgot(
            Stack(
                framework="None (vanilla HTML/CSS/JS)",
                database="localStorage (browser-native)",
                testing_framework="node --test",
            )
        )

        assert corrected == "node --test for the logic, Playwright for the page"

    @pytest.mark.parametrize(
        "fields",
        (
            {"framework": "Express", "frontend_framework": "React", "testing_framework": "jest"},
            {"framework": "None (vanilla HTML/CSS/JS)", "testing_framework": "node --test"},
            {"framework": "FastAPI", "frontend_framework": "Vue", "testing_framework": "pytest"},
            {"framework": "Django", "frontend_framework": "Svelte", "testing_framework": "pytest"},
        ),
    )
    def test_any_stack_with_a_browser_in_it_is_corrected(self, fields: dict) -> None:
        corrected = the_browser_runner_this_stack_forgot(Stack(**fields))

        assert corrected is not None
        assert "Playwright" in corrected
        assert corrected.startswith(fields["testing_framework"]), (
            "the runner the stack chose must survive; the browser one is added "
            "beside it, not instead of it"
        )


class TestItLeavesEverythingElseAlone:
    @pytest.mark.parametrize(
        "declared",
        (
            "node --test for the logic, Playwright for the page",
            "vitest + Cypress",
            "jest and puppeteer",
            "pytest with Selenium",
        ),
    )
    def test_a_stack_already_naming_a_browser_runner_is_untouched(
        self, declared: str
    ) -> None:
        stack = Stack(framework="None (vanilla HTML/CSS/JS)", testing_framework=declared)

        assert the_browser_runner_this_stack_forgot(stack) is None

    @pytest.mark.parametrize(
        "fields",
        (
            {"language": "Python", "framework": "Click", "database": "SQLite", "testing_framework": "pytest"},
            {"language": "Go", "framework": "Gin", "database": "PostgreSQL", "testing_framework": "go test"},
            {"language": "Rust", "framework": "Axum", "database": "Postgres", "testing_framework": "cargo test"},
        ),
    )
    def test_a_product_with_no_browser_is_untouched(self, fields: dict) -> None:
        """A CLI or a backend API has no page to drive."""
        assert the_browser_runner_this_stack_forgot(Stack(**fields)) is None

    def test_a_stack_that_named_no_runner_is_untouched(self) -> None:
        """Nothing to add beside; a stack with no runner is a different fault."""
        stack = Stack(framework="None (vanilla HTML/CSS/JS)", testing_framework="")

        assert the_browser_runner_this_stack_forgot(stack) is None

    def test_a_missing_stack_does_not_raise(self) -> None:
        assert the_browser_runner_this_stack_forgot(None) is None


def test_the_corrected_stack_satisfies_both_checks(tmp_path) -> None:
    """The point of the repair: a workspace that no check objects to.

    With the stack naming only the logic runner, a project that installs
    Playwright is reported; with the browser runner named, it is not, and the
    check that demands Playwright is satisfied too.
    """
    import json

    from app.analysis.integration_checks import (
        _a_test_runner_the_stack_did_not_choose,
        _missing_playwright_for_ui,
    )

    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"@playwright/test": "^1.63.0"}}), encoding="utf-8"
    )
    (tmp_path / "index.html").write_text(
        '<html><body><script type="module" src="app.js"></script></body></html>',
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text("export const a = 1;\n", encoding="utf-8")
    files = [tmp_path / "package.json", tmp_path / "index.html", tmp_path / "app.js"]

    before = Stack(
        framework="None (vanilla HTML/CSS/JS)", testing_framework="node --test"
    )
    assert _a_test_runner_the_stack_did_not_choose(files, tmp_path, before), (
        "this is the finding run-1bdbc08a shipped with"
    )

    after = Stack(
        framework="None (vanilla HTML/CSS/JS)",
        testing_framework=the_browser_runner_this_stack_forgot(before) or "",
    )
    assert _a_test_runner_the_stack_did_not_choose(files, tmp_path, after) == []
    assert _missing_playwright_for_ui(files, tmp_path, after) == []


def test_the_node_applies_the_repair_before_rendering_the_document() -> None:
    """The document readers see is rendered from the selection, so the repair
    has to happen before `_record_document`, not after."""
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow.build_workflow_graph)
    node = source.split("def stack_selector_node", 1)[1].split("def principal_architect_node", 1)[0]
    repair = node.find("the_browser_runner_this_stack_forgot")
    render = node.find("docs/technology_stack.md")

    assert repair != -1 and render != -1
    assert repair < render
