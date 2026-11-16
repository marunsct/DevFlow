"""A file that makes its own `require` with `createRequire` is an ES module, not CommonJS left behind (found on a run).

Measured on one run (a C# service whose acceptance suite runs on Node): the locked spec began
`import { createRequire } from 'module'; const require = createRequire(import.meta.url);` under the pack's
`"type": "module"`. The check called it CommonJS that "cannot run" before any test had loaded; two fixers changed the
manifest, broke the suite (0 tests ran) and were reverted, while the suite passed 12 of 12 as written.
"""
from __future__ import annotations

from app.analysis import integration_checks as checks


def _package(tmp_path, spec):
    (tmp_path / "package.json").write_text('{"type": "module"}\n')
    (tmp_path / "acceptance").mkdir()
    (tmp_path / "acceptance" / "notes.spec.js").write_text(spec)
    return [tmp_path / "package.json", tmp_path / "acceptance" / "notes.spec.js"]


def test_a_require_made_with_create_require_is_left_alone(tmp_path):
    files = _package(tmp_path, "import { test } from '@playwright/test';\nimport { createRequire } from 'module';\n"
                               "const require = createRequire(import.meta.url);\nconst { start } = require('./service.cjs');\n")
    assert checks._files_that_contradict_the_declared_module_type(files, tmp_path) == []


def test_a_plain_require_is_still_named(tmp_path):
    files = _package(tmp_path, "const { test } = require('@playwright/test');\n")
    assert checks._files_that_contradict_the_declared_module_type(files, tmp_path)


def test_module_exports_is_still_named_even_with_create_require(tmp_path):
    files = _package(tmp_path, "import { createRequire } from 'module';\nconst require = createRequire(import.meta.url);\n"
                               "module.exports = { a: 1 };\n")
    assert checks._files_that_contradict_the_declared_module_type(files, tmp_path)
