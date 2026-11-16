"""Unit tests that do not compile are a failure the release names, not "nothing failing" (found on a language sweep).

Measured on one run (a Rust service, 9/9 hidden): the project's unit tests did not compile at release (a test client
the web framework does not have), the runner wrote no report, and `ci.unit_failures` read "no report" as "none
failing" - so the release named nothing, and an escalation that accepted the sprint recorded no open unit test.
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


class Runner:
    def __init__(self, root, unit_compiles=True):
        self.root, self.unit_compiles = root, unit_compiles

    def __call__(self, argv, category, working_directory):
        if category == "test":
            unit = list(argv) == PACK.commands(working_directory)["unit_test"]
            if unit and not self.unit_compiles:
                return {"returncode": "101", "stdout": "", "stderr": "error[E0433]: could not find `TestClient`"}
            target = self.root / working_directory / (PACK.unit_report if unit else PACK.acceptance_report)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("<testsuites><testsuite><testcase name='adds'/></testsuite></testsuites>")
        return {"returncode": "0", "stdout": "", "stderr": ""}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    initialise_repository(tmp_path)
    assert scaffold(tmp_path, PACK, "notes", "Notes", run=Runner(tmp_path)).ok
    suite.save_criteria(tmp_path, number("# Brief\n## Features\n- Add a note\n"))
    return SimpleNamespace(root=tmp_path)


def test_a_unit_run_that_failed_with_no_report_is_named_as_failing(workspace):
    failing = ci.unit_failures(workspace.root, Runner(workspace.root, unit_compiles=False))
    assert failing == [ci.UNIT_TESTS_DID_NOT_RUN]


def test_the_accepted_state_holds_it_open_too(workspace, monkeypatch):
    snapshot = ci.take(workspace.root, "accepted", runner=Runner(workspace.root, unit_compiles=False))
    assert snapshot.unit == {ci.UNIT_TESTS_DID_NOT_RUN: "failed"}


def test_a_passing_run_and_a_run_that_cannot_start_are_as_before(workspace):
    assert ci.unit_failures(workspace.root, Runner(workspace.root)) == []
    assert ci.unit_failures(workspace.root, lambda *args: None) == []
