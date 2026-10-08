"""A scaffold whose smoke test failed once was left to the agents, its files unkept.

Measured on one run, started a minute after the worker was recreated: the
acceptance smoke test of a pack every other run proves failed once (0 passed, 1
failed), the scaffold was recorded as "left to the agents", and its files stayed
in the workspace with no contract behind them - "the harness keeps this" in
their own comments, and nothing kept them. A later sprint's tester switched the
next sprint's tests off in the runner configuration, nothing put it back, and
those criteria were then judged beyond repair.

The smoke test now gets one retry, as the install already did.
"""

from __future__ import annotations

from pathlib import Path

from app.stacks import contract, pack_named
from app.stacks.scaffold import scaffold

PASSED = "<testsuites><testcase name='smoke'/></testsuites>"
FAILED = "<testsuites><testcase name='smoke'><failure message='no'>no</failure></testcase></testsuites>"


def _runner(root: Path, pack, acceptance_failures: int):
    """Unit smoke passes; the acceptance smoke fails the first `acceptance_failures` times."""
    left = {"failures": acceptance_failures}

    def run(argv, category, working_directory):
        commands = pack.commands(working_directory)
        if category != "test":
            return {"returncode": "0", "stdout": "", "stderr": ""}
        unit = list(argv) == commands["unit_test"]
        target = root / working_directory / (pack.unit_report if unit else pack.acceptance_report)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not unit and left["failures"] > 0:
            left["failures"] -= 1
            target.write_text(FAILED)
            return {"returncode": "1", "stdout": "", "stderr": ""}
        target.write_text(PASSED)
        return {"returncode": "0", "stdout": "", "stderr": ""}

    return run


def test_a_smoke_test_that_fails_once_is_tried_again(tmp_path: Path) -> None:
    pack = pack_named("browser-javascript")

    result = scaffold(tmp_path, pack, "notes", "Notes", run=_runner(tmp_path, pack, acceptance_failures=1))

    assert result.ok, result.problem
    assert contract.read(tmp_path) is not None


def test_a_smoke_test_that_fails_twice_is_not_a_scaffold(tmp_path: Path) -> None:
    pack = pack_named("browser-javascript")

    result = scaffold(tmp_path, pack, "notes", "Notes", run=_runner(tmp_path, pack, acceptance_failures=2))

    assert not result.ok
    assert "acceptance smoke test did not pass" in result.problem
    assert contract.read(tmp_path) is None
