"""A file the plan named and nobody wrote is invisible to every other check.

Every cross-file check in `integration_checks` decides by comparing two files
that exist. A file that was planned and simply never written is referenced by
nothing, so there is no inconsistency on disk to find - there is nothing on disk
at all. The plan is the other half of the comparison, and nothing was reading it.

Two consecutive runs ended on exactly that.

run-e980310b delegated "Create style.css with basic responsive CSS rules" and
`index.html` linked it. That one is provable from the workspace, because the
link is a second file naming the first, and `_broken_local_references` finds it.

run-2ac28a2f is the version nothing could prove. Its plan named

    index.html with semantic HTML5 structure: <header>, form (#add-form) for
    task creation, unordered list container for tasks, embedded CSS

and the sprint finished with `app.js`, `app.test.js`, `package.json`,
`jest.config.cjs` and no HTML file - a "single-page application" with no page.
34 tests passed, 0 failed, 0 bugs found across three test rounds, and the
milestone reviewer raised it three times until the run hit the revision limit:

    [major] correctness: No HTML file exists for the single-page application.
    A glob search of simple-to-do-list/**/*.html returned zero results.

Language-agnostic by construction: it reads path-like tokens out of prose and
asks the filesystem, so a plan naming `Cargo.toml`, `main.go`, `pom.xml` or
`index.html` is checked the same way.
"""

from __future__ import annotations

import pytest

from app.analysis.planned_files import (
    files_the_plan_named_that_are_missing,
    paths_a_plan_named,
)

#: run-2ac28a2f's plan, verbatim from `sprint_1_summary.md`.
THE_PLAN_THAT_FAILED = [
    'Create simple-to-do-list/ project directory with package.json ("type": '
    '"module", jest test script, devDependencies for Jest + jsdom only)',
    "index.html with semantic HTML5 structure: <header>, form (#add-form) for task "
    "creation, unordered list container for tasks, embedded CSS within <style>",
    "app.js ES module exporting pure functions: loadTasks(), saveTasks(), addTask(), "
    "deleteTask()",
    "Jest test suite (app.test.js) with unit tests for addTask, deleteTask, "
    "loadTasks, saveTasks using mock storage adapters",
]


@pytest.fixture
def the_workspace_it_left(tmp_path):
    """Exactly what run-2ac28a2f finished with: everything but the page."""
    project = tmp_path / "simple-to-do-list"
    project.mkdir()
    (project / "package.json").write_text('{"type": "module"}\n')
    (project / "app.js").write_text("export const addTask = () => {};\n")
    (project / "app.test.js").write_text("test('x', () => {});\n")
    (project / "jest.config.cjs").write_text("module.exports = {};\n")
    return tmp_path


class TestTheRunThatFailed:
    def test_the_missing_page_is_reported(self, the_workspace_it_left):
        problems = files_the_plan_named_that_are_missing(
            THE_PLAN_THAT_FAILED, str(the_workspace_it_left)
        )

        assert any("index.html" in problem for problem in problems), problems

    def test_the_files_that_were_written_are_not(self, the_workspace_it_left):
        """Three of the four planned files landed, and must not be reported."""
        problems = " ".join(
            files_the_plan_named_that_are_missing(
                THE_PLAN_THAT_FAILED, str(the_workspace_it_left)
            )
        )

        assert "app.js" not in problems
        assert "app.test.js" not in problems
        assert "package.json" not in problems

    def test_it_says_a_passing_suite_does_not_clear_it(self, the_workspace_it_left):
        """34 tests passed while the deliverable did not exist. That is the point."""
        problems = files_the_plan_named_that_are_missing(
            THE_PLAN_THAT_FAILED, str(the_workspace_it_left)
        )

        assert any("passing suite says nothing about it" in p for p in problems)

    def test_it_allows_the_plan_to_have_changed(self, the_workspace_it_left):
        """A plan may be revised. What it may not be is silently not done."""
        problems = files_the_plan_named_that_are_missing(
            THE_PLAN_THAT_FAILED, str(the_workspace_it_left)
        )

        assert any("why the plan no longer needs it" in p for p in problems)

    def test_the_page_appearing_settles_it(self, the_workspace_it_left):
        (the_workspace_it_left / "simple-to-do-list" / "index.html").write_text(
            "<!doctype html><html></html>"
        )

        assert files_the_plan_named_that_are_missing(
            THE_PLAN_THAT_FAILED, str(the_workspace_it_left)
        ) == []


class TestTheProjectDirectoryIsNotThePlansToKnow:
    def test_a_bare_name_matches_a_file_inside_the_project(self, tmp_path):
        """The plan writes `index.html`; the workspace holds `todo-app/index.html`."""
        (tmp_path / "todo-app").mkdir()
        (tmp_path / "todo-app" / "index.html").write_text("<html></html>")

        assert files_the_plan_named_that_are_missing(["index.html"], str(tmp_path)) == []

    def test_a_full_path_matches_too(self, tmp_path):
        (tmp_path / "todo-app").mkdir()
        (tmp_path / "todo-app" / "index.html").write_text("<html></html>")

        assert files_the_plan_named_that_are_missing(
            ["todo-app/index.html"], str(tmp_path)
        ) == []


class TestEveryLanguageIsReadTheSameWay:
    @pytest.mark.parametrize(
        "planned,written,missing",
        [
            (["Add Cargo.toml and src/main.rs"], ["Cargo.toml"], "main.rs"),
            (["Create go.mod and main.go for the service"], ["go.mod"], "main.go"),
            (["pom.xml plus App.java under src"], ["pom.xml"], "App.java"),
            (["pyproject.toml and app/__init__.py"], ["pyproject.toml"], "__init__.py"),
            (["Gemfile and config.ru for rack"], ["Gemfile"], "config.ru"),
            (["index.html, styles.scss"], ["index.html"], "styles.scss"),
            (["composer.json and public/index.php"], ["composer.json"], "index.php"),
        ],
    )
    def test_the_missing_one_is_named(self, tmp_path, planned, written, missing):
        for name in written:
            (tmp_path / name).write_text("x")
        (tmp_path / "placeholder.txt").write_text("x")

        problems = " ".join(files_the_plan_named_that_are_missing(planned, str(tmp_path)))

        assert missing in problems, problems
        for name in written:
            assert f"`{name}`" not in problems


class TestNotReadingProseAsAFilename:
    @pytest.mark.parametrize(
        "text",
        [
            "Use jsdom for the DOM, e.g. for the render test",
            "Follow ADR-05 and section 3.2 of the specification",
            "Version 1.0.0 of the package",
            "The localStorage key is 'todo-tasks'",
            "Semantic HTML5 structure with a header",
            "Persist after every mutation i.e. on add and delete",
            "Target 80% coverage",
        ],
    )
    def test_nothing_is_reported(self, tmp_path, text):
        (tmp_path / "placeholder.txt").write_text("x")

        assert files_the_plan_named_that_are_missing([text], str(tmp_path)) == [], text

    def test_a_dotfile_with_an_extension_is_read_as_a_file(self, tmp_path):
        """The stoplist is for abbreviations, not for a file with a leading dot."""
        assert paths_a_plan_named(["Write the .eslintrc.json config"]) == [
            ".eslintrc.json"
        ]
        assert paths_a_plan_named(["Add .env.example for the keys"]) == [".env.example"]

    def test_a_dotfile_with_no_extension_is_not_matched(self):
        """A documented limit: there is nothing to anchor on but the word itself,
        and matching a bare dotted word would read half a sentence as a path."""
        assert paths_a_plan_named(["Add a .gitignore for node_modules"]) == []


class TestNeverGettingInTheWay:
    def test_a_plan_naming_no_file_reports_nothing(self, tmp_path):
        (tmp_path / "placeholder.txt").write_text("x")

        assert files_the_plan_named_that_are_missing(
            ["Users can create and delete tasks"], str(tmp_path)
        ) == []

    def test_no_plan_reports_nothing(self, tmp_path):
        (tmp_path / "placeholder.txt").write_text("x")

        assert files_the_plan_named_that_are_missing([], str(tmp_path)) == []

    def test_an_unreadable_workspace_reports_nothing(self, tmp_path):
        """A check that cannot see the files cannot say one is absent."""
        assert files_the_plan_named_that_are_missing(
            ["index.html"], str(tmp_path / "gone")
        ) == []

    def test_an_empty_workspace_reports_nothing(self, tmp_path):
        """Before any stage has written, every planned file is legitimately absent."""
        assert files_the_plan_named_that_are_missing(["index.html"], str(tmp_path)) == []

    def test_the_list_is_capped(self, tmp_path):
        (tmp_path / "placeholder.txt").write_text("x")
        planned = [f"Create file{index}.ts for the module" for index in range(12)]

        assert len(files_the_plan_named_that_are_missing(planned, str(tmp_path))) <= 4

    def test_none_of_it_raises_on_junk(self, tmp_path):
        (tmp_path / "placeholder.txt").write_text("x")

        assert files_the_plan_named_that_are_missing(
            [None, "", 123, "index.html"], str(tmp_path)  # type: ignore[list-item]
        ) != []

    def test_a_node_modules_file_does_not_satisfy_a_plan(self, tmp_path):
        """A dependency's `index.html` is not the product's page."""
        vendored = tmp_path / "app" / "node_modules" / "thing"
        vendored.mkdir(parents=True)
        (vendored / "index.html").write_text("<html></html>")
        (tmp_path / "app" / "app.js").write_text("x")

        assert files_the_plan_named_that_are_missing(["index.html"], str(tmp_path)) != []


class TestItReachesTheTestRound:
    def test_the_brief_carries_the_missing_file(self, the_workspace_it_left):
        """The stage whose job is finding defects, inside the sprint."""
        from app.agents.specialists import build_test_run_request

        brief = build_test_run_request(
            "Users can create and delete tasks",
            ["app.js"],
            str(the_workspace_it_left),
            "javascript",
            planned=THE_PLAN_THAT_FAILED,
        )["messages"][0]["content"]

        assert "index.html" in brief
        assert "Already proven by reading the files" in brief

    def test_a_brief_without_a_plan_is_unchanged(self, the_workspace_it_left):
        """Every existing caller passes no plan and must get what it always got."""
        from app.agents.specialists import build_test_run_request

        brief = build_test_run_request(
            "Users can create and delete tasks",
            ["app.js"],
            str(the_workspace_it_left),
            "javascript",
        )["messages"][0]["content"]

        assert "index.html" not in brief
        assert "Run the unit, integration" in brief

    def test_the_workflow_passes_the_plan(self):
        """Checked on the source: the node is a closure over the compiled graph."""
        import inspect

        from app.graph import workflow

        source = inspect.getsource(workflow)
        call = source.index("request = build_test_run_request(")
        block = source[call : call + 900]

        assert "planned=" in block
        assert "milestone_scope" in block
        assert "task_description" in block


class TestAJavaScriptLibraryIsNotAPlannedFile:
    """`Node.js` is a platform, and this check reported it as a missing file.

    Found by sweeping the 25 stored sprint plans. A plan saying "Use Node.js
    built-in test runner for unit tests" had `Node.js` reported as

        This sprint's plan names `Node.js` and the workspace has no file of that
        name anywhere.

    at the breaking tier, and the breaking tier is what `build_test_run_request`
    hands the test round as already proven - so a bogus blocking defect, costing a
    remediation cycle. `Vue.js`, `Next.js`, `D3.js` and `Backbone.js` all did the
    same.

    The convention is what makes it decidable: libraries are written `Node.js`,
    files are written `app.js` or `task-list.js`.
    """

    @pytest.mark.parametrize(
        "planned",
        [
            "Use Node.js built-in test runner for unit tests",
            "Target Node.js 20 and the ES2022 standard",
            "Build the view layer with Vue.js",
            "Use React.js with no build step",
            "Use Next.js for routing",
            "Render the chart with D3.js",
            "Three.js for the scene graph",
            "Chart.js for the dashboard",
            "Backbone.js is explicitly ruled out",
        ],
    )
    def test_a_library_is_not_reported_as_missing(self, tmp_path, planned):
        (tmp_path / "placeholder.txt").write_text("x")

        assert files_the_plan_named_that_are_missing([planned], str(tmp_path)) == [], planned

    @pytest.mark.parametrize(
        "planned,expected",
        [
            ("Create task-list.js for rendering", "task-list.js"),
            ("Write app.js exporting the pure functions", "app.js"),
            ("Vendor d3.js into the project", "d3.js"),
            ("Add App.java under src/main", "App.java"),
            ("Add Program.cs to the project", "Program.cs"),
            ("Add Cargo.toml and main.rs", "Cargo.toml"),
            ("Add README.md describing the setup", "README.md"),
            ("Create Widget.vue for the panel", "Widget.vue"),
        ],
    )
    def test_a_real_file_is_still_reported(self, tmp_path, planned, expected):
        """Only a capitalised stem with `.js` is excluded; nothing else changes."""
        (tmp_path / "placeholder.txt").write_text("x")

        problems = " ".join(files_the_plan_named_that_are_missing([planned], str(tmp_path)))

        assert expected in problems, planned

    def test_a_library_that_is_vendored_stays_silent(self, tmp_path):
        """A workspace that has the file was always silent, and still is."""
        (tmp_path / "vendor").mkdir()
        (tmp_path / "vendor" / "Chart.js").write_text("x")

        assert files_the_plan_named_that_are_missing(
            ["Bundle Chart.js into vendor/"], str(tmp_path)
        ) == []


class TestOnlySomethingWithARealExtension:
    """A CSS selector is not a filename, and this reported one as a missing file.

    Found live in run-1a0d3610, where the plan described an error banner and the
    check reported

        This sprint's plan names `div.error` and the workspace has no file of that
        name anywhere.

    at the breaking tier - the tier `build_test_run_request` hands the test round
    as already proven. `div.error`, `span.task-title`, `input.checkbox` and
    `li.completed` all matched, because the pattern accepted any short alphabetic
    tail as an extension.

    Checked against an allowlist now, grown from the suffix set
    `integration_checks` already maintains across every language this harness
    builds in, plus the configuration, documentation and asset extensions a plan
    names. Missing an unusual extension costs a missed detection, which is the
    safe direction: the alternative is a blocking defect for something that was
    never a file.
    """

    @pytest.mark.parametrize(
        "planned",
        [
            "Show a div.error banner when storage is unavailable",
            "Style span.task-title with a strikethrough when completed",
            "Add input.checkbox to each task item",
            "Toggle the li.completed class on the list item",
            "Give the form a button.primary submit control",
            "Target ul.task-list in the stylesheet",
        ],
    )
    def test_a_selector_is_not_reported(self, tmp_path, planned):
        (tmp_path / "placeholder.txt").write_text("x")

        assert files_the_plan_named_that_are_missing([planned], str(tmp_path)) == [], planned

    @pytest.mark.parametrize(
        "planned,expected",
        [
            ("Create index.html with the form", "index.html"),
            ("Add Cargo.toml and main.rs", "Cargo.toml"),
            ("Write docker-compose.yml for the services", "docker-compose.yml"),
            ("Add .env.example listing the keys", ".env.example"),
            ("Add schema.prisma and the migrations", "schema.prisma"),
            ("Create logo.svg for the header", "logo.svg"),
            ("Add openapi.yaml describing the routes", "openapi.yaml"),
            ("Add Program.cs to the project", "Program.cs"),
            ("Add a Makefile target in build.gradle", "build.gradle"),
            ("Write notes.md for the maintainer", "notes.md"),
        ],
    )
    def test_a_real_extension_is_still_read(self, tmp_path, planned, expected):
        (tmp_path / "placeholder.txt").write_text("x")

        problems = " ".join(files_the_plan_named_that_are_missing([planned], str(tmp_path)))

        assert expected in problems, planned

    def test_the_two_findings_that_matter_survive(self, tmp_path):
        """`index.html` on run-2ac28a2f and `style.css` on run-e980310b."""
        (tmp_path / "placeholder.txt").write_text("x")

        problems = " ".join(
            files_the_plan_named_that_are_missing(
                [
                    "index.html with semantic HTML5 structure and a form",
                    "Create style.css with basic responsive CSS rules",
                ],
                str(tmp_path),
            )
        )

        assert "index.html" in problems
        assert "style.css" in problems

    def test_the_allowlist_covers_what_the_checks_collect(self):
        """A language the cross-file checks read must not be a language this drops."""
        from app.analysis.integration_checks import _COLLECTED_SUFFIXES
        from app.analysis.planned_files import _REALLY_AN_EXTENSION

        collected = {suffix.lstrip(".") for suffix in _COLLECTED_SUFFIXES}

        assert collected <= _REALLY_AN_EXTENSION, sorted(collected - _REALLY_AN_EXTENSION)


class TestAnExtensionThatMeansTheSameThing:
    """A plan asking for `app.test.js` is satisfied by `app.test.mjs`.

    Measured on run-a6b28314. Its plan named `app.test.js`, the project built
    `app.test.mjs` - the extension its own module system requires - and this check
    reported the planned file as never written, eight times, at the breaking tier.

    That tier is handed to the test round as already proven, and a `defect_fix`
    stage tried to clear the finding by rewriting `docs/sprint_plan.md` with a
    `python3 -c` snippet: refused twice over, for executing code and for writing
    into the workflow's own directory. A false finding does not only waste a call,
    it aims a stage at the wrong file.
    """

    @pytest.fixture
    def a_project(self, tmp_path):
        project = tmp_path / "task-manager"
        project.mkdir()
        (project / "app.test.mjs").write_text("x")
        (project / "index.html").write_text("x")
        (project / "config.yaml").write_text("x")
        (project / "main.js").write_text("x")
        return tmp_path

    @pytest.mark.parametrize(
        "planned",
        [
            "Build app.test.js with unit tests",
            "Build app.test.cjs with unit tests",
            "Create index.htm for the page",
            "Add config.yml for the settings",
            "Build app.test.mjs with unit tests",
        ],
    )
    def test_an_interchangeable_extension_counts_as_delivered(self, a_project, planned):
        assert files_the_plan_named_that_are_missing([planned], str(a_project)) == [], planned

    def test_a_different_language_is_not_the_same_file(self, a_project):
        """`main.js` exists; a plan asking for `main.py` is not answered by it."""
        problems = files_the_plan_named_that_are_missing(
            ["Add main.py for the service"], str(a_project)
        )

        assert any("main.py" in problem for problem in problems)

    def test_a_genuinely_absent_file_is_still_reported(self, a_project):
        problems = files_the_plan_named_that_are_missing(
            ["Create style.css for the layout"], str(a_project)
        )

        assert any("style.css" in problem for problem in problems)


class TestASuffixPatternIsNotAFile:
    """A plan naming `.spec.ts` means "files ending in this", not a file.

    Found on run-a6b28314, alongside the extension case above. Structurally
    identical to `.env.example`, which is a real file, so this is a list rather
    than a rule - the same mechanism the prose abbreviations use.
    """

    @pytest.mark.parametrize(
        "planned",
        [
            "Add Playwright tests in .spec.ts files",
            "Name unit tests with the .test.mjs suffix",
            "Ship type declarations as .d.ts",
            "Serve the bundle as .min.js",
        ],
    )
    def test_a_suffix_pattern_is_not_reported(self, tmp_path, planned):
        (tmp_path / "placeholder.txt").write_text("x")

        assert files_the_plan_named_that_are_missing([planned], str(tmp_path)) == [], planned

    def test_a_real_dotfile_is_still_read(self, tmp_path):
        """`.env.example` has the same shape and is a file."""
        (tmp_path / "placeholder.txt").write_text("x")

        problems = files_the_plan_named_that_are_missing(
            ["Add .env.example listing the keys"], str(tmp_path)
        )

        assert any(".env.example" in problem for problem in problems)
