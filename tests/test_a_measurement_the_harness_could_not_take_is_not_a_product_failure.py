"""A measurement the harness could not take is not a product failure.

Deep review 2026-11-18, item A1: the measurement record had test outcomes and a free-text problem, and no "could not
measure" state. The sandbox's own memory refusal ("Not enough memory is free in this container") failed all 18
acceptance criteria of one round, a fix was reverted as "broke 32 tests" and the sprint was planned again; a registry
whose name did not resolve ("Could not resolve host: index.crates.io") was raised as a backend defect and cost 17 model
calls. Now such a measurement judges nothing, reverts nothing and replaces no baseline; it is tried once more first.
"""
from __future__ import annotations

import json
import re
import subprocess

import pytest

from app import ci
from app.acceptance import suite, unmeasured
from app.acceptance.criteria import Criterion
from app.graph import engineering
from app.stacks import contract, pack_named
from app.tools import resources, sandbox

GiB = 1024**3
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
REFUSAL = "Not enough memory is free in this container to run that safely (180 MiB free)."


class Refusing:
    """The sandbox as it answers the harness when the container has no memory to spare: every command refused."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, argv, category, project):
        self.calls.append(category)
        return {"error": REFUSAL, "unmeasured": REFUSAL}


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=h@example.com", "-c", "user.name=h", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def _a_scaffolded_project(root):
    contract.write(root, pack_named("python-http-api"), "app", "Notes")
    (root / "app").mkdir(exist_ok=True)
    (root / "app" / "main.py").write_text("X = 1\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return _git(root, "rev-parse", "HEAD")


def test_the_sandbox_says_a_harness_measurement_refused_for_memory_was_not_measured(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    nearly_full = resources.ResourceState(memory_limit=8 * GiB, memory_in_use=int(7.9 * GiB), memory_peak=int(7.9 * GiB),
                                          oom_kills=0, cpus=2, pids_in_use=10)
    monkeypatch.setattr(resources, "read_resource_state", lambda: nearly_full)

    answered = sandbox.SandboxExecutor.execute(["python", "-m", "pytest"], repo_root=str(tmp_path),
                                               role_name="testing_specialist", category="test", for_the_harness=True)

    assert "Not enough memory" in answered.get("unmeasured", "")


@pytest.mark.parametrize("outcome, reached_tests, not_measured", [
    ({"returncode": "101", "stderr": "error: failed to download\nCould not resolve host: index.crates.io\n"}, False, True),
    ({"returncode": "1", "stderr": "npm ERR! request to https://registry.npmjs.org failed, reason: getaddrinfo EAI_AGAIN"},
     False, True),
    ({"returncode": "1", "stderr": "Could not resolve host: api.example.com"}, True, False),
    ({"returncode": "1", "stderr": "AssertionError: expected 201, got 500"}, False, False),
    ({"returncode": "0", "stdout": "5 passed"}, True, False),
], ids=["registry-name-unresolved", "npm-registry-unresolved", "a-test-that-ran-and-failed-on-its-own-call",
        "an-ordinary-failure", "a-pass"])
def test_what_reads_as_not_measured(outcome, reached_tests, not_measured):
    assert bool(unmeasured.why(outcome, reached_tests=reached_tests)) is not_measured


def test_a_suite_run_the_harness_was_refused_judges_no_criterion_and_keeps_the_last_measurement(tmp_path, monkeypatch):
    _a_scaffolded_project(tmp_path)
    suite.save_criteria(tmp_path, [Criterion("AC-1", "lists notes", "brief"), Criterion("AC-2", "adds one", "brief")])
    last_good = {"ran": True, "passed": 2, "failed": 0, "criteria": {"AC-1": {"status": "passed"}}}
    (tmp_path / suite.RESULT_FILE).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / suite.RESULT_FILE).write_text(json.dumps(last_good))
    monkeypatch.setattr(unmeasured, "RETRY_AFTER_SECONDS", 0)
    refusing = Refusing()

    result = suite.run(tmp_path, runner=refusing)

    assert result.failing() == []
    assert "could not measure" in result.problem and not BANNED.search(result.problem)
    assert suite.last_result(tmp_path) == last_good
    assert refusing.calls.count("test") == 2, "tried once more"
    assert "Not enough memory" in unmeasured.last(tmp_path)


def test_a_fix_the_harness_could_not_measure_is_kept_unjudged(tmp_path, monkeypatch):
    base = _a_scaffolded_project(tmp_path)
    ci.save(tmp_path, ci.Snapshot(label="latest", commit=base, unit={"test_lists": "passed"}, unit_ran=True))
    (tmp_path / "app" / "main.py").write_text("X = 2\n")  # the fix
    monkeypatch.setattr(unmeasured, "RETRY_AFTER_SECONDS", 0)
    monkeypatch.setattr("app.stacks.scaffold.sandbox_runner", lambda root: Refusing())
    monkeypatch.setattr("app.analysis.language_service.underlined_in", lambda *a, **k: {})

    broke = engineering.after_a_fix(str(tmp_path), base, "defect_fix_1_1", "add a note")

    assert broke == []
    assert (tmp_path / "app" / "main.py").read_text() == "X = 2\n"
    assert ci.load(tmp_path, "latest").unit == {"test_lists": "passed"}, "the last measurement stays the baseline"


def test_an_install_refused_is_tried_again_at_the_next_measurement(tmp_path):
    _a_scaffolded_project(tmp_path)
    refusing = Refusing()

    first = contract.install_if_the_manifests_changed(tmp_path, refusing)
    asked_before = len(refusing.calls)
    contract.install_if_the_manifests_changed(tmp_path, refusing)

    assert first and not any(contract.INSTALL_FAILED in note for note in first), "not raised as the manifest's fault"
    assert not BANNED.search(" ".join(first))
    assert len(refusing.calls) > asked_before, "not recorded as installed"


def test_a_unit_run_the_harness_could_not_take_is_unknown_not_failed(tmp_path, monkeypatch):
    from app.graph import workflow

    _a_scaffolded_project(tmp_path)
    monkeypatch.setattr(unmeasured, "RETRY_AFTER_SECONDS", 0)
    monkeypatch.setattr("app.stacks.scaffold.sandbox_runner", lambda root: Refusing())

    passed, said = workflow._run_unit_tests_procedurally(str(tmp_path))

    assert passed is None
    assert "could not measure" in said and not BANNED.search(said)


def test_a_round_whose_measurement_could_not_be_taken_charges_no_attempt(tmp_path):
    from workflow_nodes import a_test_round, reported

    def refused_twice(state):
        unmeasured.record(tmp_path, "acceptance suite", REFUSAL)  # as the suite's own run records it
        return "", []

    update, _ = a_test_round(tmp_path, [reported("Every criterion fails")],
                             patches={"app.graph.acceptance_nodes.acceptance_for_round": refused_twice})

    assert update["remediation"].attempt == 0
