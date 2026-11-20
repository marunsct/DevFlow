"""A harness probe's finding at a green round is the product's to fix, even when it is merged with failing unit tests.

Measured on one run (a C# notes service): at a green round the server-error probe found `GET /notes` answering 500
and the edge probe found a title sent as a number answering 500 - one cause, a store read before any write fails, the
same one four unit tests failed on. The findings were merged under "The unit tests fail", so the fixer was told the
product already does what the specification asks and was allowed to write tests only; the sprint then settled as
"only the unit tests fail", and the release was not deliverable on the very findings the round had made.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.agents.specialists import ReportedDefect
from app.graph import defect_fix_modes, settle_when_green
from app.graph.workflow import _one_defect_per_cause
from app.sprint import Defect, RemediationCycle
from app.tools import tests_only_writes

SERVER_FAILED = "The server fails on a request it should answer or refuse:"
UNIT = ("The unit tests fail. It says:\n- 4 failing, e.g. `NotesApiTests.ListNotes_Empty_ReturnsEmptyArray`: "
        "`GET /notes` answered InternalServerError where OK was expected")
PROBE = f"{SERVER_FAILED} `GET /notes` sent with no body answered 500 where the contract gives 200."
MERGED_UNDER_THE_UNIT_TESTS = f"{UNIT}\n\nThe same problem, as other checks reported it:\n- [test round] {PROBE}"
EDGE = ("Requests at the edges of the interface contract are not handled: `POST /notes` with `title` a number (12345) "
        "answered 500.")
RUN, STAGE = "run-1", "defect_fix_2_0"


def _reported(description: str, **fields) -> ReportedDefect:
    return ReportedDefect(description=description, severity="major", reproduction_steps="r", expected_behavior="e",
                          actual_behavior="a", affected_files=[], owner="backend", **fields)


def _open(description: str, **fields) -> Defect:
    return Defect(description=description, severity="major", reproduction_steps="r", expected_behavior="e",
                  actual_behavior="a", owner="backend", **fields)


def test_a_probe_finding_leads_the_failing_unit_tests_it_is_merged_with() -> None:
    unit = _reported(UNIT)
    probe = _reported(PROBE, kind="probe_finding", evidence=[{"probe": "contract, no body", "request": "GET /notes"}])

    merged = _one_defect_per_cause([unit, probe])

    assert len(merged) == 1
    assert merged[0].description.startswith(SERVER_FAILED)
    assert "The unit tests fail." in merged[0].description
    assert merged[0].kind == "probe_finding"


@pytest.fixture
def green_suite(tmp_path, monkeypatch):
    monkeypatch.setenv("SETTLE_WHEN_ACCEPTANCE_IS_GREEN", "on")
    path = tmp_path / suite.RESULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ran": True, "passed": 10, "failed": 0}))
    return tmp_path


@pytest.mark.parametrize("open_defect", [
    _open(MERGED_UNDER_THE_UNIT_TESTS, status="open"),
    _open(UNIT, status="open", evidence=[{"test": "ListNotes_Empty"}, {"probe": "edges", "request": "POST /notes title"}]),
    # Every defect a round raises carries the command it left failing; beside a green suite that is the unit tests'.
    _open(EDGE, status="open", caught_by="dotnet test tests/UnitTests"),
], ids=["merged under the unit tests", "a probe's request among its evidence", "raised with the unit command"])
def test_a_green_sprint_does_not_settle_while_a_probe_finding_is_open(green_suite, open_defect) -> None:
    assert settle_when_green.applies(green_suite, [open_defect], replans=0) is False


def test_a_green_sprint_with_only_failing_unit_tests_open_still_settles_at_its_first_exhaustion(green_suite) -> None:
    """The owner's rule (2026-10-27) is kept: unit tests alone beside a green suite settle the sprint."""
    unit = _open(UNIT, status="open", evidence=[{"test": "ListNotes_Empty"}])
    assert settle_when_green.applies(green_suite, [unit], replans=0) is True


@pytest.fixture(autouse=True)
def _nothing_is_held_between_tests():
    yield
    tests_only_writes.release(RUN, STAGE)


def test_the_first_fix_of_a_probe_finding_merged_under_failing_unit_tests_may_change_the_product(monkeypatch, tmp_path) -> None:
    from app.observability import defect_ledger

    monkeypatch.setenv("TESTS_ONLY_WRITES", "on")
    monkeypatch.setattr(defect_fix_modes, "_the_suite_is_green", lambda state, root: True)
    monkeypatch.setattr(defect_ledger, "note", lambda *args, **kwargs: None)
    cycle = RemediationCycle(sprint_goal="g", defects=[_open(MERGED_UNDER_THE_UNIT_TESTS)])
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "test_round": 2, "current_sprint_index": 0}

    defect_fix_modes.begin(state, {"configurable": {"app_run_id": RUN}}, cycle, 0, STAGE)

    assert not tests_only_writes.holds(RUN, STAGE)


def test_the_fixer_of_a_probe_finding_is_not_told_the_product_already_does_what_the_specification_asks(tmp_path) -> None:
    from app.agents.specialists import build_defect_fix_request
    from workflow_nodes import a_defect, a_fix_stage

    def real_builder(*args, **kwargs):
        return build_defect_fix_request(*args, **kwargs)

    patches = {"app.graph.acceptance_nodes.done_by_the_definition": lambda state: ["AC-1", "AC-2"],
               "app.graph.workflow.build_defect_fix_request": real_builder}
    _, probe = a_fix_stage(tmp_path, [a_defect(MERGED_UNDER_THE_UNIT_TESTS, affected_files=[])], patches=patches)
    _, unit = a_fix_stage(tmp_path, [a_defect(UNIT, affected_files=[])], patches=patches)

    assert "Where the product stands" not in probe["requests"][0]
    assert "Where the product stands" in unit["requests"][0]
