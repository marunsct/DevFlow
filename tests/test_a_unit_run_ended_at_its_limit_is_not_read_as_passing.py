"""A unit run ended at the sandbox's time limit is a failure named as such, not "nothing failing" (LF.1642).

Measured on a service run: the harness's unit runs were ended at the 300-second limit four times, each wrote no report,
and the run was kept as no outcomes - which `ci.unit_failures` read as none failing, so a check of what a fix broke
saw nothing broken while no unit test had finished.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import ci
from app.acceptance import suite
from app.acceptance.criteria import number
from app.stacks import pack_named
from app.stacks.scaffold import scaffold
from app.tools.version_control import initialise_repository

PACK = pack_named("browser-javascript")

#: How each sandbox answers a command it ended at its limit: a container of its own, and this container.
IN_ITS_OWN_CONTAINER = {"error": "Command timed out after 300 seconds; it was ended at the time limit.",
                        "stdout": "✔ adds a note (3.1ms)\n✖ lists the notes (20004.7ms)\n", "stderr": ""}
IN_THIS_CONTAINER = {**IN_ITS_OWN_CONTAINER, "returncode": "124"}


class Runner:
    def __init__(self, root, unit_answer=None):
        self.root, self.unit_answer = root, unit_answer

    def __call__(self, argv, category, working_directory):
        if category == "test":
            unit = list(argv) == PACK.commands(working_directory)["unit_test"]
            if unit and self.unit_answer is not None:
                return dict(self.unit_answer)
            target = self.root / working_directory / (PACK.unit_report if unit else PACK.acceptance_report)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("<testsuites><testsuite><testcase name='adds'/></testsuite></testsuites>")
        return {"returncode": "0", "stdout": "", "stderr": ""}


@pytest.fixture
def workspace(tmp_path):
    initialise_repository(tmp_path)
    assert scaffold(tmp_path, PACK, "notes", "Notes", run=Runner(tmp_path)).ok
    suite.save_criteria(tmp_path, number("# Brief\n## Features\n- Add a note\n"))
    return SimpleNamespace(root=tmp_path)


@pytest.mark.parametrize("ended", [IN_ITS_OWN_CONTAINER, IN_THIS_CONTAINER], ids=["own container", "this container"])
def test_a_unit_run_ended_at_its_limit_is_named_as_not_finishing(workspace, ended):
    assert ci.unit_failures(workspace.root, Runner(workspace.root, ended)) == [ci.UNIT_TESTS_DID_NOT_FINISH]


def test_the_measured_state_holds_it_as_failed(workspace):
    snapshot = ci.take(workspace.root, "after a fix", runner=Runner(workspace.root, IN_ITS_OWN_CONTAINER))

    assert snapshot.unit == {ci.UNIT_TESTS_DID_NOT_FINISH: "failed"}


def test_the_test_round_s_kept_run_is_read_as_not_finishing(workspace, monkeypatch):
    """The test round's own run and every later reading of the same product say the same."""
    from app.graph.workflow import _run_unit_tests_procedurally
    from app.stacks import scaffold as scaffolding

    monkeypatch.setenv("MEASURE_ONCE", "on")
    monkeypatch.setattr(scaffolding, "sandbox_runner", lambda root: Runner(workspace.root, IN_ITS_OWN_CONTAINER))
    passed, said = _run_unit_tests_procedurally(str(workspace.root))

    def nothing_runs_again(argv, category, working_directory):
        if category == "test":
            raise AssertionError("the kept run stands for the same product")
        return {"returncode": "0", "stdout": "", "stderr": ""}

    assert passed is False and "lists the notes" in said
    assert ci.unit_failures(workspace.root, nothing_runs_again) == [ci.UNIT_TESTS_DID_NOT_FINISH]


def test_the_defect_for_it_is_not_typed_a_build_that_failed(workspace, monkeypatch):
    """A run ended at its limit wrote no report, as a build that failed writes none; it is a test that did not end.

    What the product logged while the tests ran is in the output, an error line among it."""
    from app.graph.workflow import _run_unit_tests_procedurally, _the_failing_unit_tests, _the_unit_tests_fail
    from app.sprint import cause
    from app.stacks import scaffold as scaffolding

    monkeypatch.setenv("MEASURE_ONCE", "on")
    logged = {**IN_THIS_CONTAINER, "stdout": IN_THIS_CONTAINER["stdout"] + "TypeError: db.prepare is not a function\n"}
    monkeypatch.setattr(scaffolding, "sandbox_runner", lambda root: Runner(workspace.root, logged))
    _, said = _run_unit_tests_procedurally(str(workspace.root))

    defect = _the_unit_tests_fail(None, said, failing=_the_failing_unit_tests(str(workspace.root)))

    assert defect.kind != cause.COMPILE_ERROR
