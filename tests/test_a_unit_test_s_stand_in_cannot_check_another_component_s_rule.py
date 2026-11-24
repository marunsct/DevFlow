"""A unit test that stands a component in cannot check that component's rule (LF.1312).

Measured over the last 60 scored runs: 12 (8 families) shipped their own unit tests failing or set aside while every
hidden test passed; on one it cost the "deliverable" verdict. There a controller slice test replaced the service with a
stand-in and asserted that an empty title is refused with 400; the rule lives in the service, the controller answered
201, and the test could never pass - while the product refused the empty title and the locked acceptance tests passed.
The fixes in tests-only mode did not repair it.

So whoever writes unit tests is told what a test with a stand-in can check, and a fixer of such a failing test is shown
the evidence: the acceptance test that refuses the same input passes, and the stand-in that hides the rule.
"""

from __future__ import annotations

import json
import re
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance.junit import TestResult

import the_fix_stage

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
EFFECTS = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "effects.py"

JAVA_SLICE_TEST = """package app.notes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(NotesController.class)
class NotesControllerTest {
    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private NoteService noteService;

    @Test
    void createNote_emptyTitle_returns400() throws Exception {
        mvc.perform(post("/notes").contentType(JSON).content("{\\"title\\":\\"\\"}")).andExpect(status().isBadRequest());
    }

    @Test
    void updateNote_invalidTitle_returns400() throws Exception {
        mvc.perform(put("/notes/1").contentType(JSON).content("{\\"title\\":\\"\\"}")).andExpect(status().isBadRequest());
    }
}
"""
JAVA_TEST_PATH = "notes-api/src/test/java/app/notes/NotesControllerTest.java"

PYTHON_PATCHED_TEST = """from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


@patch("app.service.validate_title")
def test_create_rejects_an_empty_title(validate):
    response = TestClient(app).post("/notes", json={"title": ""})
    assert response.status_code == 422
"""

JS_MOCKED_TEST = """const request = require('supertest');
jest.mock('../src/validation');
const app = require('../src/app');

describe('notes', () => {
  it('rejects an empty title', async () => {
    const res = await request(app).post('/notes').send({ title: '' });
    expect(res.status).toBe(400);
  });
});
"""

#: The locked suite's last run: the product refuses an empty title, among its other tests.
ACCEPTANCE = {
    "AC-1": ("A note is created with a title and a body", [("AC-1 creates a note and lists it", "passed")]),
    "AC-2": ("A note without a title is refused", [("AC-2 a note with an empty title is refused with 400", "passed")]),
    "AC-3": ("A note is updated", [("AC-3 updates a note's body", "passed")]),
    "AC-4": ("A note is deleted", [("AC-4 deletes a note", "passed")]),
}


def _workspace(root: Path, files: dict[str, str], acceptance=ACCEPTANCE) -> Path:
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text, encoding="utf-8")
    result = {"ran": True, "passed": 4, "failed": 0, "criteria": {
        criterion: {"id": criterion, "text": text, "status": "passed",
                    "tests": [{"name": name, "outcome": outcome, "message": ""} for name, outcome in tests]}
        for criterion, (text, tests) in acceptance.items()}}
    (root / ".harness").mkdir(exist_ok=True)
    (root / ".harness" / "acceptance-result.json").write_text(json.dumps(result), encoding="utf-8")
    return root


def _unit_defect(*failing: TestResult):
    """The defect the harness raises for a failing unit run, from the runner's report it lists."""
    from app import ci
    from app.graph import workflow

    output = "[ERROR] Tests run: 3, Failures: 2\n" + ci.what_the_failing_unit_tests_say(list(failing))
    raised = workflow._the_unit_tests_fail(SimpleNamespace(delegated_tasks=[]), output, beside_a_green_suite=True)
    return the_fix_stage.a_defect(raised.description, actual_behavior=raised.actual_behavior, affected_files=[],
                                  owner="backend")


def _java_failures(message: str = "Status expected:<400> but was:<201>"):
    return [TestResult(name="createNote_emptyTitle_returns400", suite="app.notes.NotesControllerTest",
                       outcome="failed", message=message),
            TestResult(name="updateNote_invalidTitle_returns400", suite="app.notes.NotesControllerTest",
                       outcome="failed", message="Status expected:<400> but was:<200>")]


# --- the fixer is shown the evidence ----------------------------------------------------------------------------


def test_a_slice_test_whose_mocked_service_keeps_the_rule_is_shown_to_its_fixer_with_the_passing_acceptance_test(
        tmp_path):
    root = _workspace(tmp_path, {JAVA_TEST_PATH: JAVA_SLICE_TEST})
    defect = _unit_defect(*_java_failures())

    _, seen = the_fix_stage.run(root, the_fix_stage.a_state(root, defect))

    [request] = seen.requests
    assert "A stand-in hides the rule this unit test expects" in request
    shown = request.split("A stand-in hides the rule this unit test expects", 1)[1]
    assert "AC-2 a note with an empty title is refused with 400" in shown
    assert "already refuses" in shown
    assert "`NoteService`" in shown and "NotesControllerTest.java" in shown
    assert "createNote_emptyTitle_returns400" in shown and "updateNote_invalidTitle_returns400" in shown
    assert "where it lives" in shown and "without the stand-in" in shown
    assert not BANNED.search(shown), shown


@pytest.mark.parametrize("path, source, failing, replaced", [
    ("notes/tests/test_notes.py", PYTHON_PATCHED_TEST,
     TestResult(name="test_create_rejects_an_empty_title", file="tests/test_notes.py", outcome="failed",
                message="assert 201 == 422\n +  where 201 = <Response [201 Created]>.status_code"),
     "app.service.validate_title"),
    ("notes/test/notes.test.js", JS_MOCKED_TEST,
     TestResult(name="rejects an empty title", within="notes", outcome="failed",
                message="expect(received).toBe(expected) // Object.is equality\n\nExpected: 400\nReceived: 201"),
     "../src/validation"),
], ids=["python-patched-validator", "javascript-mocked-module"])
def test_a_test_that_patches_the_validator_away_is_shown_the_same_evidence(tmp_path, path, source, failing, replaced):
    root = _workspace(tmp_path, {path: source})

    from app.analysis import stand_in_tests

    shown = stand_in_tests.for_a_fixer(root, _unit_defect(failing))

    assert "AC-2 a note with an empty title is refused with 400" in shown
    assert f"`{replaced}`" in shown and Path(path).name in shown


@pytest.mark.parametrize("acceptance, source, message", [
    # The product really lets the empty title through: its acceptance test fails.
    ({**ACCEPTANCE, "AC-2": ("A note without a title is refused",
                             [("AC-2 a note with an empty title is refused with 400", "failed")])},
     JAVA_SLICE_TEST, "Status expected:<400> but was:<201>"),
    # The test replaces nothing: it runs the real service and still gets a success.
    (ACCEPTANCE, JAVA_SLICE_TEST.replace("    @MockitoBean\n    private NoteService noteService;\n", ""),
     "Status expected:<400> but was:<201>"),
    # It did not expect a refusal: the product failed where it should have served.
    (ACCEPTANCE, JAVA_SLICE_TEST, "Status expected:<201> but was:<500>"),
    # No acceptance test refuses that input.
    ({key: value for key, value in ACCEPTANCE.items() if key != "AC-2"}, JAVA_SLICE_TEST,
     "Status expected:<400> but was:<201>"),
], ids=["the-product-lets-it-through", "no-stand-in", "not-a-refusal", "no-acceptance-test-refuses-it"])
def test_a_unit_test_failing_for_a_real_product_fault_is_given_no_such_section(tmp_path, acceptance, source, message):
    root = _workspace(tmp_path, {JAVA_TEST_PATH: source}, acceptance)
    failing = [TestResult(name="createNote_emptyTitle_returns400", suite="app.notes.NotesControllerTest",
                          outcome="failed", message=message)]

    _, seen = the_fix_stage.run(root, the_fix_stage.a_state(root, _unit_defect(*failing)))

    assert "A stand-in hides the rule" not in seen.requests[0]


def test_a_defect_that_is_not_about_the_unit_tests_is_given_no_such_section(tmp_path):
    root = _workspace(tmp_path, {JAVA_TEST_PATH: JAVA_SLICE_TEST})
    listed = _unit_defect(*_java_failures())
    defect = the_fix_stage.a_defect("AC-2 a note with an empty title is refused with 400 fails",
                                    actual_behavior=listed.description, failing_criteria=["AC-2"])

    _, seen = the_fix_stage.run(root, the_fix_stage.a_state(root, defect))

    assert "A stand-in hides the rule" not in seen.requests[0]


def test_the_effects_report_counts_a_fixer_shown_the_stand_in(tmp_path):
    root = _workspace(tmp_path, {JAVA_TEST_PATH: JAVA_SLICE_TEST})
    from app.analysis import stand_in_tests

    shown = stand_in_tests.for_a_fixer(root, _unit_defect(*_java_failures()))
    record = {"kind": "model_request", "messages": [{"role": "user", "content": "the fix request" + shown}]}

    lines = "\n".join(runpy.run_path(str(EFFECTS))["effects"]([record], ""))

    assert "   1  LF.1312 a unit test's stand-in shown hiding a rule the product keeps" in lines


# --- whoever writes or repairs unit tests is told the rule ---------------------------------------------------------


def test_the_testing_builder_is_told_what_a_test_with_a_stand_in_can_check():
    from app.agents.specialists import _system_prompt

    told = " ".join(_system_prompt("testing").split())

    assert "replaces a component with a stand-in" in told and "tested where it lives" in told


def test_the_acceptance_suite_s_writer_is_not_told_the_stand_in_rule():
    from app.agents.specialists import _system_prompt

    assert "replaces a component with a stand-in" not in " ".join(_system_prompt("testing", writing_the_suite=True).split())


def test_a_test_file_s_draft_is_told_the_rule_and_a_product_file_s_is_not(tmp_path):
    from app.graph import drafting

    order = SimpleNamespace(task_description="Notes endpoints and their tests")

    test_draft = drafting.draft_request(tmp_path, JAVA_TEST_PATH, order, None, None)
    code_draft = drafting.draft_request(tmp_path, "notes-api/src/main/java/app/notes/NotesController.java", order,
                                        None, None)

    assert "replaces a component with a stand-in" in test_draft
    assert "replaces a component with a stand-in" not in code_draft


def test_a_fixer_held_to_test_files_is_told_a_stand_in_s_check_moves_to_the_component_s_own_test():
    from app.tools import tests_only_writes

    tests_only_writes.hold("run-1", "defect_fix_3_0")
    try:
        told = tests_only_writes.briefing("run-1", "defect_fix_3_0")
    finally:
        tests_only_writes.release("run-1", "defect_fix_3_0")

    assert "stand-in can never pass" in told and "component's own test" in told
    assert not BANNED.search(told), told


def test_the_java_pack_s_guide_says_a_slice_test_checks_the_controller_only():
    from app.stacks.packs.java_spring_api import GUIDE

    assert "`@MockitoBean` stand-in" in GUIDE and "service's own JUnit test" in GUIDE


def test_the_stand_in_rules_avoid_the_banned_words():
    from app.agents.stand_in_rule import FOR_A_FIXER, FOR_TEST_WRITERS
    from app.stacks.packs.java_spring_api import GUIDE

    for text in (FOR_TEST_WRITERS, FOR_A_FIXER, GUIDE):
        assert not BANNED.search(text), text
