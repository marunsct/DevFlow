"""Files written separately have to refer to each other.

Each specialist writes its own files and each is defensible alone. Nothing
checked whether they connect, and that is where run-95ca3f72's milestone 1
broke: a stylesheet targeting an id no page declared, and a module no page
loaded, both passed four review stages.

Every case below is taken from a defect that actually shipped.
"""

from __future__ import annotations

import pytest

from app.analysis.integration_checks import summarise_integration


def _workspace(tmp_path, files: dict[str, str]):
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return str(tmp_path)


def test_a_stylesheet_targeting_a_missing_id_is_reported(tmp_path):
    """run-95ca3f72: `#app-placeholder` styled, `#app` written."""
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


def test_a_script_nothing_loads_is_reported(tmp_path):
    """run-95ca3f72: `script.js` exported a function; no page had a script tag."""
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
    """run-95ca3f72: `export function` with `testEnvironment: 'node'`, no transform."""
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
    # The message used to name only Jest, which let every project that does not
    # use Jest dismiss it - and most here do not. It now leads with the
    # consequence any runner hits and mentions Jest's extra requirement after.
    assert "does not provide an export named" in report
    assert "Jest additionally needs a `transform`" in report


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
# run-64df2b20 the selection was Python / FastAPI / PostgreSQL / pytest, and
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
    root = _workspace(tmp_path, {"package.json": '{"devDependencies":{"jest":"^29"}}'})

    assert "chosen testing framework is pytest" in summarise_integration(root, PY_STACK)


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

    assert "chosen" not in report


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

    assert "chosen" not in summarise_integration(root)


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
# is a constraint no stage ever checked against what was built. run-18c0e34c
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
# below shipped in run-3da8dd91, which completed and passed every milestone
# review.


def test_the_npm_placeholder_test_script_is_reported(tmp_path):
    """The exact artefact that cost run-95ca3f72 its entire sprint."""
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
    """run-3da8dd91 shipped jsdom under `dependencies` against a brief that
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

    run-cbd22a34's milestone reviewer found `linkedom` declared as a production
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

    Measured on run-61c5a5b6, against a brief capping the product at 500 lines:
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

    Measured on run-2b5def74: `app.js` called `init()` at module scope, so the
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
    from app.analysis.integration_checks import _NOT_APPLICATION

    assert _NOT_APPLICATION.search("proj/test-contract.js")
    assert _NOT_APPLICATION.search("proj/test_helpers.js")
    assert not _NOT_APPLICATION.search("proj/app.js")
    assert not _NOT_APPLICATION.search("proj/latest-news.js")


# --- "lines of code" is not "lines of file" -------------------------------


def test_the_report_separates_code_from_blank_and_comment(tmp_path):
    """A brief capping "lines of code" means the code lines.

    Reporting only the raw count left the reviewer comparing a number against a
    limit that means something else: on run-2b5def74 nothing could say whether
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

    Measured on run-2f252e4e: a specification describing pure functions, a
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


def test_the_module_mismatch_names_the_real_consequence(tmp_path):
    """Naming only Jest made this dismissible by every project that does not
    use Jest - which is most of them here.

    Measured on run-da6c5e19: `app.js` exported three objects, nothing declared
    the module type, `node --test` loaded it as CommonJS, and the test file
    reported "we can't directly import app.js", wrote its own copy of the
    logic, and passed.
    """
    from app.analysis.integration_checks import summarise_integration

    (tmp_path / "index.html").write_text(
        '<!doctype html><script src="app.js"></script>', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text(
        "function createTask(t){ return t; }\nexport { createTask };\n", encoding="utf-8"
    )

    summary = summarise_integration(str(tmp_path))

    assert "does not provide an export named" in summary
    assert "loads them as CommonJS" in summary


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

    Measured on run-da6c5e19: the two files that proved the copy-test fix had
    worked were the two the report told the reviewer to delete.
    """
    from app.analysis.integration_checks import _NOT_APPLICATION

    assert _NOT_APPLICATION.search(name)


@pytest.mark.parametrize("name", ["app.mjs", "app.js", "latest-news.js"])
def test_an_mjs_application_file_is_not_a_test(name: str):
    from app.analysis.integration_checks import _NOT_APPLICATION

    assert not _NOT_APPLICATION.search(name)


# --- a stylesheet rule nothing ever applies --------------------------------


def test_a_class_nothing_applies_is_reported(tmp_path):
    """Found on run-da6c5e19's second sprint by a reviewer reading three files
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
    """A word used for another reason keeps its rule. On run-da6c5e19 `.active`
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
