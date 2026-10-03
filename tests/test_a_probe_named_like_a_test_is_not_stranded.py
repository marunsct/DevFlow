"""A file named like a test that holds no test is not a stranded test.

One run's `test_import.js` imported `app.js` and printed its state - no
assertion, no test registered. The check for tests the project never runs
reported it stranded every round, and each report was recorded as a defect
no fix could clear: there was nothing in it to run.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.analysis.integration_checks import _source_files, _tests_the_project_never_runs

PROBE = (
    "globalThis.window = {localStorage: {getItem() { return null; }}};\n"
    "const mod = await import('./app.js');\n"
    "console.log(mod.getState());\n"
)
A_TEST = "import { test } from 'node:test';\nimport assert from 'node:assert';\ntest('x', () => assert.ok(true));\n"


def _project(tmp_path: Path, name: str, content: str) -> Path:
    app = tmp_path / "app"
    (app / "tests").mkdir(parents=True)
    (app / "package.json").write_text(
        json.dumps({"type": "module", "scripts": {"test": "node --test tests/"}}), encoding="utf-8"
    )
    (app / "app.js").write_text("export const getState = () => ({});\n", encoding="utf-8")
    (app / "tests" / "app.test.js").write_text(A_TEST, encoding="utf-8")
    (app / name).write_text(content, encoding="utf-8")
    return tmp_path


def test_a_probe_with_a_test_s_name_is_not_reported(tmp_path: Path) -> None:
    root = _project(tmp_path, "test_import.js", PROBE)

    assert not any("test_import.js" in p for p in _tests_the_project_never_runs(_source_files(root), root))


def test_a_real_test_the_command_misses_still_is(tmp_path: Path) -> None:
    root = _project(tmp_path, "test_import.js", A_TEST)

    assert any("test_import.js" in p for p in _tests_the_project_never_runs(_source_files(root), root))
