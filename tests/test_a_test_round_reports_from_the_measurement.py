"""A test round reports from the harness's measurement, and a failing test is shown by what it said (LF.1393-LF.1395).

Measured on one medium run's first test round (thorough delivery, 8 of 21 locked tests passing): each failing test
was shown only its runner's heading, so the round read the acceptance files 6 times each, ran the whole suite again
to learn the statuses the saved result held, read the sign-in routes 10 times and wrote a diagnostic script - 46
replies in 36 minutes for 13 failures the harness raises itself after the round, each with its evidence.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

#: A browser runner's failure as its report keeps it: its heading for the test, then the error and the values.
HEADED = (
    "auth.spec.js:23:1 › [AC-1] registration creates a new user ───────────────────────────────\n"
    "\n"
    "    Error: expect(received).toBe(expected) // Object.is equality\n"
    "\n"
    "    Expected: 201\n"
    "    Received: 500\n"
    "\n"
    "      25 |   const response = await registerUser(request, suffix);\n"
    "    > 27 |   expect(response.status()).toBe(201);\n"
    "        at /workspace/app/acceptance/auth.spec.js:27:29\n"
)


# --- LF.1393: what a failed test said, past its runner's heading -------------------------------------------------


def test_a_failing_criterion_s_defect_line_says_what_its_test_got_not_the_runner_s_heading() -> None:
    """The fixer's first line: measured, it was the test's own title, ruled off, and nothing of the 500 it got."""
    from app.graph.acceptance_nodes import the_failed_tests_line

    line = the_failed_tests_line([{"name": "[AC-1] registration creates a new user", "message": HEADED}])

    assert "Expected: 201" in line and "Received: 500" in line
    assert "toBe(expected)" in line
    assert "───" not in line and "auth.spec.js:23:1" not in line


@pytest.mark.parametrize("message, said", [
    ("assert 500 == 201\n +  where 500 = <Response [500]>.status_code", "assert 500 == 201"),
    ("expected 0 notes, found 1", "expected 0 notes, found 1"),
    ("", "failed"),
])
def test_a_message_that_opens_with_its_error_reads_as_before(message, said) -> None:
    from app.graph.acceptance_nodes import the_failed_tests_line

    assert the_failed_tests_line([{"name": "t", "message": message}]) == f"t: {said}"


BRIEF = """# Product Brief: Notes

## Requirements
1. **Features**:
   - Add a note with a title

## Acceptance Criteria
- Add a note with a title
"""


def _fake_runner(root: Path, pack, report_xml: str):
    def run(argv, category, working_directory):
        commands = pack.commands(working_directory)
        if category == "test":
            is_unit = list(argv) == commands["unit_test"]
            target = root / working_directory / (pack.unit_report if is_unit else pack.acceptance_report)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("<testsuites><testcase name='smoke'/></testsuites>" if is_unit else report_xml)
        return {"returncode": "0", "stdout": "", "stderr": ""}

    return run


def test_the_suite_s_result_a_round_reads_says_what_each_failed_test_got(tmp_path) -> None:
    """The round's request: measured, 13 failed tests each shown as its heading, and the suite was run again by hand."""
    from xml.sax.saxutils import escape

    from app.acceptance import suite
    from app.acceptance.criteria import number
    from app.stacks import pack_named
    from app.stacks.scaffold import scaffold

    pack = pack_named("browser-javascript")
    smoke = "<testsuites><testcase name='smoke'/></testsuites>"
    assert scaffold(tmp_path, pack, "notes", "Notes", run=_fake_runner(tmp_path, pack, smoke)).ok
    suite.save_criteria(tmp_path, number(BRIEF))
    spec = tmp_path / "notes/acceptance/notes.spec.js"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("import { test } from '@playwright/test';\ntest('[AC-1] a note is added', async () => {});\n")
    report = ("<testsuites><testsuite><testcase name='[AC-1] a note is added'>"
              f"<failure message='auth.spec.js:23:1 › [AC-1] a note is added'>{escape(HEADED)}</failure>"
              "</testcase></testsuite></testsuites>")

    result = suite.run(tmp_path, runner=_fake_runner(tmp_path, pack, report))

    shown = result.summary()
    assert "Expected: 201; Received: 500" in shown
    assert "───" not in shown


# --- LF.1394 and LF.1395: the round reports, the harness measures, the fixer diagnoses -----------------------------


def _state(root: str) -> dict:
    return {
        "repository": SimpleNamespace(root_path=root),
        "milestone_plan": SimpleNamespace(selected_sprint_goal="Sign-in", milestone_scope=[], delegated_tasks=[]),
        "test_round": 0,
        "specialist_outputs": {},
        "review_defects": [],
        "current_sprint_index": 0,
    }


FAILING = [{"id": "AC-1", "text": "Sign up and sign in", "status": "failed", "tests": []},
           {"id": "AC-13", "text": "Errors answered as JSON", "status": "failed", "tests": []}]


def _a_round(root: str, failing: list, *, unit: tuple = (True, ""), last_run: dict | None = None):
    """The round on a locked suite that ran with `failing` due criteria failing and the unit tests as `unit`; the
    model's round recorded, never asked. Returns (the round's update, the requests the model's round was given)."""
    from app.agents.specialists import ReportedDefect, SpecialistOutput
    from app.graph.workflow import build_workflow_graph

    asked: list[dict] = []

    def the_model_s_round(state, config, **kwargs):
        asked.append(kwargs["initial_request"])
        return {"__test_result__": SpecialistOutput(changed_files=[], defects=[])}

    raised = [] if not failing else [ReportedDefect(
        description="[AC-1] Sign up and sign in - the acceptance suite says this does not work yet.",
        severity="major", reproduction_steps="Run the suite.", expected_behavior="Sign up and sign in",
        actual_behavior="[AC-1] sign up: Expected: 201; Received: 500", affected_files=[], owner="backend")]
    with patch("app.graph.acceptance_nodes.acceptance_for_round", return_value=("The suite's result.\n\n", [])), \
         patch("app.graph.acceptance_nodes.reopen_the_suite_for", return_value=None), \
         patch("app.graph.acceptance_nodes.beyond_repair", return_value=[]), \
         patch("app.graph.acceptance_nodes._failing_due", return_value=(failing, "npm run test:acceptance")), \
         patch("app.graph.workflow._run_unit_tests_procedurally", return_value=unit), \
         patch("app.graph.acceptance_nodes.suite.is_locked", return_value=True), \
         patch("app.graph.acceptance_nodes.suite.last_result", return_value=last_run or {"ran": True, "passed": 8, "failed": 13}), \
         patch("app.agents.specialists.what_the_files_already_prove", return_value=[]), \
         patch("app.graph.acceptance_nodes.interface_defects", return_value=[]), \
         patch("app.graph.acceptance_nodes.pack_contract_defects", return_value=[]), \
         patch("app.graph.acceptance_nodes.failing_due_defects", return_value=raised), \
         patch("app.graph.workflow._run_gated_agent", side_effect=the_model_s_round):
        graph = build_workflow_graph(checkpointer=MemorySaver(), repo_root=root)
        update = graph.nodes["test_and_triage"].bound.invoke(_state(root), {"configurable": {"thread_id": "t",
                                                                                              "run_id": "r"}})
    return update, asked


def _text(request: dict) -> str:
    return "\n".join(str(message.get("content") or "") for message in request.get("messages") or [])


def test_a_red_round_is_told_the_harness_raises_its_failing_criteria_and_their_fixers_find_the_cause(
        tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DELIVERY_MODE", "thorough")
    monkeypatch.delenv("MEASURED_ROUND_WHEN_RED", raising=False)

    _, asked = _a_round(str(tmp_path), FAILING)

    assert len(asked) == 1
    told = _text(asked[0])
    assert "Already reported: the failing criteria above" in told
    assert "(AC-1, AC-13)" in told
    assert "do not work out why they fail" in told
    assert "running the acceptance suite again" in told and "a script to reproduce one" in told
    assert "the unit tests' failures (run them)" in told


def test_a_green_round_s_unit_failures_are_asked_of_the_model_as_before(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DELIVERY_MODE", "thorough")
    monkeypatch.delenv("MEASURED_ROUND_WHEN_RED", raising=False)

    _, asked = _a_round(str(tmp_path), [], unit=(False, "1 failed"), last_run={"ran": True, "passed": 21, "failed": 0})

    assert len(asked) == 1
    assert "Already reported: the failing criteria above" not in _text(asked[0])


def test_the_round_s_new_words_carry_no_product_words() -> None:
    from app.graph.measured_round import the_split

    text = the_split(FAILING)

    assert text
    assert not re.search(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", text, re.I)


def test_with_the_switch_on_a_red_thorough_round_is_the_harness_s_own(tmp_path, monkeypatch) -> None:
    """No model reads the product; the failing criteria are raised from the measurement, as in fast delivery."""
    monkeypatch.setenv("DELIVERY_MODE", "thorough")
    monkeypatch.setenv("MEASURED_ROUND_WHEN_RED", "on")

    update, asked = _a_round(str(tmp_path), FAILING)

    assert asked == []
    raised = [d.description for d in update["remediation"].defects]
    assert any(d.startswith("[AC-1] Sign up and sign in") for d in raised)


def test_with_the_switch_off_a_red_thorough_round_is_the_model_s(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DELIVERY_MODE", "thorough")
    monkeypatch.setenv("MEASURED_ROUND_WHEN_RED", "off")

    _, asked = _a_round(str(tmp_path), FAILING)

    assert len(asked) == 1
