"""CommonJS left in `.js` files after the manifest declared ESM.

`"type": "module"` reaches every `.js` file in the package at once, and
`require` and `module` stop existing in all of them. Verified in the worker
image on Node 20.20.2:

    ReferenceError: require is not defined in ES module scope, you can use
    import instead
    ReferenceError: module is not defined in ES module scope

Run d6297b2f is what this is for. `specialist_testing_1` added
`"type":"module"` to the manifest while four of its five test files still used
`require('../app.js')`, then converted them one at a time, each discovered by
a separate failing `npm test`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _files_that_contradict_the_declared_module_type as contradictions,
)

ESM_MANIFEST = '{"name":"p","type":"module","scripts":{"test":"node --test"}}'
PLAIN_MANIFEST = '{"name":"p","scripts":{"test":"node --test"}}'
REQUIRES = "const { addTask } = require('../app.js');\n"
EXPORTS = "function addTask() {}\nmodule.exports = { addTask };\n"
IMPORTS = "import { addTask } from '../app.js';\n"


@pytest.fixture
def workspace(tmp_path: Path):
    def build(files: dict[str, str]) -> tuple[list[Path], Path]:
        project = tmp_path / "app"
        written = []
        for name, content in files.items():
            path = project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            written.append(path)
        return written, tmp_path

    return build


def test_every_contradicting_file_is_named_in_one_finding(workspace):
    files, root = workspace({
        "package.json": ESM_MANIFEST,
        "test/addTask.test.js": REQUIRES,
        "test/editTask.test.js": REQUIRES,
        "app.js": IMPORTS,
    })

    problems = contradictions(files, root)

    assert len(problems) == 1
    assert "test/addTask.test.js" in problems[0]
    assert "test/editTask.test.js" in problems[0]


def test_the_finding_says_why_one_at_a_time_is_the_expensive_way(workspace):
    files, root = workspace({
        "package.json": ESM_MANIFEST,
        "test/a.test.js": REQUIRES,
    })

    assert "a failing test run per file" in contradictions(files, root)[0]


def test_the_finding_names_the_error_node_actually_throws(workspace):
    files, root = workspace({
        "package.json": ESM_MANIFEST,
        "test/a.test.js": REQUIRES,
    })

    assert "require is not defined in ES module scope" in contradictions(files, root)[0]


def test_module_exports_counts_as_well_as_require(workspace):
    files, root = workspace({"package.json": ESM_MANIFEST, "app.js": EXPORTS})

    assert len(contradictions(files, root)) == 1


def test_a_package_whose_files_all_agree_is_left_alone(workspace):
    files, root = workspace({
        "package.json": ESM_MANIFEST,
        "test/a.test.js": IMPORTS,
        "app.js": IMPORTS,
    })

    assert contradictions(files, root) == []


def test_a_cjs_file_keeps_require_and_is_exempt(workspace):
    """Verified in the worker image: `.cjs` keeps `require` under type: module."""
    files, root = workspace({"package.json": ESM_MANIFEST, "test/a.test.cjs": REQUIRES})

    assert contradictions(files, root) == []


def test_a_manifest_that_declares_nothing_is_not_this_check(workspace):
    """Node reparses a typeless `.js` that uses module syntax - measured."""
    files, root = workspace({"package.json": PLAIN_MANIFEST, "test/a.test.js": REQUIRES})

    assert contradictions(files, root) == []


def test_installed_packages_are_not_the_project(workspace):
    files, root = workspace({
        "package.json": ESM_MANIFEST,
        "node_modules/left-pad/index.js": REQUIRES,
    })

    assert contradictions(files, root) == []


def test_the_reviewer_reports_it(tmp_path: Path):
    from app.analysis.integration_checks import summarise_integration

    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(ESM_MANIFEST, encoding="utf-8")
    (project / "app.js").write_text(EXPORTS, encoding="utf-8")

    assert "ES module scope" in summarise_integration(str(tmp_path))
