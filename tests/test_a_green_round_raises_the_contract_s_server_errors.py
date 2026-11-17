"""A green test round runs the interface contract's checks and raises a 5xx as a defect, settled by the same checks.

Measured on one run: a bare `POST /notes` and `PUT /notes/:id` - no body - answered 500 on a green suite; the checks
ran only at release, so the crash shipped as a gap no fixer was given.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.acceptance import interface_contract as ic
from app.agents.specialists import SpecialistOutput
from app.graph import acceptance_nodes, workflow
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
LINES = ["AC-14 GET /health -> 200", "AC-11 PUT /notes/:id -> 404", "AC-11 POST /notes -> 400"]
REPORT = (
    '<testsuites><testsuite name="c" tests="3">'
    '<testcase name="[AC-14] contract 1: AC-14 GET /health -&gt; 200"/>'
    '<testcase name="[AC-11] contract 2: AC-11 PUT /notes/:id -&gt; 404"><failure message="x">Expected: 404\nReceived: 500</failure></testcase>'
    '<testcase name="[AC-11] contract 3: AC-11 POST /notes -&gt; 400"><failure message="x">Expected: 400\nReceived: {posted}</failure></testcase>'
    "</testsuite></testsuites>"
)


def _project(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(files={"playwright.config.js": ""}, probe_runner="playwright"), {"project": "app"}))
    (tmp_path / "app").mkdir()
    ic.record_at_lock(tmp_path, LINES)


def _runner(tmp_path, posted):
    def run(argv, category, where):
        (tmp_path / where / "test-results").mkdir(exist_ok=True)
        (tmp_path / where / ic.REPORT_FILE).write_text(REPORT.format(posted=posted))
        return {"returncode": "1"}
    return run


def test_each_5xx_is_named_without_its_criterion_and_a_4xx_is_not(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    errors = ic.server_errors(tmp_path, runner=_runner(tmp_path, 422))
    assert [(c.method, c.path, s) for c, s in errors] == [("PUT", "/notes/999999999", 500)]
    text = ic.server_error_description(errors)
    assert text.startswith(ic.SERVER_FAILED) and "answered 500 where the contract gives 404" in text
    assert "AC-" not in text  # judged by the checks, never by the criterion's tests
    assert not BANNED.search(text)
    assert ic.still_raised(tmp_path, text, runner=_runner(tmp_path, 422)) is True
    assert ic.still_raised(tmp_path, text, runner=lambda argv, c, where: (
        (tmp_path / where / "test-results").mkdir(exist_ok=True),
        (tmp_path / where / ic.REPORT_FILE).write_text(REPORT.replace("Received: 500", "Received: 404").format(posted=400)),
    )) is False
    assert ic.still_raised(tmp_path, "something else", runner=_runner(tmp_path, 500)) is None


def test_a_green_round_adds_the_defect_behind_the_switch(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    monkeypatch.setattr(acceptance_nodes.suite, "is_locked", lambda root: True)
    monkeypatch.setattr(ic, "server_errors", lambda root, runner=None: [(ic.parse([LINES[2]])[0][0], 500)])
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}
    green = SpecialistOutput(changed_files=[], defects=[], decisions=[])
    milestone = SimpleNamespace(delegated_tasks=[], milestone_scope=[])

    monkeypatch.setenv("CONTRACT_SERVER_ERRORS_AT_A_ROUND", "on")
    raised = workflow._with_the_contract_s_server_errors(state, green, milestone).defects
    assert len(raised) == 1 and "`POST /notes` sent with no body answered 500" in raised[0].description
    assert workflow._the_suite_already_guards_it.__doc__  # the checks are its regression test (see below)

    monkeypatch.setenv("CONTRACT_SERVER_ERRORS_AT_A_ROUND", "off")
    assert workflow._with_the_contract_s_server_errors(state, green, milestone).defects == []


@pytest.mark.parametrize("failing_due, failed, passed, asked", [
    ([], 0, 10, True),
    (["AC-2"], 1, 9, True),  # near green, the product answering: measured, a 500 shipped from a 9-of-10 round
    (["AC-2"], 1, 0, False),
    (["AC-2", "AC-3", "AC-4"], 3, 7, False),
], ids=["green", "near-green", "nothing-answered", "red"])
def test_the_round_asks_it_when_the_suite_is_green_or_near(tmp_path, monkeypatch, failing_due, failed, passed, asked):
    from workflow_node_stubs import a_reported_defect, run_a_test_round

    def with_a_crash(state, result, milestone):
        return result.model_copy(update={"defects": [*result.defects, a_reported_defect(f"{ic.SERVER_FAILED} POST /notes")]})

    seen = run_a_test_round(monkeypatch, tmp_path, failing_due=failing_due, saved_run={"ran": True, "failed": failed, "passed": passed},
                            found=[a_reported_defect("[AC-1] The list is empty")],
                            overrides={"app.graph.workflow._with_the_contract_s_server_errors": with_a_crash})

    raised = [d.description for d in seen.update["remediation"].defects]
    assert any(d.startswith(ic.SERVER_FAILED) for d in raised) is asked


@pytest.mark.parametrize("raised", [True, False])
def test_the_settlement_asks_the_checks_again(tmp_path, monkeypatch, raised):
    """A server error at the contract's checks is settled by those checks, run again - on the fix's own re-measure and
    on the snapshot the fix's measurement took."""
    crash = SimpleNamespace(description=f"{ic.SERVER_FAILED} POST /notes", affected_files=[])
    asked = []
    monkeypatch.setattr(ic, "still_raised", lambda root, description, **k: asked.append(description) or raised)
    monkeypatch.setattr(contract, "enforce", lambda root: None)
    monkeypatch.setattr(workflow, "_settled_by_its_own_probe", lambda root, defect: workflow._NOT_A_PROBE_S)

    assert workflow._the_defect_s_tests_pass(tmp_path, crash) is (not raised)
    assert workflow._the_defect_s_tests_in(str(tmp_path), "after defect_fix_1_0", crash) is (not raised)
    assert asked == [crash.description, crash.description]


def test_the_checks_are_its_regression_test(tmp_path, monkeypatch):
    """A fixed server error needs no named regression test: the checks run at every green round and at release."""
    crash = SimpleNamespace(description=f"{ic.SERVER_FAILED} POST /notes", affected_files=[])
    monkeypatch.setattr(workflow, "_the_defect_s_tests_in", lambda root, label, defect: True)
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}

    assert workflow._the_suite_already_guards_it(state, "after defect_fix_1_0", crash) is True
    assert workflow._the_suite_already_guards_it(
        state, "after defect_fix_1_0", SimpleNamespace(description="The page looks cramped", affected_files=[])) is False
