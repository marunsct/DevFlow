"""`test(...)` with nothing importing `test`, under `node --test`.

Jest, Vitest and Mocha inject `test`, `it` and `describe` as globals.
`node --test` does not: they are exports of `node:test`, and a file that calls
one without importing it throws on the first case. Verified in the worker image
on Node 20.20.2 - a file whose only content is `test("x", () => assert.ok(true))`
reports

    ReferenceError: test is not defined
    # tests 1   # pass 0   # fail 1

Run d6297b2f's `test_round_0` got `ReferenceError: describe is not defined` and
"fixed" it by moving every case inside a default export - the shape
`tests_the_runner_will_never_call` now catches. Run 0afef410's
`specialist_backend_2` renamed `app.test.mjs` to `app.test.js` and got
`ReferenceError: test is not defined` for its trouble.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _severity_of,
    _suites_calling_a_global_node_does_not_define as missing_import,
)

NO_IMPORT = "import assert from 'node:assert';\ntest('x', () => { assert.ok(1); });\n"
IMPORTED = (
    "import { test } from 'node:test';\n"
    "import assert from 'node:assert';\n"
    "test('x', () => { assert.ok(1); });\n"
)


@pytest.fixture
def build(tmp_path: Path):
    def make(files: dict[str, str]) -> tuple[list[Path], Path]:
        project = tmp_path / "app"
        project.mkdir(exist_ok=True)
        written = []
        for name, content in files.items():
            path = project / name
            path.write_text(content, encoding="utf-8")
            written.append(path)
        return written, tmp_path

    return make


def test_a_suite_global_with_no_import_is_reported(build):
    files, root = build({"package.json": '{"name":"p"}', "app.test.mjs": NO_IMPORT})

    problems = missing_import(files, root)

    assert len(problems) == 1
    assert "ReferenceError: test is not defined" in problems[0]


def test_it_names_the_import_to_add(build):
    files, root = build({"package.json": '{"name":"p"}', "app.test.mjs": NO_IMPORT})

    assert "from 'node:test'" in missing_import(files, root)[0]


def test_it_blocks_rather_than_reading_as_untidy(build):
    """The suite cannot run at all; a reviewer must not wave it through."""
    files, root = build({"package.json": '{"name":"p"}', "app.test.mjs": NO_IMPORT})

    assert _severity_of(missing_import(files, root)[0]) == "BREAKS"


def test_a_file_that_imports_it_is_left_alone(build):
    files, root = build({"package.json": '{"name":"p"}', "app.test.mjs": IMPORTED})

    assert missing_import(files, root) == []


def test_the_require_form_counts_as_importing_it(build):
    files, root = build({
        "package.json": '{"name":"p"}',
        "app.test.cjs": "const { test } = require('node:test');\ntest('x', () => {});\n",
    })

    assert missing_import(files, root) == []


@pytest.mark.parametrize("runner", ["jest", "vitest", "mocha", "jasmine"])
def test_a_runner_that_does_inject_the_globals_is_left_alone(build, runner: str):
    files, root = build({
        "package.json": '{"name":"p","devDependencies":{"%s":"^1"}}' % runner,
        "app.test.js": NO_IMPORT,
    })

    assert missing_import(files, root) == []


def test_a_jest_config_alone_is_enough_to_stay_quiet(build):
    files, root = build({
        "package.json": '{"name":"p"}',
        "jest.config.js": "module.exports = {};",
        "app.test.js": NO_IMPORT,
    })

    assert missing_import(files, root) == []


def test_application_code_defining_its_own_test_function_is_not_a_suite(build):
    files, root = build({
        "package.json": '{"name":"p"}',
        "app.js": "function test() {}\ntest();\n",
    })

    assert missing_import(files, root) == []


def test_describe_is_recognised_as_well_as_test(build):
    files, root = build({
        "package.json": '{"name":"p"}',
        "app.test.mjs": "describe('a group', () => {});\n",
    })

    problems = missing_import(files, root)

    assert len(problems) == 1
    assert "describe is not defined" in problems[0]
