"""Files written separately have to refer to each other.

Each specialist writes its own files and each is defensible alone. Nothing
checked whether they connect, and that is where one run's milestone 1
broke: a stylesheet targeting an id no page declared, and a module no page
loaded, both passed four review stages.

Every case below is taken from a defect that actually shipped.
"""

from __future__ import annotations

import json

import pytest

from app.analysis.integration_checks import summarise_integration


def _workspace(tmp_path, files: dict[str, str]):
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return str(tmp_path)


def test_a_stylesheet_targeting_a_missing_id_is_reported(tmp_path):
    """One run: `#app-placeholder` styled, `#app` written."""
    root = _workspace(
        tmp_path,
        {
            "index.html": '<div id="app"></div>',
            "styles.css": "#app-placeholder { width: 100%; }",
        },
    )

    report = summarise_integration(root)

    assert "#app-placeholder" in report
    assert "never applies" in report


def test_a_hex_colour_is_not_an_id_selector(tmp_path):
    """`background-color: #fafafa` is a value, not a selector for `#fafafa`."""
    root = _workspace(
        tmp_path,
        {
            "index.html": '<div id="app"></div>',
            "styles.css": "#app { background-color: #fafafa; color: #fff; }\n"
            "@media (min-width: 768px) { #app { box-shadow: 0 2px 4px #0001; } }",
        },
    )

    report = summarise_integration(root)

    assert "No cross-file problems found" in report


def test_setup_file_imported_in_test_command_is_not_stranded(tmp_path):
    """`--import` flags execute their file so they shouldn't be stranded."""
    root = _workspace(
        tmp_path,
        {
            "package.json": json.dumps(
                {"scripts": {"test": "node --import ./test-setup.mjs --test 'tests/**/*.test.js'"}}
            ),
            "test-setup.mjs": 'import { test } from "node:test";',
            "tests/app.test.js": "import '../test-setup.mjs';"
        },
    )
    report = summarise_integration(root)
    assert "No cross-file problems found" in report


def test_a_script_nothing_loads_is_reported(tmp_path):
    """One run: `script.js` exported a function; no page had a script tag."""
    root = _workspace(
        tmp_path,
        {
            "index.html": "<html><body><div id=\"app\"></div></body></html>",
            "script.js": "export function initTodoApp() {}",
        },
    )

    report = summarise_integration(root)

    assert "script.js is never loaded" in report


def test_a_script_the_page_loads_is_not_reported(tmp_path):
    root = _workspace(
        tmp_path,
        {
            "index.html": '<div id="app"></div><script src="script.js"></script>',
            "script.js": "function init() {}",
        },
    )

    assert "script.js is never loaded" not in summarise_integration(root)


def test_a_script_named_in_package_json_is_referenced(tmp_path):
    """A command in `scripts` is as much a caller as an import is."""
    root = _workspace(
        tmp_path,
        {
            "package.json": '{"scripts": {"lines": "node check_line_count.js"}}',
            "check_line_count.js": "console.log(1);",
        },
    )

    assert "check_line_count.js is never loaded" not in summarise_integration(root)


def test_a_missing_referenced_file_is_reported(tmp_path):
    root = _workspace(
        tmp_path, {"index.html": '<link rel="stylesheet" href="styles.css">'}
    )

    report = summarise_integration(root)

    assert "styles.css" in report
    assert "does not exist" in report


def test_a_remote_reference_is_not_checked(tmp_path):
    root = _workspace(
        tmp_path,
        {"index.html": '<link href="https://fonts.googleapis.com/css2?family=X">'},
    )

    assert "does not exist" not in summarise_integration(root)


def test_esm_source_under_a_commonjs_test_config_is_reported(tmp_path):
    """One run: `export function` with `testEnvironment: 'node'`, no transform."""
    root = _workspace(
        tmp_path,
        {
            "index.html": '<div id="a"></div><script src="script.js"></script>',
            "script.js": "export function initTodoApp() {}",
            "jest.config.js": "module.exports = { testEnvironment: 'node' };",
        },
    )

    report = summarise_integration(root)

    assert "ES module syntax" in report
    # Jest is the one runner here that really cannot read ESM without being
    # configured for it, and this workspace declares a `jest.config.js` with no
    # `transform`. Measured in the worker image on Node 20.20.2, `node --test`
    # reparses the same sources and passes, so the finding is Jest's alone.
    assert "Cannot use import statement outside a module" in report
    assert "transform" in report


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("jest.config.js", "module.exports = { transform: { '^.+\\\\.js$': 'babel-jest' } };"),
        ("package.json", '{"type": "module"}'),
    ],
)
def test_a_declared_module_system_is_accepted(tmp_path, name, content):
    root = _workspace(
        tmp_path,
        {
            "index.html": '<div id="a"></div><script src="script.js"></script>',
            "script.js": "export function initTodoApp() {}",
            name: content,
        },
    )

    assert "ES module syntax" not in summarise_integration(root)


def test_a_test_file_is_not_required_to_be_imported(tmp_path):
    root = _workspace(
        tmp_path, {"__tests__/sample.test.js": "test('x', () => {});"}
    )

    assert "never loaded" not in summarise_integration(root)


def test_node_modules_is_not_scanned(tmp_path):
    root = _workspace(
        tmp_path,
        {
            "index.html": '<div id="a"></div>',
            "node_modules/pkg/index.js": "export const x = 1;",
            "node_modules/pkg/style.css": "#nothing-here { color: red; }",
        },
    )

    report = summarise_integration(root)

    assert "nothing-here" not in report
    assert "node_modules" not in report


def test_an_unreadable_workspace_reports_rather_than_raises():
    assert "no cross-file checks ran" in summarise_integration("/does/not/exist")


def test_an_empty_workspace_says_so(tmp_path):
    assert "No HTML, CSS or JavaScript files" in summarise_integration(str(tmp_path))


def test_the_reviewer_is_given_the_checks(tmp_path):
    from app.agents.milestone_reviewer import build_milestone_review_request

    root = _workspace(
        tmp_path,
        {"index.html": '<div id="app"></div>', "styles.css": "#gone { color: red; }"},
    )
    request = build_milestone_review_request("goal", [], "", "", root)
    brief = request["messages"][0]["content"]

    assert "Cross-file checks" in brief
    assert "#gone" in brief


# --- stack conformance ---------------------------------------------------
#
# Nothing downstream checked the code against the stack the run chose. On
# one run the selection was Python / FastAPI / PostgreSQL / pytest, and
# the project directory held package.json with express and mongoose, a jest
# suite, an index.ts and a FastAPI main.py. Three languages, a MongoDB driver
# against a chosen PostgreSQL, and every test round running jest.

from app.agents.tools_models import TechnologyStack

PY_STACK = TechnologyStack(
    language="Python", framework="FastAPI", frontend_framework="React",
    database="PostgreSQL", testing_framework="pytest",
)


def test_a_second_language_in_the_project_is_reported(tmp_path):
    root = _workspace(tmp_path, {"main.py": "x=1", "package.json": '{"name":"a"}'})

    report = summarise_integration(root, PY_STACK)

    assert "chosen language is Python" in report
    assert "package.json" in report


def test_the_wrong_database_driver_is_reported(tmp_path):
    root = _workspace(
        tmp_path, {"package.json": '{"dependencies":{"mongoose":"^7.0.0"}}'}
    )

    assert "chosen database is PostgreSQL" in summarise_integration(root, PY_STACK)
    assert "mongoose" in summarise_integration(root, PY_STACK)


def test_the_wrong_test_runner_is_reported(tmp_path):
    """Reported by `_a_test_runner_the_stack_did_not_choose`, which names the file.

    `_stack_conflicts` used to report this too, as untidy, so a reviewer got
    one fact twice at two severities. The dedicated check supersedes it for
    JavaScript manifests; Python manifests still go through the generic path.
    """
    root = _workspace(tmp_path, {"package.json": '{"devDependencies":{"jest":"^29"}}'})

    summary = summarise_integration(root, PY_STACK)

    assert "installs 'jest'" in summary
    assert "chose 'pytest'" in summary
    # One finding, not two.
    assert "chosen testing framework is pytest" not in summary


def test_a_runner_whose_name_is_inside_the_chosen_one_is_still_wrong(tmp_path):
    """`"jest" in "pytest"` is true, so substring matching let jest through.

    The stack here chose pytest; jest is not pytest, and a suite written for
    it fails on its own setup rather than on the product.
    """
    root = _workspace(tmp_path, {"package.json": '{"devDependencies":{"jest":"^29"}}'})

    assert "installs 'jest'" in summarise_integration(root, PY_STACK)


def test_the_wrong_backend_framework_is_reported(tmp_path):
    root = _workspace(tmp_path, {"package.json": '{"dependencies":{"express":"^4"}}'})

    assert "chosen framework is FastAPI" in summarise_integration(root, PY_STACK)


def test_the_chosen_frontend_is_not_a_conflicting_framework(tmp_path):
    """React in package.json is the frontend the stack asked for."""
    root = _workspace(tmp_path, {"package.json": '{"dependencies":{"react":"^18"}}'})

    assert "chosen framework is FastAPI" not in summarise_integration(root, PY_STACK)


def test_a_conforming_project_reports_no_stack_conflict(tmp_path):
    root = _workspace(
        tmp_path,
        {
            "main.py": "from fastapi import FastAPI",
            "requirements.txt": "fastapi\npsycopg2\npytest\n",
        },
    )

    report = summarise_integration(root, PY_STACK)

    # On the findings, not on a word: "chosen" also appears in the sentence
    # naming what was checked, so using it as a proxy for a stack-conflict
    # finding made this test pass or fail on the preamble's wording.
    assert "No cross-file problems found." in report


def test_typescript_is_not_a_second_language_in_a_javascript_project(tmp_path):
    """A tsconfig in a JS project is a build choice, not another language."""
    js_stack = TechnologyStack(
        language="JavaScript", framework="Express", database="PostgreSQL",
        testing_framework="jest",
    )
    root = _workspace(tmp_path, {"package.json": "{}", "tsconfig.json": "{}"})

    assert "chosen language" not in summarise_integration(root, js_stack)


def test_no_stack_means_no_conformance_checking(tmp_path):
    """Older runs and fixtures carry no stack selection."""
    root = _workspace(tmp_path, {"package.json": '{"dependencies":{"mongoose":"^7"}}'})

    assert "No cross-file problems found." in summarise_integration(root)


def test_a_missing_stack_component_is_not_reported(tmp_path):
    """An unfinished sprint has not built everything yet; absence is normal."""
    root = _workspace(tmp_path, {"main.py": "from fastapi import FastAPI"})

    report = summarise_integration(root, PY_STACK)

    assert "PostgreSQL" not in report
    assert "pytest" not in report


def test_the_reviewer_is_given_the_stack_conflicts(tmp_path):
    from app.agents.milestone_reviewer import build_milestone_review_request

    root = _workspace(tmp_path, {"package.json": '{"dependencies":{"mongoose":"^7"}}'})
    request = build_milestone_review_request("goal", [], "", "", root, PY_STACK)

    assert "mongoose" in request["messages"][0]["content"]


# --- size against the brief's cap ----------------------------------------
#
# A brief that caps the product - brief_low says "Maximum 500 lines of code" -
# is a constraint no stage ever checked against what was built. One run
# shipped 631 application lines, 391 of them CSS, and passed every review.
# The reviewer holds the brief and can compare; it just needed someone to count.


def test_the_report_counts_the_application(tmp_path):
    root = _workspace(
        tmp_path,
        {"index.html": "<div id='a'></div>\n" * 10, "app.js": "// x\n" * 40},
    )

    report = summarise_integration(root)

    assert "application:" in report
    assert "app.js" in report


def test_tests_are_counted_separately(tmp_path):
    """A cap on "lines of code" almost never means the test suite."""
    root = _workspace(
        tmp_path,
        {
            "index.html": "<div id='a'></div>\n",
            "app.js": "// x\n" * 20,
            "__tests__/a.test.js": "// t\n" * 200,
        },
    )

    report = summarise_integration(root)
    application = report.split("application:")[1].split("\n")[0]

    assert "counted separately" in report
    assert "200" not in application, "test lines must not inflate the application total"


def test_lockfiles_and_bundles_are_not_the_product(tmp_path):
    root = _workspace(
        tmp_path,
        {
            "app.js": "// x\n" * 5,
            "package-lock.json": "{}\n" * 5000,
            "vendor.min.js": "a\n" * 5000,
        },
    )

    report = summarise_integration(root)

    assert "package-lock.json" not in report
    # A vendored bundle is neither the product's size nor an orphaned module.
    assert "vendor.min.js" not in report


def test_a_project_with_no_countable_files_reports_no_size(tmp_path):
    root = _workspace(tmp_path, {"README.md": "# hi"})

    assert "Size of the product" not in summarise_integration(root)


def test_the_reviewer_receives_the_size(tmp_path):
    from app.agents.milestone_reviewer import build_milestone_review_request

    root = _workspace(tmp_path, {"index.html": "<div id='a'></div>\n", "app.js": "// x\n" * 30})
    brief = build_milestone_review_request("goal", [], "", "", root)["messages"][0]["content"]

    assert "Size of the product as built" in brief


# --- manifest claims the project does not support ------------------------
#
# A manifest is read by tooling, by CI and by the next person. When it
# disagrees with the project it sends all three somewhere wrong. Every case
# below shipped in one run, which completed and passed every milestone
# review.


def test_the_npm_placeholder_test_script_is_reported(tmp_path):
    """The exact artefact that cost one run its entire sprint."""
    root = _workspace(
        tmp_path,
        {"package.json": '{"scripts": {"test": "echo \\"Error: no test specified\\" && exit 1"}}'},
    )

    report = summarise_integration(root)

    assert "placeholder test script" in report
    assert "fails by design" in report


def test_a_real_test_script_is_not_reported(tmp_path):
    root = _workspace(tmp_path, {"package.json": '{"scripts": {"test": "node test.js"}}'})

    assert "placeholder test script" not in summarise_integration(root)


def test_a_main_pointing_nowhere_is_reported(tmp_path):
    root = _workspace(tmp_path, {"package.json": '{"main": "index.js"}'})

    report = summarise_integration(root)

    assert '`"main": "index.js"`' in report
    assert "does not exist" in report


def test_a_main_that_exists_is_not_reported(tmp_path):
    root = _workspace(tmp_path, {"package.json": '{"main": "app.js"}', "app.js": "// x"})

    assert '"main"' not in summarise_integration(root)


def test_a_test_package_declared_as_a_runtime_dependency_is_reported(tmp_path):
    """One run shipped jsdom under `dependencies` against a brief that
    rules out external dependencies. The app loaded nothing; the manifest
    claimed otherwise."""
    root = _workspace(
        tmp_path, {"package.json": '{"dependencies": {"jsdom": "^29.1.1"}}'}
    )

    report = summarise_integration(root, PY_STACK)

    assert "jsdom" in report
    assert "belongs in `devDependencies`" in report


def test_a_test_package_the_stack_actually_chose_is_not_reported(tmp_path):
    """If the stack picked jest, jest in the manifest is the plan working."""
    from app.agents.tools_models import TechnologyStack

    stack = TechnologyStack(
        language="JavaScript", framework="Express", database="PostgreSQL",
        testing_framework="jest",
    )
    root = _workspace(tmp_path, {"package.json": '{"dependencies": {"jest": "^29"}}'})

    assert "belongs in `devDependencies`" not in summarise_integration(root, stack)


def test_devdependencies_are_left_alone(tmp_path):
    root = _workspace(tmp_path, {"package.json": '{"devDependencies": {"jsdom": "^29"}}'})

    assert "belongs in `devDependencies`" not in summarise_integration(root, PY_STACK)


def test_an_unparseable_manifest_is_reported_not_raised(tmp_path):
    root = _workspace(tmp_path, {"package.json": "{not json"})

    report = summarise_integration(root)

    assert "not valid JSON" in report


@pytest.mark.parametrize(
    "package", ["linkedom", "happy-dom", "supertest", "playwright", "c8", "msw"]
)
def test_more_test_packages_are_recognised_as_dev_only(tmp_path, package):
    """A list of known names only covers the names on it.

    One run's milestone reviewer found `linkedom` declared as a production
    dependency and this check did not, because the name was not listed. The
    list grows when a run shows a gap.
    """
    root = _workspace(tmp_path, {"package.json": '{"dependencies": {"%s": "^1"}}' % package})

    report = summarise_integration(root, PY_STACK)

    assert package in report
    assert "belongs in `devDependencies`" in report


# --- a probe left behind is not the product -------------------------------


def test_a_script_nothing_loads_is_not_counted_as_the_application(tmp_path):
    """The size report is the one number a reviewer judges the brief against.

    Measured on one run, against a brief capping the product at 500 lines:
    the report said 901, of which 447 were `verify-milestone.mjs` and three
    abandoned cleanup scripts. The application was 454 - inside the cap. The
    reviewer would have been shown nearly double it.
    """
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><script src="app.js"></script></body></html>',
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text("\n".join(f"// line {i}" for i in range(40)), encoding="utf-8")
    (tmp_path / "verify-milestone.mjs").write_text(
        "\n".join(f"// probe {i}" for i in range(300)), encoding="utf-8"
    )

    summary = summarise_integration(str(tmp_path))

    assert "application: 41 lines across 2 file(s)" in summary
    assert "not counted: 300 lines across 1 file(s) nothing loads" in summary
    assert "verify-milestone.mjs" in summary


def test_the_orphan_list_and_the_size_report_cannot_disagree(tmp_path):
    """Both read the same set, so a file cannot be an orphan in one and part of
    the product in the other."""
    from app.analysis.integration_checks import _orphaned_scripts, summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text("// app\n", encoding="utf-8")
    (tmp_path / "stray.mjs").write_text("// stray\n", encoding="utf-8")

    from pathlib import Path as _Path

    orphans = _orphaned_scripts(sorted(tmp_path.iterdir()), _Path(tmp_path))
    summary = summarise_integration(str(tmp_path))

    assert orphans == ["stray.mjs"]
    assert "stray.mjs is never loaded" in summary
    assert "not counted: 2 lines across 1 file(s)" in summary


def test_a_product_with_no_strays_reports_no_extra_bucket(tmp_path):
    """The line must not appear when there is nothing to say."""
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text("// app\n", encoding="utf-8")

    summary = summarise_integration(str(tmp_path))

    assert "not counted:" not in summary


# --- a test that copies the code instead of importing it ------------------


def test_a_test_that_redefines_the_code_is_reported(tmp_path):
    """A green suite that proves nothing.

    Measured on one run: `app.js` called `init()` at module scope, so the
    testing specialist wrote "it cannot be directly imported in a headless Node
    environment. Instead, this test file defines the same pure logic functions
    inline" - and six tests passed against a copy.
    """
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text(
        "function createTask(t){ return {t}; }\nfunction init(){}\ninit();\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/logic.test.js").write_text(
        "import {it} from 'node:test';\nimport assert from 'node:assert/strict';\n"
        "function createTask(t){ return {t}; }\n",
        encoding="utf-8",
    )

    summary = summarise_integration(str(tmp_path))

    assert "defines createTask itself" in summary
    assert "tests a copy" in summary


def test_a_test_that_imports_the_real_module_is_not_reported(tmp_path):
    """Importing the application and also defining a helper is deliberate."""
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text("export function createTask(t){ return {t}; }\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/logic.test.js").write_text(
        "import {createTask} from '../app.js';\nfunction createTask(t){}\n", encoding="utf-8"
    )

    assert "tests a copy" not in summarise_integration(str(tmp_path))


def test_a_builtin_import_does_not_count_as_reaching_the_application(tmp_path):
    """`node:assert/strict` contains a slash and is not the product. Treating it
    as an application import made the first version of this check silent on the
    very file it was written for."""
    from app.analysis.integration_checks import _redefined_instead_of_imported

    (tmp_path / "app.js").write_text("function createTask(t){}\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/a.test.js").write_text(
        "import assert from 'node:assert/strict';\nfunction createTask(t){}\n", encoding="utf-8"
    )

    problems = _redefined_instead_of_imported(sorted(tmp_path.rglob("*.js")), tmp_path)

    assert problems and "createTask" in problems[0]


def test_a_test_named_with_a_prefix_is_still_a_test(tmp_path):
    """`test-contract.js` was read as application code and reported as an
    orphaned script "nothing runs" - it is run by `node --test`."""
    from app.analysis.file_kinds import is_application

    assert not is_application("proj/test-contract.js")
    assert not is_application("proj/test_helpers.js")
    assert is_application("proj/app.js")
    assert is_application("proj/latest-news.js")


# --- "lines of code" is not "lines of file" -------------------------------


def test_the_report_separates_code_from_blank_and_comment(tmp_path):
    """A brief capping "lines of code" means the code lines.

    Reporting only the raw count left the reviewer comparing a number against a
    limit that means something else: on one run nothing could say whether
    609 raw lines broke a 500-line cap. They did not - 315 of them were code.
    """
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text(
        "// a comment\n"
        "\n"
        "function createTask(t){\n"
        "    return t;\n"
        "}\n"
        "/* a block\n"
        "   that runs on */\n"
        "const x = 1;\n",
        encoding="utf-8",
    )

    summary = summarise_integration(str(tmp_path))

    assert "of them code (neither blank nor comment)" in summary


def test_comment_and_blank_lines_are_not_code(tmp_path):
    from app.analysis.integration_checks import _code_lines

    source = (
        "// line comment\n"
        "\n"
        "   \n"
        "function a(){}\n"
        "/* block\n"
        "   continues\n"
        "   ends */\n"
        "const b = 2;\n"
        "# python style\n"
    )

    assert _code_lines(source) == 2


def test_an_html_comment_is_not_code():
    from app.analysis.integration_checks import _code_lines

    source = "<!doctype html>\n<!-- a note\n     over lines -->\n<div></div>\n"

    assert _code_lines(source) == 2


def test_a_single_line_block_comment_does_not_swallow_the_file():
    """An unterminated-block bug here would report almost nothing as code."""
    from app.analysis.integration_checks import _code_lines

    source = "/* one line */\nconst a = 1;\nconst b = 2;\n"

    assert _code_lines(source) == 2


def test_an_empty_file_has_no_code():
    from app.analysis.integration_checks import _code_lines

    assert _code_lines("") == 0
    assert _code_lines("\n\n   \n") == 0


# --- an application no runner can open ------------------------------------


def test_an_application_embedded_in_html_is_reported(tmp_path):
    """A test can only import a file. Logic inside a `<script>` tag can only be
    tested by copying it, which produces exactly the green-but-meaningless
    suite reported elsewhere - one step earlier, and for a reason nobody can
    fix after the fact.

    Measured on one run: a specification describing pure functions, a
    storage adapter and an `init()` - correctly - with all of it placed in a
    single `index.html`, "No external files, no build step, no module system".
    """
    from app.analysis.integration_checks import summarise_integration

    body = "\n".join(f"  const x{i} = {i};" for i in range(40))
    (tmp_path / "index.html").write_text(
        f"<!doctype html><html><body><script>\n{body}\n</script></body></html>",
        encoding="utf-8",
    )

    summary = summarise_integration(str(tmp_path))

    assert "No test runner can import it" in summary
    assert "<script src>" in summary


def test_a_page_that_loads_a_script_file_is_left_alone(tmp_path):
    """The file it loads is what tests will import; a bootstrap line beside it
    is not the application."""
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script><script>init();</script>',
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text("export function init(){}\n", encoding="utf-8")

    assert "No test runner can import it" not in summarise_integration(str(tmp_path))


def test_a_small_inline_script_is_not_an_application(tmp_path):
    """A bootstrap or an analytics snippet must not be reported as the product."""
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        "<!doctype html><script>\nconsole.log('hi');\n</script>", encoding="utf-8"
    )

    assert "No test runner can import it" not in summarise_integration(str(tmp_path))


def test_an_undeclared_module_type_is_not_a_finding_on_this_runtime(tmp_path):
    """Node reparses a typeless `.js` that uses module syntax, and always did here.

    This check used to fire on any ESM source with no declared module type and
    tell the stage its exports were "invisible". Measured directly in the
    worker image on Node 20.20.2 - a `{"name":"p"}` manifest, `app.js` with
    `export function addTask(...)`, and a test importing it by name - the suite
    reports `# tests 1 # pass 1 # fail 0`. Node has detected module syntax in a
    typeless `.js` since 20.19.

    The original evidence from one run was the *agent's* note in its own
    test file, "we can't directly import app.js", recorded here as Node's
    behaviour. It was the agent's misdiagnosis, and the check enshrined it.

    A check that is wrong costs more than one that is missing: this one raised
    a blocking finding against a working project. What is genuinely broken in
    this workspace - `export` behind a classic `<script>` tag - is
    `_modules_loaded_as_plain_scripts`, which is still reported.
    """
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text(
        "function createTask(t){ return t; }\nexport { createTask };\n", encoding="utf-8"
    )

    summary = summarise_integration(str(tmp_path))

    assert "Cannot use import statement outside a module" not in summary
    assert "loads them as CommonJS" not in summary
    # The real defect in these two files is still named.
    assert "plain <script> tag" in summary


def test_a_declared_module_type_clears_it(tmp_path):
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text("export function a(){}\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")

    assert "does not provide an export named" not in summarise_integration(str(tmp_path))


@pytest.mark.parametrize(
    "name",
    ["a.test.mjs", "a.test.cjs", "a.spec.mjs", "test-contract.mjs", "tests/x.test.mjs"],
)
def test_an_mjs_test_is_a_test(name: str):
    """`.mjs` is how a project declares ESM without a package.json, so it is
    exactly what a testable design produces - and the pattern matched only
    `.js`, so those files were reported as orphaned probes nothing runs.

    Measured on one run: the two files that proved the copy-test fix had
    worked were the two the report told the reviewer to delete.
    """
    from app.analysis.file_kinds import is_application

    assert not is_application(name)


@pytest.mark.parametrize("name", ["app.mjs", "app.js", "latest-news.js"])
def test_an_mjs_application_file_is_not_a_test(name: str):
    from app.analysis.file_kinds import is_application

    assert is_application(name)


# --- a stylesheet rule nothing ever applies --------------------------------


def test_a_class_nothing_applies_is_reported(tmp_path):
    """Found on one run's second sprint by a reviewer reading three files
    against each other: `.task-text` and `.empty-message` were styled and used
    by nothing."""
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><div class="task-item"></div><script src="app.js"></script>',
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text("const item = 'task-item';\n", encoding="utf-8")
    (tmp_path / "style.css").write_text(
        ".task-item { color: red; }\n.empty-message { display: none; }\n", encoding="utf-8"
    )

    summary = summarise_integration(str(tmp_path))

    assert ".empty-message" in summary
    assert ".task-item" not in summary.split("styles")[-1].split(",")[0]


def test_a_class_added_at_runtime_is_not_reported(tmp_path):
    """Unlike an id, a class is often applied by script - so any mention of the
    word anywhere in the code counts, however it is built."""
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text(
        "button.classList.add('selected');\nel.className = `row ${'striped'}`;\n",
        encoding="utf-8",
    )
    (tmp_path / "style.css").write_text(
        ".selected { color: red; }\n.striped { background: grey; }\n", encoding="utf-8"
    )

    assert "no page or script ever puts" not in summarise_integration(str(tmp_path))


def test_the_check_is_conservative_about_common_words(tmp_path):
    """A word used for another reason keeps its rule. On one run `.active`
    was genuinely dead, and this check correctly left it alone because "active"
    is one of that product's filter names - the reviewer caught it instead."""
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text(
        "const filters = ['all', 'active', 'completed'];\n", encoding="utf-8"
    )
    (tmp_path / "style.css").write_text("button.active { color: blue; }\n", encoding="utf-8")

    assert "no page or script ever puts" not in summarise_integration(str(tmp_path))


# --- instructions and manifests that do not match the project --------------


def test_a_document_naming_a_file_that_does_not_exist_is_reported(tmp_path):
    """A document is the one artefact nobody executes, so a wrong instruction
    survives every test round and reaches whoever tries to use the product.

    Measured on one run: `docs/deployment.md` said "Run with
    `node server.js`" for a project containing app.js, app.test.mjs,
    index.html, package.json and style.css. Four milestone reviews read that
    document and none tried the command.
    """
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text("export const a = 1;\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/deployment.md").write_text(
        "Run with `node server.js`, then open http://localhost:3000.\n", encoding="utf-8"
    )

    summary = summarise_integration(str(tmp_path))

    assert "tells a reader to run `server.js`" in summary


def test_a_document_naming_a_file_that_exists_is_not_reported(tmp_path):
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text("export const a = 1;\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/readme.md").write_text("Run `node app.js` to start.\n", encoding="utf-8")

    assert "tells a reader to run" not in summarise_integration(str(tmp_path))


def test_prose_about_a_command_is_not_a_command(tmp_path):
    """Only a bare filename inside a code span counts, so discussion of a
    hypothetical server is left alone."""
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text("export const a = 1;\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/notes.md").write_text(
        "A future version might ship a server.js and be run with node.\n", encoding="utf-8"
    )

    assert "tells a reader to run" not in summarise_integration(str(tmp_path))


def test_tests_with_no_way_to_run_them_are_reported(tmp_path):
    """153 passing tests and `npm test` answering "missing script: test"."""
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text("export const a = 1;\n", encoding="utf-8")
    (tmp_path / "app.test.mjs").write_text("import {a} from './app.js';\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")

    summary = summarise_integration(str(tmp_path))

    assert "declares no `test` script" in summary


def test_a_manifest_with_a_test_script_is_not_reported(tmp_path):
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text("export const a = 1;\n", encoding="utf-8")
    (tmp_path / "app.test.mjs").write_text("import {a} from './app.js';\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"type": "module", "scripts": {"test": "node --test"}}\n', encoding="utf-8"
    )

    assert "declares no `test` script" not in summarise_integration(str(tmp_path))


def test_a_project_with_no_tests_is_not_asked_for_a_test_script(tmp_path):
    """Absent tests are a different finding with a different remedy."""
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text("export const a = 1;\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")

    assert "declares no `test` script" not in summarise_integration(str(tmp_path))


def test_importing_a_module_and_shadowing_its_exports_is_still_a_copy(tmp_path):
    """The defect wearing an import.

    Measured on one run: `script.test.mjs` opened with "Inline copies of
    the pure functions (mirrors script.js exactly)", ran every behavioural
    assertion against those copies, and closed with nine tests that did import
    the real module - to assert `typeof mod.addTask === 'function'` and nothing
    more. The rule exempted any file holding a relative import, so it was
    silent on a suite bound to the application by existence checks alone.
    """
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script type="module" src="script.js"></script>',
        encoding="utf-8",
    )
    (tmp_path / "script.js").write_text(
        "export function addTask(t){ return {t}; }\n", encoding="utf-8"
    )
    (tmp_path / "script.test.mjs").write_text(
        "import {it} from 'node:test';\n"
        "import assert from 'node:assert/strict';\n"
        "function addTask(t){ return {t}; }\n"
        "it('adds', () => { assert.ok(addTask('a')); });\n"
        "it('exports addTask', async () => {\n"
        "  const mod = await import('./script.js');\n"
        "  assert.strictEqual(typeof mod.addTask, 'function');\n"
        "});\n",
        encoding="utf-8",
    )

    summary = summarise_integration(str(tmp_path))

    assert "defines addTask itself" in summary
    assert "tests a copy" in summary
    assert "not these names" in summary


def test_a_name_reached_through_the_imported_namespace_is_not_a_copy(tmp_path):
    """`const mod = await import('./script.js')` then `mod.addTask(...)`.

    The lookbehind in the call check drops anything reached through an object,
    so a suite that only ever spells the name that way is left alone.
    """
    from app.analysis.integration_checks import _redefined_instead_of_imported

    (tmp_path / "script.js").write_text(
        "export function addTask(t){ return {t}; }\n", encoding="utf-8"
    )
    (tmp_path / "script.test.mjs").write_text(
        "import {it} from 'node:test';\n"
        "const mod = await import('./script.js');\n"
        "it('adds', () => { mod.addTask('a'); });\n",
        encoding="utf-8",
    )

    assert not _redefined_instead_of_imported(
        sorted(tmp_path.rglob("*")), tmp_path
    )


def test_a_renamed_import_binds_the_name_on_the_right(tmp_path):
    """`import {addTask as make}` binds `make`, and `make` is what the tests
    call. A local `addTask` alongside it is then genuinely unused by them."""
    from app.analysis.integration_checks import _names_bound_from_a_relative_module

    bound = _names_bound_from_a_relative_module(
        "import {addTask as make, deleteTask} from './script.js';\n"
        "import * as everything from './other.js';\n"
        "const {loadTasks} = await import('./store.js');\n"
        "import assert from 'node:assert/strict';\n"
    )

    assert bound == {"make", "deleteTask", "everything", "loadTasks"}
    assert "addTask" not in bound
    assert "assert" not in bound


# --- the cap the brief states, actually checked --------------------------


def test_a_product_over_its_declared_budget_is_reported(tmp_path):
    """The comparison the harness had both operands for and did not make.

    Measured on one run: the milestone review was handed `550 of them
    code`, directly under a sentence saying that is the number a cap means. The
    cap appears six times in that run's own documents, once as the acceptance
    criterion "Total source code stays within the 500-line limit". The review
    accepted the milestone with two findings, neither about size, and the
    sprint was tagged.
    """
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/product_intake.md").write_text(
        "- Maximum 500 lines of code\n- Total source code stays within the "
        "500-line limit\n",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (tmp_path / "app.js").write_text(
        "export function a(x){ return x; }\n" * 600, encoding="utf-8"
    )
    (tmp_path / "index.html").write_text(
        '<!doctype html><script type="module" src="app.js"></script>', encoding="utf-8"
    )

    summary = summarise_integration(str(tmp_path))

    assert "against the 500-line maximum" in summary
    assert "101 over" in summary, summary


def test_a_product_inside_its_budget_says_nothing(tmp_path):
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/product_intake.md").write_text(
        "Maximum 500 lines of code\n", encoding="utf-8"
    )
    (tmp_path / "app.js").write_text("export function a(x){ return x; }\n" * 10, encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><script type="module" src="app.js"></script>', encoding="utf-8"
    )

    assert "maximum this project" not in summarise_integration(str(tmp_path))


def test_tests_do_not_count_against_the_product_budget(tmp_path):
    """A brief capping "lines of code" does not mean the suite. One run
    was 631 lines of application and 1,558 of tests the round had installed."""
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/intake.md").write_text("Maximum 500 lines of code\n", encoding="utf-8")
    (tmp_path / "app.js").write_text("export function a(x){ return x; }\n" * 50, encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><script type="module" src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.test.mjs").write_text(
        "import {a} from './app.js';\n" + "// a test line\n" * 900, encoding="utf-8"
    )

    assert "maximum this project" not in summarise_integration(str(tmp_path))


def test_a_workspace_that_states_no_budget_is_not_judged(tmp_path):
    from app.analysis.integration_checks import _declared_line_budget

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/intake.md").write_text("Build a to-do list.\n", encoding="utf-8")

    assert _declared_line_budget(tmp_path) is None


def test_both_spellings_the_workflow_writes_are_recognised(tmp_path):
    from app.analysis.integration_checks import _declared_line_budget

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/a.md").write_text("Maximum 500 lines of code\n", encoding="utf-8")
    assert _declared_line_budget(tmp_path) == 500

    (tmp_path / "docs/a.md").write_text("stays within the 400-line limit\n", encoding="utf-8")
    assert _declared_line_budget(tmp_path) == 400


def test_one_passing_mention_cannot_move_the_budget(tmp_path):
    """The most frequently stated number wins, ties to the smallest."""
    from app.analysis.integration_checks import _declared_line_budget

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/intake.md").write_text(
        "Maximum 500 lines of code\n"
        "Total source code stays within the 500-line limit\n"
        "A 5000-line limit would be typical of a larger product.\n",
        encoding="utf-8",
    )

    assert _declared_line_budget(tmp_path) == 500


def test_the_budget_check_and_the_size_report_count_the_same_lines(tmp_path):
    """Finding 06 was these two disagreeing: a size report counting abandoned
    probe scripts as product while the orphan check, in the same report, named
    them as strays."""
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/intake.md").write_text("Maximum 100 lines of code\n", encoding="utf-8")
    (tmp_path / "app.js").write_text("export function a(x){ return x; }\n" * 40, encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><script type="module" src="app.js"></script>', encoding="utf-8"
    )
    # A probe nothing loads: counted by neither.
    (tmp_path / "verify-milestone.mjs").write_text("console.log(1);\n" * 500, encoding="utf-8")

    summary = summarise_integration(str(tmp_path))

    # 40 lines of app + 1 of html is under 100, and the 500-line probe must not
    # drag it over.
    assert "maximum this project" not in summary


# --- a test that only passes from one directory ---------------------------


def test_a_test_that_opens_a_cwd_relative_path_is_reported(tmp_path):
    """The defect that passes every check the workflow makes.

    On one run the suite read `'./todo-app/index.html'`, and the test
    round ran `node --test todo-app/app.test.mjs` from the workspace root,
    where that resolves. It passed eight times. From inside the project
    directory - which is where anyone handed the project runs it - every test
    fails with ENOENT.

    One run hit the same shape with `path.resolve('./script.js')`, the
    test round happened to run from the other directory, the tests failed, and
    a defect-fix round corrected it. The difference between a caught defect and
    a shipped one was which directory the command happened to use.
    """
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "app.js").write_text("export function a(){}\n", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><script type="module" src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.test.mjs").write_text(
        "import {readFileSync} from 'node:fs';\n"
        "const page = readFileSync('./todo-app/index.html', 'utf-8');\n",
        encoding="utf-8",
    )

    summary = summarise_integration(str(tmp_path))

    assert "relative to whatever directory it is run from" in summary
    assert "import.meta.url" in summary


def test_a_path_anchored_to_the_test_file_is_left_alone(tmp_path):
    """19 of the 20 delivered test files do this correctly; the check must not
    report them."""
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "app.js").write_text("export function a(){}\n", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><script type="module" src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.test.mjs").write_text(
        "import {readFileSync} from 'node:fs';\n"
        "import {fileURLToPath} from 'node:url';\n"
        "import {dirname, join} from 'node:path';\n"
        "const here = dirname(fileURLToPath(import.meta.url));\n"
        "const page = readFileSync(join(here, 'index.html'), 'utf-8');\n",
        encoding="utf-8",
    )

    assert "relative to whatever directory" not in summarise_integration(str(tmp_path))


def test_application_code_is_not_reported(tmp_path):
    """Only tests. Application code reading a relative path is its own
    business and runs from wherever the page loads it."""
    from app.analysis.integration_checks import _tests_that_depend_on_the_working_directory

    (tmp_path / "app.js").write_text(
        "import {readFileSync} from 'node:fs';\n"
        "const x = readFileSync('./data/seed.json');\n",
        encoding="utf-8",
    )

    assert not _tests_that_depend_on_the_working_directory(
        sorted(tmp_path.rglob("*")), tmp_path
    )


def test_a_referenced_file_that_is_empty_is_reported(tmp_path):
    """Present but empty is not the same as present.

    A page that links an empty stylesheet renders unstyled and a page that
    loads an empty script does nothing. Both look correct to a check that only
    asks whether the file is there.

    Measured on one run: index.html linked `style.css` on line 6, the file
    was zero bytes, the reference check passed, and the size report counted it
    as one line of the product.
    """
    from app.analysis.integration_checks import _broken_local_references, _source_files

    (tmp_path / "p").mkdir()
    (tmp_path / "p/index.html").write_text(
        '<link rel="stylesheet" href="style.css">\n<script src="app.js"></script>',
        encoding="utf-8",
    )
    (tmp_path / "p/style.css").write_text("", encoding="utf-8")
    (tmp_path / "p/app.js").write_text("const a = 1;\n", encoding="utf-8")

    problems = _broken_local_references(_source_files(tmp_path), tmp_path)

    assert any("exists but is empty" in p and "style.css" in p for p in problems)
    assert not any("app.js" in p for p in problems)


def test_whitespace_only_counts_as_empty(tmp_path):
    from app.analysis.integration_checks import _broken_local_references, _source_files

    (tmp_path / "p").mkdir()
    (tmp_path / "p/index.html").write_text('<link href="a.css" rel="stylesheet">', encoding="utf-8")
    (tmp_path / "p/a.css").write_text("\n\n   \n", encoding="utf-8")

    problems = _broken_local_references(_source_files(tmp_path), tmp_path)

    assert any("exists but is empty" in p for p in problems)


def test_a_missing_file_is_still_reported_as_missing(tmp_path):
    """The two are different problems and must not be merged."""
    from app.analysis.integration_checks import _broken_local_references, _source_files

    (tmp_path / "p").mkdir()
    (tmp_path / "p/index.html").write_text('<link href="gone.css" rel="stylesheet">', encoding="utf-8")

    problems = _broken_local_references(_source_files(tmp_path), tmp_path)

    assert any("does not exist" in p for p in problems)
    assert not any("exists but is empty" in p for p in problems)


# ---------------------------------------------------------------------------
# The Playwright presence check, narrowed 2026-09-19. It fired on a fixture of
# one `<div>` and one stylesheet: no JavaScript, no manifest, nothing a browser
# test could assert on, and a remedy ("install it in package.json") naming a
# file that did not exist.
# ---------------------------------------------------------------------------


def test_a_static_page_is_not_asked_for_a_browser_test(tmp_path):
    """Markup and styling have no behaviour to regression-test."""
    root = _workspace(
        tmp_path,
        {
            "index.html": '<div id="app">hello</div>',
            "styles.css": "#app { color: #fff; }",
        },
    )

    # On the finding, not the word: the report preamble lists every check
    # that ran, "presence of Playwright for UI testing" among them.
    assert "Playwright is not installed" not in summarise_integration(root)


def test_a_project_with_no_manifest_is_not_told_to_edit_one(tmp_path):
    """"Not installed in package.json" cannot be acted on without one."""
    root = _workspace(
        tmp_path,
        {
            "index.html": '<div id="app"></div><script src="app.js"></script>',
            "app.js": "document.getElementById('app').textContent = 'hi';",
        },
    )

    # On the finding, not the word: the report preamble lists every check
    # that ran, "presence of Playwright for UI testing" among them.
    assert "Playwright is not installed" not in summarise_integration(root)


def test_a_ui_with_logic_and_a_manifest_is_still_asked_for_one(tmp_path):
    """The case the check was written for must survive the narrowing."""
    root = _workspace(
        tmp_path,
        {
            "index.html": '<div id="app"></div><script type="module" src="app.js"></script>',
            "app.js": "export function go() { document.getElementById('app'); }",
            "package.json": '{"name": "a", "version": "1.0.0", "type": "module"}',
        },
    )

    assert "Playwright is not installed" in summarise_integration(root)


def test_a_ui_that_already_has_playwright_is_left_alone(tmp_path):
    root = _workspace(
        tmp_path,
        {
            "index.html": '<div id="app"></div><script type="module" src="app.js"></script>',
            "app.js": "export function go() { document.getElementById('app'); }",
            "package.json": '{"name": "a", "version": "1.0.0", "type": "module",'
                            ' "devDependencies": {"@playwright/test": "^1.0.0"}}',
        },
    )

    assert "Playwright is not installed" not in summarise_integration(root)


# ---------------------------------------------------------------------------
# A suite the gating command cannot run at all.
#
# Measured on one run, which COMPLETED. Its `scripts.test` is
# `node --test tests/` and collected 34 passing tests, while
# `tests/app.test.ts` held five Playwright tests reachable only through
# `scripts["test:e2e"]`. No stage in this pipeline runs anything but
# `scripts.test`, so those five never ran at a gate, and every review read
# "# pass 34  # fail 0" as evidence the UI works. Run directly afterwards,
# all five failed.
#
# `_tests_the_project_never_runs` could not see them: it considered only
# `.js`, `.mjs` and `.cjs`. A `.ts` suite the command does not collect is
# stranded by design, and the design is what needed reporting. (Node 24 runs
# TypeScript it collects, with the types stripped; JSX it cannot load at all.)
# ---------------------------------------------------------------------------

#: The unit command as it reads on Node 24, which refuses a directory argument.
_UNIT_PATTERN = "node --test 'tests/**/*.test.mjs'"


def test_a_typescript_suite_the_test_command_cannot_run_is_reported(tmp_path):
    root = _workspace(
        tmp_path,
        {
            "package.json": json.dumps({"name": "a", "version": "1.0.0", "scripts": {
                "test": _UNIT_PATTERN, "test:e2e": "npx playwright test"}}),
            "app.js": "export function go() { return 1; }\n",
            "tests/unit.test.mjs": "import {test} from 'node:test';\ntest('x',()=>{});\n",
            "tests/app.test.ts": "import { test } from '@playwright/test';\ntest('ui', async () => {});\n",
        },
    )

    report = summarise_integration(root)

    assert "which never runs" in report
    assert "app.test.ts" in report
    assert "test:e2e" in report, "the message must name the script that does run it"


def test_it_says_when_nothing_runs_the_suite_at_all(tmp_path):
    root = _workspace(
        tmp_path,
        {
            "package.json": json.dumps({"name": "a", "version": "1.0.0", "scripts": {"test": _UNIT_PATTERN}}),
            "app.js": "export function go() { return 1; }\n",
            "tests/app.test.ts": "import { test } from '@playwright/test';\ntest('ui', async () => {});\n",
        },
    )

    assert "Nothing in the project runs them at all" in summarise_integration(root)


def test_typescript_the_command_collects_is_not_reported(tmp_path):
    """Measured in the run image on Node 24.21: a bare `node --test` ran
    `tests/f.test.ts` (`# pass 1`), so a suite in TypeScript that the command
    collects is not stranded."""
    root = _workspace(
        tmp_path,
        {
            "package.json": json.dumps({"name": "a", "version": "1.0.0", "scripts": {"test": "node --test"}}),
            "app.js": "export function go() { return 1; }\n",
            "tests/app.test.ts": "import { test } from 'node:test';\nimport assert from 'node:assert';\n"
                                 "const n: number = 1;\ntest('x', () => assert.equal(n, 1));\n",
        },
    )

    from app.analysis.integration_checks import _source_files, _tests_the_project_never_runs

    assert _tests_the_project_never_runs(_source_files(root), root) == []


def test_jsx_is_never_run_by_node(tmp_path):
    """Node 24 stops at ERR_UNKNOWN_FILE_EXTENSION on `.tsx`, however it is named."""
    root = _workspace(
        tmp_path,
        {
            "package.json": json.dumps({"name": "a", "version": "1.0.0", "scripts": {"test": "node --test"}}),
            "app.js": "export function go() { return 1; }\n",
            "tests/view.test.tsx": "import { test } from 'node:test';\ntest('x', () => {});\n",
        },
    )

    report = summarise_integration(root)

    assert "view.test.tsx" in report
    assert "cannot load JSX" in report


def test_an_all_javascript_project_is_not_newly_flagged(tmp_path):
    """The check must not start reporting projects that were always fine."""
    root = _workspace(
        tmp_path,
        {
            "package.json": '{"name":"a","version":"1.0.0","scripts":{"test":"node --test"}}',
            "app.js": "export function go() { return 1; }\n",
            "tests/unit.test.mjs": "import {test} from 'node:test';\ntest('x',()=>{});\n",
        },
    )

    assert "does not parse TypeScript" not in summarise_integration(root)


def test_a_jest_project_decides_its_own_discovery(tmp_path):
    """Jest and Vitest read their own config; a claim here would be a guess."""
    root = _workspace(
        tmp_path,
        {
            "package.json": '{"name":"a","version":"1.0.0","scripts":{"test":"jest"}}',
            "app.js": "export function go() { return 1; }\n",
            "tests/app.test.ts": "test('ui', () => {});\n",
        },
    )

    assert "does not parse TypeScript" not in summarise_integration(root)


def test_the_stranded_typescript_suite_blocks(tmp_path):
    """A suite no gate runs is a false green, and a false green must block.

    Classified untidy at first, for want of a phrase in `_BREAKS_BEHAVIOUR`.
    One run COMPLETED with five Playwright tests that had never executed
    once, and all five failed when run afterwards.
    """
    root = _workspace(
        tmp_path,
        {
            "package.json": '{"name":"a","version":"1.0.0",'
                            '"scripts":{"test":"node --test tests/",'
                            '"test:e2e":"npx playwright test"}}',
            "app.js": "export function go() { return 1; }\n",
            "tests/unit.test.mjs": "import {test} from 'node:test';\ntest('x',()=>{});\n",
            "tests/app.test.ts": "import { test } from '@playwright/test';\ntest('ui', async () => {});\n",
        },
    )

    assert "a feature DOES NOT WORK" in summarise_integration(root)


def test_every_blocking_marker_still_appears_in_a_real_message():
    """Blocking is decided by exact phrases, so a reworded message downgrades
    a check in silence.

    This is the stale-marker failure twice over in one session: the audit
    script matched one of two read-repeat wordings and reported zero, and the
    stranded-TypeScript finding was classified untidy because its phrase was
    not in the tuple. A phrase that no check can produce any more is the
    warning sign for both.
    """
    import pathlib
    import re

    from app.analysis.integration_checks import _BREAKS_BEHAVIOUR

    source = pathlib.Path("src/app/analysis/integration_checks.py").read_text(
        encoding="utf-8"
    )
    # Adjacent string literals are one string at runtime.
    joined = re.sub(r"[\"']\s*\n\s*(?:f)?[\"']", "", source)

    orphans = [m for m in _BREAKS_BEHAVIOUR if m not in joined]
    assert not orphans, (
        "these phrases mark a finding as blocking and no check produces them "
        f"any more, so whatever replaced them is now merely untidy: {orphans}"
    )


# ---------------------------------------------------------------------------
# A blocking finding against a suite that demonstrably passes, whose remedy
# would have broken it.
#
# Measured live on one run. `task-manager/app.spec.js` opens
#
#     import { test, expect } from '@playwright/test';
#
# and passes 24 of 24 under `npx playwright test`. The check called it a file
# where "every case throws ReferenceError: test is not defined", blocked the
# sprint on it, and advised adding `import { test } from 'node:test'` - which
# would have broken the working suite.
#
# It matched only `node:test`, so every runner that exports its helpers
# rather than injecting them was invisible. The question is whether the name
# is bound when the file runs; which module bound it does not change the
# answer.
# ---------------------------------------------------------------------------


def test_a_playwright_spec_is_not_told_its_import_is_missing(tmp_path):
    root = _workspace(
        tmp_path,
        {
            "package.json": '{"name":"a","version":"1.0.0",'
                            '"scripts":{"test":"npx playwright test"},'
                            '"devDependencies":{"@playwright/test":"^1.0.0"}}',
            "app.js": "export function go() { return 1; }\n",
            "app.spec.js": "import { test, expect } from '@playwright/test';\n"
                           "test('ui', async ({ page }) => { await page.goto('/'); });\n",
        },
    )

    assert "app.spec.js calls" not in summarise_integration(root)


@pytest.mark.parametrize(
    "header",
    [
        "import { test, expect } from '@playwright/test';",
        "import { test } from 'node:test';",
        "import test from 'ava';",
        "const { test } = require('node:test');",
        "import { test as check } from 'vitest';",
    ],
)
def test_the_name_imported_from_anywhere_counts(tmp_path, header):
    root = _workspace(
        tmp_path,
        {
            "package.json": '{"name":"a","version":"1.0.0","scripts":{"test":"node --test"}}',
            "app.js": "export function go() { return 1; }\n",
            "app.test.js": f"{header}\ntest('x', () => {{}});\n",
        },
    )

    assert "and nothing imports" not in summarise_integration(root)


def test_a_file_that_really_imports_nothing_is_still_reported(tmp_path):
    """The true positive must survive: this one genuinely throws."""
    root = _workspace(
        tmp_path,
        {
            "package.json": '{"name":"a","version":"1.0.0","scripts":{"test":"node --test"}}',
            "app.js": "export function go() { return 1; }\n",
            "app.test.js": "test('x', () => {});\n",
        },
    )

    report = summarise_integration(root)
    assert "and nothing imports" in report
    assert "a feature DOES NOT WORK" in report, "it stops the suite running, so it blocks"


class TestAnAttributeTheScriptSetsItself:
    """A script that sets an attribute is not reading one nothing sets.

    `_JS_ASSIGNS_ID` has covered the `setAttribute` form since it was written;
    the data-attribute side covered only `element.dataset.x = ...`. That is the
    §1-B mistake again - a rule defined over part of the set it governs.

    One run built inline editing whose inputs carry
    `setAttribute('data-field', 'title')` and whose save handler reads
    `li.querySelector('[data-field="title"]')`. It was reported for reading an
    attribute "which no HTML element sets. It is `undefined` every time", as a
    blocking finding, against code that works.
    """

    def _page(self, tmp_path):
        (tmp_path / "index.html").write_text(
            '<!doctype html><html><body><ul id="task-list"></ul>'
            '<script src="app.js"></script></body></html>'
        )

    def _problems(self, tmp_path):
        from app.analysis.integration_checks import (
            _hooks_javascript_reaches_for,
            _source_files,
        )

        return _hooks_javascript_reaches_for(_source_files(tmp_path), tmp_path)

    def test_set_attribute_then_read_by_selector_is_fine(self, tmp_path):
        self._page(tmp_path)
        (tmp_path / "app.js").write_text(
            "const el = document.getElementById('task-list');\n"
            "const input = document.createElement('input');\n"
            "input.setAttribute('data-field', 'title');\n"
            "const found = el.querySelector('[data-field=\"title\"]');\n"
        )
        assert self._problems(tmp_path) == []

    def test_dataset_assignment_then_read_by_selector_is_fine(self, tmp_path):
        """The early subtraction let the selector path put it back."""
        self._page(tmp_path)
        (tmp_path / "app.js").write_text(
            "const el = document.getElementById('task-list');\n"
            "el.dataset.field = 'title';\n"
            "const found = el.querySelector('[data-field=\"title\"]');\n"
        )
        assert self._problems(tmp_path) == []

    def test_an_attribute_genuinely_nobody_sets_is_still_reported(self, tmp_path):
        self._page(tmp_path)
        (tmp_path / "app.js").write_text(
            "const el = document.getElementById('task-list');\n"
            "const found = el.querySelector('[data-status=\"done\"]');\n"
        )
        problems = self._problems(tmp_path)
        assert len(problems) == 1 and "data-status" in problems[0]

    def test_a_camel_cased_dataset_write_matches_the_dashed_attribute(self, tmp_path):
        self._page(tmp_path)
        (tmp_path / "app.js").write_text(
            "const el = document.getElementById('task-list');\n"
            "el.dataset.taskId = '1';\n"
            "const found = el.querySelector('[data-task-id=\"1\"]');\n"
        )
        assert self._problems(tmp_path) == []


class TestABrowserHelperIsNotACopy:
    """An end-to-end helper shares a name with the application and nothing else.

    `addTask(page, title)` types into a form and clicks a button.
    `addTask(title, description)` returns an object. Importing the second in
    place of the first would defeat the test, which is why one run's
    milestone reviewer rebutted this finding in its own words: "importing the
    JS module would defeat the purpose of end-to-end verification and is not
    required or expected". One run was reported for the same thing.

    Two reviewers pushing back on a blocking finding is the signal the finding
    is wrong - and a specialist sent to fix working code is what cost one
    run its life.
    """

    def _problems(self, tmp_path):
        from app.analysis.integration_checks import (
            _redefined_instead_of_imported,
            _source_files,
        )

        return _redefined_instead_of_imported(_source_files(tmp_path), tmp_path)

    def _app(self, tmp_path):
        (tmp_path / "app.js").write_text(
            "export function addTask(title, description) {\n"
            "  return { title, description };\n}\n"
        )

    def test_a_playwright_fixture_is_not_reported(self, tmp_path):
        self._app(tmp_path)
        (tmp_path / "fixtures.ts").write_text(
            "import { expect, type Page } from '@playwright/test';\n"
            "export async function addTask(page: Page, title: string): Promise<void> {\n"
            "  await page.fill('#task-title', title);\n"
            "  await page.click('#add');\n}\n"
        )
        assert self._problems(tmp_path) == []

    def test_a_helper_taking_page_first_is_not_reported(self, tmp_path):
        self._app(tmp_path)
        (tmp_path / "e2e.spec.js").write_text(
            "export async function addTask(page, title) {\n"
            "  await page.getByRole('textbox').fill(title);\n}\n"
        )
        assert self._problems(tmp_path) == []

    def test_a_unit_test_copying_the_application_is_still_reported(self, tmp_path):
        """The defect this check exists for must survive the exemption."""
        self._app(tmp_path)
        (tmp_path / "app.test.mjs").write_text(
            "import { test } from 'node:test';\n"
            "function addTask(title, description) { return { title, description }; }\n"
            "test('adds', () => { addTask('a', 'b'); });\n"
        )

        problems = self._problems(tmp_path)

        assert len(problems) == 1
        assert "addTask" in problems[0]
        assert "tests a copy" in problems[0]

    def test_a_copy_that_merely_mentions_a_page_variable_is_still_reported(
        self, tmp_path
    ):
        """The exemption is for a driver, not for the word `page` appearing."""
        self._app(tmp_path)
        (tmp_path / "app.test.mjs").write_text(
            "import { test } from 'node:test';\n"
            "function addTask(title, description) { return { title, description }; }\n"
            "const page = 1;\n"
            "test('adds', () => { addTask('a', 'b'); });\n"
        )
        assert len(self._problems(tmp_path)) == 1



def test_a_setup_file_given_with_an_equals_sign_is_followed() -> None:
    from app.analysis.integration_checks import _explicitly_imported_in_command

    assert _explicitly_imported_in_command("node --test --import=./tests/setup.mjs tests/") == ["./tests/setup.mjs"]
    assert _explicitly_imported_in_command("node --test --require=./setup.cjs") == ["./setup.cjs"]
