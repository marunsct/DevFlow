"""`npm test` is asked for only where npm runs the project's own tests, and only beside real test files.

Measured on the first two language-sweep runs (a Go service and a Rust service, each 9/9 hidden and 8/8 quality): the
release called each not deliverable for one blocking gap - "package.json declares no `test` script, and this project
has tests (package-lock.json, playwright.config.js, ...)". The manifest was there only to run the browser acceptance
suite; the projects' own tests run with their language's command; and two of the three "tests" named were a lock
file and a runner configuration.
"""
from __future__ import annotations

import json

from app.analysis.integration_checks import summarise_integration
from app.stacks import contract


def _service(tmp_path, unit_test):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test:acceptance": "playwright test"}}))
    (tmp_path / "package-lock.json").write_text("{}")
    (tmp_path / "playwright.config.js").write_text("export default {};\n")
    (tmp_path / "server_test.go").write_text("package main\n")
    (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")
    record = tmp_path / contract.CONTRACT_FILE
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"pack": "a-service", "unit_test": unit_test}))


def test_a_project_whose_own_tests_run_another_way_is_not_asked_for_npm_test(tmp_path):
    _service(tmp_path, ["go", "test", "./..."])
    assert "declares no `test` script" not in summarise_integration(str(tmp_path))


def test_a_lock_file_and_a_runner_configuration_are_not_tests(tmp_path):
    (tmp_path / "index.html").write_text('<!doctype html><script src="app.js"></script>')
    (tmp_path / "app.js").write_text("export const a = 1;\n")
    (tmp_path / "package.json").write_text('{"type": "module"}\n')
    (tmp_path / "package-lock.json").write_text("{}")
    (tmp_path / "playwright.config.js").write_text("export default {};\n")
    assert "declares no `test` script" not in summarise_integration(str(tmp_path))


def test_where_npm_runs_the_project_s_tests_it_is_still_asked_for(tmp_path):
    _service(tmp_path, ["npm", "test"])
    (tmp_path / "app.test.mjs").write_text("import {a} from './app.js';\n")
    summary = summarise_integration(str(tmp_path))
    assert "declares no `test` script" in summary and "package-lock.json" not in summary.split("declares no")[1][:200]
