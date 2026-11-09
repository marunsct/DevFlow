"""A kept fix's measurement stands for the next fix: the product it measured is not tested again.

Found in a code review of the defect-fix loop: `after_a_fix` saved its snapshot with the commit before the fix's own,
then committed, so the next fix's `before_a_fix` read "the workspace moved since it was measured" and ran the unit
tests and the acceptance suite again on the product just measured - one more full test run per fix stage. The test
round kept its unit run with the product's fingerprint (MEASURE_ONCE) as well, but no CI snapshot consulted it, so
every snapshot ran the unit tests again on an unchanged product.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app import ci
from app.acceptance import suite
from app.acceptance.criteria import number
from app.graph import engineering, workflow
from app.stacks import pack_named
from app.stacks.scaffold import scaffold
from app.tools.version_control import initialise_repository

PACK = pack_named("browser-javascript")
BRIEF = "# Brief\n## Features\n- Add a note\n- Delete a note\n"


class Runner:
    """Writes the report each command would have written, and counts the unit and acceptance runs."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.unit: dict[str, str] = {"adds": "passed"}
        self.acceptance: dict[str, str] = {"[AC-1] adds": "passed", "[AC-2] deletes": "failed"}
        self.runs: list[str] = []

    def __call__(self, argv, category, working_directory):
        if category == "test":
            unit = list(argv) == PACK.commands(working_directory)["unit_test"]
            self.runs.append("unit" if unit else "acceptance")
            tests = self.unit if unit else self.acceptance
            cases = "".join(
                f"<testcase name='{name}'>" + ("<failure message='no'/>" if outcome == "failed" else "") + "</testcase>"
                for name, outcome in tests.items()
            )
            target = self.root / working_directory / (PACK.unit_report if unit else PACK.acceptance_report)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"<testsuites><testsuite>{cases}</testsuite></testsuites>")
        return {"returncode": "0", "stdout": "", "stderr": ""}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    initialise_repository(tmp_path)
    runner = Runner(tmp_path)
    smoke = Runner(tmp_path)
    smoke.acceptance = {"smoke": "passed"}
    assert scaffold(tmp_path, PACK, "notes", "Notes", run=smoke).ok
    suite.save_criteria(tmp_path, number(BRIEF))
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("test('[AC-1] adds', ()=>{});\ntest('[AC-2] deletes', ()=>{});\n")
    suite.lock(tmp_path)
    monkeypatch.setattr("app.stacks.scaffold.sandbox_runner", lambda root: runner)
    monkeypatch.setenv("MEASURE_ONCE", "on")
    return SimpleNamespace(root=tmp_path, runner=runner)


def test_the_snapshot_of_a_kept_fix_names_the_fix_s_own_commit(workspace) -> None:
    root = str(workspace.root)
    base = engineering.before_a_fix(root, "defect_fix_1_0")
    (workspace.root / "notes" / "src" / "main.js").write_text("// fixed\n")
    workspace.runner.acceptance = {"[AC-1] adds": "passed", "[AC-2] deletes": "passed"}

    assert engineering.after_a_fix(root, base, "defect_fix_1_0", "Delete does nothing") == []

    assert ci.head(root) != base
    assert ci.load(root, "latest").commit == ci.head(root)


def test_the_next_fix_does_not_test_the_product_the_last_fix_measured(workspace) -> None:
    root = str(workspace.root)
    base = engineering.before_a_fix(root, "defect_fix_1_0")
    (workspace.root / "notes" / "src" / "main.js").write_text("// fixed\n")
    workspace.runner.acceptance = {"[AC-1] adds": "passed", "[AC-2] deletes": "passed"}
    assert engineering.after_a_fix(root, base, "defect_fix_1_0", "Delete does nothing") == []
    workspace.runner.runs.clear()

    engineering.before_a_fix(root, "defect_fix_1_1")

    assert workspace.runner.runs == []


def test_a_snapshot_of_an_unchanged_product_reads_the_unit_run_kept(workspace) -> None:
    root = str(workspace.root)
    ci.commit(root, "the product")
    workspace.runner.runs.clear()

    first = ci.take(root, "one")
    second = ci.take(root, "two")

    assert workspace.runner.runs.count("unit") == 1
    assert second.unit == first.unit and second.unit_ran


def test_the_test_round_s_unit_run_stands_for_the_next_snapshot(workspace) -> None:
    root = str(workspace.root)
    ci.commit(root, "the product")
    workspace.runner.runs.clear()

    passed, _ = workflow._run_unit_tests_procedurally(root)
    snapshot = ci.take(root, "after the round")

    assert passed is True
    assert workspace.runner.runs.count("unit") == 1
    assert snapshot.unit == {"adds": "passed"} and snapshot.unit_ran


def test_a_changed_product_s_unit_tests_run_again(workspace) -> None:
    root = str(workspace.root)
    ci.commit(root, "the product")
    workspace.runner.runs.clear()

    ci.take(root, "one")
    (workspace.root / "notes" / "src" / "main.js").write_text("// changed\n")
    workspace.runner.unit = {"adds": "failed"}
    after = ci.take(root, "two")

    assert workspace.runner.runs.count("unit") == 2
    assert after.unit == {"adds": "failed"}


def test_off_every_snapshot_runs_the_unit_tests(workspace, monkeypatch) -> None:
    monkeypatch.setenv("MEASURE_ONCE", "off")
    root = str(workspace.root)
    ci.commit(root, "the product")
    workspace.runner.runs.clear()

    ci.take(root, "one")
    ci.take(root, "two")

    assert workspace.runner.runs.count("unit") == 2
