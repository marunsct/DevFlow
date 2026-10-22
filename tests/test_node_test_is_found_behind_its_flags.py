"""`node --test` is recognised with Node's own flags in front of `--test`.

The browser pack's own scaffold writes
`node --import ./test-setup.mjs --test ... tests/`. The checks looked for the
text "node --test", so one run's test round was handed, as a proven problem,
"package.json has no script that runs" the very suites that script ran - and
the round reported the pipeline's claim as false.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analysis import integration_checks as ic
from app.stacks import pack_named


@pytest.mark.parametrize("command, runs", [
    ("node --test", True),
    ("node --test tests/", True),
    ("mkdir -p out && node --import ./test-setup.mjs --test --test-reporter=spec tests/", True),
    ("node --inspect --test", True),
    ("node --test-reporter=spec main.js", False),
    ("node scripts/run.js --test", False),
    ("node --import ./setup.mjs scripts/run.js --test", False),
    ("node --experimental-vm-modules node_modules/jest/bin/jest.js", False),
])
def test_node_s_runner_is_found_whatever_flags_come_first(command, runs) -> None:
    assert ic._invokes_node_test(command) is runs


def test_the_browser_pack_s_own_unit_script_runs_its_node_suites(tmp_path: Path) -> None:
    project = tmp_path / "app"
    (project / "tests").mkdir(parents=True)
    script = pack_named("browser-javascript").render("app", "App")["package.json"]
    (project / "package.json").write_text(script)
    assert "--import" in json.loads(script)["scripts"]["test"]
    suite = project / "tests" / "app.test.js"
    suite.write_text("import { test } from 'node:test';\ntest('x', () => {});\n")

    files = [project / "package.json", suite]
    assert ic._node_suites_nothing_runs(files, tmp_path) == []
    assert ic._the_runner_a_script_invokes(json.loads(script)["scripts"]["test"]) == ("node --test", True)


def test_a_project_whose_scripts_never_run_node_s_runner_is_still_told(tmp_path: Path) -> None:
    project = tmp_path / "app"
    (project / "tests").mkdir(parents=True)
    (project / "package.json").write_text(json.dumps({"scripts": {"test": "npx playwright test"}}))
    suite = project / "tests" / "app.test.js"
    suite.write_text("import { test } from 'node:test';\ntest('x', () => {});\n")

    found = ic._node_suites_nothing_runs([project / "package.json", suite], tmp_path)
    assert len(found) == 1 and "app/tests/app.test.js" in found[0]
