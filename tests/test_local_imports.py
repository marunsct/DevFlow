"""Relative imports checked against the files they name.

One run had two of five tests fail, and neither failure was about the
product:

    SyntaxError: The requested module './app.js' does not provide an export
    named 'default'

    Error [ERR_MODULE_NOT_FOUND]: Cannot find module '.../test/app.mjs'
    imported from '.../test/app-regression-test2.test.mjs'

A test importing a default from a module with only named exports, and a test
inside `test/` importing `./app.mjs` when the module is in the directory above.
Both are decidable from the two files; both cost a remediation round.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.local_imports import import_problems
from app.tools.repository import write_approved_artifact

MODULE = "export function loadTasks() {}\nexport function addTask(task) {}\n"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "app.js").write_text(MODULE, encoding="utf-8")
    (tmp_path / "test").mkdir()
    return tmp_path


def test_a_default_import_from_a_module_without_one(project: Path) -> None:
    (problem,) = import_problems(
        project / "app.test.mjs", "import app from './app.js';\n", project
    )

    assert "no default export" in problem
    assert "addTask, loadTasks" in problem, "say what it does offer"


def test_an_import_from_the_wrong_directory(project: Path) -> None:
    (problem,) = import_problems(
        project / "test" / "a.test.mjs",
        "import { addTask } from './app.mjs';\n",
        project,
    )

    assert "does not resolve" in problem
    assert "app.js" in problem, "say where the module actually is"


def test_a_name_the_module_does_not_export(project: Path) -> None:
    (problem,) = import_problems(
        project / "app.test.mjs",
        "import { addTask, removeTask } from './app.js';\n",
        project,
    )

    assert "does not export `removeTask`" in problem


@pytest.mark.parametrize(
    "content",
    [
        "import { addTask } from './app.js';\n",
        "import { addTask as add } from './app.js';\n",
        "import * as api from './app.js';\n",
        "export { addTask } from './app.js';\n",
        "import 'node:test';\nimport assert from 'node:assert';\n",
    ],
)
def test_an_import_that_works_says_nothing(project: Path, content: str) -> None:
    assert import_problems(project / "app.test.mjs", content, project) == []


def test_a_default_export_is_recognised(tmp_path: Path) -> None:
    (tmp_path / "api.js").write_text("export default function api() {}\n", encoding="utf-8")

    assert import_problems(
        tmp_path / "a.mjs", "import api from './api.js';\n", tmp_path
    ) == []


def test_a_commonjs_module_is_not_judged(tmp_path: Path) -> None:
    """`module.exports` is decided at runtime and cannot be read statically."""
    (tmp_path / "api.js").write_text("module.exports = { a: 1 };\n", encoding="utf-8")

    assert import_problems(
        tmp_path / "a.cjs", "const { anything } = require('./api.js');\n", tmp_path
    ) == []


def test_a_re_export_star_is_not_judged(tmp_path: Path) -> None:
    (tmp_path / "api.js").write_text("export * from './other.js';\n", encoding="utf-8")

    assert import_problems(
        tmp_path / "a.mjs", "import { anything } from './api.js';\n", tmp_path
    ) == []


def test_it_is_a_note_and_not_a_refusal(tmp_path: Path) -> None:
    """A test written before the module it imports is the right order to work
    in, and this cannot tell that from a wrong path."""
    write_approved_artifact(tmp_path, "proj/package.json", '{"name": "p", "type": "module"}')

    result = write_approved_artifact(
        tmp_path,
        "proj/app.test.mjs",
        "import test from 'node:test';\nimport { addTask } from './not-written-yet.js';\n",
    )

    assert result["status"] == "written"
    assert "does not resolve" in (result.get("note") or "")


def test_the_note_reaches_a_write_that_is_wrong(tmp_path: Path) -> None:
    write_approved_artifact(tmp_path, "proj/package.json", '{"name": "p", "type": "module"}')
    write_approved_artifact(tmp_path, "proj/app.js", MODULE)

    result = write_approved_artifact(
        tmp_path,
        "proj/app.test.mjs",
        "import test from 'node:test';\nimport app from './app.js';\n",
    )

    assert "no default export" in (result.get("note") or "")


def test_the_suggestion_does_not_name_the_importing_file(tmp_path: Path) -> None:
    """`rglob("app.*")` matched `app.test.mjs` as well as `app.js`.

    Run d6297b2f's `defect_fix_1_0` wrote `import { ... } from './app.cjs'`
    into `app.test.mjs` and was told "There is a file of that name at app.js,
    app.test.mjs" - a file that is not of that name, and an instruction to
    import itself.
    """
    (tmp_path / "app.js").write_text("export function a() {}\n", encoding="utf-8")
    suite = tmp_path / "app.test.mjs"
    suite.write_text("import { a } from './app.cjs';\n", encoding="utf-8")

    problems = import_problems(suite, suite.read_text(), tmp_path)

    assert len(problems) == 1
    assert "app.js" in problems[0]
    assert "app.test.mjs" not in problems[0].split("There is a file")[1]


def test_a_file_whose_name_merely_starts_with_the_stem_is_not_of_that_name(
    tmp_path: Path,
) -> None:
    (tmp_path / "app.helpers.js").write_text("export function h() {}\n", encoding="utf-8")
    suite = tmp_path / "suite.mjs"
    suite.write_text("import { a } from './app.js';\n", encoding="utf-8")

    problems = import_problems(suite, suite.read_text(), tmp_path)

    assert len(problems) == 1
    assert "There is a file of that name" not in problems[0]


def test_the_real_file_is_still_found_under_another_extension(tmp_path: Path) -> None:
    (tmp_path / "store.mjs").write_text("export function s() {}\n", encoding="utf-8")
    suite = tmp_path / "suite.mjs"
    suite.write_text("import { s } from './store.cjs';\n", encoding="utf-8")

    problems = import_problems(suite, suite.read_text(), tmp_path)

    assert "store.mjs" in problems[0]
