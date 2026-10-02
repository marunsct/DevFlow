"""Jest run plainly over tests written as ES modules is named, with the one fix.

Jest loads a test file as CommonJS. In a project whose manifest says
`"type": "module"` every `import` in a test is "Cannot use import statement
outside a module" until Node is started with `--experimental-vm-modules`.

Measured on one run and the same family on three before it: three test rounds
reported three readings of it, `jest.config.cjs` was written by four stages in
ten minutes, and it ended with the flag under `globals`, where Jest ignores it.
Verified in the worker image: the same suite fails under `jest` and passes
under `node --experimental-vm-modules node_modules/jest/bin/jest.js`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analysis import integration_checks as checks
from app.plugins.seed import SEED_INSTRUCTIONS

ESM_TEST = "import { add } from '../app.js';\n\ntest('adds', () => { expect(add(1, 2)).toBe(3); });\n"
CJS_TEST = "const { add } = require('../app.js');\n\ntest('adds', () => { expect(add(1, 2)).toBe(3); });\n"


def _project(root: Path, manifest: dict, files: dict) -> None:
    project = root / "app"
    project.mkdir()
    (project / "package.json").write_text(json.dumps({"name": "app", **manifest}), encoding="utf-8")
    for name, content in {"app.js": "export function add(a, b) { return a + b; }\n", **files}.items():
        target = project / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _found(root: Path) -> list[str]:
    return checks._jest_started_without_what_es_modules_need(checks._source_files(root), root)


def test_the_run_s_setup_is_named_with_the_script_that_works(tmp_path: Path) -> None:
    _project(
        tmp_path,
        {"type": "module", "scripts": {"test": "npx jest"}},
        {
            "tests/app.test.js": ESM_TEST,
            "jest.config.cjs": "module.exports = { globals: { NODE_OPTIONS: '--experimental-vm-modules' } };\n",
        },
    )

    (problem,) = _found(tmp_path)

    assert "starts Jest as `npx jest`" in problem
    assert "app/tests/app.test.js" in problem
    assert "node --experimental-vm-modules node_modules/jest/bin/jest.js" in problem
    assert "not a key in Jest's configuration" in problem
    assert any("starts Jest as" in p for p in checks.problems_that_break_the_product(tmp_path))


@pytest.mark.parametrize("script", [
    "node --experimental-vm-modules node_modules/jest/bin/jest.js",
    "NODE_OPTIONS=--experimental-vm-modules npx jest",
])
def test_jest_started_with_the_flag_is_left_alone(tmp_path: Path, script: str) -> None:
    _project(tmp_path, {"type": "module", "scripts": {"test": script}}, {"tests/app.test.js": ESM_TEST})

    assert _found(tmp_path) == []


def test_a_project_with_a_babel_configuration_is_left_alone(tmp_path: Path) -> None:
    _project(
        tmp_path,
        {"type": "module", "scripts": {"test": "jest"}},
        {"tests/app.test.js": ESM_TEST, "babel.config.cjs": "module.exports = { presets: ['@babel/preset-env'] };\n"},
    )

    assert _found(tmp_path) == []


def test_a_commonjs_project_runs_under_plain_jest(tmp_path: Path) -> None:
    _project(tmp_path, {"scripts": {"test": "jest"}}, {"tests/app.test.js": CJS_TEST})

    assert _found(tmp_path) == []


def test_another_runner_s_spec_is_not_jest_s_to_load(tmp_path: Path) -> None:
    spec = "import { test, expect } from '@playwright/test';\ntest('x', async ({ page }) => {});\n"
    _project(
        tmp_path,
        {"type": "module", "scripts": {"test": "jest", "e2e": "playwright test"}},
        {"tests/app.test.js": CJS_TEST.replace("const { add } = require('../app.js');", "// no imports"), "e2e/a.spec.js": spec},
    )

    assert _found(tmp_path) == []


def test_another_runner_is_not_jest(tmp_path: Path) -> None:
    _project(tmp_path, {"type": "module", "scripts": {"test": "vitest run"}}, {"tests/app.test.js": ESM_TEST})

    assert _found(tmp_path) == []


# --- and the guidance says it before anything is written ----------------------


@pytest.mark.parametrize("key", ["javascript", "typescript", "node"])
def test_the_guidance_names_what_each_unit_runner_needs(key: str) -> None:
    text = SEED_INSTRUCTIONS[key]

    assert "node --experimental-vm-modules node_modules/jest/bin/jest.js" in text
    assert "`experimentalVmModules`" in text and "do NOT do this" in text
    assert "the unit runner\n  this project's stack names and no other" in text
    assert "TWO RUNNERS MUST NOT LOAD EACH OTHER'S FILES" in text
    # It no longer tells every project to use one runner whatever its stack chose.
    assert '"scripts": {"test": "node --test <your test files>"}' not in text
