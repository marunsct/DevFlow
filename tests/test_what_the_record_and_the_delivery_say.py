"""What a finished run records about itself, and what it hands over.

From one run's product audit: it scored 10/10 on the benchmark's hidden tests,
yet every Sprint Record read "Passed: 0, Failed: 0" - twelve unit tests and
nine acceptance tests were passing - and three probes named like tests
(`run_test.js`, `test_import.js`, `test_runner.js`) shipped at the top of the
product, run by no suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import ci
from app.analysis import project_memory
from app.stacks import pack_named
from app.stacks.scaffold import scaffold
from app.tools.repository import clear_the_throwaways_left_behind
from app.tools.sandbox import _the_counts_a_test_run_reported


def test_the_spec_reporter_s_counts_are_read() -> None:
    """The packs' unit scripts use Node's spec reporter, which writes "ℹ pass 12"
    where the TAP reporter writes "# pass 12"; only the latter was read."""
    spec = "✔ adds a task (1ms)\nℹ tests 12\nℹ suites 0\nℹ pass 12\nℹ fail 0\nℹ skipped 0\n"
    assert _the_counts_a_test_run_reported({"stdout": spec}) == {"passed": 12, "failed": 0, "tests": 12}
    tap = "ok 1 - a\n# tests 3\n# pass 2\n# fail 1\n"
    assert _the_counts_a_test_run_reported({"stdout": tap}) == {"passed": 2, "failed": 1, "tests": 3}


def test_a_completed_sprint_counts_what_the_harness_measured_at_acceptance(tmp_path) -> None:
    from app.graph.workflow import _the_accepted_counts

    assert _the_accepted_counts(str(tmp_path)) is None
    ci.save(tmp_path, ci.Snapshot(
        label="accepted", commit="abc",
        unit={f"unit {n}": "passed" for n in range(12)},
        acceptance={**{f"[AC-{n}] x": "passed" for n in range(1, 9)}, "[AC-9] y": "failed"},
    ), accepted=True)

    assert _the_accepted_counts(str(tmp_path)) == {"tests": 21, "passed": 20, "failed": 1}


def _runner(root: Path, pack):
    def run(argv, category, working_directory):
        unit = list(argv) == pack.commands(working_directory)["unit_test"]
        report = root / working_directory / (pack.unit_report if unit else pack.acceptance_report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("<testsuites><testcase name='smoke'/></testsuites>")
        return {"returncode": "0"}

    return run


@pytest.fixture
def project(tmp_path) -> Path:
    pack = pack_named("browser-javascript")
    assert scaffold(tmp_path, pack, "notes", "Notes", run=_runner(tmp_path, pack)).ok
    (tmp_path / ".project-directory").write_text("notes\n")
    return tmp_path


def _left(root: Path, relative: str, text: str = "console.log('probe');\n") -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    project_memory.record(root, relative, "defect_fix_1_0")


def test_a_probe_named_like_a_test_that_no_suite_runs_is_cleared(project) -> None:
    for name in ("notes/run_test.js", "notes/test_import.js", "notes/test_runner.js"):
        _left(project, name)
    _left(project, "notes/tests/app.test.js", "import { test } from 'node:test';\n")
    _left(project, "notes/acceptance/app.spec.js", "test('[AC-1] x', () => {});\n")

    removed = clear_the_throwaways_left_behind(project)

    assert sorted(removed) == ["notes/run_test.js", "notes/test_import.js", "notes/test_runner.js"]
    assert (project / "notes/tests/app.test.js").exists()
    assert (project / "notes/acceptance/app.spec.js").exists()
    assert (project / "notes/playwright.setup.mjs").exists()
    assert (project / "notes/test-setup.mjs").exists()


def test_one_something_still_runs_is_kept(project) -> None:
    _left(project, "notes/test_helpers.js", "export const helper = 1;\n")
    _left(project, "notes/tests/app.test.js", "import { helper } from '../test_helpers.js';\n")

    assert clear_the_throwaways_left_behind(project) == []
    assert (project / "notes/test_helpers.js").exists()
